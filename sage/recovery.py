"""Recovery checkpoint module for Sage.

Creates recovery checkpoints from transcript content without Claude's cooperation.
These are auto-extracted safety-net checkpoints that preserve context when
structured checkpoints aren't available.

Two-tier checkpoint system:
1. Structured (existing) - Claude-generated, full schema, highest quality
2. Recovery (new) - Auto-extracted from transcript, safety net

Architecture:
- Uses transcript.py for JSONL parsing
- Uses salience.py for content detection
- Uses headless.py for optional Claude extraction
- Stores in same checkpoints/ directory with type=recovery
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml

from sage.config import SAGE_DIR
from sage.salience import (
    extract_decisions,
    extract_open_threads,
    extract_resolutions,
    extract_salient_content,
    get_max_salience,
)
from sage.transcript import (
    TranscriptWindow,
    get_assistant_content,
    get_files_touched,
    get_tools_used,
    get_user_content,
)

logger = logging.getLogger(__name__)

# Global checkpoints directory
CHECKPOINTS_DIR = SAGE_DIR / "checkpoints"


@dataclass(frozen=True)
class RecoveryCheckpoint:
    """A recovery checkpoint auto-extracted from transcript.

    Unlike structured checkpoints, these are generated without Claude's
    explicit cooperation. They serve as a safety net for context preservation.

    Attributes:
        id: Unique identifier (format: timestamp_recovery-topic)
        type: Always "recovery"
        trigger: What triggered this checkpoint
        extracted_at: When this was extracted
        extraction_method: "local" or "claude"
        topic: Main topic being discussed
        decisions: List of decisions made
        open_threads: List of unfinished work items
        resolutions: List of problems solved
        files_touched: Files mentioned in tool calls
        tools_used: Tool names used in conversation
        summary: Optional summary (from Claude extraction)
        salience_score: Maximum salience score detected
    """

    id: str
    type: Literal["recovery"] = "recovery"
    trigger: str = "pre_compact"
    extracted_at: str = ""
    extraction_method: str = "local"

    # Extracted content
    topic: str = ""
    decisions: tuple[str, ...] = ()
    open_threads: tuple[str, ...] = ()
    resolutions: tuple[str, ...] = ()

    # Context
    files_touched: tuple[str, ...] = ()
    tools_used: tuple[str, ...] = ()

    # Optional: from headless Claude
    summary: str | None = None

    # Metadata
    salience_score: float = 0.0


def generate_recovery_id(topic: str = "") -> str:
    """Generate a recovery checkpoint ID.

    Args:
        topic: Topic to include in ID (will be slugified)

    Returns:
        ID in format: timestamp_recovery-topic
    """
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")

    # Slugify topic
    if topic:
        slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:40]
    else:
        slug = "unknown"

    return f"{ts}_recovery-{slug}"


def extract_topic(assistant_content: str, user_content: str) -> str:
    """Extract the main topic from conversation content.

    Uses heuristics to find what's being discussed:
    - First significant sentence from user
    - Recurring nouns/phrases
    - File paths mentioned

    Args:
        assistant_content: All assistant messages
        user_content: All user messages

    Returns:
        Topic string (best effort)
    """
    # Take the first user message as primary context
    first_user = user_content.split("\n\n")[0] if user_content else ""

    if first_user:
        # Extract first sentence
        sentences = re.split(r"[.!?]", first_user)
        if sentences:
            topic = sentences[0].strip()[:100]
            if topic:
                return topic

    # Fallback: look for common programming terms
    all_content = f"{assistant_content} {user_content}"

    # Look for file mentions
    file_pattern = r"\b(\w+\.(py|js|ts|go|rs|sol|md))\b"
    files = re.findall(file_pattern, all_content)
    if files:
        return f"Working on {files[0][0]}"

    # Look for function/class names
    func_pattern = r"\b(def|function|class|fn)\s+(\w+)"
    funcs = re.findall(func_pattern, all_content)
    if funcs:
        return f"Implementing {funcs[0][1]}"

    return "Unknown topic"


def extract_recovery_checkpoint(
    window: TranscriptWindow,
    trigger: str = "pre_compact",
    use_claude: bool = False,
) -> RecoveryCheckpoint:
    """Extract a recovery checkpoint from a transcript window.

    Analyzes the conversation to extract key information:
    - Topic being discussed
    - Decisions made
    - Open threads/TODOs
    - Problems resolved
    - Files and tools used

    Args:
        window: TranscriptWindow to extract from
        trigger: What triggered this extraction
        use_claude: Whether to use headless Claude for summary

    Returns:
        RecoveryCheckpoint with extracted content
    """
    if window.is_empty:
        return RecoveryCheckpoint(
            id=generate_recovery_id("empty"),
            trigger=trigger,
            extracted_at=datetime.now(UTC).isoformat(),
        )

    # Extract raw content
    assistant_content = get_assistant_content(window)
    user_content = get_user_content(window)
    all_content = f"{assistant_content}\n\n{user_content}"

    # Extract topic
    topic = extract_topic(assistant_content, user_content)

    # Extract salient content
    salient = extract_salient_content(all_content)
    max_salience = get_max_salience(salient)

    # Extract categorized content
    decisions = tuple(extract_decisions(salient))
    open_threads = tuple(extract_open_threads(salient))
    resolutions = tuple(extract_resolutions(salient))

    # Extract context from tool calls
    files_touched = tuple(get_files_touched(window))
    tools_used = tuple(get_tools_used(window))

    # Optional: use Claude for summary
    summary = None
    extraction_method = "local"

    if use_claude:
        try:
            from sage.headless import extract_with_claude, is_claude_available

            if is_claude_available():
                result = extract_with_claude(all_content)
                if result:
                    summary = result.get("summary")
                    # Claude can provide better topic
                    if result.get("topic"):
                        topic = result["topic"]
                    extraction_method = "claude"
        except ImportError:
            logger.debug("Headless Claude not available")
        except Exception as e:
            logger.warning(f"Claude extraction failed: {e}")

    return RecoveryCheckpoint(
        id=generate_recovery_id(topic),
        type="recovery",
        trigger=trigger,
        extracted_at=datetime.now(UTC).isoformat(),
        extraction_method=extraction_method,
        topic=topic,
        decisions=decisions,
        open_threads=open_threads,
        resolutions=resolutions,
        files_touched=files_touched,
        tools_used=tools_used,
        summary=summary,
        salience_score=max_salience,
    )


def _recovery_to_markdown(checkpoint: RecoveryCheckpoint) -> str:
    """Convert a recovery checkpoint to Markdown format.

    Uses the same format as structured checkpoints for consistency.

    Args:
        checkpoint: RecoveryCheckpoint to convert

    Returns:
        Markdown string with YAML frontmatter
    """
    # Frontmatter
    frontmatter = {
        "id": checkpoint.id,
        "type": "recovery",
        "trigger": checkpoint.trigger,
        "extracted_at": checkpoint.extracted_at,
        "extraction_method": checkpoint.extraction_method,
        "salience_score": checkpoint.salience_score,
    }

    # Build markdown body
    lines = []

    # Topic as title
    lines.append(f"# {checkpoint.topic}")
    lines.append("")

    # Summary if available
    if checkpoint.summary:
        lines.append("## Summary")
        lines.append(checkpoint.summary)
        lines.append("")

    # Decisions
    if checkpoint.decisions:
        lines.append("## Decisions")
        for decision in checkpoint.decisions:
            # Clean up and format
            clean = decision.strip().replace("\n", " ")[:200]
            lines.append(f"- {clean}")
        lines.append("")

    # Open threads
    if checkpoint.open_threads:
        lines.append("## Open Threads")
        for thread in checkpoint.open_threads:
            clean = thread.strip().replace("\n", " ")[:200]
            lines.append(f"- {clean}")
        lines.append("")

    # Resolutions
    if checkpoint.resolutions:
        lines.append("## Resolutions")
        for resolution in checkpoint.resolutions:
            clean = resolution.strip().replace("\n", " ")[:200]
            lines.append(f"- {clean}")
        lines.append("")

    # Context
    if checkpoint.files_touched or checkpoint.tools_used:
        lines.append("## Context")
        if checkpoint.files_touched:
            files = ", ".join(checkpoint.files_touched[:10])
            lines.append(f"**Files touched:** {files}")
        if checkpoint.tools_used:
            tools = ", ".join(checkpoint.tools_used[:10])
            lines.append(f"**Tools used:** {tools}")
        lines.append("")

    body = "\n".join(lines)

    # Combine frontmatter and body
    fm_yaml = yaml.safe_dump(
        frontmatter, default_flow_style=False, sort_keys=False, allow_unicode=True
    )
    return f"---\n{fm_yaml}---\n\n{body}"


def _markdown_to_recovery(content: str) -> RecoveryCheckpoint | None:
    """Parse a recovery checkpoint from Markdown format.

    Args:
        content: Markdown content with YAML frontmatter

    Returns:
        RecoveryCheckpoint or None if parsing fails
    """
    try:
        if not content.startswith("---"):
            return None

        # Find end of frontmatter
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return None

        fm_text = content[3:end_idx].strip()
        body = content[end_idx + 3 :].strip()

        # Parse frontmatter
        fm = yaml.safe_load(fm_text) or {}

        # Verify it's a recovery checkpoint
        if fm.get("type") != "recovery":
            return None

        # Parse body sections
        topic = ""
        summary: str | None = None
        decisions: list[str] = []
        open_threads: list[str] = []
        resolutions: list[str] = []
        files_touched: list[str] = []
        tools_used: list[str] = []

        current_section = None
        for line in body.split("\n"):
            if line.startswith("# "):
                topic = line[2:].strip()
            elif line.startswith("## "):
                current_section = line[3:].strip().lower().replace(" ", "_")
            elif line.startswith("- "):
                item = line[2:].strip()
                if current_section == "decisions":
                    decisions.append(item)
                elif current_section == "open_threads":
                    open_threads.append(item)
                elif current_section == "resolutions":
                    resolutions.append(item)
            elif current_section == "summary" and line.strip():
                summary = line.strip() if summary is None else f"{summary} {line.strip()}"
            elif line.startswith("**Files touched:**"):
                files_str = line.replace("**Files touched:**", "").strip()
                files_touched = [f.strip() for f in files_str.split(",") if f.strip()]
            elif line.startswith("**Tools used:**"):
                tools_str = line.replace("**Tools used:**", "").strip()
                tools_used = [t.strip() for t in tools_str.split(",") if t.strip()]

        return RecoveryCheckpoint(
            id=fm.get("id", ""),
            type="recovery",
            trigger=fm.get("trigger", ""),
            extracted_at=fm.get("extracted_at", ""),
            extraction_method=fm.get("extraction_method", "local"),
            topic=topic,
            decisions=tuple(decisions),
            open_threads=tuple(open_threads),
            resolutions=tuple(resolutions),
            files_touched=tuple(files_touched),
            tools_used=tuple(tools_used),
            summary=summary,
            salience_score=fm.get("salience_score", 0.0),
        )

    except (yaml.YAMLError, KeyError, ValueError) as e:
        logger.warning(f"Failed to parse recovery checkpoint: {e}")
        return None


def get_recovery_checkpoints_dir(project_path: Path | None = None) -> Path:
    """Get the checkpoints directory for recovery checkpoints.

    Uses the same directory as structured checkpoints.

    Args:
        project_path: Optional project path for project-local checkpoints

    Returns:
        Path to checkpoints directory
    """
    if project_path:
        local_dir = project_path / ".sage" / "checkpoints"
        if local_dir.exists() or (project_path / ".sage").exists():
            return local_dir
    return CHECKPOINTS_DIR


def ensure_checkpoints_dir(project_path: Path | None = None) -> Path:
    """Ensure checkpoints directory exists and return it."""
    checkpoints_dir = get_recovery_checkpoints_dir(project_path)
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    return checkpoints_dir


def save_recovery_checkpoint(
    checkpoint: RecoveryCheckpoint,
    project_path: Path | None = None,
) -> Path:
    """Save a recovery checkpoint to disk.

    Uses atomic write (temp file + rename) to prevent corruption.

    Args:
        checkpoint: RecoveryCheckpoint to save
        project_path: Optional project path for project-local storage

    Returns:
        Path to saved checkpoint file
    """
    import os
    import tempfile

    checkpoints_dir = ensure_checkpoints_dir(project_path)

    content = _recovery_to_markdown(checkpoint)
    file_path = checkpoints_dir / f"{checkpoint.id}.md"

    # Atomic write
    fd, temp_path = tempfile.mkstemp(
        dir=checkpoints_dir,
        prefix=f".{checkpoint.id}_",
        suffix=".md.tmp",
    )
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.chmod(temp_path, 0o600)
        os.rename(temp_path, file_path)
    except Exception:
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise

    logger.info(f"Saved recovery checkpoint: {checkpoint.id}")
    return file_path


def load_recovery_checkpoint(
    checkpoint_id: str,
    project_path: Path | None = None,
) -> RecoveryCheckpoint | None:
    """Load a recovery checkpoint by ID.

    Supports partial ID matching.

    Args:
        checkpoint_id: Full or partial checkpoint ID
        project_path: Optional project path

    Returns:
        RecoveryCheckpoint or None if not found
    """
    checkpoints_dir = get_recovery_checkpoints_dir(project_path)

    if not checkpoints_dir.exists():
        return None

    # Try exact match first
    file_path = checkpoints_dir / f"{checkpoint_id}.md"
    if file_path.exists():
        content = file_path.read_text()
        return _markdown_to_recovery(content)

    # Try partial match
    matches = list(checkpoints_dir.glob(f"*{checkpoint_id}*.md"))
    if len(matches) == 1:
        content = matches[0].read_text()
        return _markdown_to_recovery(content)

    return None


def list_recovery_checkpoints(
    project_path: Path | None = None,
    limit: int = 20,
) -> list[RecoveryCheckpoint]:
    """List recovery checkpoints, most recent first.

    Args:
        project_path: Optional project path
        limit: Maximum number to return

    Returns:
        List of recovery checkpoints
    """
    checkpoints_dir = get_recovery_checkpoints_dir(project_path)

    if not checkpoints_dir.exists():
        return []

    # Find all recovery checkpoint files
    files = list(checkpoints_dir.glob("*_recovery-*.md"))

    checkpoints = []
    for file_path in sorted(files, reverse=True):
        content = file_path.read_text()
        cp = _markdown_to_recovery(content)
        if cp is not None:
            checkpoints.append(cp)
            if len(checkpoints) >= limit:
                break

    return checkpoints


def format_recovery_for_context(checkpoint: RecoveryCheckpoint) -> str:
    """Format a recovery checkpoint for injection into conversation context.

    Similar to structured checkpoint formatting but notes it's auto-extracted.

    Args:
        checkpoint: RecoveryCheckpoint to format

    Returns:
        Formatted context string
    """
    parts = [
        "# Recovery Context (Auto-extracted)\n",
        f"*Checkpoint: {checkpoint.id}*\n",
        f"*Extracted: {checkpoint.extracted_at[:16].replace('T', ' ')} | "
        f"Method: {checkpoint.extraction_method}*\n\n",
        "## Topic\n",
        f"{checkpoint.topic}\n\n",
    ]

    if checkpoint.summary:
        parts.append("## Summary\n")
        parts.append(f"{checkpoint.summary}\n\n")

    if checkpoint.decisions:
        parts.append("## Decisions Made\n")
        for decision in checkpoint.decisions[:5]:
            parts.append(f"- {decision}\n")
        parts.append("\n")

    if checkpoint.open_threads:
        parts.append("## Open Threads\n")
        for thread in checkpoint.open_threads[:5]:
            parts.append(f"- {thread}\n")
        parts.append("\n")

    if checkpoint.resolutions:
        parts.append("## Resolutions\n")
        for resolution in checkpoint.resolutions[:5]:
            parts.append(f"- {resolution}\n")
        parts.append("\n")

    if checkpoint.files_touched:
        parts.append("## Files Touched\n")
        parts.append(", ".join(checkpoint.files_touched[:10]))
        parts.append("\n")

    return "".join(parts)
