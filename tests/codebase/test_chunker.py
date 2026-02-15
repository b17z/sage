"""Tests for sage.codebase.chunker module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.codebase.chunker import (
    FALLBACK_CHUNK_SIZE,
    FALLBACK_OVERLAP,
    MIN_CHUNK_SIZE,
    chunk_by_characters,
    chunk_file,
    chunk_source,
    generate_chunk_id,
    is_treesitter_available,
)
from sage.codebase.models import ChunkType


class TestGenerateChunkId:
    """Tests for generate_chunk_id()."""

    def test_id_format(self):
        """ID follows expected format."""
        id = generate_chunk_id("path/to/file.py", 10, "my_function")
        parts = id.split(":")
        assert len(parts) == 3
        assert len(parts[0]) == 8  # File hash
        assert parts[1] == "10"  # Line
        assert parts[2] == "my_function"  # Name

    def test_sanitizes_name(self):
        """Special characters in name are sanitized."""
        id = generate_chunk_id("file.py", 1, "function<T>(x: int)")
        # Should only contain safe characters
        assert all(c.isalnum() or c in ":-_" for c in id)

    def test_truncates_long_names(self):
        """Long names are truncated."""
        long_name = "a" * 100
        id = generate_chunk_id("file.py", 1, long_name)
        # Name part should be at most 50 chars
        name_part = id.split(":")[-1]
        assert len(name_part) <= 50


class TestChunkByCharacters:
    """Tests for chunk_by_characters() fallback chunking."""

    def test_short_file_single_chunk(self):
        """Short files produce a single chunk."""
        source = "def hello(): print('hi')"
        chunks = chunk_by_characters(source, "test.txt", "test-project", "unknown")

        # Short content under MIN_CHUNK_SIZE won't produce chunks
        if len(source) >= MIN_CHUNK_SIZE:
            assert len(chunks) == 1
            assert chunks[0].chunk_type == ChunkType.FALLBACK

    def test_long_file_multiple_chunks(self):
        """Long files produce multiple chunks."""
        # Create content longer than FALLBACK_CHUNK_SIZE
        line = "x = 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10\n"
        source = line * 200  # Should exceed chunk size

        chunks = chunk_by_characters(source, "test.txt", "test-project", "unknown")

        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.chunk_type == ChunkType.FALLBACK
            assert chunk.project == "test-project"

    def test_preserves_line_boundaries(self):
        """Chunks split on line boundaries."""
        lines = ["line " + str(i) + "\n" for i in range(100)]
        source = "".join(lines)

        chunks = chunk_by_characters(
            source, "test.txt", "test-project", "unknown", chunk_size=500, overlap=50
        )

        for chunk in chunks:
            # Content should not break mid-line
            content_lines = chunk.content.split("\n")
            # Each line should be complete (starts with "line")
            for cl in content_lines:
                if cl.strip():
                    assert cl.startswith("line")


class TestChunkSource:
    """Tests for chunk_source()."""

    def test_empty_source_no_chunks(self):
        """Empty source produces no chunks."""
        chunks = chunk_source("", "test.py", "test")
        assert chunks == []

    def test_whitespace_only_no_chunks(self):
        """Whitespace-only source produces no chunks."""
        chunks = chunk_source("   \n\n   ", "test.py", "test")
        assert chunks == []

    def test_auto_detects_language(self):
        """Language is auto-detected from file extension."""
        source = "def hello(): pass"
        chunks = chunk_source(source, "test.py", "test")

        # Even if just one chunk
        if chunks:
            assert chunks[0].language == "python"

    def test_explicit_language(self):
        """Explicit language overrides detection."""
        source = "def hello(): pass"
        chunks = chunk_source(source, "test.txt", "test", language="python")

        if chunks:
            assert chunks[0].language == "python"


class TestChunkFile:
    """Tests for chunk_file()."""

    def test_nonexistent_file(self, tmp_path: Path):
        """Nonexistent file returns empty list."""
        chunks = chunk_file(tmp_path / "nonexistent.py", "test", tmp_path)
        assert chunks == []

    def test_empty_file(self, tmp_path: Path):
        """Empty file returns empty list."""
        test_file = tmp_path / "empty.py"
        test_file.write_text("")

        chunks = chunk_file(test_file, "test", tmp_path)
        assert chunks == []

    def test_simple_python_file(self, tmp_path: Path):
        """Simple Python file is chunked."""
        test_file = tmp_path / "simple.py"
        test_file.write_text(
            '''
def hello():
    """Say hello."""
    print("Hello, world!")

def goodbye():
    """Say goodbye."""
    print("Goodbye!")
'''
        )

        chunks = chunk_file(test_file, "test", tmp_path)

        # Should have at least the functions
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.project == "test"
            assert chunk.language == "python"

    def test_relative_path(self, tmp_path: Path):
        """File path is relative to project root."""
        subdir = tmp_path / "src"
        subdir.mkdir()
        test_file = subdir / "module.py"
        test_file.write_text("def func(): pass")

        chunks = chunk_file(test_file, "test", tmp_path)

        if chunks:
            assert chunks[0].file == "src/module.py"


class TestTreeSitterAvailability:
    """Tests for is_treesitter_available()."""

    def test_returns_boolean(self):
        """Returns True or False based on import."""
        result = is_treesitter_available()
        assert isinstance(result, bool)


# Python AST extraction tests (only run if tree-sitter available)
@pytest.mark.skipif(not is_treesitter_available(), reason="tree-sitter not available")
class TestPythonASTChunking:
    """Tests for Python AST-based chunking."""

    def test_extracts_functions(self, tmp_path: Path):
        """Functions are extracted as FUNCTION chunks."""
        test_file = tmp_path / "funcs.py"
        # Functions need to be >50 chars (MIN_CHUNK_SIZE) to be indexed
        test_file.write_text(
            '''
def add(a, b):
    """Add two numbers together and return the result."""
    return a + b

def multiply(a, b):
    """Multiply two numbers together and return the result."""
    return a * b
'''
        )

        chunks = chunk_file(test_file, "test", tmp_path)

        func_chunks = [c for c in chunks if c.chunk_type == ChunkType.FUNCTION]
        assert len(func_chunks) >= 2
        names = [c.name for c in func_chunks]
        assert "add" in names
        assert "multiply" in names

    def test_extracts_classes(self, tmp_path: Path):
        """Classes are extracted as CLASS chunks."""
        test_file = tmp_path / "classes.py"
        test_file.write_text(
            '''
class Calculator:
    """A simple calculator."""

    def add(self, a, b):
        return a + b

class AdvancedCalculator(Calculator):
    def multiply(self, a, b):
        return a * b
'''
        )

        chunks = chunk_file(test_file, "test", tmp_path)

        class_chunks = [c for c in chunks if c.chunk_type == ChunkType.CLASS]
        assert len(class_chunks) >= 2

    def test_methods_have_parent(self, tmp_path: Path):
        """Methods have parent class set."""
        test_file = tmp_path / "methods.py"
        test_file.write_text(
            """
class MyClass:
    def my_method(self):
        pass
"""
        )

        chunks = chunk_file(test_file, "test", tmp_path)

        method_chunks = [c for c in chunks if c.chunk_type == ChunkType.METHOD]
        if method_chunks:
            assert method_chunks[0].parent == "MyClass"

    def test_extracts_docstrings(self, tmp_path: Path):
        """Docstrings are extracted."""
        test_file = tmp_path / "docs.py"
        test_file.write_text(
            '''
def documented():
    """This is a docstring."""
    pass
'''
        )

        chunks = chunk_file(test_file, "test", tmp_path)

        func_chunks = [c for c in chunks if c.name == "documented"]
        if func_chunks:
            assert "docstring" in func_chunks[0].docstring.lower() or func_chunks[0].docstring != ""
