"""Tests for sage.codebase.compiler module."""

from pathlib import Path

import pytest

from sage.codebase.chunker import is_treesitter_available
from sage.codebase.compiler import (
    _compiled_index_to_dict,
    _dict_to_compiled_index,
    compile_directory,
    compile_file,
    load_compiled_index,
    lookup_class,
    lookup_constant,
    lookup_function,
    save_compiled_index,
)
from sage.codebase.models import (
    CompiledClass,
    CompiledConstant,
    CompiledFunction,
    CompiledIndex,
)


class TestCompiledIndexSerialization:
    """Tests for CompiledIndex serialization."""

    def test_to_dict_and_back(self):
        """Index survives round-trip serialization."""
        index = CompiledIndex(
            project="test",
            compiled_at="2026-01-31T10:00:00Z",
            functions=(
                CompiledFunction(
                    name="get_user",
                    signature="def get_user(id: int) -> User",
                    file="users.py",
                    line=10,
                    docstring="Get user by ID.",
                    is_method=False,
                    parent_class="",
                ),
            ),
            classes=(
                CompiledClass(
                    name="UserService",
                    file="users.py",
                    line=1,
                    methods=("get", "create"),
                    bases=("BaseService",),
                    docstring="User operations.",
                ),
            ),
            constants=(
                CompiledConstant(
                    name="MAX_USERS",
                    value="1000",
                    file="config.py",
                    line=5,
                    type_hint="int",
                ),
            ),
        )

        data = _compiled_index_to_dict(index)
        restored = _dict_to_compiled_index(data)

        assert restored.project == index.project
        assert restored.compiled_at == index.compiled_at
        assert len(restored.functions) == 1
        assert restored.functions[0].name == "get_user"
        assert len(restored.classes) == 1
        assert restored.classes[0].name == "UserService"
        assert len(restored.constants) == 1
        assert restored.constants[0].name == "MAX_USERS"


class TestSaveLoadCompiledIndex:
    """Tests for save_compiled_index() and load_compiled_index()."""

    def test_save_creates_files(self, tmp_path: Path):
        """save_compiled_index creates expected files."""
        index = CompiledIndex(
            project="test",
            compiled_at="2026-01-31T10:00:00Z",
            functions=(
                CompiledFunction(name="func1", signature="def func1()", file="a.py", line=1),
            ),
            classes=(),
            constants=(),
        )

        output_dir = tmp_path / "compiled"
        meta_path = save_compiled_index(index, output_dir)

        assert meta_path.exists()
        assert (output_dir / "functions.json").exists()
        assert (output_dir / "classes.json").exists()
        assert (output_dir / "constants.json").exists()

    def test_round_trip(self, tmp_path: Path):
        """Index survives save/load cycle."""
        index = CompiledIndex(
            project="test",
            compiled_at="2026-01-31T10:00:00Z",
            functions=(
                CompiledFunction(
                    name="process", signature="def process(data)", file="proc.py", line=10
                ),
            ),
            classes=(
                CompiledClass(name="DataProcessor", file="proc.py", line=1, methods=("run",)),
            ),
            constants=(CompiledConstant(name="TIMEOUT", value="30", file="config.py", line=1),),
        )

        output_dir = tmp_path / "compiled"
        save_compiled_index(index, output_dir)

        loaded = load_compiled_index(output_dir)

        assert loaded is not None
        assert loaded.project == "test"
        assert len(loaded.functions) == 1
        assert loaded.functions[0].name == "process"
        assert len(loaded.classes) == 1
        assert len(loaded.constants) == 1

    def test_load_missing_returns_none(self, tmp_path: Path):
        """load_compiled_index returns None if not found."""
        result = load_compiled_index(tmp_path / "nonexistent")
        assert result is None


class TestLookupFunctions:
    """Tests for lookup functions."""

    @pytest.fixture
    def sample_index(self):
        """Create a sample index for testing."""
        return CompiledIndex(
            project="test",
            functions=(
                CompiledFunction(name="get_user", signature="def get_user()", file="a.py", line=1),
                CompiledFunction(
                    name="create_user", signature="def create_user()", file="a.py", line=10
                ),
            ),
            classes=(
                CompiledClass(name="UserService", file="a.py", line=1, methods=("get", "create")),
            ),
            constants=(CompiledConstant(name="MAX_USERS", value="100", file="config.py", line=1),),
        )

    def test_lookup_function(self, sample_index):
        """lookup_function finds by exact name."""
        result = lookup_function("get_user", sample_index)
        assert result is not None
        assert result.name == "get_user"

        assert lookup_function("not_found", sample_index) is None

    def test_lookup_class(self, sample_index):
        """lookup_class finds by exact name."""
        result = lookup_class("UserService", sample_index)
        assert result is not None
        assert result.name == "UserService"

        assert lookup_class("NotFound", sample_index) is None

    def test_lookup_constant(self, sample_index):
        """lookup_constant finds by exact name."""
        result = lookup_constant("MAX_USERS", sample_index)
        assert result is not None
        assert result.name == "MAX_USERS"

        assert lookup_constant("NOT_FOUND", sample_index) is None


@pytest.mark.skipif(not is_treesitter_available(), reason="tree-sitter not available")
class TestCompileFile:
    """Tests for compile_file()."""

    def test_compiles_python_functions(self, tmp_path: Path):
        """Python functions are compiled."""
        test_file = tmp_path / "funcs.py"
        test_file.write_text(
            '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def multiply(a, b):
    return a * b
'''
        )

        funcs, classes, consts = compile_file(test_file, tmp_path)

        assert len(funcs) >= 2
        names = [f.name for f in funcs]
        assert "add" in names
        assert "multiply" in names

    def test_compiles_classes(self, tmp_path: Path):
        """Python classes are compiled."""
        test_file = tmp_path / "classes.py"
        test_file.write_text(
            '''
class Calculator:
    """A calculator class."""

    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
'''
        )

        funcs, classes, consts = compile_file(test_file, tmp_path)

        assert len(classes) >= 1
        calc_class = next((c for c in classes if c.name == "Calculator"), None)
        assert calc_class is not None

    def test_nonexistent_file(self, tmp_path: Path):
        """Nonexistent file returns empty tuples."""
        funcs, classes, consts = compile_file(tmp_path / "nonexistent.py", tmp_path)

        assert funcs == []
        assert classes == []
        assert consts == []


@pytest.mark.skipif(not is_treesitter_available(), reason="tree-sitter not available")
class TestCompileDirectory:
    """Tests for compile_directory()."""

    def test_compiles_all_files(self, tmp_path: Path):
        """All Python files in directory are compiled."""
        (tmp_path / "module1.py").write_text("def func1(): pass")
        (tmp_path / "module2.py").write_text("def func2(): pass")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "module3.py").write_text("def func3(): pass")

        index = compile_directory(tmp_path, "test")

        assert len(index.functions) >= 3
        names = [f.name for f in index.functions]
        assert "func1" in names
        assert "func2" in names
        assert "func3" in names

    def test_excludes_patterns(self, tmp_path: Path):
        """Excluded patterns are skipped."""
        (tmp_path / "good.py").write_text("def good(): pass")
        (tmp_path / "node_modules").mkdir()
        (tmp_path / "node_modules" / "bad.py").write_text("def bad(): pass")

        index = compile_directory(tmp_path, "test")

        names = [f.name for f in index.functions]
        assert "good" in names
        assert "bad" not in names

    def test_sets_project_and_timestamp(self, tmp_path: Path):
        """Index has project and timestamp."""
        (tmp_path / "test.py").write_text("def test(): pass")

        index = compile_directory(tmp_path, "my-project")

        assert index.project == "my-project"
        assert index.compiled_at != ""
