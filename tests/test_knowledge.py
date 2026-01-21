"""Tests for sage.knowledge module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.knowledge import (
    MAX_PATTERN_LENGTH,
    KnowledgeItem,
    KnowledgeMetadata,
    KnowledgeScope,
    KnowledgeTriggers,
    RecallResult,
    _strip_frontmatter,
    _validate_regex_pattern,
    add_knowledge,
    format_recalled_context,
    load_index,
    load_knowledge_content,
    recall_knowledge,
    remove_knowledge,
    score_item,
)


@pytest.fixture
def mock_knowledge_dir(tmp_path: Path):
    """Create a temporary knowledge directory."""
    knowledge_dir = tmp_path / ".sage" / "knowledge"
    knowledge_dir.mkdir(parents=True)
    (knowledge_dir / "global").mkdir()
    (knowledge_dir / "skills").mkdir()
    return knowledge_dir


@pytest.fixture
def mock_knowledge_paths(tmp_path: Path, mock_knowledge_dir: Path):
    """Patch knowledge paths to use temporary directory."""
    with (
        patch("sage.knowledge.KNOWLEDGE_DIR", mock_knowledge_dir),
        patch("sage.knowledge.KNOWLEDGE_INDEX", mock_knowledge_dir / "index.yaml"),
        patch("sage.knowledge.SAGE_DIR", tmp_path / ".sage"),
        patch("sage.knowledge._add_embedding", return_value=False),
        patch("sage.knowledge._remove_embedding", return_value=True),
        patch("sage.knowledge._get_all_embedding_similarities", return_value={}),
    ):
        yield mock_knowledge_dir


class TestScoreItem:
    """Tests for score_item()."""

    def test_keyword_exact_match_scores_high(self):
        """Exact keyword match scores 3 points."""
        item = KnowledgeItem(
            id="test",
            file="test.md",
            triggers=KnowledgeTriggers(keywords=("gdpr", "privacy")),
            scope=KnowledgeScope(),
            metadata=KnowledgeMetadata(added="2026-01-10"),
        )

        score = score_item(item, "What are the GDPR requirements?", "privacy")
        assert score >= 3

    def test_keyword_substring_match_scores_lower(self):
        """Substring match scores 1 point."""
        item = KnowledgeItem(
            id="test",
            file="test.md",
            triggers=KnowledgeTriggers(keywords=("api",)),
            scope=KnowledgeScope(),
            metadata=KnowledgeMetadata(added="2026-01-10"),
        )

        # "api" appears as substring in "apikey"
        score = score_item(item, "How do I set the apikey?", "test")
        assert score >= 1

    def test_skill_scope_filters_items(self):
        """Items scoped to other skills score 0."""
        item = KnowledgeItem(
            id="test",
            file="test.md",
            triggers=KnowledgeTriggers(keywords=("gdpr",)),
            scope=KnowledgeScope(skills=("privacy",)),
            metadata=KnowledgeMetadata(added="2026-01-10"),
        )

        score = score_item(item, "Tell me about GDPR", "web-dev")
        assert score == 0

    def test_always_inject_gets_base_score(self):
        """Items with always=True get base score regardless of query."""
        item = KnowledgeItem(
            id="test",
            file="test.md",
            triggers=KnowledgeTriggers(),
            scope=KnowledgeScope(always=True),
            metadata=KnowledgeMetadata(added="2026-01-10"),
        )

        score = score_item(item, "Random unrelated query", "any-skill")
        assert score >= 10


class TestAddRemoveKnowledge:
    """Tests for add_knowledge() and remove_knowledge()."""

    def test_add_knowledge_creates_file_and_index(self, mock_knowledge_paths: Path):
        """add_knowledge() creates content file and updates index."""
        item = add_knowledge(
            content="# GDPR Summary\n\nKey points about GDPR...",
            knowledge_id="gdpr-summary",
            keywords=["gdpr", "privacy", "eu"],
            source="Research session 2026-01-10",
        )

        assert item.id == "gdpr-summary"
        assert item.triggers.keywords == ("gdpr", "privacy", "eu")

        # Check file was created
        content_file = mock_knowledge_paths / "global" / "gdpr-summary.md"
        assert content_file.exists()
        assert "GDPR Summary" in content_file.read_text()

        # Check index was updated
        items = load_index()
        assert len(items) == 1
        assert items[0].id == "gdpr-summary"

    def test_add_knowledge_with_skill_scope(self, mock_knowledge_paths: Path):
        """add_knowledge() with skill creates file in skill directory."""
        item = add_knowledge(
            content="Privacy-specific knowledge",
            knowledge_id="consent-patterns",
            keywords=["consent"],
            skill="privacy",
        )

        assert item.scope.skills == ("privacy",)

        # Check file is in skill directory
        content_file = mock_knowledge_paths / "skills" / "privacy" / "consent-patterns.md"
        assert content_file.exists()

    def test_remove_knowledge_deletes_file_and_index(self, mock_knowledge_paths: Path):
        """remove_knowledge() removes content file and index entry."""
        # First add an item
        add_knowledge(
            content="Test content",
            knowledge_id="to-remove",
            keywords=["test"],
        )

        # Verify it exists
        assert len(load_index()) == 1

        # Remove it
        result = remove_knowledge("to-remove")

        assert result is True
        assert len(load_index()) == 0

        # Check file was deleted
        content_file = mock_knowledge_paths / "global" / "to-remove.md"
        assert not content_file.exists()

    def test_remove_nonexistent_returns_false(self, mock_knowledge_paths: Path):
        """remove_knowledge() returns False for nonexistent item."""
        result = remove_knowledge("does-not-exist")
        assert result is False

    def test_path_traversal_prevented(self, mock_knowledge_paths: Path, tmp_path: Path):
        """Path traversal attempts are sanitized."""
        # Try to escape the knowledge directory with path traversal
        item = add_knowledge(
            content="Malicious content",
            knowledge_id="../../../.bashrc",
            keywords=["test"],
        )

        # ID should be sanitized (no path separators)
        assert "/" not in item.id
        assert ".." not in item.id

        # File should be in knowledge directory, not escaped
        assert not (tmp_path / ".bashrc.md").exists()
        assert (mock_knowledge_paths / "global" / f"{item.id}.md").exists()


class TestUpdateKnowledge:
    """Tests for update_knowledge(), deprecate_knowledge(), archive_knowledge()."""

    def test_update_knowledge_changes_content(self, mock_knowledge_paths: Path):
        """update_knowledge() updates content and re-embeds."""
        from sage.knowledge import update_knowledge

        item = add_knowledge(
            content="Original content",
            knowledge_id="test-update",
            keywords=["test"],
        )

        updated = update_knowledge(
            knowledge_id="test-update",
            content="Updated content",
        )

        assert updated is not None
        assert updated.content == "Updated content"
        assert updated.id == "test-update"

    def test_update_knowledge_changes_keywords(self, mock_knowledge_paths: Path):
        """update_knowledge() updates keywords."""
        from sage.knowledge import update_knowledge

        add_knowledge(
            content="Content",
            knowledge_id="test-keywords",
            keywords=["old", "keywords"],
        )

        updated = update_knowledge(
            knowledge_id="test-keywords",
            keywords=["new", "keywords", "here"],
        )

        assert updated is not None
        assert updated.triggers.keywords == ("new", "keywords", "here")

    def test_update_knowledge_changes_status(self, mock_knowledge_paths: Path):
        """update_knowledge() updates status."""
        from sage.knowledge import update_knowledge

        add_knowledge(
            content="Content",
            knowledge_id="test-status",
            keywords=["test"],
        )

        updated = update_knowledge(
            knowledge_id="test-status",
            status="deprecated",
        )

        assert updated is not None
        assert updated.metadata.status == "deprecated"

    def test_update_knowledge_returns_none_for_missing(self, mock_knowledge_paths: Path):
        """update_knowledge() returns None if item not found."""
        from sage.knowledge import update_knowledge

        result = update_knowledge(
            knowledge_id="nonexistent-item",
            content="New content",
        )

        assert result is None

    def test_update_knowledge_preserves_unchanged_fields(self, mock_knowledge_paths: Path):
        """update_knowledge() preserves fields not being updated."""
        from sage.knowledge import update_knowledge

        add_knowledge(
            content="Original content",
            knowledge_id="test-preserve",
            keywords=["original", "keywords"],
            source="original source",
        )

        updated = update_knowledge(
            knowledge_id="test-preserve",
            content="New content",
        )

        assert updated is not None
        assert updated.content == "New content"
        assert updated.triggers.keywords == ("original", "keywords")
        assert updated.metadata.source == "original source"

    def test_deprecate_knowledge_sets_status(self, mock_knowledge_paths: Path):
        """deprecate_knowledge() marks item as deprecated."""
        from sage.knowledge import deprecate_knowledge

        add_knowledge(
            content="Content",
            knowledge_id="test-deprecate",
            keywords=["test"],
        )

        result = deprecate_knowledge(
            knowledge_id="test-deprecate",
            reason="Outdated information",
        )

        assert result is not None
        assert result.metadata.status == "deprecated"
        assert "DEPRECATED" in result.metadata.source
        assert "Outdated information" in result.metadata.source

    def test_deprecate_knowledge_with_replacement(self, mock_knowledge_paths: Path):
        """deprecate_knowledge() includes replacement reference."""
        from sage.knowledge import deprecate_knowledge

        add_knowledge(
            content="Old content",
            knowledge_id="old-item",
            keywords=["test"],
        )
        add_knowledge(
            content="New content",
            knowledge_id="new-item",
            keywords=["test"],
        )

        result = deprecate_knowledge(
            knowledge_id="old-item",
            reason="Replaced",
            replacement_id="new-item",
        )

        assert result is not None
        assert "new-item" in result.metadata.source

    def test_archive_knowledge_sets_status(self, mock_knowledge_paths: Path):
        """archive_knowledge() marks item as archived."""
        from sage.knowledge import archive_knowledge

        add_knowledge(
            content="Content",
            knowledge_id="test-archive",
            keywords=["test"],
        )

        result = archive_knowledge("test-archive")

        assert result is not None
        assert result.metadata.status == "archived"

    def test_archived_items_excluded_from_recall(self, mock_knowledge_paths: Path):
        """Archived items are not returned by recall_knowledge()."""
        from sage.knowledge import archive_knowledge

        add_knowledge(
            content="Content about testing",
            knowledge_id="test-exclude",
            keywords=["testing", "excluded"],
        )

        # Verify it matches before archiving
        result = recall_knowledge("testing excluded", skill_name="test", threshold=0.0)
        assert any(i.id == "test-exclude" for i in result.items)

        # Archive it
        archive_knowledge("test-exclude")

        # Verify it's excluded after archiving
        result = recall_knowledge("testing excluded", skill_name="test", threshold=0.0)
        assert not any(i.id == "test-exclude" for i in result.items)

    def test_deprecated_items_still_recalled(self, mock_knowledge_paths: Path):
        """Deprecated items are still returned by recall_knowledge()."""
        from sage.knowledge import deprecate_knowledge

        add_knowledge(
            content="Content about features",
            knowledge_id="test-deprecated-recall",
            keywords=["features", "deprecated"],
        )

        deprecate_knowledge("test-deprecated-recall", reason="Old")

        result = recall_knowledge("features deprecated", skill_name="test", threshold=0.0)
        assert any(i.id == "test-deprecated-recall" for i in result.items)


class TestRecallKnowledge:
    """Tests for recall_knowledge()."""

    def test_recall_returns_matching_items(self, mock_knowledge_paths: Path):
        """recall_knowledge() returns items matching query keywords."""
        # Add some knowledge items
        add_knowledge(
            content="GDPR content",
            knowledge_id="gdpr",
            keywords=["gdpr", "privacy"],
        )
        add_knowledge(
            content="API content",
            knowledge_id="api",
            keywords=["api", "rest"],
        )

        result = recall_knowledge("What are the GDPR requirements?", "privacy", threshold=2.0)

        assert result.count == 1
        assert result.items[0].id == "gdpr"

    def test_recall_respects_max_items(self, mock_knowledge_paths: Path):
        """recall_knowledge() respects max_items limit."""
        # Add several matching items
        for i in range(5):
            add_knowledge(
                content=f"Content {i}",
                knowledge_id=f"item-{i}",
                keywords=["common"],
            )

        result = recall_knowledge("common topic", "test", max_items=2, threshold=2.0)

        assert result.count == 2

    def test_recall_respects_threshold(self, mock_knowledge_paths: Path):
        """recall_knowledge() only returns items above threshold."""
        add_knowledge(
            content="Weak match content",
            knowledge_id="weak",
            keywords=["obscure"],  # won't match well
        )

        result = recall_knowledge("totally different query", "test", threshold=2)

        assert result.count == 0


class TestFormatRecalledContext:
    """Tests for format_recalled_context()."""

    def test_format_empty_result(self):
        """Empty result returns empty string."""
        result = RecallResult(items=[], total_tokens=0)
        assert format_recalled_context(result) == ""

    def test_format_includes_item_content(self):
        """Formatted context includes item content."""
        item = KnowledgeItem(
            id="test-item",
            file="test.md",
            triggers=KnowledgeTriggers(),
            scope=KnowledgeScope(),
            metadata=KnowledgeMetadata(added="2026-01-10", source="test source"),
            content="# Test Content\n\nThis is the knowledge.",
        )
        result = RecallResult(items=[item], total_tokens=100)

        formatted = format_recalled_context(result)

        assert "📚 Recalled Knowledge (1 items" in formatted
        assert "## test-item" in formatted
        assert "test source" in formatted
        assert "This is the knowledge" in formatted


class TestStripFrontmatter:
    """Tests for _strip_frontmatter() function."""

    def test_strips_valid_frontmatter(self):
        """_strip_frontmatter() removes YAML frontmatter."""
        content = """---
id: test
type: knowledge
keywords:
- test
---

## Actual Content

This is the body."""

        result = _strip_frontmatter(content)

        assert result == "## Actual Content\n\nThis is the body."
        assert "---" not in result
        assert "id: test" not in result

    def test_returns_content_without_frontmatter_unchanged(self):
        """_strip_frontmatter() returns content without frontmatter as-is."""
        content = """## No Frontmatter

Just regular markdown content."""

        result = _strip_frontmatter(content)

        assert result == content

    def test_handles_empty_frontmatter(self):
        """_strip_frontmatter() handles empty frontmatter."""
        content = """---
---

Body content."""

        result = _strip_frontmatter(content)

        assert result == "Body content."

    def test_handles_incomplete_frontmatter(self):
        """_strip_frontmatter() handles incomplete frontmatter gracefully."""
        content = """---
id: test
no closing delimiter"""

        result = _strip_frontmatter(content)

        # Should return original since frontmatter is incomplete
        assert result == content


class TestKnowledgeFrontmatter:
    """Tests for knowledge frontmatter handling."""

    def test_add_knowledge_writes_frontmatter(self, mock_knowledge_paths: Path):
        """add_knowledge() writes content with YAML frontmatter."""
        add_knowledge(
            content="## Test Content\n\nBody here.",
            knowledge_id="frontmatter-test",
            keywords=["test", "frontmatter"],
            source="test suite",
        )

        # Read the raw file
        file_path = mock_knowledge_paths / "global" / "frontmatter-test.md"
        raw_content = file_path.read_text()

        # Should have frontmatter
        assert raw_content.startswith("---\n")
        assert "id: frontmatter-test" in raw_content
        assert "type: knowledge" in raw_content
        assert "test" in raw_content  # keyword
        assert "frontmatter" in raw_content  # keyword
        assert "source: test suite" in raw_content
        assert "## Test Content" in raw_content

    def test_load_knowledge_content_strips_frontmatter(self, mock_knowledge_paths: Path):
        """load_knowledge_content() strips frontmatter from loaded content."""
        # Add knowledge (which writes frontmatter)
        item = add_knowledge(
            content="## Actual Content\n\nThis should be visible.",
            knowledge_id="strip-test",
            keywords=["strip"],
        )

        # Load the content
        loaded = load_knowledge_content(item)

        # Content should NOT have frontmatter
        assert "---" not in loaded.content
        assert "id: strip-test" not in loaded.content
        assert "## Actual Content" in loaded.content
        assert "This should be visible." in loaded.content

    def test_frontmatter_roundtrip(self, mock_knowledge_paths: Path):
        """Content survives frontmatter round-trip."""
        original_content = """## Knowledge Title

This is important information.

- Point 1
- Point 2

### Subsection

More details here."""

        item = add_knowledge(
            content=original_content,
            knowledge_id="roundtrip-test",
            keywords=["roundtrip"],
        )

        loaded = load_knowledge_content(item)

        # Content should match original (minus frontmatter)
        assert loaded.content == original_content

    def test_frontmatter_includes_skill_when_scoped(self, mock_knowledge_paths: Path):
        """Frontmatter includes skill field when knowledge is skill-scoped."""
        add_knowledge(
            content="Skill-specific content",
            knowledge_id="scoped-test",
            keywords=["scoped"],
            skill="my-skill",
        )

        # Read the raw file
        file_path = mock_knowledge_paths / "skills" / "my-skill" / "scoped-test.md"
        raw_content = file_path.read_text()

        assert "skill: my-skill" in raw_content


class TestKnowledgeBackwardCompatibility:
    """Tests for backward compatibility with legacy knowledge files."""

    def test_load_content_without_frontmatter(self, mock_knowledge_paths: Path):
        """load_knowledge_content() handles legacy files without frontmatter."""
        # Create a legacy file without frontmatter
        legacy_content = """## Legacy Content

This file has no frontmatter."""

        legacy_path = mock_knowledge_paths / "global" / "legacy-item.md"
        legacy_path.write_text(legacy_content)

        # Create an index entry pointing to it
        item = KnowledgeItem(
            id="legacy-item",
            file="global/legacy-item.md",
            triggers=KnowledgeTriggers(keywords=("legacy",)),
            scope=KnowledgeScope(),
            metadata=KnowledgeMetadata(added="2026-01-01", source="legacy", tokens=50),
        )

        # Simulate loading (need to use the actual function with patched KNOWLEDGE_DIR)
        with patch("sage.knowledge.KNOWLEDGE_DIR", mock_knowledge_paths):
            loaded = load_knowledge_content(item)

        # Should work fine, content unchanged
        assert loaded.content == legacy_content
        assert "## Legacy Content" in loaded.content


class TestKnowledgeSecurity:
    """Security tests for knowledge module."""

    def test_regex_redos_pattern_rejected(self):
        """Dangerous ReDoS patterns are rejected."""
        # Known ReDoS patterns
        dangerous_patterns = [
            "(a+)+b",  # Nested quantifiers
            "((a+)+)+",  # Multiple nesting
            "([a-z]+)+",  # Character class with nested quantifier
        ]

        for pattern in dangerous_patterns:
            result = _validate_regex_pattern(pattern)
            assert result is not None, f"Pattern {pattern} should be rejected"
            assert "dangerous" in result.lower() or "nested" in result.lower()

    def test_regex_long_pattern_rejected(self):
        """Overly long regex patterns are rejected."""
        long_pattern = "a" * (MAX_PATTERN_LENGTH + 1)
        result = _validate_regex_pattern(long_pattern)

        assert result is not None
        assert "too long" in result.lower()

    def test_regex_invalid_pattern_rejected(self):
        """Invalid regex patterns are rejected."""
        invalid_patterns = [
            "[unclosed",
            "(unmatched",
            "**invalid",
        ]

        for pattern in invalid_patterns:
            result = _validate_regex_pattern(pattern)
            assert result is not None, f"Pattern {pattern} should be rejected"
            assert "invalid" in result.lower()

    def test_regex_safe_pattern_accepted(self):
        """Safe regex patterns are accepted."""
        safe_patterns = [
            r"\bword\b",
            r"api[_-]?key",
            r"(foo|bar)",
            r"test\d+",
        ]

        for pattern in safe_patterns:
            result = _validate_regex_pattern(pattern)
            assert result is None, f"Pattern {pattern} should be accepted"

    def test_add_knowledge_filters_dangerous_patterns(self, mock_knowledge_paths: Path):
        """add_knowledge filters out dangerous patterns."""
        item = add_knowledge(
            content="Test content",
            knowledge_id="test-security",
            keywords=["test"],
            patterns=["safe.*pattern", "(a+)+b"],  # One safe, one dangerous
        )

        # Only safe pattern should be stored
        assert len(item.triggers.patterns) == 1
        assert "safe.*pattern" in item.triggers.patterns

    def test_knowledge_file_permissions(self, mock_knowledge_paths: Path):
        """Knowledge files are created with restricted permissions."""
        import stat

        item = add_knowledge(
            content="Sensitive content",
            knowledge_id="perm-test",
            keywords=["test"],
        )

        file_path = mock_knowledge_paths / item.file
        mode = file_path.stat().st_mode

        # Should be owner read/write only (0o600)
        assert mode & stat.S_IRWXU == stat.S_IRUSR | stat.S_IWUSR  # Owner: rw
        assert mode & stat.S_IRWXG == 0  # Group: none
        assert mode & stat.S_IRWXO == 0  # Other: none

    def test_knowledge_index_permissions(self, mock_knowledge_paths: Path):
        """Knowledge index is created with restricted permissions."""
        import stat

        add_knowledge(
            content="Test content",
            knowledge_id="index-perm-test",
            keywords=["test"],
        )

        index_path = mock_knowledge_paths / "index.yaml"
        mode = index_path.stat().st_mode

        # Should be owner read/write only
        assert mode & stat.S_IRWXG == 0  # Group: none
        assert mode & stat.S_IRWXO == 0  # Other: none


class TestKnowledgeTypes:
    """Tests for knowledge types feature."""

    def test_default_type_is_knowledge(self, mock_knowledge_paths: Path):
        """Default item_type is 'knowledge'."""
        item = add_knowledge(
            content="Test content",
            knowledge_id="default-type-test",
            keywords=["test"],
        )

        assert item.item_type == "knowledge"

    def test_can_create_todo_type(self, mock_knowledge_paths: Path):
        """Can create knowledge with todo type."""
        item = add_knowledge(
            content="Todo content",
            knowledge_id="todo-test",
            keywords=["todo"],
            item_type="todo",
        )

        assert item.item_type == "todo"
        assert item.metadata.status == "pending"

    def test_can_create_preference_type(self, mock_knowledge_paths: Path):
        """Can create knowledge with preference type."""
        item = add_knowledge(
            content="Preference content",
            knowledge_id="pref-test",
            keywords=["pref"],
            item_type="preference",
        )

        assert item.item_type == "preference"

    def test_can_create_reference_type(self, mock_knowledge_paths: Path):
        """Can create knowledge with reference type."""
        item = add_knowledge(
            content="Reference content",
            knowledge_id="ref-test",
            keywords=["ref"],
            item_type="reference",
        )

        assert item.item_type == "reference"

    def test_invalid_type_falls_back_to_knowledge(self, mock_knowledge_paths: Path):
        """Invalid item_type falls back to 'knowledge'."""
        item = add_knowledge(
            content="Test content",
            knowledge_id="invalid-type-test",
            keywords=["test"],
            item_type="invalid_type",
        )

        assert item.item_type == "knowledge"

    def test_type_persists_in_index(self, mock_knowledge_paths: Path):
        """Item type is persisted in index."""
        add_knowledge(
            content="Todo content",
            knowledge_id="persist-test",
            keywords=["todo"],
            item_type="todo",
        )

        items = load_index()
        item = next(i for i in items if i.id == "persist-test")
        assert item.item_type == "todo"

    def test_type_in_frontmatter(self, mock_knowledge_paths: Path):
        """Item type is written to file frontmatter."""
        add_knowledge(
            content="Preference content",
            knowledge_id="frontmatter-type-test",
            keywords=["pref"],
            item_type="preference",
        )

        file_path = mock_knowledge_paths / "global" / "frontmatter-type-test.md"
        raw_content = file_path.read_text()

        assert "type: preference" in raw_content


class TestTodoFunctions:
    """Tests for todo-specific functions."""

    def test_list_todos_returns_only_todos(self, mock_knowledge_paths: Path):
        """list_todos returns only todo-type items."""
        from sage.knowledge import list_todos

        add_knowledge(content="Knowledge", knowledge_id="k1", keywords=["k"], item_type="knowledge")
        add_knowledge(content="Todo 1", knowledge_id="t1", keywords=["t"], item_type="todo")
        add_knowledge(content="Todo 2", knowledge_id="t2", keywords=["t"], item_type="todo")
        add_knowledge(content="Pref", knowledge_id="p1", keywords=["p"], item_type="preference")

        todos = list_todos()

        assert len(todos) == 2
        assert all(t.item_type == "todo" for t in todos)

    def test_list_todos_filter_by_status(self, mock_knowledge_paths: Path):
        """list_todos can filter by status."""
        from sage.knowledge import list_todos, mark_todo_done

        add_knowledge(content="Todo 1", knowledge_id="t1", keywords=["t"], item_type="todo")
        add_knowledge(content="Todo 2", knowledge_id="t2", keywords=["t"], item_type="todo")
        mark_todo_done("t1")

        pending = list_todos(status="pending")
        done = list_todos(status="done")

        assert len(pending) == 1
        assert pending[0].id == "t2"
        assert len(done) == 1
        assert done[0].id == "t1"

    def test_mark_todo_done_updates_status(self, mock_knowledge_paths: Path):
        """mark_todo_done updates the status to done."""
        from sage.knowledge import list_todos, mark_todo_done

        add_knowledge(content="Todo", knowledge_id="mark-test", keywords=["t"], item_type="todo")

        result = mark_todo_done("mark-test")

        assert result is True
        todos = list_todos(status="done")
        assert len(todos) == 1
        assert todos[0].id == "mark-test"

    def test_mark_todo_done_returns_false_for_nonexistent(self, mock_knowledge_paths: Path):
        """mark_todo_done returns False for nonexistent todo."""
        from sage.knowledge import mark_todo_done

        result = mark_todo_done("nonexistent")

        assert result is False

    def test_mark_todo_done_returns_false_for_non_todo(self, mock_knowledge_paths: Path):
        """mark_todo_done returns False for non-todo item."""
        from sage.knowledge import mark_todo_done

        add_knowledge(content="Knowledge", knowledge_id="not-a-todo", keywords=["k"])

        result = mark_todo_done("not-a-todo")

        assert result is False

    def test_get_pending_todos(self, mock_knowledge_paths: Path):
        """get_pending_todos returns only pending todos."""
        from sage.knowledge import get_pending_todos, mark_todo_done

        add_knowledge(content="Todo 1", knowledge_id="t1", keywords=["t"], item_type="todo")
        add_knowledge(content="Todo 2", knowledge_id="t2", keywords=["t"], item_type="todo")
        mark_todo_done("t1")

        pending = get_pending_todos()

        assert len(pending) == 1
        assert pending[0].id == "t2"


class TestTypeAwareRecall:
    """Tests for type-aware recall thresholds."""

    def test_get_type_threshold_returns_correct_values(self):
        """get_type_threshold returns correct threshold for each type."""
        from sage.knowledge import get_type_threshold

        # Knowledge: 0.70 * 10 = 7.0
        assert get_type_threshold("knowledge") == 7.0
        # Preference: 0.30 * 10 = 3.0
        assert get_type_threshold("preference") == 3.0
        # Todo: 0.40 * 10 = 4.0
        assert get_type_threshold("todo") == 4.0
        # Reference: 0.80 * 10 = 8.0
        assert get_type_threshold("reference") == 8.0

    def test_get_type_threshold_returns_default_for_unknown(self):
        """get_type_threshold returns default for unknown type."""
        from sage.knowledge import DEFAULT_TYPE_THRESHOLD, get_type_threshold

        result = get_type_threshold("unknown_type")

        assert result == DEFAULT_TYPE_THRESHOLD * 10.0

    def test_recall_with_item_types_filter(self, mock_knowledge_paths: Path):
        """recall_knowledge can filter by item_types."""
        add_knowledge(content="K1", knowledge_id="k1", keywords=["common"], item_type="knowledge")
        add_knowledge(content="T1", knowledge_id="t1", keywords=["common"], item_type="todo")
        add_knowledge(content="P1", knowledge_id="p1", keywords=["common"], item_type="preference")

        # Recall only todos
        result = recall_knowledge(
            "common query",
            "test",
            threshold=0.1,  # Low threshold to match
            item_types=("todo",),
        )

        assert result.count == 1
        assert result.items[0].id == "t1"


class TestKnowledgeTypeConstants:
    """Tests for knowledge type constants."""

    def test_knowledge_types_tuple(self):
        """KNOWLEDGE_TYPES contains expected types."""
        from sage.knowledge import KNOWLEDGE_TYPES

        assert "knowledge" in KNOWLEDGE_TYPES
        assert "preference" in KNOWLEDGE_TYPES
        assert "todo" in KNOWLEDGE_TYPES
        assert "reference" in KNOWLEDGE_TYPES
        assert len(KNOWLEDGE_TYPES) == 4

    def test_type_thresholds_dict(self):
        """TYPE_THRESHOLDS contains thresholds for all types."""
        from sage.knowledge import KNOWLEDGE_TYPES, TYPE_THRESHOLDS

        for t in KNOWLEDGE_TYPES:
            assert t in TYPE_THRESHOLDS
            assert 0.0 <= TYPE_THRESHOLDS[t] <= 1.0
