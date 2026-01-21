"""Pytest fixtures for Sage tests."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_skills_dir(tmp_path: Path):
    """Create a temporary skills directory."""
    skills_dir = tmp_path / ".claude" / "skills"
    skills_dir.mkdir(parents=True)
    return skills_dir


@pytest.fixture
def mock_sage_dir(tmp_path: Path):
    """Create a temporary sage directory."""
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir(parents=True)
    (sage_dir / "skills").mkdir()
    return sage_dir


@pytest.fixture
def sample_skill_content():
    """Sample SKILL.md content."""
    return """---
name: test-skill
description: A test skill
author: sage
version: 1.0.0
tags: [research, test]
sage_managed: true
---

# Test Skill

You are a test skill.

{shared_memory}
"""


@pytest.fixture
def mock_paths(tmp_path: Path, mock_skills_dir: Path, mock_sage_dir: Path):
    """Patch config paths to use temporary directories."""
    with (
        patch("sage.skill.SKILLS_DIR", mock_skills_dir),
        patch("sage.skill.SHARED_MEMORY_PATH", mock_sage_dir / "shared_memory.md"),
        patch("sage.skill.get_skill_path", lambda name: mock_skills_dir / name),
        patch("sage.skill.get_sage_skill_path", lambda name: mock_sage_dir / "skills" / name),
    ):
        yield {
            "skills_dir": mock_skills_dir,
            "sage_dir": mock_sage_dir,
        }


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client."""
    client = MagicMock()
    return client
