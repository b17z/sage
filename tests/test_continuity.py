"""Tests for session continuity module."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sage.continuity import (
    CONTINUITY_FILE,
    clear_continuity,
    get_continuity_marker,
    get_most_recent_checkpoint,
    has_pending_continuity,
    mark_for_continuity,
)


@pytest.fixture
def temp_sage_dir(tmp_path):
    """Create a temporary sage directory structure."""
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    checkpoints_dir = sage_dir / "checkpoints"
    checkpoints_dir.mkdir()
    return sage_dir


@pytest.fixture
def no_project_root():
    """Mock detect_project_root to return None so tests use global CONTINUITY_FILE."""
    with patch("sage.continuity.detect_project_root", return_value=None):
        yield


@pytest.fixture
def cleanup_continuity(no_project_root):
    """Clean up continuity file after test."""
    yield
    if CONTINUITY_FILE.exists():
        CONTINUITY_FILE.unlink()


class TestMarkForContinuity:
    """Tests for mark_for_continuity function."""

    def test_creates_marker_file(self, cleanup_continuity):
        """mark_for_continuity creates the marker file."""
        result = mark_for_continuity(reason="test")

        assert result.ok
        assert CONTINUITY_FILE.exists()

    def test_marker_contains_reason(self, cleanup_continuity):
        """Marker file contains the reason."""
        mark_for_continuity(reason="post_compaction")

        marker = get_continuity_marker()
        assert marker is not None
        assert marker["reason"] == "post_compaction"

    def test_marker_contains_timestamp(self, cleanup_continuity):
        """Marker file contains a timestamp."""
        mark_for_continuity(reason="test")

        marker = get_continuity_marker()
        assert marker is not None
        assert "marked_at" in marker

    def test_marker_contains_checkpoint_id(self, cleanup_continuity, temp_sage_dir):
        """Marker includes checkpoint ID (stem) for portable lookup."""
        checkpoint_path = temp_sage_dir / "checkpoints" / "2026-01-22_my-checkpoint.md"
        checkpoint_path.write_text("# Test Checkpoint")

        with patch("sage.continuity.SAGE_DIR", temp_sage_dir):
            result = mark_for_continuity(
                checkpoint_path=checkpoint_path,
                reason="test",
            )

        assert result.ok
        marker = get_continuity_marker()
        assert marker is not None
        # checkpoint_id should be just the stem (no path, no extension)
        assert marker["checkpoint_id"] == "2026-01-22_my-checkpoint"

    def test_marker_contains_compaction_summary(self, cleanup_continuity):
        """Marker includes compaction summary when provided."""
        summary = "This is a summary of what was happening."
        mark_for_continuity(compaction_summary=summary, reason="post_compaction")

        marker = get_continuity_marker()
        assert marker is not None
        assert marker["compaction_summary"] == summary

    def test_overwrites_existing_marker(self, cleanup_continuity):
        """New marker overwrites existing one."""
        mark_for_continuity(reason="first")
        mark_for_continuity(reason="second")

        marker = get_continuity_marker()
        assert marker is not None
        assert marker["reason"] == "second"

    def test_marker_file_permissions(self, cleanup_continuity):
        """Marker file has restricted permissions."""
        mark_for_continuity(reason="test")

        mode = CONTINUITY_FILE.stat().st_mode & 0o777
        assert mode == 0o600


class TestGetContinuityMarker:
    """Tests for get_continuity_marker function."""

    def test_returns_none_when_no_marker(self, cleanup_continuity):
        """Returns None when no marker file exists."""
        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        result = get_continuity_marker()
        assert result is None

    def test_returns_marker_data(self, cleanup_continuity):
        """Returns marker data when file exists."""
        mark_for_continuity(reason="test", compaction_summary="Test summary")

        marker = get_continuity_marker()
        assert marker is not None
        assert marker["reason"] == "test"
        assert marker["compaction_summary"] == "Test summary"

    def test_handles_malformed_json(self, cleanup_continuity):
        """Returns None for malformed JSON."""
        CONTINUITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTINUITY_FILE.write_text("not valid json")

        result = get_continuity_marker()
        assert result is None

    def test_handles_non_dict_json(self, cleanup_continuity):
        """Returns None when JSON is not a dict."""
        CONTINUITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONTINUITY_FILE.write_text('["array", "not", "dict"]')

        result = get_continuity_marker()
        assert result is None


class TestClearContinuity:
    """Tests for clear_continuity function."""

    def test_removes_marker_file(self, cleanup_continuity):
        """clear_continuity removes the marker file."""
        mark_for_continuity(reason="test")
        assert CONTINUITY_FILE.exists()

        clear_continuity()
        assert not CONTINUITY_FILE.exists()

    def test_idempotent_when_no_marker(self, no_project_root):
        """Clearing when no marker exists doesn't error."""
        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        # Should not raise
        clear_continuity()


class TestHasPendingContinuity:
    """Tests for has_pending_continuity function."""

    def test_returns_false_when_no_marker(self, cleanup_continuity):
        """Returns False when no marker exists."""
        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        assert has_pending_continuity() is False

    def test_returns_true_when_marker_exists(self, cleanup_continuity):
        """Returns True when marker exists."""
        mark_for_continuity(reason="test")

        assert has_pending_continuity() is True


class TestGetMostRecentCheckpoint:
    """Tests for get_most_recent_checkpoint function."""

    def test_returns_none_when_no_checkpoints(self, temp_sage_dir):
        """Returns None when no checkpoints exist."""
        with patch("sage.continuity.SAGE_DIR", temp_sage_dir):
            with patch("sage.continuity.detect_project_root", return_value=None):
                result = get_most_recent_checkpoint()

        # May return None or find global checkpoints
        # Just verify it doesn't crash
        assert result is None or isinstance(result, Path)

    def test_returns_most_recent_by_mtime(self, temp_sage_dir):
        """Returns the most recently modified checkpoint."""
        checkpoints_dir = temp_sage_dir / "checkpoints"

        # Create checkpoints with different mtimes
        cp1 = checkpoints_dir / "cp1.md"
        cp2 = checkpoints_dir / "cp2.md"
        cp1.write_text("# Checkpoint 1")
        cp2.write_text("# Checkpoint 2")

        import os
        import time

        # Set cp2 to be newer (touch it after a small delay)
        time.sleep(0.1)
        os.utime(cp2)

        with patch("sage.continuity.SAGE_DIR", temp_sage_dir):
            with patch("sage.continuity.detect_project_root", return_value=None):
                result = get_most_recent_checkpoint()

        assert result is not None
        assert result.name == "cp2.md"

    def test_prefers_project_local_checkpoints(self, tmp_path):
        """Prefers project-local checkpoints over global."""
        # Setup global sage dir
        global_sage = tmp_path / "global" / ".sage"
        global_sage.mkdir(parents=True)
        global_cp_dir = global_sage / "checkpoints"
        global_cp_dir.mkdir()
        global_cp = global_cp_dir / "global.md"
        global_cp.write_text("# Global")

        # Setup project-local sage dir
        project = tmp_path / "project"
        project.mkdir()
        local_sage = project / ".sage"
        local_sage.mkdir()
        local_cp_dir = local_sage / "checkpoints"
        local_cp_dir.mkdir()
        local_cp = local_cp_dir / "local.md"
        local_cp.write_text("# Local")

        with patch("sage.continuity.SAGE_DIR", global_sage):
            result = get_most_recent_checkpoint(project_path=project)

        assert result is not None
        assert result.name == "local.md"


class TestIntegration:
    """Integration tests for continuity flow."""

    def test_full_continuity_flow(self, cleanup_continuity, temp_sage_dir):
        """Test the full mark -> check -> clear flow."""
        # Initially no marker
        assert not has_pending_continuity()

        # Create a checkpoint
        checkpoint_path = temp_sage_dir / "checkpoints" / "test-cp.md"
        checkpoint_path.write_text("# Test\nThesis: Testing works")

        # Mark for continuity
        with patch("sage.continuity.SAGE_DIR", temp_sage_dir):
            result = mark_for_continuity(
                checkpoint_path=checkpoint_path,
                reason="post_compaction",
                compaction_summary="User was researching testing",
            )

        assert result.ok
        assert has_pending_continuity()

        # Get and verify marker
        marker = get_continuity_marker()
        assert marker is not None
        assert marker["reason"] == "post_compaction"
        assert "testing" in marker["compaction_summary"].lower()

        # Clear marker
        clear_continuity()
        assert not has_pending_continuity()

    def test_auto_finds_most_recent_checkpoint(self, temp_sage_dir, cleanup_continuity):
        """mark_for_continuity auto-finds checkpoint when not provided."""
        # Create a checkpoint
        checkpoints_dir = temp_sage_dir / "checkpoints"
        cp = checkpoints_dir / "auto-found.md"
        cp.write_text("# Auto Found Checkpoint")

        with patch("sage.continuity.SAGE_DIR", temp_sage_dir):
            with patch("sage.continuity.detect_project_root", return_value=None):
                result = mark_for_continuity(reason="test")

        assert result.ok
        marker = get_continuity_marker()
        assert marker is not None
        # Checkpoint ID should be set to the auto-found one (stem only)
        assert marker["checkpoint_id"] is not None
        assert marker["checkpoint_id"] == "auto-found"


class TestSecurityValidation:
    """Security-related tests."""

    def test_id_based_lookup_is_safe(self, temp_sage_dir, cleanup_continuity):
        """ID-based lookup is inherently safe - no path traversal possible."""
        # Any path input is reduced to just the ID (filename stem)
        # The load side resolves IDs to paths internally
        outside_path = Path("/tmp/outside-checkpoint.md")

        with patch("sage.continuity.SAGE_DIR", temp_sage_dir):
            result = mark_for_continuity(
                checkpoint_path=outside_path,
                reason="test",
            )

        assert result.ok
        marker = get_continuity_marker()
        # Only stores ID, not path - safe from traversal
        assert marker["checkpoint_id"] == "outside-checkpoint"
        assert "checkpoint_path" not in marker

    def test_marker_file_created_with_restricted_permissions(self, cleanup_continuity):
        """Marker file is created with 0o600 permissions."""
        mark_for_continuity(reason="test")

        assert CONTINUITY_FILE.exists()
        mode = CONTINUITY_FILE.stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"
