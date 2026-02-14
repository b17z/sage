"""Compaction watcher daemon with recovery checkpoint generation.

Tails the Claude Code JSONL transcript and watches for compaction events.
When detected, generates a recovery checkpoint and writes a continuity marker.

Also watches the checkpoints directory for new files (from Claude or external).

Architecture:
- Daemon process watches transcript file
- Also watches checkpoints directory for new .md files
- Periodically extracts observations from new content
- On isCompactSummary: true, generates recovery checkpoint
- Recovery checkpoint saved alongside structured checkpoints
- Continuity marker written for next session
- Session tracking scopes checkpoint injection

Usage:
    sage watcher start   # Start in background
    sage watcher stop    # Stop daemon
    sage watcher status  # Check if running

Security:
- PID file has restricted permissions (0o600)
- Log file has restricted permissions (0o600)
- No arbitrary code execution from JSONL
- Validates paths before use
- Proper signal handling for clean shutdown
- Runs as user's own process (no privilege escalation)
"""

import atexit
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from sage.config import SAGE_DIR, detect_project_root, get_sage_config
from sage.continuity import mark_for_continuity

logger = logging.getLogger(__name__)

# Daemon state files
PID_FILE = SAGE_DIR / "watcher.pid"
LOG_FILE = SAGE_DIR / "logs" / "watcher.log"
CURSOR_FILE = SAGE_DIR / "watcher_cursor.json"

# Polling interval for file watching (seconds)
POLL_INTERVAL = 0.2

# Checkpoint directory poll interval (less frequent)
CHECKPOINT_POLL_INTERVAL = 2.0

# Observation extraction interval (seconds of new content)
OBSERVATION_INTERVAL = 30.0

# Maximum line length to prevent memory exhaustion from malformed input
MAX_LINE_LENGTH = 10_000_000  # 10MB should be plenty for any summary


class WatcherError(Exception):
    """Error in watcher operations."""

    pass


class CheckpointWatcher:
    """Watches the checkpoints directory for new files.

    Emits CheckpointFileCreated events when new checkpoint files appear.
    Uses polling to avoid platform-specific file watching APIs.
    """

    def __init__(self, checkpoints_dir: Path):
        """Initialize the checkpoint watcher.

        Args:
            checkpoints_dir: Directory to watch for new checkpoints
        """
        self._dir = checkpoints_dir
        self._known_files: set[str] = set()
        self._initialized = False

    def initialize(self) -> None:
        """Scan existing files so we don't emit events for them."""
        if self._dir.exists():
            self._known_files = {f.name for f in self._dir.glob("*.md")}
        self._initialized = True
        _log_to_file(f"Checkpoint watcher initialized: {len(self._known_files)} existing files")

    def check_for_new_files(self) -> list[Path]:
        """Check for new checkpoint files.

        Returns:
            List of paths to new checkpoint files
        """
        if not self._initialized:
            self.initialize()
            return []

        if not self._dir.exists():
            return []

        current_files = {f.name for f in self._dir.glob("*.md")}
        new_files = current_files - self._known_files

        if new_files:
            self._known_files = current_files
            return [self._dir / name for name in new_files]

        return []

    @staticmethod
    def infer_checkpoint_type(filename: str) -> str:
        """Infer checkpoint type from filename.

        Args:
            filename: Name of the checkpoint file

        Returns:
            "recovery" if filename contains "_recovery-", else "structured"
        """
        if "_recovery-" in filename:
            return "recovery"
        return "structured"


def _project_path_to_dir_name(project_path: Path) -> str:
    """Convert a project path to Claude's directory name format.

    Claude Code names project directories by replacing / and . with - in the path.
    Example: /Users/be.nvy/sage -> -Users-be-nvy-sage

    Args:
        project_path: Absolute path to project directory

    Returns:
        Directory name as Claude Code would create it
    """
    # Resolve to absolute path
    resolved = project_path.resolve()
    # Replace / and . with - (Claude's naming scheme)
    return str(resolved).replace("/", "-").replace(".", "-")


def find_active_transcript(project_path: Path | None = None) -> Path | None:
    """Find the most recently modified Claude Code transcript.

    If project_path is provided, only looks in that project's directory.
    Otherwise, looks across all projects for the most recent transcript.

    Args:
        project_path: Optional path to limit search to a specific project

    Returns:
        Path to active transcript, or None if not found

    Security:
        - Only looks in expected Claude directory
        - Returns resolved path (no symlink following outside)
    """
    claude_projects = Path.home() / ".claude" / "projects"

    if not claude_projects.exists():
        return None

    # Security: resolve to real path, ensure still under claude_projects
    claude_projects = claude_projects.resolve()

    # If project_path specified, only look in that project's directory
    if project_path is not None:
        project_dir_name = _project_path_to_dir_name(project_path)
        project_dir = claude_projects / project_dir_name

        if not project_dir.exists():
            logger.debug(f"Project directory not found: {project_dir}")
            return None

        transcripts = list(project_dir.glob("*.jsonl"))
        if not transcripts:
            return None

        return max(transcripts, key=lambda p: p.stat().st_mtime)

    # Global search across all projects
    transcripts = []
    for jsonl in claude_projects.glob("*/*.jsonl"):
        # Resolve and verify it's under the expected directory
        resolved = jsonl.resolve()
        try:
            resolved.relative_to(claude_projects)
            transcripts.append(resolved)
        except ValueError:
            # Path escaped claude_projects via symlink, skip
            logger.warning(f"Skipping transcript outside expected directory: {jsonl}")
            continue

    if not transcripts:
        return None

    return max(transcripts, key=lambda p: p.stat().st_mtime)


def _log_to_file(message: str) -> None:
    """Append message to watcher log file.

    Security:
        - Creates log directory with restricted permissions
        - Log file has restricted permissions (0o600)
    """
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.parent.chmod(0o700)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"[{timestamp}] {message}\n")

        # Ensure log file has restricted permissions
        LOG_FILE.chmod(0o600)
    except OSError:
        pass  # Best effort logging


def _generate_recovery_checkpoint(transcript_path: Path, trigger: str = "pre_compact") -> bool:
    """Generate a recovery checkpoint from the current transcript.

    Extracts salient content from the conversation and saves a recovery
    checkpoint that can be used if no structured checkpoint exists.

    Args:
        transcript_path: Path to the transcript file
        trigger: What triggered this generation

    Returns:
        True if checkpoint was saved successfully
    """
    try:
        from sage.recovery import (
            extract_recovery_checkpoint,
            save_recovery_checkpoint,
        )
        from sage.transcript import read_full_transcript

        # Read transcript from beginning for full context on compaction
        # (recovery checkpoint needs full conversation context)
        window = read_full_transcript(transcript_path, max_entries=500)

        if window.is_empty:
            _log_to_file("Empty transcript, skipping recovery checkpoint")
            return False

        # Get config for extraction method
        config = get_sage_config()
        use_claude = getattr(config, "recovery_use_claude", False)

        # Extract recovery checkpoint
        checkpoint = extract_recovery_checkpoint(
            window=window,
            trigger=trigger,
            use_claude=use_claude,
        )

        # Save to project-local or global
        project_root = detect_project_root()
        save_recovery_checkpoint(checkpoint, project_path=project_root)

        _log_to_file(
            f"Recovery checkpoint saved: {checkpoint.id} "
            f"(salience: {checkpoint.salience_score:.2f})"
        )
        return True

    except ImportError as e:
        _log_to_file(f"Recovery modules not available: {e}")
        return False
    except Exception as e:
        _log_to_file(f"Failed to generate recovery checkpoint: {e}")
        return False


def _load_cursor_state() -> dict | None:
    """Load cursor state from file."""
    if not CURSOR_FILE.exists():
        return None

    try:
        with open(CURSOR_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_cursor_state(transcript_path: str, position: int) -> None:
    """Save cursor state to file."""
    try:
        CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "file_path": transcript_path,
            "position": position,
            "last_read": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with open(CURSOR_FILE, "w") as f:
            json.dump(data, f)
        CURSOR_FILE.chmod(0o600)
    except OSError as e:
        _log_to_file(f"Failed to save cursor state: {e}")


def _handle_compaction(summary: str, transcript_path: Path | None = None) -> None:
    """Handle detected compaction event.

    Dispatches to the plugin system for handling.
    Falls back to direct handling if plugins unavailable.

    Args:
        summary: The compaction summary from Claude Code
        transcript_path: Path to the transcript for recovery extraction
    """
    _log_to_file(f"Compaction detected! Summary length: {len(summary)}")

    try:
        from datetime import UTC, datetime

        from sage.plugins import execute_actions, get_plugins_for_event
        from sage.plugins.events import CompactionDetected

        # Create event
        event = CompactionDetected(
            timestamp=datetime.now(UTC).isoformat(),
            summary=summary,
            transcript_path=str(transcript_path) if transcript_path else "",
        )

        # Dispatch to plugins
        plugins = get_plugins_for_event(event)
        if plugins:
            for plugin in plugins:
                result = plugin.handle(event)
                execute_actions(result)
            return

        # No plugins enabled, fall through to legacy handling
        _log_to_file("No plugins enabled, using legacy handling")

    except ImportError as e:
        _log_to_file(f"Plugin system unavailable: {e}")
    except Exception as e:
        _log_to_file(f"Plugin dispatch failed: {e}")

    # Legacy fallback: direct handling
    if transcript_path:
        _generate_recovery_checkpoint(transcript_path, trigger="pre_compact")

    # Get project root for project-scoped continuity marker
    project_root = detect_project_root()

    result = mark_for_continuity(
        reason="post_compaction",
        compaction_summary=summary,
        project_dir=project_root,
    )

    if result.ok:
        _log_to_file(f"Continuity marker written: {result.unwrap()}")
    else:
        _log_to_file(f"Failed to write marker: {result.unwrap_err().message}")


def _emit_daemon_started(transcript_path: Path) -> None:
    """Emit DaemonStarted event to plugins."""
    try:
        from datetime import UTC, datetime

        from sage.plugins import execute_actions, get_plugins_for_event
        from sage.plugins.events import DaemonStarted

        event = DaemonStarted(
            timestamp=datetime.now(UTC).isoformat(),
            transcript_path=str(transcript_path),
            pid=os.getpid(),
        )

        for plugin in get_plugins_for_event(event):
            result = plugin.handle(event)
            execute_actions(result)

    except ImportError:
        pass  # Plugin system not available
    except Exception as e:
        _log_to_file(f"Failed to emit DaemonStarted: {e}")


def _emit_daemon_stopping(reason: str) -> None:
    """Emit DaemonStopping event to plugins."""
    try:
        from datetime import UTC, datetime

        from sage.plugins import execute_actions, get_plugins_for_event
        from sage.plugins.events import DaemonStopping

        event = DaemonStopping(
            timestamp=datetime.now(UTC).isoformat(),
            reason=reason,
        )

        for plugin in get_plugins_for_event(event):
            result = plugin.handle(event)
            # Use blocking=True for shutdown to ensure actions complete
            execute_actions(result, blocking=True)

    except ImportError:
        pass  # Plugin system not available
    except Exception as e:
        _log_to_file(f"Failed to emit DaemonStopping: {e}")


def _emit_checkpoint_file_created(file_path: Path) -> None:
    """Emit CheckpointFileCreated event to plugins."""
    try:
        from datetime import UTC, datetime

        from sage.plugins import execute_actions, get_plugins_for_event
        from sage.plugins.events import CheckpointFileCreated

        checkpoint_type = CheckpointWatcher.infer_checkpoint_type(file_path.name)

        event = CheckpointFileCreated(
            timestamp=datetime.now(UTC).isoformat(),
            file_path=str(file_path),
            checkpoint_id=file_path.stem,
            checkpoint_type=checkpoint_type,
        )

        for plugin in get_plugins_for_event(event):
            result = plugin.handle(event)
            execute_actions(result)

    except ImportError:
        pass  # Plugin system not available
    except Exception as e:
        _log_to_file(f"Failed to emit CheckpointFileCreated: {e}")


def watch_transcript(transcript_path: Path) -> None:
    """Tail the transcript and watch for compaction events.

    Also watches the checkpoints directory for new files.
    Runs indefinitely until interrupted. On SIGTERM/SIGINT,
    exits cleanly.

    Args:
        transcript_path: Path to the JSONL transcript file

    Security:
        - Validates JSON before processing
        - Limits line length to prevent memory exhaustion
        - No arbitrary code execution from transcript content
    """
    _log_to_file(f"Watching: {transcript_path}")

    # Emit daemon started event
    _emit_daemon_started(transcript_path)

    # Set up checkpoint directory watcher
    project_root = detect_project_root()
    if project_root:
        checkpoints_dir = project_root / ".sage" / "checkpoints"
    else:
        checkpoints_dir = SAGE_DIR / "checkpoints"

    checkpoint_watcher = CheckpointWatcher(checkpoints_dir)
    checkpoint_watcher.initialize()
    last_checkpoint_poll = time.time()

    # Set up signal handlers for clean shutdown
    shutdown_requested = False

    def handle_shutdown(signum, frame):
        nonlocal shutdown_requested
        shutdown_requested = True
        _log_to_file("Shutdown signal received")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        with open(transcript_path) as f:
            # Seek to end - we only care about new events
            f.seek(0, 2)

            while not shutdown_requested:
                line = f.readline()

                if not line:
                    # No new transcript content - check for new checkpoints
                    now = time.time()
                    if now - last_checkpoint_poll >= CHECKPOINT_POLL_INTERVAL:
                        last_checkpoint_poll = now
                        for new_file in checkpoint_watcher.check_for_new_files():
                            _log_to_file(f"New checkpoint detected: {new_file.name}")
                            _emit_checkpoint_file_created(new_file)

                    time.sleep(POLL_INTERVAL)
                    continue

                # Security: limit line length
                if len(line) > MAX_LINE_LENGTH:
                    _log_to_file(f"Skipping oversized line: {len(line)} bytes")
                    continue

                try:
                    data = json.loads(line)

                    # Check for compaction signal
                    # Only process if it has the expected structure
                    if (
                        isinstance(data, dict)
                        and data.get("isCompactSummary") is True
                        and isinstance(data.get("message"), dict)
                    ):
                        summary = data["message"].get("content", "")

                        # Validate summary is a string
                        if isinstance(summary, str):
                            _handle_compaction(summary, transcript_path)
                        else:
                            _log_to_file("Compaction summary not a string, skipping")

                except json.JSONDecodeError:
                    # Normal for partial lines or non-JSON content
                    continue
                except (KeyError, TypeError) as e:
                    _log_to_file(f"Unexpected data structure: {e}")
                    continue

    except FileNotFoundError:
        _log_to_file(f"Transcript file not found: {transcript_path}")
        _emit_daemon_stopping("file_not_found")
    except PermissionError:
        _log_to_file(f"Permission denied reading transcript: {transcript_path}")
        _emit_daemon_stopping("permission_denied")
    except OSError as e:
        _log_to_file(f"Error reading transcript: {e}")
        _emit_daemon_stopping("os_error")

    # Emit stopping event for clean shutdown
    if shutdown_requested:
        _emit_daemon_stopping("signal")

    _log_to_file("Watcher stopped")


def _write_pid_file(pid: int) -> None:
    """Write PID to file with restricted permissions.

    Security:
        - PID file has 0o600 permissions
        - Directory has 0o700 permissions
    """
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.parent.chmod(0o700)
    PID_FILE.write_text(str(pid))
    PID_FILE.chmod(0o600)


def _remove_pid_file() -> None:
    """Remove PID file on exit."""
    try:
        PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def start_daemon(project_path: Path | None = None, force_restart: bool = False) -> bool:
    """Start the watcher as a background daemon.

    Uses fork() to daemonize. Not available on Windows.

    Args:
        project_path: Optional project path to scope transcript search.
                      If provided, only watches transcripts from this project.
        force_restart: If True, stop existing watcher before starting.
                       Use this when switching projects.

    Returns:
        True if daemon started successfully, False otherwise

    Security:
        - Runs as user's own process
        - PID file has restricted permissions
        - Proper cleanup on exit
    """
    if is_running():
        if force_restart:
            stop_daemon()
        else:
            return False  # Already running

    transcript = find_active_transcript(project_path)
    if not transcript:
        _log_to_file(f"No transcript found for project {project_path}, cannot start")
        return False

    # Check platform
    if sys.platform == "win32":
        _log_to_file("Daemon mode not supported on Windows")
        return False

    # Fork to background
    try:
        pid = os.fork()
    except OSError as e:
        _log_to_file(f"Fork failed: {e}")
        return False

    if pid > 0:
        # Parent process: write PID and exit function
        _write_pid_file(pid)
        return True

    # Child process: become daemon
    try:
        os.setsid()  # Create new session

        # Fork again to prevent zombie processes
        pid = os.fork()
        if pid > 0:
            # Exit first child
            os._exit(0)

        # Second child continues as daemon
        # Update PID file with actual daemon PID
        _write_pid_file(os.getpid())

        # Register cleanup
        atexit.register(_remove_pid_file)

        # Close standard file descriptors
        sys.stdin.close()

        # Redirect stdout/stderr to log
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log_fd = os.open(str(LOG_FILE), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.dup2(log_fd, sys.stdout.fileno())
        os.dup2(log_fd, sys.stderr.fileno())

        # Start watching
        watch_transcript(transcript)

    except Exception as e:
        _log_to_file(f"Daemon startup failed: {e}")
        os._exit(1)

    os._exit(0)


def stop_daemon() -> bool:
    """Stop the watcher daemon.

    Sends SIGTERM to the daemon process.

    Returns:
        True if daemon was stopped, False if not running
    """
    if not PID_FILE.exists():
        return False

    try:
        pid = int(PID_FILE.read_text().strip())

        # Validate PID is reasonable
        if pid <= 0:
            PID_FILE.unlink(missing_ok=True)
            return False

        # Send SIGTERM
        os.kill(pid, signal.SIGTERM)

        # Wait briefly for process to exit
        for _ in range(10):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)  # Check if still alive
            except ProcessLookupError:
                break  # Process exited

        PID_FILE.unlink(missing_ok=True)
        return True

    except (ValueError, ProcessLookupError):
        # Invalid PID or process doesn't exist
        PID_FILE.unlink(missing_ok=True)
        return False
    except PermissionError:
        # Can't kill the process (not ours?)
        return False


def is_running() -> bool:
    """Check if watcher daemon is running.

    Returns:
        True if daemon is running (process exists and is ours)
    """
    if not PID_FILE.exists():
        return False

    try:
        pid = int(PID_FILE.read_text().strip())

        if pid <= 0:
            return False

        # Check if process exists
        os.kill(pid, 0)
        return True

    except (ValueError, ProcessLookupError, PermissionError):
        return False


def get_watcher_status() -> dict:
    """Get detailed watcher status.

    Returns:
        Dict with running status, PID, transcript path, etc.
    """
    status = {
        "running": False,
        "pid": None,
        "transcript": None,
        "log_file": str(LOG_FILE),
    }

    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            status["pid"] = pid

            # Check if actually running
            os.kill(pid, 0)
            status["running"] = True
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    transcript = find_active_transcript()
    if transcript:
        status["transcript"] = str(transcript)

    return status
