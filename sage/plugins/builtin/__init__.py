"""Built-in plugins for the watcher daemon.

These are the only plugins that can be loaded by the plugin system.
User-provided plugins are not supported for security reasons.
"""

from sage.plugins.builtin.checkpoint_queue import CheckpointQueuePlugin
from sage.plugins.builtin.recovery import RecoveryPlugin
from sage.plugins.builtin.session import SessionPlugin

__all__ = ["RecoveryPlugin", "CheckpointQueuePlugin", "SessionPlugin"]
