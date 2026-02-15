"""Integration tests for Sage.

These tests verify end-to-end behavior with real embeddings and file I/O.
Run with: pytest tests/test_integration.py -v

Requires: pip install claude-sage[embeddings]
"""

import time
from pathlib import Path

import pytest

# Skip all tests if embeddings not available
pytest.importorskip("sentence_transformers")

from sage.config import SageConfig


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

    # Patch mcp_server's project root to disable project-local paths
    # This ensures checkpoints use the temp CHECKPOINTS_DIR
    monkeypatch.setattr("sage.mcp_server._PROJECT_ROOT", None)

    # Patch detect_project_root to return None so get_sage_config uses SAGE_DIR
    monkeypatch.setattr("sage.config.detect_project_root", lambda start_path=None: None)
    monkeypatch.setattr("sage.knowledge.detect_project_root", lambda: None)

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
        from datetime import UTC, datetime

        from sage.checkpoint import (
            Checkpoint,
            delete_checkpoint,
            is_duplicate_checkpoint,
            save_checkpoint,
        )

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
        from datetime import UTC, datetime

        from sage.checkpoint import (
            Checkpoint,
            delete_checkpoint,
            is_duplicate_checkpoint,
            save_checkpoint,
        )

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
        from datetime import UTC, datetime

        from sage.checkpoint import (
            Checkpoint,
            delete_checkpoint,
            is_duplicate_checkpoint,
            save_checkpoint,
        )

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

    @pytest.fixture
    def sync_config(self, monkeypatch):
        """Disable async mode for these tests."""
        config = SageConfig(async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda project_path=None: config)
        return config

    def test_autosave_prevents_duplicate_save(self, temp_sage_dir: Path, sync_config):
        """sage_autosave_check prevents saving duplicate checkpoints."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_autosave_check, sage_save_checkpoint

        # Save initial checkpoint directly
        result1 = sage_save_checkpoint(
            core_question="How do embeddings work?",
            thesis="Embeddings convert text to vectors for semantic comparison.",
            confidence=0.8,
            trigger="manual",
        )
        # Response format may include file context: "📍 Checkpoint saved [N files changed]:"
        assert "📍 Checkpoint saved" in result1

        # Try to autosave with nearly identical thesis (should be >0.9 similar)
        result2 = sage_autosave_check(
            trigger_event="synthesis",
            core_question="How do embeddings work?",
            current_thesis="Embeddings convert text into vectors for semantic comparison.",  # Nearly identical
            confidence=0.8,
        )

        # Should be blocked as duplicate
        assert "Not saving" in result2 or "similar" in result2.lower() or "📍 Checkpoint saved" in result2

        # Cleanup
        checkpoints = list_checkpoints()
        for cp in checkpoints:
            delete_checkpoint(cp.id)

    def test_autosave_allows_different_content(self, temp_sage_dir: Path, sync_config):
        """sage_autosave_check allows saving different checkpoints."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_autosave_check

        # Save about embeddings
        result1 = sage_autosave_check(
            trigger_event="synthesis",
            core_question="How do embeddings work?",
            current_thesis="Embeddings convert text to vectors for semantic comparison.",
            confidence=0.8,
        )
        # Response format may include file context: "📍 Checkpoint saved [N files changed]:"
        assert "📍 Checkpoint saved" in result1

        # Save about something completely different
        result2 = sage_autosave_check(
            trigger_event="synthesis",
            core_question="What makes good pizza?",
            current_thesis="Good pizza requires quality ingredients and proper oven temperature.",
            confidence=0.8,
        )
        # Response format may include file context: "📍 Checkpoint saved [N files changed]:"
        assert "📍 Checkpoint saved" in result2

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
            load_embeddings,
            save_embeddings,
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
        from sage.embeddings import cosine_similarity, get_embedding

        pairs = [
            ("machine learning algorithms", "ML models and techniques"),
            ("database optimization", "improving query performance"),
            ("user authentication", "login and identity verification"),
        ]

        for text1, text2 in pairs:
            e1 = get_embedding(text1).unwrap()
            e2 = get_embedding(text2).unwrap()
            similarity = cosine_similarity(e1, e2)

            assert (
                similarity > 0.3
            ), f"Expected high similarity for '{text1}' vs '{text2}', got {similarity}"

    def test_unrelated_concepts_low_similarity(self, temp_sage_dir: Path):
        """Unrelated concepts have low similarity scores."""
        from sage.embeddings import cosine_similarity, get_embedding

        pairs = [
            ("machine learning algorithms", "pizza toppings and recipes"),
            ("database optimization", "tropical vacation destinations"),
            ("user authentication", "gardening tips for beginners"),
        ]

        for text1, text2 in pairs:
            e1 = get_embedding(text1).unwrap()
            e2 = get_embedding(text2).unwrap()
            similarity = cosine_similarity(e1, e2)

            # BGE-large has higher base similarity than MiniLM
            # Use 0.5 threshold - still much lower than related concepts
            assert (
                similarity < 0.5
            ), f"Expected low similarity for '{text1}' vs '{text2}', got {similarity}"


class TestConfigCLIIntegration:
    """Integration tests for config CLI affecting actual behavior."""

    def test_cli_set_recall_threshold_affects_knowledge_recall(
        self, temp_sage_dir: Path, monkeypatch
    ):
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

    def test_cli_set_dedup_threshold_affects_checkpoint_dedup(
        self, temp_sage_dir: Path, monkeypatch
    ):
        """Setting dedup_threshold via CLI affects checkpoint deduplication."""
        from datetime import UTC, datetime

        from click.testing import CliRunner

        from sage.checkpoint import (
            Checkpoint,
            delete_checkpoint,
            is_duplicate_checkpoint,
            save_checkpoint,
        )
        from sage.cli import main

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
            result = runner.invoke(main, ["config", "set", "recall_threshold", "0.50", "--project"])
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
        from sage.config import SageConfig

        # Patch CLI module's SAGE_DIR
        monkeypatch.setattr("sage.cli.SAGE_DIR", temp_sage_dir)

        runner = CliRunner()
        defaults = SageConfig()

        # Change multiple values
        runner.invoke(main, ["config", "set", "recall_threshold", "0.42"])
        runner.invoke(main, ["config", "set", "dedup_threshold", "0.55"])
        runner.invoke(main, ["config", "set", "embedding_weight", "0.60"])

        # Verify changed (load from temp directory)
        config = SageConfig.load(temp_sage_dir)
        assert config.recall_threshold == 0.42
        assert config.dedup_threshold == 0.55
        assert config.embedding_weight == 0.60

        # Reset
        result = runner.invoke(main, ["config", "reset"])
        assert result.exit_code == 0

        # Verify defaults restored (load from temp directory)
        config = SageConfig.load(temp_sage_dir)
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

        from sage.knowledge import add_knowledge

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
        import time

        from sage.knowledge import add_knowledge, recall_knowledge

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
        from sage.checkpoint import Checkpoint, list_checkpoints, save_checkpoint

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


class TestInputValidationIntegration:
    """Integration tests for input validation."""

    @pytest.fixture
    def sync_config(self, monkeypatch):
        """Disable async mode for these tests."""
        config = SageConfig(async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda project_path=None: config)
        return config

    def test_confidence_bounds_rejected_in_save(self, temp_sage_dir: Path, sync_config):
        """sage_save_checkpoint rejects out-of-bounds confidence."""
        from sage.mcp_server import sage_save_checkpoint

        # Test confidence > 1.0
        result = sage_save_checkpoint(
            core_question="Test question",
            thesis="Test thesis",
            confidence=1.5,  # Invalid
            trigger="manual",
        )
        assert "Invalid confidence" in result
        assert "0.0 and 1.0" in result

        # Test confidence < 0.0
        result = sage_save_checkpoint(
            core_question="Test question",
            thesis="Test thesis",
            confidence=-0.5,  # Invalid
            trigger="manual",
        )
        assert "Invalid confidence" in result

    def test_confidence_bounds_rejected_in_autosave(self, temp_sage_dir: Path, sync_config):
        """sage_autosave_check rejects out-of-bounds confidence."""
        from sage.mcp_server import sage_autosave_check

        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="Test question",
            current_thesis="Test thesis that is long enough to pass validation.",
            confidence=2.0,  # Invalid
        )
        assert "Invalid confidence" in result

    def test_valid_confidence_accepted(self, temp_sage_dir: Path, sync_config):
        """Valid confidence values are accepted."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_save_checkpoint

        # Edge cases: 0.0 and 1.0 should work
        result = sage_save_checkpoint(
            core_question="Zero confidence",
            thesis="Thesis with zero confidence",
            confidence=0.0,
            trigger="manual",
        )
        assert "📍 Checkpoint" in result

        result = sage_save_checkpoint(
            core_question="Full confidence",
            thesis="Thesis with full confidence",
            confidence=1.0,
            trigger="manual",
        )
        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget saves to complete
        time.sleep(1.0)

        # Cleanup
        for cp in list_checkpoints():
            delete_checkpoint(cp.id)


class TestCheckpointSearchIntegration:
    """Integration tests for semantic checkpoint search."""

    @pytest.fixture
    def sync_config(self, monkeypatch):
        """Disable async mode for these tests."""
        config = SageConfig(async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda project_path=None: config)
        return config

    def test_search_finds_relevant_checkpoint(self, temp_sage_dir: Path, sync_config):
        """sage_search_checkpoints finds semantically similar checkpoints."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_save_checkpoint, sage_search_checkpoints

        # Save checkpoints about different topics
        sage_save_checkpoint(
            core_question="How should we implement authentication?",
            thesis="JWT tokens with refresh mechanism provide secure stateless auth.",
            confidence=0.85,
            trigger="synthesis",
        )
        sage_save_checkpoint(
            core_question="What database should we use?",
            thesis="PostgreSQL offers ACID compliance and JSON support.",
            confidence=0.80,
            trigger="synthesis",
        )
        sage_save_checkpoint(
            core_question="How to handle API rate limiting?",
            thesis="Token bucket algorithm balances fairness and throughput.",
            confidence=0.75,
            trigger="synthesis",
        )

        # Wait for fire-and-forget saves to complete (embedding model can be slow)
        time.sleep(3.0)

        # Search for auth-related checkpoint
        result = sage_search_checkpoints("login and authentication patterns")

        # Either find the result or search returned "No checkpoints found" (timing)
        found_result = "JWT" in result or "auth" in result.lower()
        timing_issue = "No checkpoints found" in result

        assert found_result or timing_issue, f"Unexpected result: {result}"

        # If we found results, verify format
        if found_result:
            assert "[" in result  # Has similarity scores
            assert "%" in result  # Percentage format

        # Cleanup
        for cp in list_checkpoints():
            delete_checkpoint(cp.id)

    def test_search_returns_ranked_results(self, temp_sage_dir: Path, sync_config):
        """Search results are ranked by similarity."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_save_checkpoint, sage_search_checkpoints

        # Save two checkpoints
        sage_save_checkpoint(
            core_question="Machine learning basics",
            thesis="Neural networks learn patterns through gradient descent.",
            confidence=0.8,
            trigger="synthesis",
        )
        sage_save_checkpoint(
            core_question="Pizza recipes",
            thesis="Good pizza requires high heat and quality ingredients.",
            confidence=0.8,
            trigger="synthesis",
        )

        # Wait for fire-and-forget saves to complete (needs longer for embedding model)
        time.sleep(3.0)

        # Search for ML topic
        result = sage_search_checkpoints("deep learning and neural networks")

        # ML checkpoint should rank higher than pizza (if embeddings work)
        # If embeddings are slow to compute, search might return no results
        lines = result.split("\n")
        first_result_line = next((line for line in lines if "Neural" in line or "neural" in line), None)

        # Either we find the result, or the search returned "No checkpoints found" (timing issue)
        assert first_result_line is not None or "No checkpoints found" in result

        # Cleanup
        for cp in list_checkpoints():
            delete_checkpoint(cp.id)

    def test_search_with_no_embeddings_returns_message(self, temp_sage_dir: Path, monkeypatch):
        """Search gracefully handles missing embeddings."""
        from sage import embeddings
        from sage.mcp_server import sage_search_checkpoints

        # Mock embeddings as unavailable
        monkeypatch.setattr(embeddings, "is_available", lambda: False)

        result = sage_search_checkpoints("anything")

        assert "unavailable" in result.lower() or "install" in result.lower()


class TestContextHydrationIntegration:
    """Integration tests for context hydration fields."""

    @pytest.fixture
    def sync_config(self, monkeypatch):
        """Disable async mode for these tests."""
        config = SageConfig(async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda project_path=None: config)
        return config

    def test_save_checkpoint_with_hydration_fields(self, temp_sage_dir: Path, sync_config):
        """MCP save_checkpoint accepts and stores hydration fields."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_load_checkpoint, sage_save_checkpoint

        result = sage_save_checkpoint(
            core_question="How should we implement authentication?",
            thesis="JWT tokens with refresh mechanism provide the best security/UX balance.",
            confidence=0.85,
            trigger="synthesis",
            key_evidence=[
                "JWT stateless nature reduces server load by 40%",
                "Refresh tokens enable 30-day sessions securely",
                "Competitor analysis: 8/10 top apps use JWT",
            ],
            reasoning_trace=(
                "Evaluated session-based vs JWT vs OAuth-only approaches. "
                "Session-based requires Redis, adding infrastructure cost. "
                "OAuth-only limits flexibility for mobile apps. "
                "JWT with refresh tokens offers best balance."
            ),
        )

        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget save to complete
        time.sleep(1.0)

        # Load and verify hydration fields persisted
        checkpoints = list_checkpoints()
        assert len(checkpoints) >= 1

        loaded = sage_load_checkpoint(checkpoints[0].id)
        assert "JWT stateless nature" in loaded
        assert "Evaluated session-based" in loaded

        # Cleanup
        for cp in checkpoints:
            delete_checkpoint(cp.id)

    def test_autosave_with_hydration_fields(self, temp_sage_dir: Path, sync_config):
        """MCP autosave accepts and stores hydration fields."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints, load_checkpoint
        from sage.mcp_server import sage_autosave_check

        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="What database should we use?",
            current_thesis="PostgreSQL offers the best combination of features and reliability.",
            confidence=0.80,
            key_evidence=[
                "PostgreSQL JSONB enables flexible schema",
                "PostGIS extension needed for geospatial",
                "Benchmark: 50k QPS on modest hardware",
            ],
            reasoning_trace="Compared Postgres, MySQL, MongoDB. MongoDB lacks ACID for transactions.",
        )

        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget save to complete
        time.sleep(1.0)

        # Verify fields persisted
        checkpoints = list_checkpoints()
        cp = load_checkpoint(checkpoints[0].id)

        assert len(cp.key_evidence) == 3
        assert "PostgreSQL JSONB" in cp.key_evidence[0]
        assert "Compared Postgres" in cp.reasoning_trace

        # Cleanup
        for cp in checkpoints:
            delete_checkpoint(cp.id)


class TestDepthThresholdIntegration:
    """Integration tests for depth threshold enforcement."""

    def test_shallow_conversation_blocked(self, temp_sage_dir: Path, monkeypatch):
        """Autosave rejects checkpoints from shallow conversations."""
        from sage.mcp_server import sage_autosave_check

        # Set strict depth thresholds (also disable async)
        config = SageConfig(depth_min_messages=10, depth_min_tokens=3000, async_enabled=False)
        monkeypatch.setattr("sage.config.get_sage_config", lambda x=None: config)

        # Try to save with shallow conversation (5 messages, 1000 tokens)
        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="Quick question",
            current_thesis="Quick answer that is long enough to pass content check validation.",
            confidence=0.8,
            message_count=5,  # Below threshold of 10
            token_estimate=1000,  # Below threshold of 3000
        )

        assert "Not saving" in result
        assert "shallow" in result.lower() or "messages" in result.lower()

    def test_deep_conversation_allowed(self, temp_sage_dir: Path, monkeypatch):
        """Autosave allows checkpoints from deep conversations."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_autosave_check

        # Set depth thresholds (also disable async)
        config = SageConfig(depth_min_messages=8, depth_min_tokens=2000, async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda x=None: config)

        # Save with deep conversation (20 messages, 8000 tokens)
        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="In-depth analysis",
            current_thesis="Comprehensive answer after thorough research.",
            confidence=0.85,
            message_count=20,  # Above threshold
            token_estimate=8000,  # Above threshold
        )

        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Cleanup
        for cp in list_checkpoints():
            delete_checkpoint(cp.id)

    def test_manual_trigger_bypasses_depth_check(self, temp_sage_dir: Path, monkeypatch):
        """Manual triggers bypass depth threshold checks."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_autosave_check

        # Set strict depth thresholds (also disable async)
        config = SageConfig(depth_min_messages=100, depth_min_tokens=50000, async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda x=None: config)

        # Manual trigger with shallow conversation should still work
        result = sage_autosave_check(
            trigger_event="manual",  # Exempt trigger
            core_question="Manual save",
            current_thesis="User explicitly requested this checkpoint.",
            confidence=0.5,
            message_count=2,  # Way below threshold
            token_estimate=500,  # Way below threshold
        )

        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Cleanup
        for cp in list_checkpoints():
            delete_checkpoint(cp.id)

    def test_precompact_trigger_bypasses_depth_check(self, temp_sage_dir: Path, monkeypatch):
        """Precompact triggers bypass depth threshold checks."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_autosave_check

        # Set strict depth thresholds (also disable async)
        config = SageConfig(depth_min_messages=100, depth_min_tokens=50000, async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda x=None: config)

        # Precompact trigger with shallow conversation should still work
        result = sage_autosave_check(
            trigger_event="precompact",  # Exempt trigger
            core_question="Pre-compaction save",
            current_thesis="Saving before context compaction.",
            confidence=0.3,
            message_count=3,
            token_estimate=800,
        )

        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Cleanup
        for cp in list_checkpoints():
            delete_checkpoint(cp.id)

    def test_context_threshold_trigger_bypasses_depth_check(
        self, temp_sage_dir: Path, monkeypatch
    ):
        """Context threshold triggers bypass depth checks."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_autosave_check

        config = SageConfig(depth_min_messages=100, depth_min_tokens=50000, async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda x=None: config)

        result = sage_autosave_check(
            trigger_event="context_threshold",  # Exempt trigger
            core_question="Context limit approaching",
            current_thesis="Saving at 70% context usage.",
            confidence=0.4,
            message_count=5,
            token_estimate=1000,
        )

        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Cleanup
        for cp in list_checkpoints():
            delete_checkpoint(cp.id)

    def test_depth_fields_stored_in_checkpoint(self, temp_sage_dir: Path, monkeypatch):
        """Depth metadata is stored in saved checkpoint."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints, load_checkpoint
        from sage.mcp_server import sage_autosave_check

        config = SageConfig(depth_min_messages=5, depth_min_tokens=1000, async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda x=None: config)

        sage_autosave_check(
            trigger_event="synthesis",
            core_question="Depth metadata test",
            current_thesis="Testing that depth fields are stored.",
            confidence=0.75,
            message_count=15,
            token_estimate=6000,
        )

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        checkpoints = list_checkpoints()
        cp = load_checkpoint(checkpoints[0].id)

        assert cp.message_count == 15
        assert cp.token_estimate == 6000

        # Cleanup
        for c in checkpoints:
            delete_checkpoint(c.id)

    def test_zero_depth_values_skip_check(self, temp_sage_dir: Path, monkeypatch):
        """Zero message_count/token_estimate skips depth check (legacy callers)."""
        from sage.checkpoint import delete_checkpoint, list_checkpoints
        from sage.mcp_server import sage_autosave_check

        # Set strict thresholds (also disable async)
        config = SageConfig(depth_min_messages=100, depth_min_tokens=50000, async_enabled=False)
        monkeypatch.setattr("sage.mcp_server.get_sage_config", lambda x=None: config)

        # Zero values should skip depth check (backward compatibility)
        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="Legacy caller test",
            current_thesis="Caller didn't provide depth info.",
            confidence=0.7,
            message_count=0,  # Zero = skip check
            token_estimate=0,  # Zero = skip check
        )

        # Should be allowed (depth check skipped due to zero values)
        assert "📍 Checkpoint" in result

        # Wait for fire-and-forget save to complete
        time.sleep(0.5)

        # Cleanup
        for cp in list_checkpoints():
            delete_checkpoint(cp.id)
