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
    with (
        patch("sage.checkpoint.CHECKPOINTS_DIR", mock_checkpoints_dir),
        patch("sage.checkpoint.SAGE_DIR", tmp_path / ".sage"),
    ):
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
        """Formatted context includes all key sections (markdown format)."""
        formatted = format_checkpoint_for_context(sample_checkpoint, use_toon=False)

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

    def test_list_checkpoints_includes_both_formats(
        self, mock_checkpoint_paths: Path, sample_checkpoint
    ):
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

        invalid_data = {"not_checkpoint": {"id": "test"}}
        result = _validate_checkpoint_schema(invalid_data)

        assert result is not None
        assert "checkpoint" in result.lower()

    def test_schema_validation_rejects_missing_required_fields(self):
        """Schema validation rejects data with missing required fields."""

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


class TestContextHydration:
    """Tests for context hydration fields (key_evidence, reasoning_trace)."""

    @pytest.fixture
    def checkpoint_with_hydration(self):
        """Create a checkpoint with context hydration fields."""
        return Checkpoint(
            id="2026-01-18T12-00-00_hydration-test",
            ts="2026-01-18T12:00:00+00:00",
            trigger="synthesis",
            core_question="What is the best payment processor for crypto?",
            thesis="Stripe offers the best balance of features and compliance for crypto payments.",
            confidence=0.75,
            key_evidence=[
                "Stripe supports 135+ currencies including USDC",
                "Stripe Connect enables marketplace payouts",
                "Competitor analysis: Square lacks international support",
            ],
            reasoning_trace=(
                "Started by evaluating major processors: Stripe, Square, PayPal, Adyen. "
                "Eliminated PayPal due to crypto policy restrictions. "
                "Square lacks the international coverage needed. "
                "Adyen requires higher volume minimums. "
                "Stripe emerged as the clear winner after considering compliance, "
                "feature set, and integration complexity."
            ),
            open_questions=["What about emerging processors?"],
        )

    def test_key_evidence_serialized_to_markdown(self, checkpoint_with_hydration):
        """key_evidence is serialized as bullet list in markdown."""
        md = _checkpoint_to_markdown(checkpoint_with_hydration)

        assert "## Key Evidence" in md
        assert "- Stripe supports 135+ currencies including USDC" in md
        assert "- Stripe Connect enables marketplace payouts" in md
        assert "- Competitor analysis: Square lacks international support" in md

    def test_reasoning_trace_serialized_to_markdown(self, checkpoint_with_hydration):
        """reasoning_trace is serialized as paragraph in markdown."""
        md = _checkpoint_to_markdown(checkpoint_with_hydration)

        assert "## Reasoning Trace" in md
        assert "Started by evaluating major processors" in md
        assert "Stripe emerged as the clear winner" in md

    def test_key_evidence_roundtrip(self, checkpoint_with_hydration):
        """key_evidence survives markdown round-trip."""
        md = _checkpoint_to_markdown(checkpoint_with_hydration)
        parsed = _markdown_to_checkpoint(md)

        assert parsed is not None
        assert len(parsed.key_evidence) == 3
        assert "Stripe supports 135+ currencies including USDC" in parsed.key_evidence
        assert "Stripe Connect enables marketplace payouts" in parsed.key_evidence

    def test_reasoning_trace_roundtrip(self, checkpoint_with_hydration):
        """reasoning_trace survives markdown round-trip."""
        md = _checkpoint_to_markdown(checkpoint_with_hydration)
        parsed = _markdown_to_checkpoint(md)

        assert parsed is not None
        assert "Started by evaluating major processors" in parsed.reasoning_trace
        assert "Stripe emerged as the clear winner" in parsed.reasoning_trace

    def test_empty_hydration_fields_omitted(self):
        """Empty key_evidence and reasoning_trace are not in markdown."""
        cp = Checkpoint(
            id="test-no-hydration",
            ts="2026-01-18T12:00:00Z",
            trigger="manual",
            core_question="Minimal checkpoint",
            thesis="Simple thesis without hydration fields",
            confidence=0.5,
            key_evidence=[],
            reasoning_trace="",
        )
        md = _checkpoint_to_markdown(cp)

        assert "## Key Evidence" not in md
        assert "## Reasoning Trace" not in md

    def test_empty_hydration_fields_default(self):
        """Checkpoints without hydration fields get empty defaults."""
        md = """---
id: test-legacy
type: checkpoint
ts: "2026-01-18T12:00:00Z"
trigger: manual
confidence: 0.5
---

# Legacy question?

## Thesis
Legacy thesis without new fields.
"""
        parsed = _markdown_to_checkpoint(md)

        assert parsed is not None
        assert parsed.key_evidence == []
        assert parsed.reasoning_trace == ""

    def test_format_checkpoint_includes_key_evidence(self, checkpoint_with_hydration):
        """format_checkpoint_for_context includes key_evidence (markdown format)."""
        formatted = format_checkpoint_for_context(checkpoint_with_hydration, use_toon=False)

        assert "## Key Evidence" in formatted
        assert "- Stripe supports 135+ currencies including USDC" in formatted

    def test_format_checkpoint_includes_reasoning_trace(self, checkpoint_with_hydration):
        """format_checkpoint_for_context includes reasoning_trace (markdown format)."""
        formatted = format_checkpoint_for_context(checkpoint_with_hydration, use_toon=False)

        assert "## Reasoning Trace" in formatted
        assert "Started by evaluating major processors" in formatted

    def test_create_checkpoint_from_dict_with_hydration(self):
        """create_checkpoint_from_dict handles hydration fields."""
        data = {
            "core_question": "What's the approach?",
            "thesis": "Use approach A",
            "confidence": 0.8,
            "key_evidence": [
                "Evidence point 1",
                "Evidence point 2",
            ],
            "reasoning_trace": "We compared A and B, then chose A because...",
        }

        cp = create_checkpoint_from_dict(data, trigger="synthesis")

        assert len(cp.key_evidence) == 2
        assert "Evidence point 1" in cp.key_evidence
        assert "We compared A and B" in cp.reasoning_trace

    def test_save_load_preserves_hydration(self, mock_checkpoint_paths, checkpoint_with_hydration):
        """save_checkpoint and load_checkpoint preserve hydration fields."""
        save_checkpoint(checkpoint_with_hydration)

        loaded = load_checkpoint(checkpoint_with_hydration.id)

        assert loaded is not None
        assert len(loaded.key_evidence) == 3
        assert loaded.reasoning_trace == checkpoint_with_hydration.reasoning_trace


class TestDepthMetadata:
    """Tests for depth metadata fields (message_count, token_estimate)."""

    def test_depth_fields_in_frontmatter(self, mock_checkpoint_paths):
        """message_count and token_estimate are stored in frontmatter."""
        cp = Checkpoint(
            id="2026-01-18T12-00-00_depth-test",
            ts="2026-01-18T12:00:00Z",
            trigger="synthesis",
            core_question="Depth test?",
            thesis="Testing depth fields",
            confidence=0.7,
            message_count=15,
            token_estimate=5000,
        )
        md = _checkpoint_to_markdown(cp)

        assert "message_count: 15" in md
        assert "token_estimate: 5000" in md

    def test_depth_fields_roundtrip(self, mock_checkpoint_paths):
        """Depth metadata fields survive markdown round-trip."""
        cp = Checkpoint(
            id="2026-01-18T12-00-00_depth-roundtrip",
            ts="2026-01-18T12:00:00Z",
            trigger="synthesis",
            core_question="Depth roundtrip?",
            thesis="Testing depth roundtrip",
            confidence=0.7,
            message_count=20,
            token_estimate=8000,
        )
        md = _checkpoint_to_markdown(cp)
        parsed = _markdown_to_checkpoint(md)

        assert parsed is not None
        assert parsed.message_count == 20
        assert parsed.token_estimate == 8000

    def test_depth_fields_default_to_zero(self):
        """Depth metadata fields default to 0 if not present."""
        md = """---
id: test-no-depth
type: checkpoint
ts: "2026-01-18T12:00:00Z"
trigger: manual
confidence: 0.5
---

# No depth metadata?

## Thesis
Checkpoint without depth fields.
"""
        parsed = _markdown_to_checkpoint(md)

        assert parsed is not None
        assert parsed.message_count == 0
        assert parsed.token_estimate == 0


class TestCheckpointMaintenance:
    """Tests for checkpoint maintenance (pruning and capping)."""

    @pytest.fixture
    def maintenance_paths(self, tmp_path: Path):
        """Set up paths for maintenance testing."""
        checkpoints_dir = tmp_path / ".sage" / "checkpoints"
        checkpoints_dir.mkdir(parents=True)

        with (
            patch("sage.checkpoint.CHECKPOINTS_DIR", checkpoints_dir),
            patch("sage.checkpoint.SAGE_DIR", tmp_path / ".sage"),
            patch("sage.checkpoint._add_checkpoint_embedding", return_value=True),
            patch("sage.checkpoint._remove_checkpoint_embedding", return_value=True),
        ):
            yield checkpoints_dir

    def test_maintenance_prunes_old_checkpoints(self, maintenance_paths: Path):
        """run_checkpoint_maintenance() prunes checkpoints older than max_age_days."""
        import os
        import time

        from sage.checkpoint import (
            Checkpoint,
            run_checkpoint_maintenance,
            save_checkpoint,
        )

        # Create some checkpoints
        for i in range(3):
            cp = Checkpoint(
                id=f"2026-01-{10+i:02d}T12-00-00_test-{i}",
                ts=f"2026-01-{10+i:02d}T12:00:00Z",
                trigger="manual",
                core_question=f"Q{i}",
                thesis=f"T{i}",
                confidence=0.5,
            )
            save_checkpoint(cp)

        # Make one file appear old (backdate mtime)
        old_file = maintenance_paths / "2026-01-10T12-00-00_test-0.md"
        old_time = time.time() - (100 * 24 * 3600)  # 100 days ago
        os.utime(old_file, (old_time, old_time))

        # Run maintenance with max_age=90 days
        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 90
            mock_cfg.return_value.checkpoint_max_count = 0
            mock_cfg.return_value.maintenance_on_save = False

            result = run_checkpoint_maintenance(max_age_days=90, max_count=0)

        assert result.pruned_by_age == 1
        assert result.total_remaining == 2
        assert not old_file.exists()

    def test_maintenance_respects_max_age_zero(self, maintenance_paths: Path):
        """run_checkpoint_maintenance() skips age pruning when max_age_days=0."""
        import os
        import time

        from sage.checkpoint import (
            Checkpoint,
            run_checkpoint_maintenance,
            save_checkpoint,
        )

        # Create a checkpoint
        cp = Checkpoint(
            id="2026-01-10T12-00-00_test",
            ts="2026-01-10T12:00:00Z",
            trigger="manual",
            core_question="Q",
            thesis="T",
            confidence=0.5,
        )
        save_checkpoint(cp)

        # Make file very old
        old_file = maintenance_paths / "2026-01-10T12-00-00_test.md"
        old_time = time.time() - (365 * 24 * 3600)  # 1 year ago
        os.utime(old_file, (old_time, old_time))

        # Run with max_age=0 (disabled)
        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 0
            mock_cfg.return_value.checkpoint_max_count = 0
            mock_cfg.return_value.maintenance_on_save = False

            result = run_checkpoint_maintenance(max_age_days=0, max_count=0)

        assert result.pruned_by_age == 0
        assert old_file.exists()

    def test_maintenance_caps_to_max_count(self, maintenance_paths: Path):
        """run_checkpoint_maintenance() caps checkpoints to max_count."""
        from sage.checkpoint import (
            Checkpoint,
            run_checkpoint_maintenance,
            save_checkpoint,
        )

        # Create 5 checkpoints
        for i in range(5):
            cp = Checkpoint(
                id=f"2026-01-{10+i:02d}T12-00-00_test-{i}",
                ts=f"2026-01-{10+i:02d}T12:00:00Z",
                trigger="manual",
                core_question=f"Q{i}",
                thesis=f"T{i}",
                confidence=0.5,
            )
            save_checkpoint(cp)

        # Cap to 3
        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 0
            mock_cfg.return_value.checkpoint_max_count = 3
            mock_cfg.return_value.maintenance_on_save = False

            result = run_checkpoint_maintenance(max_age_days=0, max_count=3)

        assert result.pruned_by_cap == 2
        assert result.total_remaining == 3

    def test_maintenance_respects_max_count_zero(self, maintenance_paths: Path):
        """run_checkpoint_maintenance() skips capping when max_count=0."""
        from sage.checkpoint import (
            Checkpoint,
            run_checkpoint_maintenance,
            save_checkpoint,
        )

        # Create many checkpoints
        for i in range(10):
            cp = Checkpoint(
                id=f"2026-01-{10+i:02d}T12-00-00_test-{i}",
                ts=f"2026-01-{10+i:02d}T12:00:00Z",
                trigger="manual",
                core_question=f"Q{i}",
                thesis=f"T{i}",
                confidence=0.5,
            )
            save_checkpoint(cp)

        # max_count=0 means unlimited
        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 0
            mock_cfg.return_value.checkpoint_max_count = 0
            mock_cfg.return_value.maintenance_on_save = False

            result = run_checkpoint_maintenance(max_age_days=0, max_count=0)

        assert result.pruned_by_cap == 0
        assert result.total_remaining == 10

    def test_maintenance_preserves_recent_checkpoints(self, maintenance_paths: Path):
        """run_checkpoint_maintenance() preserves most recent checkpoints when capping."""
        import time

        from sage.checkpoint import (
            Checkpoint,
            run_checkpoint_maintenance,
            save_checkpoint,
        )

        # Create checkpoints with slight time gaps
        for i in range(5):
            cp = Checkpoint(
                id=f"2026-01-{10+i:02d}T12-00-00_test-{i}",
                ts=f"2026-01-{10+i:02d}T12:00:00Z",
                trigger="manual",
                core_question=f"Q{i}",
                thesis=f"T{i}",
                confidence=0.5,
            )
            save_checkpoint(cp)
            time.sleep(0.01)  # Ensure different mtime

        # Cap to 2 - should keep the two newest
        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 0
            mock_cfg.return_value.checkpoint_max_count = 2
            mock_cfg.return_value.maintenance_on_save = False

            result = run_checkpoint_maintenance(max_age_days=0, max_count=2)

        assert result.total_remaining == 2

        # Newest files should remain
        remaining_files = list(maintenance_paths.glob("*.md"))
        assert len(remaining_files) == 2

        # Should have the two most recent (highest numbered)
        remaining_ids = {f.stem for f in remaining_files}
        assert "2026-01-14T12-00-00_test-4" in remaining_ids
        assert "2026-01-13T12-00-00_test-3" in remaining_ids

    def test_maintenance_returns_correct_counts(self, maintenance_paths: Path):
        """run_checkpoint_maintenance() returns correct MaintenanceResult."""
        from sage.checkpoint import (
            MaintenanceResult,
            run_checkpoint_maintenance,
        )

        # No checkpoints
        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 0
            mock_cfg.return_value.checkpoint_max_count = 0
            mock_cfg.return_value.maintenance_on_save = False

            result = run_checkpoint_maintenance()

        assert isinstance(result, MaintenanceResult)
        assert result.pruned_by_age == 0
        assert result.pruned_by_cap == 0
        assert result.total_remaining == 0

    def test_maintenance_handles_empty_directory(self, maintenance_paths: Path):
        """run_checkpoint_maintenance() handles empty directory gracefully."""
        from sage.checkpoint import run_checkpoint_maintenance

        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 30
            mock_cfg.return_value.checkpoint_max_count = 10
            mock_cfg.return_value.maintenance_on_save = False

            result = run_checkpoint_maintenance()

        assert result.pruned_by_age == 0
        assert result.pruned_by_cap == 0
        assert result.total_remaining == 0

    def test_maintenance_handles_corrupted_files(self, maintenance_paths: Path):
        """run_checkpoint_maintenance() handles corrupted files gracefully."""
        from sage.checkpoint import (
            Checkpoint,
            run_checkpoint_maintenance,
            save_checkpoint,
        )

        # Create a valid checkpoint
        cp = Checkpoint(
            id="valid-checkpoint",
            ts="2026-01-10T12:00:00Z",
            trigger="manual",
            core_question="Q",
            thesis="T",
            confidence=0.5,
        )
        save_checkpoint(cp)

        # Create a corrupted file
        corrupted = maintenance_paths / "corrupted.md"
        corrupted.write_text("not valid yaml frontmatter")

        # Maintenance should still work (counts files, not content)
        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 0
            mock_cfg.return_value.checkpoint_max_count = 0
            mock_cfg.return_value.maintenance_on_save = False

            result = run_checkpoint_maintenance()

        # Both files should be counted
        assert result.total_remaining == 2

    def test_save_checkpoint_triggers_maintenance(self, maintenance_paths: Path):
        """save_checkpoint() triggers maintenance when enabled."""
        from sage.checkpoint import (
            Checkpoint,
            save_checkpoint,
        )

        # Create initial checkpoints
        for i in range(5):
            with patch("sage.checkpoint.get_sage_config") as mock_cfg:
                mock_cfg.return_value.checkpoint_max_age_days = 0
                mock_cfg.return_value.checkpoint_max_count = 0
                mock_cfg.return_value.maintenance_on_save = False

                cp = Checkpoint(
                    id=f"2026-01-{10+i:02d}T12-00-00_init-{i}",
                    ts=f"2026-01-{10+i:02d}T12:00:00Z",
                    trigger="manual",
                    core_question=f"Q{i}",
                    thesis=f"T{i}",
                    confidence=0.5,
                )
                save_checkpoint(cp)

        # Now save with maintenance enabled and max_count=3
        with patch("sage.checkpoint.get_sage_config") as mock_cfg:
            mock_cfg.return_value.checkpoint_max_age_days = 0
            mock_cfg.return_value.checkpoint_max_count = 3
            mock_cfg.return_value.maintenance_on_save = True

            cp = Checkpoint(
                id="2026-01-20T12-00-00_trigger",
                ts="2026-01-20T12:00:00Z",
                trigger="manual",
                core_question="Q",
                thesis="T",
                confidence=0.5,
            )
            save_checkpoint(cp)

        # Should have capped to 3
        remaining = list(maintenance_paths.glob("*.md"))
        assert len(remaining) == 3


# =============================================================================
# Code Context Tests (v1.3)
# =============================================================================


class TestCodeRef:
    """Tests for CodeRef dataclass."""

    def test_code_ref_is_frozen(self):
        """CodeRef is immutable."""
        from sage.checkpoint import CodeRef

        ref = CodeRef(file="/path/to/file.py")
        with pytest.raises(AttributeError):
            ref.file = "/other/file.py"

    def test_code_ref_with_all_fields(self):
        """CodeRef stores all fields correctly."""
        from sage.checkpoint import CodeRef

        ref = CodeRef(
            file="/path/to/file.py",
            lines=(10, 50),
            chunk_id="abc123",
            snippet="def foo(): pass",
            relevance="supports",
        )
        assert ref.file == "/path/to/file.py"
        assert ref.lines == (10, 50)
        assert ref.chunk_id == "abc123"
        assert ref.snippet == "def foo(): pass"
        assert ref.relevance == "supports"

    def test_code_ref_default_values(self):
        """CodeRef has sensible defaults."""
        from sage.checkpoint import CodeRef

        ref = CodeRef(file="/path/to/file.py")
        assert ref.lines is None
        assert ref.chunk_id is None
        assert ref.snippet is None
        assert ref.relevance == "context"


class TestCheckpointCodeContext:
    """Tests for checkpoint code context fields."""

    def test_checkpoint_with_code_context(self):
        """Checkpoint stores code context fields."""
        cp = Checkpoint(
            id="test-code-ctx",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            files_explored=frozenset(["/a.py", "/b.py"]),
            files_changed=frozenset(["/c.py"]),
        )
        assert cp.files_explored == frozenset(["/a.py", "/b.py"])
        assert cp.files_changed == frozenset(["/c.py"])

    def test_checkpoint_code_context_default_empty(self):
        """Checkpoint code context defaults to empty."""
        cp = Checkpoint(
            id="test-no-ctx",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
        )
        assert cp.files_explored == frozenset()
        assert cp.files_changed == frozenset()
        assert cp.code_refs == ()

    def test_checkpoint_with_code_refs(self):
        """Checkpoint stores code refs."""
        from sage.checkpoint import CodeRef

        cp = Checkpoint(
            id="test-code-refs",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            code_refs=(
                CodeRef(file="/a.py", relevance="supports"),
                CodeRef(file="/b.py", lines=(10, 20), relevance="context"),
            ),
        )
        assert len(cp.code_refs) == 2
        assert cp.code_refs[0].file == "/a.py"
        assert cp.code_refs[1].lines == (10, 20)


class TestCheckpointCodeContextSerialization:
    """Tests for checkpoint code context markdown serialization."""

    def test_files_explored_in_frontmatter(self):
        """files_explored is serialized to frontmatter."""
        cp = Checkpoint(
            id="test-files-explored",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            files_explored=frozenset(["/a.py", "/b.py"]),
        )
        md = _checkpoint_to_markdown(cp)

        assert "files_explored:" in md
        assert "/a.py" in md
        assert "/b.py" in md

    def test_files_changed_in_frontmatter(self):
        """files_changed is serialized to frontmatter."""
        cp = Checkpoint(
            id="test-files-changed",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            files_changed=frozenset(["/c.py"]),
        )
        md = _checkpoint_to_markdown(cp)

        assert "files_changed:" in md
        assert "/c.py" in md

    def test_code_refs_in_body(self):
        """code_refs are serialized to markdown body."""
        from sage.checkpoint import CodeRef

        cp = Checkpoint(
            id="test-code-refs-body",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            code_refs=(
                CodeRef(file="/a.py", relevance="supports"),
                CodeRef(file="/b.py", lines=(10, 20), relevance="context"),
            ),
        )
        md = _checkpoint_to_markdown(cp)

        assert "## Code References" in md
        assert "[+] `/a.py`" in md
        assert "[~] `/b.py:10-20`" in md

    def test_code_context_roundtrip(self, mock_checkpoint_paths):
        """Code context survives save/load roundtrip."""
        cp = Checkpoint(
            id="test-roundtrip-ctx",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            files_explored=frozenset(["/a.py", "/b.py"]),
            files_changed=frozenset(["/c.py"]),
        )
        save_checkpoint(cp)

        loaded = load_checkpoint(cp.id)

        assert loaded is not None
        assert loaded.files_explored == frozenset(["/a.py", "/b.py"])
        assert loaded.files_changed == frozenset(["/c.py"])

    def test_empty_code_context_omitted(self):
        """Empty code context fields are not in markdown."""
        cp = Checkpoint(
            id="test-no-ctx",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
        )
        md = _checkpoint_to_markdown(cp)

        assert "files_explored:" not in md
        assert "files_changed:" not in md
        assert "## Code References" not in md


class TestFormatCheckpointCodeContext:
    """Tests for format_checkpoint_for_context with code context."""

    def test_format_includes_code_refs(self):
        """format_checkpoint_for_context includes code refs (markdown format)."""
        from sage.checkpoint import CodeRef

        cp = Checkpoint(
            id="test-fmt-refs",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            code_refs=(
                CodeRef(file="/auth.py", relevance="supports"),
            ),
        )
        formatted = format_checkpoint_for_context(cp, use_toon=False)

        assert "## Code References" in formatted
        assert "[+] `/auth.py`" in formatted

    def test_format_includes_files_changed(self):
        """format_checkpoint_for_context includes files changed (markdown format)."""
        cp = Checkpoint(
            id="test-fmt-changed",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            files_changed=frozenset(["/edited.py", "/written.py"]),
        )
        formatted = format_checkpoint_for_context(cp, use_toon=False)

        assert "## Files Changed" in formatted
        assert "`/edited.py`" in formatted
        assert "`/written.py`" in formatted

    def test_format_files_explored_shown_when_no_changes(self):
        """format_checkpoint_for_context shows files explored when no changes (markdown format)."""
        cp = Checkpoint(
            id="test-fmt-explored",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            files_explored=frozenset(["/a.py", "/b.py"]),
            files_changed=frozenset(),  # No changes
        )
        formatted = format_checkpoint_for_context(cp, use_toon=False)

        assert "## Files Explored" in formatted
        assert "`/a.py`" in formatted

    def test_format_files_explored_hidden_when_changes_exist(self):
        """format_checkpoint_for_context hides files explored when changes exist (markdown format)."""
        cp = Checkpoint(
            id="test-fmt-hide-explored",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            files_explored=frozenset(["/a.py"]),
            files_changed=frozenset(["/b.py"]),
        )
        formatted = format_checkpoint_for_context(cp, use_toon=False)

        # Files Changed is shown
        assert "## Files Changed" in formatted
        # Files Explored is hidden (redundant when changes exist)
        assert "## Files Explored" not in formatted


class TestToonFormat:
    """Tests for TOON-style checkpoint formatting."""

    def test_toon_format_uses_compact_headers(self):
        """TOON format uses shorter section headers."""
        from sage.checkpoint import format_checkpoint_toon

        cp = Checkpoint(
            id="test-toon",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Test question?",
            thesis="Test thesis.",
            confidence=0.8,
            key_evidence=("Evidence 1", "Evidence 2"),
            open_questions=("Question 1?",),
        )
        formatted = format_checkpoint_toon(cp)

        # TOON uses compact headers
        assert "## Question" in formatted
        assert "## Thesis" in formatted
        assert "## Evidence [2]" in formatted
        assert "## Open [1]" in formatted
        # Not the verbose markdown headers
        assert "## Core Question" not in formatted
        assert "## Key Evidence" not in formatted

    def test_toon_format_tabular_sources(self):
        """TOON format uses tabular layout for 3+ sources."""
        from sage.checkpoint import format_checkpoint_toon

        cp = Checkpoint(
            id="test-toon-sources",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            sources=(
                Source(id="s1", type="repo", take="Take 1", relation="supports"),
                Source(id="s2", type="paper", take="Take 2", relation="contradicts"),
                Source(id="s3", type="blog", take="Take 3", relation="nuances"),
            ),
        )
        formatted = format_checkpoint_toon(cp)

        # Tabular format with field hints
        assert "sources[3]{id,type,take,rel}:" in formatted
        assert "s1,repo,Take 1,+" in formatted
        assert "s2,paper,Take 2,-" in formatted
        assert "s3,blog,Take 3,~" in formatted

    def test_toon_format_tabular_code_refs(self):
        """TOON format uses tabular layout for 3+ code refs."""
        from sage.checkpoint import format_checkpoint_toon, CodeRef

        cp = Checkpoint(
            id="test-toon-refs",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            code_refs=(
                CodeRef(file="a.py", lines=(1, 10), relevance="supports"),
                CodeRef(file="b.py", lines=(20, 30), relevance="contradicts"),
                CodeRef(file="c.py", lines=(40, 50), relevance="context"),
            ),
        )
        formatted = format_checkpoint_toon(cp)

        # Tabular format with field hints
        assert "refs[3]{file,lines,rel}:" in formatted
        assert "a.py,1-10,+" in formatted
        assert "b.py,20-30,-" in formatted
        assert "c.py,40-50,~" in formatted

    def test_toon_format_config_default(self):
        """format_checkpoint_for_context respects config.output_format."""
        # When config says "toon", it should use TOON format
        cp = Checkpoint(
            id="test-config",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Test?",
            thesis="Test.",
            confidence=0.8,
        )

        # Explicit use_toon=True
        toon = format_checkpoint_for_context(cp, use_toon=True)
        assert "## Question" in toon

        # Explicit use_toon=False
        md = format_checkpoint_for_context(cp, use_toon=False)
        assert "## Core Question" in md

    def test_toon_format_smaller_than_markdown(self):
        """TOON format produces smaller output for structured data."""
        from sage.checkpoint import format_checkpoint_toon, CodeRef

        # Create checkpoint with lots of structured data
        cp = Checkpoint(
            id="test-size",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Big question?",
            thesis="Big thesis.",
            confidence=0.8,
            sources=tuple(
                Source(id=f"src-{i}", type="repo", take=f"Take {i}", relation="supports")
                for i in range(10)
            ),
            code_refs=tuple(
                CodeRef(file=f"file{i}.py", lines=(i*10, i*10+5), relevance="supports")
                for i in range(10)
            ),
        )

        toon = format_checkpoint_toon(cp)
        md = format_checkpoint_for_context(cp, use_toon=False)

        # TOON should be smaller
        assert len(toon) < len(md)


class TestCreateCheckpointFromDictCodeContext:
    """Tests for create_checkpoint_from_dict with code context."""

    def test_create_with_code_refs(self):
        """create_checkpoint_from_dict handles code_refs."""
        data = {
            "core_question": "Q",
            "thesis": "T",
            "confidence": 0.8,
            "code_refs": [
                {"file": "/a.py", "relevance": "supports"},
                {"file": "/b.py", "lines": [10, 20], "relevance": "context"},
            ],
        }
        cp = create_checkpoint_from_dict(data, trigger="synthesis")

        assert len(cp.code_refs) == 2
        assert cp.code_refs[0].file == "/a.py"
        assert cp.code_refs[0].relevance == "supports"
        assert cp.code_refs[1].lines == (10, 20)

    def test_create_with_files_explored(self):
        """create_checkpoint_from_dict handles files_explored."""
        data = {
            "core_question": "Q",
            "thesis": "T",
            "confidence": 0.8,
            "files_explored": ["/a.py", "/b.py"],
            "files_changed": ["/c.py"],
        }
        cp = create_checkpoint_from_dict(data, trigger="synthesis")

        assert cp.files_explored == frozenset(["/a.py", "/b.py"])
        assert cp.files_changed == frozenset(["/c.py"])


class TestEnrichCheckpointWithCodeContext:
    """Tests for enrich_checkpoint_with_code_context function."""

    def test_enrich_adds_file_context(self, tmp_path: Path):
        """enrich_checkpoint_with_code_context adds files from transcript."""
        import json

        from sage.checkpoint import enrich_checkpoint_with_code_context

        # Create a transcript
        transcript_path = tmp_path / "session.jsonl"
        entries = [
            {
                "timestamp": "t1",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/read.py"}},
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/edited.py"}},
                    ],
                },
            },
        ]
        with open(transcript_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        # Create a checkpoint without context
        cp = Checkpoint(
            id="test-enrich",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
        )

        # Enrich it
        enriched = enrich_checkpoint_with_code_context(cp, transcript_path)

        assert "/read.py" in enriched.files_explored
        assert "/edited.py" in enriched.files_changed

    def test_enrich_merges_with_existing_context(self, tmp_path: Path):
        """enrich_checkpoint_with_code_context merges with existing context."""
        import json

        from sage.checkpoint import enrich_checkpoint_with_code_context

        # Create a transcript
        transcript_path = tmp_path / "session.jsonl"
        entries = [
            {
                "timestamp": "t1",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/new.py"}},
                    ],
                },
            },
        ]
        with open(transcript_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        # Create a checkpoint with existing context
        cp = Checkpoint(
            id="test-merge",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
            files_explored=frozenset(["/existing.py"]),
        )

        # Enrich it
        enriched = enrich_checkpoint_with_code_context(cp, transcript_path)

        # Both files should be present
        assert "/existing.py" in enriched.files_explored
        assert "/new.py" in enriched.files_explored

    def test_enrich_empty_transcript_returns_unchanged(self, tmp_path: Path):
        """enrich_checkpoint_with_code_context returns unchanged for empty transcript."""
        from sage.checkpoint import enrich_checkpoint_with_code_context

        # Create empty transcript
        transcript_path = tmp_path / "empty.jsonl"
        transcript_path.write_text("")

        cp = Checkpoint(
            id="test-empty",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
        )

        enriched = enrich_checkpoint_with_code_context(cp, transcript_path)

        assert enriched.files_explored == frozenset()
        assert enriched.files_changed == frozenset()

    def test_enrich_nonexistent_transcript_returns_unchanged(self, tmp_path: Path):
        """enrich_checkpoint_with_code_context returns unchanged for nonexistent file."""
        from sage.checkpoint import enrich_checkpoint_with_code_context

        transcript_path = tmp_path / "nonexistent.jsonl"

        cp = Checkpoint(
            id="test-nonexistent",
            ts="2026-01-20T12:00:00Z",
            trigger="synthesis",
            core_question="Q",
            thesis="T",
            confidence=0.8,
        )

        enriched = enrich_checkpoint_with_code_context(cp, transcript_path)

        # Should return unchanged checkpoint
        assert enriched.files_explored == frozenset()
        assert enriched.files_changed == frozenset()
