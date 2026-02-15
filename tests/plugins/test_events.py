"""Tests for plugin event types."""

import pytest

from sage.plugins.events import (
    CheckpointCreated,
    CompactionDetected,
    DaemonStarted,
    DaemonStopping,
    SessionChanged,
)


class TestDaemonStarted:
    """Tests for DaemonStarted event."""

    def test_creates_with_all_fields(self):
        """Event can be created with all required fields."""
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/transcript.jsonl",
            pid=12345,
        )

        assert event.timestamp == "2024-01-01T00:00:00Z"
        assert event.transcript_path == "/path/to/transcript.jsonl"
        assert event.pid == 12345

    def test_is_frozen(self):
        """Event is immutable."""
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/transcript.jsonl",
            pid=12345,
        )

        with pytest.raises(AttributeError):
            event.pid = 99999

    def test_is_watcher_event(self):
        """Event is a valid WatcherEvent type."""
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/transcript.jsonl",
            pid=12345,
        )
        # Check it's one of the union types
        assert isinstance(event, DaemonStarted)


class TestDaemonStopping:
    """Tests for DaemonStopping event."""

    def test_creates_with_all_fields(self):
        """Event can be created with all required fields."""
        event = DaemonStopping(
            timestamp="2024-01-01T00:00:00Z",
            reason="signal",
        )

        assert event.timestamp == "2024-01-01T00:00:00Z"
        assert event.reason == "signal"

    def test_is_frozen(self):
        """Event is immutable."""
        event = DaemonStopping(
            timestamp="2024-01-01T00:00:00Z",
            reason="signal",
        )

        with pytest.raises(AttributeError):
            event.reason = "error"


class TestCompactionDetected:
    """Tests for CompactionDetected event."""

    def test_creates_with_all_fields(self):
        """Event can be created with all required fields."""
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="Conversation has been compacted...",
            transcript_path="/path/to/transcript.jsonl",
        )

        assert event.timestamp == "2024-01-01T00:00:00Z"
        assert event.summary == "Conversation has been compacted..."
        assert event.transcript_path == "/path/to/transcript.jsonl"

    def test_is_frozen(self):
        """Event is immutable."""
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/path/to/transcript.jsonl",
        )

        with pytest.raises(AttributeError):
            event.summary = "modified"


class TestCheckpointCreated:
    """Tests for CheckpointCreated event."""

    def test_creates_with_all_fields(self):
        """Event can be created with all required fields."""
        event = CheckpointCreated(
            timestamp="2024-01-01T00:00:00Z",
            checkpoint_id="2024-01-01T00-00-00_recovery-test",
            checkpoint_type="recovery",
        )

        assert event.timestamp == "2024-01-01T00:00:00Z"
        assert event.checkpoint_id == "2024-01-01T00-00-00_recovery-test"
        assert event.checkpoint_type == "recovery"

    def test_is_frozen(self):
        """Event is immutable."""
        event = CheckpointCreated(
            timestamp="2024-01-01T00:00:00Z",
            checkpoint_id="test-id",
            checkpoint_type="recovery",
        )

        with pytest.raises(AttributeError):
            event.checkpoint_type = "structured"

    def test_structured_type(self):
        """Event can have structured checkpoint type."""
        event = CheckpointCreated(
            timestamp="2024-01-01T00:00:00Z",
            checkpoint_id="test-id",
            checkpoint_type="structured",
        )

        assert event.checkpoint_type == "structured"


class TestSessionChanged:
    """Tests for SessionChanged event."""

    def test_creates_with_all_fields(self):
        """Event can be created with all required fields."""
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        assert event.timestamp == "2024-01-01T00:00:00Z"
        assert event.old_transcript_path == "/path/to/old.jsonl"
        assert event.new_transcript_path == "/path/to/new.jsonl"
        assert event.project_path == "/path/to/project"

    def test_old_transcript_can_be_none(self):
        """Old transcript path can be None on first detection."""
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path=None,
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        assert event.old_transcript_path is None

    def test_is_frozen(self):
        """Event is immutable."""
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path="/path/to/old.jsonl",
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )

        with pytest.raises(AttributeError):
            event.new_transcript_path = "/different/path.jsonl"

    def test_is_watcher_event(self):
        """Event is a valid WatcherEvent type."""
        event = SessionChanged(
            timestamp="2024-01-01T00:00:00Z",
            old_transcript_path=None,
            new_transcript_path="/path/to/new.jsonl",
            project_path="/path/to/project",
        )
        assert isinstance(event, SessionChanged)
