"""Type definitions for trigger detection.

Immutable dataclasses representing triggers and message state.
Following functional patterns: frozen dataclasses, typed enums.
"""

from dataclasses import dataclass
from enum import Enum
from typing import NewType

import numpy as np


class TriggerType(str, Enum):
    """Types of checkpoint-worthy moments.

    Each type represents a distinct reason to checkpoint:
    - TOPIC_SHIFT: Conversation moved to a new subject
    - SYNTHESIS: Research converged to a conclusion
    - BRANCH_POINT: Multiple options identified, decision pending
    - CONSTRAINT: Blocker or limitation discovered
    """
    TOPIC_SHIFT = "topic_shift"
    SYNTHESIS = "synthesis"
    BRANCH_POINT = "branch_point"
    CONSTRAINT = "constraint_discovered"


class TriggerSource(str, Enum):
    """Origin of the trigger signal.

    Used to understand why a trigger fired:
    - STRUCTURAL: Embedding-based detection (topic drift, convergence)
    - LINGUISTIC: Pattern matching (keywords, phrases)
    - COMBINED: Both structural and linguistic signals
    """
    STRUCTURAL = "structural"
    LINGUISTIC = "linguistic"
    COMBINED = "structural+linguistic"


# Confidence score between 0 and 1
Confidence = NewType("Confidence", float)


@dataclass(frozen=True)
class Trigger:
    """A detected checkpoint-worthy moment.

    Immutable record of a trigger event with its confidence and source.

    Attributes:
        type: What kind of inflection point was detected
        confidence: How confident we are (0.0-1.0)
        source: Whether structural, linguistic, or combined
        reason: Human-readable explanation for debugging
    """
    type: TriggerType
    confidence: Confidence
    source: TriggerSource
    reason: str

    def __post_init__(self) -> None:
        """Validate confidence is in valid range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")


@dataclass(frozen=True)
class MessageBuffer:
    """A message in the conversation buffer with computed embedding.

    Stores the message content along with its embedding for similarity
    calculations. Tracks role (user/assistant) and whether it's a question.

    Attributes:
        content: The message text (truncated if very long)
        embedding: Pre-computed embedding vector
        role: "user" or "assistant"
        is_question: Whether message appears to be a question
    """
    content: str
    embedding: np.ndarray
    role: str
    is_question: bool

    def __hash__(self) -> int:
        """Custom hash since numpy arrays aren't hashable."""
        return hash((self.content, self.role, self.is_question))

    def __eq__(self, other: object) -> bool:
        """Custom equality comparison."""
        if not isinstance(other, MessageBuffer):
            return False
        return (
            self.content == other.content
            and self.role == other.role
            and self.is_question == other.is_question
            and np.array_equal(self.embedding, other.embedding)
        )


@dataclass(frozen=True)
class TriggerResult:
    """Result of analyzing a message for triggers.

    Contains both structural and linguistic signals separately,
    allowing the combiner to apply the 70/30 weighting.

    Attributes:
        structural: Trigger from embedding-based detection (may be None)
        linguistic: Trigger from pattern matching (may be None)
        combined_score: Final score after 70/30 weighting
        should_trigger: Whether combined score exceeds threshold
    """
    structural: Trigger | None
    linguistic: Trigger | None
    combined_score: Confidence
    should_trigger: bool

    @property
    def trigger(self) -> Trigger | None:
        """Get the final trigger if should_trigger is True."""
        if not self.should_trigger:
            return None

        # Prefer structural for the type, but note the combined source
        if self.structural and self.linguistic:
            return Trigger(
                type=self.structural.type,
                confidence=self.combined_score,
                source=TriggerSource.COMBINED,
                reason=f"{self.structural.reason}; confirmed by: {self.linguistic.reason}"
            )
        elif self.structural:
            return self.structural
        elif self.linguistic:
            return self.linguistic
        return None


# Constants for the 70/30 hybrid scoring (matching knowledge recall)
EMBEDDING_WEIGHT: float = 0.7
KEYWORD_WEIGHT: float = 0.3

# Default trigger threshold - lower than knowledge (0.70) because:
# - False negatives (missing checkpoints) are worse than false positives
# - Extra checkpoints can be deleted; missed insights are lost forever
# - With 70/30 weighting, keywords alone max at 0.30
# - Pure structural needs ~0.86 to trigger alone (0.86 * 0.7 = 0.60)
DEFAULT_TRIGGER_THRESHOLD: float = 0.60
