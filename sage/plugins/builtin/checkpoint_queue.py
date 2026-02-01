"""Checkpoint queue plugin for the watcher daemon.

Maintains a queue of checkpoints for injection into future sessions.
Listens for CheckpointCreated, CheckpointFileCreated, and DaemonStarted events.

The plugin:
1. On CheckpointCreated/CheckpointFileCreated: Queues the checkpoint for later injection
2. On DaemonStarted: Logs current queue status
"""

from typing import Any, ClassVar

from sage.plugins.base import BasePlugin, PluginAction, PluginResult
from sage.plugins.events import (
    CheckpointCreated,
    CheckpointFileCreated,
    DaemonStarted,
    WatcherEvent,
)


class CheckpointQueuePlugin(BasePlugin):
    """Plugin that queues checkpoints for injection.

    Configuration options (via plugins.yaml):
        enabled: bool - Whether plugin is active (default: True)
        settings:
            max_queue_size: int - Maximum queue entries (default: 20)
    """

    name: ClassVar[str] = "checkpoint-queue"
    subscribes_to: ClassVar[tuple[type, ...]] = (
        CheckpointCreated,
        CheckpointFileCreated,
        DaemonStarted,
    )

    def __init__(self) -> None:
        """Initialize plugin with default settings."""
        self._max_queue_size: int = 20

    def configure(self, config: dict[str, Any]) -> None:
        """Apply configuration settings.

        Args:
            config: Settings dict from plugins.yaml
        """
        if "max_queue_size" in config:
            size = config["max_queue_size"]
            if isinstance(size, int) and size > 0:
                self._max_queue_size = size

    def handle(self, event: WatcherEvent) -> PluginResult:
        """Handle checkpoint-related events.

        Args:
            event: The event to handle

        Returns:
            PluginResult with appropriate actions
        """
        match event:
            case CheckpointCreated():
                return self._handle_checkpoint_created(event)
            case CheckpointFileCreated():
                return self._handle_checkpoint_file_created(event)
            case DaemonStarted():
                return self._handle_daemon_started(event)
            case _:
                return PluginResult.empty()

    def _handle_checkpoint_created(self, event: CheckpointCreated) -> PluginResult:
        """Handle a new checkpoint creation.

        Queues the checkpoint for later injection.

        Args:
            event: CheckpointCreated event

        Returns:
            PluginResult with queue action
        """
        return PluginResult.from_actions(
            PluginAction(
                action_type="queue_for_injection",
                parameters={
                    "checkpoint_id": event.checkpoint_id,
                    "checkpoint_type": event.checkpoint_type,
                },
            ),
            PluginAction(
                action_type="log",
                parameters={
                    "message": f"Queued {event.checkpoint_type} checkpoint: {event.checkpoint_id}",
                    "level": "info",
                },
            ),
        )

    def _handle_checkpoint_file_created(
        self, event: CheckpointFileCreated
    ) -> PluginResult:
        """Handle a new checkpoint file detected in directory.

        Queues the checkpoint for later injection.

        Args:
            event: CheckpointFileCreated event

        Returns:
            PluginResult with queue action
        """
        return PluginResult.from_actions(
            PluginAction(
                action_type="queue_for_injection",
                parameters={
                    "checkpoint_id": event.checkpoint_id,
                    "checkpoint_type": event.checkpoint_type,
                },
            ),
            PluginAction(
                action_type="log",
                parameters={
                    "message": f"Detected new {event.checkpoint_type} checkpoint: {event.checkpoint_id}",
                    "level": "info",
                },
            ),
        )

    def _handle_daemon_started(self, event: DaemonStarted) -> PluginResult:
        """Handle daemon start event.

        Logs queue status on startup.

        Args:
            event: DaemonStarted event

        Returns:
            PluginResult with log action
        """
        return PluginResult.single(
            PluginAction(
                action_type="log",
                parameters={
                    "message": f"Checkpoint queue plugin active (pid: {event.pid})",
                    "level": "info",
                },
            ),
        )
