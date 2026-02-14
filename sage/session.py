"""Session tracking for the watcher daemon.

Tracks session boundaries to scope checkpoint injection appropriately.
Sessions are defined by daemon start/stop and transcript changes.

A session represents a continuous period of work. Checkpoints created
during a session are queued for injection if compaction occurs.

Storage:
    ~/.sage/session.json - Current session state
    ~/.sage/injection_queue.json - Session-scoped checkpoint queue
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sage.config import SAGE_DIR

logger = logging.getLogger(__name__)

# Session state file
SESSION_FILE = SAGE_DIR / "session.json"

# Injection queue file
INJECTION_QUEUE_FILE = SAGE_DIR / "injection_queue.json"


@dataclass(frozen=True)
class Session:
    """Represents a watcher session.

    Attributes:
        session_id: Unique identifier for this session
        started_at: ISO timestamp when session started
        transcript_path: Path to transcript being watched
        last_activity: ISO timestamp of last event
    """

    session_id: str
    started_at: str
    transcript_path: str
    last_activity: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "transcript_path": self.transcript_path,
            "last_activity": self.last_activity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """Create from dictionary."""
        return cls(
            session_id=data["session_id"],
            started_at=data["started_at"],
            transcript_path=data["transcript_path"],
            last_activity=data["last_activity"],
        )


@dataclass(frozen=True)
class QueueEntry:
    """An entry in the injection queue.

    Attributes:
        checkpoint_id: ID of the checkpoint
        checkpoint_type: Type ("structured" or "recovery")
        session_id: Session this checkpoint belongs to
        queued_at: ISO timestamp when queued
    """

    checkpoint_id: str
    checkpoint_type: str
    session_id: str
    queued_at: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_type": self.checkpoint_type,
            "session_id": self.session_id,
            "queued_at": self.queued_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueEntry":
        """Create from dictionary."""
        return cls(
            checkpoint_id=data["checkpoint_id"],
            checkpoint_type=data["checkpoint_type"],
            session_id=data["session_id"],
            queued_at=data["queued_at"],
        )


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return uuid.uuid4().hex[:12]


def start_session(transcript_path: str) -> Session:
    """Start a new session.

    Creates a new session and persists it to disk.

    Args:
        transcript_path: Path to the transcript being watched

    Returns:
        The new Session
    """
    now = datetime.now(UTC).isoformat()
    session = Session(
        session_id=generate_session_id(),
        started_at=now,
        transcript_path=transcript_path,
        last_activity=now,
    )

    _save_session(session)
    logger.info(f"Session started: {session.session_id}")
    return session


def get_current_session() -> Session | None:
    """Get the current session, if any.

    Returns:
        Current Session or None if no active session
    """
    if not SESSION_FILE.exists():
        return None

    try:
        with open(SESSION_FILE) as f:
            data = json.load(f)
        return Session.from_dict(data)
    except (json.JSONDecodeError, KeyError, OSError) as e:
        logger.warning(f"Failed to load session: {e}")
        return None


def update_session_activity() -> None:
    """Update the last_activity timestamp of the current session."""
    session = get_current_session()
    if session is None:
        return

    updated = Session(
        session_id=session.session_id,
        started_at=session.started_at,
        transcript_path=session.transcript_path,
        last_activity=datetime.now(UTC).isoformat(),
    )
    _save_session(updated)


def end_session() -> None:
    """End the current session.

    Removes the session file. Does not clear the queue - that's done
    after injection.
    """
    try:
        SESSION_FILE.unlink(missing_ok=True)
        logger.info("Session ended")
    except OSError as e:
        logger.warning(f"Failed to end session: {e}")


def _save_session(session: Session) -> None:
    """Save session to disk."""
    try:
        SAGE_DIR.mkdir(parents=True, exist_ok=True)
        with open(SESSION_FILE, "w") as f:
            json.dump(session.to_dict(), f, indent=2)
        SESSION_FILE.chmod(0o600)
    except OSError as e:
        logger.warning(f"Failed to save session: {e}")


# =============================================================================
# Injection Queue
# =============================================================================


def queue_checkpoint(
    checkpoint_id: str,
    checkpoint_type: str,
    session_id: str | None = None,
) -> bool:
    """Add a checkpoint to the injection queue.

    Args:
        checkpoint_id: ID of the checkpoint
        checkpoint_type: Type ("structured" or "recovery")
        session_id: Session ID (uses current session if None)

    Returns:
        True if queued successfully
    """
    if session_id is None:
        session = get_current_session()
        if session is None:
            logger.warning("No active session, cannot queue checkpoint")
            return False
        session_id = session.session_id

    entry = QueueEntry(
        checkpoint_id=checkpoint_id,
        checkpoint_type=checkpoint_type,
        session_id=session_id,
        queued_at=datetime.now(UTC).isoformat(),
    )

    queue = _load_queue()

    # Avoid duplicates
    if any(e.checkpoint_id == checkpoint_id for e in queue):
        logger.debug(f"Checkpoint already queued: {checkpoint_id}")
        return True

    queue.append(entry)

    # Keep queue bounded (last 20 entries)
    queue = queue[-20:]

    _save_queue(queue)
    logger.info(f"Queued checkpoint: {checkpoint_id} (session: {session_id})")
    return True


def get_queue_for_session(session_id: str) -> list[QueueEntry]:
    """Get all queue entries for a specific session.

    Args:
        session_id: Session to filter by

    Returns:
        List of QueueEntry for that session
    """
    queue = _load_queue()
    return [e for e in queue if e.session_id == session_id]


def get_pending_injections(ttl_hours: float = 4.0) -> list[QueueEntry]:
    """Get checkpoints pending injection.

    Returns entries from the current session plus recent entries from other
    sessions (within TTL). The LLM decides what's relevant from the candidates.

    Args:
        ttl_hours: Maximum age for non-current-session entries (default 4 hours)

    Returns:
        List of QueueEntry to inject (current session first, then recent others)
    """
    queue = _load_queue()
    if not queue:
        return []

    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=ttl_hours)

    # Get current session ID if active
    session = get_current_session()
    current_session_id = session.session_id if session else None

    # Partition: current session vs others
    current_session_entries = []
    other_entries = []

    for entry in queue:
        # Parse queued_at timestamp
        try:
            queued_at = datetime.fromisoformat(entry.queued_at)
        except ValueError:
            continue  # Skip malformed entries

        if entry.session_id == current_session_id:
            current_session_entries.append(entry)
        elif queued_at > cutoff:
            # Recent entry from another session - include as candidate
            other_entries.append(entry)
        # else: expired, will be garbage collected

    # Current session first, then recent others (most recent first)
    other_entries.sort(key=lambda e: e.queued_at, reverse=True)
    return current_session_entries + other_entries


def clear_queue_for_session(session_id: str) -> int:
    """Clear queue entries for a specific session.

    Args:
        session_id: Session to clear

    Returns:
        Number of entries removed
    """
    queue = _load_queue()
    original_len = len(queue)
    queue = [e for e in queue if e.session_id != session_id]
    _save_queue(queue)
    removed = original_len - len(queue)
    if removed > 0:
        logger.info(f"Cleared {removed} queue entries for session {session_id}")
    return removed


def clear_injected(checkpoint_ids: list[str]) -> int:
    """Clear specific checkpoints from the queue after injection.

    Args:
        checkpoint_ids: IDs to remove

    Returns:
        Number of entries removed
    """
    queue = _load_queue()
    original_len = len(queue)
    ids_set = set(checkpoint_ids)
    queue = [e for e in queue if e.checkpoint_id not in ids_set]
    _save_queue(queue)
    return original_len - len(queue)


def garbage_collect_queue(max_age_hours: float = 24.0) -> int:
    """Remove expired entries from the queue.

    Called periodically to prevent unbounded queue growth.
    Default TTL for injection is 4 hours, but we keep entries for 24 hours
    before garbage collection (in case user wants to manually recover).

    Args:
        max_age_hours: Maximum age before removal (default 24 hours)

    Returns:
        Number of entries removed
    """
    queue = _load_queue()
    if not queue:
        return 0

    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=max_age_hours)
    original_len = len(queue)

    kept = []
    for entry in queue:
        try:
            queued_at = datetime.fromisoformat(entry.queued_at)
            if queued_at > cutoff:
                kept.append(entry)
        except ValueError:
            pass  # Drop malformed entries

    if len(kept) < original_len:
        _save_queue(kept)
        removed = original_len - len(kept)
        logger.info(f"Garbage collected {removed} expired queue entries")
        return removed

    return 0


def _load_queue() -> list[QueueEntry]:
    """Load the injection queue from disk."""
    if not INJECTION_QUEUE_FILE.exists():
        return []

    try:
        content = INJECTION_QUEUE_FILE.read_text().strip()
        if not content:
            # Empty file - likely from interrupted write, clean it up
            logger.warning("Injection queue file empty, removing corrupted file")
            INJECTION_QUEUE_FILE.unlink(missing_ok=True)
            return []
        data = json.loads(content)
        if not isinstance(data, list):
            logger.warning("Injection queue not a list, resetting")
            INJECTION_QUEUE_FILE.unlink(missing_ok=True)
            return []
        return [QueueEntry.from_dict(e) for e in data if isinstance(e, dict)]
    except json.JSONDecodeError as e:
        logger.warning(f"Corrupted injection queue JSON, resetting: {e}")
        INJECTION_QUEUE_FILE.unlink(missing_ok=True)
        return []
    except (KeyError, OSError) as e:
        logger.warning(f"Failed to load injection queue: {e}")
        return []


def _save_queue(queue: list[QueueEntry]) -> None:
    """Save the injection queue to disk atomically."""
    from sage.atomic import atomic_write_json

    try:
        SAGE_DIR.mkdir(parents=True, exist_ok=True)
        data = [e.to_dict() for e in queue]
        result = atomic_write_json(INJECTION_QUEUE_FILE, data, mode=0o600, indent=2)
        if result.is_err():
            logger.warning(f"Failed to save injection queue: {result.unwrap_err().message}")
    except Exception as e:
        logger.warning(f"Failed to save injection queue: {e}")
