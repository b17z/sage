"""Skill management for Sage.

Skills are stored in ~/.claude/skills/ (standard Agent Skills location).
Sage metadata is stored in ~/.sage/skills/.
"""

import re
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path

import yaml

from sage.config import SHARED_MEMORY_PATH, SKILLS_DIR, get_sage_skill_path, get_skill_path
from sage.errors import Result, SageError, err, ok, skill_exists, skill_not_found
from sage.history import read_history


@dataclass(frozen=True)
class SkillMetadata:
    """Skill metadata from YAML frontmatter."""

    name: str
    description: str
    author: str = "sage"
    version: str = "1.0.0"
    tags: tuple[str, ...] = ()
    sage_managed: bool = True


@dataclass(frozen=True)
class Skill:
    """Loaded skill with all context."""

    name: str
    metadata: SkillMetadata
    content: str
    docs: tuple[tuple[str, str], ...]  # (filename, content) pairs
    shared_memory: str


SKILL_TEMPLATE = """---
name: {name}
description: {description}
author: sage
version: 1.0.0
tags: [research]
sage_managed: true
---

# {title} Research Expert

You are a specialized research expert focused on {description_lower}.

## Your Domain Expertise
{expertise}

## How You Work
- Provide deep, technical analysis grounded in current sources
- When you search, use specific 2-5 word queries
- Cite sources with URLs when referencing search results
- Identify gaps in your knowledge and proactively search to fill them
- Be direct and opinionated when evidence supports a position
- Flag uncertainty explicitly rather than hedging everything

## Context Documents
The `docs/` directory contains reference materials. Load them when relevant to the query.

## Shared Memory
Cross-skill insights are injected below. These represent learnings from other research threads that may inform your analysis.

---
{{shared_memory}}
---
"""


def list_skills() -> list[str]:
    """List all Sage-managed skills."""
    if not SKILLS_DIR.exists():
        return []

    skills = []
    for skill_dir in SKILLS_DIR.iterdir():
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                # Check if Sage-managed
                content = skill_md.read_text()
                if "sage_managed: true" in content:
                    skills.append(skill_dir.name)

    return sorted(skills)


def find_similar_skills(name: str) -> list[str]:
    """Find skills with similar names."""
    all_skills = list_skills()
    return get_close_matches(name, all_skills, n=3, cutoff=0.6)


def skill_exists_check(name: str) -> bool:
    """Check if a skill already exists."""
    return (get_skill_path(name) / "SKILL.md").exists()


def load_shared_memory() -> str:
    """Load shared memory content."""
    if not SHARED_MEMORY_PATH.exists():
        return ""
    return SHARED_MEMORY_PATH.read_text()


def parse_skill_frontmatter(content: str) -> SkillMetadata | None:
    """Parse YAML frontmatter from skill content."""
    match = re.match(r"^---\n(.+?)\n---", content, re.DOTALL)
    if not match:
        return None

    try:
        data = yaml.safe_load(match.group(1))
        return SkillMetadata(
            name=data.get("name", ""),
            description=data.get("description", ""),
            author=data.get("author", "sage"),
            version=data.get("version", "1.0.0"),
            tags=tuple(data.get("tags", [])),
            sage_managed=data.get("sage_managed", False),
        )
    except yaml.YAMLError:
        return None


def load_skill(name: str) -> Result[Skill, SageError]:
    """Load a skill with all its context."""
    skill_path = get_skill_path(name)
    skill_md = skill_path / "SKILL.md"

    if not skill_md.exists():
        similar = find_similar_skills(name)
        return err(skill_not_found(name, similar))

    content = skill_md.read_text()
    metadata = parse_skill_frontmatter(content)
    if not metadata:
        return err(
            SageError(
                code="skill_invalid",
                message=f"Could not parse skill metadata for '{name}'",
            )
        )

    # Load docs
    docs = []
    docs_dir = skill_path / "docs"
    if docs_dir.exists():
        for doc_path in sorted(docs_dir.glob("*.md")):
            docs.append((doc_path.name, doc_path.read_text()))

    # Load shared memory
    shared_memory = load_shared_memory()

    # Inject shared memory into content
    if "{shared_memory}" in content:
        content = content.replace("{shared_memory}", shared_memory or "(No shared memory yet)")

    return ok(
        Skill(
            name=name,
            metadata=metadata,
            content=content,
            docs=tuple(docs),
            shared_memory=shared_memory,
        )
    )


def create_skill(
    name: str,
    description: str,
    expertise_points: list[str] | None = None,
) -> Result[Path, SageError]:
    """Create a new Sage-managed skill."""
    if skill_exists_check(name):
        return err(skill_exists(name))

    # Create skill directory structure
    skill_path = get_skill_path(name)
    skill_path.mkdir(parents=True, exist_ok=True)
    (skill_path / "docs").mkdir(exist_ok=True)
    (skill_path / "scripts").mkdir(exist_ok=True)

    # Create Sage metadata directory
    sage_path = get_sage_skill_path(name)
    sage_path.mkdir(parents=True, exist_ok=True)
    (sage_path / "sessions").mkdir(exist_ok=True)
    (sage_path / "archive").mkdir(exist_ok=True)

    # Generate expertise section
    if expertise_points:
        expertise = "\n".join(f"- {point}" for point in expertise_points)
    else:
        expertise = f"- Deep knowledge of {description.lower()}\n- Current awareness of developments in this space\n- Ability to synthesize complex information"

    # Generate title (capitalize first letter of each word)
    title = " ".join(word.capitalize() for word in name.replace("-", " ").replace("_", " ").split())

    # Generate SKILL.md
    skill_content = SKILL_TEMPLATE.format(
        name=name,
        description=description,
        title=title,
        description_lower=description.lower(),
        expertise=expertise,
    )

    skill_md = skill_path / "SKILL.md"
    skill_md.write_text(skill_content)

    return ok(skill_path)


def get_skill_info(name: str) -> Result[dict, SageError]:
    """Get comprehensive info about a skill."""
    result = load_skill(name)
    if not result.ok:
        return result

    skill = result.value
    history = read_history(name, limit=5)
    sage_path = get_sage_skill_path(name)

    # Count sessions
    sessions_dir = sage_path / "sessions"
    session_count = len(list(sessions_dir.glob("*.md"))) if sessions_dir.exists() else 0

    # Get last active time from history
    last_active = None
    if history:
        last_active = history[0].ts

    # Calculate doc sizes (rough token estimate: 1 token ≈ 4 chars)
    doc_info = [{"name": name, "tokens": len(content) // 4} for name, content in skill.docs]

    return ok(
        {
            "name": skill.name,
            "metadata": skill.metadata,
            "docs": doc_info,
            "doc_count": len(skill.docs),
            "session_count": session_count,
            "history_count": len(read_history(name)),
            "last_active": last_active,
            "shared_memory_size": len(skill.shared_memory) // 4,  # rough token estimate
        }
    )


def build_context(skill: Skill, include_docs: bool = True) -> str:
    """Build full context string for a skill."""
    parts = [skill.content]

    if include_docs and skill.docs:
        parts.append("\n\n---\n\n# Reference Documents\n")
        for doc_name, doc_content in skill.docs:
            parts.append(f"\n## {doc_name}\n\n{doc_content}")

    return "".join(parts)
