"""Tests for sage.skill module."""

from pathlib import Path

from sage.skill import Skill, SkillMetadata, build_context, create_skill, load_skill


class TestLoadSkill:
    """Tests for load_skill()."""

    def test_load_skill_returns_ok_for_existing_skill(
        self, mock_paths: dict, sample_skill_content: str
    ):
        """load_skill() returns Ok result with valid Skill data for existing skill."""
        skills_dir = mock_paths["skills_dir"]
        sage_dir = mock_paths["sage_dir"]

        # Create skill directory and SKILL.md
        skill_path = skills_dir / "test-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text(sample_skill_content)

        # Create docs directory with a doc
        docs_dir = skill_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "reference.md").write_text("# Reference\nSome content.")

        # Create shared memory
        (sage_dir / "shared_memory.md").write_text("Shared insight from other skills.")

        result = load_skill("test-skill")

        assert result.ok is True
        skill = result.value
        assert isinstance(skill, Skill)
        assert skill.name == "test-skill"
        assert skill.metadata.name == "test-skill"
        assert skill.metadata.description == "A test skill"
        assert skill.metadata.author == "sage"
        assert skill.metadata.version == "1.0.0"
        assert skill.metadata.tags == ("research", "test")
        assert skill.metadata.sage_managed is True
        assert len(skill.docs) == 1
        assert skill.docs[0][0] == "reference.md"
        assert "Reference" in skill.docs[0][1]
        assert skill.shared_memory == "Shared insight from other skills."
        assert "Shared insight" in skill.content

    def test_load_skill_returns_err_for_missing_skill(self, mock_paths: dict):
        """load_skill() returns Err result with skill_not_found error for missing skill."""
        result = load_skill("nonexistent-skill")

        assert result.ok is False
        assert result.error.code == "skill_not_found"
        assert "nonexistent-skill" in result.error.message


class TestCreateSkill:
    """Tests for create_skill()."""

    def test_create_skill_creates_directory_structure(self, mock_paths: dict):
        """create_skill() creates new skill directory structure and SKILL.md."""
        skills_dir = mock_paths["skills_dir"]
        sage_dir = mock_paths["sage_dir"]

        result = create_skill("new-skill", "A brand new skill")

        assert result.ok is True
        skill_path = result.value
        assert isinstance(skill_path, Path)

        # Verify directory structure in skills_dir
        assert (skills_dir / "new-skill").exists()
        assert (skills_dir / "new-skill" / "SKILL.md").exists()
        assert (skills_dir / "new-skill" / "docs").exists()
        assert (skills_dir / "new-skill" / "scripts").exists()

        # Verify sage metadata directory
        assert (sage_dir / "skills" / "new-skill").exists()
        assert (sage_dir / "skills" / "new-skill" / "sessions").exists()
        assert (sage_dir / "skills" / "new-skill" / "archive").exists()

        # Verify SKILL.md content
        skill_content = (skills_dir / "new-skill" / "SKILL.md").read_text()
        assert "name: new-skill" in skill_content
        assert "description: A brand new skill" in skill_content
        assert "sage_managed: true" in skill_content

    def test_create_skill_with_custom_expertise(self, mock_paths: dict):
        """create_skill() uses custom expertise points when provided."""
        skills_dir = mock_paths["skills_dir"]

        result = create_skill(
            "expert-skill",
            "An expert skill",
            expertise_points=["Expert in X", "Knows Y well"],
        )

        assert result.ok is True
        skill_content = (skills_dir / "expert-skill" / "SKILL.md").read_text()
        assert "Expert in X" in skill_content
        assert "Knows Y well" in skill_content


class TestBuildContext:
    """Tests for build_context()."""

    def test_build_context_contains_skill_content_and_docs(self):
        """build_context() returns context string containing skill content and docs."""
        skill = Skill(
            name="context-skill",
            metadata=SkillMetadata(
                name="context-skill",
                description="A context test skill",
            ),
            content="# Context Skill\n\nYou are a context skill.",
            docs=(
                ("doc1.md", "# Doc 1\nFirst document content."),
                ("doc2.md", "# Doc 2\nSecond document content."),
            ),
            shared_memory="Some shared memory.",
        )

        context = build_context(skill)

        assert "# Context Skill" in context
        assert "You are a context skill" in context
        assert "# Reference Documents" in context
        assert "## doc1.md" in context
        assert "First document content" in context
        assert "## doc2.md" in context
        assert "Second document content" in context

    def test_build_context_without_docs(self):
        """build_context() works when include_docs=False."""
        skill = Skill(
            name="no-docs-skill",
            metadata=SkillMetadata(name="no-docs-skill", description="No docs"),
            content="# Skill Content",
            docs=(("doc.md", "Doc content"),),
            shared_memory="",
        )

        context = build_context(skill, include_docs=False)

        assert "# Skill Content" in context
        assert "Reference Documents" not in context
        assert "Doc content" not in context
