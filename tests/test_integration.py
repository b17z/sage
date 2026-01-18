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
            threshold=2.0,  # Lower threshold for semantic matching
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
            threshold=2.0,  # Lower threshold for semantic matching
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


class TestConfigCLIIntegration:
    """Integration tests for config CLI affecting actual behavior."""

    def test_cli_set_recall_threshold_affects_knowledge_recall(self, temp_sage_dir: Path, monkeypatch):
        """Setting recall_threshold via CLI affects knowledge recall behavior."""
        from click.testing import CliRunner
        from sage.cli import main
        from sage.knowledge import add_knowledge, recall_knowledge

        # Patch CLI module's SAGE_DIR too
        monkeypatch.setattr("sage.cli.SAGE_DIR", temp_sage_dir)

        runner = CliRunner()

        # Add knowledge item
        add_knowledge(
            content="Stablecoins maintain a stable value pegged to fiat currency.",
            knowledge_id="stablecoin-basics",
            keywords=["stablecoin", "crypto"],
            source="test",
        )

        # Set very high threshold via CLI (should filter out most matches)
        result = runner.invoke(main, ["config", "set", "recall_threshold", "0.99"])
        assert result.exit_code == 0

        # Query - should get no results with 0.99 threshold
        recall_result = recall_knowledge(
            query="What is cryptocurrency?",
            skill_name="test",
            use_embeddings=True,
            threshold=None,  # Use config threshold
        )
        high_threshold_count = recall_result.count

        # Now set low threshold
        result = runner.invoke(main, ["config", "set", "recall_threshold", "0.30"])
        assert result.exit_code == 0

        # Query again - should get results with lower threshold
        recall_result = recall_knowledge(
            query="What is cryptocurrency?",
            skill_name="test",
            use_embeddings=True,
            threshold=None,  # Use config threshold
        )
        low_threshold_count = recall_result.count

        # Lower threshold should return more (or equal) results
        assert low_threshold_count >= high_threshold_count

    def test_cli_set_dedup_threshold_affects_checkpoint_dedup(self, temp_sage_dir: Path, monkeypatch):
        """Setting dedup_threshold via CLI affects checkpoint deduplication."""
        from click.testing import CliRunner
        from sage.cli import main
        from sage.checkpoint import (
            Checkpoint,
            save_checkpoint,
            is_duplicate_checkpoint,
            delete_checkpoint,
        )
        from datetime import datetime, UTC

        # Patch CLI module's SAGE_DIR
        monkeypatch.setattr("sage.cli.SAGE_DIR", temp_sage_dir)

        runner = CliRunner()

        # Save a checkpoint
        cp = Checkpoint(
            id="config-test-cp",
            ts=datetime.now(UTC).isoformat(),
            trigger="manual",
            core_question="Config test",
            thesis="AI systems need semantic checkpointing for context preservation.",
            confidence=0.8,
        )
        save_checkpoint(cp)

        # Similar thesis
        similar = "AI systems require semantic checkpoints to preserve context."

        # Set high dedup threshold (0.99) - similar should NOT be flagged as duplicate
        result = runner.invoke(main, ["config", "set", "dedup_threshold", "0.99"])
        assert result.exit_code == 0

        dedup_result = is_duplicate_checkpoint(similar, threshold=None)
        is_dup_high_threshold = dedup_result.is_duplicate

        # Set low dedup threshold (0.3) - similar SHOULD be flagged as duplicate
        result = runner.invoke(main, ["config", "set", "dedup_threshold", "0.30"])
        assert result.exit_code == 0

        dedup_result = is_duplicate_checkpoint(similar, threshold=None)
        is_dup_low_threshold = dedup_result.is_duplicate

        # Low threshold should flag as duplicate, high should not
        assert is_dup_low_threshold is True
        assert is_dup_high_threshold is False

        # Cleanup
        delete_checkpoint("config-test-cp")

    def test_cli_project_config_creates_local_file(self, tmp_path: Path):
        """Project-level config set via CLI creates .sage/tuning.yaml in cwd."""
        from click.testing import CliRunner
        from sage.cli import main

        runner = CliRunner()

        # Use isolated filesystem to simulate project directory
        with runner.isolated_filesystem(temp_dir=tmp_path) as project_dir:
            # Set project-level config
            result = runner.invoke(
                main, ["config", "set", "recall_threshold", "0.50", "--project"]
            )
            assert result.exit_code == 0
            assert "project-level" in result.output

            # Verify project config file exists
            from pathlib import Path
            import yaml

            project_tuning = Path(project_dir) / ".sage" / "tuning.yaml"
            assert project_tuning.exists()

            content = yaml.safe_load(project_tuning.read_text())
            assert content["recall_threshold"] == 0.50

    def test_cli_config_reset_restores_behavior(self, temp_sage_dir: Path, monkeypatch):
        """Resetting config via CLI restores default behavior."""
        from click.testing import CliRunner
        from sage.cli import main
        from sage.config import get_sage_config, SageConfig

        # Patch CLI module's SAGE_DIR
        monkeypatch.setattr("sage.cli.SAGE_DIR", temp_sage_dir)

        runner = CliRunner()
        defaults = SageConfig()

        # Change multiple values
        runner.invoke(main, ["config", "set", "recall_threshold", "0.42"])
        runner.invoke(main, ["config", "set", "dedup_threshold", "0.55"])
        runner.invoke(main, ["config", "set", "embedding_weight", "0.60"])

        # Verify changed
        config = get_sage_config()
        assert config.recall_threshold == 0.42
        assert config.dedup_threshold == 0.55
        assert config.embedding_weight == 0.60

        # Reset
        result = runner.invoke(main, ["config", "reset"])
        assert result.exit_code == 0

        # Verify defaults restored
        config = get_sage_config()
        assert config.recall_threshold == defaults.recall_threshold
        assert config.dedup_threshold == defaults.dedup_threshold
        assert config.embedding_weight == defaults.embedding_weight


class TestSecurityIntegration:
    """Integration tests for security features with real file I/O."""

    def test_config_file_not_world_readable(self, temp_sage_dir: Path, monkeypatch):
        """Config file with API key is created with restricted permissions."""
        import stat
        from sage.config import Config

        # Patch CONFIG_PATH to use temp dir
        config_path = temp_sage_dir / "config.yaml"
        monkeypatch.setattr("sage.config.CONFIG_PATH", config_path)

        # Create config with API key
        config = Config(api_key="sk-test-key-12345")
        config.save()

        # Verify permissions
        mode = config_path.stat().st_mode
        assert mode & stat.S_IRWXG == 0, "Group should have no access"
        assert mode & stat.S_IRWXO == 0, "Others should have no access"

    def test_history_file_not_world_readable(self, temp_sage_dir: Path, monkeypatch):
        """History files are created with restricted permissions."""
        import stat
        from sage.history import append_entry, create_entry

        # Create skill directory
        skill_dir = temp_sage_dir / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        history_path = skill_dir / "history.jsonl"

        monkeypatch.setattr("sage.history.get_history_path", lambda x: history_path)

        entry = create_entry(
            entry_type="ask",
            query="test query",
            model="test-model",
            tokens_in=100,
            tokens_out=200,
        )
        append_entry("test-skill", entry)

        mode = history_path.stat().st_mode
        assert mode & stat.S_IRWXG == 0, "Group should have no access"
        assert mode & stat.S_IRWXO == 0, "Others should have no access"

    def test_checkpoint_with_sensitive_content_protected(self, temp_sage_dir: Path):
        """Checkpoints containing research are permission-protected."""
        import stat
        from sage.checkpoint import Checkpoint, save_checkpoint

        cp = Checkpoint(
            id="sensitive-research",
            ts="2026-01-18T12:00:00Z",
            trigger="manual",
            core_question="Confidential project analysis",
            thesis="Internal findings about competitive landscape.",
            confidence=0.9,
        )
        file_path = save_checkpoint(cp)

        mode = file_path.stat().st_mode
        assert mode & stat.S_IRWXG == 0, "Group should have no access"
        assert mode & stat.S_IRWXO == 0, "Others should have no access"

    def test_knowledge_end_to_end_with_permissions(self, temp_sage_dir: Path):
        """Full knowledge workflow maintains permissions throughout."""
        import stat
        from sage.knowledge import add_knowledge, KNOWLEDGE_DIR

        # Ensure global dir exists
        (temp_sage_dir / "knowledge" / "global").mkdir(parents=True, exist_ok=True)

        # Add sensitive knowledge
        item = add_knowledge(
            content="Internal API documentation with auth patterns.",
            knowledge_id="internal-api",
            keywords=["api", "auth", "internal"],
            source="internal-docs",
        )

        # Verify content file permissions
        content_path = temp_sage_dir / "knowledge" / item.file
        mode = content_path.stat().st_mode
        assert mode & stat.S_IRWXG == 0, "Content: Group should have no access"
        assert mode & stat.S_IRWXO == 0, "Content: Others should have no access"

        # Verify index permissions
        index_path = temp_sage_dir / "knowledge" / "index.yaml"
        mode = index_path.stat().st_mode
        assert mode & stat.S_IRWXG == 0, "Index: Group should have no access"
        assert mode & stat.S_IRWXO == 0, "Index: Others should have no access"

    def test_redos_pattern_blocked_in_recall(self, temp_sage_dir: Path):
        """ReDoS patterns are filtered during add, not executed during recall."""
        from sage.knowledge import add_knowledge, recall_knowledge
        import time

        # Ensure global dir exists
        (temp_sage_dir / "knowledge" / "global").mkdir(parents=True, exist_ok=True)

        # Add knowledge with dangerous pattern (should be filtered)
        item = add_knowledge(
            content="Test content",
            knowledge_id="redos-test",
            keywords=["test"],
            patterns=["(a+)+$"],  # Dangerous ReDoS pattern
        )

        # Pattern should have been filtered out
        assert "(a+)+$" not in item.triggers.patterns

        # Recall should complete quickly (no ReDoS hang)
        start = time.time()
        recall_knowledge(
            query="a" * 50,  # Input that would trigger ReDoS
            skill_name="test",
            threshold=0.0,
        )
        elapsed = time.time() - start

        # Should complete in < 1 second (ReDoS would hang for minutes)
        assert elapsed < 1.0, f"Recall took {elapsed}s - possible ReDoS"

    def test_malformed_checkpoint_doesnt_crash_list(self, temp_sage_dir: Path):
        """Malformed checkpoint files don't crash list_checkpoints."""
        from sage.checkpoint import Checkpoint, save_checkpoint, list_checkpoints

        checkpoints_dir = temp_sage_dir / "checkpoints"

        # Create valid checkpoint
        valid_cp = Checkpoint(
            id="valid-cp",
            ts="2026-01-18T12:00:00Z",
            trigger="manual",
            core_question="Valid?",
            thesis="Yes, valid.",
            confidence=0.8,
        )
        save_checkpoint(valid_cp)

        # Create malformed files (attack scenarios)
        (checkpoints_dir / "malformed1.yaml").write_text("not: valid: yaml: {{{")
        (checkpoints_dir / "malformed2.yaml").write_text("checkpoint: 'missing fields'")

        # list_checkpoints should not crash (key security requirement)
        checkpoints = list_checkpoints()

        # Valid checkpoint should be in results
        valid_ids = [cp.id for cp in checkpoints if cp.id]
        assert "valid-cp" in valid_ids, "Valid checkpoint should be found"
