"""Session lifecycle plugin for the watcher daemon.

Manages session start/end and tracks session boundaries.
Sessions scope checkpoint injection to relevant time periods.

The plugin:
1. On DaemonStarted: Starts a new session
2. On DaemonStopping: Ends the current session
3. On CompactionDetected: Logs compaction (session continues)
4. On SessionChanged: Marks for continuity injection on new session
"""

from typing import ClassVar

from sage.plugins.base import BasePlugin, PluginAction, PluginResult
from sage.plugins.events import (
    CompactionDetected,
    DaemonStarted,
    DaemonStopping,
    SessionChanged,
    WatcherEvent,
)


class SessionPlugin(BasePlugin):
    """Plugin that manages session lifecycle.

    Configuration options (via plugins.yaml):
        enabled: bool - Whether plugin is active (default: True)
        priority: int - Should run BEFORE other plugins (default: 10)
    """

    name: ClassVar[str] = "session"
    subscribes_to: ClassVar[tuple[type, ...]] = (
        DaemonStarted,
        DaemonStopping,
        CompactionDetected,
        SessionChanged,
    )

    def handle(self, event: WatcherEvent) -> PluginResult:
        """Handle session-related events.

        Args:
            event: The event to handle

        Returns:
            PluginResult with session actions
        """
        match event:
            case DaemonStarted():
                return self._handle_daemon_started(event)
            case DaemonStopping():
                return self._handle_daemon_stopping(event)
            case CompactionDetected():
                return self._handle_compaction(event)
            case SessionChanged():
                return self._handle_session_changed(event)
            case _:
                return PluginResult.empty()

    def _handle_daemon_started(self, event: DaemonStarted) -> PluginResult:
        """Start a new session when daemon starts.

        Args:
            event: DaemonStarted event

        Returns:
            PluginResult with start_session action
        """
        return PluginResult.from_actions(
            PluginAction(
                action_type="start_session",
                parameters={
                    "transcript_path": event.transcript_path,
                },
            ),
            PluginAction(
                action_type="log",
                parameters={
                    "message": f"Session plugin: starting session for {event.transcript_path}",
                    "level": "info",
                },
            ),
        )

    def _handle_daemon_stopping(self, event: DaemonStopping) -> PluginResult:
        """End session when daemon stops.

        Args:
            event: DaemonStopping event

        Returns:
            PluginResult with end_session action
        """
        return PluginResult.from_actions(
            PluginAction(
                action_type="end_session",
                parameters={
                    "reason": event.reason,
                },
            ),
            PluginAction(
                action_type="log",
                parameters={
                    "message": f"Session plugin: ending session ({event.reason})",
                    "level": "info",
                },
            ),
        )

    def _handle_compaction(self, event: CompactionDetected) -> PluginResult:
        """End session on compaction (context reset).

        Note: A new session will start if the daemon continues running.
        The recovery plugin handles saving context before this.

        Args:
            event: CompactionDetected event

        Returns:
            PluginResult with end_session action
        """
        # Don't end session on compaction - we want checkpoints queued
        # DURING this session to be available for injection.
        # The session continues, and the queue is read on next tool call.
        return PluginResult.single(
            PluginAction(
                action_type="log",
                parameters={
                    "message": "Session plugin: compaction detected, session continues",
                    "level": "info",
                },
            ),
        )

    def _handle_session_changed(self, event: SessionChanged) -> PluginResult:
        """Handle new Claude Code session in the same project.

        This happens when the user kills Claude Code and starts fresh
        (not /compact, not --continue). We mark for continuity so the
        next sage_health() call can inject context from the last checkpoint.

        Args:
            event: SessionChanged event

        Returns:
            PluginResult with actions to mark continuity and restart session
        """
        return PluginResult.from_actions(
            # End current session
            PluginAction(
                action_type="end_session",
                parameters={
                    "reason": "session_changed",
                },
            ),
            # Mark for continuity injection
            PluginAction(
                action_type="write_marker",
                parameters={
                    "reason": "session_restart",
                },
            ),
            # Start new session for the new transcript
            PluginAction(
                action_type="start_session",
                parameters={
                    "transcript_path": event.new_transcript_path,
                },
            ),
            # Log the transition
            PluginAction(
                action_type="log",
                parameters={
                    "message": f"Session plugin: new Claude Code session detected, marked for continuity injection",
                    "level": "info",
                },
            ),
        )
