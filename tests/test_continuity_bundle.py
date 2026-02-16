"""Tests for ContinuityBundle architecture (v4.0)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sage.continuity import (
    CONTINUITY_FILE,
    ContinuityBundle,
    _build_query_from_checkpoint_id,
    _find_most_recent_substantive_checkpoint,
    _find_related_knowledge,
    _find_relevant_failures,
    clear_continuity,
    create_continuity_bundle,
    get_continuity_bundle,
    get_continuity_marker,
    mark_for_continuity_with_bundle,
)


@pytest.fixture
def temp_sage_dir(tmp_path):
    """Create a temporary sage directory structure."""
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()
    checkpoints_dir = sage_dir / "checkpoints"
    checkpoints_dir.mkdir()
    return sage_dir


@pytest.fixture
def no_project_root():
    """Mock detect_project_root to return None so tests use global CONTINUITY_FILE."""
    with patch("sage.continuity.detect_project_root", return_value=None):
        yield


@pytest.fixture
def cleanup_continuity(no_project_root):
    """Clean up continuity file after test."""
    yield
    if CONTINUITY_FILE.exists():
        CONTINUITY_FILE.unlink()


class TestContinuityBundleDataclass:
    """Tests for ContinuityBundle dataclass."""

    def test_default_values(self):
        """Bundle has sensible defaults."""
        bundle = ContinuityBundle()

        assert bundle.recovery_checkpoint_id is None
        assert bundle.substantive_checkpoint_id is None
        assert bundle.knowledge_ids == ()
        assert bundle.failure_ids == ()
        assert bundle.created_at == ""
        assert bundle.extraction_method == "semantic"

    def test_with_all_fields(self):
        """Bundle can be created with all fields."""
        bundle = ContinuityBundle(
            recovery_checkpoint_id="2026-01-22_recovery-test",
            substantive_checkpoint_id="2026-01-22_real-checkpoint",
            knowledge_ids=("knowledge-1", "knowledge-2"),
            failure_ids=("failure-1",),
            created_at="2026-01-22T10:00:00+00:00",
            extraction_method="semantic",
        )

        assert bundle.recovery_checkpoint_id == "2026-01-22_recovery-test"
        assert bundle.substantive_checkpoint_id == "2026-01-22_real-checkpoint"
        assert bundle.knowledge_ids == ("knowledge-1", "knowledge-2")
        assert bundle.failure_ids == ("failure-1",)

    def test_to_dict(self):
        """Bundle converts to dict correctly."""
        bundle = ContinuityBundle(
            recovery_checkpoint_id="recovery-id",
            substantive_checkpoint_id="substantive-id",
            knowledge_ids=("k1", "k2"),
            failure_ids=("f1",),
            created_at="2026-01-22T10:00:00+00:00",
            extraction_method="semantic",
        )

        d = bundle.to_dict()

        assert d["recovery_checkpoint_id"] == "recovery-id"
        assert d["substantive_checkpoint_id"] == "substantive-id"
        assert d["knowledge_ids"] == ["k1", "k2"]  # Tuple becomes list
        assert d["failure_ids"] == ["f1"]
        assert d["created_at"] == "2026-01-22T10:00:00+00:00"
        assert d["extraction_method"] == "semantic"

    def test_from_dict(self):
        """Bundle can be created from dict."""
        d = {
            "recovery_checkpoint_id": "recovery-id",
            "substantive_checkpoint_id": "substantive-id",
            "knowledge_ids": ["k1", "k2"],
            "failure_ids": ["f1"],
            "created_at": "2026-01-22T10:00:00+00:00",
            "extraction_method": "semantic",
        }

        bundle = ContinuityBundle.from_dict(d)

        assert bundle.recovery_checkpoint_id == "recovery-id"
        assert bundle.substantive_checkpoint_id == "substantive-id"
        assert bundle.knowledge_ids == ("k1", "k2")  # List becomes tuple
        assert bundle.failure_ids == ("f1",)

    def test_from_dict_with_missing_fields(self):
        """Bundle handles missing fields in dict."""
        d = {"recovery_checkpoint_id": "recovery-id"}

        bundle = ContinuityBundle.from_dict(d)

        assert bundle.recovery_checkpoint_id == "recovery-id"
        assert bundle.substantive_checkpoint_id is None
        assert bundle.knowledge_ids == ()
        assert bundle.failure_ids == ()

    def test_roundtrip(self):
        """Bundle survives dict roundtrip."""
        original = ContinuityBundle(
            recovery_checkpoint_id="recovery-id",
            substantive_checkpoint_id="substantive-id",
            knowledge_ids=("k1", "k2"),
            failure_ids=("f1",),
            created_at="2026-01-22T10:00:00+00:00",
            extraction_method="keyword",
        )

        restored = ContinuityBundle.from_dict(original.to_dict())

        assert restored.recovery_checkpoint_id == original.recovery_checkpoint_id
        assert restored.substantive_checkpoint_id == original.substantive_checkpoint_id
        assert restored.knowledge_ids == original.knowledge_ids
        assert restored.failure_ids == original.failure_ids
        assert restored.extraction_method == original.extraction_method

    def test_json_serialization(self):
        """Bundle dict can be JSON serialized."""
        bundle = ContinuityBundle(
            recovery_checkpoint_id="recovery-id",
            knowledge_ids=("k1",),
        )

        # Should not raise
        json_str = json.dumps(bundle.to_dict())
        restored = ContinuityBundle.from_dict(json.loads(json_str))

        assert restored.recovery_checkpoint_id == "recovery-id"


class TestMarkForContinuityWithBundle:
    """Tests for mark_for_continuity_with_bundle function."""

    def test_creates_marker_with_bundle(self, cleanup_continuity):
        """Creates marker containing bundle."""
        bundle = ContinuityBundle(
            recovery_checkpoint_id="recovery-test",
            substantive_checkpoint_id="substantive-test",
            knowledge_ids=("k1",),
            failure_ids=(),
            created_at="2026-01-22T10:00:00+00:00",
            extraction_method="semantic",
        )

        result = mark_for_continuity_with_bundle(
            bundle=bundle,
            reason="post_compaction",
            compaction_summary="Test summary",
        )

        assert result.ok
        marker = get_continuity_marker()
        assert marker is not None
        assert "bundle" in marker
        assert marker["bundle"]["recovery_checkpoint_id"] == "recovery-test"
        assert marker["bundle"]["substantive_checkpoint_id"] == "substantive-test"
        assert marker["bundle"]["knowledge_ids"] == ["k1"]

    def test_includes_compaction_summary(self, cleanup_continuity):
        """Marker includes compaction summary."""
        bundle = ContinuityBundle(recovery_checkpoint_id="test")

        mark_for_continuity_with_bundle(
            bundle=bundle,
            compaction_summary="User was working on tests",
        )

        marker = get_continuity_marker()
        assert marker["compaction_summary"] == "User was working on tests"

    def test_includes_reason(self, cleanup_continuity):
        """Marker includes reason."""
        bundle = ContinuityBundle()

        mark_for_continuity_with_bundle(bundle=bundle, reason="test_reason")

        marker = get_continuity_marker()
        assert marker["reason"] == "test_reason"


class TestGetContinuityBundle:
    """Tests for get_continuity_bundle function."""

    def test_returns_none_when_no_marker(self, cleanup_continuity):
        """Returns None when no marker exists."""
        if CONTINUITY_FILE.exists():
            CONTINUITY_FILE.unlink()

        result = get_continuity_bundle()
        assert result is None

    def test_returns_bundle_from_new_format(self, cleanup_continuity):
        """Returns bundle from new format marker."""
        bundle = ContinuityBundle(
            recovery_checkpoint_id="recovery-id",
            substantive_checkpoint_id="substantive-id",
            knowledge_ids=("k1", "k2"),
        )
        mark_for_continuity_with_bundle(bundle=bundle)

        result = get_continuity_bundle()

        assert result is not None
        assert result.recovery_checkpoint_id == "recovery-id"
        assert result.substantive_checkpoint_id == "substantive-id"
        assert result.knowledge_ids == ("k1", "k2")

    def test_backward_compatibility_legacy_format(self, cleanup_continuity):
        """Returns bundle from legacy checkpoint_id-only format."""
        # Create legacy format marker manually
        CONTINUITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        legacy_marker = {
            "checkpoint_id": "legacy-checkpoint",
            "marked_at": "2026-01-22T10:00:00+00:00",
            "reason": "post_compaction",
        }
        CONTINUITY_FILE.write_text(json.dumps(legacy_marker))

        result = get_continuity_bundle()

        assert result is not None
        assert result.recovery_checkpoint_id == "legacy-checkpoint"
        assert result.substantive_checkpoint_id is None
        assert result.knowledge_ids == ()
        assert result.extraction_method == "legacy"

    def test_returns_none_for_empty_marker(self, cleanup_continuity):
        """Returns None when marker has no checkpoint info."""
        CONTINUITY_FILE.parent.mkdir(parents=True, exist_ok=True)
        empty_marker = {"reason": "test"}
        CONTINUITY_FILE.write_text(json.dumps(empty_marker))

        result = get_continuity_bundle()
        assert result is None


class TestFindMostRecentSubstantiveCheckpoint:
    """Tests for _find_most_recent_substantive_checkpoint."""

    def test_skips_recovery_checkpoints(self, temp_sage_dir):
        """Skips checkpoints with '_recovery-' in ID."""
        # Create a mock list_checkpoints that returns both types
        mock_checkpoints = [
            MagicMock(id="2026-01-22_recovery-test", confidence=0.0),
            MagicMock(id="2026-01-22_real-checkpoint", confidence=0.8),
        ]

        with patch("sage.checkpoint.list_checkpoints", return_value=mock_checkpoints):
            result = _find_most_recent_substantive_checkpoint()

        assert result == "2026-01-22_real-checkpoint"

    def test_skips_zero_confidence(self, temp_sage_dir):
        """Skips checkpoints with 0% confidence."""
        mock_checkpoints = [
            MagicMock(id="2026-01-22_zero-confidence", confidence=0.0),
            MagicMock(id="2026-01-22_has-confidence", confidence=0.5),
        ]

        with patch("sage.checkpoint.list_checkpoints", return_value=mock_checkpoints):
            result = _find_most_recent_substantive_checkpoint()

        assert result == "2026-01-22_has-confidence"

    def test_skips_excluded_id(self, temp_sage_dir):
        """Skips checkpoint matching exclude_id."""
        mock_checkpoints = [
            MagicMock(id="exclude-me", confidence=0.8),
            MagicMock(id="include-me", confidence=0.6),
        ]

        with patch("sage.checkpoint.list_checkpoints", return_value=mock_checkpoints):
            result = _find_most_recent_substantive_checkpoint(exclude_id="exclude-me")

        assert result == "include-me"

    def test_returns_none_when_all_filtered(self, temp_sage_dir):
        """Returns None when all checkpoints are filtered out."""
        mock_checkpoints = [
            MagicMock(id="2026-01-22_recovery-test", confidence=0.0),
        ]

        with patch("sage.checkpoint.list_checkpoints", return_value=mock_checkpoints):
            result = _find_most_recent_substantive_checkpoint()

        assert result is None


class TestBuildQueryFromCheckpointId:
    """Tests for _build_query_from_checkpoint_id."""

    def test_builds_query_from_structured_checkpoint(self):
        """Builds query from structured checkpoint fields."""
        mock_checkpoint = MagicMock()
        mock_checkpoint.thesis = "Bundle architecture improves continuity"
        mock_checkpoint.core_question = "How to preserve context?"
        mock_checkpoint.open_questions = ["What about failures?", "How to match?"]

        with patch("sage.checkpoint.load_checkpoint", return_value=mock_checkpoint):
            result = _build_query_from_checkpoint_id("test-id", None)

        assert "Bundle architecture" in result
        assert "preserve context" in result
        assert "failures" in result

    def test_builds_query_from_recovery_checkpoint(self):
        """Builds query from recovery checkpoint when structured not found."""
        mock_recovery = MagicMock()
        mock_recovery.topic = "Session continuity"
        mock_recovery.thesis = ""
        mock_recovery.open_threads = ["Fix injection", "Test bundle"]

        with (
            patch("sage.checkpoint.load_checkpoint", return_value=None),
            patch("sage.recovery.load_recovery_checkpoint", return_value=mock_recovery),
        ):
            result = _build_query_from_checkpoint_id("recovery-id", None)

        assert "Session continuity" in result
        assert "Fix injection" in result

    def test_truncates_long_query(self):
        """Truncates query to 500 chars."""
        mock_checkpoint = MagicMock()
        mock_checkpoint.thesis = "A" * 600
        mock_checkpoint.core_question = ""
        mock_checkpoint.open_questions = []

        with patch("sage.checkpoint.load_checkpoint", return_value=mock_checkpoint):
            result = _build_query_from_checkpoint_id("test-id", None)

        assert len(result) <= 500


class TestFindRelatedKnowledge:
    """Tests for _find_related_knowledge."""

    def test_returns_empty_for_empty_query(self):
        """Returns empty list for empty query."""
        result = _find_related_knowledge("", limit=5)
        assert result == []

    def test_returns_knowledge_ids(self):
        """Returns list of knowledge IDs."""
        mock_items = [MagicMock(id="k1"), MagicMock(id="k2")]
        mock_result = MagicMock(items=mock_items)

        with patch("sage.knowledge.recall_knowledge", return_value=mock_result):
            result = _find_related_knowledge("test query", limit=5)

        assert result == ["k1", "k2"]

    def test_handles_recall_failure(self):
        """Returns empty list on recall failure."""
        with patch("sage.knowledge.recall_knowledge", side_effect=Exception("fail")):
            result = _find_related_knowledge("test query", limit=5)

        assert result == []


class TestFindRelevantFailures:
    """Tests for _find_relevant_failures."""

    def test_returns_empty_for_empty_query(self):
        """Returns empty list for empty query."""
        result = _find_relevant_failures("", limit=3)
        assert result == []

    def test_returns_failure_ids(self):
        """Returns list of failure IDs."""
        mock_failures = [MagicMock(id="f1"), MagicMock(id="f2")]

        with patch("sage.failures.recall_failures", return_value=mock_failures):
            result = _find_relevant_failures("test query", limit=3)

        assert result == ["f1", "f2"]


class TestCreateContinuityBundle:
    """Tests for create_continuity_bundle."""

    def test_creates_bundle_with_both_checkpoints(self):
        """Creates bundle with recovery and substantive checkpoints."""
        mock_checkpoint = MagicMock()
        mock_checkpoint.thesis = "Test thesis"
        mock_checkpoint.core_question = "Test question"
        mock_checkpoint.open_questions = []

        with (
            patch(
                "sage.continuity._find_most_recent_substantive_checkpoint",
                return_value="substantive-id",
            ),
            patch("sage.checkpoint.load_checkpoint", return_value=mock_checkpoint),
            patch("sage.recovery.load_recovery_checkpoint", return_value=None),
            patch("sage.continuity._find_related_knowledge", return_value=["k1"]),
            patch("sage.continuity._find_relevant_failures", return_value=["f1"]),
        ):
            bundle = create_continuity_bundle(recovery_checkpoint_id="recovery-id")

        assert bundle.recovery_checkpoint_id == "recovery-id"
        assert bundle.substantive_checkpoint_id == "substantive-id"
        assert bundle.knowledge_ids == ("k1",)
        assert bundle.failure_ids == ("f1",)
        assert bundle.extraction_method == "semantic"

    def test_creates_bundle_with_only_recovery(self):
        """Creates bundle when no substantive checkpoint found."""
        with (
            patch(
                "sage.continuity._find_most_recent_substantive_checkpoint",
                return_value=None,
            ),
            patch("sage.checkpoint.load_checkpoint", return_value=None),
            patch("sage.recovery.load_recovery_checkpoint", return_value=None),
        ):
            bundle = create_continuity_bundle(recovery_checkpoint_id="recovery-id")

        assert bundle.recovery_checkpoint_id == "recovery-id"
        assert bundle.substantive_checkpoint_id is None

    def test_sets_created_at(self):
        """Sets created_at timestamp."""
        with (
            patch(
                "sage.continuity._find_most_recent_substantive_checkpoint",
                return_value=None,
            ),
            patch("sage.checkpoint.load_checkpoint", return_value=None),
            patch("sage.recovery.load_recovery_checkpoint", return_value=None),
        ):
            bundle = create_continuity_bundle(recovery_checkpoint_id="test")

        assert bundle.created_at != ""
        # Should be a valid ISO timestamp
        datetime.fromisoformat(bundle.created_at)


class TestIntegration:
    """Integration tests for bundle flow."""

    def test_full_bundle_flow(self, cleanup_continuity):
        """Test full create -> mark -> get flow."""
        # Create bundle
        bundle = ContinuityBundle(
            recovery_checkpoint_id="recovery-test",
            substantive_checkpoint_id="substantive-test",
            knowledge_ids=("k1", "k2"),
            failure_ids=("f1",),
            created_at=datetime.now(UTC).isoformat(),
            extraction_method="semantic",
        )

        # Mark with bundle
        result = mark_for_continuity_with_bundle(
            bundle=bundle,
            reason="post_compaction",
            compaction_summary="Test integration",
        )
        assert result.ok

        # Get bundle back
        restored = get_continuity_bundle()
        assert restored is not None
        assert restored.recovery_checkpoint_id == "recovery-test"
        assert restored.substantive_checkpoint_id == "substantive-test"
        assert restored.knowledge_ids == ("k1", "k2")
        assert restored.failure_ids == ("f1",)

        # Clear and verify gone
        clear_continuity()
        assert get_continuity_bundle() is None

    def test_marker_format_is_correct(self, cleanup_continuity):
        """Verify marker JSON format matches spec."""
        bundle = ContinuityBundle(
            recovery_checkpoint_id="2026-02-16T15-01-16_recovery-test",
            substantive_checkpoint_id="2026-02-16T15-00-58_updated-website",
            knowledge_ids=("session-continuity", "sage-architecture"),
            failure_ids=(),
            created_at="2026-02-16T15:01:16+00:00",
            extraction_method="semantic",
        )

        mark_for_continuity_with_bundle(
            bundle=bundle,
            reason="post_compaction",
            compaction_summary="Test summary",
        )

        # Read raw JSON
        content = CONTINUITY_FILE.read_text()
        data = json.loads(content)

        # Verify structure
        assert "bundle" in data
        assert data["bundle"]["recovery_checkpoint_id"] == "2026-02-16T15-01-16_recovery-test"
        assert data["bundle"]["substantive_checkpoint_id"] == "2026-02-16T15-00-58_updated-website"
        assert data["bundle"]["knowledge_ids"] == ["session-continuity", "sage-architecture"]
        assert data["bundle"]["failure_ids"] == []
        assert data["reason"] == "post_compaction"
        assert "marked_at" in data
