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
        result = subprocess.run(
            ["git", *args],
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
