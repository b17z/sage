"""Configuration management for Sage."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Standard paths
SAGE_DIR = Path.home() / ".sage"
SKILLS_DIR = Path.home() / ".claude" / "skills"
CONFIG_PATH = SAGE_DIR / "config.yaml"
SHARED_MEMORY_PATH = SAGE_DIR / "shared_memory.md"
ACTIVE_SKILL_PATH = SAGE_DIR / ".active_skill"
REFERENCE_DIR = SAGE_DIR / "reference"


@dataclass
class ResearchDepth:
    """Configuration for a research depth level."""

    max_searches: int
    max_loops: int


@dataclass
class ResearchConfig:
    """Research mode configuration."""

    shallow: ResearchDepth = field(default_factory=lambda: ResearchDepth(max_searches=3, max_loops=1))
    medium: ResearchDepth = field(default_factory=lambda: ResearchDepth(max_searches=7, max_loops=3))
    deep: ResearchDepth = field(default_factory=lambda: ResearchDepth(max_searches=15, max_loops=5))


@dataclass
class Config:
    """Sage configuration."""

    api_key: str | None = None
    model: str = "claude-sonnet-4-20250514"
    default_depth: str = "medium"
    max_history: int = 10
    cache_ttl: int = 300
    research: ResearchConfig = field(default_factory=ResearchConfig)

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file and environment."""
        config = cls()

        # Load from file if exists
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                data = yaml.safe_load(f) or {}
            config = cls._from_dict(data)

        # Environment variables override file config
        if env_key := os.environ.get("ANTHROPIC_API_KEY"):
            config.api_key = env_key

        return config

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "Config":
        """Create config from dictionary."""
        research_data = data.get("research", {})
        research = ResearchConfig(
            shallow=ResearchDepth(**research_data.get("shallow", {"max_searches": 3, "max_loops": 1})),
            medium=ResearchDepth(**research_data.get("medium", {"max_searches": 7, "max_loops": 3})),
            deep=ResearchDepth(**research_data.get("deep", {"max_searches": 15, "max_loops": 5})),
        )

        return cls(
            api_key=data.get("api_key"),
            model=data.get("model", "claude-sonnet-4-20250514"),
            default_depth=data.get("default_depth", "medium"),
            max_history=data.get("max_history", 10),
            cache_ttl=data.get("cache_ttl", 300),
            research=research,
        )

    def save(self) -> None:
        """Save configuration to file."""
        SAGE_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "api_key": self.api_key,
            "model": self.model,
            "default_depth": self.default_depth,
            "max_history": self.max_history,
            "cache_ttl": self.cache_ttl,
            "research": {
                "shallow": {
                    "max_searches": self.research.shallow.max_searches,
                    "max_loops": self.research.shallow.max_loops,
                },
                "medium": {
                    "max_searches": self.research.medium.max_searches,
                    "max_loops": self.research.medium.max_loops,
                },
                "deep": {
                    "max_searches": self.research.deep.max_searches,
                    "max_loops": self.research.deep.max_loops,
                },
            },
        }

        with open(CONFIG_PATH, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)

    def get_depth_config(self, depth: str) -> ResearchDepth:
        """Get research configuration for a depth level."""
        match depth:
            case "shallow":
                return self.research.shallow
            case "medium":
                return self.research.medium
            case "deep":
                return self.research.deep
            case _:
                return self.research.medium


def ensure_directories() -> None:
    """Ensure all required directories exist."""
    SAGE_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    (SAGE_DIR / "skills").mkdir(exist_ok=True)
    (SAGE_DIR / "exports").mkdir(exist_ok=True)
    (SAGE_DIR / "hooks").mkdir(exist_ok=True)


def get_skill_path(skill_name: str) -> Path:
    """Get the path to a skill's directory in ~/.claude/skills/."""
    return SKILLS_DIR / skill_name


def get_sage_skill_path(skill_name: str) -> Path:
    """Get the path to a skill's Sage metadata directory in ~/.sage/skills/."""
    return SAGE_DIR / "skills" / skill_name
