"""Salience detector for transcript content.

Pattern-based detection of important content in conversation transcripts.
Used by the recovery checkpoint system to identify what's worth preserving.

Inspired by Claude Cortex patterns for detecting meaningful moments:
- Decisions made
- Problems resolved
- Open threads identified
- Constraints discovered
- Synthesis achieved

Architecture:
- Pattern matching with salience scores
- Content filtering (skip code blocks, quotes)
- Significance threshold for triggering saves
"""

import re
from dataclasses import dataclass

# Salience patterns grouped by category with scores
# Higher score = more likely to be checkpoint-worthy
SALIENCE_PATTERNS: dict[str, tuple[list[str], float]] = {
    # Decisions (0.9) - explicit choices made
    "decision": (
        [
            r"\b(?:decided to|going with|chose|we'll use|I'll use)\b",
            r"\b(?:the approach is|the solution is|let's go with)\b",
            r"\b(?:I recommend|my recommendation is)\b",
            r"\b(?:after considering|weighing the options)\b",
        ],
        0.9,
    ),
    # Resolutions (0.9) - problems solved
    "resolution": (
        [
            r"\b(?:fixed by|the fix is|the solution was|resolved)\b",
            r"\b(?:root cause|the issue was|the problem was)\b",
            r"\b(?:this solves|this fixes|that worked)\b",
            r"\b(?:the answer is|the reason is)\b",
        ],
        0.9,
    ),
    # Open threads (0.8) - unfinished work
    "open_thread": (
        [
            r"\b(?:TODO|FIXME|XXX)\b",
            r"\b(?:next step|next steps|need to|should also)\b",
            r"\b(?:remaining work|still need|haven't yet)\b",
            r"\b(?:follow up|follow-up|later we should)\b",
            r"\b(?:we could also|might want to)\b",
        ],
        0.8,
    ),
    # Constraints (0.8) - blockers and limitations
    "constraint": (
        [
            r"\b(?:the problem is|the issue is|blocked by)\b",
            r"\b(?:won't work because|can't do|limitation)\b",
            r"\b(?:constraint|requirement|must have)\b",
            r"\b(?:breaking change|backwards compatibility)\b",
            r"\b(?:security concern|performance concern)\b",
        ],
        0.8,
    ),
    # Synthesis (0.7) - summarization and conclusions
    "synthesis": (
        [
            r"\b(?:in summary|to summarize|in conclusion)\b",
            r"\b(?:therefore|so the answer|the key insight)\b",
            r"\b(?:the main point|the takeaway|overall)\b",
            r"\b(?:putting it together|combining these)\b",
        ],
        0.7,
    ),
    # Discoveries (0.7) - new learnings
    "discovery": (
        [
            r"\b(?:found that|discovered that|realized)\b",
            r"\b(?:turns out|it appears|interesting)\b",
            r"\b(?:the key is|the trick is|importantly)\b",
            r"\b(?:TIL|learned that|now I understand)\b",
        ],
        0.7,
    ),
    # Tradeoffs (0.6) - explicit tradeoff discussions
    "tradeoff": (
        [
            r"\b(?:tradeoff|trade-off|pros and cons)\b",
            r"\b(?:on one hand|on the other hand)\b",
            r"\b(?:advantage|disadvantage)\b",
            r"\b(?:at the cost of|but then|however)\b",
        ],
        0.6,
    ),
    # Questions (0.5) - open questions
    "question": (
        [
            r"\?\s*$",  # Ends with question mark
            r"\b(?:wondering|curious|unclear)\b",
            r"\b(?:not sure|unsure|uncertain)\b",
            r"\b(?:question is|need to understand)\b",
        ],
        0.5,
    ),
}


@dataclass(frozen=True)
class SalientContent:
    """A piece of salient content from the transcript.

    Attributes:
        category: The pattern category that matched
        text: The text that was matched
        salience: Salience score (0.0-1.0)
        context: Surrounding text for context
    """

    category: str
    text: str
    salience: float
    context: str = ""


def _preprocess_text(text: str) -> str:
    """Remove code blocks and quoted content for pattern matching.

    Args:
        text: Raw text content

    Returns:
        Preprocessed text with code/quotes removed
    """
    # Remove fenced code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)

    # Remove inline code
    text = re.sub(r"`[^`]+`", "", text)

    # Remove blockquotes (lines starting with >)
    lines = text.split("\n")
    lines = [line for line in lines if not line.strip().startswith(">")]
    text = "\n".join(lines)

    return text


def _extract_context(text: str, match: re.Match, context_chars: int = 100) -> str:
    """Extract surrounding context for a match.

    Args:
        text: Full text
        match: Regex match object
        context_chars: Number of chars before/after to include

    Returns:
        Context string with the match highlighted
    """
    start = max(0, match.start() - context_chars)
    end = min(len(text), match.end() + context_chars)

    # Find sentence boundaries
    context = text[start:end]

    # Trim to sentence boundaries if possible
    if start > 0:
        first_period = context.find(". ")
        if first_period > 0 and first_period < len(context) // 2:
            context = context[first_period + 2 :]

    if end < len(text):
        last_period = context.rfind(". ")
        if last_period > len(context) // 2:
            context = context[: last_period + 1]

    return context.strip()


def extract_salient_content(
    text: str,
    min_salience: float = 0.0,
) -> list[SalientContent]:
    """Extract salient content from text using pattern matching.

    Args:
        text: Text to analyze
        min_salience: Minimum salience score to include

    Returns:
        List of SalientContent sorted by salience (highest first)
    """
    if not text or not text.strip():
        return []

    # Preprocess to remove code/quotes
    processed = _preprocess_text(text)

    results: list[SalientContent] = []
    seen_texts: set[str] = set()  # Deduplicate matches

    for category, (patterns, salience) in SALIENCE_PATTERNS.items():
        if salience < min_salience:
            continue

        for pattern in patterns:
            try:
                for match in re.finditer(pattern, processed, re.IGNORECASE | re.MULTILINE):
                    matched_text = match.group(0)

                    # Deduplicate
                    if matched_text.lower() in seen_texts:
                        continue
                    seen_texts.add(matched_text.lower())

                    context = _extract_context(processed, match)

                    results.append(
                        SalientContent(
                            category=category,
                            text=matched_text,
                            salience=salience,
                            context=context,
                        )
                    )
            except re.error:
                # Skip invalid patterns
                continue

    # Sort by salience (highest first)
    results.sort(key=lambda x: x.salience, reverse=True)

    return results


def is_significant(
    content: list[SalientContent],
    threshold: float = 0.7,
    min_count: int = 1,
) -> bool:
    """Check if content is significant enough for checkpointing.

    Args:
        content: List of salient content items
        threshold: Minimum salience score to consider significant
        min_count: Minimum number of items above threshold

    Returns:
        True if content is significant enough
    """
    if not content:
        return False

    high_salience_count = sum(1 for item in content if item.salience >= threshold)
    return high_salience_count >= min_count


def get_max_salience(content: list[SalientContent]) -> float:
    """Get the maximum salience score from content.

    Args:
        content: List of salient content items

    Returns:
        Maximum salience score, or 0.0 if empty
    """
    if not content:
        return 0.0
    return max(item.salience for item in content)


def categorize_content(
    content: list[SalientContent],
) -> dict[str, list[SalientContent]]:
    """Group salient content by category.

    Args:
        content: List of salient content items

    Returns:
        Dict mapping category to items in that category
    """
    categories: dict[str, list[SalientContent]] = {}

    for item in content:
        if item.category not in categories:
            categories[item.category] = []
        categories[item.category].append(item)

    return categories


def extract_decisions(content: list[SalientContent]) -> list[str]:
    """Extract just the decision-related contexts.

    Args:
        content: List of salient content items

    Returns:
        List of decision context strings
    """
    return [item.context for item in content if item.category == "decision"]


def extract_open_threads(content: list[SalientContent]) -> list[str]:
    """Extract just the open thread contexts.

    Args:
        content: List of salient content items

    Returns:
        List of open thread context strings
    """
    return [item.context for item in content if item.category == "open_thread"]


def extract_resolutions(content: list[SalientContent]) -> list[str]:
    """Extract just the resolution contexts.

    Args:
        content: List of salient content items

    Returns:
        List of resolution context strings
    """
    return [item.context for item in content if item.category == "resolution"]


def summarize_salience(text: str) -> dict[str, int]:
    """Get a count of salient items by category.

    Useful for quick overview of content significance.

    Args:
        text: Text to analyze

    Returns:
        Dict mapping category to count
    """
    content = extract_salient_content(text)
    categories = categorize_content(content)
    return {cat: len(items) for cat, items in categories.items()}
