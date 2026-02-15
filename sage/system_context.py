"""System context folder for Sage.

The .sage/system/ folder contains agent-managed pinned content that is
automatically injected at session start. This enables persistent context
without requiring explicit tool calls.

Directory Structure:
    .sage/system/
    ├── objective.md      # Current goal (always first)
    ├── constraints.md    # "Don't do X" rules
    ├── context.md        # Background context
    └── pinned/           # Pinned checkpoints/knowledge

Files are loaded in priority order:
1. objective.md (always first)
2. constraints.md (always second)
3. pinned/*.md (alphabetical)
4. Other *.md files (alphabetical)

Token budget is configurable via system_folder_max_tokens (default: 2000).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sage.config import detect_project_root, get_sage_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SystemFile:
    """A file from the system folder."""

    name: str  # Filename without path
    path: Path  # Full path
    content: str  # File content
    tokens: int  # Estimated token count


def get_system_folder(project_path: Path | None = None) -> Path:
    """Get the system folder path, preferring project-local.

    Args:
        project_path: Optional explicit project path

    Returns:
        Path to .sage/system/ directory
    """
    if project_path:
        return project_path / ".sage" / "system"

    # Auto-detect project root
    detected = detect_project_root()
    if detected:
        return detected / ".sage" / "system"

    # Fall back to user-level (though system folder is typically project-scoped)
    from sage.config import SAGE_DIR

    return SAGE_DIR / "system"


def _estimate_tokens(content: str) -> int:
    """Estimate token count for content.

    Uses rough heuristic of ~4 characters per token.
    """
    return len(content) // 4


def _load_file(path: Path) -> SystemFile | None:
    """Load a single system file.

    Args:
        path: Path to the file

    Returns:
        SystemFile or None if file can't be read
    """
    try:
        content = path.read_text()
        return SystemFile(
            name=path.name,
            path=path,
            content=content,
            tokens=_estimate_tokens(content),
        )
    except OSError as e:
        logger.warning(f"Failed to read system file {path}: {e}")
        return None


def load_system_files(
    project_path: Path | None = None,
    max_tokens: int | None = None,
) -> list[SystemFile]:
    """Load system folder files in priority order.

    Priority order:
    1. objective.md (current goal - always first)
    2. constraints.md (rules/restrictions - always second)
    3. pinned/*.md (pinned items - alphabetical)
    4. Other *.md files (alphabetical)

    Args:
        project_path: Optional project path
        max_tokens: Maximum total tokens to load (None uses config default)

    Returns:
        List of SystemFile objects within token budget
    """
    config = get_sage_config(project_path)

    # Check if system folder is enabled
    if not getattr(config, "system_folder_enabled", True):
        return []

    if max_tokens is None:
        max_tokens = getattr(config, "system_folder_max_tokens", 2000)

    system_folder = get_system_folder(project_path)

    if not system_folder.exists():
        return []

    files: list[SystemFile] = []
    total_tokens = 0

    # Priority files in order
    priority_files = [
        system_folder / "objective.md",
        system_folder / "constraints.md",
    ]

    # Load priority files first
    for priority_path in priority_files:
        if priority_path.exists():
            file = _load_file(priority_path)
            if file:
                if total_tokens + file.tokens <= max_tokens:
                    files.append(file)
                    total_tokens += file.tokens
                else:
                    # Truncate this file to fit
                    remaining_tokens = max_tokens - total_tokens
                    if remaining_tokens > 50:  # Only include if meaningful
                        truncated = _truncate_content(file.content, remaining_tokens)
                        files.append(
                            SystemFile(
                                name=file.name,
                                path=file.path,
                                content=truncated,
                                tokens=remaining_tokens,
                            )
                        )
                        total_tokens = max_tokens
                    break

    if total_tokens >= max_tokens:
        return files

    # Load pinned files (alphabetical)
    pinned_dir = system_folder / "pinned"
    if pinned_dir.exists():
        pinned_files = sorted(pinned_dir.glob("*.md"))
        for path in pinned_files:
            file = _load_file(path)
            if file:
                if total_tokens + file.tokens <= max_tokens:
                    files.append(file)
                    total_tokens += file.tokens
                else:
                    # Truncate or skip
                    remaining_tokens = max_tokens - total_tokens
                    if remaining_tokens > 50:
                        truncated = _truncate_content(file.content, remaining_tokens)
                        files.append(
                            SystemFile(
                                name=file.name,
                                path=file.path,
                                content=truncated,
                                tokens=remaining_tokens,
                            )
                        )
                        total_tokens = max_tokens
                    break

    if total_tokens >= max_tokens:
        return files

    # Load other .md files (alphabetical, excluding priority files)
    priority_names = {"objective.md", "constraints.md"}
    other_files = sorted(
        f
        for f in system_folder.glob("*.md")
        if f.name not in priority_names
    )

    for path in other_files:
        file = _load_file(path)
        if file:
            if total_tokens + file.tokens <= max_tokens:
                files.append(file)
                total_tokens += file.tokens
            else:
                # Truncate or skip
                remaining_tokens = max_tokens - total_tokens
                if remaining_tokens > 50:
                    truncated = _truncate_content(file.content, remaining_tokens)
                    files.append(
                        SystemFile(
                            name=file.name,
                            path=file.path,
                            content=truncated,
                            tokens=remaining_tokens,
                        )
                    )
                break

    return files


def _truncate_content(content: str, max_tokens: int) -> str:
    """Truncate content to fit within token budget.

    Args:
        content: Content to truncate
        max_tokens: Maximum tokens

    Returns:
        Truncated content with indicator
    """
    max_chars = max_tokens * 4  # Rough estimate
    if len(content) <= max_chars:
        return content

    # Truncate at word boundary if possible
    truncated = content[: max_chars - 20]  # Leave room for indicator
    last_space = truncated.rfind(" ")
    if last_space > max_chars // 2:
        truncated = truncated[:last_space]

    return truncated + "\n\n... (truncated)"


def format_system_context(
    files: list[SystemFile],
    use_toon: bool | None = None,
) -> str:
    """Format system files for context injection.

    Args:
        files: List of SystemFile objects
        use_toon: Use TOON-style compact format. If None, check config.

    Returns:
        Formatted string for injection
    """
    if not files:
        return ""

    if use_toon is None:
        config = get_sage_config()
        use_toon = getattr(config, "output_format", "markdown") == "toon"

    total_tokens = sum(f.tokens for f in files)

    if use_toon:
        return _format_system_toon(files, total_tokens)

    parts = [
        "═══ SYSTEM CONTEXT ═══",
        f"*{len(files)} file(s), ~{total_tokens} tokens*",
        "",
    ]

    for file in files:
        parts.append(f"## {file.name}")
        parts.append(file.content)
        parts.append("")

    parts.append("═══════════════════════")

    return "\n".join(parts)


def _format_system_toon(files: list[SystemFile], total_tokens: int) -> str:
    """Format system context using TOON-inspired compact format.

    Inspired by TOON (https://toon-format.org) by @mixeden.
    """
    parts = [
        f"# System [{len(files)}] ~{total_tokens}tok",
        "",
    ]

    for file in files:
        # Use filename without .md as header
        name = file.name.replace(".md", "")
        parts.append(f"## {name}")
        parts.append(file.content)
        parts.append("")

    return "\n".join(parts)


def ensure_system_folder(project_path: Path | None = None) -> Path:
    """Ensure system folder structure exists.

    Args:
        project_path: Optional project path

    Returns:
        Path to the system folder
    """
    system_folder = get_system_folder(project_path)
    system_folder.mkdir(parents=True, exist_ok=True)
    (system_folder / "pinned").mkdir(exist_ok=True)
    return system_folder


def save_system_file(
    filename: str,
    content: str,
    project_path: Path | None = None,
) -> Path:
    """Save a file to the system folder.

    Args:
        filename: Filename (should end with .md)
        content: File content
        project_path: Optional project path

    Returns:
        Path to the saved file
    """
    system_folder = ensure_system_folder(project_path)

    # Sanitize filename
    safe_name = filename.replace("..", "").replace("/", "_").replace("\\", "_")
    if not safe_name.endswith(".md"):
        safe_name += ".md"

    file_path = system_folder / safe_name
    file_path.write_text(content)
    file_path.chmod(0o600)

    return file_path


def remove_system_file(
    filename: str,
    project_path: Path | None = None,
) -> bool:
    """Remove a file from the system folder.

    Args:
        filename: Filename to remove
        project_path: Optional project path

    Returns:
        True if file was removed, False if not found
    """
    # Sanitize filename to prevent path traversal
    safe_name = filename.replace("..", "").replace("/", "_").replace("\\", "_")
    if not safe_name:
        return False

    system_folder = get_system_folder(project_path)
    file_path = system_folder / safe_name

    if file_path.exists() and file_path.is_file():
        try:
            file_path.unlink()
            return True
        except OSError as e:
            logger.warning(f"Failed to remove system file {filename}: {e}")
            return False

    return False


def list_system_files(project_path: Path | None = None) -> list[str]:
    """List all files in the system folder.

    Args:
        project_path: Optional project path

    Returns:
        List of filenames
    """
    system_folder = get_system_folder(project_path)

    if not system_folder.exists():
        return []

    files = []

    # Root .md files
    for f in sorted(system_folder.glob("*.md")):
        files.append(f.name)

    # Pinned files
    pinned_dir = system_folder / "pinned"
    if pinned_dir.exists():
        for f in sorted(pinned_dir.glob("*.md")):
            files.append(f"pinned/{f.name}")

    return files
