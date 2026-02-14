"""Atomic file write utilities for Sage.

Provides atomic write operations that prevent data corruption on crash.
Uses the temp file + rename pattern which is atomic on POSIX systems.

All functions return Result types for explicit error handling.

Security:
- Files are created with 0o600 permissions by default
- Parent directories are created with 0o700 permissions
- Temp files are cleaned up on failure
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from sage.errors import Err, Ok, Result, SageError

logger = logging.getLogger(__name__)


def atomic_write_text(
    path: Path,
    content: str,
    mode: int = 0o600,
) -> Result[Path, SageError]:
    """Atomically write text content to a file.

    Uses temp file + rename pattern for crash safety.
    Creates parent directories if they don't exist.

    Args:
        path: Target file path (must be absolute or resolvable)
        content: Text content to write
        mode: File permissions (default 0o600 - owner read/write only)

    Returns:
        Ok(path) on success, Err(SageError) on failure

    Example:
        result = atomic_write_text(Path("/path/to/file.txt"), "content")
        if result.is_ok():
            print(f"Written to {result.unwrap()}")
    """
    path = Path(path)
    temp_path: str | None = None

    try:
        # Ensure parent directory exists with restricted permissions
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        # Create temp file in same directory (required for atomic rename)
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.stem}_",
            suffix=f"{path.suffix}.tmp",
        )

        try:
            # Write content via file descriptor
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)

            # Set permissions BEFORE rename (security)
            os.chmod(temp_path, mode)

            # Atomic rename
            os.rename(temp_path, path)

            logger.debug(f"Atomic write complete: {path}")
            return Ok(path)

        except Exception as e:
            # Clean up temp file on inner failure
            _cleanup_temp(temp_path)
            raise e

    except PermissionError as e:
        logger.error(f"Permission denied writing {path}: {e}")
        return Err(
            SageError(
                code="ATOMIC_PERMISSION_DENIED",
                message=f"Permission denied writing to {path}",
                context={"path": str(path)},
            )
        )

    except OSError as e:
        logger.error(f"OS error writing {path}: {e}")
        return Err(
            SageError(
                code="ATOMIC_WRITE_FAILED",
                message=f"Failed to write {path}: {e}",
                context={"path": str(path), "error": str(e)},
            )
        )

    except Exception as e:
        logger.error(f"Unexpected error writing {path}: {e}")
        _cleanup_temp(temp_path)
        return Err(
            SageError(
                code="ATOMIC_UNEXPECTED_ERROR",
                message=f"Unexpected error writing {path}: {e}",
                context={"path": str(path), "error": str(e)},
            )
        )


def atomic_write_json(
    path: Path,
    data: Any,
    mode: int = 0o600,
    indent: int | None = 2,
    ensure_ascii: bool = False,
) -> Result[Path, SageError]:
    """Atomically write JSON data to a file.

    Args:
        path: Target file path
        data: Data to serialize as JSON
        mode: File permissions (default 0o600)
        indent: JSON indentation (default 2, None for compact)
        ensure_ascii: Escape non-ASCII characters (default False)

    Returns:
        Ok(path) on success, Err(SageError) on failure

    Example:
        result = atomic_write_json(Path("config.json"), {"key": "value"})
    """
    try:
        content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    except (TypeError, ValueError) as e:
        logger.error(f"JSON serialization failed: {e}")
        return Err(
            SageError(
                code="JSON_SERIALIZATION_FAILED",
                message=f"Failed to serialize data to JSON: {e}",
                context={"error": str(e)},
            )
        )

    return atomic_write_text(path, content, mode)


def atomic_write_yaml(
    path: Path,
    data: Any,
    mode: int = 0o600,
    default_flow_style: bool = False,
    sort_keys: bool = False,
    allow_unicode: bool = True,
) -> Result[Path, SageError]:
    """Atomically write YAML data to a file.

    Uses yaml.safe_dump for security (no arbitrary Python objects).

    Args:
        path: Target file path
        data: Data to serialize as YAML
        mode: File permissions (default 0o600)
        default_flow_style: Use flow style (default False)
        sort_keys: Sort dictionary keys (default False)
        allow_unicode: Allow unicode characters (default True)

    Returns:
        Ok(path) on success, Err(SageError) on failure

    Example:
        result = atomic_write_yaml(Path("config.yaml"), {"key": "value"})
    """
    try:
        content = yaml.safe_dump(
            data,
            default_flow_style=default_flow_style,
            sort_keys=sort_keys,
            allow_unicode=allow_unicode,
        )
    except yaml.YAMLError as e:
        logger.error(f"YAML serialization failed: {e}")
        return Err(
            SageError(
                code="YAML_SERIALIZATION_FAILED",
                message=f"Failed to serialize data to YAML: {e}",
                context={"error": str(e)},
            )
        )

    return atomic_write_text(path, content, mode)


def atomic_write_jsonl(
    path: Path,
    records: list[dict[str, Any]],
    mode: int = 0o600,
) -> Result[Path, SageError]:
    """Atomically write JSONL (JSON Lines) data to a file.

    Each record is written as a single line of JSON.

    Args:
        path: Target file path
        records: List of records to serialize as JSONL
        mode: File permissions (default 0o600)

    Returns:
        Ok(path) on success, Err(SageError) on failure

    Example:
        result = atomic_write_jsonl(Path("data.jsonl"), [{"a": 1}, {"b": 2}])
    """
    try:
        lines = [json.dumps(record) for record in records]
        content = "\n".join(lines) + "\n" if lines else ""
    except (TypeError, ValueError) as e:
        logger.error(f"JSONL serialization failed: {e}")
        return Err(
            SageError(
                code="JSONL_SERIALIZATION_FAILED",
                message=f"Failed to serialize records to JSONL: {e}",
                context={"error": str(e)},
            )
        )

    return atomic_write_text(path, content, mode)


def _cleanup_temp(temp_path: str | None) -> None:
    """Clean up temporary file, ignoring errors.

    Args:
        temp_path: Path to temp file, or None if no cleanup needed
    """
    if temp_path is None:
        return

    try:
        os.unlink(temp_path)
        logger.debug(f"Cleaned up temp file: {temp_path}")
    except OSError:
        # Best effort cleanup - temp file may already be gone
        pass
