"""Tests for sage.codebase.search module."""

from pathlib import Path

import pytest

from sage.codebase.models import (
    CompiledClass,
    CompiledConstant,
    CompiledFunction,
    CompiledIndex,
)
from sage.codebase.search import (
    _generate_highlights,
    grep_class,
    grep_constant,
    grep_function,
)


class TestGenerateHighlights:
    """Tests for _generate_highlights()."""

    def test_returns_first_line(self):
        """First line is always included."""
        content = "def hello():\n    pass"
        highlights = _generate_highlights(content, "some query")

        assert len(highlights) >= 1
        assert "def hello()" in highlights[0]

    def test_finds_query_words(self):
        """Highlights lines containing query words."""
        content = """
def process_user():
    user = get_user()
    validate_user(user)
    return user
"""
        highlights = _generate_highlights(content, "validate user")

        assert len(highlights) >= 1
        # Should find lines with "validate" or "user"

    def test_max_three_highlights(self):
        """Returns at most 3 highlights."""
        content = "\n".join([f"line {i}" for i in range(100)])
        highlights = _generate_highlights(content, "line")

        assert len(highlights) <= 3


class TestGrepFunctions:
    """Tests for grep_* lookup functions."""

    @pytest.fixture
    def mock_compiled_index(self, tmp_path: Path):
        """Create a mock compiled index."""
        index = CompiledIndex(
            project="test",
            functions=(
                CompiledFunction(name="get_user", signature="def get_user()", file="a.py", line=1),
                CompiledFunction(
                    name="create_user", signature="def create_user()", file="a.py", line=10
                ),
            ),
            classes=(CompiledClass(name="UserService", file="a.py", line=1, methods=("get",)),),
            constants=(CompiledConstant(name="MAX_USERS", value="100", file="config.py", line=1),),
        )

        # Save to tmp_path
        from sage.codebase.compiler import save_compiled_index
        from sage.codebase.indexer import get_compiled_dir

        compiled_dir = get_compiled_dir(tmp_path)
        save_compiled_index(index, compiled_dir)

        return tmp_path

    def test_grep_function_finds_match(self, mock_compiled_index):
        """grep_function finds function by name."""
        result = grep_function("get_user", mock_compiled_index)

        assert result is not None
        assert result.name == "get_user"
        assert result.file == "a.py"

    def test_grep_function_not_found(self, mock_compiled_index):
        """grep_function returns None when not found."""
        result = grep_function("nonexistent", mock_compiled_index)
        assert result is None

    def test_grep_class_finds_match(self, mock_compiled_index):
        """grep_class finds class by name."""
        result = grep_class("UserService", mock_compiled_index)

        assert result is not None
        assert result.name == "UserService"

    def test_grep_constant_finds_match(self, mock_compiled_index):
        """grep_constant finds constant by name."""
        result = grep_constant("MAX_USERS", mock_compiled_index)

        assert result is not None
        assert result.name == "MAX_USERS"
        assert result.value == "100"


class TestGrepSymbol:
    """Tests for grep_symbol() unified lookup."""

    def test_finds_function_first(self, tmp_path: Path):
        """grep_symbol checks functions first."""
        from sage.codebase.compiler import save_compiled_index
        from sage.codebase.indexer import get_compiled_dir
        from sage.codebase.search import grep_symbol

        index = CompiledIndex(
            project="test",
            functions=(CompiledFunction(name="test", signature="def test()", file="a.py", line=1),),
            classes=(CompiledClass(name="Test", file="b.py", line=1),),
            constants=(),
        )

        save_compiled_index(index, get_compiled_dir(tmp_path))

        result = grep_symbol("test", tmp_path)

        assert result is not None
        assert isinstance(result, CompiledFunction)

    def test_falls_through_to_class(self, tmp_path: Path):
        """grep_symbol finds class if no matching function."""
        from sage.codebase.compiler import save_compiled_index
        from sage.codebase.indexer import get_compiled_dir
        from sage.codebase.search import grep_symbol

        index = CompiledIndex(
            project="test",
            functions=(),
            classes=(CompiledClass(name="MyClass", file="a.py", line=1),),
            constants=(),
        )

        save_compiled_index(index, get_compiled_dir(tmp_path))

        result = grep_symbol("MyClass", tmp_path)

        assert result is not None
        assert isinstance(result, CompiledClass)

    def test_falls_through_to_constant(self, tmp_path: Path):
        """grep_symbol finds constant if no function or class."""
        from sage.codebase.compiler import save_compiled_index
        from sage.codebase.indexer import get_compiled_dir
        from sage.codebase.search import grep_symbol

        index = CompiledIndex(
            project="test",
            functions=(),
            classes=(),
            constants=(CompiledConstant(name="MY_CONST", value="42", file="a.py", line=1),),
        )

        save_compiled_index(index, get_compiled_dir(tmp_path))

        result = grep_symbol("MY_CONST", tmp_path)

        assert result is not None
        assert isinstance(result, CompiledConstant)

    def test_returns_none_not_found(self, tmp_path: Path):
        """grep_symbol returns None if nothing found."""
        from sage.codebase.compiler import save_compiled_index
        from sage.codebase.indexer import get_compiled_dir
        from sage.codebase.search import grep_symbol

        index = CompiledIndex(project="test", functions=(), classes=(), constants=())

        save_compiled_index(index, get_compiled_dir(tmp_path))

        result = grep_symbol("nonexistent", tmp_path)
        assert result is None


class TestListFunctions:
    """Tests for list_functions()."""

    def test_lists_all_functions(self, tmp_path: Path):
        """list_functions returns all functions."""
        from sage.codebase.compiler import save_compiled_index
        from sage.codebase.indexer import get_compiled_dir
        from sage.codebase.search import list_functions

        index = CompiledIndex(
            project="test",
            functions=(
                CompiledFunction(name="func_a", signature="def func_a()", file="a.py", line=1),
                CompiledFunction(name="func_b", signature="def func_b()", file="b.py", line=1),
                CompiledFunction(name="other", signature="def other()", file="c.py", line=1),
            ),
            classes=(),
            constants=(),
        )

        save_compiled_index(index, get_compiled_dir(tmp_path))

        functions = list_functions(tmp_path)
        assert len(functions) == 3

    def test_filters_by_pattern(self, tmp_path: Path):
        """list_functions filters by pattern."""
        from sage.codebase.compiler import save_compiled_index
        from sage.codebase.indexer import get_compiled_dir
        from sage.codebase.search import list_functions

        index = CompiledIndex(
            project="test",
            functions=(
                CompiledFunction(name="get_user", signature="def get_user()", file="a.py", line=1),
                CompiledFunction(
                    name="get_items", signature="def get_items()", file="b.py", line=1
                ),
                CompiledFunction(
                    name="create_user", signature="def create_user()", file="c.py", line=1
                ),
            ),
            classes=(),
            constants=(),
        )

        save_compiled_index(index, get_compiled_dir(tmp_path))

        functions = list_functions(tmp_path, filter_pattern="get")
        assert len(functions) == 2
        names = [f.name for f in functions]
        assert "get_user" in names
        assert "get_items" in names
