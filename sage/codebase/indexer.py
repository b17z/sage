"""Vector indexing for code using LanceDB.

Provides incremental indexing with mtime tracking, project isolation,
and efficient vector search. Uses Sage's embeddings module for vectors.

Storage layout:
    ~/.sage/codebase/
        lancedb/           # Vector database
        index_meta.json    # File mtimes for incremental updates

    <project>/.sage/codebase/
        compiled/          # Compiled JSON (fast lookup)
        index_meta.json    # Project index state
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sage.codebase.chunker import chunk_file
from sage.codebase.compiler import compile_directory, save_compiled_index
from sage.codebase.models import LANGUAGE_EXTENSIONS, CodeChunk, IndexStats
from sage.config import SAGE_DIR

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Paths
# =============================================================================


def get_codebase_dir(project_path: Path | None = None) -> Path:
    """Get the codebase storage directory.

    Args:
        project_path: Project root. If None, uses global storage.

    Returns:
        Path to codebase directory
    """
    if project_path:
        return project_path / ".sage" / "codebase"
    return SAGE_DIR / "codebase"


def get_lancedb_path() -> Path:
    """Get path to LanceDB storage (global)."""
    return SAGE_DIR / "codebase" / "lancedb"


def get_index_meta_path(project_path: Path | None = None) -> Path:
    """Get path to index metadata file."""
    return get_codebase_dir(project_path) / "index_meta.json"


def get_compiled_dir(project_path: Path | None = None) -> Path:
    """Get path to compiled JSON directory."""
    return get_codebase_dir(project_path) / "compiled"


# =============================================================================
# LanceDB Availability
# =============================================================================


def is_lancedb_available() -> bool:
    """Check if LanceDB is available."""
    try:
        import lancedb  # noqa: F401

        return True
    except ImportError:
        return False


def get_db():
    """Get LanceDB connection.

    Returns:
        LanceDB connection or None if unavailable
    """
    if not is_lancedb_available():
        return None

    import lancedb

    db_path = get_lancedb_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    return lancedb.connect(str(db_path))


# =============================================================================
# Schema
# =============================================================================

# LanceDB table name
CODE_TABLE = "code_chunks"

# Table schema for code chunks
CODE_SCHEMA = {
    "id": "string",
    "file": "string",
    "project": "string",
    "content": "string",
    "chunk_type": "string",
    "name": "string",
    "line_start": "int32",
    "line_end": "int32",
    "language": "string",
    "docstring": "string",
    "signature": "string",
    "parent": "string",
    "vector": "vector[1024]",  # BGE-large dimension
}


def _chunk_to_record(chunk: CodeChunk) -> dict:
    """Convert CodeChunk to LanceDB record."""
    return {
        "id": chunk.id,
        "file": chunk.file,
        "project": chunk.project,
        "content": chunk.content,
        "chunk_type": chunk.chunk_type.value,
        "name": chunk.name,
        "line_start": chunk.line_start,
        "line_end": chunk.line_end,
        "language": chunk.language,
        "docstring": chunk.docstring,
        "signature": chunk.signature,
        "parent": chunk.parent,
        "vector": chunk.embedding,
    }


def _record_to_chunk(record: dict) -> CodeChunk:
    """Convert LanceDB record to CodeChunk."""
    from sage.codebase.models import ChunkType

    return CodeChunk(
        id=record["id"],
        file=record["file"],
        project=record["project"],
        content=record["content"],
        chunk_type=ChunkType(record["chunk_type"]),
        name=record["name"],
        line_start=record["line_start"],
        line_end=record["line_end"],
        language=record["language"],
        docstring=record.get("docstring", ""),
        signature=record.get("signature", ""),
        parent=record.get("parent", ""),
        embedding=list(record.get("vector", [])),
    )


# =============================================================================
# Index Metadata
# =============================================================================


def load_index_meta(project_path: Path | None = None) -> dict:
    """Load index metadata (file mtimes, etc.).

    Args:
        project_path: Project root

    Returns:
        Dict with file mtimes and index state
    """
    meta_path = get_index_meta_path(project_path)
    if not meta_path.exists():
        return {"files": {}, "indexed_at": None, "project": None}

    try:
        return json.loads(meta_path.read_text())
    except Exception:
        return {"files": {}, "indexed_at": None, "project": None}


def save_index_meta(meta: dict, project_path: Path | None = None) -> None:
    """Save index metadata.

    Args:
        meta: Metadata dict
        project_path: Project root
    """
    meta_path = get_index_meta_path(project_path)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, indent=2))


# =============================================================================
# Embedding
# =============================================================================


def embed_chunks(chunks: list[CodeChunk]) -> list[CodeChunk]:
    """Generate embeddings for chunks.

    Args:
        chunks: Chunks to embed

    Returns:
        Chunks with embeddings populated
    """
    from sage import embeddings

    if not embeddings.is_available():
        logger.warning("Embeddings not available, chunks will not be searchable")
        return chunks

    # Build text for embedding (content + context)
    texts = []
    for chunk in chunks:
        # Include context in embedding
        parts = [chunk.content]
        if chunk.docstring:
            parts.append(chunk.docstring)
        if chunk.signature:
            parts.append(chunk.signature)
        texts.append("\n".join(parts))

    # Batch embed
    result = embeddings.get_embeddings_batch(texts)
    if result.is_err():
        logger.warning(f"Failed to embed chunks: {result.unwrap_err().message}")
        return chunks

    vectors = result.unwrap()

    # Create new chunks with embeddings
    embedded = []
    for chunk, vector in zip(chunks, vectors):
        embedded.append(
            CodeChunk(
                id=chunk.id,
                file=chunk.file,
                project=chunk.project,
                content=chunk.content,
                chunk_type=chunk.chunk_type,
                name=chunk.name,
                line_start=chunk.line_start,
                line_end=chunk.line_end,
                language=chunk.language,
                docstring=chunk.docstring,
                signature=chunk.signature,
                parent=chunk.parent,
                embedding=list(vector),
            )
        )

    return embedded


# =============================================================================
# Indexing
# =============================================================================


def detect_project_name(path: Path) -> str:
    """Detect project name from path.

    Tries:
    1. Git remote repo name
    2. pyproject.toml name
    3. package.json name
    4. Directory name

    Args:
        path: Project root path

    Returns:
        Project name string
    """
    import subprocess

    # Try git remote
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=path,
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Extract repo name
            if "/" in url:
                name = url.split("/")[-1].replace(".git", "")
                if name:
                    return name
    except Exception:
        pass

    # Try pyproject.toml
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            for line in content.split("\n"):
                if line.strip().startswith("name") and "=" in line:
                    name = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if name:
                        return name
        except Exception:
            pass

    # Try package.json
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text())
            name = data.get("name", "")
            if name:
                return name
        except Exception:
            pass

    # Fall back to directory name
    return path.name


def index_file(
    file_path: Path,
    project: str,
    project_root: Path,
) -> list[CodeChunk]:
    """Index a single file.

    Args:
        file_path: Path to file
        project: Project identifier
        project_root: Project root for relative paths

    Returns:
        List of indexed chunks (with embeddings)
    """
    chunks = chunk_file(file_path, project, project_root)
    if not chunks:
        return []

    return embed_chunks(chunks)


def index_directory(
    path: Path,
    project: str | None = None,
    extensions: set[str] | None = None,
    exclude_patterns: list[str] | None = None,
    incremental: bool = True,
) -> IndexStats:
    """Index all source files in a directory.

    Args:
        path: Directory to index
        project: Project identifier (auto-detected if None)
        extensions: File extensions to include
        exclude_patterns: Glob patterns to exclude
        incremental: Only re-index changed files

    Returns:
        IndexStats with indexing results
    """
    start_time = time.monotonic()
    path = path.resolve()

    if project is None:
        project = detect_project_name(path)

    if extensions is None:
        extensions = set(LANGUAGE_EXTENSIONS.keys())

    exclude_patterns = exclude_patterns or []
    default_excludes = [
        "**/node_modules/**",
        "**/.git/**",
        "**/venv/**",
        "**/.venv/**",
        "**/dist/**",
        "**/build/**",
        "**/__pycache__/**",
        "**/.pytest_cache/**",
        "**/target/**",
    ]
    exclude_patterns.extend(default_excludes)

    # Load existing metadata
    meta = load_index_meta(path)
    existing_mtimes = meta.get("files", {})

    # Find files to index
    files_to_index: list[Path] = []
    current_files: dict[str, float] = {}
    languages_seen: set[str] = set()

    for ext in extensions:
        for file_path in path.rglob(f"*{ext}"):
            # Check exclusions
            rel_path = str(file_path.relative_to(path))
            excluded = False
            for pattern in exclude_patterns:
                from fnmatch import fnmatch

                if fnmatch(rel_path, pattern):
                    excluded = True
                    break

            if excluded:
                continue

            # Check mtime for incremental
            mtime = file_path.stat().st_mtime
            current_files[rel_path] = mtime

            if incremental and rel_path in existing_mtimes:
                if existing_mtimes[rel_path] >= mtime:
                    continue  # File unchanged

            files_to_index.append(file_path)
            from sage.codebase.models import detect_language

            languages_seen.add(detect_language(file_path))

    logger.info(f"Indexing {len(files_to_index)} files in {path}")

    # Index files
    all_chunks: list[CodeChunk] = []
    for file_path in files_to_index:
        chunks = chunk_file(file_path, project, path)
        all_chunks.extend(chunks)

    # Embed chunks in batches
    if all_chunks:
        all_chunks = embed_chunks(all_chunks)

    # Store in LanceDB
    if is_lancedb_available() and all_chunks:
        _store_chunks(all_chunks, project)

    # Compile index for fast lookup
    compiled = compile_directory(path, project, extensions, exclude_patterns)
    save_compiled_index(compiled, get_compiled_dir(path))

    # Update metadata
    meta["files"] = current_files
    meta["indexed_at"] = datetime.now(UTC).isoformat()
    meta["project"] = project
    save_index_meta(meta, path)

    duration_ms = int((time.monotonic() - start_time) * 1000)

    return IndexStats(
        project=project,
        files_indexed=len(files_to_index),
        chunks_created=len(all_chunks),
        functions_compiled=len(compiled.functions),
        classes_compiled=len(compiled.classes),
        constants_compiled=len(compiled.constants),
        languages=tuple(languages_seen),
        duration_ms=duration_ms,
        indexed_at=meta["indexed_at"],
    )


def _store_chunks(chunks: list[CodeChunk], project: str) -> None:
    """Store chunks in LanceDB.

    Args:
        chunks: Chunks to store (with embeddings)
        project: Project identifier
    """
    if not is_lancedb_available():
        return

    db = get_db()
    if db is None:
        return

    # Convert chunks to records
    records = [_chunk_to_record(chunk) for chunk in chunks if chunk.embedding]

    if not records:
        return

    # Create or update table
    try:
        if CODE_TABLE in db.list_tables():
            table = db.open_table(CODE_TABLE)

            # Delete existing chunks for files being updated
            files = set(r["file"] for r in records)
            for file in files:
                try:
                    table.delete(f'file = "{file}" AND project = "{project}"')
                except Exception:
                    pass  # Table might be empty

            # Add new records
            table.add(records)
        else:
            # Create new table
            db.create_table(CODE_TABLE, records)

        logger.info(f"Stored {len(records)} chunks for project {project}")

    except Exception as e:
        logger.error(f"Failed to store chunks: {e}")


def remove_file(
    file_path: str,
    project: str,
) -> bool:
    """Remove a file from the index.

    Args:
        file_path: Relative file path
        project: Project identifier

    Returns:
        True if file was removed
    """
    if not is_lancedb_available():
        return False

    db = get_db()
    if db is None:
        return False

    try:
        if CODE_TABLE not in db.table_names():
            return False

        table = db.open_table(CODE_TABLE)
        table.delete(f'file = "{file_path}" AND project = "{project}"')
        return True

    except Exception as e:
        logger.error(f"Failed to remove file from index: {e}")
        return False


def remove_project(project: str) -> bool:
    """Remove all chunks for a project.

    Args:
        project: Project identifier

    Returns:
        True if project was removed
    """
    if not is_lancedb_available():
        return False

    db = get_db()
    if db is None:
        return False

    try:
        if CODE_TABLE not in db.table_names():
            return False

        table = db.open_table(CODE_TABLE)
        table.delete(f'project = "{project}"')
        return True

    except Exception as e:
        logger.error(f"Failed to remove project from index: {e}")
        return False


def get_indexed_stats(project: str | None = None) -> dict:
    """Get statistics about indexed code.

    Args:
        project: Optional project filter

    Returns:
        Dict with chunk counts, files, languages
    """
    if not is_lancedb_available():
        return {"available": False}

    db = get_db()
    if db is None:
        return {"available": False}

    try:
        if CODE_TABLE not in db.table_names():
            return {"available": True, "chunks": 0, "files": 0, "projects": []}

        table = db.open_table(CODE_TABLE)

        if project:
            results = table.search().where(f'project = "{project}"').limit(10000).to_list()
        else:
            results = table.search().limit(10000).to_list()

        files = set()
        projects = set()
        languages = set()

        for r in results:
            files.add(r["file"])
            projects.add(r["project"])
            languages.add(r["language"])

        return {
            "available": True,
            "chunks": len(results),
            "files": len(files),
            "projects": list(projects),
            "languages": list(languages),
        }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return {"available": True, "error": str(e)}
