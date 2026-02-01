"""AST-aware code chunking using tree-sitter.

Extracts semantic code units (functions, classes, methods) with context
for meaningful embedding and retrieval. Falls back to character-based
chunking for unsupported languages.

Uses tree-sitter-languages for pre-compiled grammars (50+ languages).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from sage.codebase.models import ChunkType, CodeChunk, detect_language

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Tree-sitter Availability
# =============================================================================


def is_treesitter_available() -> bool:
    """Check if tree-sitter-languages is available."""
    try:
        import tree_sitter_languages  # noqa: F401

        return True
    except ImportError:
        return False


def get_parser(language: str):
    """Get a tree-sitter parser for a language.

    Args:
        language: Language identifier (e.g., "python", "typescript")

    Returns:
        Parser instance, or None if language not supported
    """
    if not is_treesitter_available():
        return None

    try:
        import tree_sitter_languages

        return tree_sitter_languages.get_parser(language)
    except Exception:
        return None


# =============================================================================
# Language-specific Node Types
# =============================================================================

# Tree-sitter node types for semantic extraction by language
LANGUAGE_NODE_TYPES: dict[str, dict[str, list[str]]] = {
    "python": {
        "function": ["function_definition"],
        "class": ["class_definition"],
        "method": ["function_definition"],  # Methods are functions inside classes
        "constant": ["assignment"],  # Top-level assignments (UPPER_CASE = ...)
        "type": ["type_alias_statement"],
    },
    "typescript": {
        "function": ["function_declaration", "arrow_function", "function_expression"],
        "class": ["class_declaration"],
        "method": ["method_definition"],
        "constant": ["lexical_declaration"],  # const declarations
        "type": ["type_alias_declaration", "interface_declaration"],
    },
    "javascript": {
        "function": ["function_declaration", "arrow_function", "function_expression"],
        "class": ["class_declaration"],
        "method": ["method_definition"],
        "constant": ["lexical_declaration"],
        "type": [],
    },
    "solidity": {
        "function": ["function_definition"],
        "class": ["contract_definition", "interface_definition", "library_definition"],
        "method": ["function_definition"],
        "constant": ["state_variable_declaration"],
        "type": ["struct_definition", "enum_definition"],
    },
    "go": {
        "function": ["function_declaration"],
        "class": [],  # Go doesn't have classes
        "method": ["method_declaration"],
        "constant": ["const_declaration"],
        "type": ["type_declaration"],
    },
    "rust": {
        "function": ["function_item"],
        "class": ["impl_item"],  # impl blocks serve as method containers
        "method": ["function_item"],  # Methods are functions in impl blocks
        "constant": ["const_item", "static_item"],
        "type": ["struct_item", "enum_item", "trait_item", "type_item"],
    },
}


# =============================================================================
# Chunking Parameters
# =============================================================================

# Fallback chunking parameters (for unsupported languages)
FALLBACK_CHUNK_SIZE = 1500  # Characters per chunk
FALLBACK_OVERLAP = 200  # Overlap between chunks

# Maximum chunk size (truncate very long functions)
MAX_CHUNK_SIZE = 8000  # Characters

# Minimum chunk size (skip very short chunks)
MIN_CHUNK_SIZE = 50  # Characters


# =============================================================================
# Chunk ID Generation
# =============================================================================


def generate_chunk_id(file: str, line_start: int, name: str) -> str:
    """Generate a unique chunk ID.

    Format: {file_hash[:8]}:{line_start}:{name}
    """
    file_hash = hashlib.sha256(file.encode()).hexdigest()[:8]
    # Sanitize name for ID
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)[:50]
    return f"{file_hash}:{line_start}:{safe_name}"


# =============================================================================
# AST-based Chunking
# =============================================================================


@dataclass
class ExtractedNode:
    """A node extracted from AST for chunking."""

    name: str
    content: str
    chunk_type: ChunkType
    line_start: int
    line_end: int
    docstring: str = ""
    signature: str = ""
    parent: str = ""


def _get_node_text(node, source_bytes: bytes) -> str:
    """Get the text content of a tree-sitter node."""
    return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _extract_python_docstring(node, source_bytes: bytes) -> str:
    """Extract docstring from a Python function/class definition."""
    # Look for expression_statement > string as first child of body
    for child in node.children:
        if child.type == "block":
            for block_child in child.children:
                if block_child.type == "expression_statement":
                    for expr_child in block_child.children:
                        if expr_child.type == "string":
                            text = _get_node_text(expr_child, source_bytes)
                            # Strip quotes
                            if text.startswith('"""') or text.startswith("'''"):
                                return text[3:-3].strip()
                            elif text.startswith('"') or text.startswith("'"):
                                return text[1:-1].strip()
                    break  # Only check first statement
            break
    return ""


def _extract_python_signature(node, source_bytes: bytes) -> str:
    """Extract function signature from a Python function definition."""
    # Look for name and parameters
    name = ""
    params = ""
    return_type = ""

    for child in node.children:
        if child.type == "name":
            name = _get_node_text(child, source_bytes)
        elif child.type == "parameters":
            params = _get_node_text(child, source_bytes)
        elif child.type == "type":
            return_type = " -> " + _get_node_text(child, source_bytes)

    if name:
        return f"def {name}{params}{return_type}"
    return ""


def _extract_python_nodes(tree, source_bytes: bytes, source: str) -> list[ExtractedNode]:
    """Extract semantic nodes from Python AST."""
    nodes = []

    def get_parent_class(node) -> str:
        """Walk up to find parent class name."""
        parent = node.parent
        while parent:
            if parent.type == "class_definition":
                for child in parent.children:
                    if child.type == "name":
                        return _get_node_text(child, source_bytes)
            parent = parent.parent
        return ""

    def visit(node, depth=0):
        if node.type == "function_definition":
            name = ""
            for child in node.children:
                if child.type == "name":
                    name = _get_node_text(child, source_bytes)
                    break

            parent_class = get_parent_class(node)
            chunk_type = ChunkType.METHOD if parent_class else ChunkType.FUNCTION

            nodes.append(
                ExtractedNode(
                    name=name,
                    content=_get_node_text(node, source_bytes),
                    chunk_type=chunk_type,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    docstring=_extract_python_docstring(node, source_bytes),
                    signature=_extract_python_signature(node, source_bytes),
                    parent=parent_class,
                )
            )

        elif node.type == "class_definition":
            name = ""
            for child in node.children:
                if child.type == "name":
                    name = _get_node_text(child, source_bytes)
                    break

            nodes.append(
                ExtractedNode(
                    name=name,
                    content=_get_node_text(node, source_bytes),
                    chunk_type=ChunkType.CLASS,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    docstring=_extract_python_docstring(node, source_bytes),
                    signature=f"class {name}",
                    parent="",
                )
            )

        # Recurse into children
        for child in node.children:
            visit(child, depth + 1)

    visit(tree.root_node)
    return nodes


def _extract_js_ts_nodes(tree, source_bytes: bytes, source: str) -> list[ExtractedNode]:
    """Extract semantic nodes from JavaScript/TypeScript AST."""
    nodes = []

    def get_name(node) -> str:
        """Extract name from a node."""
        for child in node.children:
            if child.type in ("identifier", "property_identifier"):
                return _get_node_text(child, source_bytes)
        return ""

    def visit(node, parent_name=""):
        content = _get_node_text(node, source_bytes)

        if node.type in ("function_declaration", "function_expression"):
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.FUNCTION,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_name,
                )
            )

        elif node.type == "arrow_function":
            # Try to get name from variable declaration
            name = parent_name or "anonymous"
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.FUNCTION,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
            )

        elif node.type == "class_declaration":
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.CLASS,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
            )
            # Visit children with class as parent
            for child in node.children:
                visit(child, name)
            return  # Don't recurse again

        elif node.type == "method_definition":
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.METHOD,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=parent_name,
                )
            )

        elif node.type in ("interface_declaration", "type_alias_declaration"):
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.TYPE,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
            )

        elif node.type == "lexical_declaration":
            # Check if it's a named arrow function
            for child in node.children:
                if child.type == "variable_declarator":
                    var_name = get_name(child)
                    for sub in child.children:
                        if sub.type == "arrow_function":
                            nodes.append(
                                ExtractedNode(
                                    name=var_name,
                                    content=content,
                                    chunk_type=ChunkType.FUNCTION,
                                    line_start=node.start_point[0] + 1,
                                    line_end=node.end_point[0] + 1,
                                )
                            )
                            return  # Already handled

        # Recurse
        for child in node.children:
            visit(child, parent_name)

    visit(tree.root_node)
    return nodes


def _extract_go_nodes(tree, source_bytes: bytes, source: str) -> list[ExtractedNode]:
    """Extract semantic nodes from Go AST."""
    nodes = []

    def get_name(node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return _get_node_text(child, source_bytes)
        return ""

    def visit(node):
        content = _get_node_text(node, source_bytes)

        if node.type == "function_declaration":
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.FUNCTION,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
            )

        elif node.type == "method_declaration":
            name = get_name(node)
            # Get receiver type as parent
            receiver = ""
            for child in node.children:
                if child.type == "parameter_list":
                    receiver = _get_node_text(child, source_bytes)
                    break
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.METHOD,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=receiver,
                )
            )

        elif node.type == "type_declaration":
            # Handle struct, interface definitions
            for child in node.children:
                if child.type == "type_spec":
                    name = get_name(child)
                    nodes.append(
                        ExtractedNode(
                            name=name,
                            content=content,
                            chunk_type=ChunkType.TYPE,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                        )
                    )
                    break

        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return nodes


def _extract_rust_nodes(tree, source_bytes: bytes, source: str) -> list[ExtractedNode]:
    """Extract semantic nodes from Rust AST."""
    nodes = []
    current_impl = ""

    def get_name(node) -> str:
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return _get_node_text(child, source_bytes)
        return ""

    def visit(node, impl_name=""):
        nonlocal current_impl
        content = _get_node_text(node, source_bytes)

        if node.type == "function_item":
            name = get_name(node)
            is_method = bool(impl_name)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.METHOD if is_method else ChunkType.FUNCTION,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=impl_name,
                )
            )

        elif node.type == "impl_item":
            # Get the type being implemented
            impl_type = ""
            for child in node.children:
                if child.type == "type_identifier":
                    impl_type = _get_node_text(child, source_bytes)
                    break
            # Visit children with impl context
            for child in node.children:
                visit(child, impl_type)
            return

        elif node.type in ("struct_item", "enum_item"):
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.TYPE,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
            )

        elif node.type == "trait_item":
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.TYPE,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
            )

        for child in node.children:
            visit(child, impl_name)

    visit(tree.root_node)
    return nodes


def _extract_solidity_nodes(tree, source_bytes: bytes, source: str) -> list[ExtractedNode]:
    """Extract semantic nodes from Solidity AST."""
    nodes = []

    def get_name(node) -> str:
        for child in node.children:
            if child.type == "identifier":
                return _get_node_text(child, source_bytes)
        return ""

    def visit(node, contract_name=""):
        content = _get_node_text(node, source_bytes)

        if node.type in ("contract_definition", "interface_definition", "library_definition"):
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.CLASS,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                )
            )
            # Visit children with contract context
            for child in node.children:
                visit(child, name)
            return

        elif node.type == "function_definition":
            name = get_name(node) or "fallback"
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.METHOD if contract_name else ChunkType.FUNCTION,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=contract_name,
                )
            )

        elif node.type in ("struct_definition", "enum_definition"):
            name = get_name(node)
            nodes.append(
                ExtractedNode(
                    name=name,
                    content=content,
                    chunk_type=ChunkType.TYPE,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    parent=contract_name,
                )
            )

        for child in node.children:
            visit(child, contract_name)

    visit(tree.root_node)
    return nodes


def extract_nodes_ast(source: str, language: str) -> list[ExtractedNode]:
    """Extract semantic nodes from source code using tree-sitter.

    Args:
        source: Source code content
        language: Programming language identifier

    Returns:
        List of extracted nodes, or empty list if parsing fails
    """
    if not is_treesitter_available():
        return []

    parser = get_parser(language)
    if parser is None:
        return []

    try:
        source_bytes = source.encode("utf-8")
        tree = parser.parse(source_bytes)

        if language == "python":
            return _extract_python_nodes(tree, source_bytes, source)
        elif language in ("javascript", "typescript"):
            return _extract_js_ts_nodes(tree, source_bytes, source)
        elif language == "go":
            return _extract_go_nodes(tree, source_bytes, source)
        elif language == "rust":
            return _extract_rust_nodes(tree, source_bytes, source)
        elif language == "solidity":
            return _extract_solidity_nodes(tree, source_bytes, source)
        else:
            return []

    except Exception as e:
        logger.warning(f"AST parsing failed for {language}: {e}")
        return []


# =============================================================================
# Fallback Chunking
# =============================================================================


def chunk_by_characters(
    source: str,
    file: str,
    project: str,
    language: str,
    chunk_size: int = FALLBACK_CHUNK_SIZE,
    overlap: int = FALLBACK_OVERLAP,
) -> list[CodeChunk]:
    """Chunk source code by character boundaries (fallback method).

    Tries to split on line boundaries for cleaner chunks.

    Args:
        source: Source code content
        file: Relative file path
        project: Project identifier
        language: Language identifier
        chunk_size: Target chunk size in characters
        overlap: Overlap between chunks

    Returns:
        List of CodeChunks
    """
    chunks = []
    lines = source.split("\n")
    current_chunk = []
    current_size = 0
    line_start = 1

    for i, line in enumerate(lines, 1):
        line_len = len(line) + 1  # +1 for newline

        if current_size + line_len > chunk_size and current_chunk:
            # Create chunk
            content = "\n".join(current_chunk)
            if len(content) >= MIN_CHUNK_SIZE:
                chunks.append(
                    CodeChunk(
                        id=generate_chunk_id(file, line_start, f"chunk{len(chunks)}"),
                        file=file,
                        project=project,
                        content=content[:MAX_CHUNK_SIZE],
                        chunk_type=ChunkType.FALLBACK,
                        name=f"chunk_{len(chunks)}",
                        line_start=line_start,
                        line_end=i - 1,
                        language=language,
                    )
                )

            # Start new chunk with overlap
            overlap_lines = overlap // 80  # Approximate lines for overlap
            current_chunk = current_chunk[-overlap_lines:] if overlap_lines > 0 else []
            current_size = sum(len(line) + 1 for line in current_chunk)
            line_start = i - len(current_chunk)

        current_chunk.append(line)
        current_size += line_len

    # Final chunk
    if current_chunk:
        content = "\n".join(current_chunk)
        if len(content) >= MIN_CHUNK_SIZE:
            chunks.append(
                CodeChunk(
                    id=generate_chunk_id(file, line_start, f"chunk{len(chunks)}"),
                    file=file,
                    project=project,
                    content=content[:MAX_CHUNK_SIZE],
                    chunk_type=ChunkType.FALLBACK,
                    name=f"chunk_{len(chunks)}",
                    line_start=line_start,
                    line_end=len(lines),
                    language=language,
                )
            )

    return chunks


# =============================================================================
# Main Chunking API
# =============================================================================


def chunk_file(
    file_path: Path,
    project: str,
    project_root: Path | None = None,
) -> list[CodeChunk]:
    """Chunk a source file into semantic units.

    Uses AST-based chunking for supported languages, falls back to
    character-based chunking otherwise.

    Args:
        file_path: Absolute path to source file
        project: Project identifier
        project_root: Root directory for relative paths (default: file's parent)

    Returns:
        List of CodeChunks
    """
    if not file_path.exists():
        return []

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
        return []

    if not source.strip():
        return []

    # Detect language
    language = detect_language(file_path)

    # Try AST-based extraction
    nodes = extract_nodes_ast(source, language)

    if nodes:
        # Convert extracted nodes to chunks
        chunks = []
        for node in nodes:
            content = node.content[:MAX_CHUNK_SIZE]
            if len(content) < MIN_CHUNK_SIZE:
                continue

            chunks.append(
                CodeChunk(
                    id=generate_chunk_id(rel_path, node.line_start, node.name),
                    file=rel_path,
                    project=project,
                    content=content,
                    chunk_type=node.chunk_type,
                    name=node.name,
                    line_start=node.line_start,
                    line_end=node.line_end,
                    language=language,
                    docstring=node.docstring,
                    signature=node.signature,
                    parent=node.parent,
                )
            )
        return chunks

    # Fallback to character-based chunking
    return chunk_by_characters(source, rel_path, project, language)


def chunk_source(
    source: str,
    file: str,
    project: str,
    language: str | None = None,
) -> list[CodeChunk]:
    """Chunk source code string into semantic units.

    Args:
        source: Source code content
        file: File path (for identification)
        project: Project identifier
        language: Language identifier (auto-detected from file if None)

    Returns:
        List of CodeChunks
    """
    if not source.strip():
        return []

    if language is None:
        language = detect_language(file)

    # Try AST-based extraction
    nodes = extract_nodes_ast(source, language)

    if nodes:
        chunks = []
        for node in nodes:
            content = node.content[:MAX_CHUNK_SIZE]
            if len(content) < MIN_CHUNK_SIZE:
                continue

            chunks.append(
                CodeChunk(
                    id=generate_chunk_id(file, node.line_start, node.name),
                    file=file,
                    project=project,
                    content=content,
                    chunk_type=node.chunk_type,
                    name=node.name,
                    line_start=node.line_start,
                    line_end=node.line_end,
                    language=language,
                    docstring=node.docstring,
                    signature=node.signature,
                    parent=node.parent,
                )
            )
        return chunks

    return chunk_by_characters(source, file, project, language)
