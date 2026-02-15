"""Tests for git versioning (v4.0).

Tests the git commit functionality for checkpoint/knowledge saves.
"""

import pytest
import subprocess
from pathlib import Path

from sage.git import (
    commit_sage_change,
    get_sage_history,
    is_sage_repo,
    SageCommit,
)


def _init_git_repo(path: Path) -> bool:
    """Initialize a git repo at the given path."""
    try:
        subprocess.run(
            ["git", "init"],
            cwd=path,
            capture_output=True,
            check=True,
        )
        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=path,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=path,
            capture_output=True,
        )
        # Create initial commit
        (path / "README.md").write_text("Test repo")
        subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=path,
            capture_output=True,
        )
        return True
    except Exception:
        return False


class TestCommitSageChange:
    """Tests for commit_sage_change()."""

    def test_commits_sage_file(self, tmp_path):
        """Should commit a file within .sage/ directory."""
        if not _init_git_repo(tmp_path):
            pytest.skip("Git not available")

        # Create .sage directory and file
        sage_dir = tmp_path / ".sage" / "checkpoints"
        sage_dir.mkdir(parents=True)
        test_file = sage_dir / "test-checkpoint.md"
        test_file.write_text("Test content")

        result = commit_sage_change(
            file_path=test_file,
            change_type="checkpoint",
            item_id="test-checkpoint",
            repo_path=tmp_path,
        )

        assert result is True

        # Verify commit was created
        log = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert "sage: checkpoint test-checkpoint" in log.stdout

    def test_refuses_non_sage_file(self, tmp_path):
        """Should refuse to commit files outside .sage/ directory."""
        if not _init_git_repo(tmp_path):
            pytest.skip("Git not available")

        # Create file outside .sage/
        test_file = tmp_path / "outside.txt"
        test_file.write_text("Test content")

        result = commit_sage_change(
            file_path=test_file,
            change_type="checkpoint",
            item_id="test",
            repo_path=tmp_path,
        )

        assert result is False

    def test_returns_false_for_non_repo(self, tmp_path):
        """Should return False if not a git repo."""
        # Create .sage directory and file without git
        sage_dir = tmp_path / ".sage" / "checkpoints"
        sage_dir.mkdir(parents=True)
        test_file = sage_dir / "test.md"
        test_file.write_text("Test")

        result = commit_sage_change(
            file_path=test_file,
            change_type="checkpoint",
            item_id="test",
            repo_path=tmp_path,
        )

        assert result is False

    def test_uses_no_verify(self, tmp_path):
        """Should skip git hooks with --no-verify."""
        if not _init_git_repo(tmp_path):
            pytest.skip("Git not available")

        # Create a pre-commit hook that would fail
        hooks_dir = tmp_path / ".git" / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        pre_commit = hooks_dir / "pre-commit"
        pre_commit.write_text("#!/bin/sh\nexit 1")
        pre_commit.chmod(0o755)

        # Create .sage file
        sage_dir = tmp_path / ".sage" / "checkpoints"
        sage_dir.mkdir(parents=True)
        test_file = sage_dir / "test.md"
        test_file.write_text("Test")

        # Should succeed despite failing hook (due to --no-verify)
        result = commit_sage_change(
            file_path=test_file,
            change_type="checkpoint",
            item_id="test",
            repo_path=tmp_path,
        )

        assert result is True


class TestGetSageHistory:
    """Tests for get_sage_history()."""

    def test_returns_sage_commits(self, tmp_path):
        """Should return only sage-prefixed commits."""
        if not _init_git_repo(tmp_path):
            pytest.skip("Git not available")

        # Create .sage file and commit
        sage_dir = tmp_path / ".sage" / "checkpoints"
        sage_dir.mkdir(parents=True)
        test_file = sage_dir / "test.md"
        test_file.write_text("Test 1")
        commit_sage_change(test_file, "checkpoint", "cp-1", tmp_path)

        # Create another file
        test_file.write_text("Test 2")
        commit_sage_change(test_file, "knowledge", "kn-1", tmp_path)

        history = get_sage_history(tmp_path)

        assert len(history) == 2
        assert all(isinstance(c, SageCommit) for c in history)

        # Most recent first
        assert history[0].item_id == "kn-1"
        assert history[0].change_type == "knowledge"
        assert history[1].item_id == "cp-1"
        assert history[1].change_type == "checkpoint"

    def test_respects_limit(self, tmp_path):
        """Should respect limit parameter."""
        if not _init_git_repo(tmp_path):
            pytest.skip("Git not available")

        sage_dir = tmp_path / ".sage" / "checkpoints"
        sage_dir.mkdir(parents=True)
        test_file = sage_dir / "test.md"

        for i in range(5):
            test_file.write_text(f"Test {i}")
            commit_sage_change(test_file, "checkpoint", f"cp-{i}", tmp_path)

        history = get_sage_history(tmp_path, limit=2)
        assert len(history) == 2

    def test_returns_empty_for_non_repo(self, tmp_path):
        """Should return empty list if not a git repo."""
        history = get_sage_history(tmp_path)
        assert history == []

    def test_filters_non_sage_commits(self, tmp_path):
        """Should not include non-sage commits."""
        if not _init_git_repo(tmp_path):
            pytest.skip("Git not available")

        # Create regular commit
        (tmp_path / "file.txt").write_text("Regular file")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Regular commit"],
            cwd=tmp_path,
            capture_output=True,
        )

        # Create sage commit
        sage_dir = tmp_path / ".sage" / "checkpoints"
        sage_dir.mkdir(parents=True)
        test_file = sage_dir / "test.md"
        test_file.write_text("Sage content")
        commit_sage_change(test_file, "checkpoint", "test", tmp_path)

        history = get_sage_history(tmp_path)

        # Should only have the sage commit
        assert len(history) == 1
        assert history[0].item_id == "test"


class TestIsSageRepo:
    """Tests for is_sage_repo()."""

    def test_returns_true_for_repo_with_sage(self, tmp_path):
        """Should return True for git repo with .sage/ directory."""
        if not _init_git_repo(tmp_path):
            pytest.skip("Git not available")

        (tmp_path / ".sage").mkdir()

        assert is_sage_repo(tmp_path) is True

    def test_returns_false_without_sage(self, tmp_path):
        """Should return False for git repo without .sage/."""
        if not _init_git_repo(tmp_path):
            pytest.skip("Git not available")

        assert is_sage_repo(tmp_path) is False

    def test_returns_false_for_non_repo(self, tmp_path):
        """Should return False if not a git repo."""
        (tmp_path / ".sage").mkdir()

        assert is_sage_repo(tmp_path) is False


class TestSageCommitDataclass:
    """Tests for SageCommit dataclass."""

    def test_creates_commit(self):
        """Should create SageCommit with all fields."""
        commit = SageCommit(
            sha="abc123",
            message="sage: checkpoint test-cp",
            timestamp="2026-01-01T00:00:00",
            change_type="checkpoint",
            item_id="test-cp",
        )

        assert commit.sha == "abc123"
        assert commit.change_type == "checkpoint"
        assert commit.item_id == "test-cp"
