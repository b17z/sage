"""Watcher daemon plugin system.

Provides a plugin architecture for extending watcher daemon behavior.
Plugins are built-in Python classes that handle events and return actions.

Security:
- Only built-in plugins are supported (no user-provided code)
- Plugin names are validated against a whitelist
- Actions are data-only, executed by trusted handlers

Usage:
    from sage.plugins import get_plugins_for_event, execute_actions
    from sage.plugins.events import CompactionDetected

    event = CompactionDetected(
        timestamp="2024-01-01T00:00:00Z",
        summary="Conversation compacted...",
        transcript_path="/path/to/transcript.jsonl",
    )

    for plugin in get_plugins_for_event(event):
        result = plugin.handle(event)
        execute_actions(result)
"""

from sage.plugins.base import (
    ALLOWED_ACTION_TYPES,
    BasePlugin,
    PluginAction,
    PluginResult,
)
from sage.plugins.events import (
    CheckpointCreated,
    CheckpointFileCreated,
    CompactionDetected,
    DaemonStarted,
    DaemonStopping,
    WatcherEvent,
)
from sage.plugins.executor import execute_actions, validate_action_types
from sage.plugins.registry import (
    BUILTIN_PLUGIN_NAMES,
    PluginConfig,
    get_enabled_plugins,
    get_plugins_for_event,
    load_plugin_config,
    save_plugin_config,
)

__all__ = [
    # Events
    "WatcherEvent",
    "DaemonStarted",
    "DaemonStopping",
    "CompactionDetected",
    "CheckpointCreated",
    "CheckpointFileCreated",
    # Base classes
    "BasePlugin",
    "PluginAction",
    "PluginResult",
    "ALLOWED_ACTION_TYPES",
    # Registry
    "PluginConfig",
    "BUILTIN_PLUGIN_NAMES",
    "load_plugin_config",
    "save_plugin_config",
    "get_enabled_plugins",
    "get_plugins_for_event",
    # Executor
    "execute_actions",
    "validate_action_types",
]
