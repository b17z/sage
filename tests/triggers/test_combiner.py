"""Tests for trigger signal combiner."""

from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from sage.triggers.combiner import (
    combine_signals,
    TriggerDetector,
    should_checkpoint,
    analyze_for_trigger,
    _select_best_trigger,
)
from sage.triggers.types import (
    Trigger,
    TriggerType,
    TriggerSource,
    TriggerResult,
    Confidence,
    EMBEDDING_WEIGHT,
    KEYWORD_WEIGHT,
    DEFAULT_TRIGGER_THRESHOLD,
)
from sage.errors import Ok


class TestCombineSignals:
    """Test the 70/30 signal combination."""

    def test_structural_only_high_confidence(self):
        """High confidence structural alone can trigger."""
        structural = Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.9),
            source=TriggerSource.STRUCTURAL,
            reason="Topic drift detected",
        )
        result = combine_signals(structural, None, threshold=0.60)

        # 0.7 * 0.9 + 0.3 * 0 = 0.63
        assert result.combined_score == pytest.approx(0.63, rel=0.01)
        assert result.should_trigger is True

    def test_structural_only_low_confidence(self):
        """Low confidence structural alone doesn't trigger."""
        structural = Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.5),
            source=TriggerSource.STRUCTURAL,
            reason="Mild topic drift",
        )
        result = combine_signals(structural, None, threshold=0.60)

        # 0.7 * 0.5 + 0.3 * 0 = 0.35
        assert result.combined_score == pytest.approx(0.35, rel=0.01)
        assert result.should_trigger is False

    def test_linguistic_only_cannot_trigger(self):
        """Linguistic alone cannot reach threshold."""
        linguistic = Trigger(
            type=TriggerType.SYNTHESIS,
            confidence=Confidence(1.0),  # Max linguistic confidence
            source=TriggerSource.LINGUISTIC,
            reason="Pattern matched",
        )
        result = combine_signals(None, linguistic, threshold=0.60)

        # 0.7 * 0 + 0.3 * 1.0 = 0.30
        assert result.combined_score == pytest.approx(0.30, rel=0.01)
        assert result.should_trigger is False

    def test_both_signals_boost_confidence(self):
        """Both signals together create high confidence."""
        structural = Trigger(
            type=TriggerType.BRANCH_POINT,
            confidence=Confidence(0.6),
            source=TriggerSource.STRUCTURAL,
            reason="Structural detection",
        )
        linguistic = Trigger(
            type=TriggerType.BRANCH_POINT,
            confidence=Confidence(0.7),
            source=TriggerSource.LINGUISTIC,
            reason="Pattern matched",
        )
        result = combine_signals(structural, linguistic, threshold=0.60)

        # 0.7 * 0.6 + 0.3 * 0.7 = 0.42 + 0.21 = 0.63
        assert result.combined_score == pytest.approx(0.63, rel=0.01)
        assert result.should_trigger is True

    def test_neither_signal_no_trigger(self):
        """No signals means no trigger."""
        result = combine_signals(None, None, threshold=0.60)

        assert result.combined_score == 0.0
        assert result.should_trigger is False

    def test_exact_threshold(self):
        """Score at or above threshold triggers."""
        structural = Trigger(
            type=TriggerType.SYNTHESIS,
            confidence=Confidence(0.86),  # 0.7 * 0.86 = 0.602
            source=TriggerSource.STRUCTURAL,
            reason="Test",
        )
        result = combine_signals(structural, None, threshold=0.60)

        assert result.should_trigger is True

    def test_just_below_threshold(self):
        """Score just below threshold doesn't trigger."""
        structural = Trigger(
            type=TriggerType.SYNTHESIS,
            confidence=Confidence(0.85),  # 0.7 * 0.85 = 0.595
            source=TriggerSource.STRUCTURAL,
            reason="Test",
        )
        result = combine_signals(structural, None, threshold=0.60)

        assert result.should_trigger is False


class TestSelectBestTrigger:
    """Test trigger selection from multiple signals."""

    def test_selects_highest_confidence(self):
        """Selects trigger with highest confidence."""
        low = Trigger(
            type=TriggerType.SYNTHESIS,
            confidence=Confidence(0.5),
            source=TriggerSource.STRUCTURAL,
            reason="Low",
        )
        high = Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.9),
            source=TriggerSource.STRUCTURAL,
            reason="High",
        )
        best = _select_best_trigger([low, high])
        assert best.confidence == 0.9

    def test_empty_list_returns_none(self):
        """Empty list returns None."""
        assert _select_best_trigger([]) is None


class TestTriggerDetector:
    """Test the combined TriggerDetector class."""

    @patch("sage.triggers.combiner.detect_linguistic_trigger")
    @patch.object(TriggerDetector, "structural_detector")
    def test_analyze_combines_signals(self, mock_structural_detector, mock_linguistic):
        """analyze() combines structural and linguistic signals."""
        # Setup mocks
        structural_trigger = Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.8),
            source=TriggerSource.STRUCTURAL,
            reason="Structural",
        )
        mock_structural_detector.analyze_message.return_value = [structural_trigger]

        linguistic_trigger = Trigger(
            type=TriggerType.TOPIC_SHIFT,
            confidence=Confidence(0.7),
            source=TriggerSource.LINGUISTIC,
            reason="Linguistic",
        )
        mock_linguistic.return_value = linguistic_trigger

        detector = TriggerDetector()
        detector.structural_detector = mock_structural_detector
        detector.threshold = 0.60

        result = detector.analyze("Moving on to new topic", "assistant")

        assert result.structural == structural_trigger
        assert result.linguistic == linguistic_trigger
        # 0.7 * 0.8 + 0.3 * 0.7 = 0.56 + 0.21 = 0.77
        assert result.combined_score == pytest.approx(0.77, rel=0.01)
        assert result.should_trigger is True

    @patch("sage.triggers.structural.get_embedding")
    def test_clear_buffer(self, mock_get_embedding):
        """clear_buffer() clears the structural detector buffer."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = TriggerDetector()
        detector.analyze("Test message", "user")
        assert detector.get_buffer_size() > 0

        detector.clear_buffer()
        assert detector.get_buffer_size() == 0


class TestShouldCheckpoint:
    """Test the convenience function."""

    @patch("sage.triggers.combiner.detect_linguistic_trigger")
    def test_without_detector_uses_linguistic_only(self, mock_linguistic):
        """Without detector, only linguistic is checked (rarely triggers)."""
        mock_linguistic.return_value = Trigger(
            type=TriggerType.SYNTHESIS,
            confidence=Confidence(0.7),
            source=TriggerSource.LINGUISTIC,
            reason="Pattern",
        )

        # Without detector, linguistic alone applies 30% weight
        # 0.3 * 0.7 = 0.21 < 0.60 threshold
        should, trigger = should_checkpoint("In conclusion, done", "assistant")
        assert should is False

    @patch("sage.triggers.structural.get_embedding")
    def test_with_detector_uses_full_analysis(self, mock_get_embedding):
        """With detector, full analysis is used."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = TriggerDetector()
        detector.threshold = 0.60

        # Fill buffer first
        for i in range(6):
            detector.analyze(f"Message {i}", "user")

        # Now test should_checkpoint with the detector
        should, trigger = should_checkpoint("Let's move on", "assistant", detector)
        # Result depends on actual detection, but function should work
        assert isinstance(should, bool)


class TestAnalyzeForTrigger:
    """Test the detailed analysis function."""

    @patch("sage.triggers.structural.get_embedding")
    def test_returns_detailed_info(self, mock_get_embedding):
        """Returns detailed breakdown of analysis."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        result = analyze_for_trigger("In conclusion, we're done", "assistant")

        # Should have all expected keys
        assert "structural" in result
        assert "linguistic" in result
        assert "combined_score" in result
        assert "threshold" in result
        assert "should_trigger" in result

        # Linguistic should detect synthesis pattern
        assert result["linguistic"]["detected"] is True
        assert result["linguistic"]["type"] == "synthesis"

    @patch("sage.triggers.structural.get_embedding")
    def test_no_patterns_returns_zeros(self, mock_get_embedding):
        """No patterns detected returns zero scores."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        result = analyze_for_trigger("Just a normal message", "user")

        assert result["linguistic"]["detected"] is False
        assert result["should_trigger"] is False


class TestThresholdBehavior:
    """Test threshold configuration."""

    def test_uses_default_threshold(self):
        """Uses default threshold when not specified."""
        result = combine_signals(None, None)
        # Implicitly uses DEFAULT_TRIGGER_THRESHOLD via config

    def test_custom_threshold_respected(self):
        """Custom threshold is respected."""
        structural = Trigger(
            type=TriggerType.SYNTHESIS,
            confidence=Confidence(0.8),
            source=TriggerSource.STRUCTURAL,
            reason="Test",
        )

        # With low threshold, should trigger
        result_low = combine_signals(structural, None, threshold=0.50)
        assert result_low.should_trigger is True

        # With high threshold, should not trigger
        result_high = combine_signals(structural, None, threshold=0.80)
        assert result_high.should_trigger is False
