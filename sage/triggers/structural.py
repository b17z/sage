"""Structural trigger detection via embeddings.

Detects checkpoint-worthy moments through semantic analysis:
- Topic drift: embedding similarity drop vs recent centroid
- Convergence: shift from questions to statements (synthesis)

Pure functions where possible. Detector class maintains message buffer
but uses immutable operations internally.
"""

from dataclasses import dataclass, field

import numpy as np

from sage.config import get_sage_config
from sage.embeddings import cosine_similarity, get_embedding

from .types import (
    Confidence,
    MessageBuffer,
    Trigger,
    TriggerSource,
    TriggerType,
)

# Buffer bounds to prevent memory exhaustion
MAX_BUFFER_SIZE = 50
MIN_BUFFER_FOR_DRIFT = 5
MIN_BUFFER_FOR_CONVERGENCE = 5

# Message length limits for security/performance
MAX_MESSAGE_LENGTH = 50_000  # Truncate very long messages


def _truncate_message(content: str) -> str:
    """Truncate message to prevent memory issues with embeddings."""
    if len(content) > MAX_MESSAGE_LENGTH:
        return content[:MAX_MESSAGE_LENGTH] + "... [truncated]"
    return content


def _is_question(text: str) -> bool:
    """Detect if text is a question.

    Simple heuristics:
    - Ends with question mark
    - Starts with question words

    Args:
        text: Message content

    Returns:
        True if text appears to be a question
    """
    text = text.strip()
    if not text:
        return False

    # Direct question mark
    if text.endswith("?"):
        return True

    # Question starters (case-insensitive)
    question_starters = (
        "what", "how", "why", "when", "where", "who", "which",
        "is", "are", "can", "could", "should", "would", "do", "does",
        "will", "has", "have", "did", "was", "were",
    )
    first_word = text.lower().split()[0] if text.split() else ""
    return first_word in question_starters


def detect_topic_drift(
    current_embedding: np.ndarray,
    recent_embeddings: list[np.ndarray],
    threshold: float,
) -> Trigger | None:
    """Detect topic shift via embedding similarity to recent centroid.

    Compares current message embedding against the centroid (mean) of
    recent messages. Low similarity indicates topic change.

    Args:
        current_embedding: Embedding of current message
        recent_embeddings: Embeddings of recent messages (last N)
        threshold: Similarity threshold (below = drift detected)

    Returns:
        Trigger if drift detected, None otherwise
    """
    if len(recent_embeddings) < MIN_BUFFER_FOR_DRIFT:
        return None

    # Compute centroid of recent messages
    centroid = np.mean(recent_embeddings, axis=0)
    similarity = cosine_similarity(current_embedding, centroid)

    if similarity < threshold:
        # Lower similarity = higher confidence in drift
        confidence = Confidence(1.0 - similarity)
        return Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=confidence,
            source=TriggerSource.STRUCTURAL,
            reason=f"Topic similarity dropped to {similarity:.2f} (threshold: {threshold:.2f})"
        )

    return None


def detect_convergence(
    recent_messages: list[MessageBuffer],
    current_is_question: bool,
    question_drop_threshold: float,
) -> Trigger | None:
    """Detect shift from questions to statements (synthesis moment).

    When users transition from asking questions (exploring) to making
    statements (concluding), it often indicates synthesis.

    Args:
        recent_messages: Recent message buffer
        current_is_question: Whether current message is a question
        question_drop_threshold: How much question ratio must drop

    Returns:
        Trigger if convergence detected, None otherwise
    """
    # Only check user messages for question patterns
    user_messages = [m for m in recent_messages if m.role == "user"]

    if len(user_messages) < MIN_BUFFER_FOR_CONVERGENCE:
        return None

    # Split into early and late halves
    midpoint = len(user_messages) // 2
    early = user_messages[:midpoint]
    late = user_messages[midpoint:]

    if not early or not late:
        return None

    # Calculate question ratios
    early_q_ratio = sum(1 for m in early if m.is_question) / len(early)
    late_q_ratio = sum(1 for m in late if m.is_question) / len(late)

    # Detect significant drop in questions + current is statement
    # Early was mostly questions (>50%), late is mostly statements (<threshold)
    if (
        early_q_ratio > 0.5
        and late_q_ratio < question_drop_threshold
        and not current_is_question
    ):
        # Confidence based on how dramatic the shift is
        shift_magnitude = early_q_ratio - late_q_ratio
        confidence = Confidence(min(0.9, 0.5 + shift_magnitude))

        return Trigger(
            type=TriggerType.SYNTHESIS,
            confidence=confidence,
            source=TriggerSource.STRUCTURAL,
            reason=f"Question ratio dropped from {early_q_ratio:.0%} to {late_q_ratio:.0%}"
        )

    return None


@dataclass
class StructuralDetector:
    """Stateful detector maintaining message buffer.

    Tracks recent messages and their embeddings to detect structural
    patterns like topic drift and convergence.

    The buffer is bounded to prevent memory growth. Detection uses
    pure functions internally for testability.

    Attributes:
        buffer: Rolling window of recent messages
        _topic_drift_threshold: From config, cached
        _convergence_threshold: From config, cached
    """
    buffer: list[MessageBuffer] = field(default_factory=list)
    _topic_drift_threshold: float | None = field(default=None, repr=False)
    _convergence_threshold: float | None = field(default=None, repr=False)

    @property
    def topic_drift_threshold(self) -> float:
        """Get topic drift threshold from config (cached)."""
        if self._topic_drift_threshold is None:
            config = get_sage_config()
            self._topic_drift_threshold = config.topic_drift_threshold
        return self._topic_drift_threshold

    @property
    def convergence_threshold(self) -> float:
        """Get convergence threshold from config (cached)."""
        if self._convergence_threshold is None:
            config = get_sage_config()
            self._convergence_threshold = config.convergence_question_drop
        return self._convergence_threshold

    def analyze_message(
        self,
        content: str,
        role: str,
    ) -> list[Trigger]:
        """Analyze a message for structural triggers.

        Computes embedding for the message, checks for triggers,
        then adds message to buffer.

        Args:
            content: Message text
            role: "user" or "assistant"

        Returns:
            List of detected triggers (may be empty)
        """
        # Security: truncate very long messages
        content = _truncate_message(content)

        # Get embedding for current message
        embedding_result = get_embedding(content)
        if not embedding_result.ok:
            # Log but continue - embedding failures shouldn't break detection
            return []

        embedding = embedding_result.value
        is_question = _is_question(content)
        triggers: list[Trigger] = []

        # Check for topic drift (need sufficient buffer)
        if len(self.buffer) >= MIN_BUFFER_FOR_DRIFT:
            recent_embeddings = [m.embedding for m in self.buffer[-MIN_BUFFER_FOR_DRIFT:]]
            drift_trigger = detect_topic_drift(
                embedding,
                recent_embeddings,
                self.topic_drift_threshold,
            )
            if drift_trigger:
                triggers.append(drift_trigger)

        # Check for convergence (questions → statements)
        if role == "user" and len(self.buffer) >= MIN_BUFFER_FOR_CONVERGENCE:
            convergence_trigger = detect_convergence(
                self.buffer[-10:],  # Look at last 10 messages
                is_question,
                self.convergence_threshold,
            )
            if convergence_trigger:
                triggers.append(convergence_trigger)

        # Add to buffer
        self.buffer.append(MessageBuffer(
            content=content,
            embedding=embedding,
            role=role,
            is_question=is_question,
        ))

        # Bound buffer size
        if len(self.buffer) > MAX_BUFFER_SIZE:
            self.buffer = self.buffer[-MAX_BUFFER_SIZE:]

        return triggers

    def clear(self) -> None:
        """Clear the message buffer."""
        self.buffer = []

    def get_buffer_size(self) -> int:
        """Get current buffer size."""
        return len(self.buffer)
