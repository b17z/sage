"""Codebase indexing and semantic search for Sage.

Provides AST-aware code chunking, vector storage via LanceDB, and semantic search
for code understanding. Includes core file marking for session-start injection.

Based on patterns from ethereum-mcp for proven RAG architecture.

Usage:
    from sage.codebase import index_directory, search_code, grep_symbol

Optional dependencies:
    pip install claude-sage[code]
"""

from sage.codebase.chunker import (
    chunk_file,
    chunk_source,
    is_treesitter_available,
)
from sage.codebase.compiler import (
    compile_directory,
    compile_file,
    load_compiled_index,
    save_compiled_index,
)
from sage.codebase.core_files import (
    get_core_context,
    get_core_file,
    list_core,
    mark_core,
    unmark_core,
)
from sage.codebase.indexer import (
    get_indexed_stats,
    index_directory,
    index_file,
    is_lancedb_available,
    remove_file,
    remove_project,
)
from sage.codebase.models import (
    ChunkType,
    CodeChunk,
    CompiledClass,
    CompiledConstant,
    CompiledFunction,
    CompiledIndex,
    CoreFile,
    IndexStats,
    SearchResult,
    detect_language,
)
from sage.codebase.search import (
    analyze_function,
    grep_class,
    grep_constant,
    grep_function,
    grep_symbol,
    list_classes,
    list_functions,
    search_all,
    search_code,
)

__all__ = [
    # Models
    "ChunkType",
    "CodeChunk",
    "CompiledFunction",
    "CompiledClass",
    "CompiledConstant",
    "CompiledIndex",
    "CoreFile",
    "IndexStats",
    "SearchResult",
    "detect_language",
    # Chunking
    "chunk_file",
    "chunk_source",
    "is_treesitter_available",
    # Compilation
    "compile_directory",
    "compile_file",
    "load_compiled_index",
    "save_compiled_index",
    # Indexing
    "index_directory",
    "index_file",
    "remove_file",
    "remove_project",
    "get_indexed_stats",
    "is_lancedb_available",
    # Search
    "search_code",
    "search_all",
    "grep_symbol",
    "grep_function",
    "grep_class",
    "grep_constant",
    "analyze_function",
    "list_functions",
    "list_classes",
    # Core files
    "mark_core",
    "unmark_core",
    "list_core",
    "get_core_file",
    "get_core_context",
]
