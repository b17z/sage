"""Tests for structural trigger detection."""

from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from sage.triggers.structural import (
    StructuralDetector,
    detect_topic_drift,
    detect_convergence,
    _is_question,
    _truncate_message,
    MAX_BUFFER_SIZE,
    MIN_BUFFER_FOR_DRIFT,
    MAX_MESSAGE_LENGTH,
)
from sage.triggers.types import (
    TriggerType,
    TriggerSource,
    MessageBuffer,
    Confidence,
)
from sage.errors import Ok


class TestIsQuestion:
    """Test question detection heuristics."""

    def test_question_mark_is_question(self):
        """Text ending with ? is a question."""
        assert _is_question("What is this?") is True
        assert _is_question("Why?") is True

    def test_question_starters(self):
        """Question words at start indicate question."""
        assert _is_question("How do I do this") is True
        assert _is_question("What are the options") is True
        assert _is_question("Why does this happen") is True
        assert _is_question("When should I use this") is True
        assert _is_question("Can you help me") is True

    def test_statements_not_questions(self):
        """Statements are not questions."""
        assert _is_question("I think this is correct") is False
        assert _is_question("The answer is 42") is False
        assert _is_question("Let's do this") is False

    def test_empty_string(self):
        """Empty strings are not questions."""
        assert _is_question("") is False
        assert _is_question("   ") is False


class TestTruncateMessage:
    """Test message truncation for security."""

    def test_short_message_unchanged(self):
        """Short messages are unchanged."""
        msg = "This is a short message"
        assert _truncate_message(msg) == msg

    def test_long_message_truncated(self):
        """Long messages are truncated."""
        long_msg = "x" * (MAX_MESSAGE_LENGTH + 1000)
        result = _truncate_message(long_msg)
        assert len(result) < len(long_msg)
        assert "[truncated]" in result

    def test_exact_limit_unchanged(self):
        """Message at exact limit is unchanged."""
        msg = "x" * MAX_MESSAGE_LENGTH
        assert _truncate_message(msg) == msg


class TestDetectTopicDrift:
    """Test topic drift detection via embeddings."""

    def test_no_drift_high_similarity(self):
        """High similarity doesn't trigger drift."""
        # Create similar embeddings (same direction, similar values)
        current = np.array([1.0, 0.0, 0.0])
        recent = [np.array([0.9, 0.1, 0.0]) for _ in range(5)]

        trigger = detect_topic_drift(current, recent, threshold=0.5)
        assert trigger is None

    def test_drift_detected_low_similarity(self):
        """Low similarity triggers drift detection."""
        # Current is orthogonal to recent
        current = np.array([0.0, 1.0, 0.0])
        recent = [np.array([1.0, 0.0, 0.0]) for _ in range(5)]

        trigger = detect_topic_drift(current, recent, threshold=0.5)
        assert trigger is not None
        assert trigger.type == TriggerType.TOPIC_SHIFT
        assert trigger.source == TriggerSource.STRUCTURAL

    def test_insufficient_buffer_no_trigger(self):
        """Insufficient buffer size returns None."""
        current = np.array([0.0, 1.0, 0.0])
        recent = [np.array([1.0, 0.0, 0.0]) for _ in range(2)]  # Too few

        trigger = detect_topic_drift(current, recent, threshold=0.5)
        assert trigger is None

    def test_confidence_inversely_proportional_to_similarity(self):
        """Lower similarity = higher confidence."""
        current = np.array([0.0, 1.0, 0.0])
        recent = [np.array([1.0, 0.0, 0.0]) for _ in range(5)]

        trigger = detect_topic_drift(current, recent, threshold=0.5)
        assert trigger is not None
        # Orthogonal vectors have ~0 similarity, so confidence should be ~1
        assert trigger.confidence >= 0.8


class TestDetectConvergence:
    """Test convergence detection (questions → statements)."""

    def test_convergence_detected(self):
        """Detects shift from questions to statements."""
        # Early messages are questions
        early = [
            MessageBuffer("What is X?", np.zeros(3), "user", True),
            MessageBuffer("How does Y work?", np.zeros(3), "user", True),
            MessageBuffer("Why is Z?", np.zeros(3), "user", True),
        ]
        # Late messages are statements
        late = [
            MessageBuffer("I think the answer is...", np.zeros(3), "user", False),
            MessageBuffer("So the solution is...", np.zeros(3), "user", False),
            MessageBuffer("This means we should...", np.zeros(3), "user", False),
        ]
        all_messages = early + late

        trigger = detect_convergence(all_messages, current_is_question=False, question_drop_threshold=0.3)
        assert trigger is not None
        assert trigger.type == TriggerType.SYNTHESIS

    def test_no_convergence_all_questions(self):
        """No convergence if still asking questions."""
        messages = [
            MessageBuffer("What is X?", np.zeros(3), "user", True),
            MessageBuffer("How does Y work?", np.zeros(3), "user", True),
            MessageBuffer("Why is Z?", np.zeros(3), "user", True),
            MessageBuffer("What about W?", np.zeros(3), "user", True),
            MessageBuffer("How about V?", np.zeros(3), "user", True),
            MessageBuffer("When is U?", np.zeros(3), "user", True),
        ]

        trigger = detect_convergence(messages, current_is_question=True, question_drop_threshold=0.2)
        assert trigger is None

    def test_insufficient_messages(self):
        """Insufficient messages returns None."""
        messages = [
            MessageBuffer("Test", np.zeros(3), "user", True),
            MessageBuffer("Test2", np.zeros(3), "user", False),
        ]

        trigger = detect_convergence(messages, current_is_question=False, question_drop_threshold=0.2)
        assert trigger is None


class TestStructuralDetector:
    """Test the StructuralDetector class."""

    @patch("sage.triggers.structural.get_embedding")
    def test_analyze_message_adds_to_buffer(self, mock_get_embedding):
        """analyze_message adds message to buffer."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = StructuralDetector()
        assert detector.get_buffer_size() == 0

        detector.analyze_message("Test message", "user")
        assert detector.get_buffer_size() == 1

    @patch("sage.triggers.structural.get_embedding")
    def test_buffer_bounded(self, mock_get_embedding):
        """Buffer is bounded at MAX_BUFFER_SIZE."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = StructuralDetector()

        # Add more messages than the limit
        for i in range(MAX_BUFFER_SIZE + 10):
            detector.analyze_message(f"Message {i}", "user")

        assert detector.get_buffer_size() == MAX_BUFFER_SIZE

    @patch("sage.triggers.structural.get_embedding")
    def test_clear_buffer(self, mock_get_embedding):
        """clear() empties the buffer."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = StructuralDetector()
        detector.analyze_message("Test", "user")
        assert detector.get_buffer_size() == 1

        detector.clear()
        assert detector.get_buffer_size() == 0

    @patch("sage.triggers.structural.get_embedding")
    def test_returns_empty_on_embedding_failure(self, mock_get_embedding):
        """Returns empty list if embedding fails."""
        from sage.errors import Err, SageError

        # Simulate embedding failure with a generic SageError
        error = SageError(code="EMBEDDING_FAILED", message="Test error")
        mock_get_embedding.return_value = Err(error)

        detector = StructuralDetector()
        triggers = detector.analyze_message("Test", "user")

        assert triggers == []

    @patch("sage.triggers.structural.get_embedding")
    def test_detects_topic_drift(self, mock_get_embedding):
        """Detects topic drift when topic changes."""
        # First 5 messages about topic A
        topic_a_embedding = np.array([1.0, 0.0, 0.0])
        # Then a message about topic B (orthogonal)
        topic_b_embedding = np.array([0.0, 1.0, 0.0])

        call_count = [0]

        def side_effect(text):
            call_count[0] += 1
            if call_count[0] <= MIN_BUFFER_FOR_DRIFT:
                return Ok(topic_a_embedding + np.random.rand(3) * 0.1)
            return Ok(topic_b_embedding)

        mock_get_embedding.side_effect = side_effect

        detector = StructuralDetector()
        detector._topic_drift_threshold = 0.5

        # Fill buffer with topic A
        for i in range(MIN_BUFFER_FOR_DRIFT):
            detector.analyze_message(f"Topic A message {i}", "user")

        # Now send topic B message
        triggers = detector.analyze_message("Completely different topic B", "user")

        # Should detect topic drift
        topic_shift_triggers = [t for t in triggers if t.type == TriggerType.TOPIC_SHIFT]
        assert len(topic_shift_triggers) > 0
