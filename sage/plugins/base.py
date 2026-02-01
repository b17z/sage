"""Base classes for watcher daemon plugins.

Plugins are built-in Python classes that handle watcher events.
They return actions that describe what to do - no arbitrary code execution.

Security:
- Only whitelisted action types are allowed
- Actions are data-only, executed by trusted executor
- No user-provided code execution
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

from sage.plugins.events import WatcherEvent

# Whitelist of allowed action types
# These are the only actions plugins can request
ALLOWED_ACTION_TYPES = frozenset(
    {
        "log",  # Write to watcher log
        "save_recovery",  # Save a recovery checkpoint
        "write_marker",  # Write continuity marker
        "queue_for_injection",  # Add checkpoint to injection queue (session-scoped)
        "start_session",  # Start a new watcher session
        "end_session",  # End the current session
    }
)


@dataclass(frozen=True)
class PluginAction:
    """An action for the executor to perform.

    Actions are data-only descriptions of what to do.
    The executor is responsible for actually performing them.

    Attributes:
        action_type: Type of action (must be in ALLOWED_ACTION_TYPES)
        parameters: Action-specific parameters

    Raises:
        ValueError: If action_type is not in ALLOWED_ACTION_TYPES
    """

    action_type: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate action type on creation."""
        if self.action_type not in ALLOWED_ACTION_TYPES:
            raise ValueError(
                f"Invalid action type '{self.action_type}'. "
                f"Allowed types: {sorted(ALLOWED_ACTION_TYPES)}"
            )


@dataclass(frozen=True)
class PluginResult:
    """Result returned by a plugin after handling an event.

    Contains zero or more actions to be executed.
    Immutable to prevent modification after creation.

    Attributes:
        actions: Tuple of actions to execute
    """

    actions: tuple[PluginAction, ...] = ()

    @classmethod
    def empty(cls) -> "PluginResult":
        """Create an empty result (no actions)."""
        return cls(actions=())

    @classmethod
    def single(cls, action: PluginAction) -> "PluginResult":
        """Create a result with a single action."""
        return cls(actions=(action,))

    @classmethod
    def from_actions(cls, *actions: PluginAction) -> "PluginResult":
        """Create a result from multiple actions."""
        return cls(actions=actions)


class BasePlugin(ABC):
    """Abstract base class for watcher daemon plugins.

    Plugins must declare:
    - name: Unique identifier for the plugin
    - subscribes_to: Tuple of event types this plugin handles

    Plugins implement:
    - handle(): Process an event and return actions

    Optionally:
    - configure(): Apply configuration settings
    """

    # Class variables that subclasses must define
    name: ClassVar[str]
    subscribes_to: ClassVar[tuple[type, ...]]

    @abstractmethod
    def handle(self, event: WatcherEvent) -> PluginResult:
        """Handle an event and return actions to execute.

        Args:
            event: The event to handle (will be one of subscribes_to types)

        Returns:
            PluginResult with actions to execute
        """
        ...

    def configure(self, config: dict[str, Any]) -> None:
        """Apply configuration settings to this plugin.

        Called after plugin instantiation with user config.
        Default implementation does nothing.

        Args:
            config: Plugin-specific configuration dict
        """
        pass

    def accepts_event(self, event: WatcherEvent) -> bool:
        """Check if this plugin handles events of this type.

        Args:
            event: Event to check

        Returns:
            True if this plugin subscribes to this event type
        """
        return isinstance(event, self.subscribes_to)
