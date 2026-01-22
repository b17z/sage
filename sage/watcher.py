"""Compaction watcher daemon.

Tails the Claude Code JSONL transcript and watches for compaction events.
When detected, writes a continuity marker for the next session.

Architecture:
- Daemon process watches transcript file
- On isCompactSummary: true, extracts summary and writes marker
- Marker picked up by MCP server on next tool call

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
from typing import Optional

from sage.config import SAGE_DIR
from sage.continuity import mark_for_continuity

logger = logging.getLogger(__name__)

# Daemon state files
PID_FILE = SAGE_DIR / "watcher.pid"
LOG_FILE = SAGE_DIR / "logs" / "watcher.log"

# Polling interval for file watching (seconds)
POLL_INTERVAL = 0.2

# Maximum line length to prevent memory exhaustion from malformed input
MAX_LINE_LENGTH = 10_000_000  # 10MB should be plenty for any summary


class WatcherError(Exception):
    """Error in watcher operations."""

    pass


def find_active_transcript() -> Optional[Path]:
    """Find the most recently modified Claude Code transcript.

    Looks in ~/.claude/projects/ for .jsonl files and returns
    the most recently modified one.

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


def _handle_compaction(summary: str) -> None:
    """Handle detected compaction event.

    Args:
        summary: The compaction summary from Claude Code
    """
    _log_to_file(f"Compaction detected! Summary length: {len(summary)}")

    result = mark_for_continuity(
        reason="post_compaction",
        compaction_summary=summary,
    )

    if result.ok:
        _log_to_file(f"Continuity marker written: {result.unwrap()}")
    else:
        _log_to_file(f"Failed to write marker: {result.unwrap_err().message}")


def watch_transcript(transcript_path: Path) -> None:
    """Tail the transcript and watch for compaction events.

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

    # Set up signal handlers for clean shutdown
    shutdown_requested = False

    def handle_shutdown(signum, frame):
        nonlocal shutdown_requested
        shutdown_requested = True
        _log_to_file("Shutdown signal received")

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    try:
        with open(transcript_path, "r") as f:
            # Seek to end - we only care about new events
            f.seek(0, 2)

            while not shutdown_requested:
                line = f.readline()

                if not line:
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
                            _handle_compaction(summary)
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
    except PermissionError:
        _log_to_file(f"Permission denied reading transcript: {transcript_path}")
    except OSError as e:
        _log_to_file(f"Error reading transcript: {e}")

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


def start_daemon() -> bool:
    """Start the watcher as a background daemon.

    Uses fork() to daemonize. Not available on Windows.

    Returns:
        True if daemon started successfully, False otherwise

    Security:
        - Runs as user's own process
        - PID file has restricted permissions
        - Proper cleanup on exit
    """
    if is_running():
        return False  # Already running

    transcript = find_active_transcript()
    if not transcript:
        _log_to_file("No transcript found, cannot start")
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
