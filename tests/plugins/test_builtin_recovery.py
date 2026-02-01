"""Tests for the recovery builtin plugin."""

from sage.plugins.base import PluginResult
from sage.plugins.builtin.recovery import RecoveryPlugin
from sage.plugins.events import CompactionDetected, DaemonStarted


class TestRecoveryPlugin:
    """Tests for RecoveryPlugin."""

    def test_has_correct_name(self):
        """Plugin has correct name."""
        plugin = RecoveryPlugin()
        assert plugin.name == "recovery"

    def test_subscribes_to_compaction_detected(self):
        """Plugin subscribes to CompactionDetected events."""
        plugin = RecoveryPlugin()
        assert CompactionDetected in plugin.subscribes_to

    def test_accepts_compaction_event(self):
        """Plugin accepts CompactionDetected events."""
        plugin = RecoveryPlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/path/to/file.jsonl",
        )

        assert plugin.accepts_event(event) is True

    def test_rejects_other_events(self):
        """Plugin rejects non-subscribed events."""
        plugin = RecoveryPlugin()
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/file.jsonl",
            pid=12345,
        )

        assert plugin.accepts_event(event) is False

    def test_handle_returns_actions_for_compaction(self):
        """handle() returns actions for CompactionDetected."""
        plugin = RecoveryPlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="Conversation has been compacted...",
            transcript_path="/path/to/file.jsonl",
        )

        result = plugin.handle(event)

        assert isinstance(result, PluginResult)
        assert len(result.actions) == 3  # save_recovery, write_marker, log

        action_types = [a.action_type for a in result.actions]
        assert "save_recovery" in action_types
        assert "write_marker" in action_types
        assert "log" in action_types

    def test_handle_returns_empty_for_wrong_event(self):
        """handle() returns empty for non-subscribed events."""
        plugin = RecoveryPlugin()
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/file.jsonl",
            pid=12345,
        )

        result = plugin.handle(event)

        assert result.actions == ()

    def test_save_recovery_action_has_transcript_path(self):
        """save_recovery action includes transcript path."""
        plugin = RecoveryPlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/my/transcript.jsonl",
        )

        result = plugin.handle(event)

        save_action = next(a for a in result.actions if a.action_type == "save_recovery")
        assert save_action.parameters["transcript_path"] == "/my/transcript.jsonl"
        assert save_action.parameters["trigger"] == "pre_compact"

    def test_write_marker_action_has_summary(self):
        """write_marker action includes compaction summary."""
        plugin = RecoveryPlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="My compaction summary",
            transcript_path="/path/to/file.jsonl",
        )

        result = plugin.handle(event)

        marker_action = next(a for a in result.actions if a.action_type == "write_marker")
        assert marker_action.parameters["reason"] == "post_compaction"
        assert marker_action.parameters["compaction_summary"] == "My compaction summary"

    def test_configure_sets_salience_threshold(self):
        """configure() sets salience threshold from settings."""
        plugin = RecoveryPlugin()

        plugin.configure({"salience_threshold": 0.3})

        assert plugin._salience_threshold == 0.3

    def test_configure_validates_threshold_range(self):
        """configure() validates threshold is in valid range."""
        plugin = RecoveryPlugin()

        # Invalid: too high
        plugin.configure({"salience_threshold": 1.5})
        assert plugin._salience_threshold == 0.5  # Default unchanged

        # Invalid: negative
        plugin.configure({"salience_threshold": -0.1})
        assert plugin._salience_threshold == 0.5  # Default unchanged

        # Valid
        plugin.configure({"salience_threshold": 0.7})
        assert plugin._salience_threshold == 0.7

    def test_configure_ignores_invalid_types(self):
        """configure() ignores non-numeric threshold values."""
        plugin = RecoveryPlugin()

        plugin.configure({"salience_threshold": "not-a-number"})

        assert plugin._salience_threshold == 0.5  # Default unchanged
