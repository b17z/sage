"""Tests for sage.checkpoint module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.checkpoint import (
    Checkpoint,
    Contribution,
    Source,
    Tension,
    _checkpoint_to_markdown,
    _markdown_to_checkpoint,
    _parse_contribution_line,
    _parse_source_line,
    _parse_tension_line,
    _validate_checkpoint_schema,
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
        assert file_path.suffix == ".md"

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


class TestCheckpointMarkdownSerialization:
    """Tests for checkpoint markdown serialization/deserialization."""

    def test_checkpoint_to_markdown_includes_frontmatter(self, sample_checkpoint):
        """_checkpoint_to_markdown() generates valid YAML frontmatter."""
        md = _checkpoint_to_markdown(sample_checkpoint)

        assert md.startswith("---\n")
        assert "\n---\n" in md
        assert "id: " in md
        assert "type: checkpoint" in md
        assert "confidence: 0.8" in md

    def test_checkpoint_to_markdown_includes_core_question_as_title(self, sample_checkpoint):
        """_checkpoint_to_markdown() uses core question as H1 title."""
        md = _checkpoint_to_markdown(sample_checkpoint)

        assert "# How does GDPR affect our AI training pipeline?" in md

    def test_checkpoint_to_markdown_includes_thesis_section(self, sample_checkpoint):
        """_checkpoint_to_markdown() includes thesis section."""
        md = _checkpoint_to_markdown(sample_checkpoint)

        assert "## Thesis" in md
        assert "GDPR Article 6 requires explicit consent" in md

    def test_checkpoint_to_markdown_includes_open_questions(self, sample_checkpoint):
        """_checkpoint_to_markdown() includes open questions as list."""
        md = _checkpoint_to_markdown(sample_checkpoint)

        assert "## Open Questions" in md
        assert "- Does legitimate interest apply?" in md

    def test_checkpoint_to_markdown_includes_sources(self, sample_checkpoint):
        """_checkpoint_to_markdown() formats sources correctly."""
        md = _checkpoint_to_markdown(sample_checkpoint)

        assert "## Sources" in md
        assert "**gdpr-article-6**" in md
        assert "(document)" in md
        assert "_supports_" in md

    def test_checkpoint_to_markdown_includes_tensions(self, sample_checkpoint):
        """_checkpoint_to_markdown() formats tensions correctly."""
        md = _checkpoint_to_markdown(sample_checkpoint)

        assert "## Tensions" in md
        assert "**gdpr-article-6** vs **internal-legal**" in md
        assert "_unresolved_" in md

    def test_checkpoint_to_markdown_includes_contributions(self, sample_checkpoint):
        """_checkpoint_to_markdown() formats contributions correctly."""
        md = _checkpoint_to_markdown(sample_checkpoint)

        assert "## Unique Contributions" in md
        assert "**discovery**:" in md

    def test_markdown_roundtrip_preserves_data(self, sample_checkpoint):
        """Checkpoint survives markdown round-trip."""
        md = _checkpoint_to_markdown(sample_checkpoint)
        parsed = _markdown_to_checkpoint(md)

        assert parsed is not None
        assert parsed.id == sample_checkpoint.id
        assert parsed.thesis == sample_checkpoint.thesis
        assert parsed.confidence == sample_checkpoint.confidence
        assert parsed.core_question == sample_checkpoint.core_question
        assert len(parsed.open_questions) == len(sample_checkpoint.open_questions)
        assert len(parsed.sources) == len(sample_checkpoint.sources)
        assert len(parsed.tensions) == len(sample_checkpoint.tensions)
        assert len(parsed.unique_contributions) == len(sample_checkpoint.unique_contributions)

    def test_markdown_roundtrip_preserves_source_details(self, sample_checkpoint):
        """Source details survive markdown round-trip."""
        md = _checkpoint_to_markdown(sample_checkpoint)
        parsed = _markdown_to_checkpoint(md)

        assert parsed.sources[0].id == sample_checkpoint.sources[0].id
        assert parsed.sources[0].type == sample_checkpoint.sources[0].type
        assert parsed.sources[0].relation == sample_checkpoint.sources[0].relation

    def test_markdown_roundtrip_preserves_tension_details(self, sample_checkpoint):
        """Tension details survive markdown round-trip."""
        md = _checkpoint_to_markdown(sample_checkpoint)
        parsed = _markdown_to_checkpoint(md)

        assert parsed.tensions[0].between == sample_checkpoint.tensions[0].between
        assert parsed.tensions[0].resolution == sample_checkpoint.tensions[0].resolution

    def test_markdown_to_checkpoint_handles_empty_sections(self):
        """_markdown_to_checkpoint() handles checkpoints with empty sections."""
        cp = Checkpoint(
            id="test-minimal",
            ts="2026-01-16T12:00:00Z",
            trigger="manual",
            core_question="Minimal checkpoint",
            thesis="Simple thesis",
            confidence=0.5,
        )
        md = _checkpoint_to_markdown(cp)
        parsed = _markdown_to_checkpoint(md)

        assert parsed is not None
        assert parsed.open_questions == []
        assert parsed.sources == []
        assert parsed.tensions == []
        assert parsed.unique_contributions == []

    def test_markdown_to_checkpoint_returns_none_for_invalid(self):
        """_markdown_to_checkpoint() returns None for invalid markdown."""
        assert _markdown_to_checkpoint("not valid markdown") is None
        assert _markdown_to_checkpoint("no frontmatter here") is None
        assert _markdown_to_checkpoint("---\nincomplete") is None


class TestMarkdownParsingHelpers:
    """Tests for markdown line parsing helper functions."""

    def test_parse_source_line_valid(self):
        """_parse_source_line() parses valid source line."""
        line = "- **doc-123** (document): Key insight here — _supports_"
        source = _parse_source_line(line)

        assert source is not None
        assert source.id == "doc-123"
        assert source.type == "document"
        assert source.take == "Key insight here"
        assert source.relation == "supports"

    def test_parse_source_line_without_relation(self):
        """_parse_source_line() handles missing relation."""
        line = "- **doc-123** (api): Just the take"
        source = _parse_source_line(line)

        assert source is not None
        assert source.id == "doc-123"
        assert source.type == "api"
        assert source.take == "Just the take"
        assert source.relation == ""

    def test_parse_source_line_invalid(self):
        """_parse_source_line() returns None for invalid lines."""
        assert _parse_source_line("not a source line") is None
        assert _parse_source_line("- no bold markers") is None
        assert _parse_source_line("- **id** missing parens") is None

    def test_parse_tension_line_valid(self):
        """_parse_tension_line() parses valid tension line."""
        line = "- **source-a** vs **source-b**: They disagree — _unresolved_"
        tension = _parse_tension_line(line)

        assert tension is not None
        assert tension.between == ("source-a", "source-b")
        assert tension.nature == "They disagree"
        assert tension.resolution == "unresolved"

    def test_parse_tension_line_without_resolution(self):
        """_parse_tension_line() handles missing resolution."""
        line = "- **src1** vs **src2**: Just the nature"
        tension = _parse_tension_line(line)

        assert tension is not None
        assert tension.between == ("src1", "src2")
        assert tension.nature == "Just the nature"
        assert tension.resolution == ""

    def test_parse_tension_line_invalid(self):
        """_parse_tension_line() returns None for invalid lines."""
        assert _parse_tension_line("not a tension line") is None
        assert _parse_tension_line("- **only-one** source") is None

    def test_parse_contribution_line_valid(self):
        """_parse_contribution_line() parses valid contribution line."""
        line = "- **insight**: This is the contribution content"
        contrib = _parse_contribution_line(line)

        assert contrib is not None
        assert contrib.type == "insight"
        assert contrib.content == "This is the contribution content"

    def test_parse_contribution_line_invalid(self):
        """_parse_contribution_line() returns None for invalid lines."""
        assert _parse_contribution_line("not a contribution") is None
        assert _parse_contribution_line("- no bold type") is None


class TestCheckpointBackwardCompatibility:
    """Tests for backward compatibility with legacy .yaml format."""

    def test_load_checkpoint_reads_legacy_yaml(self, mock_checkpoint_paths: Path):
        """load_checkpoint() can read legacy .yaml files."""
        import yaml

        # Create a legacy .yaml checkpoint file
        legacy_data = {
            "checkpoint": {
                "id": "legacy-checkpoint",
                "ts": "2026-01-10T12:00:00Z",
                "trigger": "manual",
                "core_question": "Legacy question?",
                "thesis": "Legacy thesis",
                "confidence": 0.7,
                "open_questions": ["Legacy question 1"],
                "sources": [],
                "tensions": [],
                "unique_contributions": [],
                "action": {"goal": "", "type": ""},
                "metadata": {"skill": None, "project": None},
            }
        }

        yaml_path = mock_checkpoint_paths / "legacy-checkpoint.yaml"
        with open(yaml_path, "w") as f:
            yaml.safe_dump(legacy_data, f)

        # Load should work
        loaded = load_checkpoint("legacy-checkpoint")

        assert loaded is not None
        assert loaded.id == "legacy-checkpoint"
        assert loaded.thesis == "Legacy thesis"
        assert loaded.confidence == 0.7

    def test_list_checkpoints_includes_both_formats(self, mock_checkpoint_paths: Path, sample_checkpoint):
        """list_checkpoints() finds both .md and .yaml files."""
        import yaml

        # Save a new .md checkpoint
        save_checkpoint(sample_checkpoint)

        # Create a legacy .yaml checkpoint
        legacy_data = {
            "checkpoint": {
                "id": "legacy-2026-01-09",
                "ts": "2026-01-09T12:00:00Z",
                "trigger": "manual",
                "core_question": "Legacy?",
                "thesis": "Legacy",
                "confidence": 0.5,
                "open_questions": [],
                "sources": [],
                "tensions": [],
                "unique_contributions": [],
                "action": {"goal": "", "type": ""},
                "metadata": {},
            }
        }
        yaml_path = mock_checkpoint_paths / "legacy-2026-01-09.yaml"
        with open(yaml_path, "w") as f:
            yaml.safe_dump(legacy_data, f)

        # List should include both
        checkpoints = list_checkpoints()

        assert len(checkpoints) == 2
        ids = [cp.id for cp in checkpoints]
        assert sample_checkpoint.id in ids
        assert "legacy-2026-01-09" in ids


class TestCheckpointSecurity:
    """Security tests for checkpoint module."""

    def test_schema_validation_rejects_missing_checkpoint_key(self):
        """Schema validation rejects data without 'checkpoint' key."""
        from sage.checkpoint import _validate_checkpoint_schema

        invalid_data = {"not_checkpoint": {"id": "test"}}
        result = _validate_checkpoint_schema(invalid_data)

        assert result is not None
        assert "checkpoint" in result.lower()

    def test_schema_validation_rejects_missing_required_fields(self):
        """Schema validation rejects data with missing required fields."""
        from sage.checkpoint import _validate_checkpoint_schema

        # Missing 'thesis' field
        invalid_data = {
            "checkpoint": {
                "id": "test",
                "ts": "2026-01-01",
                "trigger": "manual",
                "core_question": "test?",
                # "thesis" is missing
                "confidence": 0.8,
            }
        }
        result = _validate_checkpoint_schema(invalid_data)

        assert result is not None
        assert "thesis" in result.lower()

    def test_schema_validation_rejects_invalid_types(self):
        """Schema validation rejects invalid field types."""
        from sage.checkpoint import _validate_checkpoint_schema

        # confidence should be a number, not a string
        invalid_data = {
            "checkpoint": {
                "id": "test",
                "ts": "2026-01-01",
                "trigger": "manual",
                "core_question": "test?",
                "thesis": "test thesis",
                "confidence": "high",  # Should be float
            }
        }
        result = _validate_checkpoint_schema(invalid_data)

        assert result is not None
        assert "confidence" in result.lower()

    def test_schema_validation_accepts_valid_data(self):
        """Schema validation accepts well-formed data."""
        from sage.checkpoint import _validate_checkpoint_schema

        valid_data = {
            "checkpoint": {
                "id": "test",
                "ts": "2026-01-01T12:00:00Z",
                "trigger": "manual",
                "core_question": "What is the answer?",
                "thesis": "The answer is 42.",
                "confidence": 0.95,
            }
        }
        result = _validate_checkpoint_schema(valid_data)

        assert result is None

    def test_malformed_yaml_skipped_gracefully(self, mock_checkpoint_paths: Path):
        """Malformed YAML files are skipped without crashing."""
        # Create a valid checkpoint
        valid_cp = Checkpoint(
            id="valid-checkpoint",
            ts="2026-01-10T12:00:00Z",
            trigger="manual",
            core_question="Valid?",
            thesis="Yes, valid.",
            confidence=0.9,
        )
        save_checkpoint(valid_cp)

        # Create a malformed YAML file
        malformed_path = mock_checkpoint_paths / "malformed-2026-01-09.yaml"
        malformed_path.write_text("this: is: not: valid: yaml: {{{{")

        # list_checkpoints should not crash, just skip the malformed file
        checkpoints = list_checkpoints()

        assert len(checkpoints) == 1
        assert checkpoints[0].id == "valid-checkpoint"

    def test_checkpoint_file_permissions(self, mock_checkpoint_paths: Path):
        """Checkpoint files are created with restricted permissions."""
        import stat

        cp = Checkpoint(
            id="perm-test-checkpoint",
            ts="2026-01-10T12:00:00Z",
            trigger="manual",
            core_question="Permissions?",
            thesis="Should be restricted.",
            confidence=0.8,
        )
        file_path = save_checkpoint(cp)

        mode = file_path.stat().st_mode

        # Should be owner read/write only (0o600)
        assert mode & stat.S_IRWXU == stat.S_IRUSR | stat.S_IWUSR  # Owner: rw
        assert mode & stat.S_IRWXG == 0  # Group: none
        assert mode & stat.S_IRWXO == 0  # Other: none
