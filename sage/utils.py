"""Utility functions for Sage.

Small, reusable functions that don't fit elsewhere.
"""


def estimate_tokens(text: str) -> int:
    """Estimate token count for text.

    Uses the common approximation of 1 token ≈ 4 characters.
    This is a rough estimate suitable for budgeting and display.

    For exact counts, use the API's count_tokens method in sage.client.

    Args:
        text: Text to estimate tokens for

    Returns:
        Estimated token count

    Example:
        >>> estimate_tokens("Hello, world!")
        3
        >>> estimate_tokens("a" * 400)
        100
    """
    if not text:
        return 0
    return len(text) // 4


# Common ratio used across the codebase
CHARS_PER_TOKEN = 4
