"""Plugin registry for watcher daemon.

Manages loading and configuration of built-in plugins.
Plugins are enabled/disabled via ~/.sage/plugins.yaml.

Security:
- Only built-in plugins are loaded (no arbitrary code)
- Plugin names are validated against whitelist
- YAML config uses safe_load
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from sage.config import SAGE_DIR
from sage.plugins.base import BasePlugin
from sage.plugins.events import WatcherEvent

logger = logging.getLogger(__name__)

# Built-in plugin names - these are the only plugins that can be loaded
BUILTIN_PLUGIN_NAMES = frozenset(
    {
        "session",
        "recovery",
        "checkpoint-queue",
    }
)

# Plugin config file location
PLUGINS_CONFIG_FILE = SAGE_DIR / "plugins.yaml"


@dataclass(frozen=True)
class PluginConfig:
    """Configuration for a single plugin.

    Attributes:
        enabled: Whether the plugin is active
        priority: Execution order (lower = earlier)
        settings: Plugin-specific settings dict
    """

    enabled: bool = True
    priority: int = 100
    settings: dict[str, Any] = field(default_factory=dict)


def _get_builtin_plugins() -> dict[str, type[BasePlugin]]:
    """Get mapping of plugin names to their classes.

    Imports are done here to avoid circular imports.
    Only returns plugins that are in BUILTIN_PLUGIN_NAMES.

    Returns:
        Dict mapping plugin name to plugin class
    """
    plugins: dict[str, type[BasePlugin]] = {}

    try:
        from sage.plugins.builtin.session import SessionPlugin

        plugins["session"] = SessionPlugin
    except ImportError as e:
        logger.warning(f"Failed to import session plugin: {e}")

    try:
        from sage.plugins.builtin.recovery import RecoveryPlugin

        plugins["recovery"] = RecoveryPlugin
    except ImportError as e:
        logger.warning(f"Failed to import recovery plugin: {e}")

    try:
        from sage.plugins.builtin.checkpoint_queue import CheckpointQueuePlugin

        plugins["checkpoint-queue"] = CheckpointQueuePlugin
    except ImportError as e:
        logger.warning(f"Failed to import checkpoint-queue plugin: {e}")

    return plugins


def load_plugin_config() -> dict[str, PluginConfig]:
    """Load plugin configuration from ~/.sage/plugins.yaml.

    Returns defaults for missing plugins.
    Unknown plugin names are rejected.

    Returns:
        Dict mapping plugin name to PluginConfig
    """
    configs: dict[str, PluginConfig] = {}

    # Start with defaults for all built-in plugins
    for name in BUILTIN_PLUGIN_NAMES:
        configs[name] = PluginConfig()

    # Load overrides from file
    if PLUGINS_CONFIG_FILE.exists():
        try:
            with open(PLUGINS_CONFIG_FILE) as f:
                data = yaml.safe_load(f) or {}

            if not isinstance(data, dict):
                logger.warning("plugins.yaml is not a dict, using defaults")
                return configs

            plugins_data = data.get("plugins", {})
            if not isinstance(plugins_data, dict):
                logger.warning("plugins.yaml 'plugins' is not a dict, using defaults")
                return configs

            for name, config_data in plugins_data.items():
                # Reject unknown plugin names
                if name not in BUILTIN_PLUGIN_NAMES:
                    logger.warning(f"Unknown plugin '{name}' in plugins.yaml, ignoring")
                    continue

                if not isinstance(config_data, dict):
                    continue

                # Parse config fields
                enabled = config_data.get("enabled", True)
                priority = config_data.get("priority", 100)
                settings = config_data.get("settings", {})

                # Validate types
                if not isinstance(enabled, bool):
                    enabled = True
                if not isinstance(priority, int):
                    priority = 100
                if not isinstance(settings, dict):
                    settings = {}

                configs[name] = PluginConfig(
                    enabled=enabled,
                    priority=priority,
                    settings=settings,
                )

        except yaml.YAMLError as e:
            logger.warning(f"Failed to parse plugins.yaml: {e}")
        except OSError as e:
            logger.warning(f"Failed to read plugins.yaml: {e}")

    return configs


def save_plugin_config(configs: dict[str, PluginConfig]) -> Path:
    """Save plugin configuration to ~/.sage/plugins.yaml.

    Args:
        configs: Dict mapping plugin name to PluginConfig

    Returns:
        Path to saved config file
    """
    SAGE_DIR.mkdir(parents=True, exist_ok=True)

    # Convert to serializable format
    plugins_data = {}
    for name, config in configs.items():
        if name not in BUILTIN_PLUGIN_NAMES:
            continue

        plugins_data[name] = {
            "enabled": config.enabled,
            "priority": config.priority,
            "settings": dict(config.settings),
        }

    data = {"plugins": plugins_data}

    with open(PLUGINS_CONFIG_FILE, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)

    PLUGINS_CONFIG_FILE.chmod(0o600)
    return PLUGINS_CONFIG_FILE


def get_enabled_plugins() -> list[BasePlugin]:
    """Get enabled plugins sorted by priority.

    Lower priority values execute first.
    Plugins are instantiated and configured.

    Returns:
        List of configured plugin instances
    """
    configs = load_plugin_config()
    builtin_classes = _get_builtin_plugins()

    plugins: list[tuple[int, BasePlugin]] = []

    for name, plugin_cls in builtin_classes.items():
        config = configs.get(name, PluginConfig())

        if not config.enabled:
            continue

        try:
            plugin = plugin_cls()
            plugin.configure(config.settings)
            plugins.append((config.priority, plugin))
        except Exception as e:
            logger.warning(f"Failed to instantiate plugin '{name}': {e}")

    # Sort by priority (lower first)
    plugins.sort(key=lambda x: x[0])
    return [p for _, p in plugins]


def get_plugins_for_event(event: WatcherEvent) -> list[BasePlugin]:
    """Get enabled plugins that handle a specific event type.

    Args:
        event: Event to find handlers for

    Returns:
        List of plugins that subscribe to this event type
    """
    all_plugins = get_enabled_plugins()
    return [p for p in all_plugins if p.accepts_event(event)]
