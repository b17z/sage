"""Tests for project-local checkpoint support."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.config import detect_project_root
from sage.checkpoint import (
    Checkpoint,
    get_checkpoints_dir,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)


class TestDetectProjectRoot:
    """Tests for detect_project_root()."""

    def test_detects_sage_directory(self, tmp_path: Path):
        """Finds project root when .sage directory exists."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        (project_dir / ".sage").mkdir()

        # Nested subdirectory
        subdir = project_dir / "src" / "components"
        subdir.mkdir(parents=True)

        result = detect_project_root(start_path=subdir)

        assert result == project_dir

    def test_detects_git_directory(self, tmp_path: Path):
        """Finds project root when .git directory exists."""
        project_dir = tmp_path / "my-repo"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        subdir = project_dir / "lib" / "utils"
        subdir.mkdir(parents=True)

        result = detect_project_root(start_path=subdir)

        assert result == project_dir

    def test_sage_takes_priority_over_git(self, tmp_path: Path):
        """Prefers .sage over .git when both exist at same level."""
        project_dir = tmp_path / "my-project"
        project_dir.mkdir()
        (project_dir / ".sage").mkdir()
        (project_dir / ".git").mkdir()

        result = detect_project_root(start_path=project_dir)

        assert result == project_dir

    def test_returns_none_when_no_markers(self, tmp_path: Path):
        """Returns None when no .sage or .git found."""
        orphan_dir = tmp_path / "orphan"
        orphan_dir.mkdir()

        result = detect_project_root(start_path=orphan_dir)

        assert result is None

    def test_uses_cwd_when_no_start_path(self, tmp_path: Path):
        """Uses current working directory when start_path is None."""
        project_dir = tmp_path / "cwd-project"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()

        with patch("sage.config.Path.cwd", return_value=project_dir):
            result = detect_project_root()

        assert result == project_dir


class TestProjectLocalCheckpoints:
    """Tests for project-local checkpoint storage."""

    @pytest.fixture
    def project_with_sage(self, tmp_path: Path):
        """Create a project with .sage directory."""
        project = tmp_path / "test-project"
        project.mkdir()
        sage_dir = project / ".sage"
        sage_dir.mkdir()
        (sage_dir / "checkpoints").mkdir()
        return project

    @pytest.fixture
    def global_checkpoints_dir(self, tmp_path: Path):
        """Create a global checkpoints directory."""
        global_dir = tmp_path / "global-sage" / "checkpoints"
        global_dir.mkdir(parents=True)
        return global_dir.parent

    def test_get_checkpoints_dir_uses_project_local(self, project_with_sage: Path):
        """get_checkpoints_dir() returns project-local path when available."""
        result = get_checkpoints_dir(project_path=project_with_sage)

        assert result == project_with_sage / ".sage" / "checkpoints"

    def test_get_checkpoints_dir_falls_back_to_global(
        self, tmp_path: Path, global_checkpoints_dir: Path
    ):
        """get_checkpoints_dir() falls back to global when no project."""
        with patch("sage.checkpoint.CHECKPOINTS_DIR", global_checkpoints_dir / "checkpoints"):
            result = get_checkpoints_dir(project_path=None)

        assert result == global_checkpoints_dir / "checkpoints"

    def test_save_to_project_local(self, project_with_sage: Path):
        """save_checkpoint() saves to project-local directory."""
        cp = Checkpoint(
            id="2026-01-13T10-00-00_test",
            ts="2026-01-13T10:00:00+00:00",
            trigger="manual",
            core_question="Test question",
            thesis="Test thesis",
            confidence=0.5,
        )

        path = save_checkpoint(cp, project_path=project_with_sage)

        assert path.exists()
        assert project_with_sage / ".sage" / "checkpoints" in path.parents or \
               path.parent == project_with_sage / ".sage" / "checkpoints"

    def test_load_from_project_local(self, project_with_sage: Path):
        """load_checkpoint() loads from project-local directory."""
        cp = Checkpoint(
            id="2026-01-13T11-00-00_local-test",
            ts="2026-01-13T11:00:00+00:00",
            trigger="synthesis",
            core_question="Local question",
            thesis="Local thesis",
            confidence=0.75,
        )

        save_checkpoint(cp, project_path=project_with_sage)
        loaded = load_checkpoint(cp.id, project_path=project_with_sage)

        assert loaded is not None
        assert loaded.id == cp.id
        assert loaded.thesis == "Local thesis"

    def test_list_from_project_local(self, project_with_sage: Path):
        """list_checkpoints() lists from project-local directory."""
        for i in range(3):
            cp = Checkpoint(
                id=f"2026-01-13T{10+i:02d}-00-00_cp{i}",
                ts=f"2026-01-13T{10+i:02d}:00:00+00:00",
                trigger="manual",
                core_question=f"Q{i}",
                thesis=f"T{i}",
                confidence=0.5,
            )
            save_checkpoint(cp, project_path=project_with_sage)

        checkpoints = list_checkpoints(project_path=project_with_sage)

        assert len(checkpoints) == 3

    def test_project_and_global_are_isolated(
        self, project_with_sage: Path, global_checkpoints_dir: Path
    ):
        """Project-local and global checkpoints don't interfere."""
        # Save to project-local
        local_cp = Checkpoint(
            id="2026-01-13T10-00-00_local",
            ts="2026-01-13T10:00:00+00:00",
            trigger="manual",
            core_question="Local",
            thesis="Local checkpoint",
            confidence=0.5,
        )
        save_checkpoint(local_cp, project_path=project_with_sage)

        # Save to global (with patched path)
        global_cp = Checkpoint(
            id="2026-01-13T10-00-00_global",
            ts="2026-01-13T10:00:00+00:00",
            trigger="manual",
            core_question="Global",
            thesis="Global checkpoint",
            confidence=0.5,
        )
        with patch("sage.checkpoint.CHECKPOINTS_DIR", global_checkpoints_dir / "checkpoints"):
            save_checkpoint(global_cp, project_path=None)

        # List project-local - should only see local
        local_list = list_checkpoints(project_path=project_with_sage)
        assert len(local_list) == 1
        assert local_list[0].thesis == "Local checkpoint"

        # List global - should only see global
        with patch("sage.checkpoint.CHECKPOINTS_DIR", global_checkpoints_dir / "checkpoints"):
            global_list = list_checkpoints(project_path=None)
        assert len(global_list) == 1
        assert global_list[0].thesis == "Global checkpoint"
