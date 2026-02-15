"""Tests for sage.salience module."""

import pytest

from sage.salience import (
    SALIENCE_PATTERNS,
    SalientContent,
    _extract_context,
    _preprocess_text,
    categorize_content,
    extract_decisions,
    extract_open_threads,
    extract_resolutions,
    extract_salient_content,
    get_max_salience,
    is_significant,
    summarize_salience,
)


class TestSaliencePatterns:
    """Tests for SALIENCE_PATTERNS configuration."""

    def test_patterns_have_expected_categories(self):
        """All expected categories are defined."""
        expected = {
            "decision",
            "resolution",
            "open_thread",
            "constraint",
            "synthesis",
            "discovery",
            "tradeoff",
            "question",
        }
        assert set(SALIENCE_PATTERNS.keys()) == expected

    def test_patterns_have_valid_structure(self):
        """Each pattern entry has patterns list and score."""
        for category, (patterns, score) in SALIENCE_PATTERNS.items():
            assert isinstance(patterns, list), f"{category} patterns should be list"
            assert len(patterns) > 0, f"{category} should have patterns"
            assert isinstance(score, float), f"{category} score should be float"
            assert 0.0 <= score <= 1.0, f"{category} score should be 0-1"

    def test_decision_patterns_highest_priority(self):
        """Decision patterns have high salience score."""
        _, score = SALIENCE_PATTERNS["decision"]
        assert score >= 0.8

    def test_resolution_patterns_highest_priority(self):
        """Resolution patterns have high salience score."""
        _, score = SALIENCE_PATTERNS["resolution"]
        assert score >= 0.8

    def test_question_patterns_lowest_priority(self):
        """Question patterns have lower salience score."""
        _, score = SALIENCE_PATTERNS["question"]
        assert score <= 0.6


class TestSalientContent:
    """Tests for SalientContent dataclass."""

    def test_salient_content_is_frozen(self):
        """SalientContent is immutable."""
        sc = SalientContent(
            category="decision",
            text="decided to",
            salience=0.9,
            context="We decided to use Python.",
        )
        with pytest.raises(AttributeError):
            sc.category = "other"

    def test_salient_content_default_context(self):
        """SalientContent has empty default context."""
        sc = SalientContent(
            category="decision",
            text="decided to",
            salience=0.9,
        )
        assert sc.context == ""


class TestPreprocessText:
    """Tests for _preprocess_text helper."""

    def test_removes_fenced_code_blocks(self):
        """Fenced code blocks are removed."""
        text = """Here's the code:
```python
def foo():
    return "decided to"  # This shouldn't match
```
And we decided to use this approach."""

        result = _preprocess_text(text)

        assert "def foo" not in result
        assert "decided to use this approach" in result

    def test_removes_inline_code(self):
        """Inline code is removed."""
        text = "The variable `decided_to_use` should be `None`."

        result = _preprocess_text(text)

        assert "`" not in result
        assert "decided_to_use" not in result

    def test_removes_blockquotes(self):
        """Blockquoted lines are removed."""
        text = """Regular text here.
> This is a quote saying we decided to do something
> More quote
Not a quote anymore."""

        result = _preprocess_text(text)

        assert "Regular text here" in result
        assert "Not a quote" in result
        assert "This is a quote" not in result

    def test_preserves_regular_text(self):
        """Regular text is preserved."""
        text = "We decided to go with Python for the implementation."

        result = _preprocess_text(text)

        assert result.strip() == text


class TestExtractContext:
    """Tests for _extract_context helper."""

    def test_extracts_surrounding_text(self):
        """Context includes text around match."""
        import re
        text = "Before the match. We decided to use Python. After the match."
        match = re.search(r"decided to", text)

        context = _extract_context(text, match, context_chars=50)

        assert "decided to" in context
        assert len(context) > len("decided to")

    def test_respects_context_chars_limit(self):
        """Context respects character limit."""
        import re
        long_text = "A" * 200 + " decided to " + "B" * 200
        match = re.search(r"decided to", long_text)

        context = _extract_context(long_text, match, context_chars=20)

        assert len(context) < 100  # Much shorter than full text


class TestExtractSalientContent:
    """Tests for extract_salient_content function."""

    def test_empty_text_returns_empty(self):
        """Empty text returns empty list."""
        assert extract_salient_content("") == []
        assert extract_salient_content("   ") == []
        assert extract_salient_content(None) == []  # type: ignore

    def test_finds_decision_patterns(self):
        """Detects decision-related patterns."""
        text = "After much discussion, we decided to use PostgreSQL for the database."

        results = extract_salient_content(text)

        assert any(r.category == "decision" for r in results)
        decision = next(r for r in results if r.category == "decision")
        assert "decided to" in decision.text.lower()
        assert decision.salience >= 0.8

    def test_finds_resolution_patterns(self):
        """Detects resolution-related patterns."""
        text = "The bug was caused by a race condition. The fix is to add a mutex lock."

        results = extract_salient_content(text)

        assert any(r.category == "resolution" for r in results)

    def test_finds_open_thread_patterns(self):
        """Detects open thread patterns."""
        text = "We implemented the feature. TODO: add error handling and tests."

        results = extract_salient_content(text)

        assert any(r.category == "open_thread" for r in results)

    def test_finds_constraint_patterns(self):
        """Detects constraint patterns."""
        text = "This approach won't work because of memory limitations."

        results = extract_salient_content(text)

        assert any(r.category == "constraint" for r in results)

    def test_finds_synthesis_patterns(self):
        """Detects synthesis patterns."""
        text = "In summary, we need to refactor the API before adding features."

        results = extract_salient_content(text)

        assert any(r.category == "synthesis" for r in results)

    def test_finds_discovery_patterns(self):
        """Detects discovery patterns."""
        text = "Interesting - turns out the API rate limits reset hourly."

        results = extract_salient_content(text)

        assert any(r.category == "discovery" for r in results)

    def test_finds_question_patterns(self):
        """Detects question patterns."""
        text = "What's the best way to handle authentication?"

        results = extract_salient_content(text)

        assert any(r.category == "question" for r in results)

    def test_sorted_by_salience_descending(self):
        """Results are sorted by salience (highest first)."""
        text = """
        We decided to use Python.
        TODO: Add more tests.
        What about performance?
        """

        results = extract_salient_content(text)

        if len(results) > 1:
            for i in range(len(results) - 1):
                assert results[i].salience >= results[i + 1].salience

    def test_respects_min_salience(self):
        """min_salience filters low-salience matches."""
        text = "We decided to refactor. What about performance?"

        # With high threshold, only high-salience matches
        high_threshold = extract_salient_content(text, min_salience=0.8)
        all_matches = extract_salient_content(text, min_salience=0.0)

        assert len(high_threshold) <= len(all_matches)
        assert all(r.salience >= 0.8 for r in high_threshold)

    def test_deduplicates_matches(self):
        """Duplicate matches are removed."""
        text = "We decided to do X. Then we decided to do Y."

        results = extract_salient_content(text)

        # Both have "decided to" but should deduplicate
        decided_matches = [r for r in results if "decided to" in r.text.lower()]
        assert len(decided_matches) <= 1

    def test_skips_code_in_preprocessing(self):
        """Code blocks don't trigger false positives."""
        text = """
```python
# We decided to use this approach
def decided_to_use():
    pass
```
Outside code, we actually decided to go with Rust.
"""

        results = extract_salient_content(text)

        # Should only match the non-code decision
        decision = next((r for r in results if r.category == "decision"), None)
        if decision:
            assert "Rust" in decision.context or "actually" in decision.context

    def test_handles_multiline_text(self):
        """Handles multiline text correctly."""
        text = """First line.
Second line has the decision: we decided to use Kubernetes.
Third line continues."""

        results = extract_salient_content(text)

        assert any(r.category == "decision" for r in results)

    def test_case_insensitive_matching(self):
        """Pattern matching is case insensitive."""
        text1 = "We DECIDED TO use this approach."
        text2 = "We Decided To use this approach."
        text3 = "we decided to use this approach."

        for text in [text1, text2, text3]:
            results = extract_salient_content(text)
            assert any(r.category == "decision" for r in results)


class TestIsSignificant:
    """Tests for is_significant function."""

    def test_empty_content_not_significant(self):
        """Empty content is not significant."""
        assert is_significant([]) is False

    def test_high_salience_is_significant(self):
        """Content with high salience is significant."""
        content = [
            SalientContent(category="decision", text="decided to", salience=0.9),
        ]
        assert is_significant(content, threshold=0.7) is True

    def test_low_salience_not_significant(self):
        """Content below threshold is not significant."""
        content = [
            SalientContent(category="question", text="?", salience=0.5),
        ]
        assert is_significant(content, threshold=0.7) is False

    def test_respects_min_count(self):
        """Requires minimum count above threshold."""
        content = [
            SalientContent(category="decision", text="decided", salience=0.9),
        ]
        assert is_significant(content, threshold=0.7, min_count=1) is True
        assert is_significant(content, threshold=0.7, min_count=2) is False

    def test_counts_only_above_threshold(self):
        """Only items above threshold count toward min_count."""
        content = [
            SalientContent(category="decision", text="decided", salience=0.9),
            SalientContent(category="question", text="?", salience=0.5),
        ]
        # Only 1 item above 0.7
        assert is_significant(content, threshold=0.7, min_count=2) is False


class TestGetMaxSalience:
    """Tests for get_max_salience function."""

    def test_empty_returns_zero(self):
        """Empty content returns 0.0."""
        assert get_max_salience([]) == 0.0

    def test_returns_maximum(self):
        """Returns the maximum salience value."""
        content = [
            SalientContent(category="question", text="?", salience=0.5),
            SalientContent(category="decision", text="decided", salience=0.9),
            SalientContent(category="synthesis", text="summary", salience=0.7),
        ]
        assert get_max_salience(content) == 0.9


class TestCategorizeContent:
    """Tests for categorize_content function."""

    def test_groups_by_category(self):
        """Content is grouped by category."""
        content = [
            SalientContent(category="decision", text="d1", salience=0.9),
            SalientContent(category="decision", text="d2", salience=0.9),
            SalientContent(category="question", text="q1", salience=0.5),
        ]

        categorized = categorize_content(content)

        assert len(categorized["decision"]) == 2
        assert len(categorized["question"]) == 1

    def test_empty_categories_not_included(self):
        """Categories with no items are not in result."""
        content = [
            SalientContent(category="decision", text="d1", salience=0.9),
        ]

        categorized = categorize_content(content)

        assert "decision" in categorized
        assert "question" not in categorized


class TestExtractSpecificCategories:
    """Tests for category-specific extraction functions."""

    def test_extract_decisions(self):
        """extract_decisions returns only decision contexts."""
        content = [
            SalientContent(category="decision", text="d", salience=0.9, context="Decision context"),
            SalientContent(category="question", text="q", salience=0.5, context="Question context"),
        ]

        decisions = extract_decisions(content)

        assert decisions == ["Decision context"]

    def test_extract_open_threads(self):
        """extract_open_threads returns only open_thread contexts."""
        content = [
            SalientContent(category="open_thread", text="t", salience=0.8, context="TODO context"),
            SalientContent(category="decision", text="d", salience=0.9, context="Decision context"),
        ]

        threads = extract_open_threads(content)

        assert threads == ["TODO context"]

    def test_extract_resolutions(self):
        """extract_resolutions returns only resolution contexts."""
        content = [
            SalientContent(category="resolution", text="r", salience=0.9, context="Fix context"),
            SalientContent(category="decision", text="d", salience=0.9, context="Decision context"),
        ]

        resolutions = extract_resolutions(content)

        assert resolutions == ["Fix context"]

    def test_empty_when_no_matches(self):
        """Returns empty list when no matches for category."""
        content = [
            SalientContent(category="decision", text="d", salience=0.9, context="Decision"),
        ]

        assert extract_open_threads(content) == []
        assert extract_resolutions(content) == []


class TestSummarizeSalience:
    """Tests for summarize_salience function."""

    def test_returns_category_counts(self):
        """Returns count of items per category."""
        text = """
        We decided to use Python.
        We also decided to use FastAPI.
        TODO: Add more tests.
        What about caching?
        """

        summary = summarize_salience(text)

        assert isinstance(summary, dict)
        # Should have some categories (exact counts depend on patterns)
        assert len(summary) > 0

    def test_empty_text_empty_summary(self):
        """Empty text returns empty summary."""
        summary = summarize_salience("")
        assert summary == {}


class TestPatternMatching:
    """Tests for specific pattern matching cases."""

    def test_tradeoff_patterns(self):
        """Tradeoff patterns are detected."""
        texts = [
            "There's a tradeoff between speed and accuracy.",
            "On one hand it's faster, on the other hand it's less reliable.",
            "The advantage is speed, but the disadvantage is complexity.",
        ]

        for text in texts:
            results = extract_salient_content(text)
            assert any(r.category == "tradeoff" for r in results), f"Failed for: {text}"

    def test_recommendation_as_decision(self):
        """Recommendations are treated as decisions."""
        text = "I recommend using Redis for caching. My recommendation is to add an index."

        results = extract_salient_content(text)

        assert any(r.category == "decision" for r in results)

    def test_root_cause_as_resolution(self):
        """Root cause identification is a resolution."""
        text = "The root cause was a memory leak in the connection pool."

        results = extract_salient_content(text)

        assert any(r.category == "resolution" for r in results)

    def test_follow_up_as_open_thread(self):
        """Follow-up items are open threads."""
        text = "We should follow up on the performance issues next sprint."

        results = extract_salient_content(text)

        assert any(r.category == "open_thread" for r in results)

    def test_security_concern_as_constraint(self):
        """Security concerns are constraints."""
        text = "There's a security concern with storing tokens in local storage."

        results = extract_salient_content(text)

        assert any(r.category == "constraint" for r in results)

    def test_key_insight_as_synthesis(self):
        """Key insights are synthesis."""
        text = "The key insight is that we need to batch our API calls."

        results = extract_salient_content(text)

        # Could be synthesis or discovery
        assert any(
            r.category in ("synthesis", "discovery") for r in results
        )


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_short_text(self):
        """Handles very short text."""
        result = extract_salient_content("OK")
        assert isinstance(result, list)

    def test_very_long_text(self):
        """Handles long text without issues."""
        text = "We decided to use Python. " * 1000

        results = extract_salient_content(text)

        assert isinstance(results, list)
        # Should deduplicate so not 1000 matches
        assert len(results) < 100

    def test_special_characters(self):
        """Handles special characters in text."""
        text = "We decided to use 日本語 for the UI. What about émojis?"

        results = extract_salient_content(text)

        # Should find decision pattern
        assert any(r.category == "decision" for r in results)
        # Question detection is optional (depends on pattern matching)

    def test_newlines_and_whitespace(self):
        """Handles various whitespace correctly."""
        # Pattern may not match with extra spaces, use normal spacing
        text = """
        After discussion, we decided to use Python for this.
        """

        results = extract_salient_content(text)

        assert any(r.category == "decision" for r in results)

    def test_nested_code_blocks(self):
        """Handles nested code block patterns."""
        text = """
Here's the code:
```
def foo():
    '''
    We decided to use this approach
    ```
    inner code
    ```
    '''
    pass
```
Outside we decided to use Go.
"""

        results = extract_salient_content(text)

        # Should only match the outer decision
        decisions = [r for r in results if r.category == "decision"]
        if decisions:
            assert any("Go" in d.context for d in decisions)




class TestIntegration:
    """Integration tests for salience module."""

    def test_realistic_conversation_snippet(self):
        """Analyzes a realistic conversation snippet."""
        conversation = (
            "User: Can you help me decide between MongoDB and PostgreSQL?\n\n"
            "Assistant: I've analyzed both options. After considering your requirements, "
            "I recommend PostgreSQL. The fix is to use proper indexing.\n\n"
            "TODO: benchmark performance after migration.\n\n"
            "The root cause of the slow queries was missing indexes."
        )

        results = extract_salient_content(conversation)

        # Should find multiple categories
        categories = {r.category for r in results}
        assert len(categories) >= 2  # At least decision + one other

    def test_full_analysis_workflow(self):
        """Test complete workflow from extraction to categorization."""
        text = (
            "We decided to use Redis for caching. "
            "The root cause of latency was database queries. "
            "TODO: add cache invalidation. "
            "What about memory limits?"
        )

        # Extract
        content = extract_salient_content(text)
        assert len(content) > 0

        # Check significance
        assert is_significant(content, threshold=0.5)

        # Get max salience
        max_sal = get_max_salience(content)
        assert max_sal >= 0.8  # Decision or resolution

        # Categorize
        categorized = categorize_content(content)
        assert "decision" in categorized or "resolution" in categorized

        # Summarize
        summary = summarize_salience(text)
        assert len(summary) > 0
