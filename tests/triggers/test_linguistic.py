"""Tests for linguistic trigger detection."""


from sage.triggers.linguistic import (
    TOPIC_SHIFT_PATTERNS,
    _is_meta_discussion,
    _match_patterns,
    _strip_code_and_quotes,
    detect_linguistic_trigger,
    get_all_patterns,
)
from sage.triggers.types import TriggerSource, TriggerType


class TestStripCodeAndQuotes:
    """Test content filtering."""

    def test_strips_fenced_code_blocks(self):
        """Fenced code blocks are removed."""
        text = 'Before ```python\ncode here\n``` After'
        result = _strip_code_and_quotes(text)
        assert "code here" not in result
        assert "Before" in result
        assert "After" in result

    def test_strips_inline_code(self):
        """Inline code is removed."""
        text = "Use the `option` flag for this"
        result = _strip_code_and_quotes(text)
        assert "option" not in result
        assert "Use the" in result

    def test_strips_double_quotes(self):
        """Double-quoted strings are removed."""
        text = 'The error says "option required" here'
        result = _strip_code_and_quotes(text)
        assert "option required" not in result
        assert "The error says" in result

    def test_strips_blockquotes(self):
        """Blockquotes are removed."""
        text = "Normal text\n> This is a quote\nMore text"
        result = _strip_code_and_quotes(text)
        assert "This is a quote" not in result
        assert "Normal text" in result


class TestIsMetaDiscussion:
    """Test meta-discussion detection."""

    def test_detects_hook_discussion(self):
        """Detects discussion about hooks."""
        assert _is_meta_discussion("the hook fired correctly") is True
        assert _is_meta_discussion("checkpoint trigger test") is True
        assert _is_meta_discussion("sage_autosave_check blocked") is True

    def test_normal_text_not_meta(self):
        """Normal text is not meta-discussion."""
        assert _is_meta_discussion("let's implement the feature") is False
        assert _is_meta_discussion("the database query returns") is False


class TestMatchPatterns:
    """Test pattern matching."""

    def test_match_found(self):
        """Returns PatternMatch when pattern found."""
        result = _match_patterns("let's turn to databases", TOPIC_SHIFT_PATTERNS)
        assert result.matched is True
        assert result.match_text is not None

    def test_no_match(self):
        """Returns non-matched PatternMatch when no pattern found."""
        result = _match_patterns("nothing special here", TOPIC_SHIFT_PATTERNS)
        assert result.matched is False


class TestDetectLinguisticTrigger:
    """Test the main detection function."""

    # Topic shift patterns
    def test_topic_shift_moving_on(self):
        """Detects 'moving on to' as topic shift."""
        trigger = detect_linguistic_trigger("Moving on to the next topic now")
        assert trigger is not None
        assert trigger.type == TriggerType.TOPIC_SHIFT
        assert trigger.source == TriggerSource.LINGUISTIC

    def test_topic_shift_turn_to(self):
        """Detects 'let's turn to' as topic shift."""
        trigger = detect_linguistic_trigger("Let's turn to the database design")
        assert trigger is not None
        assert trigger.type == TriggerType.TOPIC_SHIFT

    def test_topic_shift_changing_topics(self):
        """Detects 'changing topics' as topic shift."""
        trigger = detect_linguistic_trigger("Changing topics, let's discuss auth")
        assert trigger is not None
        assert trigger.type == TriggerType.TOPIC_SHIFT

    # Branch point patterns
    def test_branch_point_two_approaches(self):
        """Detects 'two approaches' as branch point."""
        trigger = detect_linguistic_trigger("There are two approaches we could take")
        assert trigger is not None
        assert trigger.type == TriggerType.BRANCH_POINT

    def test_branch_point_alternatively(self):
        """Detects 'alternatively' as branch point."""
        trigger = detect_linguistic_trigger("Alternatively, we could use Redis")
        assert trigger is not None
        assert trigger.type == TriggerType.BRANCH_POINT

    def test_branch_point_tradeoff(self):
        """Detects 'trade-off' as branch point."""
        trigger = detect_linguistic_trigger("There's a trade-off between speed and accuracy")
        assert trigger is not None
        assert trigger.type == TriggerType.BRANCH_POINT

    # Constraint patterns
    def test_constraint_wont_work(self):
        """Detects 'won't work because' as constraint."""
        trigger = detect_linguistic_trigger("This won't work because of the API limit")
        assert trigger is not None
        assert trigger.type == TriggerType.CONSTRAINT

    def test_constraint_blocked_by(self):
        """Detects 'blocked by' as constraint."""
        trigger = detect_linguistic_trigger("We're blocked by the rate limiter")
        assert trigger is not None
        assert trigger.type == TriggerType.CONSTRAINT

    def test_constraint_showstopper(self):
        """Detects 'showstopper' as constraint."""
        trigger = detect_linguistic_trigger("This is a show-stopper for our approach")
        assert trigger is not None
        assert trigger.type == TriggerType.CONSTRAINT

    # Synthesis patterns
    def test_synthesis_in_conclusion(self):
        """Detects 'in conclusion' as synthesis."""
        trigger = detect_linguistic_trigger("In conclusion, we should use PostgreSQL")
        assert trigger is not None
        assert trigger.type == TriggerType.SYNTHESIS

    def test_synthesis_putting_together(self):
        """Detects 'putting this together' as synthesis."""
        trigger = detect_linguistic_trigger("Putting this together, the solution is clear")
        assert trigger is not None
        assert trigger.type == TriggerType.SYNTHESIS

    def test_synthesis_bottom_line(self):
        """Detects 'bottom line' as synthesis."""
        trigger = detect_linguistic_trigger("The bottom line is we need more data")
        assert trigger is not None
        assert trigger.type == TriggerType.SYNTHESIS

    def test_synthesis_tldr(self):
        """Detects 'tldr' as synthesis."""
        trigger = detect_linguistic_trigger("TL;DR: use caching for this")
        assert trigger is not None
        assert trigger.type == TriggerType.SYNTHESIS

    # Filtering tests
    def test_pattern_in_code_block_ignored(self):
        """Patterns inside code blocks are ignored."""
        text = "Here's how to do it:\n```\noption = 'alternatively'\n```"
        trigger = detect_linguistic_trigger(text)
        # Should NOT trigger on "alternatively" inside code
        if trigger:
            assert "alternatively" not in trigger.reason.lower()

    def test_pattern_in_inline_code_ignored(self):
        """Patterns inside inline code are ignored."""
        text = "Use the `option` parameter for this"
        trigger = detect_linguistic_trigger(text)
        # "option" is a branch_point pattern but should be ignored
        if trigger:
            assert trigger.type != TriggerType.BRANCH_POINT or "option" not in trigger.reason

    def test_meta_discussion_ignored(self):
        """Meta-discussion about triggers is ignored."""
        text = "The hook fired and detected a trigger"
        trigger = detect_linguistic_trigger(text)
        assert trigger is None

    def test_empty_content_returns_none(self):
        """Empty content returns None."""
        assert detect_linguistic_trigger("") is None
        assert detect_linguistic_trigger("   ") is None

    def test_no_patterns_returns_none(self):
        """Content with no patterns returns None."""
        trigger = detect_linguistic_trigger("This is just a normal statement")
        assert trigger is None


class TestGetAllPatterns:
    """Test pattern retrieval."""

    def test_returns_all_trigger_types(self):
        """Returns patterns for all trigger types."""
        patterns = get_all_patterns()
        assert TriggerType.TOPIC_SHIFT in patterns
        assert TriggerType.BRANCH_POINT in patterns
        assert TriggerType.CONSTRAINT in patterns
        assert TriggerType.SYNTHESIS in patterns

    def test_patterns_are_lists(self):
        """Each trigger type has a list of patterns."""
        patterns = get_all_patterns()
        for trigger_type, pattern_list in patterns.items():
            assert isinstance(pattern_list, list)
            assert len(pattern_list) > 0


class TestPriorityOrder:
    """Test that detection follows priority order."""

    def test_topic_shift_higher_than_synthesis(self):
        """Topic shift is detected before synthesis when both match."""
        # This message could match both topic_shift and synthesis
        text = "Moving on to summarize the findings"
        trigger = detect_linguistic_trigger(text)
        assert trigger is not None
        # Topic shift should be detected (higher priority)
        assert trigger.type == TriggerType.TOPIC_SHIFT

    def test_branch_point_higher_than_synthesis(self):
        """Branch point is detected before synthesis when both match."""
        text = "In summary, we have two approaches"
        trigger = detect_linguistic_trigger(text)
        # Could match both, but branch_point is higher priority
        assert trigger is not None
        assert trigger.type == TriggerType.BRANCH_POINT
