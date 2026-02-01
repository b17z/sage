"""Data models for codebase indexing and search.

All models are frozen dataclasses for immutability.
Uses patterns consistent with sage/checkpoint.py and sage/knowledge.py.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ChunkType(str, Enum):
    """Type of code chunk extracted from source."""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"  # Top-level module docstring/imports
    CONSTANT = "constant"
    TYPE = "type"  # Type alias, interface, struct
    FALLBACK = "fallback"  # Character-based chunking for unsupported languages


@dataclass(frozen=True)
class CodeChunk:
    """A semantic chunk of code for embedding and search.

    Each chunk represents a logical unit of code (function, class, etc.)
    with enough context for meaningful retrieval.
    """

    # Identity
    id: str  # Unique ID: "{file_hash}:{line_start}:{name}"
    file: str  # Relative path from project root
    project: str  # Project identifier

    # Content
    content: str  # The actual code content
    chunk_type: ChunkType
    name: str  # Symbol name (function name, class name, etc.)

    # Location
    line_start: int
    line_end: int

    # Metadata
    language: str  # Programming language
    docstring: str = ""  # Extracted docstring if available
    signature: str = ""  # Function/method signature if available
    parent: str = ""  # Parent class/module name if applicable

    # Vector (set after embedding)
    embedding: list[float] = field(default_factory=list)


@dataclass(frozen=True)
class CompiledFunction:
    """Extracted function metadata for fast lookup.

    Stored in compiled JSON for symbol lookup without vector search.
    Pattern from ethereum-mcp: eth_grep_constant, eth_analyze_function.
    """

    name: str
    signature: str
    file: str  # Relative path
    line: int
    docstring: str = ""
    is_method: bool = False
    parent_class: str = ""


@dataclass(frozen=True)
class CompiledClass:
    """Extracted class metadata for fast lookup."""

    name: str
    file: str
    line: int
    methods: tuple[str, ...] = ()  # Method names
    bases: tuple[str, ...] = ()  # Base class names
    docstring: str = ""


@dataclass(frozen=True)
class CompiledConstant:
    """Extracted constant metadata for fast lookup."""

    name: str
    value: str  # String representation of value
    file: str
    line: int
    type_hint: str = ""  # Type annotation if available


@dataclass(frozen=True)
class CompiledIndex:
    """Complete compiled index for a project.

    Stored as JSON for fast symbol lookup without vector search.
    """

    project: str
    functions: tuple[CompiledFunction, ...] = ()
    classes: tuple[CompiledClass, ...] = ()
    constants: tuple[CompiledConstant, ...] = ()
    compiled_at: str = ""  # ISO timestamp

    def lookup_function(self, name: str) -> CompiledFunction | None:
        """Fast exact-match function lookup."""
        for fn in self.functions:
            if fn.name == name:
                return fn
        return None

    def lookup_class(self, name: str) -> CompiledClass | None:
        """Fast exact-match class lookup."""
        for cls in self.classes:
            if cls.name == name:
                return cls
        return None

    def lookup_constant(self, name: str) -> CompiledConstant | None:
        """Fast exact-match constant lookup."""
        for const in self.constants:
            if const.name == name:
                return const
        return None


@dataclass(frozen=True)
class CoreFile:
    """A file marked for session-start context injection.

    Core files are automatically injected into context when starting
    a session in a project, providing immediate codebase awareness.
    """

    path: str  # Relative path from project root
    project: str
    summary: str = ""  # Brief description of what this file does
    marked_at: str = ""  # ISO timestamp


@dataclass(frozen=True)
class IndexStats:
    """Statistics from an indexing operation."""

    project: str
    files_indexed: int
    chunks_created: int
    functions_compiled: int
    classes_compiled: int
    constants_compiled: int
    languages: tuple[str, ...] = ()
    duration_ms: int = 0
    indexed_at: str = ""


@dataclass(frozen=True)
class SearchResult:
    """A code search result with relevance score."""

    chunk: CodeChunk
    score: float  # Similarity score (0-1)
    highlights: tuple[str, ...] = ()  # Matching snippets for display


# Language detection mapping
LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".pyx": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".sol": "solidity",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".c": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".m": "objective-c",
    ".mm": "objective-c",
    ".scala": "scala",
    ".lua": "lua",
    ".r": "r",
    ".R": "r",
    ".jl": "julia",
    ".hs": "haskell",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".clj": "clojure",
    ".ml": "ocaml",
    ".php": "php",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".ps1": "powershell",
    ".sql": "sql",
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".json": "json",
    ".md": "markdown",
    ".rst": "rst",
    ".tex": "latex",
    ".vue": "vue",
    ".svelte": "svelte",
}


def detect_language(file_path: str | Path) -> str:
    """Detect programming language from file extension.

    Args:
        file_path: Path to the file

    Returns:
        Language identifier string, or "unknown" if not recognized
    """
    path = Path(file_path) if isinstance(file_path, str) else file_path
    ext = path.suffix.lower()
    return LANGUAGE_EXTENSIONS.get(ext, "unknown")
