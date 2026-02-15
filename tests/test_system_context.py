"""Tests for system_context.py (v4.0).

Tests the system folder functionality for auto-injecting agent-managed context.
"""

import pytest
from pathlib import Path

from sage.system_context import (
    SystemFile,
    get_system_folder,
    load_system_files,
    format_system_context,
    ensure_system_folder,
    save_system_file,
    remove_system_file,
    list_system_files,
    _estimate_tokens,
    _truncate_content,
)


class TestGetSystemFolder:
    """Tests for get_system_folder()."""

    def test_returns_path_for_project(self, tmp_path):
        """Should return .sage/system/ under project path."""
        result = get_system_folder(tmp_path)
        assert result == tmp_path / ".sage" / "system"

    def test_returns_path_without_project(self):
        """Should return a valid path when no project specified."""
        result = get_system_folder(None)
        assert result is not None
        assert str(result).endswith("system")


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_estimates_roughly_4_chars_per_token(self):
        """Should estimate ~4 chars per token."""
        content = "a" * 100
        tokens = _estimate_tokens(content)
        assert tokens == 25

    def test_handles_empty_string(self):
        """Should handle empty string."""
        assert _estimate_tokens("") == 0


class TestTruncateContent:
    """Tests for content truncation."""

    def test_returns_content_under_limit(self):
        """Should return unchanged if under limit."""
        content = "Short content"
        result = _truncate_content(content, max_tokens=100)
        assert result == content

    def test_truncates_long_content(self):
        """Should truncate content exceeding limit."""
        content = "word " * 500  # ~2500 chars
        result = _truncate_content(content, max_tokens=100)  # ~400 chars
        assert len(result) < 500
        assert result.endswith("... (truncated)")

    def test_truncates_at_word_boundary(self):
        """Should try to truncate at word boundary."""
        content = "word1 word2 word3 word4 word5"
        result = _truncate_content(content, max_tokens=5)  # ~20 chars
        # Should truncate cleanly
        assert "... (truncated)" in result


class TestLoadSystemFiles:
    """Tests for loading system folder files."""

    def test_returns_empty_list_for_nonexistent_folder(self, tmp_path):
        """Should return empty list if folder doesn't exist."""
        result = load_system_files(tmp_path)
        assert result == []

    def test_loads_objective_first(self, tmp_path):
        """Should load objective.md as first file."""
        system_dir = tmp_path / ".sage" / "system"
        system_dir.mkdir(parents=True)

        (system_dir / "zzz.md").write_text("Z content")
        (system_dir / "objective.md").write_text("Objective content")
        (system_dir / "aaa.md").write_text("A content")

        result = load_system_files(tmp_path)

        assert len(result) == 3
        assert result[0].name == "objective.md"
        assert result[0].content == "Objective content"

    def test_loads_constraints_second(self, tmp_path):
        """Should load constraints.md as second file."""
        system_dir = tmp_path / ".sage" / "system"
        system_dir.mkdir(parents=True)

        (system_dir / "zzz.md").write_text("Z content")
        (system_dir / "constraints.md").write_text("Constraints content")
        (system_dir / "objective.md").write_text("Objective content")

        result = load_system_files(tmp_path)

        assert len(result) == 3
        assert result[0].name == "objective.md"
        assert result[1].name == "constraints.md"

    def test_loads_pinned_files(self, tmp_path):
        """Should load pinned/* files after priority files."""
        system_dir = tmp_path / ".sage" / "system"
        pinned_dir = system_dir / "pinned"
        pinned_dir.mkdir(parents=True)

        (system_dir / "other.md").write_text("Other content")
        (pinned_dir / "pinned1.md").write_text("Pinned content")

        result = load_system_files(tmp_path)

        # pinned should come before other (non-priority) files
        names = [f.name for f in result]
        assert "pinned1.md" in names
        assert "other.md" in names

    def test_respects_token_budget(self, tmp_path):
        """Should stop loading when token budget exhausted."""
        system_dir = tmp_path / ".sage" / "system"
        system_dir.mkdir(parents=True)

        # Write large files
        (system_dir / "objective.md").write_text("x" * 8000)  # ~2000 tokens
        (system_dir / "second.md").write_text("y" * 8000)  # ~2000 tokens

        # Load with small budget
        result = load_system_files(tmp_path, max_tokens=500)

        # Should only load one file (possibly truncated)
        assert len(result) <= 2
        total_tokens = sum(f.tokens for f in result)
        assert total_tokens <= 500 + 50  # Allow some overflow from truncation

    def test_truncates_file_to_fit(self, tmp_path):
        """Should truncate file if it exceeds remaining budget."""
        system_dir = tmp_path / ".sage" / "system"
        system_dir.mkdir(parents=True)

        (system_dir / "objective.md").write_text("a" * 400)  # ~100 tokens
        (system_dir / "second.md").write_text("b" * 4000)  # ~1000 tokens

        result = load_system_files(tmp_path, max_tokens=200)

        assert len(result) == 2
        # Second file should be truncated
        assert result[1].content.endswith("... (truncated)")


class TestFormatSystemContext:
    """Tests for formatting system context."""

    def test_returns_empty_string_for_no_files(self):
        """Should return empty string if no files."""
        result = format_system_context([])
        assert result == ""

    def test_formats_with_header(self):
        """Should include header with file count."""
        files = [
            SystemFile(name="test.md", path=Path("test.md"), content="Content", tokens=10)
        ]
        result = format_system_context(files, use_toon=False)

        assert "SYSTEM CONTEXT" in result
        assert "1 file(s)" in result
        assert "10 tokens" in result

    def test_formats_file_content(self):
        """Should include file content with header."""
        files = [
            SystemFile(name="objective.md", path=Path("objective.md"), content="My goal", tokens=5)
        ]
        result = format_system_context(files, use_toon=False)

        assert "## objective.md" in result
        assert "My goal" in result

    def test_toon_format(self):
        """Should use compact format with use_toon=True."""
        files = [
            SystemFile(name="objective.md", path=Path("objective.md"), content="My goal", tokens=5)
        ]
        result = format_system_context(files, use_toon=True)

        # TOON format uses shorter headers
        assert "# System [1]" in result
        assert "## objective" in result  # Without .md extension


class TestEnsureSystemFolder:
    """Tests for ensuring system folder structure."""

    def test_creates_system_folder(self, tmp_path):
        """Should create .sage/system/ directory."""
        result = ensure_system_folder(tmp_path)

        assert result.exists()
        assert result == tmp_path / ".sage" / "system"

    def test_creates_pinned_subfolder(self, tmp_path):
        """Should create pinned/ subdirectory."""
        ensure_system_folder(tmp_path)

        pinned = tmp_path / ".sage" / "system" / "pinned"
        assert pinned.exists()

    def test_is_idempotent(self, tmp_path):
        """Should be safe to call multiple times."""
        ensure_system_folder(tmp_path)
        ensure_system_folder(tmp_path)
        ensure_system_folder(tmp_path)

        assert (tmp_path / ".sage" / "system").exists()


class TestSaveSystemFile:
    """Tests for saving system files."""

    def test_saves_file(self, tmp_path):
        """Should save file to system folder."""
        result = save_system_file("test.md", "Content", tmp_path)

        assert result.exists()
        assert result.read_text() == "Content"

    def test_adds_md_extension(self, tmp_path):
        """Should add .md extension if missing."""
        result = save_system_file("test", "Content", tmp_path)

        assert result.name == "test.md"

    def test_sanitizes_filename(self, tmp_path):
        """Should sanitize dangerous filenames."""
        result = save_system_file("../../../etc/passwd", "Content", tmp_path)

        # Should not contain path traversal
        assert ".." not in str(result)
        assert result.parent == tmp_path / ".sage" / "system"


class TestRemoveSystemFile:
    """Tests for removing system files."""

    def test_removes_existing_file(self, tmp_path):
        """Should remove existing file."""
        save_system_file("test.md", "Content", tmp_path)

        result = remove_system_file("test.md", tmp_path)

        assert result is True
        assert not (tmp_path / ".sage" / "system" / "test.md").exists()

    def test_returns_false_for_nonexistent(self, tmp_path):
        """Should return False if file doesn't exist."""
        ensure_system_folder(tmp_path)

        result = remove_system_file("nonexistent.md", tmp_path)

        assert result is False


class TestListSystemFiles:
    """Tests for listing system files."""

    def test_returns_empty_for_nonexistent(self, tmp_path):
        """Should return empty list if folder doesn't exist."""
        result = list_system_files(tmp_path)
        assert result == []

    def test_lists_root_files(self, tmp_path):
        """Should list files in system folder root."""
        save_system_file("a.md", "A", tmp_path)
        save_system_file("b.md", "B", tmp_path)

        result = list_system_files(tmp_path)

        assert "a.md" in result
        assert "b.md" in result

    def test_lists_pinned_files(self, tmp_path):
        """Should list pinned files with path prefix."""
        ensure_system_folder(tmp_path)
        pinned = tmp_path / ".sage" / "system" / "pinned"
        (pinned / "test.md").write_text("Test")

        result = list_system_files(tmp_path)

        assert "pinned/test.md" in result
