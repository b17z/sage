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
from dataclasses import dataclass
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

    # Structural detection thresholds (for trigger detection)
    topic_drift_threshold: float = 0.50
    convergence_question_drop: float = 0.20
    trigger_threshold: float = 0.60  # Combined score threshold for 70/30 hybrid
    depth_min_messages: int = 8
    depth_min_tokens: int = 2000

    # Embedding models
    embedding_model: str = "BAAI/bge-large-en-v1.5"  # For prose (knowledge, checkpoints)
    code_embedding_model: str = "codesage/codesage-large"  # For code indexing

    # Async settings (v2.0)
    async_enabled: bool = False  # Sync by default; use CLAUDE.md Task subagent for backgrounding
    notify_success: bool = True  # Show success notifications via hook
    notify_errors: bool = True  # Show error notifications (always recommended)
    worker_timeout: float = 5.0  # Graceful shutdown timeout in seconds

    # Logging settings (v2.0.1)
    logging_enabled: bool = True  # Enable structured JSON logging to ~/.sage/logs/
    log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # Poll agent settings (v2.0.2)
    poll_agent_type: str = "general-purpose"  # Agent type for task polling
    poll_agent_model: str = "haiku"  # Model for polling agent (haiku is efficient)

    # Autosave trigger thresholds (v2.3) - minimum confidence to trigger checkpoint
    autosave_research_start: float = 0.0  # Always save starting point
    autosave_web_search_complete: float = 0.3  # Save if we learned something
    autosave_synthesis: float = 0.5  # Save meaningful conclusions
    autosave_topic_shift: float = 0.3  # Save before switching
    autosave_user_validated: float = 0.4  # User confirmed something
    autosave_constraint_discovered: float = 0.3  # Important pivot point
    autosave_branch_point: float = 0.4  # Decision point
    autosave_precompact: float = 0.0  # Always save before context compaction
    autosave_context_threshold: float = 0.0  # Always save when context threshold hit
    autosave_manual: float = 0.0  # Always save manual requests

    # Session continuity settings (v2.4)
    continuity_enabled: bool = True  # Inject context after compaction
    watcher_auto_start: bool = False  # Auto-start watcher on MCP init (opt-in)

    # Recovery checkpoint settings (v2.7)
    recovery_enabled: bool = True  # Generate recovery checkpoints on compaction
    recovery_use_claude: bool = True  # Use headless Claude for high-quality extraction
    recovery_salience_threshold: float = 0.5  # Min salience to save observation

    # Storage maintenance settings (v3.1)
    checkpoint_max_age_days: int = 90  # Prune checkpoints older than N days (0 = never)
    checkpoint_max_count: int = 200  # Cap to max N checkpoints (0 = unlimited)
    knowledge_max_age_days: int = 0  # Prune knowledge older than N days (0 = never)
    maintenance_on_save: bool = True  # Auto-run maintenance on save operations

    # Caching settings (v3.1)
    knowledge_cache_ttl_seconds: float = 45.0  # TTL for knowledge index cache

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        import logging

        logger = logging.getLogger(__name__)

        # Warn if weights don't sum to 1.0 (with floating point tolerance)
        weight_sum = self.embedding_weight + self.keyword_weight
        if abs(weight_sum - 1.0) > 0.001:
            logger.warning(
                f"embedding_weight ({self.embedding_weight}) + "
                f"keyword_weight ({self.keyword_weight}) = {weight_sum}, "
                "expected 1.0. This may affect scoring accuracy."
            )

        # Validate maintenance settings
        if 0 < self.checkpoint_max_count < 10:
            logger.warning(
                f"checkpoint_max_count={self.checkpoint_max_count} is very low. "
                "Consider using at least 10 to retain meaningful history."
            )

        if self.checkpoint_max_age_days < 0:
            logger.warning("checkpoint_max_age_days cannot be negative, treating as 0")
            object.__setattr__(self, "checkpoint_max_age_days", 0)

        if self.knowledge_max_age_days < 0:
            logger.warning("knowledge_max_age_days cannot be negative, treating as 0")
            object.__setattr__(self, "knowledge_max_age_days", 0)

        if self.knowledge_cache_ttl_seconds < 0:
            logger.warning("knowledge_cache_ttl_seconds cannot be negative, using 0")
            object.__setattr__(self, "knowledge_cache_ttl_seconds", 0.0)

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
        """Convert config to dictionary (all fields)."""
        return {
            field.name: getattr(self, field.name)
            for field in self.__dataclass_fields__.values()
        }

    def get_autosave_threshold(self, trigger_event: str) -> float | None:
        """Get autosave threshold for a trigger event.

        Args:
            trigger_event: The trigger name (e.g., "synthesis", "manual")

        Returns:
            Threshold value, or None if unknown trigger
        """
        attr_name = f"autosave_{trigger_event}"
        if hasattr(self, attr_name):
            return getattr(self, attr_name)
        return None


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
