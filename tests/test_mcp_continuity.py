"""Tests for MCP server continuity integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def cleanup_continuity():
    """Clean up continuity marker after test."""
    from sage.continuity import CONTINUITY_FILE

    yield
    if CONTINUITY_FILE.exists():
        CONTINUITY_FILE.unlink()


@pytest.fixture
def temp_sage_dir(tmp_path):
    """Create temporary sage directory."""
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    checkpoints_dir = sage_dir / "checkpoints"
    checkpoints_dir.mkdir()
    return sage_dir


class TestGetContinuityContext:
    """Tests for _get_continuity_context helper function."""

    def test_returns_none_when_no_marker(self, cleanup_continuity):
        """Returns None when no continuity marker exists."""
        from sage.continuity import CONTINUITY_FILE

        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        from sage.mcp_server import _get_continuity_context

        result = _get_continuity_context()
        assert result is None

    def test_returns_context_when_marker_present(self, cleanup_continuity):
        """Returns context string when marker exists."""
        from sage.continuity import mark_for_continuity
        from sage.mcp_server import _get_continuity_context

        mark_for_continuity(
            reason="test",
            compaction_summary="Testing continuity feature",
        )

        result = _get_continuity_context()

        assert result is not None
        assert "SESSION CONTINUITY" in result
        assert "Testing continuity" in result

    def test_clears_marker_after_injection(self, cleanup_continuity):
        """Marker is cleared after context is retrieved."""
        from sage.continuity import has_pending_continuity, mark_for_continuity
        from sage.mcp_server import _get_continuity_context

        mark_for_continuity(reason="test", compaction_summary="Test")
        assert has_pending_continuity()

        _get_continuity_context()

        assert not has_pending_continuity()

    def test_includes_compaction_summary(self, cleanup_continuity):
        """Context includes the compaction summary."""
        from sage.continuity import mark_for_continuity
        from sage.mcp_server import _get_continuity_context

        summary = "User was researching Python patterns for async code"
        mark_for_continuity(reason="post_compaction", compaction_summary=summary)

        result = _get_continuity_context()

        assert result is not None
        assert "Python patterns" in result

    def test_truncates_very_long_summaries(self, cleanup_continuity):
        """Very long summaries are truncated."""
        from sage.continuity import mark_for_continuity
        from sage.mcp_server import _get_continuity_context

        long_summary = "A" * 3000  # Over 2000 char limit
        mark_for_continuity(reason="test", compaction_summary=long_summary)

        # Mock checkpoint loading to isolate summary truncation test
        with patch("sage.mcp_server.load_checkpoint", return_value=None):
            result = _get_continuity_context()

        assert result is not None
        # Summary should be truncated to ~2000 chars + "..."
        assert "A" * 2000 in result  # First 2000 chars preserved
        assert "..." in result  # Truncation marker present
        # Full summary (3000 A's) should NOT be present
        assert "A" * 3000 not in result

    def test_respects_continuity_enabled_config(self, cleanup_continuity):
        """Returns None if continuity is disabled in config."""
        from sage.continuity import mark_for_continuity

        mark_for_continuity(reason="test", compaction_summary="Test")

        # Mock config with continuity_enabled=False
        mock_config = MagicMock()
        mock_config.continuity_enabled = False

        with patch("sage.mcp_server.get_sage_config", return_value=mock_config):
            from sage.mcp_server import _get_continuity_context

            result = _get_continuity_context()

        assert result is None


class TestSageContinuityStatus:
    """Tests for sage_continuity_status MCP tool."""

    def test_injects_pending_context(self, cleanup_continuity):
        """Injects context if pending marker exists."""
        from sage.continuity import mark_for_continuity
        from sage.mcp_server import sage_continuity_status

        mark_for_continuity(reason="test", compaction_summary="Test summary")

        result = sage_continuity_status()

        assert "SESSION CONTINUITY" in result
        assert "Test summary" in result

    def test_returns_status_when_no_marker(self, cleanup_continuity):
        """Returns status info when no marker exists."""
        from sage.continuity import CONTINUITY_FILE

        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        # Mock watcher status - need to patch in sage.watcher module
        mock_watcher = {"running": False, "pid": None, "transcript": None}

        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            from sage.mcp_server import sage_continuity_status

            result = sage_continuity_status()

        assert "Continuity Status" in result
        assert "No pending continuity" in result

    def test_shows_watcher_running_status(self, cleanup_continuity):
        """Shows watcher status in output."""
        from sage.continuity import CONTINUITY_FILE

        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        mock_watcher = {"running": True, "pid": 12345, "transcript": "/path/to/transcript.jsonl"}

        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            from sage.mcp_server import sage_continuity_status

            result = sage_continuity_status()

        assert "12345" in result
        assert "running" in result.lower()


class TestSageHealthWithContinuity:
    """Tests for sage_health integration with continuity."""

    def test_health_includes_watcher_status(self, cleanup_continuity):
        """sage_health includes watcher daemon status."""
        mock_watcher = {"running": False, "pid": None, "transcript": None}

        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            from sage.mcp_server import sage_health

            result = sage_health()

        # Should mention watcher
        assert "watcher" in result.lower()

    def test_health_injects_continuity_if_pending(self, cleanup_continuity):
        """sage_health injects continuity context if pending."""
        from sage.continuity import mark_for_continuity

        mark_for_continuity(reason="test", compaction_summary="Health check test")

        mock_watcher = {"running": True, "pid": 1234, "transcript": None}

        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            from sage.mcp_server import sage_health

            result = sage_health()

        # Should include both continuity context and health info
        assert "SESSION CONTINUITY" in result
        assert "Health Check" in result

    def test_health_shows_watcher_not_running(self, cleanup_continuity):
        """sage_health shows instruction to start watcher."""
        from sage.continuity import CONTINUITY_FILE

        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        mock_watcher = {"running": False, "pid": None, "transcript": None}

        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            from sage.mcp_server import sage_health

            result = sage_health()

        assert "not running" in result.lower() or "watcher start" in result.lower()


class TestContinuityConfigOptions:
    """Tests for continuity-related config options."""

    def test_continuity_enabled_default_true(self):
        """continuity_enabled defaults to True."""
        from sage.config import SageConfig

        config = SageConfig()
        assert config.continuity_enabled is True

    def test_watcher_auto_start_default_false(self):
        """watcher_auto_start defaults to False."""
        from sage.config import SageConfig

        config = SageConfig()
        assert config.watcher_auto_start is False


class TestCheckpointInjection:
    """Tests for checkpoint loading during continuity injection."""

    def test_loads_checkpoint_from_marker(self, cleanup_continuity, temp_sage_dir):
        """Loads and formats checkpoint from marker path."""
        # Create a checkpoint file
        checkpoint_path = temp_sage_dir / "checkpoints" / "test-checkpoint.md"
        checkpoint_content = """---
id: test-checkpoint
ts: 2024-01-15T10:00:00Z
trigger: synthesis
core_question: How does X work?
thesis: X works by doing Y
confidence: 0.8
---

# Test Checkpoint

This is a test checkpoint for continuity testing.
"""
        checkpoint_path.write_text(checkpoint_content)

        # Create marker pointing to checkpoint
        from sage.continuity import mark_for_continuity

        with patch("sage.continuity.SAGE_DIR", temp_sage_dir):
            mark_for_continuity(
                checkpoint_path=checkpoint_path,
                reason="post_compaction",
                compaction_summary="Test summary",
            )

        # Mock the checkpoint loading
        mock_checkpoint = MagicMock()
        mock_checkpoint.id = "test-checkpoint"
        mock_checkpoint.thesis = "X works by doing Y"
        mock_checkpoint.confidence = 0.8

        with patch("sage.mcp_server.load_checkpoint", return_value=mock_checkpoint):
            with patch("sage.mcp_server.format_checkpoint_for_context", return_value="Formatted checkpoint"):
                from sage.mcp_server import _get_continuity_context

                result = _get_continuity_context()

        assert result is not None
        # Should include either checkpoint content or "not found" message
        # (depends on whether load_checkpoint finds it)

    def test_handles_missing_checkpoint(self, cleanup_continuity, temp_sage_dir):
        """Handles case where checkpoint file doesn't exist."""
        from sage.continuity import mark_for_continuity

        nonexistent = temp_sage_dir / "checkpoints" / "nonexistent.md"

        with patch("sage.continuity.SAGE_DIR", temp_sage_dir):
            mark_for_continuity(
                checkpoint_path=nonexistent,
                reason="test",
            )

        with patch("sage.mcp_server.load_checkpoint", return_value=None):
            from sage.mcp_server import _get_continuity_context

            result = _get_continuity_context()

        # Should still return something, indicating checkpoint not found
        assert result is not None
        assert "not found" in result.lower() or "no checkpoint" in result.lower()


class TestIntegration:
    """Integration tests for continuity in MCP server."""

    def test_full_continuity_injection_flow(self, cleanup_continuity):
        """Test complete flow: mark -> inject -> cleared."""
        from sage.continuity import has_pending_continuity, mark_for_continuity
        from sage.mcp_server import _get_continuity_context

        # 1. Initially no marker
        assert not has_pending_continuity()

        # 2. Mark for continuity (simulating watcher detecting compaction)
        mark_for_continuity(
            reason="post_compaction",
            compaction_summary="User was working on feature X",
        )
        assert has_pending_continuity()

        # 3. Get context (simulating sage tool call)
        context = _get_continuity_context()
        assert context is not None
        assert "feature X" in context

        # 4. Marker should be cleared
        assert not has_pending_continuity()

        # 5. Subsequent calls return None
        assert _get_continuity_context() is None

    def test_multiple_tools_only_inject_once(self, cleanup_continuity):
        """Context is only injected on first tool call."""
        from sage.continuity import mark_for_continuity
        from sage.mcp_server import _get_continuity_context

        mark_for_continuity(reason="test", compaction_summary="Once only")

        # First call gets context
        first = _get_continuity_context()
        assert first is not None
        assert "Once only" in first

        # Second call returns None
        second = _get_continuity_context()
        assert second is None
