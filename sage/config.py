"""Configuration management for Sage.

Storage Structure
-----------------
Sage uses a layered storage model:

~/.sage/                      # User-level (NEVER in git repos)
├── config.yaml               # API key, model preferences (secrets!)
├── embeddings/               # Binary embedding caches
└── skills/*/history.jsonl    # Query history

<project>/.sage/              # Project-level (shareable via git)
├── checkpoints/              # Research checkpoints (team context)
├── knowledge/                # Knowledge base (team insights)
├── tuning.yaml               # Threshold config (team settings)
└── local/                    # GITIGNORED - project-local overrides

Configuration Classes
---------------------
**Config** (Runtime/Secrets)
    Stored ONLY in ~/.sage/config.yaml. Never in project directories.
    - api_key: Anthropic API key (or ANTHROPIC_API_KEY env var)
    - model: Default Claude model
    - max_history, cache_ttl, research depths

**SageConfig** (Tuning/Shareable)
    Cascade: project .sage/tuning.yaml → user ~/.sage/tuning.yaml → defaults
    - recall_threshold, dedup_threshold: Retrieval thresholds (0-1)
    - embedding_weight, keyword_weight: Scoring balance (sum to 1.0)
    - topic_drift_threshold, depth_min_*: Detection thresholds
    - embedding_model: Sentence transformer model name
"""

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
class Config:
    """Sage configuration."""

    api_key: str | None = None
    model: str = "claude-sonnet-4-20250514"
    max_history: int = 10
    cache_ttl: int = 300

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
        return cls(
            api_key=data.get("api_key"),
            model=data.get("model", "claude-sonnet-4-20250514"),
            max_history=data.get("max_history", 10),
            cache_ttl=data.get("cache_ttl", 300),
        )

    def save(self) -> None:
        """Save configuration to file."""
        SAGE_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "api_key": self.api_key,
            "model": self.model,
            "max_history": self.max_history,
            "cache_ttl": self.cache_ttl,
        }

        with open(CONFIG_PATH, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)
        # Restrict permissions - config may contain API key
        CONFIG_PATH.chmod(0o600)


def ensure_directories() -> None:
    """Ensure all required directories exist."""
    SAGE_DIR.mkdir(parents=True, exist_ok=True)
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    (SAGE_DIR / "skills").mkdir(exist_ok=True)
    (SAGE_DIR / "exports").mkdir(exist_ok=True)
    (SAGE_DIR / "hooks").mkdir(exist_ok=True)


def _sanitize_name(name: str) -> str:
    """Sanitize a name to prevent path traversal attacks.
    
    Only allows alphanumeric, hyphens, underscores.
    Prevents names like '../../../.bashrc' from escaping directories.
    """
    import re
    sanitized = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")
    return sanitized or "unnamed"


def get_skill_path(skill_name: str) -> Path:
    """Get the path to a skill's directory in ~/.claude/skills/."""
    safe_name = _sanitize_name(skill_name)
    return SKILLS_DIR / safe_name


def get_sage_skill_path(skill_name: str) -> Path:
    """Get the path to a skill's Sage metadata directory in ~/.sage/skills/."""
    safe_name = _sanitize_name(skill_name)
    return SAGE_DIR / "skills" / safe_name


@dataclass
class SageConfig:
    """User-configurable parameters for retrieval and detection.

    These are tunable thresholds that power users can adjust for their
    specific knowledge base and workflow.
    """

    # Retrieval thresholds
    recall_threshold: float = 0.70
    dedup_threshold: float = 0.90
    embedding_weight: float = 0.70
    keyword_weight: float = 0.30

    # Structural detection thresholds (for future trigger detection)
    topic_drift_threshold: float = 0.50
    convergence_question_drop: float = 0.20
    depth_min_messages: int = 8
    depth_min_tokens: int = 2000

    # Embedding model (current default, upgrade path available)
    embedding_model: str = "all-MiniLM-L6-v2"

    @classmethod
    def load(cls, sage_dir: Path) -> "SageConfig":
        """Load config from a sage directory.

        Args:
            sage_dir: Path to .sage directory (project-local or user-level)

        Returns:
            SageConfig with values from file, or defaults if not found
        """
        config_path = sage_dir / "tuning.yaml"
        if config_path.exists():
            with open(config_path) as f:
                overrides = yaml.safe_load(f) or {}
            # Only apply known fields - use dataclass fields, not hasattr (security)
            valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
            valid_overrides = {k: v for k, v in overrides.items() if k in valid_fields}
            return cls(**valid_overrides)
        return cls()

    def save(self, sage_dir: Path) -> Path:
        """Save config to a sage directory.

        Args:
            sage_dir: Path to .sage directory

        Returns:
            Path to saved config file
        """
        sage_dir.mkdir(parents=True, exist_ok=True)
        config_path = sage_dir / "tuning.yaml"

        # Only save non-default values to keep file clean
        defaults = SageConfig()
        data = {}
        for key, value in self.__dict__.items():
            if getattr(defaults, key) != value:
                data[key] = value

        # If all defaults, save empty dict (or minimal marker)
        if not data:
            data = {"_version": 1}  # Marker that config was explicitly saved

        with open(config_path, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False)
        # Restrict permissions - tuning config is user-specific
        config_path.chmod(0o600)

        return config_path

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "recall_threshold": self.recall_threshold,
            "dedup_threshold": self.dedup_threshold,
            "embedding_weight": self.embedding_weight,
            "keyword_weight": self.keyword_weight,
            "topic_drift_threshold": self.topic_drift_threshold,
            "convergence_question_drop": self.convergence_question_drop,
            "depth_min_messages": self.depth_min_messages,
            "depth_min_tokens": self.depth_min_tokens,
            "embedding_model": self.embedding_model,
        }


def get_sage_config(project_path: Path | None = None) -> SageConfig:
    """Load SageConfig with project → user → default cascade.

    Priority (highest to lowest):
    1. Project-level config (<project>/.sage/tuning.yaml)
    2. User-level config (~/.sage/tuning.yaml)
    3. Built-in defaults

    Args:
        project_path: Explicit project path. If None, auto-detects.

    Returns:
        SageConfig with merged values
    """
    # Try project-level first
    if project_path is not None:
        project_sage = project_path / ".sage"
        if project_sage.exists():
            return SageConfig.load(project_sage)

    # Auto-detect project root
    detected_root = detect_project_root()
    if detected_root is not None:
        project_sage = detected_root / ".sage"
        if project_sage.exists():
            return SageConfig.load(project_sage)

    # Fall back to user-level
    return SageConfig.load(SAGE_DIR)


def detect_project_root(start_path: Path | None = None) -> Path | None:
    """Detect project root by traversing up from start_path looking for markers.

    Looks for (in order of priority):
    1. A .sage directory (explicit Sage project)
    2. A .git directory (git repository root)

    Args:
        start_path: Starting path for traversal. Defaults to cwd.

    Returns:
        Project root path, or None if no project markers found.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()
    home = Path.home()

    while current != current.parent:
        # Stop traversal at or above home directory
        if current == home or home not in current.parents:
            # Check current before stopping
            if (current / ".sage").is_dir() or (current / ".git").exists():
                return current
            if current == home or len(current.parts) <= len(home.parts):
                break

        # Check for .sage first (explicit Sage project)
        if (current / ".sage").is_dir():
            return current

        # Check for .git (git repository)
        if (current / ".git").exists():
            return current

        current = current.parent

    return None
