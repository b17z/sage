"""Tests for the checkpoint queue builtin plugin."""

from sage.plugins.base import PluginResult
from sage.plugins.builtin.checkpoint_queue import CheckpointQueuePlugin
from sage.plugins.events import CheckpointCreated, CompactionDetected, DaemonStarted


class TestCheckpointQueuePlugin:
    """Tests for CheckpointQueuePlugin."""

    def test_has_correct_name(self):
        """Plugin has correct name."""
        plugin = CheckpointQueuePlugin()
        assert plugin.name == "checkpoint-queue"

    def test_subscribes_to_checkpoint_created(self):
        """Plugin subscribes to CheckpointCreated events."""
        plugin = CheckpointQueuePlugin()
        assert CheckpointCreated in plugin.subscribes_to

    def test_subscribes_to_daemon_started(self):
        """Plugin subscribes to DaemonStarted events."""
        plugin = CheckpointQueuePlugin()
        assert DaemonStarted in plugin.subscribes_to

    def test_accepts_checkpoint_created_event(self):
        """Plugin accepts CheckpointCreated events."""
        plugin = CheckpointQueuePlugin()
        event = CheckpointCreated(
            timestamp="2024-01-01T00:00:00Z",
            checkpoint_id="test-id",
            checkpoint_type="recovery",
        )

        assert plugin.accepts_event(event) is True

    def test_accepts_daemon_started_event(self):
        """Plugin accepts DaemonStarted events."""
        plugin = CheckpointQueuePlugin()
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/file.jsonl",
            pid=12345,
        )

        assert plugin.accepts_event(event) is True

    def test_rejects_other_events(self):
        """Plugin rejects non-subscribed events."""
        plugin = CheckpointQueuePlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/path/to/file.jsonl",
        )

        assert plugin.accepts_event(event) is False

    def test_handle_checkpoint_created_queues(self):
        """handle() queues checkpoint on CheckpointCreated."""
        plugin = CheckpointQueuePlugin()
        event = CheckpointCreated(
            timestamp="2024-01-01T00:00:00Z",
            checkpoint_id="my-checkpoint-id",
            checkpoint_type="recovery",
        )

        result = plugin.handle(event)

        assert isinstance(result, PluginResult)
        assert len(result.actions) == 2  # queue_for_injection, log

        queue_action = next(a for a in result.actions if a.action_type == "queue_for_injection")
        assert queue_action.parameters["checkpoint_id"] == "my-checkpoint-id"
        assert queue_action.parameters["checkpoint_type"] == "recovery"

    def test_handle_daemon_started_logs(self):
        """handle() logs on DaemonStarted."""
        plugin = CheckpointQueuePlugin()
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/file.jsonl",
            pid=12345,
        )

        result = plugin.handle(event)

        assert isinstance(result, PluginResult)
        assert len(result.actions) == 1

        log_action = result.actions[0]
        assert log_action.action_type == "log"
        assert "12345" in log_action.parameters["message"]

    def test_handle_returns_empty_for_wrong_event(self):
        """handle() returns empty for non-subscribed events."""
        plugin = CheckpointQueuePlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/path/to/file.jsonl",
        )

        result = plugin.handle(event)

        assert result.actions == ()

    def test_configure_sets_max_queue_size(self):
        """configure() sets max queue size from settings."""
        plugin = CheckpointQueuePlugin()

        plugin.configure({"max_queue_size": 50})

        assert plugin._max_queue_size == 50

    def test_configure_validates_queue_size(self):
        """configure() validates queue size is positive integer."""
        plugin = CheckpointQueuePlugin()

        # Invalid: zero
        plugin.configure({"max_queue_size": 0})
        assert plugin._max_queue_size == 20  # Default unchanged

        # Invalid: negative
        plugin.configure({"max_queue_size": -5})
        assert plugin._max_queue_size == 20  # Default unchanged

        # Valid
        plugin.configure({"max_queue_size": 100})
        assert plugin._max_queue_size == 100

    def test_configure_ignores_invalid_types(self):
        """configure() ignores non-integer queue size values."""
        plugin = CheckpointQueuePlugin()

        plugin.configure({"max_queue_size": "not-a-number"})

        assert plugin._max_queue_size == 20  # Default unchanged

    def test_handles_structured_checkpoint_type(self):
        """handle() works with structured checkpoint type."""
        plugin = CheckpointQueuePlugin()
        event = CheckpointCreated(
            timestamp="2024-01-01T00:00:00Z",
            checkpoint_id="structured-id",
            checkpoint_type="structured",
        )

        result = plugin.handle(event)

        queue_action = next(a for a in result.actions if a.action_type == "queue_for_injection")
        assert queue_action.parameters["checkpoint_type"] == "structured"
