"""Tests for sage.codebase.core_files module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.codebase.core_files import (
    mark_core,
    unmark_core,
    list_core,
    get_core_file,
    get_core_context,
    get_core_files_path,
    _load_core_files,
    _save_core_files,
)
from sage.codebase.models import CoreFile


class TestCoreFilePaths:
    """Tests for path functions."""

    def test_get_core_files_path_global(self):
        """Global path is under ~/.sage."""
        path = get_core_files_path()
        assert ".sage" in str(path)
        assert "core_files.yaml" in str(path)

    def test_get_core_files_path_project(self, tmp_path: Path):
        """Project path is under project/.sage."""
        path = get_core_files_path(tmp_path)
        assert str(tmp_path) in str(path)
        assert "core_files.yaml" in str(path)


class TestLoadSaveCoreFiles:
    """Tests for _load_core_files() and _save_core_files()."""

    def test_load_missing_returns_empty(self, tmp_path: Path):
        """Loading non-existent file returns empty list."""
        files = _load_core_files(tmp_path)
        assert files == []

    def test_save_and_load(self, tmp_path: Path):
        """Files survive save/load cycle."""
        files = [
            CoreFile(
                path="src/main.py",
                project="test",
                summary="Main entry point",
                marked_at="2026-01-31T10:00:00Z",
            ),
            CoreFile(
                path="src/config.py",
                project="test",
                summary="Configuration",
                marked_at="2026-01-31T10:00:01Z",
            ),
        ]

        _save_core_files(files, tmp_path)
        loaded = _load_core_files(tmp_path)

        assert len(loaded) == 2
        assert loaded[0].path == "src/main.py"
        assert loaded[1].path == "src/config.py"


class TestMarkCore:
    """Tests for mark_core()."""

    def test_marks_file(self, tmp_path: Path):
        """mark_core creates CoreFile entry."""
        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                result = mark_core("src/main.py", tmp_path, "Main entry point")

        assert result.path == "src/main.py"
        assert result.project == "test"
        assert result.summary == "Main entry point"
        assert result.marked_at != ""

        # Verify persisted
        files = _load_core_files(tmp_path)
        assert len(files) == 1

    def test_updates_existing(self, tmp_path: Path):
        """Marking same file updates rather than duplicates."""
        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                mark_core("src/main.py", tmp_path, "First summary")
                mark_core("src/main.py", tmp_path, "Updated summary")

        files = _load_core_files(tmp_path)
        assert len(files) == 1
        assert files[0].summary == "Updated summary"

    def test_handles_absolute_path(self, tmp_path: Path):
        """Absolute paths are converted to relative."""
        abs_path = tmp_path / "src" / "main.py"

        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                result = mark_core(str(abs_path), tmp_path, "")

        assert result.path == "src/main.py"


class TestUnmarkCore:
    """Tests for unmark_core()."""

    def test_removes_file(self, tmp_path: Path):
        """unmark_core removes CoreFile entry."""
        # First mark
        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                mark_core("src/main.py", tmp_path, "")

        # Then unmark
        result = unmark_core("src/main.py", tmp_path)

        assert result is True
        files = _load_core_files(tmp_path)
        assert len(files) == 0

    def test_returns_false_not_found(self, tmp_path: Path):
        """unmark_core returns False if not found."""
        result = unmark_core("nonexistent.py", tmp_path)
        assert result is False


class TestListCore:
    """Tests for list_core()."""

    def test_lists_all_files(self, tmp_path: Path):
        """list_core returns all marked files."""
        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                mark_core("src/a.py", tmp_path, "A")
                mark_core("src/b.py", tmp_path, "B")

        files = list_core(tmp_path)

        assert len(files) == 2
        paths = [f.path for f in files]
        assert "src/a.py" in paths
        assert "src/b.py" in paths

    def test_filters_by_project(self, tmp_path: Path):
        """list_core can filter by project."""
        files = [
            CoreFile(path="a.py", project="proj1", summary="", marked_at=""),
            CoreFile(path="b.py", project="proj2", summary="", marked_at=""),
        ]
        _save_core_files(files, tmp_path)

        filtered = list_core(tmp_path, project="proj1")

        assert len(filtered) == 1
        assert filtered[0].path == "a.py"


class TestGetCoreFile:
    """Tests for get_core_file()."""

    def test_finds_file(self, tmp_path: Path):
        """get_core_file finds file by path."""
        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                mark_core("src/main.py", tmp_path, "Main")

        result = get_core_file("src/main.py", tmp_path)

        assert result is not None
        assert result.path == "src/main.py"

    def test_returns_none_not_found(self, tmp_path: Path):
        """get_core_file returns None if not found."""
        result = get_core_file("nonexistent.py", tmp_path)
        assert result is None


class TestGetCoreContext:
    """Tests for get_core_context()."""

    def test_empty_when_no_files(self, tmp_path: Path):
        """Returns empty string when no core files."""
        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            result = get_core_context(tmp_path)

        assert result == ""

    def test_includes_file_content(self, tmp_path: Path):
        """Context includes file content."""
        # Create a real file
        (tmp_path / "main.py").write_text("print('hello')")

        # Mark it
        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                mark_core("main.py", tmp_path, "Main file")

        result = get_core_context(tmp_path)

        assert "CORE FILES" in result
        assert "main.py" in result
        assert "print('hello')" in result

    def test_includes_summary(self, tmp_path: Path):
        """Context includes file summary."""
        (tmp_path / "config.py").write_text("DEBUG = True")

        with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
            with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                mark_core("config.py", tmp_path, "Configuration settings")

        result = get_core_context(tmp_path)

        assert "Configuration settings" in result

    def test_respects_max_files(self, tmp_path: Path):
        """Context respects max_files limit."""
        for i in range(10):
            (tmp_path / f"file{i}.py").write_text(f"# File {i}")
            with patch("sage.codebase.core_files.detect_project_root", return_value=tmp_path):
                with patch("sage.codebase.core_files.detect_project_name", return_value="test"):
                    mark_core(f"file{i}.py", tmp_path, "")

        result = get_core_context(tmp_path, max_files=3)

        # Should mention there are more files not shown
        assert "more core files" in result.lower() or result.count("##") <= 4
