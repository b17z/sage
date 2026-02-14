"""Action executor for watcher daemon plugins.

Executes actions returned by plugins. Actions are data-only descriptions
that are interpreted and executed by trusted code here.

Security:
- Only whitelisted action types are executed
- No arbitrary code execution
- All handlers validate parameters
- Fire-and-forget uses daemon threads for non-blocking execution
"""

import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sage.plugins.base import ALLOWED_ACTION_TYPES, PluginAction, PluginResult

logger = logging.getLogger(__name__)


def _log_to_watcher_file(message: str) -> None:
    """Append message to watcher log file.

    Mirrors the _log_to_file function in watcher.py.
    """
    from sage.config import SAGE_DIR

    log_file = SAGE_DIR / "logs" / "watcher.log"

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        log_file.parent.chmod(0o700)

        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] {message}\n")

        log_file.chmod(0o600)
    except OSError:
        pass  # Best effort logging


def _execute_log(params: dict[str, Any]) -> None:
    """Execute a log action.

    Parameters:
        message (str): Message to log
        level (str, optional): Log level (debug, info, warning, error)
    """
    message = params.get("message", "")
    level = params.get("level", "info").lower()

    if not isinstance(message, str) or not message:
        logger.warning("log action: missing or invalid 'message' parameter")
        return

    # Log to both Python logger and watcher file
    log_fn = getattr(logger, level, logger.info)
    log_fn(f"[plugin] {message}")
    _log_to_watcher_file(f"[plugin] {message}")


def _execute_save_recovery(params: dict[str, Any]) -> None:
    """Execute a save_recovery action.

    Parameters:
        transcript_path (str): Path to transcript file
        trigger (str, optional): What triggered the recovery
    """
    transcript_path = params.get("transcript_path")
    trigger = params.get("trigger", "pre_compact")

    if not transcript_path:
        logger.warning("save_recovery action: missing 'transcript_path' parameter")
        return

    try:
        from sage.config import detect_project_root, get_sage_config
        from sage.recovery import extract_recovery_checkpoint, save_recovery_checkpoint
        from sage.transcript import read_full_transcript

        transcript = Path(transcript_path)
        if not transcript.exists():
            logger.warning(f"save_recovery action: transcript not found: {transcript_path}")
            return

        # Read transcript
        window = read_full_transcript(transcript, max_entries=500)

        if window.is_empty:
            logger.debug("save_recovery action: empty transcript, skipping")
            return

        # Get config for extraction
        config = get_sage_config()
        use_claude = getattr(config, "recovery_use_claude", False)

        # Extract and save
        checkpoint = extract_recovery_checkpoint(
            window=window,
            trigger=trigger,
            use_claude=use_claude,
        )

        project_root = detect_project_root()
        save_recovery_checkpoint(checkpoint, project_path=project_root)

        _log_to_watcher_file(
            f"Recovery checkpoint saved: {checkpoint.id} "
            f"(salience: {checkpoint.salience_score:.2f})"
        )

    except ImportError as e:
        logger.warning(f"save_recovery action: import error: {e}")
    except Exception as e:
        logger.warning(f"save_recovery action: failed: {e}")


def _execute_write_marker(params: dict[str, Any]) -> None:
    """Execute a write_marker action.

    Parameters:
        reason (str): Reason for the marker
        compaction_summary (str, optional): Summary from compaction
    """
    reason = params.get("reason", "post_compaction")
    compaction_summary = params.get("compaction_summary")

    try:
        from sage.config import detect_project_root
        from sage.continuity import mark_for_continuity

        # Get project root for project-scoped continuity marker
        project_root = detect_project_root()

        result = mark_for_continuity(
            reason=reason,
            compaction_summary=compaction_summary,
            project_dir=project_root,
        )

        if result.ok:
            _log_to_watcher_file(f"Continuity marker written: {result.unwrap()}")
        else:
            _log_to_watcher_file(f"Failed to write marker: {result.unwrap_err().message}")

    except Exception as e:
        logger.warning(f"write_marker action: failed: {e}")


def _execute_queue_for_injection(params: dict[str, Any]) -> None:
    """Execute a queue_for_injection action.

    Uses session-scoped queue from sage.session module.

    Parameters:
        checkpoint_id (str): ID of checkpoint to queue
        checkpoint_type (str): Type of checkpoint
    """
    checkpoint_id = params.get("checkpoint_id")
    checkpoint_type = params.get("checkpoint_type", "unknown")

    if not checkpoint_id:
        logger.warning("queue_for_injection action: missing 'checkpoint_id' parameter")
        return

    try:
        from sage.session import queue_checkpoint

        success = queue_checkpoint(
            checkpoint_id=checkpoint_id,
            checkpoint_type=checkpoint_type,
        )

        if success:
            _log_to_watcher_file(f"Queued checkpoint for injection: {checkpoint_id}")
        else:
            _log_to_watcher_file(f"Failed to queue checkpoint (no session): {checkpoint_id}")

    except Exception as e:
        logger.warning(f"queue_for_injection action: failed: {e}")


def _execute_start_session(params: dict[str, Any]) -> None:
    """Execute a start_session action.

    Parameters:
        transcript_path (str): Path to transcript being watched
    """
    transcript_path = params.get("transcript_path", "")

    try:
        from sage.session import start_session

        session = start_session(transcript_path)
        _log_to_watcher_file(f"Session started: {session.session_id}")

    except Exception as e:
        logger.warning(f"start_session action: failed: {e}")


def _execute_end_session(params: dict[str, Any]) -> None:
    """Execute an end_session action.

    Parameters:
        reason (str, optional): Why the session is ending
    """
    reason = params.get("reason", "unknown")

    try:
        from sage.session import end_session

        end_session()
        _log_to_watcher_file(f"Session ended: {reason}")

    except Exception as e:
        logger.warning(f"end_session action: failed: {e}")


# Action handlers mapping
ACTION_HANDLERS = {
    "log": _execute_log,
    "save_recovery": _execute_save_recovery,
    "write_marker": _execute_write_marker,
    "queue_for_injection": _execute_queue_for_injection,
    "start_session": _execute_start_session,
    "end_session": _execute_end_session,
}


def _execute_action(action: PluginAction) -> None:
    """Execute a single action.

    Args:
        action: Action to execute

    Raises:
        ValueError: If action type is unknown
    """
    if action.action_type not in ACTION_HANDLERS:
        raise ValueError(f"Unknown action type: {action.action_type}")

    handler = ACTION_HANDLERS[action.action_type]
    handler(action.parameters)


def execute_actions(result: PluginResult, blocking: bool = False) -> None:
    """Execute all actions in a plugin result.

    Args:
        result: PluginResult containing actions
        blocking: If True, execute synchronously. If False, fire-and-forget.
    """
    for action in result.actions:
        if blocking:
            try:
                _execute_action(action)
            except Exception as e:
                logger.warning(f"Action execution failed: {e}")
        else:
            # Fire-and-forget in daemon thread
            def _wrapper(a: PluginAction = action) -> None:
                try:
                    _execute_action(a)
                except Exception as e:
                    logger.warning(f"Background action execution failed: {e}")

            thread = threading.Thread(target=_wrapper, daemon=True)
            thread.start()


def validate_action_types() -> bool:
    """Verify all allowed action types have handlers.

    Returns:
        True if all action types have handlers
    """
    for action_type in ALLOWED_ACTION_TYPES:
        if action_type not in ACTION_HANDLERS:
            logger.error(f"Missing handler for action type: {action_type}")
            return False
    return True
