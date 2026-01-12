"""Integration tests for Sage.

These tests verify end-to-end behavior with real embeddings and file I/O.
Run with: pytest tests/test_integration.py -v

Requires: pip install claude-sage[embeddings]
"""

import shutil
from pathlib import Path

import pytest

# Skip all tests if embeddings not available
pytest.importorskip("sentence_transformers")


@pytest.fixture
def temp_sage_dir(tmp_path: Path, monkeypatch):
    """Create a temporary .sage directory for testing."""
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    (sage_dir / "knowledge").mkdir()
    (sage_dir / "checkpoints").mkdir()
    (sage_dir / "embeddings").mkdir()
    
    # Patch SAGE_DIR to use temp directory
    monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)
    monkeypatch.setattr("sage.knowledge.SAGE_DIR", sage_dir)
    monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", sage_dir / "knowledge")
    monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", sage_dir / "knowledge" / "index.yaml")
    monkeypatch.setattr("sage.checkpoint.SAGE_DIR", sage_dir)
    monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", sage_dir / "checkpoints")
    monkeypatch.setattr("sage.embeddings.SAGE_DIR", sage_dir)
    monkeypatch.setattr("sage.embeddings.EMBEDDINGS_DIR", sage_dir / "embeddings")
    
    return sage_dir


class TestKnowledgeRecallIntegration:
    """Integration tests for knowledge recall with embeddings."""
    
    def test_semantic_recall_without_keyword_match(self, temp_sage_dir: Path):
        """Knowledge is recalled based on semantic similarity, not just keywords."""
        from sage.knowledge import add_knowledge, recall_knowledge
        
        # Add knowledge about GDPR
        add_knowledge(
            content="GDPR requires explicit consent for processing personal data. Key articles: 6, 7, 13.",
            knowledge_id="gdpr-consent",
            keywords=["gdpr", "consent"],
            source="test",
        )
        
        # Query with semantically similar but different words
        result = recall_knowledge(
            query="What privacy regulations apply in Europe?",
            skill_name="test",
            use_embeddings=True,
        )
        
        # Should recall GDPR knowledge despite no keyword match
        assert result.count >= 1
        assert any("gdpr" in item.id.lower() for item in result.items)
    
    def test_unrelated_query_not_recalled(self, temp_sage_dir: Path):
        """Unrelated queries don't recall knowledge."""
        from sage.knowledge import add_knowledge, recall_knowledge
        
        add_knowledge(
            content="GDPR requires explicit consent for processing personal data.",
            knowledge_id="gdpr-consent",
            keywords=["gdpr", "consent"],
            source="test",
        )
        
        # Query about something completely different
        result = recall_knowledge(
            query="What are the best pizza toppings?",
            skill_name="test",
            threshold=3.0,  # Higher threshold
            use_embeddings=True,
        )
        
        # Should not recall GDPR for pizza query
        assert result.count == 0
    
    def test_combined_scoring_boosts_keyword_matches(self, temp_sage_dir: Path):
        """Items with both semantic and keyword matches score higher."""
        from sage.knowledge import add_knowledge, recall_knowledge
        
        # Add two knowledge items
        add_knowledge(
            content="GDPR requires explicit consent for processing personal data.",
            knowledge_id="gdpr-direct",
            keywords=["gdpr", "consent", "privacy"],  # Has keyword match
            source="test",
        )
        add_knowledge(
            content="Data protection laws vary by country and region.",
            knowledge_id="data-protection",
            keywords=["data", "protection"],  # No direct keyword match for "privacy"
            source="test",
        )
        
        # Query with "privacy" keyword
        result = recall_knowledge(
            query="What are the privacy requirements?",
            skill_name="test",
            use_embeddings=True,
        )
        
        # GDPR should rank higher due to keyword boost
        if result.count >= 2:
            assert result.items[0].id == "gdpr-direct"


class TestCheckpointDeduplicationIntegration:
    """Integration tests for checkpoint deduplication."""
    
    def test_duplicate_thesis_detected(self, temp_sage_dir: Path):
        """Semantically similar theses are detected as duplicates."""
        from sage.checkpoint import (
            Checkpoint,
            is_duplicate_checkpoint,
            save_checkpoint,
            delete_checkpoint,
        )
        from datetime import datetime, UTC
        
        # Save a checkpoint
        cp = Checkpoint(
            id="test-dedup-original",
            ts=datetime.now(UTC).isoformat(),
            trigger="manual",
            core_question="How should AI systems handle memory?",
            thesis="AI systems need semantic checkpointing to preserve context across sessions.",
            confidence=0.8,
        )
        save_checkpoint(cp)
        
        # Check similar thesis
        similar_thesis = "AI needs semantic checkpoints to maintain context between sessions."
        result = is_duplicate_checkpoint(similar_thesis, threshold=0.8)
        
        assert result.is_duplicate is True
        assert result.similarity_score > 0.8
        assert result.similar_checkpoint_id == "test-dedup-original"
        
        # Cleanup
        delete_checkpoint("test-dedup-original")
    
    def test_different_thesis_not_duplicate(self, temp_sage_dir: Path):
        """Different theses are not detected as duplicates."""
        from sage.checkpoint import (
            Checkpoint,
            is_duplicate_checkpoint,
            save_checkpoint,
            delete_checkpoint,
        )
        from datetime import datetime, UTC
        
        # Save a checkpoint about AI
        cp = Checkpoint(
            id="test-dedup-ai",
            ts=datetime.now(UTC).isoformat(),
            trigger="manual",
            core_question="How should AI systems handle memory?",
            thesis="AI systems need semantic checkpointing to preserve context.",
            confidence=0.8,
        )
        save_checkpoint(cp)
        
        # Check completely different thesis
        different_thesis = "Pizza toppings should include pineapple for optimal flavor."
        result = is_duplicate_checkpoint(different_thesis, threshold=0.8)
        
        assert result.is_duplicate is False
        
        # Cleanup
        delete_checkpoint("test-dedup-ai")
    
    def test_dedup_threshold_respected(self, temp_sage_dir: Path):
        """Deduplication respects the threshold parameter."""
        from sage.checkpoint import (
            Checkpoint,
            is_duplicate_checkpoint,
            save_checkpoint,
            delete_checkpoint,
        )
        from datetime import datetime, UTC
        
        # Save a checkpoint
        cp = Checkpoint(
            id="test-threshold",
            ts=datetime.now(UTC).isoformat(),
            trigger="manual",
            core_question="Test question",
            thesis="AI systems benefit from persistent memory mechanisms.",
            confidence=0.8,
        )
        save_checkpoint(cp)
        
        # Similar but not identical thesis
        similar = "Machine learning models can use memory for context."
        
        # With low threshold, should be duplicate
        result_low = is_duplicate_checkpoint(similar, threshold=0.3)
        
        # With high threshold, should not be duplicate  
        result_high = is_duplicate_checkpoint(similar, threshold=0.95)
        
        # Low threshold flags as duplicate, high threshold doesn't
        assert result_low.is_duplicate is True
        assert result_high.is_duplicate is False
        # When flagged, similarity is reported; when not, it's 0
        assert result_low.similarity_score > 0.3
        
        # Cleanup
        delete_checkpoint("test-threshold")


class TestMCPAutosaveIntegration:
    """Integration tests for MCP autosave with deduplication."""
    
    def test_autosave_prevents_duplicate_save(self, temp_sage_dir: Path):
        """sage_autosave_check prevents saving duplicate checkpoints."""
        from sage.mcp_server import sage_autosave_check, sage_save_checkpoint
        from sage.checkpoint import list_checkpoints, delete_checkpoint
        
        # Save initial checkpoint directly
        result1 = sage_save_checkpoint(
            core_question="How do embeddings work?",
            thesis="Embeddings convert text to vectors for semantic comparison.",
            confidence=0.8,
            trigger="manual",
        )
        assert "Checkpoint saved" in result1
        
        # Try to autosave with nearly identical thesis (should be >0.9 similar)
        result2 = sage_autosave_check(
            trigger_event="synthesis",
            core_question="How do embeddings work?",
            current_thesis="Embeddings convert text into vectors for semantic comparison.",  # Nearly identical
            confidence=0.8,
        )
        
        # Should be blocked as duplicate
        assert "Not saving" in result2 or "similar" in result2.lower()
        
        # Cleanup
        checkpoints = list_checkpoints()
        for cp in checkpoints:
            delete_checkpoint(cp.id)
    
    def test_autosave_allows_different_content(self, temp_sage_dir: Path):
        """sage_autosave_check allows saving different checkpoints."""
        from sage.mcp_server import sage_autosave_check
        from sage.checkpoint import list_checkpoints, delete_checkpoint
        
        # Save about embeddings
        result1 = sage_autosave_check(
            trigger_event="synthesis",
            core_question="How do embeddings work?",
            current_thesis="Embeddings convert text to vectors for semantic comparison.",
            confidence=0.8,
        )
        assert "Autosaved" in result1
        
        # Save about something completely different
        result2 = sage_autosave_check(
            trigger_event="synthesis",
            core_question="What makes good pizza?",
            current_thesis="Good pizza requires quality ingredients and proper oven temperature.",
            confidence=0.8,
        )
        assert "Autosaved" in result2
        
        # Should have 2 checkpoints
        checkpoints = list_checkpoints()
        assert len(checkpoints) >= 2
        
        # Cleanup
        for cp in checkpoints:
            delete_checkpoint(cp.id)


class TestEmbeddingStoreIntegration:
    """Integration tests for embedding storage persistence."""
    
    def test_embeddings_persist_across_loads(self, temp_sage_dir: Path):
        """Embeddings are saved and loaded correctly."""
        from sage.embeddings import (
            EmbeddingStore,
            get_embedding,
            save_embeddings,
            load_embeddings,
        )
        
        path = temp_sage_dir / "embeddings" / "test.npy"
        
        # Create and save embeddings
        text1 = "Machine learning is fascinating"
        text2 = "Deep learning uses neural networks"
        
        e1 = get_embedding(text1).unwrap()
        e2 = get_embedding(text2).unwrap()
        
        store = EmbeddingStore.empty()
        store = store.add("item1", e1)
        store = store.add("item2", e2)
        
        save_embeddings(path, store)
        
        # Load and verify
        loaded = load_embeddings(path).unwrap()
        
        assert len(loaded) == 2
        assert "item1" in loaded.ids
        assert "item2" in loaded.ids
        
        # Verify embeddings are correct (high self-similarity)
        from sage.embeddings import cosine_similarity
        assert cosine_similarity(loaded.get("item1"), e1) > 0.99
        assert cosine_similarity(loaded.get("item2"), e2) > 0.99
    
    def test_knowledge_embeddings_persist(self, temp_sage_dir: Path):
        """Knowledge item embeddings persist across sessions."""
        from sage.knowledge import add_knowledge, recall_knowledge, remove_knowledge
        
        # Add knowledge (generates embedding)
        add_knowledge(
            content="Python is a programming language known for readability.",
            knowledge_id="python-lang",
            keywords=["python"],
            source="test",
        )
        
        # Verify embedding file exists
        embedding_path = temp_sage_dir / "embeddings" / "knowledge.npy"
        ids_path = temp_sage_dir / "embeddings" / "knowledge.json"
        assert embedding_path.exists()
        assert ids_path.exists()
        
        # Recall should work using embeddings
        result = recall_knowledge(
            query="What programming languages are easy to read?",
            skill_name="test",
            use_embeddings=True,
        )
        
        assert result.count >= 1
        
        # Cleanup
        remove_knowledge("python-lang")


class TestSemanticSimilarityAccuracy:
    """Tests for semantic similarity accuracy."""
    
    def test_similar_concepts_high_similarity(self, temp_sage_dir: Path):
        """Semantically similar concepts have high similarity scores."""
        from sage.embeddings import get_embedding, cosine_similarity
        
        pairs = [
            ("machine learning algorithms", "ML models and techniques"),
            ("database optimization", "improving query performance"),
            ("user authentication", "login and identity verification"),
        ]
        
        for text1, text2 in pairs:
            e1 = get_embedding(text1).unwrap()
            e2 = get_embedding(text2).unwrap()
            similarity = cosine_similarity(e1, e2)
            
            assert similarity > 0.3, f"Expected high similarity for '{text1}' vs '{text2}', got {similarity}"
    
    def test_unrelated_concepts_low_similarity(self, temp_sage_dir: Path):
        """Unrelated concepts have low similarity scores."""
        from sage.embeddings import get_embedding, cosine_similarity
        
        pairs = [
            ("machine learning algorithms", "pizza toppings and recipes"),
            ("database optimization", "tropical vacation destinations"),
            ("user authentication", "gardening tips for beginners"),
        ]
        
        for text1, text2 in pairs:
            e1 = get_embedding(text1).unwrap()
            e2 = get_embedding(text2).unwrap()
            similarity = cosine_similarity(e1, e2)
            
            assert similarity < 0.3, f"Expected low similarity for '{text1}' vs '{text2}', got {similarity}"
