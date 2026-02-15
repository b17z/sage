"""Tests for knowledge linking (v4.0).

Tests the knowledge linking functionality for multi-hop reasoning.
"""

import pytest

from sage.knowledge import (
    KnowledgeLink,
    add_knowledge,
    link_knowledge,
    get_linked_knowledge,
    load_index,
)


class TestKnowledgeLinkDataclass:
    """Tests for KnowledgeLink dataclass."""

    def test_creates_link(self):
        """Should create KnowledgeLink with all fields."""
        link = KnowledgeLink(
            target_id="target-item",
            relation="extends",
            note="Extended with new patterns",
        )

        assert link.target_id == "target-item"
        assert link.relation == "extends"
        assert link.note == "Extended with new patterns"

    def test_defaults(self):
        """Should have sensible defaults."""
        link = KnowledgeLink(target_id="target")

        assert link.relation == "related"
        assert link.note == ""


class TestLinkKnowledge:
    """Tests for link_knowledge()."""

    def test_creates_link(self, tmp_path):
        """Should create a link between two knowledge items."""
        # Create source and target items
        add_knowledge(
            content="Source content",
            knowledge_id="source-item",
            keywords=["source"],
            project_path=tmp_path,
        )
        add_knowledge(
            content="Target content",
            knowledge_id="target-item",
            keywords=["target"],
            project_path=tmp_path,
        )

        # Create link
        result = link_knowledge(
            source_id="source-item",
            target_id="target-item",
            relation="extends",
            project_path=tmp_path,
        )

        assert result is not None
        assert result.id == "source-item"
        assert len(result.knowledge_links) == 1
        assert result.knowledge_links[0].target_id == "target-item"
        assert result.knowledge_links[0].relation == "extends"

    def test_returns_none_for_missing_source(self, tmp_path):
        """Should return None if source doesn't exist."""
        add_knowledge(
            content="Target",
            knowledge_id="target",
            keywords=["target"],
            project_path=tmp_path,
        )

        result = link_knowledge(
            source_id="nonexistent",
            target_id="target",
            project_path=tmp_path,
        )

        assert result is None

    def test_returns_none_for_missing_target(self, tmp_path):
        """Should return None if target doesn't exist."""
        add_knowledge(
            content="Source",
            knowledge_id="source",
            keywords=["source"],
            project_path=tmp_path,
        )

        result = link_knowledge(
            source_id="source",
            target_id="nonexistent",
            project_path=tmp_path,
        )

        assert result is None

    def test_adds_note(self, tmp_path):
        """Should include note in link."""
        add_knowledge(content="Source", knowledge_id="source", keywords=["s"], project_path=tmp_path)
        add_knowledge(content="Target", knowledge_id="target", keywords=["t"], project_path=tmp_path)

        result = link_knowledge(
            source_id="source",
            target_id="target",
            note="Important relationship",
            project_path=tmp_path,
        )

        assert result.knowledge_links[0].note == "Important relationship"

    def test_bidirectional_link(self, tmp_path):
        """Should create reverse link when bidirectional=True."""
        add_knowledge(content="A", knowledge_id="a", keywords=["a"], project_path=tmp_path)
        add_knowledge(content="B", knowledge_id="b", keywords=["b"], project_path=tmp_path)

        link_knowledge(
            source_id="a",
            target_id="b",
            relation="related",
            bidirectional=True,
            project_path=tmp_path,
        )

        items = load_index(project_path=tmp_path)
        item_a = next(i for i in items if i.id == "a")
        item_b = next(i for i in items if i.id == "b")

        # Both should have links
        assert len(item_a.knowledge_links) == 1
        assert item_a.knowledge_links[0].target_id == "b"

        assert len(item_b.knowledge_links) == 1
        assert item_b.knowledge_links[0].target_id == "a"

    def test_updates_existing_link(self, tmp_path):
        """Should update existing link to same target."""
        add_knowledge(content="Source", knowledge_id="source", keywords=["s"], project_path=tmp_path)
        add_knowledge(content="Target", knowledge_id="target", keywords=["t"], project_path=tmp_path)

        # Create initial link
        link_knowledge(
            source_id="source",
            target_id="target",
            relation="related",
            project_path=tmp_path,
        )

        # Update link
        result = link_knowledge(
            source_id="source",
            target_id="target",
            relation="extends",
            note="Updated",
            project_path=tmp_path,
        )

        # Should have only one link, updated
        assert len(result.knowledge_links) == 1
        assert result.knowledge_links[0].relation == "extends"
        assert result.knowledge_links[0].note == "Updated"


class TestGetLinkedKnowledge:
    """Tests for get_linked_knowledge()."""

    def test_returns_linked_items(self, tmp_path):
        """Should return items linked from source."""
        add_knowledge(content="A", knowledge_id="a", keywords=["a"], project_path=tmp_path)
        add_knowledge(content="B", knowledge_id="b", keywords=["b"], project_path=tmp_path)
        add_knowledge(content="C", knowledge_id="c", keywords=["c"], project_path=tmp_path)

        link_knowledge("a", "b", project_path=tmp_path)
        link_knowledge("a", "c", project_path=tmp_path)

        linked = get_linked_knowledge("a", project_path=tmp_path)

        assert len(linked) == 2
        ids = {i.id for i in linked}
        assert "b" in ids
        assert "c" in ids

    def test_returns_empty_for_no_links(self, tmp_path):
        """Should return empty list if no links."""
        add_knowledge(content="A", knowledge_id="a", keywords=["a"], project_path=tmp_path)

        linked = get_linked_knowledge("a", project_path=tmp_path)

        assert linked == []

    def test_returns_empty_for_nonexistent(self, tmp_path):
        """Should return empty list for nonexistent item."""
        linked = get_linked_knowledge("nonexistent", project_path=tmp_path)
        assert linked == []

    def test_follows_multiple_hops(self, tmp_path):
        """Should follow links to specified depth."""
        add_knowledge(content="A", knowledge_id="a", keywords=["a"], project_path=tmp_path)
        add_knowledge(content="B", knowledge_id="b", keywords=["b"], project_path=tmp_path)
        add_knowledge(content="C", knowledge_id="c", keywords=["c"], project_path=tmp_path)

        link_knowledge("a", "b", project_path=tmp_path)
        link_knowledge("b", "c", project_path=tmp_path)

        # Single hop - should only get B
        linked_1 = get_linked_knowledge("a", project_path=tmp_path, max_depth=1)
        assert len(linked_1) == 1
        assert linked_1[0].id == "b"

        # Two hops - should get B and C
        linked_2 = get_linked_knowledge("a", project_path=tmp_path, max_depth=2)
        assert len(linked_2) == 2
        ids = {i.id for i in linked_2}
        assert "b" in ids
        assert "c" in ids

    def test_avoids_cycles(self, tmp_path):
        """Should handle circular links without infinite loop."""
        add_knowledge(content="A", knowledge_id="a", keywords=["a"], project_path=tmp_path)
        add_knowledge(content="B", knowledge_id="b", keywords=["b"], project_path=tmp_path)

        link_knowledge("a", "b", project_path=tmp_path)
        link_knowledge("b", "a", project_path=tmp_path)

        # Should not infinite loop
        linked = get_linked_knowledge("a", project_path=tmp_path, max_depth=10)

        # Should get B but not revisit A
        assert len(linked) == 1
        assert linked[0].id == "b"


class TestIndexSerialization:
    """Tests for knowledge link persistence."""

    def test_links_persist_through_save_load(self, tmp_path):
        """Links should persist through index save/load cycle."""
        add_knowledge(content="Source", knowledge_id="source", keywords=["s"], project_path=tmp_path)
        add_knowledge(content="Target", knowledge_id="target", keywords=["t"], project_path=tmp_path)

        link_knowledge(
            source_id="source",
            target_id="target",
            relation="extends",
            note="Test note",
            project_path=tmp_path,
        )

        # Force reload from disk
        items = load_index(project_path=tmp_path, bypass_cache=True)
        source = next(i for i in items if i.id == "source")

        assert len(source.knowledge_links) == 1
        assert source.knowledge_links[0].target_id == "target"
        assert source.knowledge_links[0].relation == "extends"
        assert source.knowledge_links[0].note == "Test note"

    def test_multiple_links_persist(self, tmp_path):
        """Multiple links should all persist."""
        add_knowledge(content="A", knowledge_id="a", keywords=["a"], project_path=tmp_path)
        add_knowledge(content="B", knowledge_id="b", keywords=["b"], project_path=tmp_path)
        add_knowledge(content="C", knowledge_id="c", keywords=["c"], project_path=tmp_path)

        link_knowledge("a", "b", relation="extends", project_path=tmp_path)
        link_knowledge("a", "c", relation="contradicts", project_path=tmp_path)

        items = load_index(project_path=tmp_path, bypass_cache=True)
        item_a = next(i for i in items if i.id == "a")

        assert len(item_a.knowledge_links) == 2
        targets = {l.target_id for l in item_a.knowledge_links}
        assert targets == {"b", "c"}


class TestRelationTypes:
    """Tests for different relation types."""

    @pytest.mark.parametrize(
        "relation",
        ["related", "supersedes", "contradicts", "extends"],
    )
    def test_valid_relations(self, tmp_path, relation):
        """Should accept valid relation types."""
        add_knowledge(content="S", knowledge_id="source", keywords=["s"], project_path=tmp_path)
        add_knowledge(content="T", knowledge_id="target", keywords=["t"], project_path=tmp_path)

        result = link_knowledge(
            source_id="source",
            target_id="target",
            relation=relation,
            project_path=tmp_path,
        )

        assert result is not None
        assert result.knowledge_links[0].relation == relation

    def test_supersedes_creates_superseded_by_reverse(self, tmp_path):
        """Bidirectional 'supersedes' should create 'superseded_by' reverse."""
        add_knowledge(content="New", knowledge_id="new", keywords=["new"], project_path=tmp_path)
        add_knowledge(content="Old", knowledge_id="old", keywords=["old"], project_path=tmp_path)

        link_knowledge(
            source_id="new",
            target_id="old",
            relation="supersedes",
            bidirectional=True,
            project_path=tmp_path,
        )

        items = load_index(project_path=tmp_path)
        old_item = next(i for i in items if i.id == "old")

        assert len(old_item.knowledge_links) == 1
        assert old_item.knowledge_links[0].relation == "superseded_by"
