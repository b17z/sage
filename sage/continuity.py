"""Session continuity via compaction detection.

Provides marker-based continuity across Claude Code compaction events.
When compaction is detected (via watcher), a marker is written pointing
to the most recent checkpoint. On the next sage tool call, context is
injected automatically.

Flow:
1. 70% context hook saves checkpoint (existing)
2. Compaction watcher detects isCompactSummary in JSONL
3. Watcher calls mark_for_continuity() with a ContinuityBundle
4. Next sage tool call: bundle context is injected and marker cleared

Bundle Architecture (v4.0):
- ContinuityBundle captures BOTH recovery + substantive checkpoints
- Also includes related knowledge and failures matched semantically
- Injected atomically on session resume for full context restoration

Security:
- Marker file has restricted permissions (0o600)
- Paths are validated before use
- JSON parsing uses safe_load equivalent (json.loads)
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sage.config import SAGE_DIR, detect_project_root
from sage.errors import Result, SageError, err, ok

logger = logging.getLogger(__name__)

# Global marker file location (fallback when no project)
CONTINUITY_FILE = SAGE_DIR / "continuity.json"


@dataclass(frozen=True)
class ContinuityBundle:
    """Context bundle for session continuity.

    Captures BOTH recovery checkpoint AND most recent substantive checkpoint,
    plus related context. This handles the case where user saves a checkpoint
    at 50% context, continues working, then auto-compact happens at 5%.

    All IDs, not full objects - loaded at injection time.

    Attributes:
        recovery_checkpoint_id: Thin checkpoint from compaction time
        substantive_checkpoint_id: Most recent checkpoint with confidence > 0
        knowledge_ids: Semantically matched knowledge item IDs
        failure_ids: Relevant past failure IDs
        created_at: ISO timestamp when bundle was created
        extraction_method: How knowledge/failures were matched (semantic/keyword)
    """

    # Primary: recovery checkpoint (what was happening at compact time)
    recovery_checkpoint_id: str | None = None

    # Secondary: most recent substantive checkpoint (confidence > 0)
    # This captures the richer context from earlier in the session
    substantive_checkpoint_id: str | None = None

    # Related context (IDs only - loaded at injection)
    knowledge_ids: tuple[str, ...] = ()  # Semantically matched knowledge
    failure_ids: tuple[str, ...] = ()  # Relevant past failures

    # Metadata
    created_at: str = ""  # ISO timestamp
    extraction_method: str = "semantic"  # "semantic" | "keyword" | "explicit"

    def to_dict(self) -> dict:
        """Convert bundle to dictionary for JSON serialization."""
        return {
            "recovery_checkpoint_id": self.recovery_checkpoint_id,
            "substantive_checkpoint_id": self.substantive_checkpoint_id,
            "knowledge_ids": list(self.knowledge_ids),
            "failure_ids": list(self.failure_ids),
            "created_at": self.created_at,
            "extraction_method": self.extraction_method,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ContinuityBundle":
        """Create bundle from dictionary (from JSON)."""
        return cls(
            recovery_checkpoint_id=data.get("recovery_checkpoint_id"),
            substantive_checkpoint_id=data.get("substantive_checkpoint_id"),
            knowledge_ids=tuple(data.get("knowledge_ids", [])),
            failure_ids=tuple(data.get("failure_ids", [])),
            created_at=data.get("created_at", ""),
            extraction_method=data.get("extraction_method", "semantic"),
        )


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


# =============================================================================
# Bundle Architecture (v4.0)
# =============================================================================


def _find_most_recent_substantive_checkpoint(
    project_path: Path | None = None,
    exclude_id: str | None = None,
) -> str | None:
    """Find most recent checkpoint with confidence > 0.

    Skips recovery checkpoints (type=recovery) and 0% confidence ones.
    This captures the richer context from earlier in the session.

    Args:
        project_path: Optional project path
        exclude_id: Optional checkpoint ID to skip (e.g., the recovery checkpoint)

    Returns:
        Checkpoint ID or None if not found
    """
    from sage.checkpoint import list_checkpoints

    checkpoints = list_checkpoints(project_path, limit=10)

    for cp in checkpoints:
        # Skip the checkpoint we're excluding (usually recovery)
        if exclude_id and cp.id == exclude_id:
            continue

        # Skip recovery checkpoints (identified by "_recovery-" in ID)
        if "_recovery-" in cp.id:
            continue

        # Skip 0% confidence
        if cp.confidence > 0:
            return cp.id

    return None


def _build_query_from_checkpoint_id(checkpoint_id: str, project_path: Path | None) -> str:
    """Build semantic query from a checkpoint's content.

    Extracts thesis, core_question, and open_questions for semantic matching.

    Args:
        checkpoint_id: Checkpoint ID to load
        project_path: Project path for checkpoint lookup

    Returns:
        Query string for semantic matching (up to 500 chars)
    """
    from sage.checkpoint import load_checkpoint
    from sage.recovery import load_recovery_checkpoint

    parts = []

    # Try loading as structured checkpoint first
    checkpoint = load_checkpoint(checkpoint_id, project_path)
    if checkpoint:
        if checkpoint.thesis:
            parts.append(checkpoint.thesis)
        if checkpoint.core_question:
            parts.append(checkpoint.core_question)
        if checkpoint.open_questions:
            parts.extend(checkpoint.open_questions[:3])
    else:
        # Try loading as recovery checkpoint
        recovery = load_recovery_checkpoint(checkpoint_id, project_path)
        if recovery:
            if recovery.topic:
                parts.append(recovery.topic)
            if recovery.thesis:
                parts.append(recovery.thesis)
            if recovery.open_threads:
                parts.extend(list(recovery.open_threads[:3]))

    return " ".join(parts)[:500]


def _find_related_knowledge(query: str, limit: int = 5, project_path: Path | None = None) -> list[str]:
    """Find knowledge items semantically related to query.

    Args:
        query: Search query
        limit: Maximum items to return
        project_path: Project path for knowledge lookup

    Returns:
        List of knowledge item IDs
    """
    if not query:
        return []

    try:
        from sage.knowledge import recall_knowledge

        # Use lower threshold for broader matching during continuity
        result = recall_knowledge(query, skill_name="", threshold=0.35, max_items=limit)
        return [item.id for item in result.items]
    except Exception as e:
        logger.debug(f"Knowledge recall failed: {e}")
        return []


def _find_relevant_failures(query: str, limit: int = 3, project_path: Path | None = None) -> list[str]:
    """Find failures semantically related to query.

    Args:
        query: Search query
        limit: Maximum items to return
        project_path: Project path for failure lookup

    Returns:
        List of failure IDs
    """
    if not query:
        return []

    try:
        from sage.failures import recall_failures

        failures = recall_failures(query, limit=limit, project_path=project_path)
        return [f.id for f in failures]
    except ImportError:
        # Failures module not available
        return []
    except Exception as e:
        logger.debug(f"Failure recall failed: {e}")
        return []


def create_continuity_bundle(
    recovery_checkpoint_id: str | None = None,
    project_path: Path | None = None,
) -> ContinuityBundle:
    """Create bundle with BOTH recovery + substantive checkpoints.

    Finds the most recent substantive checkpoint (confidence > 0) to pair with
    the recovery checkpoint. This captures the full context arc of the session.

    Also matches related knowledge and failures semantically against both
    checkpoints' content.

    Args:
        recovery_checkpoint_id: ID of the recovery checkpoint (from compaction)
        project_path: Project path for lookups

    Returns:
        ContinuityBundle with all related context
    """
    # Find most recent substantive checkpoint (confidence > 0)
    substantive_id = _find_most_recent_substantive_checkpoint(
        project_path, exclude_id=recovery_checkpoint_id
    )

    # Build query from BOTH checkpoints for semantic matching
    query_parts = []

    if recovery_checkpoint_id:
        recovery_query = _build_query_from_checkpoint_id(recovery_checkpoint_id, project_path)
        if recovery_query:
            query_parts.append(recovery_query)

    if substantive_id:
        substantive_query = _build_query_from_checkpoint_id(substantive_id, project_path)
        if substantive_query:
            query_parts.append(substantive_query)

    query = " ".join(query_parts)[:500]

    # Find related knowledge (semantic match against both checkpoints)
    knowledge_ids = _find_related_knowledge(query, limit=5, project_path=project_path)

    # Find relevant failures (semantic match)
    failure_ids = _find_relevant_failures(query, limit=3, project_path=project_path)

    return ContinuityBundle(
        recovery_checkpoint_id=recovery_checkpoint_id,
        substantive_checkpoint_id=substantive_id,
        knowledge_ids=tuple(knowledge_ids),
        failure_ids=tuple(failure_ids),
        created_at=datetime.now(UTC).isoformat(),
        extraction_method="semantic" if query else "none",
    )


def mark_for_continuity_with_bundle(
    bundle: ContinuityBundle,
    reason: str = "post_compaction",
    compaction_summary: str | None = None,
    project_dir: Path | None = None,
) -> Result[Path, SageError]:
    """Mark for continuity injection with a full bundle.

    This is the v4.0 bundle-aware version of mark_for_continuity.
    Stores the full bundle in the marker for atomic injection.

    Args:
        bundle: ContinuityBundle with checkpoints and related context
        reason: Why this was marked (post_compaction, manual, etc.)
        compaction_summary: Claude Code's summary from isCompactSummary message
        project_dir: Optional project scope

    Returns:
        Path to the marker file on success

    Security:
        - Marker file created with 0o600 permissions
    """
    from sage.atomic import atomic_write_json

    data = {
        "bundle": bundle.to_dict(),
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
        logger.info(f"Continuity bundle written: {reason} -> {marker_file}")
        return ok(marker_file)
    else:
        error = result.unwrap_err()
        return err(SageError(code="CONTINUITY_WRITE_FAILED", message=error.message))


def get_continuity_bundle(project_path: Path | None = None) -> ContinuityBundle | None:
    """Get bundle from marker, with backward compatibility.

    Supports both new bundle format and legacy checkpoint_id-only format.

    Args:
        project_path: Optional project path to scope marker lookup

    Returns:
        ContinuityBundle or None if no pending continuity
    """
    marker = get_continuity_marker(project_path)
    if not marker:
        return None

    # New format: bundle field
    if "bundle" in marker:
        return ContinuityBundle.from_dict(marker["bundle"])

    # Legacy format: checkpoint_id only (backward compatibility)
    if marker.get("checkpoint_id"):
        return ContinuityBundle(
            recovery_checkpoint_id=marker["checkpoint_id"],
            substantive_checkpoint_id=None,
            knowledge_ids=(),
            failure_ids=(),
            created_at=marker.get("marked_at", ""),
            extraction_method="legacy",
        )

    return None
