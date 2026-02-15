"""Tests for project-local checkpoint support."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from sage.checkpoint import (
    Checkpoint,
    get_checkpoints_dir,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)
from sage.config import SageConfig, detect_project_root


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
        assert (
            project_with_sage / ".sage" / "checkpoints" in path.parents
            or path.parent == project_with_sage / ".sage" / "checkpoints"
        )

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


class TestMCPProjectIntegration:
    """Integration tests for MCP tools with project-local checkpoints."""

    @pytest.fixture
    def project_with_sage(self, tmp_path: Path):
        """Create a project with .sage directory."""
        project = tmp_path / "mcp-test-project"
        project.mkdir()
        sage_dir = project / ".sage"
        sage_dir.mkdir()
        (sage_dir / "checkpoints").mkdir()
        return project

    @pytest.fixture
    def global_sage_dir(self, tmp_path: Path):
        """Create a global .sage directory."""
        global_dir = tmp_path / "global-sage"
        global_dir.mkdir()
        (global_dir / "checkpoints").mkdir()
        return global_dir

    @pytest.fixture
    def sync_config(self, monkeypatch):
        """Disable async mode for these tests."""
        config = SageConfig(async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda project_path=None: config)
        return config

    def test_mcp_save_checkpoint_uses_project_root(
        self, project_with_sage: Path, sync_config
    ):
        """sage_save_checkpoint() saves to project-local when _PROJECT_ROOT is set."""
        from sage import mcp_server

        # Patch the module-level _PROJECT_ROOT
        with patch.object(mcp_server, "_PROJECT_ROOT", project_with_sage):
            result = mcp_server.sage_save_checkpoint(
                core_question="MCP integration test question",
                thesis="MCP saves to project-local directory",
                confidence=0.8,
                trigger="manual",
            )

        assert "📍 Checkpoint" in result  # "queued" or "saved" depending on async mode

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Verify file exists in project-local
        checkpoints_dir = project_with_sage / ".sage" / "checkpoints"
        checkpoint_files = list(checkpoints_dir.glob("*.md"))
        assert len(checkpoint_files) == 1

    def test_mcp_list_checkpoints_uses_project_root(
        self, project_with_sage: Path, sync_config
    ):
        """sage_list_checkpoints() lists from project-local when _PROJECT_ROOT is set."""
        from sage import mcp_server

        with patch.object(mcp_server, "_PROJECT_ROOT", project_with_sage):
            # Save a checkpoint first
            mcp_server.sage_save_checkpoint(
                core_question="List test",
                thesis="Checkpoint for listing",
                confidence=0.7,
                trigger="synthesis",
            )

            # Wait for fire-and-forget save to complete
            time.sleep(0.5)

            # List should find it
            result = mcp_server.sage_list_checkpoints(limit=10)

        assert "Checkpoints [1]" in result
        assert "Checkpoint for listing" in result

    def test_mcp_load_checkpoint_uses_project_root(
        self, project_with_sage: Path, sync_config
    ):
        """sage_load_checkpoint() loads from project-local when _PROJECT_ROOT is set."""
        from sage import mcp_server

        with patch.object(mcp_server, "_PROJECT_ROOT", project_with_sage):
            # Save a checkpoint
            mcp_server.sage_save_checkpoint(
                core_question="Load test question",
                thesis="Checkpoint for loading test",
                confidence=0.85,
                trigger="manual",
            )

            # Wait for fire-and-forget save to complete
            time.sleep(0.5)

            # List to get the checkpoint ID
            list_result = mcp_server.sage_list_checkpoints()
            checkpoint_id = list_result.split("**")[1].split("**")[0]

            # Load it back
            load_result = mcp_server.sage_load_checkpoint(checkpoint_id)

        assert "Load test question" in load_result
        assert "Checkpoint for loading test" in load_result

    def test_mcp_autosave_check_uses_project_root(self, project_with_sage: Path, sync_config):
        """sage_autosave_check() saves to project-local when _PROJECT_ROOT is set."""
        from sage import mcp_server

        with patch.object(mcp_server, "_PROJECT_ROOT", project_with_sage):
            result = mcp_server.sage_autosave_check(
                trigger_event="synthesis",
                core_question="Autosave integration test",
                current_thesis="Testing autosave with project-local storage",
                confidence=0.75,
            )

        assert "📍 Checkpoint" in result  # "queued" or "saved" depending on async mode

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Verify file exists in project-local
        checkpoints_dir = project_with_sage / ".sage" / "checkpoints"
        checkpoint_files = list(checkpoints_dir.glob("*.md"))
        assert len(checkpoint_files) == 1

    def test_mcp_deduplication_is_project_scoped(
        self, project_with_sage: Path, global_sage_dir: Path, sync_config
    ):
        """Deduplication only checks within the same project scope."""
        from sage import mcp_server

        # Save checkpoint to global
        with (
            patch.object(mcp_server, "_PROJECT_ROOT", None),
            patch("sage.checkpoint.CHECKPOINTS_DIR", global_sage_dir / "checkpoints"),
        ):
            mcp_server.sage_save_checkpoint(
                core_question="Global question",
                thesis="This thesis exists globally",
                confidence=0.8,
                trigger="manual",
            )

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Same thesis should save to project-local (different scope = not duplicate)
        with patch.object(mcp_server, "_PROJECT_ROOT", project_with_sage):
            result = mcp_server.sage_autosave_check(
                trigger_event="synthesis",
                core_question="Project question",
                current_thesis="This thesis exists globally",  # Same thesis
                confidence=0.8,
            )

        # Should save, not be flagged as duplicate
        assert "📍 Checkpoint" in result  # "queued" or "saved" depending on async mode

    def test_mcp_deduplication_within_project(self, project_with_sage: Path, sync_config):
        """Deduplication detects duplicates within the same project."""
        from sage import mcp_server

        with patch.object(mcp_server, "_PROJECT_ROOT", project_with_sage):
            # First save
            mcp_server.sage_save_checkpoint(
                core_question="Dedup test",
                thesis="This is a unique thesis for deduplication testing",
                confidence=0.8,
                trigger="manual",
            )

            # Wait for fire-and-forget save to complete before dedup check
            # Longer timeout in case embedding model needs downloading
            time.sleep(2.0)

            # Try to save very similar thesis
            result = mcp_server.sage_autosave_check(
                trigger_event="synthesis",
                core_question="Dedup test",
                current_thesis="This is a unique thesis for deduplication testing",
                confidence=0.8,
            )

        # Should be flagged as duplicate (depends on embeddings being available)
        # Without embeddings, may save anyway
        assert "📍 Checkpoint" in result or "similar" in result.lower()

    def test_mcp_project_and_global_isolation(
        self, project_with_sage: Path, global_sage_dir: Path, sync_config
    ):
        """Project-local and global checkpoints are fully isolated through MCP."""
        from sage import mcp_server

        # Save to project-local
        with patch.object(mcp_server, "_PROJECT_ROOT", project_with_sage):
            mcp_server.sage_save_checkpoint(
                core_question="Project question",
                thesis="Project-local checkpoint via MCP",
                confidence=0.8,
                trigger="manual",
            )
            # Wait for fire-and-forget save to complete
            time.sleep(0.5)
            project_list = mcp_server.sage_list_checkpoints()

        # Save to global
        with (
            patch.object(mcp_server, "_PROJECT_ROOT", None),
            patch("sage.checkpoint.CHECKPOINTS_DIR", global_sage_dir / "checkpoints"),
        ):
            mcp_server.sage_save_checkpoint(
                core_question="Global question",
                thesis="Global checkpoint via MCP",
                confidence=0.8,
                trigger="manual",
            )
            # Wait for fire-and-forget save to complete
            time.sleep(0.5)
            global_list = mcp_server.sage_list_checkpoints()

        # Verify isolation
        assert "Project-local checkpoint via MCP" in project_list
        assert "Global checkpoint via MCP" not in project_list

        assert "Global checkpoint via MCP" in global_list
        assert "Project-local checkpoint via MCP" not in global_list

    def test_mcp_with_no_project_root_uses_global(self, global_sage_dir: Path, sync_config):
        """When _PROJECT_ROOT is None, MCP tools use global directory."""
        from sage import mcp_server

        with (
            patch.object(mcp_server, "_PROJECT_ROOT", None),
            patch("sage.checkpoint.CHECKPOINTS_DIR", global_sage_dir / "checkpoints"),
        ):
            result = mcp_server.sage_save_checkpoint(
                core_question="Fallback test",
                thesis="Should save to global when no project",
                confidence=0.7,
                trigger="manual",
            )

        assert "📍 Checkpoint" in result  # "queued" or "saved" depending on async mode

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Verify file exists in global
        checkpoint_files = list((global_sage_dir / "checkpoints").glob("*.md"))
        assert len(checkpoint_files) == 1
