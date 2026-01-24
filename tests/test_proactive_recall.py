"""Tests for proactive knowledge recall feature."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_session_state():
    """Reset session injection state before each test."""
    from sage.mcp_server import _reset_session_state

    _reset_session_state()
    yield
    _reset_session_state()


class TestGetProjectContext:
    """Tests for _get_project_context helper function."""

    def test_returns_none_when_no_project_root(self):
        """Returns None when PROJECT_ROOT is None."""
        with patch("sage.mcp_server._PROJECT_ROOT", None):
            from sage.mcp_server import _get_project_context

            result = _get_project_context()

        # May still find git info, but should handle gracefully
        assert result is None or isinstance(result, str)

    def test_includes_directory_name(self, tmp_path):
        """Includes current directory name in context."""
        project_dir = tmp_path / "my-awesome-project"
        project_dir.mkdir()

        with patch("sage.mcp_server._PROJECT_ROOT", project_dir):
            from sage.mcp_server import _get_project_context

            result = _get_project_context()

        assert result is not None
        assert "my-awesome-project" in result

    def test_includes_git_repo_name(self, tmp_path):
        """Includes git remote repo name in context."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/user/cool-repo.git\n"

        with patch("sage.mcp_server._PROJECT_ROOT", project_dir):
            with patch("subprocess.run", return_value=mock_result):
                from sage.mcp_server import _get_project_context

                result = _get_project_context()

        assert result is not None
        assert "cool-repo" in result

    def test_includes_pyproject_name(self, tmp_path):
        """Includes package name from pyproject.toml."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        pyproject = project_dir / "pyproject.toml"
        pyproject.write_text('[project]\nname = "my-python-package"\nversion = "1.0.0"')

        with patch("sage.mcp_server._PROJECT_ROOT", project_dir):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                from sage.mcp_server import _get_project_context

                result = _get_project_context()

        assert result is not None
        assert "my-python-package" in result

    def test_includes_package_json_name(self, tmp_path):
        """Includes package name from package.json."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        pkg_json = project_dir / "package.json"
        pkg_json.write_text(json.dumps({"name": "my-node-package", "version": "1.0.0"}))

        with patch("sage.mcp_server._PROJECT_ROOT", project_dir):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                from sage.mcp_server import _get_project_context

                result = _get_project_context()

        assert result is not None
        assert "my-node-package" in result

    def test_handles_git_timeout_gracefully(self, tmp_path):
        """Handles git command timeout without crashing."""
        import subprocess

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("sage.mcp_server._PROJECT_ROOT", project_dir):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 2)):
                from sage.mcp_server import _get_project_context

                result = _get_project_context()

        # Should still return directory name at minimum
        assert result is not None
        assert "project" in result

    def test_deduplicates_signals(self, tmp_path):
        """Doesn't repeat the same signal multiple times."""
        project_dir = tmp_path / "sage"
        project_dir.mkdir()

        # Git remote also returns "sage"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/user/sage.git\n"

        with patch("sage.mcp_server._PROJECT_ROOT", project_dir):
            with patch("subprocess.run", return_value=mock_result):
                from sage.mcp_server import _get_project_context

                result = _get_project_context()

        assert result is not None
        # "sage" should only appear once
        assert result.count("sage") == 1


class TestGetProactiveRecall:
    """Tests for _get_proactive_recall helper function."""

    def test_returns_none_when_no_context(self):
        """Returns None when no project context available."""
        with patch("sage.mcp_server._get_project_context", return_value=None):
            from sage.mcp_server import _get_proactive_recall

            result = _get_proactive_recall()

        assert result is None

    def test_returns_none_when_no_knowledge_matches(self, tmp_path):
        """Returns None when no knowledge matches context."""
        mock_result = MagicMock()
        mock_result.count = 0
        mock_result.items = []

        with patch("sage.mcp_server._get_project_context", return_value="my-project"):
            with patch("sage.knowledge.recall_knowledge", return_value=mock_result):
                from sage.mcp_server import _get_proactive_recall

                result = _get_proactive_recall()

        assert result is None

    def test_returns_formatted_knowledge_when_matches(self, tmp_path):
        """Returns formatted knowledge when matches found."""
        mock_item = MagicMock()
        mock_item.id = "test-knowledge"
        mock_item.triggers.keywords = ["project", "testing"]
        mock_item.content = "This is important knowledge about the project."

        mock_result = MagicMock()
        mock_result.count = 1
        mock_result.items = [mock_item]

        with patch("sage.mcp_server._get_project_context", return_value="my-project"):
            with patch("sage.knowledge.recall_knowledge", return_value=mock_result):
                from sage.mcp_server import _get_proactive_recall

                result = _get_proactive_recall()

        assert result is not None
        assert "RECALLED KNOWLEDGE" in result
        assert "test-knowledge" in result
        assert "important knowledge" in result

    def test_includes_project_context_in_output(self, tmp_path):
        """Shows what context was used for recall."""
        mock_item = MagicMock()
        mock_item.id = "item"
        mock_item.triggers.keywords = ["kw"]
        mock_item.content = "content"

        mock_result = MagicMock()
        mock_result.count = 1
        mock_result.items = [mock_item]

        with patch("sage.mcp_server._get_project_context", return_value="awesome-project"):
            with patch("sage.knowledge.recall_knowledge", return_value=mock_result):
                from sage.mcp_server import _get_proactive_recall

                result = _get_proactive_recall()

        assert result is not None
        assert "awesome-project" in result


class TestSageHealthProactiveRecall:
    """Tests for proactive recall integration in sage_health."""

    def test_health_includes_proactive_recall(self):
        """sage_health includes proactive recall when knowledge matches."""
        mock_recall = "═══ RECALLED KNOWLEDGE ═══\nTest knowledge"

        with patch("sage.mcp_server._get_continuity_context", return_value=None):
            with patch("sage.mcp_server._get_proactive_recall", return_value=mock_recall):
                from sage.mcp_server import sage_health

                result = sage_health()

        assert "RECALLED KNOWLEDGE" in result
        assert "Test knowledge" in result

    def test_health_works_without_proactive_recall(self):
        """sage_health works when no proactive recall available."""
        with patch("sage.mcp_server._get_continuity_context", return_value=None):
            with patch("sage.mcp_server._get_proactive_recall", return_value=None):
                from sage.mcp_server import sage_health

                result = sage_health()

        assert "Sage Health Check" in result
        assert "RECALLED KNOWLEDGE" not in result

    def test_health_shows_both_continuity_and_recall(self):
        """sage_health shows both continuity and proactive recall."""
        mock_continuity = "═══ SESSION CONTINUITY ═══\nContinuity context"
        mock_recall = "═══ RECALLED KNOWLEDGE ═══\nRecalled knowledge"

        with patch("sage.mcp_server._get_continuity_context", return_value=mock_continuity):
            with patch("sage.mcp_server._get_proactive_recall", return_value=mock_recall):
                from sage.mcp_server import sage_health

                result = sage_health()

        assert "SESSION CONTINUITY" in result
        assert "RECALLED KNOWLEDGE" in result
        # Continuity should come first
        assert result.index("SESSION CONTINUITY") < result.index("RECALLED KNOWLEDGE")


class TestIntegration:
    """Integration tests for proactive recall."""

    def test_full_proactive_recall_flow(self, tmp_path):
        """Test full flow: project context -> recall -> inject."""
        # Create a project directory
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Mock the proactive recall to return something
        mock_recall = "═══ RECALLED KNOWLEDGE ═══\nTest knowledge for test-project"

        with patch("sage.mcp_server._PROJECT_ROOT", project_dir):
            with patch("sage.mcp_server._get_continuity_context", return_value=None):
                with patch("sage.mcp_server._get_proactive_recall", return_value=mock_recall):
                    from sage.mcp_server import sage_health

                    result = sage_health()

        # Should include the recalled knowledge
        assert "Sage Health Check" in result
        assert "RECALLED KNOWLEDGE" in result
        assert "test-project" in result
