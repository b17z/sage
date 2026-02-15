"""Tests for the session builtin plugin."""

from sage.plugins.base import PluginResult
from sage.plugins.builtin.session import SessionPlugin
from sage.plugins.events import (
    CompactionDetected,
    DaemonStarted,
    DaemonStopping,
    SessionChanged,
)


class TestSessionPlugin:
    """Tests for SessionPlugin."""

    def test_has_correct_name(self):
        """Plugin has correct name."""
        plugin = SessionPlugin()
        assert plugin.name == "session"

    def test_subscribes_to_daemon_started(self):
        """Plugin subscribes to DaemonStarted events."""
        plugin = SessionPlugin()
        assert DaemonStarted in plugin.subscribes_to

    def test_subscribes_to_daemon_stopping(self):
        """Plugin subscribes to DaemonStopping events."""
        plugin = SessionPlugin()
        assert DaemonStopping in plugin.subscribes_to

    def test_subscribes_to_compaction_detected(self):
        """Plugin subscribes to CompactionDetected events."""
        plugin = SessionPlugin()
        assert CompactionDetected in plugin.subscribes_to

    def test_subscribes_to_session_changed(self):
        """Plugin subscribes to SessionChanged events."""
        plugin = SessionPlugin()
        assert SessionChanged in plugin.subscribes_to

    def test_accepts_daemon_started_event(self):
        """Plugin accepts DaemonStarted events."""
        plugin = SessionPlugin()
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/file.jsonl",
            pid=12345,
        )
        assert plugin.accepts_event(event) is True

    def test_accepts_session_changed_event(self):
        """Plugin accepts SessionChanged events."""
        plugin = SessionPlugin()
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )
        assert plugin.accepts_event(event) is True

    def test_handle_daemon_started_returns_actions(self):
        """handle() returns actions for DaemonStarted."""
        plugin = SessionPlugin()
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/file.jsonl",
            pid=12345,
        )

        result = plugin.handle(event)

        assert isinstance(result, PluginResult)
        action_types = [a.action_type for a in result.actions]
        assert "start_session" in action_types
        assert "log" in action_types

    def test_handle_daemon_stopping_returns_actions(self):
        """handle() returns actions for DaemonStopping."""
        plugin = SessionPlugin()
        event = DaemonStopping(
            timestamp="2024-01-01T00:00:00Z",
            reason="signal",
        )

        result = plugin.handle(event)

        assert isinstance(result, PluginResult)
        action_types = [a.action_type for a in result.actions]
        assert "end_session" in action_types
        assert "log" in action_types

    def test_handle_compaction_logs_but_continues_session(self):
        """handle() logs on compaction but doesn't end session."""
        plugin = SessionPlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test summary",
            transcript_path="/path/to/file.jsonl",
        )

        result = plugin.handle(event)

        assert isinstance(result, PluginResult)
        action_types = [a.action_type for a in result.actions]
        assert "log" in action_types
        # Should NOT end session on compaction
        assert "end_session" not in action_types


class TestSessionChangedHandling:
    """Tests for SessionChanged event handling - the restart detection feature."""

    def test_session_changed_marks_for_continuity(self):
        """SessionChanged triggers write_marker action."""
        plugin = SessionPlugin()
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        result = plugin.handle(event)

        action_types = [a.action_type for a in result.actions]
        assert "write_marker" in action_types

    def test_session_changed_ends_old_session(self):
        """SessionChanged ends the old session."""
        plugin = SessionPlugin()
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        result = plugin.handle(event)

        action_types = [a.action_type for a in result.actions]
        assert "end_session" in action_types

    def test_session_changed_starts_new_session(self):
        """SessionChanged starts a new session with new transcript."""
        plugin = SessionPlugin()
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        result = plugin.handle(event)

        action_types = [a.action_type for a in result.actions]
        assert "start_session" in action_types

        # Verify the start_session uses the NEW transcript path
        start_action = next(a for a in result.actions if a.action_type == "start_session")
        assert start_action.parameters["transcript_path"] == "/path/to/new.jsonl"

    def test_session_changed_logs_transition(self):
        """SessionChanged logs the transition."""
        plugin = SessionPlugin()
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        result = plugin.handle(event)

        action_types = [a.action_type for a in result.actions]
        assert "log" in action_types

    def test_session_changed_marker_has_correct_reason(self):
        """write_marker action has session_restart reason."""
        plugin = SessionPlugin()
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        result = plugin.handle(event)

        marker_action = next(a for a in result.actions if a.action_type == "write_marker")
        assert marker_action.parameters["reason"] == "session_restart"

    def test_session_changed_with_none_old_transcript(self):
        """SessionChanged works when old transcript is None."""
        plugin = SessionPlugin()
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path=None,
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        result = plugin.handle(event)

        # Should still return all expected actions
        action_types = [a.action_type for a in result.actions]
        assert "end_session" in action_types
        assert "write_marker" in action_types
        assert "start_session" in action_types
        assert "log" in action_types

    def test_session_changed_action_order(self):
        """Actions are in correct order: end, mark, start, log."""
        plugin = SessionPlugin()
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        result = plugin.handle(event)

        action_types = [a.action_type for a in result.actions]
        # Verify the order: end old session, mark for continuity, start new session, log
        assert action_types == ["end_session", "write_marker", "start_session", "log"]
