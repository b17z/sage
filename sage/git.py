"""Git integration for Sage.

Provides git context capture and change detection using git CLI.
Used for:
- Capturing branch/commit state in checkpoints
- Detecting stale code links (files changed since knowledge was saved)
- Triggering reindex when code has changed

All functions gracefully handle non-git directories by returning None/empty values.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# =============================================================================
# Data Types
# =============================================================================


@dataclass(frozen=True)
class GitContext:
    """Git state at a point in time.

    Captured when saving checkpoints/knowledge to enable:
    - Showing what branch/commit research was done on
    - Detecting when code has changed since then
    """

    branch: str  # Current branch name (e.g., "main", "feature/auth")
    commit: str  # Short SHA (e.g., "a3f2b1c")
    dirty: bool  # Uncommitted changes present?
    recent_commits: tuple[str, ...]  # Last N commit messages (1-liners)

    def to_dict(self) -> dict:
        """Serialize to dict for storage."""
        return {
            "branch": self.branch,
            "commit": self.commit,
            "dirty": self.dirty,
            "recent_commits": list(self.recent_commits),
        }

    @classmethod
    def from_dict(cls, data: dict) -> GitContext:
        """Deserialize from dict."""
        return cls(
            branch=data.get("branch", ""),
            commit=data.get("commit", ""),
            dirty=data.get("dirty", False),
            recent_commits=tuple(data.get("recent_commits", [])),
        )


@dataclass(frozen=True)
class DiffSummary:
    """Summary of uncommitted changes."""

    files_changed: tuple[str, ...]  # Modified/added/deleted files
    staged_files: tuple[str, ...]  # Files in staging area
    insertions: int  # Lines added
    deletions: int  # Lines removed

    @property
    def summary(self) -> str:
        """Human-readable summary like '+142 -67 across 5 files'."""
        if not self.files_changed and not self.staged_files:
            return "no changes"
        total_files = len(set(self.files_changed) | set(self.staged_files))
        return f"+{self.insertions} -{self.deletions} across {total_files} files"

    def to_dict(self) -> dict:
        """Serialize to dict for storage."""
        return {
            "files_changed": list(self.files_changed),
            "staged_files": list(self.staged_files),
            "insertions": self.insertions,
            "deletions": self.deletions,
        }

    @classmethod
    def from_dict(cls, data: dict) -> DiffSummary:
        """Deserialize from dict."""
        return cls(
            files_changed=tuple(data.get("files_changed", [])),
            staged_files=tuple(data.get("staged_files", [])),
            insertions=data.get("insertions", 0),
            deletions=data.get("deletions", 0),
        )


# =============================================================================
# Git CLI Helpers
# =============================================================================


def _run_git(args: list[str], cwd: Path | None = None) -> str | None:
    """Run a git command and return stdout, or None on failure.

    Args:
        args: Git command arguments (without 'git' prefix)
        cwd: Working directory (defaults to current)

    Returns:
        Stdout string on success, None on failure
    """
    try:
        # Security: shell=False (default), args are internal constants
        result = subprocess.run(
            ["git", *args],  # noqa: S603, S607
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.debug(f"Git command failed: {e}")
        return None


def is_git_repo(path: Path | None = None) -> bool:
    """Check if path is inside a git repository."""
    return _run_git(["rev-parse", "--git-dir"], cwd=path) is not None


def get_branch(path: Path | None = None) -> str:
    """Get current branch name.

    Returns:
        Branch name or "HEAD" if detached, "" if not a git repo
    """
    # Try symbolic-ref first (works for normal branches)
    branch = _run_git(["symbolic-ref", "--short", "HEAD"], cwd=path)
    if branch:
        return branch

    # Detached HEAD - try to get a meaningful name
    desc = _run_git(["describe", "--tags", "--always"], cwd=path)
    return desc or ""


def get_commit(path: Path | None = None, short: bool = True) -> str:
    """Get current commit SHA.

    Args:
        path: Repository path
        short: Return short SHA (7 chars) if True

    Returns:
        Commit SHA or "" if not a git repo
    """
    args = ["rev-parse"]
    if short:
        args.append("--short")
    args.append("HEAD")

    return _run_git(args, cwd=path) or ""


def is_dirty(path: Path | None = None) -> bool:
    """Check if working tree has uncommitted changes."""
    status = _run_git(["status", "--porcelain"], cwd=path)
    return bool(status)


def get_recent_commits(path: Path | None = None, count: int = 3) -> tuple[str, ...]:
    """Get recent commit messages (one-liners).

    Args:
        path: Repository path
        count: Number of commits to retrieve

    Returns:
        Tuple of commit messages
    """
    output = _run_git(["log", f"-{count}", "--oneline", "--no-decorate"], cwd=path)
    if not output:
        return ()
    return tuple(output.split("\n"))


def get_changed_files_since(
    commit: str,
    path: Path | None = None,
) -> tuple[str, ...]:
    """Get files changed since a specific commit.

    Args:
        commit: Commit SHA to compare against
        path: Repository path

    Returns:
        Tuple of relative file paths that changed
    """
    output = _run_git(["diff", "--name-only", commit, "HEAD"], cwd=path)
    if not output:
        return ()
    return tuple(output.split("\n"))


def get_file_commits_since(
    file_path: str,
    since_commit: str,
    path: Path | None = None,
) -> tuple[str, ...]:
    """Get commits that touched a specific file since a commit.

    Args:
        file_path: Relative path to file
        since_commit: Commit SHA to start from
        path: Repository path

    Returns:
        Tuple of commit SHAs that modified the file
    """
    output = _run_git(
        ["log", "--oneline", f"{since_commit}..HEAD", "--", file_path],
        cwd=path,
    )
    if not output:
        return ()
    return tuple(output.split("\n"))


def get_diff_summary(path: Path | None = None) -> DiffSummary:
    """Get summary of uncommitted changes.

    Returns:
        DiffSummary with changed files and line counts
    """
    # Get unstaged changes
    unstaged = _run_git(["diff", "--name-only"], cwd=path)
    unstaged_files = tuple(unstaged.split("\n")) if unstaged else ()

    # Get staged changes
    staged = _run_git(["diff", "--staged", "--name-only"], cwd=path)
    staged_files = tuple(staged.split("\n")) if staged else ()

    # Get line stats (staged + unstaged)
    stats = _run_git(["diff", "--shortstat", "HEAD"], cwd=path)
    insertions = 0
    deletions = 0

    if stats:
        # Parse "3 files changed, 42 insertions(+), 17 deletions(-)"
        import re

        ins_match = re.search(r"(\d+) insertion", stats)
        del_match = re.search(r"(\d+) deletion", stats)
        if ins_match:
            insertions = int(ins_match.group(1))
        if del_match:
            deletions = int(del_match.group(1))

    return DiffSummary(
        files_changed=unstaged_files,
        staged_files=staged_files,
        insertions=insertions,
        deletions=deletions,
    )


# =============================================================================
# High-Level Functions
# =============================================================================


def capture_git_context(path: Path | None = None, recent_count: int = 3) -> GitContext | None:
    """Capture current git state for storage.

    Args:
        path: Repository path
        recent_count: Number of recent commits to include

    Returns:
        GitContext or None if not a git repo
    """
    if not is_git_repo(path):
        return None

    return GitContext(
        branch=get_branch(path),
        commit=get_commit(path),
        dirty=is_dirty(path),
        recent_commits=get_recent_commits(path, recent_count),
    )


def check_file_changed(
    file_path: str,
    since_commit: str,
    repo_path: Path | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Check if a file has changed since a commit.

    Args:
        file_path: Relative path to file
        since_commit: Commit SHA when the reference was created
        repo_path: Repository path

    Returns:
        (changed: bool, commits: tuple of commit descriptions that touched the file)
    """
    if not since_commit:
        return False, ()

    commits = get_file_commits_since(file_path, since_commit, repo_path)
    return bool(commits), commits


def check_index_freshness(
    indexed_at_commit: str,
    repo_path: Path | None = None,
) -> tuple[bool, int, tuple[str, ...]]:
    """Check if code index is behind current HEAD.

    Args:
        indexed_at_commit: Commit SHA when index was last built
        repo_path: Repository path

    Returns:
        (stale: bool, files_changed: int, changed_files: tuple)
    """
    if not indexed_at_commit:
        return False, 0, ()

    current = get_commit(repo_path)
    if current == indexed_at_commit:
        return False, 0, ()

    changed = get_changed_files_since(indexed_at_commit, repo_path)
    return bool(changed), len(changed), changed


# =============================================================================
# Git Versioning for Sage Storage (v4.0)
# =============================================================================


@dataclass(frozen=True)
class SageCommit:
    """A Sage-related git commit."""

    sha: str  # Short SHA
    message: str  # Commit message
    timestamp: str  # ISO timestamp
    change_type: str  # checkpoint, knowledge, failure
    item_id: str  # Item ID from message


def commit_sage_change(
    file_path: Path,
    change_type: str,
    item_id: str,
    repo_path: Path | None = None,
) -> bool:
    """Commit a Sage storage change to git.

    Creates a commit with message format: "sage: {change_type} {item_id}"
    Only commits files within .sage/ subdirectory.

    Args:
        file_path: Path to the changed file
        change_type: Type of change (checkpoint, knowledge, failure)
        item_id: ID of the item being saved
        repo_path: Repository path

    Returns:
        True if commit was created, False on failure

    Note:
        Uses --no-verify to skip hooks for speed.
        Never auto-pushes (local only).
    """
    if not is_git_repo(repo_path):
        logger.debug("Not a git repo, skipping sage commit")
        return False

    # Security: Ensure file is within .sage/ directory
    try:
        file_path = file_path.resolve()
        if ".sage" not in str(file_path):
            logger.warning(f"Refusing to commit non-.sage file: {file_path}")
            return False
    except Exception:
        return False

    # Stage the file
    # Note: If .sage/ is in .gitignore, this will fail silently.
    # Users must remove .sage/ from .gitignore to enable git versioning.
    stage_result = _run_git(["add", str(file_path)], cwd=repo_path)
    if stage_result is None:
        logger.debug(f"Failed to stage file: {file_path}")
        return False

    # Commit with sage prefix
    message = f"sage: {change_type} {item_id}"
    commit_result = _run_git(
        ["commit", "-m", message, "--no-verify"],
        cwd=repo_path,
    )

    if commit_result is not None:
        logger.debug(f"Created sage commit: {message}")
        return True

    # Check if there was nothing to commit (file unchanged)
    status = _run_git(["status", "--porcelain", str(file_path)], cwd=repo_path)
    if not status:
        logger.debug("File unchanged, no commit needed")
        return True  # Not an error

    logger.debug(f"Failed to commit: {message}")
    return False


def get_sage_history(
    repo_path: Path | None = None,
    limit: int = 20,
) -> list[SageCommit]:
    """Get history of Sage-related commits.

    Filters git log for commits with "sage:" prefix.

    Args:
        repo_path: Repository path
        limit: Maximum commits to return

    Returns:
        List of SageCommit objects, most recent first
    """
    output = _run_git(
        ["log", f"-{limit}", "--oneline", "--grep=^sage:", "--format=%h|%s|%aI"],
        cwd=repo_path,
    )

    if not output:
        return []

    commits = []
    for line in output.split("\n"):
        if "|" not in line:
            continue

        parts = line.split("|", 2)
        if len(parts) != 3:
            continue

        sha, message, timestamp = parts

        # Parse message: "sage: {type} {id}"
        if not message.startswith("sage: "):
            continue

        rest = message[6:]  # Remove "sage: " prefix
        parts = rest.split(" ", 1)
        change_type = parts[0] if parts else "unknown"
        item_id = parts[1] if len(parts) > 1 else ""

        commits.append(
            SageCommit(
                sha=sha,
                message=message,
                timestamp=timestamp,
                change_type=change_type,
                item_id=item_id,
            )
        )

    return commits


def is_sage_repo(project_path: Path | None = None) -> bool:
    """Check if path is a git repo with .sage directory.

    Args:
        project_path: Repository path

    Returns:
        True if both git repo and .sage/ exists
    """
    if not is_git_repo(project_path):
        return False

    if project_path:
        return (project_path / ".sage").exists()

    from sage.config import detect_project_root

    detected = detect_project_root()
    if detected:
        return (detected / ".sage").exists()

    return False
