"""Default Sage methodology skills.

These skills teach Claude HOW to use Sage effectively.
Installed via `sage skills install`.

Skills are loaded from the skills/ directory in the package root,
making them easy to edit as markdown files.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from sage.config import SKILLS_DIR


def _sanitize_skill_name(name: str) -> str:
    """Sanitize a skill name to prevent path traversal attacks.

    Removes any characters that could be used for directory traversal
    or shell injection. Only allows alphanumeric, underscore, and hyphen.
    """
    # Remove any path separators and dangerous characters
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")
    return sanitized or "unnamed"


# Sage skills live in ~/.claude/skills/sage/
SAGE_SKILLS_DIR = SKILLS_DIR / "sage"

# Source skills directory (in package)
SKILLS_SOURCE_DIR = Path(__file__).parent.parent / "skills"

# Default skill names (order matters for installation)
DEFAULT_SKILL_NAMES = [
    "sage-memory",
    "sage-research",
    "sage-session",
    "sage-knowledge-hygiene",
    "sage-knowledge",
]


@dataclass(frozen=True)
class DefaultSkill:
    """A default Sage skill definition."""

    name: str
    content: str


def _load_skill_from_source(skill_name: str) -> DefaultSkill | None:
    """Load a skill from the skills/ source directory.

    Args:
        skill_name: Name of the skill directory

    Returns:
        DefaultSkill if found, None otherwise
    """
    skill_path = SKILLS_SOURCE_DIR / skill_name / "SKILL.md"
    if not skill_path.exists():
        return None

    content = skill_path.read_text()
    return DefaultSkill(name=skill_name, content=content)


def get_default_skills() -> list[DefaultSkill]:
    """Load all default skills from the skills/ directory.

    Returns:
        List of DefaultSkill objects
    """
    skills = []
    for name in DEFAULT_SKILL_NAMES:
        skill = _load_skill_from_source(name)
        if skill:
            skills.append(skill)
    return skills


# Lazy-loaded cache for backward compatibility
_default_skills_cache: list[DefaultSkill] | None = None


def _get_default_skills_cached() -> list[DefaultSkill]:
    """Get default skills with caching."""
    global _default_skills_cache
    if _default_skills_cache is None:
        _default_skills_cache = get_default_skills()
    return _default_skills_cache


def get_skill_path(skill_name: str) -> Path:
    """Get the path where a Sage skill should be installed.

    Security: skill_name is sanitized to prevent path traversal.
    """
    safe_name = _sanitize_skill_name(skill_name)
    return SAGE_SKILLS_DIR / safe_name / "SKILL.md"


def install_skill(skill: DefaultSkill, force: bool = False) -> tuple[bool, str]:
    """Install a single skill.

    Returns:
        (success, message) tuple
    """
    skill_dir = SAGE_SKILLS_DIR / skill.name
    skill_path = skill_dir / "SKILL.md"

    if skill_path.exists() and not force:
        return False, f"Skill '{skill.name}' already exists (use --force to overwrite)"

    # Create directory and write skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill.content)

    # Set restrictive permissions (0o644 for skill files - readable but not world-writable)
    skill_path.chmod(0o644)

    action = "Updated" if skill_path.exists() else "Installed"
    return True, f"{action} {skill.name}"


def install_all_skills(force: bool = False) -> list[tuple[str, bool, str]]:
    """Install all default Sage skills.

    Returns:
        List of (skill_name, success, message) tuples
    """
    results = []
    for skill in _get_default_skills_cached():
        success, message = install_skill(skill, force=force)
        results.append((skill.name, success, message))
    return results


def get_installed_sage_skills() -> list[str]:
    """List installed Sage methodology skills."""
    if not SAGE_SKILLS_DIR.exists():
        return []

    skills = []
    for skill_dir in SAGE_SKILLS_DIR.iterdir():
        if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
            skills.append(skill_dir.name)

    return sorted(skills)


def check_skill_version(skill_name: str) -> tuple[str | None, str | None]:
    """Check installed vs available version for a skill.

    Security: skill_name is sanitized to prevent path traversal.

    Returns:
        (installed_version, available_version) tuple
    """
    safe_name = _sanitize_skill_name(skill_name)
    skill_path = SAGE_SKILLS_DIR / safe_name / "SKILL.md"

    # Get installed version
    installed_version = None
    if skill_path.exists():
        content = skill_path.read_text()
        match = re.search(r"version:\s*([^\n]+)", content)
        if match:
            installed_version = match.group(1).strip()

    # Get available version from source
    available_version = None
    skill = _load_skill_from_source(skill_name)
    if skill:
        match = re.search(r"version:\s*([^\n]+)", skill.content)
        if match:
            available_version = match.group(1).strip()

    return installed_version, available_version


def get_skill_by_name(skill_name: str) -> DefaultSkill | None:
    """Get a specific default skill by name.

    Args:
        skill_name: Name of the skill

    Returns:
        DefaultSkill if found, None otherwise
    """
    for skill in _get_default_skills_cached():
        if skill.name == skill_name:
            return skill
    return None
