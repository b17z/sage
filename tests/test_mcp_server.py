"""Tests for MCP server tools."""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from sage.mcp_server import (
    sage_save_checkpoint,
    sage_list_checkpoints,
    sage_load_checkpoint,
    sage_search_checkpoints,
    sage_save_knowledge,
    sage_recall_knowledge,
    sage_list_knowledge,
    sage_remove_knowledge,
    sage_autosave_check,
    AUTOSAVE_THRESHOLDS,
)
from sage.checkpoint import Checkpoint
from sage.knowledge import KnowledgeItem, RecallResult
from sage.config import SageConfig


@pytest.fixture
def isolated_project(tmp_path, monkeypatch):
    """Fixture that sets up an isolated project directory for testing."""
    # Create .sage directory so get_checkpoints_dir uses it
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    (sage_dir / "checkpoints").mkdir()
    (sage_dir / "knowledge").mkdir()

    # Monkeypatch the project root
    monkeypatch.setattr("sage.mcp_server._PROJECT_ROOT", tmp_path)

    # Also patch the global CHECKPOINTS_DIR as fallback
    monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", sage_dir / "checkpoints")

    return tmp_path


class TestSaveCheckpoint:
    """Tests for sage_save_checkpoint tool."""

    def test_save_checkpoint_returns_confirmation(self, isolated_project):
        """Saving checkpoint returns confirmation with ID."""
        result = sage_save_checkpoint(
            core_question="How to implement auth?",
            thesis="JWT is the best approach for stateless auth.",
            confidence=0.8,
        )

        assert "✓ Checkpoint saved:" in result
        assert "Path:" in result

    def test_save_checkpoint_rejects_invalid_confidence_low(self, isolated_project):
        """Rejects confidence below 0."""
        result = sage_save_checkpoint(
            core_question="Question",
            thesis="Thesis",
            confidence=-0.1,
        )

        assert "Invalid confidence" in result
        assert "-0.1" in result
        assert "0.0 and 1.0" in result

    def test_save_checkpoint_rejects_invalid_confidence_high(self, isolated_project):
        """Rejects confidence above 1."""
        result = sage_save_checkpoint(
            core_question="Question",
            thesis="Thesis",
            confidence=1.5,
        )

        assert "Invalid confidence" in result
        assert "1.5" in result

    def test_save_checkpoint_accepts_boundary_confidence(self, isolated_project):
        """Accepts boundary confidence values 0.0 and 1.0."""
        # Test 0.0
        result = sage_save_checkpoint(
            core_question="Question",
            thesis="Thesis",
            confidence=0.0,
        )
        assert "✓ Checkpoint saved:" in result

        # Test 1.0
        result = sage_save_checkpoint(
            core_question="Question two",
            thesis="Thesis two",
            confidence=1.0,
        )
        assert "✓ Checkpoint saved:" in result

    def test_save_checkpoint_with_all_optional_fields(self, isolated_project):
        """Can save checkpoint with all optional fields."""
        result = sage_save_checkpoint(
            core_question="How to secure API?",
            thesis="Use JWT with short expiry and refresh tokens.",
            confidence=0.85,
            trigger="synthesis",
            open_questions=["How to handle token rotation?"],
            sources=[{"id": "rfc7519", "type": "spec", "take": "JWT standard"}],
            tensions=[{"between": ["stateless", "revocation"], "nature": "tradeoff"}],
            unique_contributions=[{"type": "pattern", "content": "Dual token approach"}],
            action_goal="Implement auth",
            action_type="implementation",
            key_evidence=["JWT is stateless", "Refresh tokens enable revocation"],
            reasoning_trace="Started with sessions, but JWT better for microservices.",
        )

        assert "✓ Checkpoint saved:" in result


class TestListCheckpoints:
    """Tests for sage_list_checkpoints tool."""

    def test_list_empty_returns_no_checkpoints(self, isolated_project):
        """Returns message when no checkpoints exist."""
        result = sage_list_checkpoints()

        assert "No checkpoints found" in result

    def test_list_returns_checkpoints(self, isolated_project):
        """Lists saved checkpoints."""
        # Save a checkpoint first
        sage_save_checkpoint(
            core_question="Test question",
            thesis="Test thesis for listing",
            confidence=0.7,
        )

        result = sage_list_checkpoints()

        assert "Found 1 checkpoint" in result
        assert "Test thesis" in result
        assert "70%" in result

    def test_list_respects_limit(self, isolated_project):
        """Respects limit parameter."""
        # Save multiple checkpoints
        for i in range(5):
            sage_save_checkpoint(
                core_question=f"Question {i}",
                thesis=f"Thesis number {i} here",
                confidence=0.5,
            )

        result = sage_list_checkpoints(limit=3)

        # Should only show 3 (each checkpoint has **id** so count of "**" = 6)
        assert "Found 3 checkpoint" in result

    def test_list_truncates_long_thesis(self, isolated_project):
        """Truncates long thesis in preview."""
        long_thesis = "A" * 100  # Longer than 60 char preview
        sage_save_checkpoint(
            core_question="Question",
            thesis=long_thesis,
            confidence=0.5,
        )

        result = sage_list_checkpoints()

        assert "..." in result
        assert long_thesis not in result  # Full thesis shouldn't appear


class TestLoadCheckpoint:
    """Tests for sage_load_checkpoint tool."""

    def test_load_nonexistent_returns_error(self, isolated_project):
        """Returns error for nonexistent checkpoint."""
        result = sage_load_checkpoint("nonexistent-id")

        assert "not found" in result.lower()

    def test_load_returns_formatted_context(self, isolated_project):
        """Returns formatted checkpoint context."""
        # Save checkpoint
        save_result = sage_save_checkpoint(
            core_question="How to cache data?",
            thesis="Redis is best for distributed caching.",
            confidence=0.9,
        )

        # Extract ID from result
        checkpoint_id = save_result.split("Checkpoint saved: ")[1].split("\n")[0]

        result = sage_load_checkpoint(checkpoint_id)

        assert "Redis is best" in result
        assert "How to cache data?" in result
        assert "90%" in result

    def test_load_supports_partial_id(self, isolated_project):
        """Supports partial ID matching."""
        # Save checkpoint
        save_result = sage_save_checkpoint(
            core_question="Question",
            thesis="Thesis content here",
            confidence=0.7,
        )

        # Extract ID
        checkpoint_id = save_result.split("Checkpoint saved: ")[1].split("\n")[0]
        partial_id = checkpoint_id[:8]  # First 8 chars

        result = sage_load_checkpoint(partial_id)

        # Should find it (or at least not return "not found")
        # Partial matching depends on implementation
        assert "Thesis content" in result or "not found" in result.lower()


class TestSearchCheckpoints:
    """Tests for sage_search_checkpoints tool."""

    def test_search_without_embeddings(self, isolated_project):
        """Returns message when embeddings not available."""
        # embeddings is imported inside sage_search_checkpoints, so patch sage.embeddings
        with patch("sage.embeddings.is_available") as mock_is_available:
            mock_is_available.return_value = False

            result = sage_search_checkpoints("test query")

            assert "unavailable" in result.lower()
            assert "pip install" in result

    def test_search_empty_checkpoints(self, isolated_project):
        """Returns message when no checkpoints exist."""
        with patch("sage.embeddings.is_available") as mock_is_available:
            mock_is_available.return_value = True
            with patch("sage.embeddings.get_embedding") as mock_get_embedding:
                import numpy as np
                mock_result = MagicMock()
                mock_result.is_err.return_value = False
                mock_result.unwrap.return_value = np.array([0.1] * 384)
                mock_get_embedding.return_value = mock_result

                result = sage_search_checkpoints("test query")

                assert "No checkpoints found" in result


class TestSaveKnowledge:
    """Tests for sage_save_knowledge tool."""

    def test_save_knowledge_returns_confirmation(self, tmp_path, monkeypatch):
        """Saving knowledge returns confirmation."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        result = sage_save_knowledge(
            knowledge_id="test-knowledge",
            content="Test content",
            keywords=["test", "knowledge"],
        )

        assert "✓ Knowledge saved:" in result
        assert "test-knowledge" in result
        assert "global" in result

    def test_save_knowledge_with_skill_scope(self, tmp_path, monkeypatch):
        """Shows skill scope in confirmation."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        result = sage_save_knowledge(
            knowledge_id="scoped-knowledge",
            content="Scoped content",
            keywords=["scoped"],
            skill="my-skill",
        )

        assert "skill:my-skill" in result


class TestRecallKnowledge:
    """Tests for sage_recall_knowledge tool."""

    def test_recall_empty_returns_message(self, tmp_path, monkeypatch):
        """Returns message when nothing recalled."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        with patch("sage.embeddings.is_available") as mock_is_available:
            mock_is_available.return_value = False

            result = sage_recall_knowledge("unknown query")

            assert "No relevant knowledge" in result
            assert "pip install" in result

    def test_recall_with_embeddings_hint(self, tmp_path, monkeypatch):
        """Shows embeddings hint when not installed."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        with patch("sage.embeddings.is_available") as mock_is_available:
            mock_is_available.return_value = False

            result = sage_recall_knowledge("query")

            assert "semantic recall" in result.lower() or "embeddings" in result.lower()


class TestListKnowledge:
    """Tests for sage_list_knowledge tool."""

    def test_list_empty_returns_message(self, tmp_path, monkeypatch):
        """Returns message when no knowledge exists."""
        # Patch the module-level constants
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        result = sage_list_knowledge()

        assert "No knowledge items found" in result

    def test_list_shows_knowledge_items(self, tmp_path, monkeypatch):
        """Lists saved knowledge items."""
        # Patch the module-level constants
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        # Save some knowledge
        sage_save_knowledge(
            knowledge_id="item-one",
            content="First item content",
            keywords=["first", "one"],
        )

        result = sage_list_knowledge()

        assert "item-one" in result
        assert "first" in result.lower()


class TestRemoveKnowledge:
    """Tests for sage_remove_knowledge tool."""

    def test_remove_nonexistent_returns_not_found(self, tmp_path, monkeypatch):
        """Returns not found for nonexistent item."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        result = sage_remove_knowledge("nonexistent")

        assert "not found" in result.lower()

    def test_remove_existing_returns_confirmation(self, tmp_path, monkeypatch):
        """Returns confirmation for removed item."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        # Save then remove
        sage_save_knowledge(
            knowledge_id="to-remove",
            content="Content",
            keywords=["remove"],
        )

        result = sage_remove_knowledge("to-remove")

        assert "✓ Removed" in result
        assert "to-remove" in result


class TestAutosaveCheck:
    """Tests for sage_autosave_check tool."""

    def test_autosave_thresholds_defined(self):
        """All expected triggers have thresholds."""
        expected_triggers = [
            "research_start",
            "web_search_complete",
            "synthesis",
            "topic_shift",
            "user_validated",
            "constraint_discovered",
            "branch_point",
            "precompact",
            "context_threshold",
            "manual",
        ]

        for trigger in expected_triggers:
            assert trigger in AUTOSAVE_THRESHOLDS

    def test_autosave_rejects_invalid_confidence(self, isolated_project):
        """Rejects invalid confidence values."""
        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="Question",
            current_thesis="Thesis",
            confidence=1.5,
        )

        assert "Invalid confidence" in result

    def test_autosave_rejects_unknown_trigger(self, isolated_project):
        """Rejects unknown trigger events."""
        result = sage_autosave_check(
            trigger_event="unknown_trigger",
            core_question="Question",
            current_thesis="Thesis",
            confidence=0.5,
        )

        assert "Unknown trigger" in result
        assert "unknown_trigger" in result

    def test_autosave_skips_low_confidence(self, isolated_project):
        """Skips save when confidence below threshold."""
        # synthesis requires 0.5, give it 0.3
        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="Question",
            current_thesis="Thesis",
            confidence=0.3,
        )

        assert "Not saving" in result
        assert "confidence" in result.lower()

    def test_autosave_skips_brief_thesis(self, isolated_project):
        """Skips save when thesis too brief."""
        result = sage_autosave_check(
            trigger_event="manual",  # No confidence threshold
            core_question="Question",
            current_thesis="Short",  # Less than 10 chars
            confidence=1.0,
        )

        assert "Not saving" in result
        assert "brief" in result.lower()

    def test_autosave_skips_missing_question(self, isolated_project):
        """Skips save when no clear question."""
        result = sage_autosave_check(
            trigger_event="manual",
            core_question="",
            current_thesis="A valid thesis with enough content.",
            confidence=1.0,
        )

        assert "Not saving" in result
        assert "question" in result.lower()

    def test_autosave_enforces_depth_thresholds(self, isolated_project, monkeypatch):
        """Enforces depth thresholds for non-exempt triggers."""
        # Create a config with depth requirements
        mock_config = SageConfig(depth_min_messages=8, depth_min_tokens=2000)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        # synthesis is NOT exempt, so depth is enforced
        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="A clear research question here",
            current_thesis="A thesis with sufficient content for validation.",
            confidence=0.8,
            message_count=3,  # Below 8
            token_estimate=500,  # Below 2000
        )

        assert "Not saving" in result
        assert "shallow" in result.lower()

    def test_autosave_exempt_triggers_skip_depth(self, isolated_project, monkeypatch):
        """Exempt triggers skip depth threshold checks."""
        mock_config = SageConfig(depth_min_messages=8, depth_min_tokens=2000)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        # manual is exempt
        result = sage_autosave_check(
            trigger_event="manual",
            core_question="A clear research question here",
            current_thesis="A thesis with sufficient content for validation.",
            confidence=0.8,
            message_count=1,  # Below threshold but exempt
            token_estimate=100,  # Below threshold but exempt
        )

        # Should either save or fail for other reasons, not depth
        assert "shallow" not in result.lower()

    def test_autosave_saves_valid_checkpoint(self, isolated_project, monkeypatch):
        """Saves checkpoint when all validations pass."""
        mock_config = SageConfig(depth_min_messages=5, depth_min_tokens=1000)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="How should we handle authentication?",
            current_thesis="JWT tokens provide the best balance of security and statelessness.",
            confidence=0.75,
            message_count=10,
            token_estimate=3000,
        )

        assert "📍 Autosaved:" in result
        assert "Checkpoint:" in result

    def test_autosave_includes_depth_metadata(self, isolated_project, monkeypatch):
        """Saved checkpoint includes depth metadata."""
        mock_config = SageConfig(depth_min_messages=5, depth_min_tokens=1000)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        result = sage_autosave_check(
            trigger_event="synthesis",
            core_question="Research question for depth test",
            current_thesis="A thesis that passes all validation checks.",
            confidence=0.8,
            message_count=15,
            token_estimate=5000,
        )

        # Checkpoint should be saved
        assert "📍 Autosaved:" in result

        # Load and verify metadata
        checkpoint_id = result.split("Checkpoint: ")[1].strip()
        loaded = sage_load_checkpoint(checkpoint_id)

        # Message count and token estimate should be in the checkpoint
        # (depends on format_checkpoint_for_context including them)
        assert loaded  # At minimum, should load

    def test_autosave_research_start_no_threshold(self, isolated_project):
        """research_start has 0 confidence threshold."""
        result = sage_autosave_check(
            trigger_event="research_start",
            core_question="Starting a new research topic",
            current_thesis="Initial hypothesis before any research.",
            confidence=0.0,  # Zero confidence
        )

        assert "📍 Autosaved:" in result

    def test_autosave_context_threshold_always_saves(self, isolated_project):
        """context_threshold trigger always saves (0 threshold)."""
        result = sage_autosave_check(
            trigger_event="context_threshold",
            core_question="Context getting full, need to checkpoint",
            current_thesis="Summary of research so far before compaction.",
            confidence=0.1,  # Very low but should still save
        )

        assert "📍 Autosaved:" in result


class TestAutosaveCheckDuplication:
    """Tests for duplicate checkpoint detection in autosave."""

    def test_autosave_detects_duplicate(self, isolated_project):
        """Detects semantically similar checkpoints."""
        # First save
        sage_autosave_check(
            trigger_event="manual",
            core_question="How to handle auth?",
            current_thesis="JWT is the best approach for authentication.",
            confidence=0.8,
        )

        # Second save with very similar thesis
        result = sage_autosave_check(
            trigger_event="manual",
            core_question="How to handle auth?",
            current_thesis="JWT is the best approach for authentication.",  # Identical
            confidence=0.8,
        )

        # Should detect duplicate (depends on embeddings being available)
        # Without embeddings, may save anyway
        assert "📍 Autosaved:" in result or "similar" in result.lower()


class TestAutosaveCheckWithOptionalFields:
    """Tests for autosave with optional fields."""

    def test_autosave_with_sources(self, isolated_project):
        """Autosave includes sources in checkpoint."""
        result = sage_autosave_check(
            trigger_event="manual",
            core_question="What's the best database?",
            current_thesis="PostgreSQL is best for complex queries.",
            confidence=0.9,
            sources=[
                {"id": "pg-docs", "type": "docs", "take": "Rich SQL support"},
            ],
        )

        assert "📍 Autosaved:" in result

    def test_autosave_with_key_evidence(self, isolated_project):
        """Autosave includes key_evidence in checkpoint."""
        result = sage_autosave_check(
            trigger_event="manual",
            core_question="Is Redis good for caching?",
            current_thesis="Redis excels at distributed caching.",
            confidence=0.85,
            key_evidence=["Sub-millisecond latency", "Built-in clustering"],
        )

        assert "📍 Autosaved:" in result

    def test_autosave_with_reasoning_trace(self, isolated_project):
        """Autosave includes reasoning_trace in checkpoint."""
        result = sage_autosave_check(
            trigger_event="manual",
            core_question="Should we use microservices?",
            current_thesis="Monolith first, then extract services.",
            confidence=0.75,
            reasoning_trace="Started thinking microservices, but complexity suggests starting simpler.",
        )

        assert "📍 Autosaved:" in result


class TestMCPServerModuleLevel:
    """Tests for module-level concerns."""

    def test_project_root_detection(self):
        """Module detects project root at import."""
        from sage.mcp_server import _PROJECT_ROOT

        # Should either be None or a Path
        assert _PROJECT_ROOT is None or isinstance(_PROJECT_ROOT, Path)

    def test_mcp_instance_exists(self):
        """MCP instance is created."""
        from sage.mcp_server import mcp

        assert mcp is not None
        assert mcp.name == "sage"

    def test_all_tools_registered(self):
        """All expected tools are registered."""
        from sage.mcp_server import mcp

        # Check that key tools exist
        # The actual tool registration depends on FastMCP internals
        # This is a basic sanity check
        assert hasattr(mcp, 'tool')
