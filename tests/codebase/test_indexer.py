"""Tests for sage.codebase.indexer module."""

from pathlib import Path

import pytest

from sage.codebase.indexer import (
    detect_project_name,
    get_codebase_dir,
    get_compiled_dir,
    get_index_meta_path,
    get_lancedb_path,
    is_lancedb_available,
    load_index_meta,
    save_index_meta,
)


class TestPaths:
    """Tests for path functions."""

    def test_get_codebase_dir_global(self):
        """Global codebase dir is under ~/.sage."""
        path = get_codebase_dir()
        assert ".sage" in str(path)
        assert "codebase" in str(path)

    def test_get_codebase_dir_project(self, tmp_path: Path):
        """Project codebase dir is under project/.sage."""
        path = get_codebase_dir(tmp_path)
        assert str(tmp_path) in str(path)
        assert ".sage" in str(path)
        assert "codebase" in str(path)

    def test_get_lancedb_path(self):
        """LanceDB path is under global codebase dir."""
        path = get_lancedb_path()
        assert "lancedb" in str(path)

    def test_get_index_meta_path(self, tmp_path: Path):
        """Index meta path is in codebase dir."""
        path = get_index_meta_path(tmp_path)
        assert "index_meta.json" in str(path)

    def test_get_compiled_dir(self, tmp_path: Path):
        """Compiled dir is in codebase dir."""
        path = get_compiled_dir(tmp_path)
        assert "compiled" in str(path)


class TestIndexMeta:
    """Tests for index metadata functions."""

    def test_load_missing_returns_defaults(self, tmp_path: Path):
        """Loading non-existent meta returns defaults."""
        meta = load_index_meta(tmp_path)

        assert meta["files"] == {}
        assert meta["indexed_at"] is None
        assert meta["project"] is None

    def test_save_and_load(self, tmp_path: Path):
        """Meta survives save/load cycle."""
        meta = {
            "files": {"test.py": 1234567890.0},
            "indexed_at": "2026-01-31T10:00:00Z",
            "project": "test",
        }

        save_index_meta(meta, tmp_path)
        loaded = load_index_meta(tmp_path)

        assert loaded["files"] == meta["files"]
        assert loaded["indexed_at"] == meta["indexed_at"]
        assert loaded["project"] == meta["project"]


class TestDetectProjectName:
    """Tests for detect_project_name()."""

    def test_uses_directory_name_fallback(self, tmp_path: Path):
        """Falls back to directory name."""
        name = detect_project_name(tmp_path)
        assert name == tmp_path.name

    def test_uses_pyproject_name(self, tmp_path: Path):
        """Extracts name from pyproject.toml."""
        (tmp_path / "pyproject.toml").write_text(
            """
[project]
name = "my-cool-project"
version = "1.0.0"
"""
        )

        name = detect_project_name(tmp_path)
        assert name == "my-cool-project"

    def test_uses_package_json_name(self, tmp_path: Path):
        """Extracts name from package.json."""
        (tmp_path / "package.json").write_text('{"name": "my-js-project", "version": "1.0.0"}')

        name = detect_project_name(tmp_path)
        assert name == "my-js-project"


class TestLanceDBAvailability:
    """Tests for is_lancedb_available()."""

    def test_returns_boolean(self):
        """Returns True or False based on import."""
        result = is_lancedb_available()
        assert isinstance(result, bool)


# Skip these tests if LanceDB not available
@pytest.mark.skipif(not is_lancedb_available(), reason="LanceDB not available")
class TestIndexDirectory:
    """Tests for index_directory() (requires LanceDB)."""

    def test_indexes_empty_directory(self, tmp_path: Path):
        """Empty directory produces empty stats."""
        from sage.codebase.indexer import index_directory

        stats = index_directory(tmp_path, project="test")

        assert stats.project == "test"
        assert stats.files_indexed == 0
        assert stats.chunks_created == 0

    def test_indexes_python_files(self, tmp_path: Path):
        """Python files are indexed."""
        from sage.codebase.indexer import index_directory

        (tmp_path / "module.py").write_text(
            """
def hello():
    print("Hello")

def world():
    print("World")
"""
        )

        stats = index_directory(tmp_path, project="test")

        assert stats.files_indexed >= 1
        assert "python" in stats.languages


class TestIncrementalIndexing:
    """Tests for incremental indexing."""

    def test_mtime_tracking(self, tmp_path: Path):
        """File mtimes are tracked for incremental updates."""
        (tmp_path / "test.py").write_text("def test(): pass")

        # First save
        save_index_meta(
            {"files": {"test.py": 1000.0}, "indexed_at": None, "project": None}, tmp_path
        )

        # Load and verify
        meta = load_index_meta(tmp_path)
        assert "test.py" in meta["files"]
        assert meta["files"]["test.py"] == 1000.0
