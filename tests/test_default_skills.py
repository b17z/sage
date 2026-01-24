"""Tests for default Sage methodology skills."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from sage.default_skills import (
    DEFAULT_SKILLS,
    SAGE_MEMORY_SKILL,
    SAGE_RESEARCH_SKILL,
    SAGE_SESSION_SKILL,
    DefaultSkill,
    _sanitize_skill_name,
    check_skill_version,
    get_installed_sage_skills,
    get_skill_path,
    install_all_skills,
    install_skill,
)


class TestDefaultSkillDefinitions:
    """Tests for skill definitions."""

    def test_all_skills_have_required_fields(self):
        """All default skills have name and content."""
        for skill in DEFAULT_SKILLS:
            assert skill.name, f"Skill missing name"
            assert skill.content, f"Skill {skill.name} missing content"
            assert isinstance(skill, DefaultSkill)

    def test_skill_content_has_frontmatter(self):
        """All skills have YAML frontmatter."""
        for skill in DEFAULT_SKILLS:
            assert skill.content.startswith("---"), f"{skill.name} missing frontmatter"
            # Find closing ---
            lines = skill.content.split("\n")
            closing_index = None
            for i, line in enumerate(lines[1:], 1):
                if line.strip() == "---":
                    closing_index = i
                    break
            assert closing_index is not None, f"{skill.name} missing closing ---"

    def test_skill_frontmatter_has_name(self):
        """All skills have name in frontmatter."""
        for skill in DEFAULT_SKILLS:
            assert f"name: {skill.name}" in skill.content, f"{skill.name} missing name in frontmatter"

    def test_skill_frontmatter_has_triggers(self):
        """All skills have triggers in frontmatter."""
        for skill in DEFAULT_SKILLS:
            assert "triggers:" in skill.content, f"{skill.name} missing triggers"

    def test_skill_frontmatter_has_version(self):
        """All skills have version in frontmatter."""
        for skill in DEFAULT_SKILLS:
            assert "version:" in skill.content, f"{skill.name} missing version"

    def test_sage_memory_skill_content(self):
        """sage-memory skill has expected content."""
        assert "Background" in SAGE_MEMORY_SKILL.content
        assert "Task" in SAGE_MEMORY_SKILL.content
        assert "sage_save_checkpoint" in SAGE_MEMORY_SKILL.content

    def test_sage_research_skill_content(self):
        """sage-research skill has expected content."""
        assert "synthesis" in SAGE_RESEARCH_SKILL.content
        assert "checkpoint" in SAGE_RESEARCH_SKILL.content.lower()
        assert "sage_autosave_check" in SAGE_RESEARCH_SKILL.content

    def test_sage_session_skill_content(self):
        """sage-session skill has expected content."""
        assert "sage_health" in SAGE_SESSION_SKILL.content
        assert "session" in SAGE_SESSION_SKILL.content.lower()


class TestGetSkillPath:
    """Tests for get_skill_path function."""

    def test_returns_path_object(self):
        """Returns a Path object."""
        result = get_skill_path("test-skill")
        assert isinstance(result, Path)

    def test_path_includes_skill_name(self):
        """Path includes the skill name."""
        result = get_skill_path("my-skill")
        assert "my-skill" in str(result)

    def test_path_ends_with_skill_md(self):
        """Path ends with SKILL.md."""
        result = get_skill_path("test")
        assert result.name == "SKILL.md"


class TestInstallSkill:
    """Tests for install_skill function."""

    def test_creates_skill_directory(self, tmp_path):
        """Creates skill directory if it doesn't exist."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path / "skills" / "sage"):
            skill = DefaultSkill(name="test-skill", content="---\nname: test-skill\n---\nContent")
            success, message = install_skill(skill)

        assert success
        assert (tmp_path / "skills" / "sage" / "test-skill" / "SKILL.md").exists()

    def test_writes_skill_content(self, tmp_path):
        """Writes skill content to SKILL.md."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path / "skills" / "sage"):
            content = "---\nname: test\ntriggers: [test]\n---\n\n# Test Skill\n\nContent here."
            skill = DefaultSkill(name="test", content=content)
            install_skill(skill)

        skill_path = tmp_path / "skills" / "sage" / "test" / "SKILL.md"
        assert skill_path.read_text() == content

    def test_does_not_overwrite_without_force(self, tmp_path):
        """Does not overwrite existing skill without force flag."""
        skills_dir = tmp_path / "skills" / "sage"
        skill_dir = skills_dir / "existing"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text("original content")

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            skill = DefaultSkill(name="existing", content="new content")
            success, message = install_skill(skill)

        assert not success
        assert "already exists" in message
        assert skill_path.read_text() == "original content"

    def test_overwrites_with_force(self, tmp_path):
        """Overwrites existing skill with force flag."""
        skills_dir = tmp_path / "skills" / "sage"
        skill_dir = skills_dir / "existing"
        skill_dir.mkdir(parents=True)
        skill_path = skill_dir / "SKILL.md"
        skill_path.write_text("original content")

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            skill = DefaultSkill(name="existing", content="new content")
            success, message = install_skill(skill, force=True)

        assert success
        assert skill_path.read_text() == "new content"

    def test_sets_file_permissions(self, tmp_path):
        """Sets restrictive file permissions."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path / "skills" / "sage"):
            skill = DefaultSkill(name="test", content="---\nname: test\n---")
            install_skill(skill)

        skill_path = tmp_path / "skills" / "sage" / "test" / "SKILL.md"
        # Check permissions (0o644 = rw-r--r--)
        mode = skill_path.stat().st_mode & 0o777
        assert mode == 0o644


class TestInstallAllSkills:
    """Tests for install_all_skills function."""

    def test_installs_all_default_skills(self, tmp_path):
        """Installs all default skills."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path / "skills" / "sage"):
            results = install_all_skills()

        assert len(results) == len(DEFAULT_SKILLS)
        for skill_name, success, message in results:
            assert success, f"Failed to install {skill_name}: {message}"

    def test_returns_results_for_each_skill(self, tmp_path):
        """Returns (name, success, message) for each skill."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path / "skills" / "sage"):
            results = install_all_skills()

        for result in results:
            assert len(result) == 3
            name, success, message = result
            assert isinstance(name, str)
            assert isinstance(success, bool)
            assert isinstance(message, str)


class TestGetInstalledSageSkills:
    """Tests for get_installed_sage_skills function."""

    def test_returns_empty_when_no_skills(self, tmp_path):
        """Returns empty list when no skills installed."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path / "nonexistent"):
            result = get_installed_sage_skills()

        assert result == []

    def test_returns_installed_skill_names(self, tmp_path):
        """Returns names of installed skills."""
        skills_dir = tmp_path / "skills"
        for name in ["skill-a", "skill-b"]:
            skill_dir = skills_dir / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("content")

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            result = get_installed_sage_skills()

        assert set(result) == {"skill-a", "skill-b"}

    def test_ignores_directories_without_skill_md(self, tmp_path):
        """Ignores directories that don't have SKILL.md."""
        skills_dir = tmp_path / "skills"
        (skills_dir / "valid").mkdir(parents=True)
        (skills_dir / "valid" / "SKILL.md").write_text("content")
        (skills_dir / "invalid").mkdir(parents=True)  # No SKILL.md

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            result = get_installed_sage_skills()

        assert result == ["valid"]

    def test_returns_sorted_list(self, tmp_path):
        """Returns skills in sorted order."""
        skills_dir = tmp_path / "skills"
        for name in ["zebra", "alpha", "beta"]:
            skill_dir = skills_dir / name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text("content")

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            result = get_installed_sage_skills()

        assert result == ["alpha", "beta", "zebra"]


class TestCheckSkillVersion:
    """Tests for check_skill_version function."""

    def test_returns_none_when_not_installed(self, tmp_path):
        """Returns (None, available) when skill not installed."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path):
            installed, available = check_skill_version("sage-memory")

        assert installed is None
        assert available == "1.0.0"  # From DEFAULT_SKILLS

    def test_returns_installed_version(self, tmp_path):
        """Returns installed version from SKILL.md."""
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "sage-memory"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: sage-memory\nversion: 2.0.0\n---")

        with patch("sage.default_skills.SAGE_SKILLS_DIR", skills_dir):
            installed, available = check_skill_version("sage-memory")

        assert installed == "2.0.0"
        assert available == "1.0.0"

    def test_returns_none_for_unknown_skill(self, tmp_path):
        """Returns (None, None) for unknown skill."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path):
            installed, available = check_skill_version("unknown-skill")

        assert installed is None
        assert available is None


class TestSanitizeSkillName:
    """Security tests for skill name sanitization."""

    def test_removes_path_separators(self):
        """Removes path separators to prevent traversal."""
        assert _sanitize_skill_name("../../../etc/passwd") == "etc-passwd"
        assert _sanitize_skill_name("foo/bar/baz") == "foo-bar-baz"
        assert _sanitize_skill_name("..") == "unnamed"  # Empty after strip -> unnamed

    def test_removes_shell_injection_chars(self):
        """Removes characters that could be used for shell injection."""
        # Note: spaces and special chars become hyphens, may result in double hyphens
        result = _sanitize_skill_name("skill;rm -rf /")
        assert ";" not in result
        assert "/" not in result

        result = _sanitize_skill_name("skill`whoami`")
        assert "`" not in result

        result = _sanitize_skill_name("skill$(id)")
        assert "$" not in result
        assert "(" not in result

        result = _sanitize_skill_name("skill|cat")
        assert "|" not in result

    def test_allows_safe_characters(self):
        """Allows alphanumeric, underscore, and hyphen."""
        assert _sanitize_skill_name("my-skill_v2") == "my-skill_v2"
        assert _sanitize_skill_name("SageMemory123") == "SageMemory123"

    def test_handles_empty_input(self):
        """Returns 'unnamed' for empty or all-dangerous input."""
        assert _sanitize_skill_name("") == "unnamed"
        assert _sanitize_skill_name("../..") == "unnamed"
        assert _sanitize_skill_name("///") == "unnamed"

    def test_strips_leading_trailing_hyphens(self):
        """Strips leading and trailing hyphens."""
        assert _sanitize_skill_name("--skill--") == "skill"
        assert _sanitize_skill_name("-test-") == "test"


class TestGetSkillPathSecurity:
    """Security tests for get_skill_path function."""

    def test_sanitizes_path_traversal_attempts(self):
        """Prevents path traversal attacks."""
        path = get_skill_path("../../../etc/passwd")
        assert ".." not in str(path)
        assert "/etc/passwd" not in str(path)

    def test_path_stays_within_skills_dir(self, tmp_path):
        """Path stays within the skills directory."""
        with patch("sage.default_skills.SAGE_SKILLS_DIR", tmp_path / "skills"):
            path = get_skill_path("../../../../etc/passwd")
            # Path should be under tmp_path/skills, not /etc/passwd
            assert str(path).startswith(str(tmp_path))


class TestSkillContentQuality:
    """Tests for skill content quality and completeness."""

    def test_sage_memory_mentions_mcp_tools(self):
        """sage-memory mentions the MCP tools it applies to."""
        content = SAGE_MEMORY_SKILL.content
        assert "sage_save_checkpoint" in content
        assert "sage_save_knowledge" in content
        assert "sage_autosave_check" in content

    def test_sage_research_mentions_triggers(self):
        """sage-research mentions checkpoint triggers."""
        content = SAGE_RESEARCH_SKILL.content
        assert "synthesis" in content
        assert "topic_shift" in content or "topic shift" in content.lower()

    def test_sage_session_mentions_health(self):
        """sage-session mentions sage_health for session start."""
        content = SAGE_SESSION_SKILL.content
        assert "sage_health" in content

    def test_all_skills_have_meaningful_triggers(self):
        """All skills have at least 3 trigger keywords."""
        for skill in DEFAULT_SKILLS:
            match = re.search(r"triggers:\s*\[([^\]]+)\]", skill.content)
            assert match, f"{skill.name} has no triggers"
            triggers = match.group(1).split(",")
            assert len(triggers) >= 3, f"{skill.name} has fewer than 3 triggers"
