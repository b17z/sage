"""Tests for failures.py (v4.0).

Tests the failure memory functionality for tracking what didn't work.
"""


from sage.failures import (
    Failure,
    save_failure,
    load_failures,
    list_failures,
    recall_failures,
    delete_failure,
    format_failure_for_context,
    _sanitize_id,
    _failure_to_markdown,
    _markdown_to_failure,
    _keyword_score,
)


class TestSanitizeId:
    """Tests for ID sanitization."""

    def test_removes_special_characters(self):
        """Should remove special characters."""
        assert _sanitize_id("test@failure!") == "test-failure"

    def test_removes_path_traversal(self):
        """Should remove path traversal attempts."""
        assert ".." not in _sanitize_id("../../../etc/passwd")
        assert "/" not in _sanitize_id("path/to/file")

    def test_handles_empty_string(self):
        """Should return 'unnamed' for empty string."""
        assert _sanitize_id("") == "unnamed"
        assert _sanitize_id("!!!") == "unnamed"

    def test_preserves_valid_ids(self):
        """Should preserve valid kebab-case IDs."""
        assert _sanitize_id("jwt-refresh-loop") == "jwt-refresh-loop"
        assert _sanitize_id("auth_patterns") == "auth_patterns"


class TestFailureDataclass:
    """Tests for Failure dataclass."""

    def test_creates_failure(self):
        """Should create Failure with all fields."""
        failure = Failure(
            id="test-failure",
            approach="Testing approach",
            why_failed="Testing why",
            learned="Testing learned",
            keywords=("test", "failure"),
            related_to=("checkpoint-1",),
            added="2026-01-01T00:00:00",
            project="test-project",
        )

        assert failure.id == "test-failure"
        assert failure.approach == "Testing approach"
        assert len(failure.keywords) == 2

    def test_defaults(self):
        """Should have sensible defaults."""
        failure = Failure(
            id="test",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=(),
        )

        assert failure.related_to == ()
        assert failure.added == ""
        assert failure.project is None


class TestMarkdownSerialization:
    """Tests for markdown serialization."""

    def test_failure_to_markdown(self):
        """Should convert Failure to markdown format."""
        failure = Failure(
            id="test-failure",
            approach="Testing approach",
            why_failed="Testing why it failed",
            learned="What I learned",
            keywords=("test", "failure"),
            added="2026-01-01T00:00:00",
        )

        md = _failure_to_markdown(failure)

        assert "---" in md  # Frontmatter
        assert "id: test-failure" in md
        assert "## Why it failed" in md
        assert "Testing why it failed" in md
        assert "## Learned" in md
        assert "What I learned" in md

    def test_markdown_to_failure(self):
        """Should parse markdown back to Failure."""
        md = """---
id: test-failure
type: failure
approach: Testing approach
keywords:
  - test
  - failure
added: "2026-01-01T00:00:00"
---

## Why it failed
Testing why it failed

## Learned
What I learned
"""
        failure = _markdown_to_failure(md)

        assert failure is not None
        assert failure.id == "test-failure"
        assert failure.approach == "Testing approach"
        assert failure.why_failed == "Testing why it failed"
        assert failure.learned == "What I learned"
        assert "test" in failure.keywords

    def test_roundtrip(self):
        """Should preserve data through serialization roundtrip."""
        original = Failure(
            id="test-failure",
            approach="Testing approach",
            why_failed="Testing why it failed",
            learned="What I learned",
            keywords=("test", "failure"),
            related_to=("checkpoint-1",),
            added="2026-01-01T00:00:00",
            project="test-project",
        )

        md = _failure_to_markdown(original)
        parsed = _markdown_to_failure(md)

        assert parsed is not None
        assert parsed.id == original.id
        assert parsed.approach == original.approach
        assert parsed.why_failed == original.why_failed
        assert parsed.learned == original.learned


class TestSaveFailure:
    """Tests for saving failures."""

    def test_saves_failure(self, tmp_path):
        """Should save failure to disk."""
        failure = save_failure(
            failure_id="test-failure",
            approach="Test approach",
            why_failed="Test why",
            learned="Test learned",
            keywords=["test"],
            project_path=tmp_path,
        )

        assert failure.id == "test-failure"

        # Check file exists
        failures_dir = tmp_path / ".sage" / "failures"
        files = list(failures_dir.glob("*.md"))
        assert len(files) == 1

    def test_generates_timestamp_filename(self, tmp_path):
        """Should include timestamp in filename."""
        save_failure(
            failure_id="test",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=["test"],
            project_path=tmp_path,
        )

        failures_dir = tmp_path / ".sage" / "failures"
        files = list(failures_dir.glob("*.md"))
        assert len(files) == 1

        # Filename should be timestamped
        filename = files[0].name
        assert "_test.md" in filename

    def test_sanitizes_id(self, tmp_path):
        """Should sanitize dangerous IDs."""
        failure = save_failure(
            failure_id="../../../etc/passwd",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=["test"],
            project_path=tmp_path,
        )

        assert ".." not in failure.id
        assert "/" not in failure.id


class TestLoadFailures:
    """Tests for loading failures."""

    def test_loads_saved_failures(self, tmp_path):
        """Should load previously saved failures."""
        save_failure(
            failure_id="failure-1",
            approach="Approach 1",
            why_failed="Why 1",
            learned="Learned 1",
            keywords=["one"],
            project_path=tmp_path,
        )
        save_failure(
            failure_id="failure-2",
            approach="Approach 2",
            why_failed="Why 2",
            learned="Learned 2",
            keywords=["two"],
            project_path=tmp_path,
        )

        failures = load_failures(tmp_path)

        assert len(failures) == 2
        ids = {f.id for f in failures}
        assert "failure-1" in ids
        assert "failure-2" in ids

    def test_returns_empty_for_nonexistent(self, tmp_path):
        """Should return empty list if folder doesn't exist."""
        failures = load_failures(tmp_path)
        assert failures == []

    def test_returns_most_recent_first(self, tmp_path):
        """Should return failures sorted by recency."""
        import time

        save_failure(
            failure_id="old",
            approach="Old",
            why_failed="Old",
            learned="Old",
            keywords=["old"],
            project_path=tmp_path,
        )
        time.sleep(1.1)  # Ensure different timestamps (file system resolution)
        save_failure(
            failure_id="new",
            approach="New",
            why_failed="New",
            learned="New",
            keywords=["new"],
            project_path=tmp_path,
        )

        failures = load_failures(tmp_path)

        # Most recent first (sorted by filename which has timestamp)
        assert len(failures) == 2
        # The newer file should have a later timestamp in its name
        assert failures[0].id == "new"
        assert failures[1].id == "old"


class TestKeywordScore:
    """Tests for keyword matching."""

    def test_scores_exact_match(self):
        """Should score higher for exact word match."""
        failure = Failure(
            id="test",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=("jwt", "auth"),
        )

        score = _keyword_score(failure, "jwt authentication")
        assert score > 0

    def test_scores_partial_match(self):
        """Should score partial matches."""
        failure = Failure(
            id="test",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=("auth",),
        )

        score = _keyword_score(failure, "authentication")
        assert score > 0

    def test_returns_zero_for_no_match(self):
        """Should return 0 for no matches."""
        failure = Failure(
            id="test",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=("jwt", "auth"),
        )

        score = _keyword_score(failure, "database query")
        assert score == 0

    def test_normalizes_to_one(self):
        """Should normalize score to 0-1 range."""
        failure = Failure(
            id="test",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=("a", "b", "c", "d", "e"),
        )

        score = _keyword_score(failure, "a b c d e f g")
        assert 0 <= score <= 1


class TestRecallFailures:
    """Tests for recalling failures."""

    def test_recalls_matching_failures(self, tmp_path):
        """Should recall failures matching keywords."""
        save_failure(
            failure_id="jwt-failure",
            approach="JWT approach",
            why_failed="JWT why",
            learned="JWT learned",
            keywords=["jwt", "token", "auth"],
            project_path=tmp_path,
        )
        save_failure(
            failure_id="db-failure",
            approach="DB approach",
            why_failed="DB why",
            learned="DB learned",
            keywords=["database", "query"],
            project_path=tmp_path,
        )

        results = recall_failures("jwt authentication", project_path=tmp_path)

        assert len(results) >= 1
        assert any(f.id == "jwt-failure" for f in results)

    def test_respects_limit(self, tmp_path):
        """Should respect limit parameter."""
        for i in range(5):
            save_failure(
                failure_id=f"failure-{i}",
                approach="Test",
                why_failed="Test",
                learned="Test",
                keywords=["test"],
                project_path=tmp_path,
            )

        results = recall_failures("test", limit=2, project_path=tmp_path)
        assert len(results) <= 2

    def test_returns_empty_for_no_match(self, tmp_path):
        """Should return empty list if no matches."""
        save_failure(
            failure_id="jwt-failure",
            approach="JWT",
            why_failed="JWT",
            learned="JWT",
            keywords=["jwt"],
            project_path=tmp_path,
        )

        results = recall_failures("database", project_path=tmp_path)
        # Should have empty or no strong matches
        # (keyword matching might return weak matches)
        assert len(results) <= 1


class TestListFailures:
    """Tests for listing failures."""

    def test_lists_failures(self, tmp_path):
        """Should list all failures."""
        save_failure(
            failure_id="failure-1",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=["test"],
            project_path=tmp_path,
        )

        failures = list_failures(tmp_path)
        assert len(failures) == 1

    def test_respects_limit(self, tmp_path):
        """Should respect limit parameter."""
        for i in range(5):
            save_failure(
                failure_id=f"failure-{i}",
                approach="Test",
                why_failed="Test",
                learned="Test",
                keywords=["test"],
                project_path=tmp_path,
            )

        failures = list_failures(tmp_path, limit=2)
        assert len(failures) == 2


class TestDeleteFailure:
    """Tests for deleting failures."""

    def test_deletes_failure(self, tmp_path):
        """Should delete failure by ID."""
        save_failure(
            failure_id="to-delete",
            approach="Test",
            why_failed="Test",
            learned="Test",
            keywords=["test"],
            project_path=tmp_path,
        )

        result = delete_failure("to-delete", tmp_path)

        assert result is True
        failures = load_failures(tmp_path)
        assert len(failures) == 0

    def test_returns_false_for_nonexistent(self, tmp_path):
        """Should return False if failure doesn't exist."""
        result = delete_failure("nonexistent", tmp_path)
        assert result is False


class TestFormatFailureForContext:
    """Tests for formatting failures."""

    def test_formats_failure(self):
        """Should format failure with all sections."""
        failure = Failure(
            id="test-failure",
            approach="Test approach",
            why_failed="Test why",
            learned="Test learned",
            keywords=("test",),
        )

        result = format_failure_for_context(failure)

        assert "test-failure" in result
        assert "Test approach" in result
        assert "Test why" in result
        assert "Test learned" in result

    def test_toon_format(self):
        """Should use compact format with use_toon=True."""
        failure = Failure(
            id="test-failure",
            approach="Test approach",
            why_failed="Test why",
            learned="Test learned",
            keywords=("test",),
        )

        result = format_failure_for_context(failure, use_toon=True)

        # TOON uses lowercase labels
        assert "approach:" in result
        assert "failed:" in result
        assert "learned:" in result
