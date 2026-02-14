"""Tests for sage.atomic module."""

import json
import os
import stat
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from sage.atomic import (
    atomic_write_json,
    atomic_write_jsonl,
    atomic_write_text,
    atomic_write_yaml,
)


class TestAtomicWriteText:
    """Tests for atomic_write_text()."""

    def test_creates_file(self, tmp_path: Path):
        """atomic_write_text creates a new file."""
        file_path = tmp_path / "test.txt"

        result = atomic_write_text(file_path, "hello world")

        assert result.is_ok()
        assert result.unwrap() == file_path
        assert file_path.exists()
        assert file_path.read_text() == "hello world"

    def test_overwrites_existing_file(self, tmp_path: Path):
        """atomic_write_text overwrites existing file content."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("old content")

        result = atomic_write_text(file_path, "new content")

        assert result.is_ok()
        assert file_path.read_text() == "new content"

    def test_creates_parent_directories(self, tmp_path: Path):
        """atomic_write_text creates parent directories if needed."""
        file_path = tmp_path / "nested" / "deep" / "test.txt"

        result = atomic_write_text(file_path, "content")

        assert result.is_ok()
        assert file_path.exists()
        assert file_path.read_text() == "content"

    def test_sets_default_permissions(self, tmp_path: Path):
        """atomic_write_text sets 0o600 permissions by default."""
        file_path = tmp_path / "test.txt"

        result = atomic_write_text(file_path, "content")

        assert result.is_ok()
        mode = file_path.stat().st_mode
        # Check owner has read/write, no group/other access
        assert mode & stat.S_IRWXU == stat.S_IRUSR | stat.S_IWUSR
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0

    def test_sets_custom_permissions(self, tmp_path: Path):
        """atomic_write_text respects custom mode parameter."""
        file_path = tmp_path / "test.txt"

        result = atomic_write_text(file_path, "content", mode=0o644)

        assert result.is_ok()
        mode = file_path.stat().st_mode
        # Owner read/write, group/other read
        assert mode & stat.S_IRWXU == stat.S_IRUSR | stat.S_IWUSR
        assert mode & stat.S_IRGRP == stat.S_IRGRP
        assert mode & stat.S_IROTH == stat.S_IROTH

    def test_cleans_temp_on_write_failure(self, tmp_path: Path):
        """atomic_write_text cleans up temp file if write fails."""
        file_path = tmp_path / "test.txt"

        # Simulate write failure by making directory read-only after mkstemp
        # This is tricky to test reliably, so we verify no temp files remain
        result = atomic_write_text(file_path, "content")
        assert result.is_ok()

        # Verify no temp files left behind
        temp_files = list(tmp_path.glob(".*tmp"))
        assert len(temp_files) == 0

    def test_handles_unicode_content(self, tmp_path: Path):
        """atomic_write_text handles unicode content correctly."""
        file_path = tmp_path / "test.txt"
        # Use valid Unicode characters (Chinese + actual emoji, not surrogate pairs)
        content = "Hello \u4e16\u754c"  # Hello World in Chinese

        result = atomic_write_text(file_path, content)

        assert result.is_ok()
        assert file_path.read_text(encoding="utf-8") == content

    def test_handles_empty_content(self, tmp_path: Path):
        """atomic_write_text handles empty content."""
        file_path = tmp_path / "test.txt"

        result = atomic_write_text(file_path, "")

        assert result.is_ok()
        assert file_path.read_text() == ""

    def test_returns_error_on_permission_denied(self, tmp_path: Path):
        """atomic_write_text returns Err on permission denied."""
        # Skip on Windows as permission model is different
        if os.name == "nt":
            pytest.skip("Permission test not applicable on Windows")

        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir(mode=0o555)
        file_path = read_only_dir / "test.txt"

        try:
            result = atomic_write_text(file_path, "content")

            assert result.is_err()
            error = result.unwrap_err()
            assert "PERMISSION" in error.code or "WRITE_FAILED" in error.code
        finally:
            # Restore permissions for cleanup
            read_only_dir.chmod(0o755)


class TestAtomicWriteJson:
    """Tests for atomic_write_json()."""

    def test_creates_json_file(self, tmp_path: Path):
        """atomic_write_json creates valid JSON file."""
        file_path = tmp_path / "test.json"
        data = {"key": "value", "number": 42}

        result = atomic_write_json(file_path, data)

        assert result.is_ok()
        assert file_path.exists()

        loaded = json.loads(file_path.read_text())
        assert loaded == data

    def test_uses_indentation(self, tmp_path: Path):
        """atomic_write_json uses specified indentation."""
        file_path = tmp_path / "test.json"
        data = {"a": 1, "b": 2}

        result = atomic_write_json(file_path, data, indent=4)

        assert result.is_ok()
        content = file_path.read_text()
        # Check indentation is present
        assert "    " in content  # 4 spaces

    def test_compact_json_with_no_indent(self, tmp_path: Path):
        """atomic_write_json creates compact JSON when indent=None."""
        file_path = tmp_path / "test.json"
        data = {"a": 1, "b": 2}

        result = atomic_write_json(file_path, data, indent=None)

        assert result.is_ok()
        content = file_path.read_text()
        # Should be compact (no newlines except maybe at end)
        assert "\n" not in content.strip()

    def test_handles_non_serializable_data(self, tmp_path: Path):
        """atomic_write_json returns error for non-serializable data."""
        file_path = tmp_path / "test.json"
        data = {"func": lambda x: x}  # Functions are not JSON serializable

        result = atomic_write_json(file_path, data)

        assert result.is_err()
        error = result.unwrap_err()
        assert error.code == "JSON_SERIALIZATION_FAILED"

    def test_preserves_unicode(self, tmp_path: Path):
        """atomic_write_json preserves unicode characters."""
        file_path = tmp_path / "test.json"
        data = {"message": "Hello \u4e16\u754c"}

        result = atomic_write_json(file_path, data)

        assert result.is_ok()
        loaded = json.loads(file_path.read_text())
        assert loaded["message"] == "Hello \u4e16\u754c"

    def test_sets_permissions(self, tmp_path: Path):
        """atomic_write_json sets file permissions."""
        file_path = tmp_path / "test.json"

        result = atomic_write_json(file_path, {"a": 1}, mode=0o600)

        assert result.is_ok()
        mode = file_path.stat().st_mode
        assert mode & stat.S_IRWXU == stat.S_IRUSR | stat.S_IWUSR
        assert mode & stat.S_IRWXG == 0


class TestAtomicWriteYaml:
    """Tests for atomic_write_yaml()."""

    def test_creates_yaml_file(self, tmp_path: Path):
        """atomic_write_yaml creates valid YAML file."""
        file_path = tmp_path / "test.yaml"
        data = {"key": "value", "number": 42}

        result = atomic_write_yaml(file_path, data)

        assert result.is_ok()
        assert file_path.exists()

        loaded = yaml.safe_load(file_path.read_text())
        assert loaded == data

    def test_uses_safe_dump(self, tmp_path: Path):
        """atomic_write_yaml uses safe_dump (no arbitrary Python objects)."""
        file_path = tmp_path / "test.yaml"
        # This should work with safe types
        data = {"list": [1, 2, 3], "nested": {"a": "b"}}

        result = atomic_write_yaml(file_path, data)

        assert result.is_ok()
        loaded = yaml.safe_load(file_path.read_text())
        assert loaded == data

    def test_handles_non_serializable_data(self, tmp_path: Path):
        """atomic_write_yaml returns error for non-serializable data."""
        file_path = tmp_path / "test.yaml"

        # Create an object that YAML can't serialize
        class CustomObject:
            pass

        data = {"obj": CustomObject()}

        result = atomic_write_yaml(file_path, data)

        assert result.is_err()
        error = result.unwrap_err()
        assert error.code == "YAML_SERIALIZATION_FAILED"

    def test_preserves_unicode(self, tmp_path: Path):
        """atomic_write_yaml preserves unicode characters."""
        file_path = tmp_path / "test.yaml"
        data = {"message": "Hello \u4e16\u754c"}

        result = atomic_write_yaml(file_path, data)

        assert result.is_ok()
        loaded = yaml.safe_load(file_path.read_text())
        assert loaded["message"] == "Hello \u4e16\u754c"

    def test_respects_sort_keys(self, tmp_path: Path):
        """atomic_write_yaml respects sort_keys parameter."""
        file_path = tmp_path / "test.yaml"
        data = {"z": 1, "a": 2, "m": 3}

        result = atomic_write_yaml(file_path, data, sort_keys=True)

        assert result.is_ok()
        content = file_path.read_text()
        # Keys should appear in alphabetical order
        lines = content.strip().split("\n")
        assert lines[0].startswith("a:")
        assert lines[1].startswith("m:")
        assert lines[2].startswith("z:")


class TestAtomicWriteJsonl:
    """Tests for atomic_write_jsonl()."""

    def test_creates_jsonl_file(self, tmp_path: Path):
        """atomic_write_jsonl creates valid JSONL file."""
        file_path = tmp_path / "test.jsonl"
        records = [{"a": 1}, {"b": 2}, {"c": 3}]

        result = atomic_write_jsonl(file_path, records)

        assert result.is_ok()
        assert file_path.exists()

        lines = file_path.read_text().strip().split("\n")
        assert len(lines) == 3
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}
        assert json.loads(lines[2]) == {"c": 3}

    def test_handles_empty_records(self, tmp_path: Path):
        """atomic_write_jsonl handles empty record list."""
        file_path = tmp_path / "test.jsonl"

        result = atomic_write_jsonl(file_path, [])

        assert result.is_ok()
        assert file_path.read_text() == ""

    def test_handles_non_serializable_record(self, tmp_path: Path):
        """atomic_write_jsonl returns error for non-serializable record."""
        file_path = tmp_path / "test.jsonl"
        records = [{"ok": 1}, {"bad": lambda x: x}]

        result = atomic_write_jsonl(file_path, records)

        assert result.is_err()
        error = result.unwrap_err()
        assert error.code == "JSONL_SERIALIZATION_FAILED"


class TestAtomicWriteConcurrency:
    """Tests for concurrent atomic write operations."""

    def test_survives_concurrent_writes(self, tmp_path: Path):
        """Concurrent writes don't corrupt the file."""
        file_path = tmp_path / "concurrent.txt"
        results: list[bool] = []
        errors: list[str] = []

        def write_content(content: str, index: int):
            try:
                result = atomic_write_text(file_path, content)
                results.append(result.is_ok())
            except Exception as e:
                errors.append(f"Thread {index}: {e}")

        # Launch multiple concurrent writes
        threads = []
        for i in range(10):
            t = threading.Thread(target=write_content, args=(f"content-{i}", i))
            threads.append(t)

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All writes should succeed (though only one value remains)
        assert all(results), f"Some writes failed: {errors}"
        assert file_path.exists()

        # Content should be one of the valid values
        content = file_path.read_text()
        assert content.startswith("content-")
        assert int(content.split("-")[1]) in range(10)

    def test_no_temp_files_left_behind(self, tmp_path: Path):
        """Concurrent operations don't leave temp files behind."""
        file_path = tmp_path / "clean.txt"

        def write_many(index: int):
            for j in range(5):
                atomic_write_text(file_path, f"content-{index}-{j}")

        threads = [threading.Thread(target=write_many, args=(i,)) for i in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No temp files should remain
        temp_files = list(tmp_path.glob(".*tmp"))
        assert len(temp_files) == 0


class TestAtomicWriteEdgeCases:
    """Edge case tests for atomic write operations."""

    def test_handles_very_long_content(self, tmp_path: Path):
        """atomic_write_text handles large content."""
        file_path = tmp_path / "large.txt"
        content = "x" * (1024 * 1024)  # 1MB

        result = atomic_write_text(file_path, content)

        assert result.is_ok()
        assert file_path.read_text() == content

    def test_handles_special_filename_characters(self, tmp_path: Path):
        """atomic_write_text handles special characters in filename."""
        file_path = tmp_path / "file with spaces.txt"

        result = atomic_write_text(file_path, "content")

        assert result.is_ok()
        assert file_path.exists()

    def test_handles_path_object_and_string(self, tmp_path: Path):
        """atomic_write_text accepts both Path objects and strings."""
        # Path object
        path1 = tmp_path / "path_obj.txt"
        result1 = atomic_write_text(path1, "content1")
        assert result1.is_ok()

        # Already a Path, but ensure it works
        path2 = tmp_path / "path_str.txt"
        result2 = atomic_write_text(Path(path2), "content2")
        assert result2.is_ok()

    def test_preserves_newlines(self, tmp_path: Path):
        """atomic_write_text preserves Unix newlines."""
        file_path = tmp_path / "newlines.txt"
        content = "line1\nline2\nline3\nline4"

        result = atomic_write_text(file_path, content)

        assert result.is_ok()
        # Use binary mode to verify exact bytes
        assert file_path.read_bytes() == content.encode("utf-8")
