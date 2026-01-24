"""Integration tests for sage skills CLI commands."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from sage.cli import main
from sage.default_skills import DEFAULT_SKILLS


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_skills_dir(tmp_path):
    """Create a temporary skills directory."""
    skills_dir = tmp_path / "skills" / "sage"
    skills_dir.mkdir(parents=True)
    return skills_dir


class TestSkillsInstall:
    """Tests for 'sage skills install' command."""

    def test_install_creates_skills(self, runner, tmp_path):
        """Install command creates all default skills."""
        skills_dir = tmp_path / "skills" / "sage"

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            with patch("sage.cli.console"):  # Suppress output
                result = runner.invoke(main, ["skills", "install"])

        assert result.exit_code == 0
        for skill in DEFAULT_SKILLS:
            skill_path = skills_dir / skill.name / "SKILL.md"
            assert skill_path.exists(), f"Missing {skill.name}"

    def test_install_shows_success_messages(self, runner, tmp_path):
        """Install command shows success messages."""
        skills_dir = tmp_path / "skills" / "sage"

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            result = runner.invoke(main, ["skills", "install"])

        assert result.exit_code == 0
        assert "sage-memory" in result.output
        assert "sage-research" in result.output
        assert "sage-session" in result.output

    def test_install_with_existing_skills(self, runner, tmp_path):
        """Install command doesn't overwrite without --force."""
        skills_dir = tmp_path / "skills" / "sage"
        skill_dir = skills_dir / "sage-memory"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("custom content")

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            result = runner.invoke(main, ["skills", "install"])

        assert result.exit_code == 0
        assert "already exists" in result.output
        # Verify content wasn't changed
        assert (skill_dir / "SKILL.md").read_text() == "custom content"

    def test_install_force_overwrites(self, runner, tmp_path):
        """Install --force overwrites existing skills."""
        skills_dir = tmp_path / "skills" / "sage"
        skill_dir = skills_dir / "sage-memory"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("custom content")

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            result = runner.invoke(main, ["skills", "install", "--force"])

        assert result.exit_code == 0
        # Verify content was replaced
        content = (skill_dir / "SKILL.md").read_text()
        assert "custom content" not in content
        assert "Background" in content  # From sage-memory template


class TestSkillsList:
    """Tests for 'sage skills list' command."""

    def test_list_empty(self, runner, tmp_path):
        """List command shows message when no skills."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path / "nonexistent"):
            result = runner.invoke(main, ["skills", "list"])

        assert result.exit_code == 0
        assert "No Sage skills" in result.output

    def test_list_shows_installed_skills(self, runner, tmp_path):
        """List command shows installed skills."""
        skills_dir = tmp_path / "skills" / "sage"

        # Install skills first
        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            runner.invoke(main, ["skills", "install"])
            result = runner.invoke(main, ["skills", "list"])

        assert result.exit_code == 0
        assert "sage-memory" in result.output
        assert "sage-research" in result.output
        assert "sage-session" in result.output

    def test_list_shows_versions(self, runner, tmp_path):
        """List command shows version information."""
        skills_dir = tmp_path / "skills" / "sage"

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            runner.invoke(main, ["skills", "install"])
            result = runner.invoke(main, ["skills", "list"])

        assert result.exit_code == 0
        assert "1.0.0" in result.output


class TestSkillsUpdate:
    """Tests for 'sage skills update' command."""

    def test_update_overwrites_all(self, runner, tmp_path):
        """Update command force-updates all skills."""
        skills_dir = tmp_path / "skills" / "sage"
        skill_dir = skills_dir / "sage-memory"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("old content")

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            result = runner.invoke(main, ["skills", "update"])

        assert result.exit_code == 0
        assert "Updated" in result.output or "sage-memory" in result.output
        # Verify all skills are now installed with latest content
        for skill in DEFAULT_SKILLS:
            skill_path = skills_dir / skill.name / "SKILL.md"
            assert skill_path.exists()


class TestSkillsShow:
    """Tests for 'sage skills show' command."""

    def test_show_displays_skill_content(self, runner, tmp_path):
        """Show command displays skill content."""
        skills_dir = tmp_path / "skills" / "sage"

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            runner.invoke(main, ["skills", "install"])
            result = runner.invoke(main, ["skills", "show", "sage-memory"])

        assert result.exit_code == 0
        assert "name: sage-memory" in result.output
        assert "Background" in result.output

    def test_show_error_for_missing_skill(self, runner, tmp_path):
        """Show command shows error for missing skill."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path):
            result = runner.invoke(main, ["skills", "show", "nonexistent"])

        assert result.exit_code == 1
        assert "not found" in result.output


class TestSkillsIntegration:
    """End-to-end integration tests."""

    def test_full_workflow(self, runner, tmp_path):
        """Test full install -> list -> show workflow."""
        skills_dir = tmp_path / "skills" / "sage"

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            # Install
            result = runner.invoke(main, ["skills", "install"])
            assert result.exit_code == 0

            # List
            result = runner.invoke(main, ["skills", "list"])
            assert result.exit_code == 0
            assert len(DEFAULT_SKILLS) == 3  # Verify we have 3 default skills
            for skill in DEFAULT_SKILLS:
                assert skill.name in result.output

            # Show each
            for skill in DEFAULT_SKILLS:
                result = runner.invoke(main, ["skills", "show", skill.name])
                assert result.exit_code == 0
                assert f"name: {skill.name}" in result.output

            # Update
            result = runner.invoke(main, ["skills", "update"])
            assert result.exit_code == 0

    def test_skills_persist_across_commands(self, runner, tmp_path):
        """Skills persist between CLI invocations."""
        skills_dir = tmp_path / "skills" / "sage"

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            # Install
            runner.invoke(main, ["skills", "install"])

        # Verify files exist on disk
        for skill in DEFAULT_SKILLS:
            skill_path = skills_dir / skill.name / "SKILL.md"
            assert skill_path.exists()
            content = skill_path.read_text()
            assert "---" in content  # Has frontmatter
