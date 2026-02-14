"""Session continuity via compaction detection.

Provides marker-based continuity across Claude Code compaction events.
When compaction is detected (via watcher), a marker is written pointing
to the most recent checkpoint. On the next sage tool call, context is
injected automatically.

Flow:
1. 70% context hook saves checkpoint (existing)
2. Compaction watcher detects isCompactSummary in JSONL
3. Watcher calls mark_for_continuity()
4. Next sage tool call: _maybe_inject_continuity() injects and clears

Security:
- Marker file has restricted permissions (0o600)
- Paths are validated before use
- JSON parsing uses safe_load equivalent (json.loads)
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from sage.config import SAGE_DIR, detect_project_root
from sage.errors import Result, SageError, err, ok

logger = logging.getLogger(__name__)

# Global marker file location (fallback when no project)
CONTINUITY_FILE = SAGE_DIR / "continuity.json"


def _get_continuity_file(project_path: Path | None = None) -> Path:
    """Get the continuity marker file path, preferring project-local.

    Continuity markers are project-scoped so that:
    - Compacting in project A doesn't inject into project B
    - Project markers can be shared via git (though typically gitignored)

    Args:
        project_path: Optional project path to use

    Returns:
        Path to continuity.json (project-local if available, else global)
    """
    if project_path:
        project_sage = project_path / ".sage"
        if project_sage.exists():
            return project_sage / "continuity.json"

    # Auto-detect project
    detected = detect_project_root()
    if detected:
        project_sage = detected / ".sage"
        if project_sage.exists():
            return project_sage / "continuity.json"

    # Fall back to global
    return CONTINUITY_FILE


def _get_checkpoints_dir(project_path: Path | None = None) -> Path:
    """Get checkpoints directory, preferring project-local."""
    if project_path:
        local_dir = project_path / ".sage" / "checkpoints"
        if local_dir.exists():
            return local_dir
    return SAGE_DIR / "checkpoints"


def get_most_recent_checkpoint(project_path: Path | None = None) -> Path | None:
    """Find the most recently modified checkpoint file.

    Args:
        project_path: Optional project path to check first

    Returns:
        Path to most recent checkpoint, or None if none exist
    """
    # Try project-local first
    if project_path is None:
        project_path = detect_project_root()

    checkpoints_dir = _get_checkpoints_dir(project_path)

    if not checkpoints_dir.exists():
        # Fall back to global
        checkpoints_dir = SAGE_DIR / "checkpoints"
        if not checkpoints_dir.exists():
            return None

    checkpoints = list(checkpoints_dir.glob("*.md"))
    if not checkpoints:
        return None

    return max(checkpoints, key=lambda p: p.stat().st_mtime)


def mark_for_continuity(
    checkpoint_path: Path | None = None,
    reason: str = "post_compaction",
    compaction_summary: str | None = None,
    project_dir: Path | None = None,
) -> Result[Path, SageError]:
    """Mark for continuity injection on next sage tool call.

    Called by the compaction watcher when it detects isCompactSummary: true.
    Overwrites any existing marker - only most recent matters.

    Markers are project-scoped: stored in <project>/.sage/continuity.json
    when in a project, or ~/.sage/continuity.json globally.

    Args:
        checkpoint_path: Path to checkpoint file. If None, uses most recent.
        reason: Why this was marked (post_compaction, manual, etc.)
        compaction_summary: Claude Code's summary from isCompactSummary message
        project_dir: Optional project scope

    Returns:
        Path to the marker file on success

    Security:
        - Marker file created with 0o600 permissions
        - checkpoint_path validated if provided
    """
    from sage.atomic import atomic_write_json

    # Find checkpoint if not provided
    if checkpoint_path is None:
        checkpoint_path = get_most_recent_checkpoint(project_dir)

    # Extract checkpoint ID (filename stem) for portable lookup
    # ID-based lookup is safe - no path traversal concerns
    checkpoint_id: str | None = None
    if checkpoint_path is not None:
        checkpoint_path = Path(checkpoint_path).resolve()
        checkpoint_id = checkpoint_path.stem  # Just the filename without extension

    data = {
        "checkpoint_id": checkpoint_id,  # Store ID only - load_checkpoint handles resolution
        "compaction_summary": compaction_summary,
        "marked_at": datetime.now(UTC).isoformat(),
        "reason": reason,
        "project_dir": str(project_dir) if project_dir else None,
    }

    # Get project-scoped marker file
    marker_file = _get_continuity_file(project_dir)

    # Ensure parent directory exists
    marker_file.parent.mkdir(parents=True, exist_ok=True)

    # Atomic write via shared utility
    result = atomic_write_json(marker_file, data, mode=0o600)
    if result.is_ok():
        logger.info(f"Continuity marker written: {reason} -> {marker_file}")
        return ok(marker_file)
    else:
        error = result.unwrap_err()
        return err(SageError(code="CONTINUITY_WRITE_FAILED", message=error.message))


def get_continuity_marker(project_path: Path | None = None) -> dict | None:
    """Get pending continuity marker, if any.

    Args:
        project_path: Optional project path to scope marker lookup

    Returns:
        Marker data dict or None if no pending continuity.
        Returns None on parse errors (logs warning).
    """
    marker_file = _get_continuity_file(project_path)

    if not marker_file.exists():
        return None

    try:
        content = marker_file.read_text()
        data = json.loads(content)

        # Basic validation
        if not isinstance(data, dict):
            logger.warning("Continuity marker is not a dict, ignoring")
            return None

        return data

    except json.JSONDecodeError as e:
        logger.warning(f"Malformed continuity marker JSON: {e}")
        return None
    except OSError as e:
        logger.warning(f"Failed to read continuity marker: {e}")
        return None


def clear_continuity(project_path: Path | None = None) -> None:
    """Clear continuity marker after successful injection.

    Args:
        project_path: Optional project path to scope marker lookup

    Idempotent - safe to call if marker doesn't exist.
    """
    marker_file = _get_continuity_file(project_path)

    try:
        marker_file.unlink(missing_ok=True)
        logger.debug(f"Continuity marker cleared: {marker_file}")
    except OSError as e:
        logger.warning(f"Failed to clear continuity marker: {e}")


def has_pending_continuity(project_path: Path | None = None) -> bool:
    """Check if continuity marker exists without loading it.

    Args:
        project_path: Optional project path to scope marker lookup

    Returns:
        True if marker file exists
    """
    marker_file = _get_continuity_file(project_path)
    return marker_file.exists()
