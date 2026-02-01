"""Event types for the watcher daemon plugin system.

Events are immutable dataclasses that represent things that happened
in the watcher daemon. Plugins subscribe to specific event types and
receive instances when those events occur.

Security:
- All events are frozen (immutable)
- No arbitrary code execution from event data
- Event data is validated before creation
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DaemonStarted:
    """Emitted when the watcher daemon starts.

    Attributes:
        timestamp: ISO format timestamp when daemon started
        transcript_path: Path to the transcript file being watched
        pid: Process ID of the daemon
    """

    timestamp: str
    transcript_path: str
    pid: int


@dataclass(frozen=True)
class DaemonStopping:
    """Emitted when the watcher daemon is stopping.

    Attributes:
        timestamp: ISO format timestamp when stopping began
        reason: Why the daemon is stopping (signal, error, manual)
    """

    timestamp: str
    reason: str


@dataclass(frozen=True)
class CompactionDetected:
    """Emitted when compaction is detected in the transcript.

    This is the primary event that triggers recovery checkpoint generation.

    Attributes:
        timestamp: ISO format timestamp when compaction was detected
        summary: The compaction summary from Claude Code
        transcript_path: Path to the transcript file
    """

    timestamp: str
    summary: str
    transcript_path: str


@dataclass(frozen=True)
class CheckpointCreated:
    """Emitted when any checkpoint is created.

    Allows plugins to react to checkpoint creation, such as
    queueing for injection or updating indexes.

    Attributes:
        timestamp: ISO format timestamp when checkpoint was created
        checkpoint_id: Unique identifier for the checkpoint
        checkpoint_type: Type of checkpoint ("structured" or "recovery")
    """

    timestamp: str
    checkpoint_id: str
    checkpoint_type: str


@dataclass(frozen=True)
class CheckpointFileCreated:
    """Emitted when a new checkpoint file appears in the checkpoints directory.

    This is detected by directory polling, not by the code that creates
    the checkpoint. Used to queue checkpoints created by Claude (structured)
    or by external processes.

    Attributes:
        timestamp: ISO format timestamp when file was detected
        file_path: Full path to the checkpoint file
        checkpoint_id: Extracted checkpoint ID (filename stem)
        checkpoint_type: Inferred type ("structured" or "recovery")
    """

    timestamp: str
    file_path: str
    checkpoint_id: str
    checkpoint_type: str


# Union type for all events
WatcherEvent = (
    DaemonStarted
    | DaemonStopping
    | CompactionDetected
    | CheckpointCreated
    | CheckpointFileCreated
)
