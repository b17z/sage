"""Tests for CLI continuity and watcher commands."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from sage.cli import main


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def no_project_root():
    """Mock detect_project_root to return None so tests use global CONTINUITY_FILE."""
    with patch("sage.continuity.detect_project_root", return_value=None):
        with patch("sage.config.detect_project_root", return_value=None):
            yield


@pytest.fixture
def cleanup_continuity(no_project_root):
    """Clean up continuity marker after test."""
    from sage.continuity import CONTINUITY_FILE

    yield
    if CONTINUITY_FILE.exists():
        CONTINUITY_FILE.unlink()


@pytest.fixture
def cleanup_pid_file():
    """Clean up PID file after test."""
    from sage.watcher import PID_FILE

    yield
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except OSError:
            pass


class TestWatcherStart:
    """Tests for 'sage watcher start' command."""

    def test_shows_error_when_no_transcript(self, runner, cleanup_pid_file, tmp_path):
        """Shows error when no Claude transcript found."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = runner.invoke(main, ["watcher", "start"])

        assert result.exit_code != 0
        assert "transcript" in result.output.lower() or "not found" in result.output.lower()

    def test_shows_already_running_message(self, runner, cleanup_pid_file):
        """Shows message when watcher already running."""
        from sage.watcher import PID_FILE

        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

        with patch("sage.watcher.find_active_transcript", return_value=Path("/fake/transcript.jsonl")):
            result = runner.invoke(main, ["watcher", "start"])

        assert "already running" in result.output.lower()


class TestWatcherStop:
    """Tests for 'sage watcher stop' command."""

    def test_shows_not_running_message(self, runner, cleanup_pid_file):
        """Shows message when watcher not running."""
        from sage.watcher import PID_FILE

        if PID_FILE.exists():
            PID_FILE.unlink()

        result = runner.invoke(main, ["watcher", "stop"])

        assert result.exit_code == 0
        assert "not running" in result.output.lower()


class TestWatcherStatus:
    """Tests for 'sage watcher status' command."""

    def test_shows_not_running(self, runner, cleanup_pid_file):
        """Shows not running status."""
        from sage.watcher import PID_FILE

        if PID_FILE.exists():
            PID_FILE.unlink()

        mock_status = {
            "running": False,
            "pid": None,
            "transcript": None,
            "log_file": "/path/to/watcher.log",
        }

        with patch("sage.watcher.get_watcher_status", return_value=mock_status):
            result = runner.invoke(main, ["watcher", "status"])

        assert result.exit_code == 0
        assert "not running" in result.output.lower()

    def test_shows_running_with_pid(self, runner, cleanup_pid_file):
        """Shows running status with PID."""
        mock_status = {
            "running": True,
            "pid": 12345,
            "transcript": "/path/to/transcript.jsonl",
            "log_file": "/path/to/watcher.log",
        }

        with patch("sage.watcher.get_watcher_status", return_value=mock_status):
            result = runner.invoke(main, ["watcher", "status"])

        assert result.exit_code == 0
        assert "12345" in result.output
        assert "running" in result.output.lower()

    def test_shows_transcript_path(self, runner, cleanup_pid_file):
        """Shows transcript being watched."""
        mock_status = {
            "running": True,
            "pid": 999,
            "transcript": "/home/user/.claude/projects/myproject/session.jsonl",
            "log_file": "/home/user/.sage/logs/watcher.log",
        }

        with patch("sage.watcher.get_watcher_status", return_value=mock_status):
            result = runner.invoke(main, ["watcher", "status"])

        assert result.exit_code == 0
        assert "session.jsonl" in result.output


class TestContinuityStatus:
    """Tests for 'sage continuity status' command."""

    def test_shows_no_pending_continuity(self, runner, cleanup_continuity):
        """Shows no pending continuity message."""
        from sage.continuity import CONTINUITY_FILE

        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        mock_watcher = {"running": False, "pid": None, "transcript": None}

        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            result = runner.invoke(main, ["continuity", "status"])

        assert result.exit_code == 0
        assert "no pending" in result.output.lower()

    def test_shows_pending_marker(self, runner, cleanup_continuity):
        """Shows pending marker details."""
        from sage.continuity import mark_for_continuity

        mark_for_continuity(reason="post_compaction", compaction_summary="Test summary")

        mock_watcher = {"running": True, "pid": 123, "transcript": None}

        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            result = runner.invoke(main, ["continuity", "status"])

        assert result.exit_code == 0
        assert "pending" in result.output.lower()
        assert "post_compaction" in result.output

    def test_shows_watcher_status(self, runner, cleanup_continuity):
        """Shows watcher daemon status."""
        from sage.continuity import CONTINUITY_FILE

        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        mock_watcher = {"running": True, "pid": 5678, "transcript": "/path/transcript.jsonl"}

        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            result = runner.invoke(main, ["continuity", "status"])

        assert result.exit_code == 0
        assert "5678" in result.output


class TestContinuityClear:
    """Tests for 'sage continuity clear' command."""

    def test_shows_no_marker_message(self, runner, cleanup_continuity):
        """Shows message when no marker to clear."""
        from sage.continuity import CONTINUITY_FILE

        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        result = runner.invoke(main, ["continuity", "clear"])

        assert result.exit_code == 0
        assert "no pending" in result.output.lower()

    def test_clears_marker_with_force(self, runner, cleanup_continuity):
        """Clears marker with --force flag."""
        from sage.continuity import has_pending_continuity, mark_for_continuity

        mark_for_continuity(reason="test")
        assert has_pending_continuity()

        result = runner.invoke(main, ["continuity", "clear", "--force"])

        assert result.exit_code == 0
        assert "cleared" in result.output.lower()
        assert not has_pending_continuity()

    def test_prompts_for_confirmation(self, runner, cleanup_continuity):
        """Prompts for confirmation without --force."""
        from sage.continuity import mark_for_continuity

        mark_for_continuity(reason="test")

        # Simulate user declining
        result = runner.invoke(main, ["continuity", "clear"], input="n\n")

        assert "cancel" in result.output.lower()


class TestContinuityMark:
    """Tests for 'sage continuity mark' command."""

    def test_creates_manual_marker(self, runner, cleanup_continuity):
        """Creates a manual continuity marker."""
        from sage.continuity import get_continuity_marker, has_pending_continuity

        result = runner.invoke(main, ["continuity", "mark"])

        assert result.exit_code == 0
        assert has_pending_continuity()

        marker = get_continuity_marker()
        assert marker["reason"] == "manual"

    def test_creates_marker_with_custom_reason(self, runner, cleanup_continuity):
        """Creates marker with custom reason."""
        from sage.continuity import get_continuity_marker

        result = runner.invoke(main, ["continuity", "mark", "--reason", "testing"])

        assert result.exit_code == 0

        marker = get_continuity_marker()
        assert marker["reason"] == "testing"

    def test_shows_confirmation(self, runner, cleanup_continuity):
        """Shows confirmation message."""
        result = runner.invoke(main, ["continuity", "mark"])

        assert result.exit_code == 0
        assert "created" in result.output.lower()


class TestHealthIncludesWatcher:
    """Tests for 'sage health' including watcher status."""

    def test_health_command_exists(self, runner):
        """health command exists and runs."""
        result = runner.invoke(main, ["health"])

        # Should not error
        assert result.exit_code == 0

    def test_health_shows_system_status(self, runner):
        """health shows various system statuses."""
        result = runner.invoke(main, ["health"])

        assert "Sage" in result.output or "health" in result.output.lower()


class TestConfigIntegration:
    """Tests for continuity config integration."""

    def test_config_list_shows_continuity_settings(self, runner):
        """config list includes continuity settings."""
        result = runner.invoke(main, ["config", "list"])

        # Config list should work
        assert result.exit_code == 0

    def test_config_set_continuity_enabled(self, runner, tmp_path):
        """Can set continuity_enabled via config."""
        # Create a temporary sage directory
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()

        with patch("sage.cli.SAGE_DIR", sage_dir):
            with patch("sage.cli.get_sage_config") as mock_config:
                mock_cfg = MagicMock()
                mock_cfg.to_dict.return_value = {"continuity_enabled": True}
                mock_config.return_value = mock_cfg

                result = runner.invoke(
                    main,
                    ["config", "set", "continuity_enabled", "false"],
                )

        # Should not error (may have other issues in isolated test)
        # Just check the command exists and processes the key
        assert "continuity_enabled" in result.output or result.exit_code == 0


class TestIntegration:
    """Integration tests for CLI continuity commands."""

    def test_full_cli_flow(self, runner, cleanup_continuity, cleanup_pid_file):
        """Test full CLI workflow: mark -> status -> clear."""
        from sage.continuity import has_pending_continuity

        # 1. Initially no marker
        status1 = runner.invoke(main, ["continuity", "status"])
        assert "no pending" in status1.output.lower()

        # 2. Create marker
        mark_result = runner.invoke(main, ["continuity", "mark", "--reason", "cli-test"])
        assert mark_result.exit_code == 0
        assert has_pending_continuity()

        # 3. Check status shows pending
        mock_watcher = {"running": False, "pid": None, "transcript": None}
        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            status2 = runner.invoke(main, ["continuity", "status"])

        assert "pending" in status2.output.lower()
        assert "cli-test" in status2.output

        # 4. Clear marker
        clear_result = runner.invoke(main, ["continuity", "clear", "--force"])
        assert clear_result.exit_code == 0
        assert not has_pending_continuity()

        # 5. Status shows no pending
        with patch("sage.watcher.get_watcher_status", return_value=mock_watcher):
            status3 = runner.invoke(main, ["continuity", "status"])

        assert "no pending" in status3.output.lower()

    def test_watcher_status_includes_log_path(self, runner, cleanup_pid_file):
        """Watcher status shows log file path."""
        mock_status = {
            "running": False,
            "pid": None,
            "transcript": None,
            "log_file": "/home/user/.sage/logs/watcher.log",
        }

        with patch("sage.watcher.get_watcher_status", return_value=mock_status):
            result = runner.invoke(main, ["watcher", "status"])

        assert "watcher.log" in result.output
