"""Compile structured metadata from code for fast symbol lookup.

Extracts functions, classes, and constants into JSON format for direct
lookup without vector search. Pattern from ethereum-mcp: eth_grep_constant.

The compiled index enables:
- Fast exact symbol lookup: grep_symbol("get_embedding")
- Function source retrieval: analyze_function("save_checkpoint")
- Class method listing
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sage.codebase.chunker import extract_nodes_ast
from sage.codebase.models import (
    ChunkType,
    CompiledClass,
    CompiledConstant,
    CompiledFunction,
    CompiledIndex,
    detect_language,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Path Matching
# =============================================================================


def matches_exclude_pattern(rel_path: str, pattern: str) -> bool:
    """Check if a path matches an exclude pattern.

    Supports **/ and /** glob patterns:
    - **/dirname/** matches dirname anywhere in path
    - dirname/** matches dirname at start
    - Standard fnmatch patterns otherwise

    Args:
        rel_path: Relative file path
        pattern: Glob pattern (may include **)

    Returns:
        True if path matches the exclude pattern
    """
    from fnmatch import fnmatch
    from pathlib import PurePath

    # Handle ** patterns by checking path parts
    if "**" in pattern:
        # Strip leading/trailing **/ and /**
        core = pattern.replace("**/", "").replace("/**", "")
        # Check if core appears as a path component
        return core in PurePath(rel_path).parts

    # For non-** patterns, use fnmatch
    return fnmatch(rel_path, pattern)


# =============================================================================
# Compilation
# =============================================================================


def compile_file(
    file_path: Path,
    project_root: Path | None = None,
) -> tuple[list[CompiledFunction], list[CompiledClass], list[CompiledConstant]]:
    """Compile a single file into structured metadata.

    Args:
        file_path: Path to source file
        project_root: Root for relative paths

    Returns:
        Tuple of (functions, classes, constants)
    """
    if not file_path.exists():
        return [], [], []

    # Calculate relative path
    if project_root:
        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = file_path.name
    else:
        rel_path = file_path.name

    # Read source
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Failed to read {file_path}: {e}")
        return [], [], []

    language = detect_language(file_path)
    nodes = extract_nodes_ast(source, language)

    functions: list[CompiledFunction] = []
    classes: list[CompiledClass] = []
    constants: list[CompiledConstant] = []

    # Track class methods for aggregation
    class_methods: dict[str, list[str]] = {}

    for node in nodes:
        if node.chunk_type == ChunkType.FUNCTION:
            functions.append(
                CompiledFunction(
                    name=node.name,
                    signature=node.signature or f"def {node.name}(...)",
                    file=rel_path,
                    line=node.line_start,
                    docstring=node.docstring,
                    is_method=False,
                    parent_class="",
                )
            )

        elif node.chunk_type == ChunkType.METHOD:
            functions.append(
                CompiledFunction(
                    name=node.name,
                    signature=node.signature or f"def {node.name}(...)",
                    file=rel_path,
                    line=node.line_start,
                    docstring=node.docstring,
                    is_method=True,
                    parent_class=node.parent,
                )
            )
            # Track for class aggregation
            if node.parent:
                class_methods.setdefault(node.parent, []).append(node.name)

        elif node.chunk_type == ChunkType.CLASS:
            classes.append(
                CompiledClass(
                    name=node.name,
                    file=rel_path,
                    line=node.line_start,
                    methods=(),  # Will be filled later
                    bases=(),  # TODO: extract from AST
                    docstring=node.docstring,
                )
            )

        elif node.chunk_type == ChunkType.CONSTANT:
            # Extract value from content (first line after name =)
            value = ""
            if "=" in node.content:
                parts = node.content.split("=", 1)
                if len(parts) > 1:
                    value = parts[1].strip()[:100]  # Truncate long values

            constants.append(
                CompiledConstant(
                    name=node.name,
                    value=value,
                    file=rel_path,
                    line=node.line_start,
                )
            )

    # Update classes with their methods
    updated_classes = []
    for cls in classes:
        methods = tuple(class_methods.get(cls.name, []))
        updated_classes.append(
            CompiledClass(
                name=cls.name,
                file=cls.file,
                line=cls.line,
                methods=methods,
                bases=cls.bases,
                docstring=cls.docstring,
            )
        )

    return functions, updated_classes, constants


def compile_directory(
    path: Path,
    project: str,
    extensions: set[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> CompiledIndex:
    """Compile all source files in a directory.

    Args:
        path: Directory to compile
        project: Project identifier
        extensions: File extensions to include (default: all known)
        exclude_patterns: Glob patterns to exclude (e.g., ["**/test_*"])

    Returns:
        CompiledIndex with all extracted metadata
    """
    from sage.codebase.models import LANGUAGE_EXTENSIONS

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
        "**/target/**",  # Rust
    ]
    exclude_patterns.extend(default_excludes)

    all_functions: list[CompiledFunction] = []
    all_classes: list[CompiledClass] = []
    all_constants: list[CompiledConstant] = []

    # Find all source files
    for ext in extensions:
        for file_path in path.rglob(f"*{ext}"):
            # Check exclusions
            rel_path = str(file_path.relative_to(path))
            excluded = any(
                matches_exclude_pattern(rel_path, pattern)
                for pattern in exclude_patterns
            )

            if excluded:
                continue

            # Compile file
            funcs, classes, consts = compile_file(file_path, project_root=path)
            all_functions.extend(funcs)
            all_classes.extend(classes)
            all_constants.extend(consts)

    return CompiledIndex(
        project=project,
        functions=tuple(all_functions),
        classes=tuple(all_classes),
        constants=tuple(all_constants),
        compiled_at=datetime.now(UTC).isoformat(),
    )


# =============================================================================
# Persistence
# =============================================================================


def _compiled_index_to_dict(index: CompiledIndex) -> dict:
    """Convert CompiledIndex to JSON-serializable dict."""
    return {
        "project": index.project,
        "compiled_at": index.compiled_at,
        "functions": [
            {
                "name": fn.name,
                "signature": fn.signature,
                "file": fn.file,
                "line": fn.line,
                "docstring": fn.docstring,
                "is_method": fn.is_method,
                "parent_class": fn.parent_class,
            }
            for fn in index.functions
        ],
        "classes": [
            {
                "name": cls.name,
                "file": cls.file,
                "line": cls.line,
                "methods": list(cls.methods),
                "bases": list(cls.bases),
                "docstring": cls.docstring,
            }
            for cls in index.classes
        ],
        "constants": [
            {
                "name": const.name,
                "value": const.value,
                "file": const.file,
                "line": const.line,
                "type_hint": const.type_hint,
            }
            for const in index.constants
        ],
    }


def _dict_to_compiled_index(data: dict) -> CompiledIndex:
    """Convert dict to CompiledIndex."""
    return CompiledIndex(
        project=data.get("project", ""),
        compiled_at=data.get("compiled_at", ""),
        functions=tuple(
            CompiledFunction(
                name=fn["name"],
                signature=fn["signature"],
                file=fn["file"],
                line=fn["line"],
                docstring=fn.get("docstring", ""),
                is_method=fn.get("is_method", False),
                parent_class=fn.get("parent_class", ""),
            )
            for fn in data.get("functions", [])
        ),
        classes=tuple(
            CompiledClass(
                name=cls["name"],
                file=cls["file"],
                line=cls["line"],
                methods=tuple(cls.get("methods", [])),
                bases=tuple(cls.get("bases", [])),
                docstring=cls.get("docstring", ""),
            )
            for cls in data.get("classes", [])
        ),
        constants=tuple(
            CompiledConstant(
                name=const["name"],
                value=const["value"],
                file=const["file"],
                line=const["line"],
                type_hint=const.get("type_hint", ""),
            )
            for const in data.get("constants", [])
        ),
    )


def save_compiled_index(index: CompiledIndex, output_dir: Path) -> Path:
    """Save compiled index to JSON files.

    Creates:
        output_dir/functions.json
        output_dir/classes.json
        output_dir/constants.json
        output_dir/meta.json

    Args:
        index: The compiled index
        output_dir: Directory to save to

    Returns:
        Path to the meta.json file
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    data = _compiled_index_to_dict(index)

    # Save separate files for faster loading
    (output_dir / "functions.json").write_text(
        json.dumps(data["functions"], indent=2, ensure_ascii=False)
    )
    (output_dir / "classes.json").write_text(
        json.dumps(data["classes"], indent=2, ensure_ascii=False)
    )
    (output_dir / "constants.json").write_text(
        json.dumps(data["constants"], indent=2, ensure_ascii=False)
    )

    # Meta file with project info
    meta = {
        "project": data["project"],
        "compiled_at": data["compiled_at"],
        "counts": {
            "functions": len(data["functions"]),
            "classes": len(data["classes"]),
            "constants": len(data["constants"]),
        },
    }
    meta_path = output_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2))

    return meta_path


def load_compiled_index(input_dir: Path) -> CompiledIndex | None:
    """Load compiled index from JSON files.

    Args:
        input_dir: Directory containing compiled JSON

    Returns:
        CompiledIndex or None if not found
    """
    meta_path = input_dir / "meta.json"
    if not meta_path.exists():
        return None

    try:
        meta = json.loads(meta_path.read_text())

        functions = []
        funcs_path = input_dir / "functions.json"
        if funcs_path.exists():
            functions = json.loads(funcs_path.read_text())

        classes = []
        classes_path = input_dir / "classes.json"
        if classes_path.exists():
            classes = json.loads(classes_path.read_text())

        constants = []
        consts_path = input_dir / "constants.json"
        if consts_path.exists():
            constants = json.loads(consts_path.read_text())

        return _dict_to_compiled_index(
            {
                "project": meta.get("project", ""),
                "compiled_at": meta.get("compiled_at", ""),
                "functions": functions,
                "classes": classes,
                "constants": constants,
            }
        )
    except Exception as e:
        logger.warning(f"Failed to load compiled index from {input_dir}: {e}")
        return None


# =============================================================================
# Lookup API
# =============================================================================


def lookup_function(name: str, index: CompiledIndex) -> CompiledFunction | None:
    """Fast exact-match function lookup.

    Args:
        name: Function name to find
        index: Compiled index to search

    Returns:
        CompiledFunction or None
    """
    return index.lookup_function(name)


def lookup_class(name: str, index: CompiledIndex) -> CompiledClass | None:
    """Fast exact-match class lookup.

    Args:
        name: Class name to find
        index: Compiled index to search

    Returns:
        CompiledClass or None
    """
    return index.lookup_class(name)


def lookup_constant(name: str, index: CompiledIndex) -> CompiledConstant | None:
    """Fast exact-match constant lookup.

    Args:
        name: Constant name to find
        index: Compiled index to search

    Returns:
        CompiledConstant or None
    """
    return index.lookup_constant(name)


def get_function_source(
    name: str,
    index: CompiledIndex,
    project_root: Path,
) -> str | None:
    """Get the full source code of a function.

    Args:
        name: Function name
        index: Compiled index
        project_root: Project root for file resolution

    Returns:
        Function source code or None
    """
    fn = index.lookup_function(name)
    if fn is None:
        return None

    file_path = project_root / fn.file
    if not file_path.exists():
        return None

    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
        lines = source.split("\n")

        # Find the function and extract it
        # For simplicity, use the same AST extraction
        language = detect_language(file_path)
        nodes = extract_nodes_ast(source, language)

        for node in nodes:
            if node.name == name and node.line_start == fn.line:
                return node.content

        # Fallback: return lines from known start
        # Try to find function end by indentation (Python) or braces
        start_idx = fn.line - 1
        if start_idx >= len(lines):
            return None

        # Simple heuristic: take next 50 lines or until we find a new definition
        end_idx = min(start_idx + 50, len(lines))
        return "\n".join(lines[start_idx:end_idx])

    except Exception as e:
        logger.warning(f"Failed to get function source for {name}: {e}")
        return None
