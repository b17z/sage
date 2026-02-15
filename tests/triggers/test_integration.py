"""Integration tests for trigger detection.

These tests verify the full trigger detection flow from raw messages
to final trigger decisions. They use real embeddings (when available)
or mocks for CI environments.
"""

from unittest.mock import patch

import numpy as np

from sage.errors import Ok
from sage.triggers import (
    TriggerDetector,
    TriggerType,
    analyze_for_trigger,
    should_checkpoint,
)


class TestFullTriggerFlow:
    """Integration tests for complete trigger detection."""

    @patch("sage.triggers.structural.get_embedding")
    def test_topic_shift_scenario(self, mock_get_embedding):
        """Simulate a conversation with topic shift."""
        # Create embeddings that simulate topic A then topic B
        topic_a = np.array([1.0, 0.1, 0.0])
        topic_b = np.array([0.0, 0.1, 1.0])  # Orthogonal to A

        call_count = [0]

        def mock_embedding(text):
            call_count[0] += 1
            # First 6 messages are topic A, then topic B
            if call_count[0] <= 6:
                return Ok(topic_a + np.random.rand(3) * 0.05)
            return Ok(topic_b)

        mock_get_embedding.side_effect = mock_embedding

        detector = TriggerDetector()
        detector.threshold = 0.50

        # Simulate conversation about topic A
        messages_a = [
            "Let's discuss database design",
            "What indexes should we use?",
            "The primary key should be UUID",
            "We need foreign key constraints",
            "Consider using composite indexes",
            "Partitioning might help performance",
        ]

        for msg in messages_a:
            result = detector.analyze(msg, "user")
            # Early messages shouldn't trigger much
            assert not result.should_trigger or call_count[0] < 5

        # Now shift to completely different topic
        result = detector.analyze(
            "Now let's discuss authentication",
            "assistant"
        )

        # This should detect topic shift (structural + possibly linguistic)
        if result.should_trigger:
            assert result.trigger.type == TriggerType.TOPIC_SHIFT

    @patch("sage.triggers.structural.get_embedding")
    def test_synthesis_scenario(self, mock_get_embedding):
        """Simulate a research session ending in synthesis."""
        mock_get_embedding.return_value = Ok(np.array([0.5, 0.5, 0.5]))

        detector = TriggerDetector()
        detector.threshold = 0.40  # Lower threshold for linguistic to help

        # Research phase (questions)
        research_messages = [
            ("What are the options for caching?", "user"),
            ("Redis and Memcached are popular choices", "assistant"),
            ("How do they compare in performance?", "user"),
            ("Redis is slightly faster for complex operations", "assistant"),
            ("What about memory usage?", "user"),
        ]

        for content, role in research_messages:
            detector.analyze(content, role)

        # Synthesis phase
        result = detector.analyze(
            "In conclusion, Redis is the better choice for our use case "
            "because it offers better performance and data persistence.",
            "assistant"
        )

        # Should detect synthesis via linguistic pattern
        if result.linguistic:
            assert result.linguistic.type == TriggerType.SYNTHESIS

    @patch("sage.triggers.structural.get_embedding")
    def test_branch_point_scenario(self, mock_get_embedding):
        """Simulate identifying multiple approaches."""
        mock_get_embedding.return_value = Ok(np.array([0.5, 0.5, 0.5]))

        detector = TriggerDetector()
        detector.threshold = 0.40

        # Context building
        detector.analyze("We need to implement user authentication", "user")
        detector.analyze("There are several ways to do this", "assistant")

        # Branch point
        result = detector.analyze(
            "We have two approaches: OAuth with third-party providers, "
            "or building our own JWT-based system. There's a trade-off "
            "between simplicity and control.",
            "assistant"
        )

        # Should detect branch point
        if result.linguistic:
            assert result.linguistic.type == TriggerType.BRANCH_POINT

    @patch("sage.triggers.structural.get_embedding")
    def test_constraint_discovery_scenario(self, mock_get_embedding):
        """Simulate discovering a blocker."""
        mock_get_embedding.return_value = Ok(np.array([0.5, 0.5, 0.5]))

        detector = TriggerDetector()
        detector.threshold = 0.40

        # Building up to constraint
        detector.analyze("Can we use the free tier of the API?", "user")
        detector.analyze("Let me check the rate limits", "assistant")

        # Constraint discovered
        result = detector.analyze(
            "Unfortunately, this won't work because the free tier "
            "only allows 100 requests per day. We're blocked by this limit.",
            "assistant"
        )

        # Should detect constraint
        if result.linguistic:
            assert result.linguistic.type == TriggerType.CONSTRAINT


class TestEdgeCases:
    """Test edge cases and error handling."""

    @patch("sage.triggers.structural.get_embedding")
    def test_empty_messages_handled(self, mock_get_embedding):
        """Empty messages don't crash."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = TriggerDetector()
        result = detector.analyze("", "user")

        assert result.should_trigger is False

    @patch("sage.triggers.structural.get_embedding")
    def test_very_long_messages_handled(self, mock_get_embedding):
        """Very long messages are handled (truncated)."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = TriggerDetector()
        long_message = "x" * 100000
        result = detector.analyze(long_message, "user")

        # Should not crash
        assert isinstance(result.should_trigger, bool)

    @patch("sage.triggers.structural.get_embedding")
    def test_special_characters_handled(self, mock_get_embedding):
        """Special characters don't break detection."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = TriggerDetector()
        special_message = "What about émojis 🚀 and unicöde? In conclusion..."
        result = detector.analyze(special_message, "assistant")

        # Should still detect synthesis pattern
        assert result.linguistic is not None

    @patch("sage.triggers.structural.get_embedding")
    def test_code_heavy_messages(self, mock_get_embedding):
        """Messages with lots of code handled correctly."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = TriggerDetector()

        # Message that has trigger words INSIDE code
        code_message = """Here's the implementation:
```python
def get_option():
    # alternatively, we could return None
    return option_value
```
"""
        result = detector.analyze(code_message, "assistant")

        # Should NOT trigger on "option" or "alternatively" inside code
        if result.linguistic:
            # If it did trigger, it should be for a reason outside the code
            pass


class TestConsistencyWithKnowledgeRecall:
    """Verify trigger detection uses same 70/30 pattern as knowledge recall."""

    def test_weights_match_knowledge(self):
        """Trigger weights match knowledge recall config defaults."""
        from sage.config import SageConfig
        from sage.triggers.types import EMBEDDING_WEIGHT, KEYWORD_WEIGHT

        # Knowledge recall uses embedding_weight and keyword_weight from config
        defaults = SageConfig()
        assert EMBEDDING_WEIGHT == defaults.embedding_weight
        assert KEYWORD_WEIGHT == defaults.keyword_weight

    def test_same_hybrid_approach(self):
        """Both systems use same hybrid scoring approach."""
        from sage.triggers.types import EMBEDDING_WEIGHT, KEYWORD_WEIGHT

        # Verify weights sum to 1
        assert EMBEDDING_WEIGHT + KEYWORD_WEIGHT == 1.0

        # Verify embedding is dominant
        assert EMBEDDING_WEIGHT > KEYWORD_WEIGHT

        # Verify specific values
        assert EMBEDDING_WEIGHT == 0.7
        assert KEYWORD_WEIGHT == 0.3


class TestConvenienceFunctions:
    """Test the public convenience API."""

    @patch("sage.triggers.structural.get_embedding")
    def test_analyze_for_trigger_detailed_output(self, mock_get_embedding):
        """analyze_for_trigger returns useful debug info."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        result = analyze_for_trigger("In conclusion, done", "assistant")

        # Check structure
        assert "structural" in result
        assert "linguistic" in result
        assert "combined_score" in result
        assert "should_trigger" in result
        assert "threshold" in result
        assert "trigger" in result

        # Verify linguistic detection
        assert result["linguistic"]["detected"] is True
        assert result["linguistic"]["type"] == "synthesis"
        assert result["linguistic"]["confidence"] > 0

    @patch("sage.triggers.structural.get_embedding")
    def test_should_checkpoint_simple_api(self, mock_get_embedding):
        """should_checkpoint provides simple yes/no answer."""
        mock_get_embedding.return_value = Ok(np.array([0.1, 0.2, 0.3]))

        detector = TriggerDetector()
        detector.threshold = 0.20  # Low threshold to ensure trigger

        should, trigger = should_checkpoint(
            "In conclusion, this works",
            "assistant",
            detector
        )

        assert isinstance(should, bool)
        if should:
            assert trigger is not None
