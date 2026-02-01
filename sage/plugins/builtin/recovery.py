"""Recovery checkpoint plugin for the watcher daemon.

Generates recovery checkpoints when compaction is detected.
This is the core functionality extracted from watcher.py into the plugin system.

The plugin:
1. Listens for CompactionDetected events
2. Generates a recovery checkpoint from the transcript
3. Writes a continuity marker for the next session
"""

from typing import Any, ClassVar

from sage.plugins.base import BasePlugin, PluginAction, PluginResult
from sage.plugins.events import CompactionDetected, WatcherEvent


class RecoveryPlugin(BasePlugin):
    """Plugin that generates recovery checkpoints on compaction.

    Configuration options (via plugins.yaml):
        enabled: bool - Whether plugin is active (default: True)
        settings:
            salience_threshold: float - Minimum salience to save (default: 0.5)
    """

    name: ClassVar[str] = "recovery"
    subscribes_to: ClassVar[tuple[type, ...]] = (CompactionDetected,)

    def __init__(self) -> None:
        """Initialize plugin with default settings."""
        self._salience_threshold: float = 0.5

    def configure(self, config: dict[str, Any]) -> None:
        """Apply configuration settings.

        Args:
            config: Settings dict from plugins.yaml
        """
        if "salience_threshold" in config:
            threshold = config["salience_threshold"]
            if isinstance(threshold, (int, float)) and 0.0 <= threshold <= 1.0:
                self._salience_threshold = float(threshold)

    def handle(self, event: WatcherEvent) -> PluginResult:
        """Handle a compaction event.

        Generates actions to:
        1. Save a recovery checkpoint
        2. Write a continuity marker

        Args:
            event: The event to handle

        Returns:
            PluginResult with save_recovery and write_marker actions
        """
        if not isinstance(event, CompactionDetected):
            return PluginResult.empty()

        actions = [
            # First save the recovery checkpoint
            PluginAction(
                action_type="save_recovery",
                parameters={
                    "transcript_path": event.transcript_path,
                    "trigger": "pre_compact",
                },
            ),
            # Then write the continuity marker
            PluginAction(
                action_type="write_marker",
                parameters={
                    "reason": "post_compaction",
                    "compaction_summary": event.summary,
                },
            ),
            # Log the event
            PluginAction(
                action_type="log",
                parameters={
                    "message": f"Compaction detected, summary length: {len(event.summary)}",
                    "level": "info",
                },
            ),
        ]

        return PluginResult.from_actions(*actions)
