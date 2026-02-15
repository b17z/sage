"""Semantic code search using vector similarity.

Provides:
- search_code(): Semantic/vector search across indexed code
- grep_symbol(): Fast exact lookup from compiled JSON (no vector search)
- analyze_function(): Get full function source with context

Pattern from ethereum-mcp: eth_search, eth_grep_constant, eth_analyze_function.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sage.codebase.compiler import get_function_source, load_compiled_index
from sage.codebase.indexer import (
    CODE_TABLE,
    _record_to_chunk,
    get_compiled_dir,
    get_db,
    is_lancedb_available,
)
from sage.codebase.models import (
    ChunkType,
    CompiledClass,
    CompiledConstant,
    CompiledFunction,
    SearchResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Semantic Search (Vector)
# =============================================================================


def search_code(
    query: str,
    project: str | None = None,
    project_path: Path | None = None,
    limit: int = 10,
    language: str | None = None,
    chunk_types: list[ChunkType] | None = None,
) -> list[SearchResult]:
    """Semantic search over indexed code.

    Uses vector similarity to find code relevant to the query.

    Args:
        query: Natural language query (e.g., "how does authentication work")
        project: Optional project filter
        project_path: Project root for project-local database
        limit: Maximum results
        language: Optional language filter
        chunk_types: Optional chunk type filter

    Returns:
        List of SearchResults sorted by relevance
    """
    from sage import embeddings

    if not is_lancedb_available():
        logger.warning("LanceDB not available. Install with: pip install claude-sage[code]")
        return []

    if not embeddings.is_available():
        logger.warning("Embeddings not available")
        return []

    db = get_db(project_path)
    if db is None:
        return []

    if CODE_TABLE not in db.table_names():
        return []

    # Get query embedding using code-specific model
    result = embeddings.get_code_query_embedding(query)
    if result.is_err():
        logger.warning(f"Failed to embed query: {result.unwrap_err().message}")
        return []

    query_embedding = result.unwrap()

    # Build filter
    filters = []
    if project:
        filters.append(f'project = "{project}"')
    if language:
        filters.append(f'language = "{language}"')
    if chunk_types:
        type_values = [ct.value for ct in chunk_types]
        type_filter = " OR ".join(f'chunk_type = "{t}"' for t in type_values)
        filters.append(f"({type_filter})")

    where_clause = " AND ".join(filters) if filters else None

    # Search
    try:
        table = db.open_table(CODE_TABLE)
        search = table.search(query_embedding.tolist())

        if where_clause:
            search = search.where(where_clause)

        results = search.limit(limit).to_list()

        # Convert to SearchResults
        search_results = []
        for r in results:
            chunk = _record_to_chunk(r)
            score = 1 - r.get("_distance", 0)  # Convert distance to similarity

            # Generate highlights (first few lines of content)
            highlights = _generate_highlights(chunk.content, query)

            search_results.append(
                SearchResult(
                    chunk=chunk,
                    score=score,
                    highlights=tuple(highlights),
                )
            )

        return search_results

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


def _generate_highlights(content: str, query: str) -> list[str]:
    """Generate highlight snippets from content.

    Args:
        content: Code content
        query: Search query

    Returns:
        List of highlight snippets
    """
    lines = content.split("\n")

    # Take first few lines as context
    highlights = []

    # First, get signature or first line
    if lines:
        first_line = lines[0].strip()
        if first_line:
            highlights.append(first_line)

    # Look for query words in content
    query_words = query.lower().split()
    for i, line in enumerate(lines):
        line_lower = line.lower()
        for word in query_words:
            if word in line_lower and len(highlights) < 3:
                snippet = line.strip()
                if snippet and snippet not in highlights:
                    highlights.append(snippet)
                break

    return highlights[:3]


# =============================================================================
# Fast Symbol Lookup (Compiled JSON)
# =============================================================================


def grep_symbol(
    name: str,
    project_path: Path | None = None,
) -> CompiledFunction | CompiledClass | CompiledConstant | None:
    """Fast exact symbol lookup from compiled index.

    No vector search - directly looks up in compiled JSON.
    Pattern from ethereum-mcp: eth_grep_constant.

    Args:
        name: Symbol name to find
        project_path: Project root

    Returns:
        Compiled symbol metadata or None
    """
    compiled_dir = get_compiled_dir(project_path)
    index = load_compiled_index(compiled_dir)

    if index is None:
        return None

    # Try function first (most common)
    fn = index.lookup_function(name)
    if fn:
        return fn

    # Try class
    cls = index.lookup_class(name)
    if cls:
        return cls

    # Try constant
    const = index.lookup_constant(name)
    if const:
        return const

    return None


def grep_function(
    name: str,
    project_path: Path | None = None,
) -> CompiledFunction | None:
    """Fast exact function lookup.

    Args:
        name: Function name
        project_path: Project root

    Returns:
        CompiledFunction or None
    """
    compiled_dir = get_compiled_dir(project_path)
    index = load_compiled_index(compiled_dir)

    if index is None:
        return None

    return index.lookup_function(name)


def grep_class(
    name: str,
    project_path: Path | None = None,
) -> CompiledClass | None:
    """Fast exact class lookup.

    Args:
        name: Class name
        project_path: Project root

    Returns:
        CompiledClass or None
    """
    compiled_dir = get_compiled_dir(project_path)
    index = load_compiled_index(compiled_dir)

    if index is None:
        return None

    return index.lookup_class(name)


def grep_constant(
    name: str,
    project_path: Path | None = None,
) -> CompiledConstant | None:
    """Fast exact constant lookup.

    Args:
        name: Constant name
        project_path: Project root

    Returns:
        CompiledConstant or None
    """
    compiled_dir = get_compiled_dir(project_path)
    index = load_compiled_index(compiled_dir)

    if index is None:
        return None

    return index.lookup_constant(name)


# =============================================================================
# Function Analysis
# =============================================================================


def analyze_function(
    name: str,
    project_path: Path,
) -> dict | None:
    """Get full function source with context.

    Pattern from ethereum-mcp: eth_analyze_function.

    Args:
        name: Function name
        project_path: Project root

    Returns:
        Dict with function details and source, or None
    """
    compiled_dir = get_compiled_dir(project_path)
    index = load_compiled_index(compiled_dir)

    if index is None:
        return None

    fn = index.lookup_function(name)
    if fn is None:
        return None

    # Get source code
    source = get_function_source(name, index, project_path)

    return {
        "name": fn.name,
        "signature": fn.signature,
        "file": fn.file,
        "line": fn.line,
        "docstring": fn.docstring,
        "is_method": fn.is_method,
        "parent_class": fn.parent_class,
        "source": source,
    }


def list_functions(
    project_path: Path | None = None,
    filter_pattern: str | None = None,
) -> list[CompiledFunction]:
    """List all indexed functions.

    Args:
        project_path: Project root
        filter_pattern: Optional name filter (substring match)

    Returns:
        List of CompiledFunctions
    """
    compiled_dir = get_compiled_dir(project_path)
    index = load_compiled_index(compiled_dir)

    if index is None:
        return []

    functions = list(index.functions)

    if filter_pattern:
        pattern_lower = filter_pattern.lower()
        functions = [f for f in functions if pattern_lower in f.name.lower()]

    return functions


def list_classes(
    project_path: Path | None = None,
    filter_pattern: str | None = None,
) -> list[CompiledClass]:
    """List all indexed classes.

    Args:
        project_path: Project root
        filter_pattern: Optional name filter

    Returns:
        List of CompiledClasses
    """
    compiled_dir = get_compiled_dir(project_path)
    index = load_compiled_index(compiled_dir)

    if index is None:
        return []

    classes = list(index.classes)

    if filter_pattern:
        pattern_lower = filter_pattern.lower()
        classes = [c for c in classes if pattern_lower in c.name.lower()]

    return classes


# =============================================================================
# Multi-Source Search
# =============================================================================


def search_all(
    query: str,
    project_path: Path | None = None,
    limit: int = 10,
) -> dict:
    """Search across both vector and compiled indexes.

    Combines:
    - Semantic search (vector similarity)
    - Exact symbol matches (compiled JSON)

    Deduplicates by (file, line).

    Args:
        query: Search query
        project_path: Project root
        limit: Maximum results

    Returns:
        Dict with semantic_results, exact_matches, combined
    """
    from sage.codebase.indexer import detect_project_name

    # Detect project
    project = None
    if project_path:
        project = detect_project_name(project_path)

    # Semantic search
    semantic_results = search_code(query, project=project, project_path=project_path, limit=limit)

    # Try exact lookup (in case query is a symbol name)
    exact_match = grep_symbol(query, project_path)

    # Combine and dedupe
    seen = set()
    combined = []

    # Exact match first if found
    if exact_match:
        key = (getattr(exact_match, "file", ""), getattr(exact_match, "line", 0))
        if key not in seen:
            seen.add(key)
            combined.append(
                {
                    "type": "exact",
                    "name": exact_match.name,
                    "file": exact_match.file,
                    "line": getattr(exact_match, "line", 0),
                    "score": 1.0,
                }
            )

    # Then semantic results
    for sr in semantic_results:
        key = (sr.chunk.file, sr.chunk.line_start)
        if key not in seen:
            seen.add(key)
            combined.append(
                {
                    "type": "semantic",
                    "name": sr.chunk.name,
                    "file": sr.chunk.file,
                    "line": sr.chunk.line_start,
                    "score": sr.score,
                    "highlights": sr.highlights,
                }
            )

    return {
        "semantic_results": semantic_results,
        "exact_match": exact_match,
        "combined": combined[:limit],
    }
