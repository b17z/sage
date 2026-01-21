"""Structured logging for Sage.

Security-conscious logging that:
- NEVER logs sensitive data (API keys, tokens, secrets)
- NEVER logs content (checkpoint thesis, knowledge content, user queries)
- Sanitizes paths (replaces $HOME with ~)
- Uses restrictive file permissions (0o600)
- Supports log rotation to prevent disk exhaustion

Usage:
    from sage.logging import get_logger, log_event

    logger = get_logger(__name__)
    logger.info("Operation started", task_id="task_123", operation="checkpoint")

    # Or use structured events
    log_event("task_completed", task_id="task_123", duration_ms=150)
"""

from __future__ import annotations

import json
import logging
import os
import re
import stat
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from sage.config import SAGE_DIR

# Log directory
LOGS_DIR = SAGE_DIR / "logs"
LOG_FILE = LOGS_DIR / "sage.log"

# Rotation settings
MAX_LOG_SIZE = 5 * 1024 * 1024  # 5MB
BACKUP_COUNT = 3  # Keep 3 rotated files

# Patterns for sensitive data detection
SENSITIVE_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{20,}", re.IGNORECASE),  # API keys
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]

# Fields that should never be logged (content fields)
REDACTED_FIELDS = frozenset(
    {
        "thesis",
        "content",
        "query",
        "message",  # Could contain user content
        "reasoning_trace",
        "key_evidence",
        "sources",
        "tensions",
        "unique_contributions",
        "open_questions",
        "api_key",
        "token",
        "secret",
        "password",
    }
)


def _sanitize_path(path: str | Path) -> str:
    """Replace home directory with ~ for privacy."""
    path_str = str(path)
    home = os.path.expanduser("~")
    if path_str.startswith(home):
        return "~" + path_str[len(home) :]
    return path_str


def _contains_sensitive_data(value: str) -> bool:
    """Check if a string might contain sensitive data."""
    if not isinstance(value, str):
        return False
    for pattern in SENSITIVE_PATTERNS:
        if pattern.search(value):
            return True
    return False


def _sanitize_value(key: str, value: Any) -> Any:
    """Sanitize a value for logging.

    - Redacts known sensitive fields
    - Detects and redacts potential secrets
    - Sanitizes file paths
    - Truncates long strings
    """
    key_lower = key.lower()

    # Redact known sensitive fields
    if key_lower in REDACTED_FIELDS:
        if isinstance(value, str):
            return f"[REDACTED:{len(value)} chars]"
        elif isinstance(value, (list, dict)):
            return f"[REDACTED:{type(value).__name__}]"
        return "[REDACTED]"

    # Handle strings
    if isinstance(value, str):
        # Check for sensitive patterns
        if _contains_sensitive_data(value):
            return "[REDACTED:sensitive]"

        # Sanitize paths
        if "/" in value or "\\" in value:
            value = _sanitize_path(value)

        # Truncate long strings (but not paths)
        if len(value) > 200 and "~" not in value:
            return value[:200] + f"...[truncated:{len(value)} chars]"

    # Handle paths
    elif isinstance(value, Path):
        return _sanitize_path(value)

    # Handle nested dicts
    elif isinstance(value, dict):
        return {k: _sanitize_value(k, v) for k, v in value.items()}

    # Handle lists
    elif isinstance(value, (list, tuple)):
        if len(value) > 10:
            return f"[list:{len(value)} items]"
        return [_sanitize_value(str(i), v) for i, v in enumerate(value)]

    return value


class SecureJSONFormatter(logging.Formatter):
    """JSON formatter that sanitizes sensitive data."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON with sanitization."""
        # Base log entry
        entry = {
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields (sanitized)
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                # Skip standard LogRecord attributes
                if key in {
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "stack_info",
                    "exc_info",
                    "exc_text",
                    "thread",
                    "threadName",
                    "message",
                    "asctime",
                }:
                    continue
                entry[key] = _sanitize_value(key, value)

        # Add exception info if present
        if record.exc_info:
            entry["error"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
            }

        return json.dumps(entry, default=str)


def _ensure_log_dir() -> None:
    """Create log directory with secure permissions."""
    if not LOGS_DIR.exists():
        LOGS_DIR.mkdir(parents=True, mode=0o700)

    # Ensure directory has correct permissions
    current_mode = LOGS_DIR.stat().st_mode
    if current_mode & 0o077:  # If group/other have any permissions
        LOGS_DIR.chmod(0o700)


def _secure_file_handler() -> RotatingFileHandler:
    """Create a rotating file handler with secure permissions."""
    _ensure_log_dir()

    handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(SecureJSONFormatter())

    # Set secure permissions on log file if it exists
    if LOG_FILE.exists():
        LOG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600

    return handler


# Global handler (lazy initialized)
_file_handler: RotatingFileHandler | None = None
_initialized: bool = False


def _get_handler() -> RotatingFileHandler:
    """Get or create the file handler."""
    global _file_handler
    if _file_handler is None:
        _file_handler = _secure_file_handler()
    return _file_handler


def get_logger(name: str) -> logging.Logger:
    """Get a logger configured for Sage.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    global _initialized

    logger = logging.getLogger(name)

    # Only add handler once per logger
    if not _initialized or not logger.handlers:
        logger.addHandler(_get_handler())
        logger.setLevel(logging.DEBUG)
        _initialized = True

    return logger


def log_event(
    event: str,
    level: str = "INFO",
    **kwargs: Any,
) -> None:
    """Log a structured event.

    Args:
        event: Event name (e.g., "task_queued", "checkpoint_saved")
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        **kwargs: Additional fields to log (will be sanitized)

    Example:
        log_event("task_completed", task_id="task_123", duration_ms=150)
    """
    logger = get_logger("sage.events")
    log_func = getattr(logger, level.lower(), logger.info)

    # Create a LogRecord with extra fields
    extra = {k: v for k, v in kwargs.items()}
    extra["event"] = event

    log_func(event, extra=extra)


# Convenience functions for common events
def log_task_queued(task_id: str, task_type: str) -> None:
    """Log task queued event."""
    log_event("task_queued", task_id=task_id, task_type=task_type)


def log_task_started(task_id: str, task_type: str) -> None:
    """Log task started event."""
    log_event("task_started", task_id=task_id, task_type=task_type)


def log_task_completed(task_id: str, task_type: str, duration_ms: int) -> None:
    """Log task completed event."""
    log_event("task_completed", task_id=task_id, task_type=task_type, duration_ms=duration_ms)


def log_task_failed(task_id: str, task_type: str, error: str) -> None:
    """Log task failed event."""
    # Truncate error to avoid logging sensitive stack traces
    safe_error = error[:200] if len(error) > 200 else error
    log_event("task_failed", level="ERROR", task_id=task_id, task_type=task_type, error=safe_error)


def log_checkpoint_saved(checkpoint_id: str, trigger: str) -> None:
    """Log checkpoint saved event."""
    log_event("checkpoint_saved", checkpoint_id=checkpoint_id, trigger=trigger)


def log_knowledge_saved(knowledge_id: str, item_type: str) -> None:
    """Log knowledge saved event."""
    log_event("knowledge_saved", knowledge_id=knowledge_id, item_type=item_type)


def log_config_loaded(project_path: str | None) -> None:
    """Log config loaded event."""
    log_event("config_loaded", project_path=_sanitize_path(project_path) if project_path else None)
