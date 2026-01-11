"""Tests for sage.checkpoint module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.checkpoint import (
    Checkpoint,
    Contribution,
    Source,
    Tension,
    create_checkpoint_from_dict,
    delete_checkpoint,
    format_checkpoint_for_context,
    generate_checkpoint_id,
    list_checkpoints,
    load_checkpoint,
    save_checkpoint,
)


@pytest.fixture
def mock_checkpoints_dir(tmp_path: Path):
    """Create a temporary checkpoints directory."""
    checkpoints_dir = tmp_path / ".sage" / "checkpoints"
    checkpoints_dir.mkdir(parents=True)
    return checkpoints_dir


@pytest.fixture
def mock_checkpoint_paths(tmp_path: Path, mock_checkpoints_dir: Path):
    """Patch checkpoint paths to use temporary directory."""
    with patch("sage.checkpoint.CHECKPOINTS_DIR", mock_checkpoints_dir), \
         patch("sage.checkpoint.SAGE_DIR", tmp_path / ".sage"):
        yield mock_checkpoints_dir


@pytest.fixture
def sample_checkpoint():
    """Create a sample checkpoint."""
    return Checkpoint(
        id="2026-01-10T23-00-00_gdpr-analysis",
        ts="2026-01-10T23:00:00+00:00",
        trigger="manual",
        core_question="How does GDPR affect our AI training pipeline?",
        thesis="GDPR Article 6 requires explicit consent for AI training on personal data.",
        confidence=0.8,
        open_questions=[
            "Does legitimate interest apply?",
            "What about anonymized data?",
        ],
        sources=[
            Source(
                id="gdpr-article-6",
                type="document",
                take="Legal basis for processing requires consent or legitimate interest",
                relation="supports",
            ),
        ],
        tensions=[
            Tension(
                between=("gdpr-article-6", "internal-legal"),
                nature="Disagree on whether legitimate interest applies to ML training",
                resolution="unresolved",
            ),
        ],
        unique_contributions=[
            Contribution(
                type="discovery",
                content="Found that anonymization threshold is 5+ individuals",
            ),
        ],
        action_goal="Determine if we need consent flow",
        action_type="decision",
    )


class TestGenerateCheckpointId:
    """Tests for generate_checkpoint_id()."""

    def test_includes_timestamp_and_slug(self):
        """ID includes timestamp and slugified description."""
        checkpoint_id = generate_checkpoint_id("GDPR consent analysis")
        
        # Should have timestamp prefix
        assert checkpoint_id.startswith("20")
        # Should have slugified description
        assert "gdpr" in checkpoint_id.lower()
        assert "consent" in checkpoint_id.lower()

    def test_truncates_long_descriptions(self):
        """Long descriptions are truncated."""
        long_desc = "This is a very long description that should be truncated to fit"
        checkpoint_id = generate_checkpoint_id(long_desc)
        
        # Slug portion should be ≤40 chars
        slug = checkpoint_id.split("_", 1)[1] if "_" in checkpoint_id else checkpoint_id
        assert len(slug) <= 40


class TestSaveLoadCheckpoint:
    """Tests for save_checkpoint() and load_checkpoint()."""

    def test_save_and_load_checkpoint(self, mock_checkpoint_paths: Path, sample_checkpoint):
        """save_checkpoint() creates file, load_checkpoint() reads it back."""
        file_path = save_checkpoint(sample_checkpoint)

        assert file_path.exists()
        assert file_path.suffix == ".yaml"

        loaded = load_checkpoint(sample_checkpoint.id)

        assert loaded is not None
        assert loaded.id == sample_checkpoint.id
        assert loaded.thesis == sample_checkpoint.thesis
        assert loaded.confidence == sample_checkpoint.confidence
        assert len(loaded.sources) == 1
        assert loaded.sources[0].id == "gdpr-article-6"
        assert len(loaded.tensions) == 1
        assert loaded.tensions[0].resolution == "unresolved"

    def test_load_nonexistent_returns_none(self, mock_checkpoint_paths: Path):
        """load_checkpoint() returns None for nonexistent ID."""
        result = load_checkpoint("nonexistent-checkpoint")
        assert result is None

    def test_load_partial_match(self, mock_checkpoint_paths: Path, sample_checkpoint):
        """load_checkpoint() supports partial ID matching."""
        save_checkpoint(sample_checkpoint)

        # Should find by partial match
        loaded = load_checkpoint("gdpr-analysis")
        assert loaded is not None
        assert loaded.id == sample_checkpoint.id


class TestListCheckpoints:
    """Tests for list_checkpoints()."""

    def test_list_returns_checkpoints_most_recent_first(self, mock_checkpoint_paths: Path):
        """list_checkpoints() returns checkpoints sorted by recency."""
        # Create multiple checkpoints
        cp1 = Checkpoint(
            id="2026-01-10T10-00-00_first",
            ts="2026-01-10T10:00:00+00:00",
            trigger="manual",
            core_question="Q1",
            thesis="T1",
            confidence=0.5,
        )
        cp2 = Checkpoint(
            id="2026-01-10T20-00-00_second",
            ts="2026-01-10T20:00:00+00:00",
            trigger="synthesis",
            core_question="Q2",
            thesis="T2",
            confidence=0.7,
        )

        save_checkpoint(cp1)
        save_checkpoint(cp2)

        checkpoints = list_checkpoints()

        assert len(checkpoints) == 2
        # Most recent first (alphabetically by filename, which has timestamp prefix)
        assert checkpoints[0].id == cp2.id

    def test_list_respects_limit(self, mock_checkpoint_paths: Path):
        """list_checkpoints() respects limit parameter."""
        for i in range(5):
            cp = Checkpoint(
                id=f"2026-01-10T{10+i:02d}-00-00_cp{i}",
                ts=f"2026-01-10T{10+i:02d}:00:00+00:00",
                trigger="manual",
                core_question=f"Q{i}",
                thesis=f"T{i}",
                confidence=0.5,
            )
            save_checkpoint(cp)

        checkpoints = list_checkpoints(limit=3)
        assert len(checkpoints) == 3


class TestDeleteCheckpoint:
    """Tests for delete_checkpoint()."""

    def test_delete_removes_file(self, mock_checkpoint_paths: Path, sample_checkpoint):
        """delete_checkpoint() removes the checkpoint file."""
        file_path = save_checkpoint(sample_checkpoint)
        assert file_path.exists()

        result = delete_checkpoint(sample_checkpoint.id)

        assert result is True
        assert not file_path.exists()

    def test_delete_nonexistent_returns_false(self, mock_checkpoint_paths: Path):
        """delete_checkpoint() returns False for nonexistent checkpoint."""
        result = delete_checkpoint("nonexistent")
        assert result is False


class TestFormatCheckpointForContext:
    """Tests for format_checkpoint_for_context()."""

    def test_includes_key_sections(self, sample_checkpoint):
        """Formatted context includes all key sections."""
        formatted = format_checkpoint_for_context(sample_checkpoint)

        assert "Research Context" in formatted
        assert "Core Question" in formatted
        assert "Current Thesis" in formatted
        assert "GDPR Article 6" in formatted
        assert "Open Questions" in formatted
        assert "legitimate interest" in formatted.lower()
        assert "Key Sources" in formatted
        assert "[+]" in formatted  # supports indicator
        assert "Unresolved Tensions" in formatted
        assert "Unique Discoveries" in formatted

    def test_shows_confidence(self, sample_checkpoint):
        """Formatted context shows confidence percentage."""
        formatted = format_checkpoint_for_context(sample_checkpoint)
        assert "80%" in formatted


class TestCreateCheckpointFromDict:
    """Tests for create_checkpoint_from_dict()."""

    def test_creates_checkpoint_from_dict(self):
        """create_checkpoint_from_dict() parses dictionary correctly."""
        data = {
            "core_question": "What's the best approach?",
            "thesis": "We should use approach A",
            "confidence": 0.75,
            "open_questions": ["What about edge cases?"],
            "sources": [
                {"id": "doc1", "type": "document", "take": "Supports A", "relation": "supports"}
            ],
        }

        cp = create_checkpoint_from_dict(data, trigger="synthesis")

        assert cp.core_question == "What's the best approach?"
        assert cp.thesis == "We should use approach A"
        assert cp.confidence == 0.75
        assert cp.trigger == "synthesis"
        assert len(cp.sources) == 1
