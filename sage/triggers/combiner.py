"""Trigger signal combiner with 70/30 hybrid scoring.

Combines structural (embedding-based) and linguistic (pattern-based)
signals using the same 70/30 weighting as knowledge recall.

Key insight: Linguistic signals alone are too noisy. Structural signals
provide the foundation; linguistic signals boost confidence.

Score formula:
    combined = 0.7 * structural + 0.3 * linguistic

This means:
- Pure structural (0.86+) can trigger alone: 0.86 * 0.7 = 0.60
- Pure linguistic maxes at 0.30: insufficient alone
- Both signals together create high confidence
"""

from dataclasses import dataclass

from sage.config import get_sage_config

from .types import (
    Trigger,
    TriggerType,
    TriggerSource,
    TriggerResult,
    Confidence,
    EMBEDDING_WEIGHT,
    KEYWORD_WEIGHT,
    DEFAULT_TRIGGER_THRESHOLD,
)
from .structural import StructuralDetector
from .linguistic import detect_linguistic_trigger


def combine_signals(
    structural: Trigger | None,
    linguistic: Trigger | None,
    threshold: float | None = None,
) -> TriggerResult:
    """Combine structural and linguistic signals using 70/30 weighting.

    The combined score determines whether to trigger a checkpoint.

    Weighting rationale (matching knowledge recall):
    - 70% structural: Embeddings capture semantic meaning reliably
    - 30% linguistic: Patterns provide confirmation, not initiation

    Args:
        structural: Trigger from embedding-based detection (may be None)
        linguistic: Trigger from pattern matching (may be None)
        threshold: Override trigger threshold (default from config)

    Returns:
        TriggerResult with combined score and trigger decision
    """
    if threshold is None:
        config = get_sage_config()
        threshold = getattr(config, 'trigger_threshold', DEFAULT_TRIGGER_THRESHOLD)

    # Extract confidence scores (0 if no trigger)
    structural_conf = structural.confidence if structural else 0.0
    linguistic_conf = linguistic.confidence if linguistic else 0.0

    # Apply 70/30 weighting
    combined_score = Confidence(
        EMBEDDING_WEIGHT * structural_conf + KEYWORD_WEIGHT * linguistic_conf
    )

    # Determine if we should trigger
    should_trigger = combined_score >= threshold

    return TriggerResult(
        structural=structural,
        linguistic=linguistic,
        combined_score=combined_score,
        should_trigger=should_trigger,
    )


def _select_best_trigger(triggers: list[Trigger]) -> Trigger | None:
    """Select the highest-confidence trigger from a list.

    When multiple triggers fire (e.g., topic_shift and synthesis),
    prefer the one with highest confidence.

    Args:
        triggers: List of triggered signals

    Returns:
        Highest confidence trigger, or None if list is empty
    """
    if not triggers:
        return None
    return max(triggers, key=lambda t: t.confidence)


@dataclass
class TriggerDetector:
    """Combined trigger detector with both structural and linguistic analysis.

    This is the main entry point for trigger detection. It maintains the
    structural detector's state and combines signals for final decisions.

    Usage:
        detector = TriggerDetector()
        result = detector.analyze("Let's move on to databases now", "assistant")
        if result.should_trigger:
            # Create checkpoint
            trigger = result.trigger
            print(f"Triggered: {trigger.type} with {trigger.confidence:.0%} confidence")

    Attributes:
        structural_detector: Maintains message buffer for embedding analysis
        threshold: Combined score threshold for triggering (configurable)
    """
    structural_detector: StructuralDetector | None = None
    threshold: float | None = None

    def __post_init__(self) -> None:
        """Initialize structural detector if not provided."""
        if self.structural_detector is None:
            self.structural_detector = StructuralDetector()

    def analyze(
        self,
        content: str,
        role: str,
    ) -> TriggerResult:
        """Analyze a message for checkpoint-worthy moments.

        Runs both structural and linguistic detection, then combines
        the signals using 70/30 weighting.

        Args:
            content: Message text
            role: "user" or "assistant"

        Returns:
            TriggerResult with analysis and trigger decision
        """
        # Get structural triggers (updates buffer internally)
        structural_triggers = self.structural_detector.analyze_message(content, role)
        structural = _select_best_trigger(structural_triggers)

        # Get linguistic trigger
        linguistic = detect_linguistic_trigger(content, role)

        # Combine signals
        return combine_signals(structural, linguistic, self.threshold)

    def clear_buffer(self) -> None:
        """Clear the message buffer (e.g., for new conversation)."""
        self.structural_detector.clear()

    def get_buffer_size(self) -> int:
        """Get current message buffer size."""
        return self.structural_detector.get_buffer_size()


# =============================================================================
# Convenience functions
# =============================================================================

def should_checkpoint(
    content: str,
    role: str,
    detector: TriggerDetector | None = None,
) -> tuple[bool, Trigger | None]:
    """Simple interface for checking if a checkpoint should be created.

    If no detector is provided, creates a stateless check (linguistic only).
    For full structural detection, maintain a TriggerDetector instance.

    Args:
        content: Message text
        role: "user" or "assistant"
        detector: Optional detector with message history

    Returns:
        Tuple of (should_trigger, trigger_info)
    """
    if detector:
        result = detector.analyze(content, role)
        return result.should_trigger, result.trigger
    else:
        # Stateless: linguistic only (limited, but no state required)
        linguistic = detect_linguistic_trigger(content, role)
        if linguistic:
            # Linguistic alone applies 30% weight
            combined_score = KEYWORD_WEIGHT * linguistic.confidence
            config = get_sage_config()
            threshold = getattr(config, 'trigger_threshold', DEFAULT_TRIGGER_THRESHOLD)
            # This will rarely trigger (0.3 * 0.7 = 0.21 max)
            should_trigger = combined_score >= threshold
            return should_trigger, linguistic if should_trigger else None
        return False, None


def analyze_for_trigger(
    content: str,
    role: str = "assistant",
    detector: TriggerDetector | None = None,
) -> dict:
    """Analyze content and return detailed trigger information.

    Useful for debugging and understanding why triggers fire or don't.

    Args:
        content: Message text
        role: "user" or "assistant"
        detector: Optional detector with message history

    Returns:
        Dict with structural, linguistic, combined score, and decision
    """
    if detector is None:
        detector = TriggerDetector()

    result = detector.analyze(content, role)

    return {
        "structural": {
            "detected": result.structural is not None,
            "type": result.structural.type.value if result.structural else None,
            "confidence": result.structural.confidence if result.structural else 0.0,
            "reason": result.structural.reason if result.structural else None,
        },
        "linguistic": {
            "detected": result.linguistic is not None,
            "type": result.linguistic.type.value if result.linguistic else None,
            "confidence": result.linguistic.confidence if result.linguistic else 0.0,
            "reason": result.linguistic.reason if result.linguistic else None,
        },
        "combined_score": result.combined_score,
        "threshold": detector.threshold or DEFAULT_TRIGGER_THRESHOLD,
        "should_trigger": result.should_trigger,
        "trigger": result.trigger.type.value if result.trigger else None,
    }
