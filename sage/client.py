"""Anthropic API client for Sage.

Handles API interactions with retry logic and streaming.
"""

import time
from dataclasses import dataclass
from typing import Callable, Iterator

import anthropic

from sage.config import Config
from sage.errors import Result, SageError, api_error, api_key_missing, err, ok


@dataclass(frozen=True)
class Message:
    """A message in the conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass(frozen=True)
class ApiResponse:
    """Response from the API."""

    content: str
    tokens_in: int
    tokens_out: int
    cache_read: int
    cache_write: int
    searches: int
    stop_reason: str


def create_client(config: Config) -> Result[anthropic.Anthropic, SageError]:
    """Create an Anthropic client."""
    if not config.api_key:
        return err(api_key_missing())

    try:
        client = anthropic.Anthropic(api_key=config.api_key)
        return ok(client)
    except Exception as e:
        return err(api_error(str(e)))


def send_message(
    client: anthropic.Anthropic,
    system: str,
    messages: list[Message],
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 4096,
    enable_search: bool = True,
    on_text: Callable[[str], None] | None = None,
) -> Result[ApiResponse, SageError]:
    """Send a message to the API with streaming.

    Args:
        client: Anthropic client
        system: System prompt
        messages: Conversation history
        model: Model to use
        max_tokens: Maximum tokens to generate
        enable_search: Enable web search tool
        on_text: Callback for streaming text chunks
    """
    # Build message list
    api_messages = [{"role": m.role, "content": m.content} for m in messages]

    # Build tools
    tools = []
    if enable_search:
        tools.append({
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 10,
        })

    # Make request with retry
    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            content_parts = []
            usage = None
            stop_reason = None
            search_count = 0

            with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=api_messages,
                tools=tools if tools else anthropic.NOT_GIVEN,
            ) as stream:
                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                text = event.delta.text
                                content_parts.append(text)
                                if on_text:
                                    on_text(text)
                        elif event.type == "message_delta":
                            if hasattr(event, "usage"):
                                usage = event.usage
                            stop_reason = getattr(event.delta, "stop_reason", None)
                        elif event.type == "content_block_start":
                            # Track tool use for search counting
                            if hasattr(event.content_block, "type"):
                                if event.content_block.type == "tool_use":
                                    if getattr(event.content_block, "name", "") == "web_search":
                                        search_count += 1

                # Get final message for complete usage stats
                final = stream.get_final_message()
                usage = final.usage

            # Extract cache stats
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0

            return ok(ApiResponse(
                content="".join(content_parts),
                tokens_in=usage.input_tokens,
                tokens_out=usage.output_tokens,
                cache_read=cache_read,
                cache_write=cache_write,
                searches=search_count,
                stop_reason=stop_reason or "end_turn",
            ))

        except anthropic.RateLimitError as e:
            last_error = e
            wait_time = 2 ** attempt
            time.sleep(wait_time)
            continue

        except anthropic.APIStatusError as e:
            return err(api_error(f"API error: {e.status_code} - {e.message}"))

        except anthropic.APIConnectionError as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(1)
                continue
            return err(api_error(f"Connection error: {e}"))

        except Exception as e:
            return err(api_error(str(e)))

    return err(api_error(f"Max retries exceeded: {last_error}"))


def count_tokens(client: anthropic.Anthropic, text: str, model: str = "claude-sonnet-4-20250514") -> int:
    """Count tokens in text. Returns rough estimate if API fails."""
    try:
        result = client.messages.count_tokens(
            model=model,
            messages=[{"role": "user", "content": text}],
        )
        return result.input_tokens
    except Exception:
        # Rough estimate: 1 token ≈ 4 characters
        return len(text) // 4
