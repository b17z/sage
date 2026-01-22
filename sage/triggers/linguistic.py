"""Linguistic trigger detection via pattern matching.

Detects checkpoint-worthy moments through keyword and phrase patterns.
This complements structural detection (embeddings) in the 70/30 hybrid.

Patterns are organized by trigger type and prioritized to reduce noise.
Code blocks, quotes, and meta-discussion are filtered out.
"""

import re
from dataclasses import dataclass

from .types import (
    Trigger,
    TriggerType,
    TriggerSource,
    Confidence,
)


# =============================================================================
# Pattern Definitions
# =============================================================================

# Topic shift patterns - highest signal
TOPIC_SHIFT_PATTERNS = [
    r"moving on to",
    r"let.?s (now )?turn to",
    r"shifting (focus|gears)",
    r"on a (different|separate) note",
    r"changing topics?",
    r"now.*let.?s (look at|consider)",
    r"switching to",
    r"next topic",
    r"different subject",
]

# Branch point patterns - decision points
BRANCH_POINT_PATTERNS = [
    r"we could (either|go with)",
    r"two (main )?approaches",
    r"option (a|b|1|2|one|two)",
    r"alternatively[,.]",
    r"on one hand.*on the other",
    r"trade-?off",
    r"versus",
    r"choice between",
    r"fork in",
    r"either.*or",
    r"multiple (options|approaches|paths)",
]

# Constraint patterns - blockers discovered
CONSTRAINT_PATTERNS = [
    r"this means we can.?t",
    r"won.?t work because",
    r"unfortunately.*limit",
    r"blocked by",
    r"show-?stopper",
    r"deal-?breaker",
    r"rules out",
    r"eliminates the possibility",
    r"can.?t do.*because",
    r"fundamental limitation",
    r"not (possible|feasible)",
]

# Synthesis patterns - conclusions reached
SYNTHESIS_PATTERNS = [
    r"in conclusion",
    r"putting (this|these|it all) together",
    r"this suggests that",
    r"combining these",
    r"taken together",
    r"synthesizing",
    r"the key (insight|takeaway)",
    r"overall[,.]",
    r"in summary",
    r"bottom line",
    r"the honest truth",
    r"my (take|recommendation|verdict)",
    r"if i were (starting|building)",
    r"to summarize",
    r"tl;?dr",
]

# Meta-discussion patterns - filter these out (they're about the system, not research)
META_PATTERNS = [
    r"(hook|checkpoint|trigger|pattern|detector|cooldown|sage_autosave).*(fire|detect|block|test)",
    r"test.*summary",
    r"trigger.*loop",
    r"calling sage",
    r"checkpoint system",
]


# =============================================================================
# Content Filtering
# =============================================================================

def _strip_code_and_quotes(text: str) -> str:
    """Remove code blocks, inline code, quotes, and blockquotes.

    These often contain keywords that aren't relevant to the actual
    conversation context. E.g., discussing code that contains "option".

    Args:
        text: Raw message content

    Returns:
        Text with code/quotes stripped
    """
    # Remove fenced code blocks (```...```)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)

    # Remove inline code (`...`)
    text = re.sub(r"`[^`]+`", "", text)

    # Remove double-quoted strings
    text = re.sub(r'"[^"]*"', "", text)

    # Remove blockquotes (lines starting with >)
    text = re.sub(r"^>.*$", "", text, flags=re.MULTILINE)

    return text


def _is_meta_discussion(text: str) -> bool:
    """Check if text is discussing the trigger/checkpoint system itself.

    Meta-discussion about how the system works shouldn't trigger checkpoints.

    Args:
        text: Message content (lowercase)

    Returns:
        True if this appears to be meta-discussion
    """
    text_lower = text.lower()
    for pattern in META_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


# =============================================================================
# Pattern Matching
# =============================================================================

@dataclass(frozen=True)
class PatternMatch:
    """Result of a pattern match attempt."""
    matched: bool
    pattern: str | None = None
    match_text: str | None = None


def _match_patterns(text: str, patterns: list[str]) -> PatternMatch:
    """Check if text matches any pattern in the list.

    Args:
        text: Text to search (should be lowercase, stripped)
        patterns: List of regex patterns

    Returns:
        PatternMatch with details if matched
    """
    text_lower = text.lower()
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return PatternMatch(
                matched=True,
                pattern=pattern,
                match_text=match.group(0),
            )
    return PatternMatch(matched=False)


def detect_linguistic_trigger(
    content: str,
    role: str = "assistant",
) -> Trigger | None:
    """Detect triggers through linguistic pattern matching.

    Checks message content against known trigger patterns for each type.
    Filters out code blocks, quotes, and meta-discussion first.

    Args:
        content: Message text
        role: "user" or "assistant" (some patterns only apply to assistant)

    Returns:
        Trigger if pattern matched, None otherwise
    """
    # Skip empty content
    if not content or not content.strip():
        return None

    # Filter out code and quotes
    stripped = _strip_code_and_quotes(content)

    # Skip meta-discussion
    if _is_meta_discussion(stripped):
        return None

    # Check patterns in priority order (most actionable first)

    # 1. Topic shift - checkpoint before losing context
    match = _match_patterns(stripped, TOPIC_SHIFT_PATTERNS)
    if match.matched:
        return Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.7),  # Linguistic alone = moderate confidence
            source=TriggerSource.LINGUISTIC,
            reason=f"Pattern matched: '{match.match_text}'",
        )

    # 2. Branch point - decision pending
    match = _match_patterns(stripped, BRANCH_POINT_PATTERNS)
    if match.matched:
        return Trigger(
            type=TriggerType.BRANCH_POINT,
            confidence=Confidence(0.7),
            source=TriggerSource.LINGUISTIC,
            reason=f"Pattern matched: '{match.match_text}'",
        )

    # 3. Constraint - blocker discovered
    match = _match_patterns(stripped, CONSTRAINT_PATTERNS)
    if match.matched:
        return Trigger(
            type=TriggerType.CONSTRAINT,
            confidence=Confidence(0.7),
            source=TriggerSource.LINGUISTIC,
            reason=f"Pattern matched: '{match.match_text}'",
        )

    # 4. Synthesis - conclusion reached (lowest priority, catch-all)
    match = _match_patterns(stripped, SYNTHESIS_PATTERNS)
    if match.matched:
        return Trigger(
            type=TriggerType.SYNTHESIS,
            confidence=Confidence(0.6),  # Lower confidence for synthesis (more common phrases)
            source=TriggerSource.LINGUISTIC,
            reason=f"Pattern matched: '{match.match_text}'",
        )

    return None


def get_all_patterns() -> dict[TriggerType, list[str]]:
    """Get all patterns organized by trigger type.

    Useful for debugging and testing.

    Returns:
        Dict mapping trigger types to their pattern lists
    """
    return {
        TriggerType.TOPIC_SHIFT: TOPIC_SHIFT_PATTERNS,
        TriggerType.BRANCH_POINT: BRANCH_POINT_PATTERNS,
        TriggerType.CONSTRAINT: CONSTRAINT_PATTERNS,
        TriggerType.SYNTHESIS: SYNTHESIS_PATTERNS,
    }
