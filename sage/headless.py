"""Headless Claude integration for recovery checkpoint extraction.

Optional higher-quality extraction using Claude CLI in headless mode.
Falls back to local extraction if Claude is not available.

Security:
- Uses --dangerously-skip-permissions for non-interactive operation
- Content is sanitized before sending
- Timeouts prevent hanging
- No arbitrary code execution
"""

import json
import logging
import shutil
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

# Maximum content length to send to Claude (tokens ~ chars/4)
MAX_CONTENT_LENGTH = 100_000  # ~25k tokens

# Timeout for Claude CLI execution (seconds)
EXTRACTION_TIMEOUT = 60

# Extraction prompt template - matches structured checkpoint schema
EXTRACTION_PROMPT = '''You are extracting a research checkpoint from a conversation transcript.

Extract the following:

1. CORE_QUESTION: What decision or action is this work driving toward? (1 sentence)
2. THESIS: Current synthesized position or conclusion (1-2 sentences)
3. CONFIDENCE: How confident in the thesis? (0.0-1.0, where 0.5=uncertain, 0.9=highly confident)
4. OPEN_QUESTIONS: What remains unknown or needs more work? (list, max 5)
5. DECISIONS: Key decisions made during this session (list, max 5)
6. TOPIC: Brief topic slug for identification (3-5 words, lowercase, hyphens)

Respond in this exact JSON format:
{{
    "core_question": "...",
    "thesis": "...",
    "confidence": 0.7,
    "open_questions": ["...", "..."],
    "decisions": ["...", "..."],
    "topic": "implementing-auth-flow"
}}

Transcript:
{content}
'''


def is_claude_available() -> bool:
    """Check if Claude CLI is available.

    Returns:
        True if 'claude' command is found in PATH
    """
    return shutil.which("claude") is not None


def _sanitize_content(content: str) -> str:
    """Sanitize content for Claude extraction.

    Truncates and removes potentially problematic content.

    Args:
        content: Raw transcript content

    Returns:
        Sanitized content safe for extraction
    """
    # Truncate to max length (take from end - more recent is more relevant)
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[-MAX_CONTENT_LENGTH:]
        # Find first complete sentence
        first_period = content.find(". ")
        if first_period > 0 and first_period < len(content) // 4:
            content = content[first_period + 2 :]

    # Remove any potential prompt injection attempts
    # (Though Claude is robust, extra caution doesn't hurt)
    content = content.replace("IMPORTANT:", "[IMPORTANT]")
    content = content.replace("CRITICAL:", "[CRITICAL]")
    content = content.replace("IGNORE PREVIOUS", "[IGNORE PREVIOUS]")

    return content


def _parse_claude_response(output: str) -> dict[str, Any] | None:
    """Parse Claude's JSON response.

    Args:
        output: Claude CLI stdout

    Returns:
        Parsed dict or None if parsing fails
    """
    # Find JSON in response
    try:
        # Look for JSON block
        start = output.find("{")
        end = output.rfind("}") + 1

        if start >= 0 and end > start:
            json_str = output[start:end]
            return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse Claude response as JSON: {e}")

    return None


def extract_with_claude(
    transcript_content: str,
    model: str = "haiku",
    timeout: int = EXTRACTION_TIMEOUT,
) -> dict[str, Any] | None:
    """Extract recovery checkpoint content using Claude CLI.

    Runs Claude in headless mode to extract structured information
    from the conversation transcript.

    Args:
        transcript_content: Raw transcript content
        model: Claude model to use (haiku recommended for speed/cost)
        timeout: Maximum seconds to wait

    Returns:
        Dict with topic, decisions, open_threads, summary
        None if extraction fails
    """
    if not is_claude_available():
        logger.warning("Claude CLI not available")
        return None

    # Sanitize content
    content = _sanitize_content(transcript_content)

    if not content.strip():
        logger.warning("Empty content after sanitization")
        return None

    # Build prompt
    prompt = EXTRACTION_PROMPT.format(content=content)

    # Run Claude CLI
    try:
        result = subprocess.run(
            [
                "claude",
                "--dangerously-skip-permissions",
                "--print",
                "--model", model,
                "-p", prompt,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            logger.warning(f"Claude CLI failed: {result.stderr}")
            return None

        # Parse response
        return _parse_claude_response(result.stdout)

    except subprocess.TimeoutExpired:
        logger.warning(f"Claude CLI timed out after {timeout}s")
        return None
    except FileNotFoundError:
        logger.warning("Claude CLI not found")
        return None
    except Exception as e:
        logger.warning(f"Claude extraction error: {e}")
        return None


def get_claude_version() -> str | None:
    """Get the installed Claude CLI version.

    Returns:
        Version string or None if not available
    """
    if not is_claude_available():
        return None

    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:  # Best-effort version check - don't crash on any error
        logger.debug("Could not get Claude version: %s", e)

    return None
