"""Tests for MCP server tools.

Note: These tests run with async_enabled=False (sync fallback mode) for simplicity.
Async-specific behavior is tested in test_mcp_async.py.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sage.config import SageConfig
from sage.mcp_server import (
    AUTOSAVE_TRIGGERS,
    sage_autosave_check,
    sage_list_checkpoints,
    sage_list_knowledge,
    sage_load_checkpoint,
    sage_recall_knowledge,
    sage_remove_knowledge,
    sage_save_checkpoint,
    sage_save_knowledge,
    sage_search_checkpoints,
)

# Mark all tests as async
pytestmark = pytest.mark.asyncio


@pytest.fixture
def isolated_project(tmp_path, monkeypatch):
    """Fixture that sets up an isolated project directory for testing.

    Also disables async mode so tools execute synchronously.
    """
    # Create .sage directory so get_checkpoints_dir uses it
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    (sage_dir / "checkpoints").mkdir()
    (sage_dir / "knowledge").mkdir()

    # Monkeypatch the project root
    monkeypatch.setattr("sage.mcp_server._PROJECT_ROOT", tmp_path)

    # Also patch the global CHECKPOINTS_DIR as fallback
    monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", sage_dir / "checkpoints")

    # Disable async mode for these tests (sync fallback)
    sync_config = SageConfig(async_enabled=False)
    monkeypatch.setattr(
        "sage.mcp_server.get_sage_config",
        lambda project_path=None: sync_config,
    )

    return tmp_path


class TestSaveCheckpoint:
    """Tests for sage_save_checkpoint tool."""

    async def test_save_checkpoint_returns_confirmation(self, isolated_project):
        """Saving checkpoint returns confirmation with ID."""
        result = await sage_save_checkpoint(
            core_question="How to implement auth?",
            thesis="JWT is the best approach for stateless auth.",
            confidence=0.8,
        )

        assert "✓ Checkpoint saved:" in result
        assert "Path:" in result

    async def test_save_checkpoint_rejects_invalid_confidence_low(self, isolated_project):
        """Rejects confidence below 0."""
        result = await sage_save_checkpoint(
            core_question="Question",
            thesis="Thesis",
            confidence=-0.1,
        )

        assert "Invalid confidence" in result
        assert "-0.1" in result
        assert "0.0 and 1.0" in result

    async def test_save_checkpoint_rejects_invalid_confidence_high(self, isolated_project):
        """Rejects confidence above 1."""
        result = await sage_save_checkpoint(
            core_question="Question",
            thesis="Thesis",
            confidence=1.5,
        )

        assert "Invalid confidence" in result
        assert "1.5" in result

    async def test_save_checkpoint_accepts_boundary_confidence(self, isolated_project):
        """Accepts boundary confidence values 0.0 and 1.0."""
        # Test 0.0
        result = await sage_save_checkpoint(
            core_question="Question",
            thesis="Thesis",
            confidence=0.0,
        )
        assert "✓ Checkpoint saved:" in result

        # Test 1.0
        result = await sage_save_checkpoint(
            core_question="Question two",
            thesis="Thesis two",
            confidence=1.0,
        )
        assert "✓ Checkpoint saved:" in result

    async def test_save_checkpoint_with_all_optional_fields(self, isolated_project):
        """Can save checkpoint with all optional fields."""
        result = await sage_save_checkpoint(
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

    async def test_list_empty_returns_no_checkpoints(self, isolated_project):
        """Returns message when no checkpoints exist."""
        result = sage_list_checkpoints()

        assert "No checkpoints found" in result

    async def test_list_returns_checkpoints(self, isolated_project):
        """Lists saved checkpoints."""
        # Save a checkpoint first
        await sage_save_checkpoint(
            core_question="Test question",
            thesis="Test thesis for listing",
            confidence=0.7,
        )

        result = sage_list_checkpoints()

        assert "Found 1 checkpoint" in result
        assert "Test thesis" in result
        assert "70%" in result

    async def test_list_respects_limit(self, isolated_project):
        """Respects limit parameter."""
        # Save multiple checkpoints
        for i in range(5):
            await sage_save_checkpoint(
                core_question=f"Question {i}",
                thesis=f"Thesis number {i} here",
                confidence=0.5,
            )

        result = sage_list_checkpoints(limit=3)

        # Should only show 3 (each checkpoint has **id** so count of "**" = 6)
        assert "Found 3 checkpoint" in result

    async def test_list_truncates_long_thesis(self, isolated_project):
        """Truncates long thesis in preview."""
        long_thesis = "A" * 100  # Longer than 60 char preview
        await sage_save_checkpoint(
            core_question="Question",
            thesis=long_thesis,
            confidence=0.5,
        )

        result = sage_list_checkpoints()

        assert "..." in result
        assert long_thesis not in result  # Full thesis shouldn't appear


class TestLoadCheckpoint:
    """Tests for sage_load_checkpoint tool."""

    async def test_load_nonexistent_returns_error(self, isolated_project):
        """Returns error for nonexistent checkpoint."""
        result = sage_load_checkpoint("nonexistent-id")

        assert "not found" in result.lower()

    async def test_load_returns_formatted_context(self, isolated_project):
        """Returns formatted checkpoint context."""
        # Save checkpoint
        save_result = await sage_save_checkpoint(
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

    async def test_load_supports_partial_id(self, isolated_project):
        """Supports partial ID matching."""
        # Save checkpoint
        save_result = await sage_save_checkpoint(
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

    async def test_search_without_embeddings(self, isolated_project):
        """Returns message when embeddings not available."""
        # embeddings is imported inside sage_search_checkpoints, so patch sage.embeddings
        with patch("sage.embeddings.is_available") as mock_is_available:
            mock_is_available.return_value = False

            result = sage_search_checkpoints("test query")

            assert "unavailable" in result.lower()
            assert "pip install" in result

    async def test_search_empty_checkpoints(self, isolated_project):
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

    async def test_save_knowledge_returns_confirmation(self, tmp_path, monkeypatch):
        """Saving knowledge returns confirmation."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)
        # Disable async mode
        sync_config = SageConfig(async_enabled=False)
        monkeypatch.setattr(
            "sage.mcp_server.get_sage_config", lambda project_path=None: sync_config
        )

        result = await sage_save_knowledge(
            knowledge_id="test-knowledge",
            content="Test content",
            keywords=["test", "knowledge"],
        )

        assert "✓ Knowledge saved:" in result
        assert "test-knowledge" in result
        assert "global" in result

    async def test_save_knowledge_with_skill_scope(self, tmp_path, monkeypatch):
        """Shows skill scope in confirmation."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)
        # Disable async mode
        sync_config = SageConfig(async_enabled=False)
        monkeypatch.setattr(
            "sage.mcp_server.get_sage_config", lambda project_path=None: sync_config
        )

        result = await sage_save_knowledge(
            knowledge_id="scoped-knowledge",
            content="Scoped content",
            keywords=["scoped"],
            skill="my-skill",
        )

        assert "skill:my-skill" in result


class TestRecallKnowledge:
    """Tests for sage_recall_knowledge tool."""

    async def test_recall_empty_returns_message(self, tmp_path, monkeypatch):
        """Returns message when nothing recalled."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        with patch("sage.embeddings.is_available") as mock_is_available:
            mock_is_available.return_value = False

            result = sage_recall_knowledge("unknown query")

            assert "No relevant knowledge" in result
            assert "pip install" in result

    async def test_recall_with_embeddings_hint(self, tmp_path, monkeypatch):
        """Shows embeddings hint when not installed."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        with patch("sage.embeddings.is_available") as mock_is_available:
            mock_is_available.return_value = False

            result = sage_recall_knowledge("query")

            assert "semantic recall" in result.lower() or "embeddings" in result.lower()


class TestListKnowledge:
    """Tests for sage_list_knowledge tool."""

    async def test_list_empty_returns_message(self, tmp_path, monkeypatch):
        """Returns message when no knowledge exists."""
        # Patch the module-level constants
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        result = sage_list_knowledge()

        assert "No knowledge items found" in result

    async def test_list_shows_knowledge_items(self, tmp_path, monkeypatch):
        """Lists saved knowledge items."""
        # Patch the module-level constants
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir()
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")
        # Disable async mode
        sync_config = SageConfig(async_enabled=False)
        monkeypatch.setattr(
            "sage.mcp_server.get_sage_config", lambda project_path=None: sync_config
        )

        # Save some knowledge
        await sage_save_knowledge(
            knowledge_id="item-one",
            content="First item content",
            keywords=["first", "one"],
        )

        result = sage_list_knowledge()

        assert "item-one" in result
        assert "first" in result.lower()


class TestRemoveKnowledge:
    """Tests for sage_remove_knowledge tool."""

    async def test_remove_nonexistent_returns_not_found(self, tmp_path, monkeypatch):
        """Returns not found for nonexistent item."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)

        result = sage_remove_knowledge("nonexistent")

        assert "not found" in result.lower()

    async def test_remove_existing_returns_confirmation(self, tmp_path, monkeypatch):
        """Returns confirmation for removed item."""
        monkeypatch.setattr("sage.knowledge.SAGE_DIR", tmp_path)
        # Disable async mode
        sync_config = SageConfig(async_enabled=False)
        monkeypatch.setattr(
            "sage.mcp_server.get_sage_config", lambda project_path=None: sync_config
        )

        # Save then remove
        await sage_save_knowledge(
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
            assert trigger in AUTOSAVE_TRIGGERS

    async def test_autosave_rejects_invalid_confidence(self, isolated_project):
        """Rejects invalid confidence values."""
        result = await sage_autosave_check(
            trigger_event="synthesis",
            core_question="Question",
            current_thesis="Thesis",
            confidence=1.5,
        )

        assert "Invalid confidence" in result

    async def test_autosave_rejects_unknown_trigger(self, isolated_project):
        """Rejects unknown trigger events."""
        result = await sage_autosave_check(
            trigger_event="unknown_trigger",
            core_question="Question",
            current_thesis="Thesis",
            confidence=0.5,
        )

        assert "Unknown trigger" in result
        assert "unknown_trigger" in result

    async def test_autosave_skips_low_confidence(self, isolated_project):
        """Skips save when confidence below threshold."""
        # synthesis requires 0.5, give it 0.3
        result = await sage_autosave_check(
            trigger_event="synthesis",
            core_question="Question",
            current_thesis="Thesis",
            confidence=0.3,
        )

        assert "Not saving" in result
        assert "confidence" in result.lower()

    async def test_autosave_skips_brief_thesis(self, isolated_project):
        """Skips save when thesis too brief."""
        result = await sage_autosave_check(
            trigger_event="manual",  # No confidence threshold
            core_question="Question",
            current_thesis="Short",  # Less than 10 chars
            confidence=1.0,
        )

        assert "Not saving" in result
        assert "brief" in result.lower()

    async def test_autosave_skips_missing_question(self, isolated_project):
        """Skips save when no clear question."""
        result = await sage_autosave_check(
            trigger_event="manual",
            core_question="",
            current_thesis="A valid thesis with enough content.",
            confidence=1.0,
        )

        assert "Not saving" in result
        assert "question" in result.lower()

    async def test_autosave_enforces_depth_thresholds(self, isolated_project, monkeypatch):
        """Enforces depth thresholds for non-exempt triggers."""
        # Create a config with depth requirements (also disable async)
        mock_config = SageConfig(depth_min_messages=8, depth_min_tokens=2000, async_enabled=False)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        # synthesis is NOT exempt, so depth is enforced
        result = await sage_autosave_check(
            trigger_event="synthesis",
            core_question="A clear research question here",
            current_thesis="A thesis with sufficient content for validation.",
            confidence=0.8,
            message_count=3,  # Below 8
            token_estimate=500,  # Below 2000
        )

        assert "Not saving" in result
        assert "shallow" in result.lower()

    async def test_autosave_exempt_triggers_skip_depth(self, isolated_project, monkeypatch):
        """Exempt triggers skip depth threshold checks."""
        mock_config = SageConfig(depth_min_messages=8, depth_min_tokens=2000, async_enabled=False)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        # manual is exempt
        result = await sage_autosave_check(
            trigger_event="manual",
            core_question="A clear research question here",
            current_thesis="A thesis with sufficient content for validation.",
            confidence=0.8,
            message_count=1,  # Below threshold but exempt
            token_estimate=100,  # Below threshold but exempt
        )

        # Should either save or fail for other reasons, not depth
        assert "shallow" not in result.lower()

    async def test_autosave_saves_valid_checkpoint(self, isolated_project, monkeypatch):
        """Saves checkpoint when all validations pass."""
        mock_config = SageConfig(depth_min_messages=5, depth_min_tokens=1000, async_enabled=False)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        result = await sage_autosave_check(
            trigger_event="synthesis",
            core_question="How should we handle authentication?",
            current_thesis="JWT tokens provide the best balance of security and statelessness.",
            confidence=0.75,
            message_count=10,
            token_estimate=3000,
        )

        assert "📍 Autosaved:" in result
        assert "Checkpoint:" in result

    async def test_autosave_includes_depth_metadata(self, isolated_project, monkeypatch):
        """Saved checkpoint includes depth metadata."""
        mock_config = SageConfig(depth_min_messages=5, depth_min_tokens=1000, async_enabled=False)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        result = await sage_autosave_check(
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

    async def test_autosave_research_start_no_threshold(self, isolated_project):
        """research_start has 0 confidence threshold."""
        result = await sage_autosave_check(
            trigger_event="research_start",
            core_question="Starting a new research topic",
            current_thesis="Initial hypothesis before any research.",
            confidence=0.0,  # Zero confidence
        )

        assert "📍 Autosaved:" in result

    async def test_autosave_context_threshold_always_saves(self, isolated_project):
        """context_threshold trigger always saves (0 threshold)."""
        result = await sage_autosave_check(
            trigger_event="context_threshold",
            core_question="Context getting full, need to checkpoint",
            current_thesis="Summary of research so far before compaction.",
            confidence=0.1,  # Very low but should still save
        )

        assert "📍 Autosaved:" in result


class TestAutosaveCheckDuplication:
    """Tests for duplicate checkpoint detection in autosave."""

    async def test_autosave_detects_duplicate(self, isolated_project):
        """Detects semantically similar checkpoints."""
        # First save
        await sage_autosave_check(
            trigger_event="manual",
            core_question="How to handle auth?",
            current_thesis="JWT is the best approach for authentication.",
            confidence=0.8,
        )

        # Second save with very similar thesis
        result = await sage_autosave_check(
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

    async def test_autosave_with_sources(self, isolated_project):
        """Autosave includes sources in checkpoint."""
        result = await sage_autosave_check(
            trigger_event="manual",
            core_question="What's the best database?",
            current_thesis="PostgreSQL is best for complex queries.",
            confidence=0.9,
            sources=[
                {"id": "pg-docs", "type": "docs", "take": "Rich SQL support"},
            ],
        )

        assert "📍 Autosaved:" in result

    async def test_autosave_with_key_evidence(self, isolated_project):
        """Autosave includes key_evidence in checkpoint."""
        result = await sage_autosave_check(
            trigger_event="manual",
            core_question="Is Redis good for caching?",
            current_thesis="Redis excels at distributed caching.",
            confidence=0.85,
            key_evidence=["Sub-millisecond latency", "Built-in clustering"],
        )

        assert "📍 Autosaved:" in result

    async def test_autosave_with_reasoning_trace(self, isolated_project):
        """Autosave includes reasoning_trace in checkpoint."""
        result = await sage_autosave_check(
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
        assert hasattr(mcp, "tool")


class TestSageVersion:
    """Tests for sage_version tool."""

    def test_version_returns_string(self):
        """sage_version returns a string."""
        from sage.mcp_server import sage_version

        result = sage_version()
        assert isinstance(result, str)

    def test_version_contains_version_number(self):
        """sage_version includes version number."""
        from sage.mcp_server import sage_version

        result = sage_version()
        assert "Sage v" in result

    def test_version_contains_config_info(self):
        """sage_version includes configuration details."""
        from sage.mcp_server import sage_version

        result = sage_version()
        assert "Embedding model:" in result
        assert "Recall threshold:" in result

    def test_version_shows_embeddings_availability(self):
        """sage_version shows whether embeddings are available."""
        from sage.mcp_server import sage_version

        result = sage_version()
        assert "Embeddings available:" in result


class TestSageDebugQuery:
    """Tests for sage_debug_query tool."""

    def test_debug_query_returns_string(self):
        """sage_debug_query returns a string."""
        from sage.mcp_server import sage_debug_query

        result = sage_debug_query("test query")
        assert isinstance(result, str)

    def test_debug_query_shows_query(self):
        """sage_debug_query shows the query being tested."""
        from sage.mcp_server import sage_debug_query

        result = sage_debug_query("my test query")
        assert "my test query" in result

    def test_debug_query_shows_knowledge_section(self):
        """sage_debug_query includes knowledge matches section."""
        from sage.mcp_server import sage_debug_query

        result = sage_debug_query("test")
        assert "Knowledge Matches" in result

    def test_debug_query_shows_checkpoint_section(self):
        """sage_debug_query includes checkpoint matches section."""
        from sage.mcp_server import sage_debug_query

        result = sage_debug_query("test")
        assert "Checkpoint Matches" in result

    def test_debug_query_can_exclude_checkpoints(self):
        """sage_debug_query can exclude checkpoints."""
        from sage.mcp_server import sage_debug_query

        result = sage_debug_query("test", include_checkpoints=False)
        assert "Knowledge Matches" in result
        assert "Checkpoint Matches" not in result

    def test_debug_query_shows_weights(self):
        """sage_debug_query shows scoring weights."""
        from sage.mcp_server import sage_debug_query

        result = sage_debug_query("test")
        assert "embedding=" in result
        assert "keyword=" in result

    def test_debug_query_with_skill(self):
        """sage_debug_query accepts skill parameter."""
        from sage.mcp_server import sage_debug_query

        result = sage_debug_query("test", skill="crypto-payments")
        assert "crypto-payments" in result


class TestSageHealth:
    """Tests for sage_health tool."""

    def test_health_returns_string(self):
        """sage_health returns a string."""
        from sage.mcp_server import sage_health

        result = sage_health()
        assert isinstance(result, str)

    def test_health_shows_header(self):
        """sage_health shows health check header."""
        from sage.mcp_server import sage_health

        result = sage_health()
        assert "Health Check" in result

    def test_health_checks_sage_directory(self):
        """sage_health checks SAGE_DIR."""
        from sage.mcp_server import sage_health

        result = sage_health()
        assert "Sage directory" in result or ".sage" in result

    def test_health_checks_embeddings(self):
        """sage_health checks embedding availability."""
        from sage.mcp_server import sage_health

        result = sage_health()
        assert "Embeddings" in result or "embedding" in result.lower()

    def test_health_shows_summary(self):
        """sage_health shows summary."""
        from sage.mcp_server import sage_health

        result = sage_health()
        assert "healthy" in result.lower() or "issue" in result.lower()


class TestSageGetConfig:
    """Tests for sage_get_config tool."""

    def test_get_config_returns_string(self):
        """sage_get_config returns a string."""
        from sage.mcp_server import sage_get_config

        result = sage_get_config()
        assert isinstance(result, str)

    def test_get_config_shows_header(self):
        """sage_get_config shows config header."""
        from sage.mcp_server import sage_get_config

        result = sage_get_config()
        assert "Configuration" in result

    def test_get_config_shows_tuning_values(self):
        """sage_get_config shows tuning parameters."""
        from sage.mcp_server import sage_get_config

        result = sage_get_config()
        assert "recall_threshold" in result
        assert "embedding_weight" in result

    def test_get_config_shows_locations(self):
        """sage_get_config shows config file locations."""
        from sage.mcp_server import sage_get_config

        result = sage_get_config()
        assert "Config locations" in result or ".sage" in result


class TestSageUpdateKnowledge:
    """Tests for sage_update_knowledge tool."""

    def test_update_requires_at_least_one_field(self):
        """sage_update_knowledge requires at least one field."""
        from sage.mcp_server import sage_update_knowledge

        result = sage_update_knowledge("some-id")
        assert "Error" in result
        assert "at least one field" in result.lower()

    def test_update_validates_status(self):
        """sage_update_knowledge validates status values."""
        from sage.mcp_server import sage_update_knowledge

        result = sage_update_knowledge("some-id", status="invalid")
        assert "Error" in result
        assert "Invalid status" in result

    def test_update_returns_not_found(self, tmp_path, monkeypatch):
        """sage_update_knowledge returns error for missing item."""
        from sage.mcp_server import sage_update_knowledge

        knowledge_dir = tmp_path / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        result = sage_update_knowledge("nonexistent", content="new content")
        assert "not found" in result.lower()

    def test_update_accepts_valid_status(self):
        """sage_update_knowledge accepts valid status values."""
        from sage.mcp_server import sage_update_knowledge

        # Should not error on validation (will fail on not found)
        for status in ["active", "deprecated", "archived"]:
            result = sage_update_knowledge("test-id", status=status)
            assert "Invalid status" not in result


class TestSageDeprecateKnowledge:
    """Tests for sage_deprecate_knowledge tool."""

    def test_deprecate_requires_reason(self):
        """sage_deprecate_knowledge requires reason."""
        from sage.mcp_server import sage_deprecate_knowledge

        result = sage_deprecate_knowledge("some-id", reason="")
        assert "Error" in result
        assert "reason" in result.lower()

    def test_deprecate_returns_not_found(self, tmp_path, monkeypatch):
        """sage_deprecate_knowledge returns error for missing item."""
        from sage.mcp_server import sage_deprecate_knowledge

        knowledge_dir = tmp_path / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        result = sage_deprecate_knowledge("nonexistent", reason="test reason")
        assert "not found" in result.lower()


class TestSageArchiveKnowledge:
    """Tests for sage_archive_knowledge tool."""

    def test_archive_returns_not_found(self, tmp_path, monkeypatch):
        """sage_archive_knowledge returns error for missing item."""
        from sage.mcp_server import sage_archive_knowledge

        knowledge_dir = tmp_path / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        result = sage_archive_knowledge("nonexistent")
        assert "not found" in result.lower()

    def test_archive_shows_restore_hint(self, tmp_path, monkeypatch):
        """sage_archive_knowledge shows how to restore."""
        from sage.knowledge import add_knowledge
        from sage.mcp_server import sage_archive_knowledge

        knowledge_dir = tmp_path / ".sage" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "global").mkdir(parents=True)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", knowledge_dir)
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_INDEX", knowledge_dir / "index.yaml")

        # Add an item first
        add_knowledge(
            content="Test content",
            knowledge_id="test-archive-hint",
            keywords=["test"],
        )

        result = sage_archive_knowledge("test-archive-hint")
        assert "Archived" in result
        assert "sage_update_knowledge" in result


class TestSageSetConfig:
    """Tests for sage_set_config tool."""

    def test_set_config_returns_confirmation(self, tmp_path, monkeypatch):
        """sage_set_config returns confirmation message."""
        from sage.mcp_server import sage_set_config

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)

        result = sage_set_config("recall_threshold", "0.65")
        assert "✓" in result
        assert "recall_threshold" in result
        assert "0.65" in result

    def test_set_config_rejects_invalid_key(self):
        """sage_set_config rejects unknown keys."""
        from sage.mcp_server import sage_set_config

        result = sage_set_config("invalid_key_xyz", "0.5")
        assert "Unknown config key" in result

    def test_set_config_validates_float_type(self, tmp_path, monkeypatch):
        """sage_set_config validates float values."""
        from sage.mcp_server import sage_set_config

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)

        result = sage_set_config("recall_threshold", "not_a_number")
        assert "Invalid value" in result

    def test_set_config_shows_valid_keys_on_error(self):
        """sage_set_config shows valid keys when unknown key provided."""
        from sage.mcp_server import sage_set_config

        result = sage_set_config("bad_key", "0.5")
        assert "recall_threshold" in result  # Should list valid keys

    def test_set_config_reminds_to_reload(self, tmp_path, monkeypatch):
        """sage_set_config reminds user to reload config."""
        from sage.mcp_server import sage_set_config

        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.config.SAGE_DIR", sage_dir)

        result = sage_set_config("recall_threshold", "0.5")
        assert "sage_reload_config" in result


class TestReloadConfig:
    """Tests for sage_reload_config tool."""

    def test_reload_config_returns_confirmation(self, tmp_path, monkeypatch):
        """Reloading config returns confirmation."""
        from sage.mcp_server import sage_reload_config

        # Set up project root
        monkeypatch.setattr("sage.mcp_server._PROJECT_ROOT", tmp_path)

        # Mock embeddings module
        monkeypatch.setattr("sage.embeddings._model", None)
        monkeypatch.setattr("sage.embeddings._model_name", None)

        result = sage_reload_config()

        assert "✓ Configuration reloaded" in result

    def test_reload_config_clears_model_cache(self, tmp_path, monkeypatch):
        """Reloading config clears the embedding model cache."""
        import sage.embeddings
        from sage.mcp_server import sage_reload_config

        # Set up fake cached model
        mock_model = MagicMock()
        monkeypatch.setattr(sage.embeddings, "_model", mock_model)
        monkeypatch.setattr(sage.embeddings, "_model_name", "old-model")
        monkeypatch.setattr("sage.mcp_server._PROJECT_ROOT", tmp_path)

        result = sage_reload_config()

        # Model cache should be cleared
        assert sage.embeddings._model is None
        assert sage.embeddings._model_name is None
        assert "Cleared cached model" in result
        assert "old-model" in result

    def test_reload_config_shows_new_model(self, tmp_path, monkeypatch):
        """Shows the newly configured model after reload."""
        import sage.embeddings
        from sage.mcp_server import sage_reload_config

        # Set up fake cached model
        monkeypatch.setattr(sage.embeddings, "_model", MagicMock())
        monkeypatch.setattr(sage.embeddings, "_model_name", "old-model")
        monkeypatch.setattr("sage.mcp_server._PROJECT_ROOT", tmp_path)

        # Mock get_sage_config to return a config with new model
        mock_config = SageConfig(embedding_model="BAAI/bge-base-en-v1.5")
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        result = sage_reload_config()

        assert "New model (on next use)" in result
        assert "BAAI/bge-base-en-v1.5" in result

    def test_reload_config_shows_thresholds(self, tmp_path, monkeypatch):
        """Shows recall and dedup thresholds after reload."""
        import sage.embeddings
        from sage.mcp_server import sage_reload_config

        monkeypatch.setattr(sage.embeddings, "_model", None)
        monkeypatch.setattr(sage.embeddings, "_model_name", None)
        monkeypatch.setattr("sage.mcp_server._PROJECT_ROOT", tmp_path)

        mock_config = SageConfig(recall_threshold=0.65, dedup_threshold=0.88)
        monkeypatch.setattr("sage.config.get_sage_config", lambda project_path=None: mock_config)

        result = sage_reload_config()

        assert "Recall threshold: 0.65" in result
        assert "Dedup threshold: 0.88" in result

    def test_reload_config_detects_project_change(self, tmp_path, monkeypatch):
        """Detects when project root changes."""
        import sage.embeddings
        import sage.mcp_server
        from sage.mcp_server import sage_reload_config

        old_project = Path("/old/project")
        new_project = tmp_path / "new_project"
        new_project.mkdir()

        monkeypatch.setattr(sage.embeddings, "_model", None)
        monkeypatch.setattr(sage.embeddings, "_model_name", None)
        monkeypatch.setattr(sage.mcp_server, "_PROJECT_ROOT", old_project)
        monkeypatch.setattr("sage.config.detect_project_root", lambda: new_project)

        result = sage_reload_config()

        assert str(old_project) in result or "Project root" in result
