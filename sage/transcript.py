"""Transcript extractor for Claude Code JSONL files.

Reads and parses Claude Code conversation transcripts for recovery checkpoint
extraction. Uses cursor-based incremental reading for efficient tailing.

Architecture:
- TranscriptEntry represents a single conversation turn
- TranscriptWindow holds a collection of entries with cursor position
- Cursor-based reading enables incremental tailing for the watcher daemon

Security:
- JSON parsing uses safe json.loads (no code execution)
- Line length limits prevent memory exhaustion
- Path validation before reading
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Maximum line length to prevent memory exhaustion
MAX_LINE_LENGTH = 10_000_000  # 10MB - same as watcher


@dataclass(frozen=True)
class ToolCall:
    """A tool call from the transcript."""

    name: str
    input: dict[str, Any] = field(default_factory=dict)
    output: str = ""


@dataclass(frozen=True)
class TranscriptEntry:
    """A single entry from the conversation transcript.

    Represents one turn in the conversation (user message, assistant message,
    or tool use).
    """

    role: str  # "user" | "assistant" | "tool"
    content: str
    timestamp: str
    tool_calls: tuple[ToolCall, ...] = ()
    is_compaction: bool = False

    @classmethod
    def from_jsonl(cls, data: dict[str, Any]) -> "TranscriptEntry | None":
        """Parse a TranscriptEntry from a JSONL line.

        Args:
            data: Parsed JSON object from JSONL line

        Returns:
            TranscriptEntry or None if not a valid entry
        """
        # Skip non-dict entries
        if not isinstance(data, dict):
            return None

        # Check for compaction summary
        if data.get("isCompactSummary") is True:
            message = data.get("message", {})
            content = message.get("content", "") if isinstance(message, dict) else ""
            return cls(
                role="system",
                content=content,
                timestamp=datetime.now(UTC).isoformat(),
                is_compaction=True,
            )

        # Extract message field
        message = data.get("message", {})
        if not isinstance(message, dict):
            return None

        role = message.get("role", "")
        if not role:
            return None

        # Extract content (may be string or list of content blocks)
        content_raw = message.get("content", "")
        content = _extract_text_content(content_raw)

        # Extract timestamp
        timestamp = data.get("timestamp", "")
        if not timestamp:
            timestamp = datetime.now(UTC).isoformat()

        # Extract tool calls from content blocks
        tool_calls = _extract_tool_calls(content_raw)

        return cls(
            role=role,
            content=content,
            timestamp=timestamp,
            tool_calls=tuple(tool_calls),
        )


def _extract_text_content(content: Any) -> str:
    """Extract text content from message content field.

    Content can be:
    - A string
    - A list of content blocks with type="text"
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
        return "\n".join(texts)

    return ""


def _extract_tool_calls(content: Any) -> list[ToolCall]:
    """Extract tool calls from message content blocks."""
    if not isinstance(content, list):
        return []

    tool_calls = []
    for block in content:
        if not isinstance(block, dict):
            continue

        if block.get("type") == "tool_use":
            tool_calls.append(
                ToolCall(
                    name=block.get("name", "unknown"),
                    input=block.get("input", {}),
                )
            )
        elif block.get("type") == "tool_result":
            # Tool results have content but no name directly
            # They reference a tool_use_id
            pass

    return tool_calls


@dataclass(frozen=True)
class TranscriptWindow:
    """A window of transcript entries with cursor position.

    The cursor tracks file offset for incremental reading.
    """

    entries: tuple[TranscriptEntry, ...]
    cursor_position: int  # File byte offset after last read

    def __len__(self) -> int:
        return len(self.entries)

    @property
    def is_empty(self) -> bool:
        return len(self.entries) == 0


@dataclass(frozen=True)
class CursorState:
    """Persistent cursor state for incremental reading."""

    file_path: str
    position: int
    last_read: str  # ISO timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "position": self.position,
            "last_read": self.last_read,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CursorState":
        return cls(
            file_path=data.get("file_path", ""),
            position=data.get("position", 0),
            last_read=data.get("last_read", ""),
        )


def read_transcript_since(
    path: Path,
    cursor: int = 0,
    max_entries: int = 1000,
) -> TranscriptWindow:
    """Read transcript entries since cursor position.

    Args:
        path: Path to the JSONL transcript file
        cursor: File byte offset to start reading from
        max_entries: Maximum number of entries to return

    Returns:
        TranscriptWindow with entries and new cursor position

    Security:
        - Validates path before reading
        - Limits line length to prevent memory exhaustion
        - Returns empty window on errors (graceful degradation)
    """
    if not path.exists():
        logger.warning(f"Transcript not found: {path}")
        return TranscriptWindow(entries=(), cursor_position=cursor)

    if not path.is_file():
        logger.warning(f"Transcript path is not a file: {path}")
        return TranscriptWindow(entries=(), cursor_position=cursor)

    entries = []
    new_cursor = cursor

    try:
        with open(path, "r", encoding="utf-8") as f:
            f.seek(cursor)

            # Use readline() instead of iteration to allow f.tell()
            while True:
                line = f.readline()
                if not line:
                    break  # EOF

                # Limit line length
                if len(line) > MAX_LINE_LENGTH:
                    logger.warning(f"Skipping oversized line: {len(line)} bytes")
                    new_cursor = f.tell()
                    continue

                line = line.strip()
                if not line:
                    new_cursor = f.tell()
                    continue

                try:
                    data = json.loads(line)
                    entry = TranscriptEntry.from_jsonl(data)
                    if entry is not None:
                        entries.append(entry)

                        if len(entries) >= max_entries:
                            new_cursor = f.tell()
                            break

                except json.JSONDecodeError:
                    # Normal for partial lines, skip
                    pass

                new_cursor = f.tell()

    except (OSError, IOError) as e:
        logger.error(f"Failed to read transcript: {e}")
        return TranscriptWindow(entries=(), cursor_position=cursor)

    return TranscriptWindow(entries=tuple(entries), cursor_position=new_cursor)


def read_full_transcript(
    path: Path,
    max_entries: int = 10000,
) -> TranscriptWindow:
    """Read the entire transcript from the beginning.

    Convenience wrapper around read_transcript_since with cursor=0.

    Args:
        path: Path to the JSONL transcript file
        max_entries: Maximum entries to return

    Returns:
        TranscriptWindow with all entries
    """
    return read_transcript_since(path, cursor=0, max_entries=max_entries)


def get_assistant_content(window: TranscriptWindow) -> str:
    """Extract all assistant message content from a window.

    Args:
        window: TranscriptWindow to extract from

    Returns:
        Concatenated assistant content (newline separated)
    """
    return "\n\n".join(
        entry.content for entry in window.entries if entry.role == "assistant" and entry.content
    )


def get_user_content(window: TranscriptWindow) -> str:
    """Extract all user message content from a window.

    Args:
        window: TranscriptWindow to extract from

    Returns:
        Concatenated user content (newline separated)
    """
    return "\n\n".join(
        entry.content for entry in window.entries if entry.role == "user" and entry.content
    )


def get_tool_summary(window: TranscriptWindow) -> list[str]:
    """Get a summary of tool calls from a window.

    Args:
        window: TranscriptWindow to extract from

    Returns:
        List of "ToolName(args...)" strings
    """
    summaries = []
    for entry in window.entries:
        for tool in entry.tool_calls:
            # Create brief summary of tool call
            args_preview = ", ".join(
                f"{k}={repr(v)[:20]}" for k, v in list(tool.input.items())[:3]
            )
            summaries.append(f"{tool.name}({args_preview})")

    return summaries


def get_files_touched(window: TranscriptWindow) -> list[str]:
    """Extract file paths from tool calls.

    Looks for file_path, path, file arguments in tool calls.

    Args:
        window: TranscriptWindow to extract from

    Returns:
        Deduplicated list of file paths
    """
    files = set()

    for entry in window.entries:
        for tool in entry.tool_calls:
            # Look for common file path argument names
            for key in ("file_path", "path", "file", "notebook_path"):
                if key in tool.input:
                    value = tool.input[key]
                    if isinstance(value, str) and value:
                        files.add(value)

    return sorted(files)


def get_tools_used(window: TranscriptWindow) -> list[str]:
    """Get unique tool names used in a window.

    Args:
        window: TranscriptWindow to extract from

    Returns:
        Deduplicated sorted list of tool names
    """
    tools = set()

    for entry in window.entries:
        for tool in entry.tool_calls:
            tools.add(tool.name)

    return sorted(tools)


def has_compaction(window: TranscriptWindow) -> bool:
    """Check if the window contains a compaction event.

    Args:
        window: TranscriptWindow to check

    Returns:
        True if any entry is a compaction summary
    """
    return any(entry.is_compaction for entry in window.entries)


def get_compaction_summary(window: TranscriptWindow) -> str | None:
    """Get the compaction summary content if present.

    Args:
        window: TranscriptWindow to check

    Returns:
        Compaction summary text or None
    """
    for entry in window.entries:
        if entry.is_compaction:
            return entry.content
    return None


def save_cursor(path: Path, cursor: CursorState) -> bool:
    """Save cursor state to a file.

    Args:
        path: Path to save cursor state
        cursor: CursorState to save

    Returns:
        True if saved successfully
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(cursor.to_dict(), f)
        path.chmod(0o600)
        return True
    except (OSError, IOError) as e:
        logger.error(f"Failed to save cursor: {e}")
        return False


def load_cursor(path: Path) -> CursorState | None:
    """Load cursor state from a file.

    Args:
        path: Path to load cursor state from

    Returns:
        CursorState or None if not found/invalid
    """
    if not path.exists():
        return None

    try:
        with open(path) as f:
            data = json.load(f)
        return CursorState.from_dict(data)
    except (json.JSONDecodeError, OSError, IOError) as e:
        logger.warning(f"Failed to load cursor: {e}")
        return None
