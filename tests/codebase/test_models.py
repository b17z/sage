"""Tests for sage.codebase.models module."""

from pathlib import Path

import pytest

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
    LANGUAGE_EXTENSIONS,
)


class TestDetectLanguage:
    """Tests for detect_language()."""

    def test_python_files(self):
        """Python file extensions are detected."""
        assert detect_language("test.py") == "python"
        assert detect_language("test.pyx") == "python"
        assert detect_language("test.pyi") == "python"

    def test_javascript_files(self):
        """JavaScript file extensions are detected."""
        assert detect_language("app.js") == "javascript"
        assert detect_language("component.jsx") == "javascript"

    def test_typescript_files(self):
        """TypeScript file extensions are detected."""
        assert detect_language("app.ts") == "typescript"
        assert detect_language("component.tsx") == "typescript"

    def test_solidity_files(self):
        """Solidity file extensions are detected."""
        assert detect_language("Token.sol") == "solidity"

    def test_go_files(self):
        """Go file extensions are detected."""
        assert detect_language("main.go") == "go"

    def test_rust_files(self):
        """Rust file extensions are detected."""
        assert detect_language("lib.rs") == "rust"

    def test_path_object(self):
        """Works with Path objects."""
        assert detect_language(Path("/some/path/test.py")) == "python"

    def test_unknown_extension(self):
        """Unknown extensions return 'unknown'."""
        assert detect_language("file.xyz") == "unknown"
        assert detect_language("README") == "unknown"

    def test_case_insensitive(self):
        """Extension detection is case insensitive."""
        assert detect_language("test.PY") == "python"
        assert detect_language("test.Py") == "python"


class TestCodeChunk:
    """Tests for CodeChunk dataclass."""

    def test_frozen(self):
        """CodeChunk is immutable."""
        chunk = CodeChunk(
            id="test:1:main",
            file="test.py",
            project="test-project",
            content="def main(): pass",
            chunk_type=ChunkType.FUNCTION,
            name="main",
            line_start=1,
            line_end=1,
            language="python",
        )

        with pytest.raises(AttributeError):
            chunk.name = "other"

    def test_defaults(self):
        """Default values are set correctly."""
        chunk = CodeChunk(
            id="test:1:main",
            file="test.py",
            project="test",
            content="def main(): pass",
            chunk_type=ChunkType.FUNCTION,
            name="main",
            line_start=1,
            line_end=1,
            language="python",
        )

        assert chunk.docstring == ""
        assert chunk.signature == ""
        assert chunk.parent == ""
        assert chunk.embedding == []


class TestCompiledIndex:
    """Tests for CompiledIndex lookup methods."""

    def test_lookup_function(self):
        """lookup_function finds function by name."""
        fn = CompiledFunction(
            name="get_user",
            signature="def get_user(id: int) -> User",
            file="users.py",
            line=10,
        )
        index = CompiledIndex(project="test", functions=(fn,))

        result = index.lookup_function("get_user")
        assert result == fn

        assert index.lookup_function("not_found") is None

    def test_lookup_class(self):
        """lookup_class finds class by name."""
        cls = CompiledClass(
            name="UserService",
            file="users.py",
            line=1,
            methods=("get", "create", "delete"),
        )
        index = CompiledIndex(project="test", classes=(cls,))

        result = index.lookup_class("UserService")
        assert result == cls

        assert index.lookup_class("NotFound") is None

    def test_lookup_constant(self):
        """lookup_constant finds constant by name."""
        const = CompiledConstant(
            name="MAX_RETRIES",
            value="5",
            file="config.py",
            line=1,
        )
        index = CompiledIndex(project="test", constants=(const,))

        result = index.lookup_constant("MAX_RETRIES")
        assert result == const

        assert index.lookup_constant("NOT_FOUND") is None


class TestCoreFile:
    """Tests for CoreFile dataclass."""

    def test_frozen(self):
        """CoreFile is immutable."""
        cf = CoreFile(
            path="sage/config.py",
            project="sage",
            summary="Configuration management",
        )

        with pytest.raises(AttributeError):
            cf.summary = "New summary"


class TestIndexStats:
    """Tests for IndexStats dataclass."""

    def test_all_fields(self):
        """IndexStats has all required fields."""
        stats = IndexStats(
            project="test",
            files_indexed=10,
            chunks_created=50,
            functions_compiled=30,
            classes_compiled=15,
            constants_compiled=5,
            languages=("python", "typescript"),
            duration_ms=1500,
            indexed_at="2026-01-31T10:00:00Z",
        )

        assert stats.project == "test"
        assert stats.files_indexed == 10
        assert stats.chunks_created == 50
        assert len(stats.languages) == 2


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_has_chunk_and_score(self):
        """SearchResult contains chunk and score."""
        chunk = CodeChunk(
            id="test:1:main",
            file="test.py",
            project="test",
            content="def main(): pass",
            chunk_type=ChunkType.FUNCTION,
            name="main",
            line_start=1,
            line_end=1,
            language="python",
        )
        result = SearchResult(chunk=chunk, score=0.85, highlights=("def main",))

        assert result.chunk == chunk
        assert result.score == 0.85
        assert result.highlights == ("def main",)


class TestChunkType:
    """Tests for ChunkType enum."""

    def test_values(self):
        """ChunkType has expected values."""
        assert ChunkType.FUNCTION.value == "function"
        assert ChunkType.CLASS.value == "class"
        assert ChunkType.METHOD.value == "method"
        assert ChunkType.MODULE.value == "module"
        assert ChunkType.CONSTANT.value == "constant"
        assert ChunkType.TYPE.value == "type"
        assert ChunkType.FALLBACK.value == "fallback"

    def test_string_conversion(self):
        """ChunkType works as string."""
        assert str(ChunkType.FUNCTION) == "ChunkType.FUNCTION"
        assert ChunkType.FUNCTION == "function"
