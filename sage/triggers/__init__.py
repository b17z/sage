"""Trigger detection for checkpoint-worthy moments.

This module provides structural (embedding-based) and linguistic (pattern-based)
detection of inflection points in conversations that warrant checkpoints.

Usage:
    from sage.triggers import TriggerDetector, TriggerType

    detector = TriggerDetector()

    # Analyze messages as they come in
    for message in conversation:
        result = detector.analyze(message.content, message.role)
        if result.should_trigger:
            trigger = result.trigger
            print(f"Checkpoint: {trigger.type} ({trigger.confidence:.0%})")

The 70/30 hybrid approach:
- 70% weight on structural signals (embeddings, topic drift)
- 30% weight on linguistic signals (keyword patterns)
- Linguistic alone can't trigger (too noisy)
- Structural alone can trigger if confident enough
- Both together create high confidence

Configurable thresholds in sage config:
- trigger_threshold: Combined score needed to trigger (default 0.60)
- topic_drift_threshold: Similarity threshold for topic change (default 0.50)
- convergence_question_drop: Question ratio drop for synthesis (default 0.20)
"""

from .types import (
    Trigger,
    TriggerType,
    TriggerSource,
    TriggerResult,
    MessageBuffer,
    Confidence,
    EMBEDDING_WEIGHT,
    KEYWORD_WEIGHT,
    DEFAULT_TRIGGER_THRESHOLD,
)
from .structural import (
    StructuralDetector,
    detect_topic_drift,
    detect_convergence,
)
from .linguistic import (
    detect_linguistic_trigger,
    get_all_patterns,
)
from .combiner import (
    TriggerDetector,
    combine_signals,
    should_checkpoint,
    analyze_for_trigger,
)

__all__ = [
    # Types
    "Trigger",
    "TriggerType",
    "TriggerSource",
    "TriggerResult",
    "MessageBuffer",
    "Confidence",
    # Constants
    "EMBEDDING_WEIGHT",
    "KEYWORD_WEIGHT",
    "DEFAULT_TRIGGER_THRESHOLD",
    # Structural detection
    "StructuralDetector",
    "detect_topic_drift",
    "detect_convergence",
    # Linguistic detection
    "detect_linguistic_trigger",
    "get_all_patterns",
    # Combined detection
    "TriggerDetector",
    "combine_signals",
    "should_checkpoint",
    "analyze_for_trigger",
]
