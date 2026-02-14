"""Tests for plugin action executor."""

import json
import time
from pathlib import Path

import pytest

from sage.plugins.base import ALLOWED_ACTION_TYPES, PluginAction, PluginResult
from sage.plugins.executor import (
    ACTION_HANDLERS,
    _execute_action,
    execute_actions,
    validate_action_types,
)


@pytest.fixture
def temp_sage_dir(tmp_path: Path, monkeypatch):
    """Create a temporary .sage directory for testing."""
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    (sage_dir / "logs").mkdir()

    # Patch SAGE_DIR in config module - executor imports it from there
    monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)

    return sage_dir


class TestActionHandlers:
    """Tests for ACTION_HANDLERS mapping."""

    def test_all_allowed_types_have_handlers(self):
        """Every allowed action type has a handler."""
        for action_type in ALLOWED_ACTION_TYPES:
            assert action_type in ACTION_HANDLERS

    def test_handlers_are_callable(self):
        """All handlers are callable functions."""
        for handler in ACTION_HANDLERS.values():
            assert callable(handler)

    def test_validate_action_types_passes(self):
        """validate_action_types() returns True when all handlers present."""
        assert validate_action_types() is True


class TestExecuteLog:
    """Tests for log action execution."""

    def test_executes_without_error(self, temp_sage_dir: Path, caplog):
        """Log action executes without error."""
        action = PluginAction(
            action_type="log",
            parameters={"message": "Test log message", "level": "info"},
        )

        # Should not raise
        _execute_action(action)

    def test_writes_to_log_file(self, temp_sage_dir: Path):
        """Log action writes to watcher log file."""
        # Import here to get the patched SAGE_DIR
        from sage.plugins.executor import _log_to_watcher_file

        _log_to_watcher_file("Test message")

        log_file = temp_sage_dir / "logs" / "watcher.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "Test message" in content

    def test_handles_missing_message(self, temp_sage_dir: Path, caplog):
        """Log action handles missing message parameter."""
        action = PluginAction(action_type="log", parameters={})

        # Should not raise, but should log warning
        _execute_action(action)


class TestExecuteWriteMarker:
    """Tests for write_marker action execution."""

    def test_writes_continuity_marker(self, temp_sage_dir: Path, monkeypatch):
        """write_marker action creates continuity marker."""
        # Patch continuity module to use temp dir and disable project detection
        monkeypatch.setattr("sage.continuity.SAGE_DIR", temp_sage_dir)
        monkeypatch.setattr(
            "sage.continuity.CONTINUITY_FILE",
            temp_sage_dir / "continuity.json",
        )
        monkeypatch.setattr("sage.continuity.detect_project_root", lambda: None)
        monkeypatch.setattr("sage.config.detect_project_root", lambda: None)

        action = PluginAction(
            action_type="write_marker",
            parameters={
                "reason": "post_compaction",
                "compaction_summary": "Test summary",
            },
        )

        _execute_action(action)

        marker_file = temp_sage_dir / "continuity.json"
        assert marker_file.exists()

        data = json.loads(marker_file.read_text())
        assert data["reason"] == "post_compaction"
        assert data["compaction_summary"] == "Test summary"


class TestExecuteQueueForInjection:
    """Tests for queue_for_injection action execution."""

    def _start_session(self, temp_sage_dir: Path):
        """Helper to start a session for queue tests."""
        from sage.session import start_session

        # Patch session module to use temp dir
        import sage.session

        sage.session.SESSION_FILE = temp_sage_dir / "session.json"
        sage.session.INJECTION_QUEUE_FILE = temp_sage_dir / "injection_queue.json"

        start_session("/test/transcript.jsonl")

    def test_creates_queue_file(self, temp_sage_dir: Path, monkeypatch):
        """queue_for_injection creates queue file."""
        # Patch session module paths
        monkeypatch.setattr("sage.session.SAGE_DIR", temp_sage_dir)
        monkeypatch.setattr("sage.session.SESSION_FILE", temp_sage_dir / "session.json")
        monkeypatch.setattr(
            "sage.session.INJECTION_QUEUE_FILE", temp_sage_dir / "injection_queue.json"
        )

        self._start_session(temp_sage_dir)

        action = PluginAction(
            action_type="queue_for_injection",
            parameters={
                "checkpoint_id": "test-checkpoint-id",
                "checkpoint_type": "recovery",
            },
        )

        _execute_action(action)

        queue_file = temp_sage_dir / "injection_queue.json"
        assert queue_file.exists()

        data = json.loads(queue_file.read_text())
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["checkpoint_id"] == "test-checkpoint-id"
        assert data[0]["checkpoint_type"] == "recovery"

    def test_appends_to_existing_queue(self, temp_sage_dir: Path, monkeypatch):
        """queue_for_injection appends to existing queue."""
        # Patch session module paths
        monkeypatch.setattr("sage.session.SAGE_DIR", temp_sage_dir)
        monkeypatch.setattr("sage.session.SESSION_FILE", temp_sage_dir / "session.json")
        monkeypatch.setattr(
            "sage.session.INJECTION_QUEUE_FILE", temp_sage_dir / "injection_queue.json"
        )

        self._start_session(temp_sage_dir)

        # Create initial queue entry via the session API
        from sage.session import queue_checkpoint

        queue_checkpoint("existing", "structured")

        action = PluginAction(
            action_type="queue_for_injection",
            parameters={
                "checkpoint_id": "new-checkpoint",
                "checkpoint_type": "recovery",
            },
        )

        _execute_action(action)

        queue_file = temp_sage_dir / "injection_queue.json"
        data = json.loads(queue_file.read_text())
        assert len(data) == 2
        assert data[0]["checkpoint_id"] == "existing"
        assert data[1]["checkpoint_id"] == "new-checkpoint"

    def test_avoids_duplicates(self, temp_sage_dir: Path, monkeypatch):
        """queue_for_injection doesn't add duplicate entries."""
        # Patch session module paths
        monkeypatch.setattr("sage.session.SAGE_DIR", temp_sage_dir)
        monkeypatch.setattr("sage.session.SESSION_FILE", temp_sage_dir / "session.json")
        monkeypatch.setattr(
            "sage.session.INJECTION_QUEUE_FILE", temp_sage_dir / "injection_queue.json"
        )

        self._start_session(temp_sage_dir)

        # Create initial entry
        from sage.session import queue_checkpoint

        queue_checkpoint("existing", "recovery")

        action = PluginAction(
            action_type="queue_for_injection",
            parameters={
                "checkpoint_id": "existing",  # Same ID
                "checkpoint_type": "recovery",
            },
        )

        _execute_action(action)

        queue_file = temp_sage_dir / "injection_queue.json"
        data = json.loads(queue_file.read_text())
        assert len(data) == 1  # No duplicate added


class TestExecuteActions:
    """Tests for execute_actions function."""

    def test_executes_all_actions(self, temp_sage_dir: Path, caplog):
        """Executes all actions in result."""
        result = PluginResult.from_actions(
            PluginAction(action_type="log", parameters={"message": "First"}),
            PluginAction(action_type="log", parameters={"message": "Second"}),
        )

        execute_actions(result, blocking=True)

        # Both log messages should have been processed
        # (we can't easily verify without deeper mocking)

    def test_blocking_mode_waits(self, temp_sage_dir: Path):
        """Blocking mode executes synchronously."""
        start = time.time()

        result = PluginResult.single(
            PluginAction(action_type="log", parameters={"message": "test"})
        )

        execute_actions(result, blocking=True)

        # Should complete immediately (no thread)
        elapsed = time.time() - start
        assert elapsed < 1.0

    def test_fire_and_forget_returns_immediately(self, temp_sage_dir: Path):
        """Non-blocking mode returns immediately."""
        start = time.time()

        result = PluginResult.single(
            PluginAction(action_type="log", parameters={"message": "test"})
        )

        execute_actions(result, blocking=False)

        # Should return immediately (spawns thread)
        elapsed = time.time() - start
        assert elapsed < 0.1

    def test_handles_unknown_action_type(self, temp_sage_dir: Path):
        """Raises error for unknown action type in blocking mode."""

        # We can't create an invalid PluginAction, so we test _execute_action directly
        # with a mocked invalid action
        class FakeAction:
            action_type = "unknown"
            parameters = {}

        with pytest.raises(ValueError, match="Unknown action type"):
            _execute_action(FakeAction())  # type: ignore

    def test_empty_result_does_nothing(self, temp_sage_dir: Path):
        """Empty result executes without error."""
        result = PluginResult.empty()

        # Should not raise
        execute_actions(result, blocking=True)
