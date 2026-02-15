"""Tests for trigger type definitions."""

import numpy as np
import pytest

from sage.triggers.types import (
    DEFAULT_TRIGGER_THRESHOLD,
    EMBEDDING_WEIGHT,
    KEYWORD_WEIGHT,
    Confidence,
    MessageBuffer,
    Trigger,
    TriggerResult,
    TriggerSource,
    TriggerType,
)


class TestTrigger:
    """Test the Trigger dataclass."""

    def test_create_valid_trigger(self):
        """Valid trigger creation works."""
        trigger = Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.8),
            source=TriggerSource.STRUCTURAL,
            reason="Topic similarity dropped to 0.35",
        )
        assert trigger.type == TriggerType.TOPIC_SHIFT
        assert trigger.confidence == 0.8
        assert trigger.source == TriggerSource.STRUCTURAL

    def test_confidence_must_be_in_range(self):
        """Confidence must be between 0 and 1."""
        with pytest.raises(ValueError, match="Confidence must be 0.0-1.0"):
            Trigger(
                type=TriggerType.SYNTHESIS,
                confidence=Confidence(1.5),
                source=TriggerSource.LINGUISTIC,
                reason="Invalid",
            )

        with pytest.raises(ValueError, match="Confidence must be 0.0-1.0"):
            Trigger(
                type=TriggerType.SYNTHESIS,
                confidence=Confidence(-0.1),
                source=TriggerSource.LINGUISTIC,
                reason="Invalid",
            )

    def test_trigger_is_frozen(self):
        """Trigger is immutable."""
        trigger = Trigger(
            type=TriggerType.BRANCH_POINT,
            confidence=Confidence(0.7),
            source=TriggerSource.COMBINED,
            reason="Test",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            trigger.confidence = 0.9


class TestMessageBuffer:
    """Test the MessageBuffer dataclass."""

    def test_create_message_buffer(self):
        """MessageBuffer creation works."""
        embedding = np.array([0.1, 0.2, 0.3])
        msg = MessageBuffer(
            content="What is the weather?",
            embedding=embedding,
            role="user",
            is_question=True,
        )
        assert msg.content == "What is the weather?"
        assert msg.role == "user"
        assert msg.is_question is True

    def test_message_buffer_equality(self):
        """MessageBuffer equality comparison."""
        embedding = np.array([0.1, 0.2, 0.3])
        msg1 = MessageBuffer("Test", embedding, "user", True)
        msg2 = MessageBuffer("Test", embedding, "user", True)
        msg3 = MessageBuffer("Different", embedding, "user", True)

        assert msg1 == msg2
        assert msg1 != msg3

    def test_message_buffer_hash(self):
        """MessageBuffer is hashable."""
        embedding = np.array([0.1, 0.2, 0.3])
        msg = MessageBuffer("Test", embedding, "user", True)
        # Should be hashable (no exception)
        hash(msg)


class TestTriggerResult:
    """Test the TriggerResult dataclass."""

    def test_trigger_property_with_both_signals(self):
        """trigger property returns combined trigger when both present."""
        structural = Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.7),
            source=TriggerSource.STRUCTURAL,
            reason="Topic drift",
        )
        linguistic = Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.6),
            source=TriggerSource.LINGUISTIC,
            reason="Pattern matched",
        )
        result = TriggerResult(
            structural=structural,
            linguistic=linguistic,
            combined_score=Confidence(0.67),
            should_trigger=True,
        )

        trigger = result.trigger
        assert trigger is not None
        assert trigger.source == TriggerSource.COMBINED
        assert "confirmed by" in trigger.reason

    def test_trigger_property_returns_none_when_not_triggered(self):
        """trigger property returns None when should_trigger is False."""
        result = TriggerResult(
            structural=None,
            linguistic=None,
            combined_score=Confidence(0.2),
            should_trigger=False,
        )
        assert result.trigger is None


class TestConstants:
    """Test module constants."""

    def test_weights_sum_to_one(self):
        """Embedding and keyword weights should sum to 1.0."""
        assert EMBEDDING_WEIGHT + KEYWORD_WEIGHT == 1.0

    def test_default_threshold_reasonable(self):
        """Default threshold is in reasonable range."""
        assert 0.5 <= DEFAULT_TRIGGER_THRESHOLD <= 0.8

    def test_embedding_weight_dominant(self):
        """Embedding weight should be dominant (structural > linguistic)."""
        assert EMBEDDING_WEIGHT > KEYWORD_WEIGHT
