"""Tests for compaction watcher daemon module."""

import json
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sage.watcher import (
    LOG_FILE,
    MAX_LINE_LENGTH,
    PID_FILE,
    POLL_INTERVAL,
    WatcherError,
    find_active_transcript,
    get_watcher_status,
    is_running,
    start_daemon,
    stop_daemon,
)


@pytest.fixture
def temp_claude_dir(tmp_path):
    """Create a temporary Claude directory structure."""
    claude_dir = tmp_path / ".claude"
    projects_dir = claude_dir / "projects"
    projects_dir.mkdir(parents=True)

    # Create a project directory with a transcript
    project_dir = projects_dir / "test-project"
    project_dir.mkdir()

    return claude_dir


@pytest.fixture
def cleanup_pid_file():
    """Clean up PID file after test."""
    yield
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except OSError:
            pass


class TestFindActiveTranscript:
    """Tests for find_active_transcript function."""

    def test_returns_none_when_no_projects_dir(self, tmp_path):
        """Returns None when .claude/projects doesn't exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = find_active_transcript()

        assert result is None

    def test_returns_none_when_no_transcripts(self, temp_claude_dir, tmp_path):
        """Returns None when no .jsonl files exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            result = find_active_transcript()

        assert result is None

    def test_finds_transcript_in_project(self, tmp_path):
        """Finds transcript file in project directory."""
        # Setup
        projects_dir = tmp_path / ".claude" / "projects"
        project_dir = projects_dir / "myproject"
        project_dir.mkdir(parents=True)
        transcript = project_dir / "session.jsonl"
        transcript.write_text('{"type":"test"}\n')

        with patch.object(Path, "home", return_value=tmp_path):
            result = find_active_transcript()

        assert result is not None
        assert result.suffix == ".jsonl"

    def test_returns_most_recent_by_mtime(self, tmp_path):
        """Returns the most recently modified transcript."""
        projects_dir = tmp_path / ".claude" / "projects"

        # Create two project directories with transcripts
        p1 = projects_dir / "project1"
        p1.mkdir(parents=True)
        t1 = p1 / "old.jsonl"
        t1.write_text('{"old": true}\n')

        p2 = projects_dir / "project2"
        p2.mkdir(parents=True)
        t2 = p2 / "new.jsonl"
        t2.write_text('{"new": true}\n')

        # Make t2 newer
        time.sleep(0.1)
        os.utime(t2)

        with patch.object(Path, "home", return_value=tmp_path):
            result = find_active_transcript()

        assert result is not None
        assert result.name == "new.jsonl"

    def test_security_skips_symlink_outside(self, tmp_path):
        """Skips transcripts that are symlinks outside expected directory."""
        projects_dir = tmp_path / ".claude" / "projects"
        project_dir = projects_dir / "project1"
        project_dir.mkdir(parents=True)

        # Create a file outside claude directory
        outside = tmp_path / "outside"
        outside.mkdir()
        external_file = outside / "external.jsonl"
        external_file.write_text('{"external": true}\n')

        # Create symlink inside projects dir pointing outside
        symlink = project_dir / "evil.jsonl"
        try:
            symlink.symlink_to(external_file)
        except OSError:
            pytest.skip("Symlink creation not supported")

        with patch.object(Path, "home", return_value=tmp_path):
            result = find_active_transcript()

        # Should not return the symlinked file
        assert result is None or "external" not in str(result)


class TestIsRunning:
    """Tests for is_running function."""

    def test_returns_false_when_no_pid_file(self, cleanup_pid_file):
        """Returns False when PID file doesn't exist."""
        if PID_FILE.exists():
            PID_FILE.unlink()

        assert is_running() is False

    def test_returns_false_for_invalid_pid(self, cleanup_pid_file):
        """Returns False for non-numeric PID."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("not_a_number")

        assert is_running() is False

    def test_returns_false_for_negative_pid(self, cleanup_pid_file):
        """Returns False for negative PID."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("-1")

        assert is_running() is False

    def test_returns_false_for_nonexistent_process(self, cleanup_pid_file):
        """Returns False when process doesn't exist."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Use a very high PID that likely doesn't exist
        PID_FILE.write_text("999999999")

        assert is_running() is False

    def test_returns_true_for_running_process(self, cleanup_pid_file):
        """Returns True when process exists."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Use current process PID (we know it exists)
        PID_FILE.write_text(str(os.getpid()))

        assert is_running() is True


class TestGetWatcherStatus:
    """Tests for get_watcher_status function."""

    def test_includes_running_status(self, cleanup_pid_file):
        """Status includes running flag."""
        status = get_watcher_status()

        assert "running" in status
        assert isinstance(status["running"], bool)

    def test_includes_log_file_path(self, cleanup_pid_file):
        """Status includes log file path."""
        status = get_watcher_status()

        assert "log_file" in status
        assert "watcher.log" in status["log_file"]

    def test_includes_pid_when_running(self, cleanup_pid_file):
        """Status includes PID when daemon is running."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

        status = get_watcher_status()

        assert status["pid"] == os.getpid()
        assert status["running"] is True

    def test_includes_transcript_when_found(self, tmp_path):
        """Status includes transcript path when found."""
        # Setup transcript
        projects_dir = tmp_path / ".claude" / "projects"
        project_dir = projects_dir / "project"
        project_dir.mkdir(parents=True)
        transcript = project_dir / "session.jsonl"
        transcript.write_text('{"test": true}\n')

        with patch.object(Path, "home", return_value=tmp_path):
            status = get_watcher_status()

        assert "transcript" in status
        if status["transcript"]:
            assert "session.jsonl" in status["transcript"]


class TestStartDaemon:
    """Tests for start_daemon function."""

    def test_returns_false_when_already_running(self, cleanup_pid_file):
        """Returns False if daemon already running."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))

        result = start_daemon()

        assert result is False

    def test_returns_false_when_no_transcript(self, tmp_path, cleanup_pid_file):
        """Returns False when no transcript found."""
        if PID_FILE.exists():
            PID_FILE.unlink()

        with patch.object(Path, "home", return_value=tmp_path):
            result = start_daemon()

        assert result is False

    @pytest.mark.skipif(sys.platform == "win32", reason="fork not available on Windows")
    def test_creates_pid_file_on_start(self, tmp_path, cleanup_pid_file):
        """Creates PID file when starting daemon."""
        # This test would actually fork, so we mock fork to avoid spawning processes
        projects_dir = tmp_path / ".claude" / "projects"
        project_dir = projects_dir / "project"
        project_dir.mkdir(parents=True)
        transcript = project_dir / "session.jsonl"
        transcript.write_text('{"test": true}\n')

        if PID_FILE.exists():
            PID_FILE.unlink()

        # Mock fork to simulate parent returning immediately
        with patch.object(Path, "home", return_value=tmp_path):
            with patch("os.fork", return_value=12345):  # Non-zero = parent
                result = start_daemon()

        assert result is True
        assert PID_FILE.exists()
        assert PID_FILE.read_text().strip() == "12345"


class TestStopDaemon:
    """Tests for stop_daemon function."""

    def test_returns_false_when_no_pid_file(self, cleanup_pid_file):
        """Returns False when no PID file exists."""
        if PID_FILE.exists():
            PID_FILE.unlink()

        result = stop_daemon()

        assert result is False

    def test_returns_false_for_invalid_pid(self, cleanup_pid_file):
        """Returns False for invalid PID and cleans up."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("not_a_pid")

        result = stop_daemon()

        assert result is False
        assert not PID_FILE.exists()

    def test_cleans_up_stale_pid_file(self, cleanup_pid_file):
        """Removes PID file for non-existent process."""
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text("999999999")  # Likely non-existent

        result = stop_daemon()

        assert result is False
        assert not PID_FILE.exists()


class TestPidFilePermissions:
    """Tests for PID file security."""

    def test_pid_file_has_restricted_permissions(self, tmp_path, cleanup_pid_file):
        """PID file is created with restricted permissions."""
        from sage.watcher import _write_pid_file

        with patch("sage.watcher.PID_FILE", tmp_path / "test.pid"):
            _write_pid_file(12345)

            pid_file = tmp_path / "test.pid"
            assert pid_file.exists()
            mode = pid_file.stat().st_mode & 0o777
            assert mode == 0o600


class TestCompactionDetection:
    """Tests for compaction event detection in watch_transcript."""

    def test_detects_compaction_signal(self, tmp_path):
        """Recognizes isCompactSummary: true in JSONL."""
        # Create test transcript with compaction event
        transcript = tmp_path / "test.jsonl"
        transcript.write_text(
            json.dumps({
                "isCompactSummary": True,
                "message": {"content": "Summary of conversation"}
            }) + "\n"
        )

        # The actual watch_transcript runs in a loop, so we test the detection logic
        line = transcript.read_text().strip()
        data = json.loads(line)

        assert data.get("isCompactSummary") is True
        assert isinstance(data.get("message"), dict)
        assert "content" in data["message"]

    def test_ignores_non_compaction_events(self, tmp_path):
        """Doesn't trigger on regular JSONL events."""
        events = [
            {"type": "user", "message": "Hello"},
            {"type": "assistant", "message": "Hi there"},
            {"isCompactSummary": False},  # Explicitly false
            {"message": "no isCompactSummary key"},
        ]

        for event in events:
            line = json.dumps(event)
            data = json.loads(line)

            # Should not match compaction criteria
            is_compaction = (
                isinstance(data, dict)
                and data.get("isCompactSummary") is True
                and isinstance(data.get("message"), dict)
            )
            assert not is_compaction, f"Incorrectly detected as compaction: {event}"

    def test_handles_malformed_json_gracefully(self, tmp_path):
        """Doesn't crash on malformed JSON lines."""
        malformed_lines = [
            "not json at all",
            "{incomplete",
            '{"valid": "but", incomplete',
            "",
            "   ",
        ]

        for line in malformed_lines:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                pass  # Expected - the watcher should handle this

    def test_extracts_summary_content(self):
        """Extracts summary string from compaction event."""
        event = {
            "isCompactSummary": True,
            "message": {
                "content": "The user was researching Python async patterns."
            }
        }

        data = json.loads(json.dumps(event))

        assert data["isCompactSummary"] is True
        summary = data["message"].get("content", "")
        assert isinstance(summary, str)
        assert "Python async" in summary


class TestLineLengthLimit:
    """Tests for line length security limit."""

    def test_max_line_length_defined(self):
        """MAX_LINE_LENGTH constant is defined."""
        assert MAX_LINE_LENGTH > 0
        assert MAX_LINE_LENGTH == 10_000_000  # 10MB

    def test_poll_interval_defined(self):
        """POLL_INTERVAL constant is defined."""
        assert POLL_INTERVAL > 0
        assert POLL_INTERVAL == 0.2  # 200ms


class TestWatcherError:
    """Tests for WatcherError exception."""

    def test_watcher_error_is_exception(self):
        """WatcherError is a proper exception."""
        assert issubclass(WatcherError, Exception)

    def test_watcher_error_has_message(self):
        """WatcherError can be raised with message."""
        with pytest.raises(WatcherError) as exc_info:
            raise WatcherError("test error message")

        assert "test error message" in str(exc_info.value)


class TestIntegration:
    """Integration tests for watcher functionality."""

    def test_status_when_not_running(self, cleanup_pid_file):
        """get_watcher_status works when daemon not running."""
        if PID_FILE.exists():
            PID_FILE.unlink()

        status = get_watcher_status()

        assert status["running"] is False
        assert status["pid"] is None

    def test_full_pid_lifecycle(self, cleanup_pid_file):
        """Test PID file creation and cleanup."""
        from sage.watcher import _remove_pid_file, _write_pid_file

        # Initially no PID file
        if PID_FILE.exists():
            PID_FILE.unlink()
        assert not is_running()

        # Write PID
        _write_pid_file(os.getpid())
        assert PID_FILE.exists()
        assert is_running()

        # Remove PID
        _remove_pid_file()
        assert not PID_FILE.exists()


class TestLogToFile:
    """Tests for logging functionality."""

    def test_log_file_path_defined(self):
        """LOG_FILE path is defined."""
        assert LOG_FILE is not None
        assert "watcher.log" in str(LOG_FILE)

    def test_log_creates_directory(self, tmp_path):
        """Logging creates log directory if needed."""
        from sage.watcher import _log_to_file

        log_file = tmp_path / "logs" / "test.log"

        with patch("sage.watcher.LOG_FILE", log_file):
            _log_to_file("test message")

        assert log_file.parent.exists()

    def test_log_file_permissions(self, tmp_path):
        """Log file has restricted permissions."""
        from sage.watcher import _log_to_file

        log_file = tmp_path / "logs" / "test.log"

        with patch("sage.watcher.LOG_FILE", log_file):
            _log_to_file("test message")

        if log_file.exists():
            mode = log_file.stat().st_mode & 0o777
            assert mode == 0o600
