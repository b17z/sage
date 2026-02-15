"""Tests for sage.git module.

Tests git integration functionality including:
- GitContext dataclass
- DiffSummary dataclass
- Git CLI helpers
- Context capture
- Staleness checking
"""

import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sage.git import (
    GitContext,
    DiffSummary,
    is_git_repo,
    get_branch,
    get_commit,
    is_dirty,
    get_recent_commits,
    get_changed_files_since,
    get_file_commits_since,
    get_diff_summary,
    capture_git_context,
    check_file_changed,
    check_index_freshness,
)


# =============================================================================
# GitContext Tests
# =============================================================================


class TestGitContext:
    """Tests for GitContext dataclass."""

    def test_git_context_is_frozen(self):
        """GitContext should be immutable."""
        ctx = GitContext(
            branch="main",
            commit="abc1234",
            dirty=False,
            recent_commits=("commit 1", "commit 2"),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            ctx.branch = "other"

    def test_git_context_to_dict(self):
        """GitContext should serialize to dict correctly."""
        ctx = GitContext(
            branch="feature/test",
            commit="def5678",
            dirty=True,
            recent_commits=("abc1234 first commit", "def5678 second commit"),
        )
        d = ctx.to_dict()
        assert d["branch"] == "feature/test"
        assert d["commit"] == "def5678"
        assert d["dirty"] is True
        assert d["recent_commits"] == ["abc1234 first commit", "def5678 second commit"]

    def test_git_context_from_dict(self):
        """GitContext should deserialize from dict correctly."""
        data = {
            "branch": "main",
            "commit": "123abc",
            "dirty": False,
            "recent_commits": ["commit 1"],
        }
        ctx = GitContext.from_dict(data)
        assert ctx.branch == "main"
        assert ctx.commit == "123abc"
        assert ctx.dirty is False
        assert ctx.recent_commits == ("commit 1",)

    def test_git_context_from_dict_defaults(self):
        """GitContext should handle missing fields with defaults."""
        data = {}
        ctx = GitContext.from_dict(data)
        assert ctx.branch == ""
        assert ctx.commit == ""
        assert ctx.dirty is False
        assert ctx.recent_commits == ()

    def test_git_context_roundtrip(self):
        """GitContext should survive serialization roundtrip."""
        original = GitContext(
            branch="develop",
            commit="aaa111",
            dirty=True,
            recent_commits=("a", "b", "c"),
        )
        restored = GitContext.from_dict(original.to_dict())
        assert restored == original


# =============================================================================
# DiffSummary Tests
# =============================================================================


class TestDiffSummary:
    """Tests for DiffSummary dataclass."""

    def test_diff_summary_is_frozen(self):
        """DiffSummary should be immutable."""
        ds = DiffSummary(
            files_changed=("file1.py",),
            staged_files=(),
            insertions=10,
            deletions=5,
        )
        with pytest.raises(Exception):
            ds.insertions = 20

    def test_diff_summary_summary_property(self):
        """DiffSummary.summary should format correctly."""
        ds = DiffSummary(
            files_changed=("a.py", "b.py"),
            staged_files=("c.py",),
            insertions=42,
            deletions=17,
        )
        assert ds.summary == "+42 -17 across 3 files"

    def test_diff_summary_no_changes(self):
        """DiffSummary.summary should handle no changes."""
        ds = DiffSummary(
            files_changed=(),
            staged_files=(),
            insertions=0,
            deletions=0,
        )
        assert ds.summary == "no changes"

    def test_diff_summary_to_dict(self):
        """DiffSummary should serialize to dict."""
        ds = DiffSummary(
            files_changed=("x.py",),
            staged_files=("y.py",),
            insertions=100,
            deletions=50,
        )
        d = ds.to_dict()
        assert d["files_changed"] == ["x.py"]
        assert d["staged_files"] == ["y.py"]
        assert d["insertions"] == 100
        assert d["deletions"] == 50

    def test_diff_summary_from_dict(self):
        """DiffSummary should deserialize from dict."""
        data = {
            "files_changed": ["a.py", "b.py"],
            "staged_files": [],
            "insertions": 20,
            "deletions": 10,
        }
        ds = DiffSummary.from_dict(data)
        assert ds.files_changed == ("a.py", "b.py")
        assert ds.staged_files == ()
        assert ds.insertions == 20
        assert ds.deletions == 10


# =============================================================================
# Git CLI Helper Tests (mocked)
# =============================================================================


class TestGitCliHelpers:
    """Tests for git CLI helper functions."""

    @patch("sage.git._run_git")
    def test_is_git_repo_true(self, mock_run):
        """is_git_repo should return True for git repos."""
        mock_run.return_value = ".git"
        assert is_git_repo() is True
        mock_run.assert_called_once_with(["rev-parse", "--git-dir"], cwd=None)

    @patch("sage.git._run_git")
    def test_is_git_repo_false(self, mock_run):
        """is_git_repo should return False for non-git directories."""
        mock_run.return_value = None
        assert is_git_repo() is False

    @patch("sage.git._run_git")
    def test_get_branch_normal(self, mock_run):
        """get_branch should return branch name."""
        mock_run.return_value = "main"
        assert get_branch() == "main"

    @patch("sage.git._run_git")
    def test_get_branch_detached(self, mock_run):
        """get_branch should handle detached HEAD."""
        # First call (symbolic-ref) fails, second (describe) succeeds
        mock_run.side_effect = [None, "v1.2.3"]
        assert get_branch() == "v1.2.3"

    @patch("sage.git._run_git")
    def test_get_commit_short(self, mock_run):
        """get_commit should return short SHA by default."""
        mock_run.return_value = "abc1234"
        assert get_commit() == "abc1234"
        mock_run.assert_called_with(["rev-parse", "--short", "HEAD"], cwd=None)

    @patch("sage.git._run_git")
    def test_get_commit_full(self, mock_run):
        """get_commit(short=False) should return full SHA."""
        mock_run.return_value = "abc1234def5678"
        assert get_commit(short=False) == "abc1234def5678"
        mock_run.assert_called_with(["rev-parse", "HEAD"], cwd=None)

    @patch("sage.git._run_git")
    def test_is_dirty_true(self, mock_run):
        """is_dirty should return True when there are changes."""
        mock_run.return_value = " M file.py"
        assert is_dirty() is True

    @patch("sage.git._run_git")
    def test_is_dirty_false(self, mock_run):
        """is_dirty should return False for clean working tree."""
        mock_run.return_value = ""
        assert is_dirty() is False

    @patch("sage.git._run_git")
    def test_get_recent_commits(self, mock_run):
        """get_recent_commits should return commit messages."""
        mock_run.return_value = "abc1234 First\ndef5678 Second"
        commits = get_recent_commits(count=2)
        assert commits == ("abc1234 First", "def5678 Second")

    @patch("sage.git._run_git")
    def test_get_recent_commits_empty(self, mock_run):
        """get_recent_commits should handle empty repo."""
        mock_run.return_value = None
        commits = get_recent_commits()
        assert commits == ()

    @patch("sage.git._run_git")
    def test_get_changed_files_since(self, mock_run):
        """get_changed_files_since should return file paths."""
        mock_run.return_value = "src/a.py\nsrc/b.py"
        files = get_changed_files_since("abc1234")
        assert files == ("src/a.py", "src/b.py")

    @patch("sage.git._run_git")
    def test_get_file_commits_since(self, mock_run):
        """get_file_commits_since should return commits touching file."""
        mock_run.return_value = "def5678 Changed file\nghi9012 Also changed"
        commits = get_file_commits_since("file.py", "abc1234")
        assert len(commits) == 2


# =============================================================================
# High-Level Function Tests
# =============================================================================


class TestCaptureGitContext:
    """Tests for capture_git_context function."""

    @patch("sage.git.is_git_repo")
    def test_capture_returns_none_for_non_repo(self, mock_is_repo):
        """capture_git_context should return None for non-git directories."""
        mock_is_repo.return_value = False
        assert capture_git_context() is None

    @patch("sage.git.get_recent_commits")
    @patch("sage.git.is_dirty")
    @patch("sage.git.get_commit")
    @patch("sage.git.get_branch")
    @patch("sage.git.is_git_repo")
    def test_capture_returns_context(
        self, mock_is_repo, mock_branch, mock_commit, mock_dirty, mock_recent
    ):
        """capture_git_context should return GitContext for git repos."""
        mock_is_repo.return_value = True
        mock_branch.return_value = "main"
        mock_commit.return_value = "abc1234"
        mock_dirty.return_value = True
        mock_recent.return_value = ("commit 1", "commit 2")

        ctx = capture_git_context()

        assert ctx is not None
        assert ctx.branch == "main"
        assert ctx.commit == "abc1234"
        assert ctx.dirty is True
        assert ctx.recent_commits == ("commit 1", "commit 2")


class TestCheckFilChanged:
    """Tests for check_file_changed function."""

    def test_check_empty_commit_returns_false(self):
        """check_file_changed should return False for empty commit."""
        changed, commits = check_file_changed("file.py", "")
        assert changed is False
        assert commits == ()

    @patch("sage.git.get_file_commits_since")
    def test_check_file_changed_true(self, mock_commits):
        """check_file_changed should detect changed files."""
        mock_commits.return_value = ("def5678 Changed file",)
        changed, commits = check_file_changed("file.py", "abc1234")
        assert changed is True
        assert commits == ("def5678 Changed file",)

    @patch("sage.git.get_file_commits_since")
    def test_check_file_changed_false(self, mock_commits):
        """check_file_changed should detect unchanged files."""
        mock_commits.return_value = ()
        changed, commits = check_file_changed("file.py", "abc1234")
        assert changed is False
        assert commits == ()


class TestCheckIndexFreshness:
    """Tests for check_index_freshness function."""

    def test_check_empty_commit_returns_false(self):
        """check_index_freshness should handle empty commit."""
        stale, count, files = check_index_freshness("")
        assert stale is False
        assert count == 0
        assert files == ()

    @patch("sage.git.get_changed_files_since")
    @patch("sage.git.get_commit")
    def test_check_same_commit_not_stale(self, mock_commit, mock_changed):
        """check_index_freshness should detect fresh index."""
        mock_commit.return_value = "abc1234"
        stale, count, files = check_index_freshness("abc1234")
        assert stale is False
        assert count == 0
        # get_changed_files_since shouldn't be called if commits match
        mock_changed.assert_not_called()

    @patch("sage.git.get_changed_files_since")
    @patch("sage.git.get_commit")
    def test_check_different_commit_with_changes_stale(self, mock_commit, mock_changed):
        """check_index_freshness should detect stale index."""
        mock_commit.return_value = "def5678"
        mock_changed.return_value = ("file1.py", "file2.py")
        stale, count, files = check_index_freshness("abc1234")
        assert stale is True
        assert count == 2
        assert files == ("file1.py", "file2.py")


class TestGetDiffSummary:
    """Tests for get_diff_summary function."""

    @patch("sage.git._run_git")
    def test_diff_summary_empty(self, mock_run):
        """get_diff_summary should handle no changes."""
        mock_run.return_value = ""
        ds = get_diff_summary()
        assert ds.files_changed == ()
        assert ds.staged_files == ()
        assert ds.insertions == 0
        assert ds.deletions == 0

    @patch("sage.git._run_git")
    def test_diff_summary_with_changes(self, mock_run):
        """get_diff_summary should parse changes correctly."""
        # Mock sequence: unstaged, staged, stats
        mock_run.side_effect = [
            "src/a.py\nsrc/b.py",  # unstaged
            "src/c.py",  # staged
            "3 files changed, 42 insertions(+), 17 deletions(-)",  # stats
        ]
        ds = get_diff_summary()
        assert ds.files_changed == ("src/a.py", "src/b.py")
        assert ds.staged_files == ("src/c.py",)
        assert ds.insertions == 42
        assert ds.deletions == 17


# =============================================================================
# Integration Tests (real git commands on test repo)
# =============================================================================


class TestGitIntegration:
    """Integration tests using real git commands on the sage repo."""

    def test_is_git_repo_on_sage(self):
        """Sage repo should be detected as git repo."""
        # This test runs in the sage repo
        assert is_git_repo(Path.cwd()) is True

    def test_get_branch_returns_string(self):
        """get_branch should return a non-empty string."""
        branch = get_branch(Path.cwd())
        assert isinstance(branch, str)
        assert len(branch) > 0

    def test_get_commit_returns_sha(self):
        """get_commit should return a valid short SHA."""
        commit = get_commit(Path.cwd())
        assert isinstance(commit, str)
        assert len(commit) == 7  # short SHA

    def test_get_recent_commits_returns_commits(self):
        """get_recent_commits should return commit strings."""
        commits = get_recent_commits(Path.cwd(), count=3)
        assert isinstance(commits, tuple)
        assert len(commits) <= 3
        if commits:
            # Each commit should have SHA and message
            assert " " in commits[0]

    def test_capture_git_context_returns_context(self):
        """capture_git_context should return valid context for sage repo."""
        ctx = capture_git_context(Path.cwd())
        assert ctx is not None
        assert isinstance(ctx, GitContext)
        assert ctx.branch != ""
        assert ctx.commit != ""
        assert isinstance(ctx.dirty, bool)
