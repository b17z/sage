"""Core file marking for session-start context injection.

Core files are key files that should be injected into context when
starting a session in a project, providing immediate codebase awareness.

Storage:
    ~/.sage/codebase/core_files.yaml       # Global core files
    <project>/.sage/codebase/core_files.yaml  # Project-specific
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml

from sage.codebase.indexer import detect_project_name, get_codebase_dir
from sage.codebase.models import CoreFile
from sage.config import detect_project_root

logger = logging.getLogger(__name__)


# =============================================================================
# Paths
# =============================================================================


def get_core_files_path(project_path: Path | None = None) -> Path:
    """Get path to core files YAML.

    Args:
        project_path: Project root. If None, uses global storage.

    Returns:
        Path to core_files.yaml
    """
    return get_codebase_dir(project_path) / "core_files.yaml"


# =============================================================================
# Storage
# =============================================================================


def _load_core_files(project_path: Path | None = None) -> list[CoreFile]:
    """Load core files from YAML.

    Args:
        project_path: Project root

    Returns:
        List of CoreFile objects
    """
    path = get_core_files_path(project_path)
    if not path.exists():
        return []

    try:
        data = yaml.safe_load(path.read_text()) or {}
        files = []
        for item in data.get("files", []):
            files.append(
                CoreFile(
                    path=item["path"],
                    project=item.get("project", ""),
                    summary=item.get("summary", ""),
                    marked_at=item.get("marked_at", ""),
                )
            )
        return files
    except Exception as e:
        logger.warning(f"Failed to load core files from {path}: {e}")
        return []


def _save_core_files(files: list[CoreFile], project_path: Path | None = None) -> None:
    """Save core files to YAML.

    Args:
        files: List of CoreFile objects
        project_path: Project root
    """
    path = get_core_files_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": 1,
        "files": [
            {
                "path": f.path,
                "project": f.project,
                "summary": f.summary,
                "marked_at": f.marked_at,
            }
            for f in files
        ],
    }

    path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))


# =============================================================================
# Core File API
# =============================================================================


def mark_core(
    file_path: str | Path,
    project_path: Path | None = None,
    summary: str = "",
) -> CoreFile:
    """Mark a file as a core file for session injection.

    Args:
        file_path: Path to the file (absolute or relative)
        project_path: Project root (auto-detected if None)
        summary: Brief description of what this file does

    Returns:
        Created CoreFile
    """
    # Resolve paths
    if project_path is None:
        project_path = detect_project_root()

    if project_path is None:
        project_path = Path.cwd()

    # Make path relative to project
    file_path = Path(file_path)
    if file_path.is_absolute():
        try:
            rel_path = str(file_path.relative_to(project_path))
        except ValueError:
            rel_path = str(file_path)
    else:
        rel_path = str(file_path)

    # Get project name
    project = detect_project_name(project_path)

    # Create CoreFile
    core_file = CoreFile(
        path=rel_path,
        project=project,
        summary=summary,
        marked_at=datetime.now(UTC).isoformat(),
    )

    # Load existing and add/update
    files = _load_core_files(project_path)

    # Remove existing entry for same path
    files = [f for f in files if f.path != rel_path]
    files.append(core_file)

    _save_core_files(files, project_path)
    logger.info(f"Marked core file: {rel_path}")

    return core_file


def unmark_core(
    file_path: str | Path,
    project_path: Path | None = None,
) -> bool:
    """Remove a file's core marking.

    Args:
        file_path: Path to the file
        project_path: Project root

    Returns:
        True if file was unmarked, False if not found
    """
    if project_path is None:
        project_path = detect_project_root() or Path.cwd()

    # Make path relative
    file_path = Path(file_path)
    if file_path.is_absolute():
        try:
            rel_path = str(file_path.relative_to(project_path))
        except ValueError:
            rel_path = str(file_path)
    else:
        rel_path = str(file_path)

    files = _load_core_files(project_path)
    original_count = len(files)
    files = [f for f in files if f.path != rel_path]

    if len(files) == original_count:
        return False  # Not found

    _save_core_files(files, project_path)
    logger.info(f"Unmarked core file: {rel_path}")
    return True


def list_core(
    project_path: Path | None = None,
    project: str | None = None,
) -> list[CoreFile]:
    """List all core files.

    Args:
        project_path: Project root
        project: Optional project name filter

    Returns:
        List of CoreFile objects
    """
    files = _load_core_files(project_path)

    if project:
        files = [f for f in files if f.project == project]

    return files


def get_core_file(
    file_path: str | Path,
    project_path: Path | None = None,
) -> CoreFile | None:
    """Get a specific core file by path.

    Args:
        file_path: Path to the file
        project_path: Project root

    Returns:
        CoreFile or None
    """
    if project_path is None:
        project_path = detect_project_root() or Path.cwd()

    # Make path relative
    file_path = Path(file_path)
    if file_path.is_absolute():
        try:
            rel_path = str(file_path.relative_to(project_path))
        except ValueError:
            rel_path = str(file_path)
    else:
        rel_path = str(file_path)

    files = _load_core_files(project_path)
    for f in files:
        if f.path == rel_path:
            return f

    return None


# =============================================================================
# Context Injection
# =============================================================================


def get_core_context(
    project_path: Path | None = None,
    max_files: int = 5,
    max_tokens: int = 4000,
) -> str:
    """Get formatted core files context for session injection.

    Args:
        project_path: Project root
        max_files: Maximum files to include
        max_tokens: Maximum total tokens

    Returns:
        Formatted context string for injection
    """
    if project_path is None:
        project_path = detect_project_root()

    if project_path is None:
        return ""

    files = list_core(project_path)
    if not files:
        return ""

    lines = [
        "═══ CORE FILES ═══",
        f"*Project: {detect_project_name(project_path)}*",
        "",
    ]

    total_tokens = 0
    included = 0

    for core_file in files[:max_files]:
        # Try to read file content
        file_path = project_path / core_file.path
        content = ""

        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                # Estimate tokens
                tokens = len(content) // 4
                if total_tokens + tokens > max_tokens:
                    content = content[: (max_tokens - total_tokens) * 4]
                    tokens = len(content) // 4
                total_tokens += tokens
            except Exception:
                content = "(failed to read)"

        lines.append(f"## {core_file.path}")
        if core_file.summary:
            lines.append(f"*{core_file.summary}*")
        lines.append("")

        if content:
            # Truncate for display
            preview_lines = content.split("\n")[:50]  # First 50 lines
            lines.append("```")
            lines.extend(preview_lines)
            if len(content.split("\n")) > 50:
                lines.append("... (truncated)")
            lines.append("```")
        lines.append("")

        included += 1
        if total_tokens >= max_tokens:
            break

    if included < len(files):
        lines.append(f"*({len(files) - included} more core files not shown)*")

    lines.append("")
    lines.append("═══════════════════")

    return "\n".join(lines)


def inject_core_context_if_available(response: str, project_path: Path | None = None) -> str:
    """Inject core file context into a response if available.

    Used by sage_continuity_status() to include core files in session start.

    Args:
        response: Original response
        project_path: Project root

    Returns:
        Response with core context prepended if available
    """
    context = get_core_context(project_path)
    if context:
        return context + "\n\n" + response
    return response
