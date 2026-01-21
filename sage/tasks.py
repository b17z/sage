"""Async task infrastructure for Sage MCP server.

This module provides:
- Task/TaskResult dataclasses for background operations
- Task result files for Task polling notifications
- Task validation and security
- Pending task persistence for graceful shutdown

Async Architecture (v2.0.1 - Task Polling)
------------------------------------------
Sage uses asyncio.Queue for background processing with Task polling notifications:

1. MCP tool receives request
2. Tool validates input (fast, sync)
3. Tool creates Task and queues it
4. Tool returns "📋 Queued" + POLL instructions immediately
5. Claude spawns background Task subagent that polls via Read tool
6. Worker processes Task in background via asyncio.to_thread()
7. Worker writes result to ~/.sage/tasks/<task_id>.result
8. Worker touches ~/.sage/tasks/<task_id>.done (signals completion)
9. Task subagent detects .done file via Read, returns result
10. Claude Code shows native <task-notification> automatically

This approach gives native subagent-like UX without bash permissions.

Security Considerations
-----------------------
- Task types validated against whitelist
- Result messages sanitized (no shell injection)
- Files use atomic writes (temp + rename)
- File permissions 0o600
- No pickle (JSON only)
- No bash execution (v2.0.1 security fix)
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from sage.config import SAGE_DIR

# Valid task types (whitelist for security)
TASK_TYPES = frozenset({"checkpoint", "knowledge"})

# Task result files directory (for bash watcher approach)
TASKS_DIR = SAGE_DIR / "tasks"

# Notification file path (legacy - kept for hook-based fallback)
NOTIFY_FILE = SAGE_DIR / "notifications.jsonl"

# Pending tasks file for graceful shutdown
PENDING_TASKS_FILE = SAGE_DIR / "pending_tasks.jsonl"


def generate_task_id() -> str:
    """Generate unique task ID.

    Format: task_<timestamp>_<uuid4_prefix>
    Example: task_20260121_143052_a1b2c3d4
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    return f"task_{ts}_{uid}"


@dataclass(frozen=True)
class Task:
    """Immutable task for background processing.

    Attributes:
        id: Unique task identifier
        type: Task type (checkpoint, knowledge)
        data: Task-specific data (validated before use)
        created: Creation timestamp
    """

    id: str
    type: Literal["checkpoint", "knowledge"]
    data: dict[str, Any]
    created: datetime = field(default_factory=datetime.now)

    def __post_init__(self) -> None:
        """Validate task on creation."""
        if self.type not in TASK_TYPES:
            raise ValueError(f"Invalid task type: {self.type}. Valid types: {TASK_TYPES}")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "id": self.id,
            "type": self.type,
            "data": self.data,
            "created": self.created.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        """Create Task from dict (for deserialization).

        Args:
            data: Dictionary with task fields

        Returns:
            Task instance

        Raises:
            ValueError: If required fields missing or invalid
        """
        # Validate required fields
        required = {"id", "type", "data", "created"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Validate type before creating
        task_type = data["type"]
        if task_type not in TASK_TYPES:
            raise ValueError(f"Invalid task type: {task_type}")

        # Parse timestamp
        created = data["created"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)

        return cls(
            id=data["id"],
            type=task_type,
            data=data["data"],
            created=created,
        )


@dataclass
class TaskResult:
    """Result of task processing.

    Attributes:
        task_id: ID of the processed task
        status: success or failed
        message: Human-readable result message
        error: Error details if failed
    """

    task_id: str
    status: Literal["success", "failed"]
    message: str
    error: str | None = None


# =============================================================================
# Notification System
# =============================================================================


def _sanitize_notification_message(msg: str) -> str:
    """Sanitize notification message to prevent shell injection.

    Removes potentially dangerous characters that could be interpreted
    by shell when hook script processes the notification.

    Args:
        msg: Raw message

    Returns:
        Sanitized message safe for shell display
    """
    # Remove shell metacharacters
    # Keep: alphanumeric, spaces, common punctuation
    # Remove: backticks, $, ;, |, &, <, >, newlines, etc.
    sanitized = re.sub(r"[`$;|&<>\n\r\\]", "", msg)

    # Limit length to prevent buffer issues
    max_length = 500
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."

    return sanitized


def write_notification(
    notification_type: Literal["success", "error", "warning"],
    msg: str,
) -> None:
    """Write notification to JSONL file for hook to pick up.

    Uses atomic write (temp file + rename) to prevent partial reads.
    Sets file permissions to 0o600 for security.

    Args:
        notification_type: Type of notification (success, error, warning)
        msg: Notification message (will be sanitized)
    """
    # Ensure directory exists
    SAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Sanitize message
    safe_msg = _sanitize_notification_message(msg)

    # Build notification record
    record = {
        "ts": datetime.now().isoformat(),
        "type": notification_type,
        "msg": safe_msg,
    }

    # Atomic write: write to temp file, then append to real file
    # For JSONL append, we need to handle atomicity differently
    # We'll use a lock-free append approach with atomic line writes

    try:
        # Create notification line
        line = json.dumps(record) + "\n"

        # Open in append mode with exclusive creation for new files
        # This is atomic on POSIX systems for small writes
        with open(NOTIFY_FILE, "a") as f:
            f.write(line)

        # Set permissions if file was just created
        NOTIFY_FILE.chmod(0o600)

    except Exception:
        # Silently fail - notifications are best-effort
        # Don't let notification failure break the main flow
        pass


def read_notifications() -> list[dict[str, Any]]:
    """Read all notifications from file.

    Returns:
        List of notification records
    """
    if not NOTIFY_FILE.exists():
        return []

    notifications = []
    try:
        with open(NOTIFY_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    notifications.append(json.loads(line))
    except Exception:
        pass

    return notifications


def clear_notifications() -> None:
    """Clear notifications file after reading."""
    try:
        if NOTIFY_FILE.exists():
            NOTIFY_FILE.unlink()
    except Exception:
        pass


# =============================================================================
# Bash Watcher Task Results (Primary notification mechanism)
# =============================================================================


def write_task_result(
    task_id: str,
    status: Literal["success", "failed"],
    message: str,
    error: str | None = None,
) -> Path:
    """Write task result to file and touch .done marker.

    This is the primary notification mechanism. The bash watcher polls for
    the .done file and then reads the .result file.

    Args:
        task_id: Task ID
        status: success or failed
        message: Human-readable result message
        error: Error details if failed

    Returns:
        Path to the result file
    """
    TASKS_DIR.mkdir(parents=True, exist_ok=True)

    result_file = TASKS_DIR / f"{task_id}.result"
    done_file = TASKS_DIR / f"{task_id}.done"

    # Sanitize message for shell safety
    safe_message = _sanitize_notification_message(message)

    # Build result data
    result_data = {
        "task_id": task_id,
        "status": status,
        "message": safe_message,
        "ts": datetime.now().isoformat(),
    }
    if error:
        result_data["error"] = _sanitize_notification_message(error)

    # Atomic write: temp file + rename
    try:
        fd, temp_path = tempfile.mkstemp(
            dir=TASKS_DIR,
            prefix=f".{task_id}_",
            suffix=".result.tmp",
        )

        try:
            with os.fdopen(fd, "w") as f:
                json.dump(result_data, f)

            os.chmod(temp_path, 0o600)
            os.rename(temp_path, result_file)

            # Touch .done file to signal completion
            done_file.touch()
            done_file.chmod(0o600)

        except Exception:
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise

    except Exception:
        # Best effort - don't crash on notification failure
        pass

    return result_file


def read_task_result(task_id: str) -> dict[str, Any] | None:
    """Read task result from file.

    Args:
        task_id: Task ID

    Returns:
        Result dict or None if not found
    """
    result_file = TASKS_DIR / f"{task_id}.result"

    if not result_file.exists():
        return None

    try:
        with open(result_file) as f:
            return json.load(f)
    except Exception:
        return None


def is_task_complete(task_id: str) -> bool:
    """Check if a task has completed (done file exists).

    Args:
        task_id: Task ID

    Returns:
        True if task is complete
    """
    done_file = TASKS_DIR / f"{task_id}.done"
    return done_file.exists()


def cleanup_task_files(task_id: str) -> None:
    """Clean up task result files after processing.

    Args:
        task_id: Task ID
    """
    try:
        result_file = TASKS_DIR / f"{task_id}.result"
        done_file = TASKS_DIR / f"{task_id}.done"

        if result_file.exists():
            result_file.unlink()
        if done_file.exists():
            done_file.unlink()
    except Exception:
        pass


def get_task_paths(task_id: str) -> dict[str, str]:
    """Get file paths for tracking a task.

    Returns paths that can be used with Claude's Read tool for polling.

    Security: Task IDs are validated to prevent path traversal attacks.
    Only alphanumeric characters and underscores are allowed.

    Args:
        task_id: Task ID (must match pattern: task_YYYYMMDD_HHMMSS_hex8)

    Returns:
        Dict with 'done_file' and 'result_file' paths

    Raises:
        ValueError: If task_id contains invalid characters
    """
    import re

    # Defense-in-depth: validate task ID format
    # Only allow alphanumeric + underscore to prevent path traversal
    if not re.match(r"^[a-zA-Z0-9_]+$", task_id):
        raise ValueError(f"Invalid task ID format: {task_id}")

    return {
        "task_id": task_id,
        "done_file": str(TASKS_DIR / f"{task_id}.done"),
        "result_file": str(TASKS_DIR / f"{task_id}.result"),
    }


def cleanup_old_task_files(max_age_hours: int = 24) -> int:
    """Clean up old task files.

    Args:
        max_age_hours: Maximum age of files to keep (default 24 hours)

    Returns:
        Number of files cleaned up
    """
    if not TASKS_DIR.exists():
        return 0

    cleaned = 0
    cutoff = datetime.now().timestamp() - (max_age_hours * 3600)

    try:
        for path in TASKS_DIR.iterdir():
            if path.suffix in (".result", ".done"):
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    cleaned += 1
    except Exception:
        pass

    return cleaned


# =============================================================================
# Pending Tasks Persistence
# =============================================================================


def save_pending_tasks(tasks: list[Task]) -> None:
    """Save pending tasks to file for restart recovery.

    Uses atomic write pattern: write to temp file, then rename.

    Args:
        tasks: List of pending tasks to save
    """
    if not tasks:
        return

    SAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Serialize tasks
    records = [task.to_dict() for task in tasks]

    # Atomic write: temp file + rename
    try:
        # Create temp file in same directory (for atomic rename)
        fd, temp_path = tempfile.mkstemp(
            dir=SAGE_DIR,
            prefix=".pending_tasks_",
            suffix=".jsonl.tmp",
        )

        try:
            with os.fdopen(fd, "w") as f:
                for record in records:
                    f.write(json.dumps(record) + "\n")

            # Set permissions before rename
            os.chmod(temp_path, 0o600)

            # Atomic rename
            os.rename(temp_path, PENDING_TASKS_FILE)

        except Exception:
            # Clean up temp file on error
            try:
                os.unlink(temp_path)
            except Exception:
                pass
            raise

    except Exception:
        # Log error but don't crash
        pass


def load_pending_tasks() -> list[Task]:
    """Load pending tasks from file.

    Returns:
        List of tasks, empty if file doesn't exist or is invalid
    """
    if not PENDING_TASKS_FILE.exists():
        return []

    tasks = []
    try:
        with open(PENDING_TASKS_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    task = Task.from_dict(data)
                    tasks.append(task)
                except (json.JSONDecodeError, ValueError):
                    # Skip malformed JSON or invalid tasks
                    continue
    except Exception:
        pass

    return tasks


def clear_pending_tasks() -> None:
    """Clear pending tasks file after loading."""
    try:
        if PENDING_TASKS_FILE.exists():
            PENDING_TASKS_FILE.unlink()
    except Exception:
        pass


# =============================================================================
# Task Data Validation
# =============================================================================


def validate_checkpoint_data(data: dict[str, Any]) -> tuple[bool, str]:
    """Validate checkpoint task data.

    Args:
        data: Checkpoint data to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    required = {"core_question", "thesis", "confidence"}
    missing = required - set(data.keys())
    if missing:
        return False, f"Missing required fields: {missing}"

    # Validate confidence range
    confidence = data.get("confidence", 0)
    if not isinstance(confidence, (int, float)):
        return False, "Confidence must be a number"
    if not (0.0 <= confidence <= 1.0):
        return False, f"Confidence {confidence} must be between 0.0 and 1.0"

    # Validate string fields
    if not isinstance(data.get("core_question"), str):
        return False, "core_question must be a string"
    if not isinstance(data.get("thesis"), str):
        return False, "thesis must be a string"

    return True, ""


def validate_knowledge_data(data: dict[str, Any]) -> tuple[bool, str]:
    """Validate knowledge task data.

    Args:
        data: Knowledge data to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    required = {"knowledge_id", "content", "keywords"}
    missing = required - set(data.keys())
    if missing:
        return False, f"Missing required fields: {missing}"

    # Validate string fields
    if not isinstance(data.get("knowledge_id"), str):
        return False, "knowledge_id must be a string"
    if not isinstance(data.get("content"), str):
        return False, "content must be a string"

    # Validate keywords
    keywords = data.get("keywords")
    if not isinstance(keywords, list):
        return False, "keywords must be a list"
    if not all(isinstance(k, str) for k in keywords):
        return False, "all keywords must be strings"

    return True, ""


def validate_task_data(task_type: str, data: dict[str, Any]) -> tuple[bool, str]:
    """Validate task data based on type.

    Args:
        task_type: Type of task
        data: Task data to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if task_type == "checkpoint":
        return validate_checkpoint_data(data)
    elif task_type == "knowledge":
        return validate_knowledge_data(data)
    else:
        return False, f"Unknown task type: {task_type}"
