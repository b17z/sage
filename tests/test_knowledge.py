"""Tests for sage.knowledge module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.knowledge import (
    KnowledgeItem,
    KnowledgeMetadata,
    KnowledgeScope,
    KnowledgeTriggers,
    RecallResult,
    add_knowledge,
    format_recalled_context,
    list_knowledge,
    load_index,
    recall_knowledge,
    remove_knowledge,
    save_index,
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
    with patch("sage.knowledge.KNOWLEDGE_DIR", mock_knowledge_dir), \
         patch("sage.knowledge.KNOWLEDGE_INDEX", mock_knowledge_dir / "index.yaml"), \
         patch("sage.knowledge.SAGE_DIR", tmp_path / ".sage"):
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
        
        result = recall_knowledge("What are the GDPR requirements?", "privacy")
        
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
        
        result = recall_knowledge("common topic", "test", max_items=2)
        
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
