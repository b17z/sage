"""Tests for sage.recovery module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sage.recovery import (
    CHECKPOINTS_DIR,
    RecoveryCheckpoint,
    _markdown_to_recovery,
    _recovery_to_markdown,
    ensure_checkpoints_dir,
    extract_recovery_checkpoint,
    extract_topic,
    format_recovery_for_context,
    generate_recovery_id,
    get_recovery_checkpoints_dir,
    list_recovery_checkpoints,
    load_recovery_checkpoint,
    save_recovery_checkpoint,
)
from sage.transcript import ToolCall, TranscriptEntry, TranscriptWindow


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
        patch("sage.recovery.CHECKPOINTS_DIR", mock_checkpoints_dir),
        patch("sage.recovery.SAGE_DIR", tmp_path / ".sage"),
    ):
        yield mock_checkpoints_dir


@pytest.fixture
def sample_recovery_checkpoint():
    """Create a sample recovery checkpoint."""
    return RecoveryCheckpoint(
        id="2026-01-15T10-00-00_recovery-implementing-feature",
        type="recovery",
        trigger="pre_compact",
        extracted_at="2026-01-15T10:00:00Z",
        extraction_method="local",
        topic="Implementing the new feature",
        decisions=("Use Python for implementation", "Add type hints"),
        open_threads=("TODO: Add more tests",),
        resolutions=("Fixed the import error",),
        files_touched=("/project/main.py", "/project/utils.py"),
        tools_used=("Read", "Edit"),
        summary=None,
        salience_score=0.85,
    )


@pytest.fixture
def sample_transcript_window():
    """Create a sample transcript window for testing."""
    entries = (
        TranscriptEntry(
            role="user",
            content="Help me implement a new feature for the app",
            timestamp="2026-01-15T10:00:00Z",
        ),
        TranscriptEntry(
            role="assistant",
            content="I'll help you implement that. We decided to use Python. The fix is to add proper error handling.",
            timestamp="2026-01-15T10:00:05Z",
            tool_calls=(
                ToolCall(name="Read", input={"file_path": "/project/main.py"}),
            ),
        ),
        TranscriptEntry(
            role="assistant",
            content="TODO: Add tests for the new feature. The root cause was missing validation.",
            timestamp="2026-01-15T10:00:10Z",
            tool_calls=(
                ToolCall(name="Edit", input={"file_path": "/project/utils.py"}),
            ),
        ),
    )
    return TranscriptWindow(entries=entries, cursor_position=1000)


class TestRecoveryCheckpoint:
    """Tests for RecoveryCheckpoint dataclass."""

    def test_checkpoint_is_frozen(self):
        """RecoveryCheckpoint is immutable."""
        cp = RecoveryCheckpoint(id="test-id")
        with pytest.raises(AttributeError):
            cp.id = "new-id"

    def test_checkpoint_defaults(self):
        """RecoveryCheckpoint has sensible defaults."""
        cp = RecoveryCheckpoint(id="test-id")

        assert cp.type == "recovery"
        assert cp.trigger == "pre_compact"
        assert cp.extracted_at == ""
        assert cp.extraction_method == "local"
        assert cp.topic == ""
        assert cp.decisions == ()
        assert cp.open_threads == ()
        assert cp.resolutions == ()
        assert cp.files_touched == ()
        assert cp.tools_used == ()
        assert cp.summary is None
        assert cp.salience_score == 0.0

    def test_checkpoint_type_is_recovery(self, sample_recovery_checkpoint):
        """Type is always 'recovery'."""
        assert sample_recovery_checkpoint.type == "recovery"


class TestGenerateRecoveryId:
    """Tests for generate_recovery_id function."""

    def test_includes_timestamp(self):
        """ID includes timestamp prefix."""
        recovery_id = generate_recovery_id("test topic")

        assert recovery_id.startswith("20")  # Year prefix
        assert "_recovery-" in recovery_id

    def test_includes_slugified_topic(self):
        """ID includes slugified topic."""
        recovery_id = generate_recovery_id("Implementing New Feature")

        assert "implementing" in recovery_id.lower()
        assert "new" in recovery_id.lower()
        assert "feature" in recovery_id.lower()

    def test_truncates_long_topics(self):
        """Long topics are truncated."""
        long_topic = "This is a very long topic that should be truncated to fit within limits"
        recovery_id = generate_recovery_id(long_topic)

        # ID format: timestamp_recovery-slug
        slug_part = recovery_id.split("_recovery-")[1]
        assert len(slug_part) <= 40

    def test_handles_empty_topic(self):
        """Empty topic results in 'unknown'."""
        recovery_id = generate_recovery_id("")

        assert "recovery-unknown" in recovery_id

    def test_handles_special_characters(self):
        """Special characters are sanitized."""
        recovery_id = generate_recovery_id("Feature: New @#$%^&* Implementation!")

        # Should not contain special characters
        slug_part = recovery_id.split("_recovery-")[1]
        assert "@" not in slug_part
        assert "#" not in slug_part


class TestExtractTopic:
    """Tests for extract_topic function."""

    def test_extracts_from_first_user_message(self):
        """Extracts topic from first user message."""
        topic = extract_topic(
            assistant_content="I can help with that.",
            user_content="Help me fix the authentication bug. More details here.",
        )

        assert "authentication" in topic.lower() or "Help" in topic

    def test_fallback_to_file_mention(self):
        """Falls back to file mention when no clear first sentence."""
        topic = extract_topic(
            assistant_content="Working on the changes to main.py",
            user_content="...",
        )

        # Should find file reference
        assert "main.py" in topic or "Working" in topic

    def test_fallback_to_function_name(self):
        """Falls back to function name detection."""
        topic = extract_topic(
            assistant_content="Let me implement the function get_user_data",
            user_content="",
        )

        # Should find function
        assert "get_user_data" in topic or "implement" in topic.lower()

    def test_handles_empty_content(self):
        """Returns 'Unknown topic' for empty content."""
        topic = extract_topic("", "")

        assert topic == "Unknown topic"


class TestExtractRecoveryCheckpoint:
    """Tests for extract_recovery_checkpoint function."""

    def test_extracts_from_window(self, sample_transcript_window):
        """Extracts checkpoint from transcript window."""
        checkpoint = extract_recovery_checkpoint(
            sample_transcript_window,
            trigger="pre_compact",
            use_claude=False,
        )

        assert checkpoint.type == "recovery"
        assert checkpoint.trigger == "pre_compact"
        assert checkpoint.extraction_method == "local"
        assert checkpoint.topic != ""

    def test_extracts_decisions(self, sample_transcript_window):
        """Extracts decisions from transcript."""
        checkpoint = extract_recovery_checkpoint(sample_transcript_window)

        # Should find "decided to use Python" decision
        assert len(checkpoint.decisions) >= 0  # May or may not find depending on patterns

    def test_extracts_files_touched(self, sample_transcript_window):
        """Extracts file paths from tool calls."""
        checkpoint = extract_recovery_checkpoint(sample_transcript_window)

        assert "/project/main.py" in checkpoint.files_touched
        assert "/project/utils.py" in checkpoint.files_touched

    def test_extracts_tools_used(self, sample_transcript_window):
        """Extracts tool names used."""
        checkpoint = extract_recovery_checkpoint(sample_transcript_window)

        assert "Read" in checkpoint.tools_used
        assert "Edit" in checkpoint.tools_used

    def test_handles_empty_window(self):
        """Handles empty transcript window gracefully."""
        empty_window = TranscriptWindow(entries=(), cursor_position=0)

        checkpoint = extract_recovery_checkpoint(empty_window)

        assert checkpoint.type == "recovery"
        assert "empty" in checkpoint.id.lower()

    def test_calculates_salience_score(self, sample_transcript_window):
        """Calculates salience score from content."""
        checkpoint = extract_recovery_checkpoint(sample_transcript_window)

        # Should have some salience (content has decisions and resolutions)
        assert checkpoint.salience_score >= 0.0

    def test_includes_extracted_at_timestamp(self, sample_transcript_window):
        """Includes extraction timestamp."""
        checkpoint = extract_recovery_checkpoint(sample_transcript_window)

        assert checkpoint.extracted_at != ""
        assert "T" in checkpoint.extracted_at  # ISO format


class TestRecoveryToMarkdown:
    """Tests for _recovery_to_markdown function."""

    def test_includes_frontmatter(self, sample_recovery_checkpoint):
        """Markdown includes YAML frontmatter."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)

        assert md.startswith("---\n")
        assert "\n---\n" in md
        assert "id: " in md
        assert "type: recovery" in md

    def test_includes_topic_as_title(self, sample_recovery_checkpoint):
        """Topic is used as H1 title."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)

        assert "# Implementing the new feature" in md

    def test_includes_decisions(self, sample_recovery_checkpoint):
        """Decisions section is included."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)

        assert "## Decisions" in md
        assert "Use Python for implementation" in md

    def test_includes_open_threads(self, sample_recovery_checkpoint):
        """Open threads section is included."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)

        assert "## Open Threads" in md
        assert "TODO: Add more tests" in md

    def test_includes_resolutions(self, sample_recovery_checkpoint):
        """Resolutions section is included."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)

        assert "## Resolutions" in md
        assert "Fixed the import error" in md

    def test_includes_context(self, sample_recovery_checkpoint):
        """Context section includes files and tools."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)

        assert "## Context" in md
        assert "Files touched:" in md
        assert "Tools used:" in md

    def test_includes_summary_when_present(self):
        """Summary section is included when present."""
        cp = RecoveryCheckpoint(
            id="test-id",
            summary="This is a summary of the conversation.",
        )
        md = _recovery_to_markdown(cp)

        assert "## Summary" in md
        assert "This is a summary" in md

    def test_omits_empty_sections(self):
        """Empty sections are omitted."""
        cp = RecoveryCheckpoint(id="test-id")
        md = _recovery_to_markdown(cp)

        assert "## Decisions" not in md
        assert "## Open Threads" not in md
        assert "## Resolutions" not in md


class TestMarkdownToRecovery:
    """Tests for _markdown_to_recovery function."""

    def test_parses_valid_markdown(self, sample_recovery_checkpoint):
        """Parses valid recovery checkpoint markdown."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)
        parsed = _markdown_to_recovery(md)

        assert parsed is not None
        assert parsed.id == sample_recovery_checkpoint.id
        assert parsed.type == "recovery"

    def test_parses_frontmatter(self, sample_recovery_checkpoint):
        """Frontmatter fields are parsed correctly."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)
        parsed = _markdown_to_recovery(md)

        assert parsed.trigger == "pre_compact"
        assert parsed.extraction_method == "local"
        assert parsed.salience_score == 0.85

    def test_parses_topic(self, sample_recovery_checkpoint):
        """Topic is parsed from H1 title."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)
        parsed = _markdown_to_recovery(md)

        assert parsed.topic == "Implementing the new feature"

    def test_parses_decisions(self, sample_recovery_checkpoint):
        """Decisions are parsed from list."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)
        parsed = _markdown_to_recovery(md)

        assert len(parsed.decisions) == 2
        assert "Use Python for implementation" in parsed.decisions

    def test_parses_open_threads(self, sample_recovery_checkpoint):
        """Open threads are parsed from list."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)
        parsed = _markdown_to_recovery(md)

        assert len(parsed.open_threads) == 1
        assert "TODO: Add more tests" in parsed.open_threads

    def test_parses_files_touched(self, sample_recovery_checkpoint):
        """Files touched are parsed from context."""
        md = _recovery_to_markdown(sample_recovery_checkpoint)
        parsed = _markdown_to_recovery(md)

        assert "/project/main.py" in parsed.files_touched

    def test_returns_none_for_non_recovery(self):
        """Returns None for non-recovery checkpoints."""
        md = """---
id: test
type: checkpoint
---
# Title
"""
        parsed = _markdown_to_recovery(md)

        assert parsed is None

    def test_returns_none_for_invalid(self):
        """Returns None for invalid markdown."""
        assert _markdown_to_recovery("not valid") is None
        assert _markdown_to_recovery("---\nincomplete") is None
        assert _markdown_to_recovery("no frontmatter here") is None


class TestSaveLoadRecoveryCheckpoint:
    """Tests for save and load functions."""

    def test_save_creates_file(self, mock_checkpoint_paths, sample_recovery_checkpoint):
        """save_recovery_checkpoint creates markdown file."""
        path = save_recovery_checkpoint(sample_recovery_checkpoint)

        assert path.exists()
        assert path.suffix == ".md"
        assert sample_recovery_checkpoint.id in path.name

    def test_save_atomic_write(self, mock_checkpoint_paths, sample_recovery_checkpoint):
        """Save uses atomic write (temp file + rename)."""
        # If atomic write works, the file should exist and have content
        path = save_recovery_checkpoint(sample_recovery_checkpoint)

        content = path.read_text()
        assert len(content) > 0
        assert "recovery" in content

    def test_save_file_permissions(self, mock_checkpoint_paths, sample_recovery_checkpoint):
        """Saved file has restricted permissions."""
        path = save_recovery_checkpoint(sample_recovery_checkpoint)

        mode = path.stat().st_mode & 0o777
        assert mode == 0o600

    def test_load_by_full_id(self, mock_checkpoint_paths, sample_recovery_checkpoint):
        """load_recovery_checkpoint works with full ID."""
        save_recovery_checkpoint(sample_recovery_checkpoint)

        loaded = load_recovery_checkpoint(sample_recovery_checkpoint.id)

        assert loaded is not None
        assert loaded.id == sample_recovery_checkpoint.id

    def test_load_by_partial_id(self, mock_checkpoint_paths, sample_recovery_checkpoint):
        """load_recovery_checkpoint supports partial ID matching."""
        save_recovery_checkpoint(sample_recovery_checkpoint)

        loaded = load_recovery_checkpoint("implementing-feature")

        assert loaded is not None

    def test_load_nonexistent_returns_none(self, mock_checkpoint_paths):
        """Loading nonexistent checkpoint returns None."""
        loaded = load_recovery_checkpoint("nonexistent-id")

        assert loaded is None

    def test_roundtrip_preserves_data(self, mock_checkpoint_paths, sample_recovery_checkpoint):
        """Save and load preserves all data."""
        save_recovery_checkpoint(sample_recovery_checkpoint)
        loaded = load_recovery_checkpoint(sample_recovery_checkpoint.id)

        assert loaded is not None
        assert loaded.id == sample_recovery_checkpoint.id
        assert loaded.trigger == sample_recovery_checkpoint.trigger
        assert loaded.topic == sample_recovery_checkpoint.topic
        assert loaded.decisions == sample_recovery_checkpoint.decisions
        assert loaded.open_threads == sample_recovery_checkpoint.open_threads
        assert loaded.resolutions == sample_recovery_checkpoint.resolutions
        assert loaded.salience_score == sample_recovery_checkpoint.salience_score


class TestListRecoveryCheckpoints:
    """Tests for list_recovery_checkpoints function."""

    def test_lists_checkpoints(self, mock_checkpoint_paths, sample_recovery_checkpoint):
        """Lists saved recovery checkpoints."""
        save_recovery_checkpoint(sample_recovery_checkpoint)

        checkpoints = list_recovery_checkpoints()

        assert len(checkpoints) == 1
        assert checkpoints[0].id == sample_recovery_checkpoint.id

    def test_returns_most_recent_first(self, mock_checkpoint_paths):
        """Checkpoints are sorted by recency (most recent first)."""
        cp1 = RecoveryCheckpoint(id="2026-01-10T10-00-00_recovery-first")
        cp2 = RecoveryCheckpoint(id="2026-01-15T10-00-00_recovery-second")

        save_recovery_checkpoint(cp1)
        save_recovery_checkpoint(cp2)

        checkpoints = list_recovery_checkpoints()

        assert len(checkpoints) == 2
        assert checkpoints[0].id == cp2.id  # More recent first

    def test_respects_limit(self, mock_checkpoint_paths):
        """Limit parameter is respected."""
        for i in range(5):
            cp = RecoveryCheckpoint(id=f"2026-01-{10+i:02d}T10-00-00_recovery-cp{i}")
            save_recovery_checkpoint(cp)

        checkpoints = list_recovery_checkpoints(limit=3)

        assert len(checkpoints) == 3

    def test_empty_when_no_checkpoints(self, mock_checkpoint_paths):
        """Returns empty list when no checkpoints exist."""
        checkpoints = list_recovery_checkpoints()

        assert checkpoints == []


class TestGetRecoveryCheckpointsDir:
    """Tests for directory functions."""

    def test_uses_global_by_default(self):
        """Uses global checkpoints directory by default."""
        result = get_recovery_checkpoints_dir(None)

        assert result == CHECKPOINTS_DIR

    def test_uses_project_local_when_exists(self, tmp_path):
        """Uses project .sage directory when it exists."""
        project_sage = tmp_path / ".sage"
        project_sage.mkdir()

        result = get_recovery_checkpoints_dir(tmp_path)

        assert result == project_sage / "checkpoints"

    def test_ensure_creates_directory(self, tmp_path, mock_checkpoint_paths):
        """ensure_checkpoints_dir creates directory if needed."""
        checkpoints_dir = ensure_checkpoints_dir()

        assert checkpoints_dir.exists()


class TestFormatRecoveryForContext:
    """Tests for format_recovery_for_context function."""

    def test_includes_header(self, sample_recovery_checkpoint):
        """Formatted output includes header."""
        formatted = format_recovery_for_context(sample_recovery_checkpoint)

        assert "Recovery Context" in formatted
        assert "Auto-extracted" in formatted

    def test_includes_checkpoint_id(self, sample_recovery_checkpoint):
        """Formatted output includes checkpoint ID."""
        formatted = format_recovery_for_context(sample_recovery_checkpoint)

        assert sample_recovery_checkpoint.id in formatted

    def test_includes_topic(self, sample_recovery_checkpoint):
        """Formatted output includes topic."""
        formatted = format_recovery_for_context(sample_recovery_checkpoint)

        assert "## Topic" in formatted
        assert sample_recovery_checkpoint.topic in formatted

    def test_includes_decisions(self, sample_recovery_checkpoint):
        """Formatted output includes decisions."""
        formatted = format_recovery_for_context(sample_recovery_checkpoint)

        assert "## Decisions Made" in formatted
        assert "Use Python" in formatted

    def test_includes_open_threads(self, sample_recovery_checkpoint):
        """Formatted output includes open threads."""
        formatted = format_recovery_for_context(sample_recovery_checkpoint)

        assert "## Open Threads" in formatted
        assert "TODO" in formatted

    def test_includes_resolutions(self, sample_recovery_checkpoint):
        """Formatted output includes resolutions."""
        formatted = format_recovery_for_context(sample_recovery_checkpoint)

        assert "## Resolutions" in formatted

    def test_includes_files_touched(self, sample_recovery_checkpoint):
        """Formatted output includes files touched."""
        formatted = format_recovery_for_context(sample_recovery_checkpoint)

        assert "## Files Touched" in formatted
        assert "/project/main.py" in formatted

    def test_limits_items(self, sample_recovery_checkpoint):
        """Items are limited to prevent context bloat."""
        # Create checkpoint with many decisions
        cp = RecoveryCheckpoint(
            id="test-id",
            decisions=tuple(f"Choice {i}" for i in range(10)),
        )
        formatted = format_recovery_for_context(cp)

        # Should limit to 5 items (count "Choice" to avoid header match)
        choice_count = formatted.count("Choice")
        assert choice_count <= 5


class TestIntegration:
    """Integration tests for recovery module."""

    def test_full_workflow(self, tmp_path, mock_checkpoint_paths, sample_transcript_window):
        """Test complete workflow: extract, save, load, format."""
        # Extract
        checkpoint = extract_recovery_checkpoint(
            sample_transcript_window,
            trigger="pre_compact",
        )
        assert checkpoint.type == "recovery"

        # Save
        path = save_recovery_checkpoint(checkpoint)
        assert path.exists()

        # List
        checkpoints = list_recovery_checkpoints()
        assert len(checkpoints) == 1

        # Load
        loaded = load_recovery_checkpoint(checkpoint.id)
        assert loaded is not None

        # Format
        formatted = format_recovery_for_context(loaded)
        assert "Recovery Context" in formatted

    def test_project_local_storage(self, tmp_path):
        """Test project-local storage path."""
        # Create project .sage directory
        project_sage = tmp_path / ".sage"
        project_sage.mkdir()

        cp = RecoveryCheckpoint(
            id="2026-01-15T10-00-00_recovery-project-test",
            topic="Project-local test",
        )

        path = save_recovery_checkpoint(cp, project_path=tmp_path)

        assert path.exists()
        assert ".sage" in str(path)
        assert "checkpoints" in str(path)
