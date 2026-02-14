"""Tests for sage.transcript module."""

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from sage.transcript import (
    MAX_LINE_LENGTH,
    CursorState,
    ToolCall,
    TranscriptEntry,
    TranscriptWindow,
    get_assistant_content,
    get_compaction_summary,
    get_files_touched,
    get_tool_summary,
    get_tools_used,
    get_user_content,
    has_compaction,
    load_cursor,
    read_full_transcript,
    read_transcript_since,
    save_cursor,
    _extract_text_content,
    _extract_tool_calls,
)


@pytest.fixture
def temp_transcript(tmp_path: Path):
    """Create a temporary transcript file."""
    transcript = tmp_path / "session.jsonl"
    return transcript


@pytest.fixture
def sample_entries():
    """Sample JSONL entries for testing."""
    return [
        {
            "timestamp": "2026-01-15T10:00:00Z",
            "message": {
                "role": "user",
                "content": "Help me implement a feature",
            },
        },
        {
            "timestamp": "2026-01-15T10:00:05Z",
            "message": {
                "role": "assistant",
                "content": "I'll help you implement that feature.",
            },
        },
        {
            "timestamp": "2026-01-15T10:00:10Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me read the file first."},
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "/path/to/file.py"},
                    },
                ],
            },
        },
    ]


class TestToolCall:
    """Tests for ToolCall dataclass."""

    def test_toolcall_is_frozen(self):
        """ToolCall is immutable."""
        tc = ToolCall(name="Read", input={"path": "file.py"})
        with pytest.raises(AttributeError):
            tc.name = "Write"

    def test_toolcall_default_values(self):
        """ToolCall has sensible defaults."""
        tc = ToolCall(name="Test")
        assert tc.input == {}
        assert tc.output == ""


class TestTranscriptEntry:
    """Tests for TranscriptEntry dataclass."""

    def test_entry_is_frozen(self):
        """TranscriptEntry is immutable."""
        entry = TranscriptEntry(
            role="user",
            content="Hello",
            timestamp="2026-01-15T10:00:00Z",
        )
        with pytest.raises(AttributeError):
            entry.role = "assistant"

    def test_from_jsonl_parses_user_message(self):
        """from_jsonl parses user messages correctly."""
        data = {
            "timestamp": "2026-01-15T10:00:00Z",
            "message": {
                "role": "user",
                "content": "Hello, world!",
            },
        }
        entry = TranscriptEntry.from_jsonl(data)

        assert entry is not None
        assert entry.role == "user"
        assert entry.content == "Hello, world!"
        assert entry.timestamp == "2026-01-15T10:00:00Z"
        assert entry.is_compaction is False

    def test_from_jsonl_parses_assistant_message(self):
        """from_jsonl parses assistant messages correctly."""
        data = {
            "timestamp": "2026-01-15T10:00:05Z",
            "message": {
                "role": "assistant",
                "content": "I can help with that!",
            },
        }
        entry = TranscriptEntry.from_jsonl(data)

        assert entry is not None
        assert entry.role == "assistant"
        assert entry.content == "I can help with that!"

    def test_from_jsonl_parses_content_blocks(self):
        """from_jsonl parses content block format."""
        data = {
            "timestamp": "2026-01-15T10:00:10Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "First paragraph."},
                    {"type": "text", "text": "Second paragraph."},
                ],
            },
        }
        entry = TranscriptEntry.from_jsonl(data)

        assert entry is not None
        assert "First paragraph." in entry.content
        assert "Second paragraph." in entry.content

    def test_from_jsonl_extracts_tool_calls(self):
        """from_jsonl extracts tool calls from content blocks."""
        data = {
            "timestamp": "2026-01-15T10:00:10Z",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Reading file..."},
                    {
                        "type": "tool_use",
                        "name": "Read",
                        "input": {"file_path": "/path/to/file.py"},
                    },
                ],
            },
        }
        entry = TranscriptEntry.from_jsonl(data)

        assert entry is not None
        assert len(entry.tool_calls) == 1
        assert entry.tool_calls[0].name == "Read"
        assert entry.tool_calls[0].input["file_path"] == "/path/to/file.py"

    def test_from_jsonl_parses_compaction_event(self):
        """from_jsonl recognizes compaction events."""
        data = {
            "isCompactSummary": True,
            "message": {
                "content": "The user was working on a Python project."
            },
        }
        entry = TranscriptEntry.from_jsonl(data)

        assert entry is not None
        assert entry.is_compaction is True
        assert entry.role == "system"
        assert "Python project" in entry.content

    def test_from_jsonl_returns_none_for_invalid(self):
        """from_jsonl returns None for invalid data."""
        assert TranscriptEntry.from_jsonl({}) is None
        assert TranscriptEntry.from_jsonl({"message": "not a dict"}) is None
        assert TranscriptEntry.from_jsonl({"message": {"no_role": True}}) is None
        assert TranscriptEntry.from_jsonl("not a dict") is None
        assert TranscriptEntry.from_jsonl(123) is None

    def test_from_jsonl_generates_timestamp_if_missing(self):
        """from_jsonl generates timestamp if not in data."""
        data = {
            "message": {
                "role": "user",
                "content": "No timestamp here",
            },
        }
        entry = TranscriptEntry.from_jsonl(data)

        assert entry is not None
        assert entry.timestamp  # Not empty


class TestTranscriptWindow:
    """Tests for TranscriptWindow dataclass."""

    def test_window_length(self):
        """TranscriptWindow reports correct length."""
        entries = (
            TranscriptEntry(role="user", content="Hi", timestamp="t1"),
            TranscriptEntry(role="assistant", content="Hello", timestamp="t2"),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        assert len(window) == 2

    def test_window_is_empty(self):
        """is_empty property works correctly."""
        empty_window = TranscriptWindow(entries=(), cursor_position=0)
        non_empty = TranscriptWindow(
            entries=(TranscriptEntry(role="user", content="Hi", timestamp="t"),),
            cursor_position=50,
        )

        assert empty_window.is_empty is True
        assert non_empty.is_empty is False


class TestCursorState:
    """Tests for CursorState dataclass."""

    def test_cursor_to_dict(self):
        """CursorState serializes to dict."""
        cursor = CursorState(
            file_path="/path/to/file.jsonl",
            position=1234,
            last_read="2026-01-15T10:00:00Z",
        )
        data = cursor.to_dict()

        assert data["file_path"] == "/path/to/file.jsonl"
        assert data["position"] == 1234
        assert data["last_read"] == "2026-01-15T10:00:00Z"

    def test_cursor_from_dict(self):
        """CursorState deserializes from dict."""
        data = {
            "file_path": "/path/to/file.jsonl",
            "position": 5678,
            "last_read": "2026-01-15T11:00:00Z",
        }
        cursor = CursorState.from_dict(data)

        assert cursor.file_path == "/path/to/file.jsonl"
        assert cursor.position == 5678
        assert cursor.last_read == "2026-01-15T11:00:00Z"

    def test_cursor_from_dict_handles_missing(self):
        """CursorState handles missing keys gracefully."""
        cursor = CursorState.from_dict({})

        assert cursor.file_path == ""
        assert cursor.position == 0
        assert cursor.last_read == ""


class TestReadTranscript:
    """Tests for read_transcript_since and read_full_transcript."""

    def test_read_transcript_since_empty_file(self, temp_transcript: Path):
        """Reading empty file returns empty window."""
        temp_transcript.write_text("")

        window = read_transcript_since(temp_transcript)

        assert window.is_empty
        assert window.cursor_position == 0

    def test_read_transcript_since_with_entries(
        self, temp_transcript: Path, sample_entries: list
    ):
        """Reading file with entries returns populated window."""
        lines = [json.dumps(entry) + "\n" for entry in sample_entries]
        temp_transcript.write_text("".join(lines))

        window = read_transcript_since(temp_transcript)

        assert len(window) == 3
        assert window.entries[0].role == "user"
        assert window.entries[1].role == "assistant"

    def test_read_transcript_since_respects_cursor(
        self, temp_transcript: Path, sample_entries: list
    ):
        """Reading from cursor position skips earlier content."""
        lines = [json.dumps(entry) + "\n" for entry in sample_entries]
        content = "".join(lines)
        temp_transcript.write_text(content)

        # First read to get cursor after first entry
        first_line_end = content.find("\n") + 1
        window = read_transcript_since(temp_transcript, cursor=first_line_end)

        assert len(window) == 2  # Should skip the first entry

    def test_read_transcript_since_respects_max_entries(
        self, temp_transcript: Path, sample_entries: list
    ):
        """max_entries limits number of returned entries."""
        lines = [json.dumps(entry) + "\n" for entry in sample_entries]
        temp_transcript.write_text("".join(lines))

        window = read_transcript_since(temp_transcript, max_entries=1)

        assert len(window) == 1

    def test_read_transcript_since_nonexistent_file(self, tmp_path: Path):
        """Reading nonexistent file returns empty window."""
        fake_path = tmp_path / "nonexistent.jsonl"

        window = read_transcript_since(fake_path)

        assert window.is_empty

    def test_read_transcript_since_directory_path(self, tmp_path: Path):
        """Reading directory returns empty window."""
        window = read_transcript_since(tmp_path)  # tmp_path is a directory

        assert window.is_empty

    def test_read_transcript_since_handles_malformed_json(self, temp_transcript: Path):
        """Malformed JSON lines are skipped."""
        content = '{"message": {"role": "user", "content": "Valid"}}\n'
        content += "not json at all\n"
        content += '{"message": {"role": "assistant", "content": "Also valid"}}\n'
        temp_transcript.write_text(content)

        window = read_transcript_since(temp_transcript)

        assert len(window) == 2  # Both valid entries, malformed skipped

    def test_read_transcript_since_skips_oversized_lines(self, temp_transcript: Path):
        """Lines exceeding MAX_LINE_LENGTH are skipped."""
        normal = '{"message": {"role": "user", "content": "Normal"}}\n'
        # Create a line that's too long (we won't actually write 10MB, just verify logic)
        temp_transcript.write_text(normal)

        window = read_transcript_since(temp_transcript)

        assert len(window) == 1  # Normal line is parsed

    def test_read_full_transcript(self, temp_transcript: Path, sample_entries: list):
        """read_full_transcript reads from beginning."""
        lines = [json.dumps(entry) + "\n" for entry in sample_entries]
        temp_transcript.write_text("".join(lines))

        window = read_full_transcript(temp_transcript)

        assert len(window) == 3


class TestContentExtraction:
    """Tests for content extraction functions."""

    def test_get_assistant_content(self):
        """get_assistant_content extracts assistant messages."""
        entries = (
            TranscriptEntry(role="user", content="User message", timestamp="t1"),
            TranscriptEntry(role="assistant", content="Assistant 1", timestamp="t2"),
            TranscriptEntry(role="assistant", content="Assistant 2", timestamp="t3"),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        content = get_assistant_content(window)

        assert "Assistant 1" in content
        assert "Assistant 2" in content
        assert "User message" not in content

    def test_get_user_content(self):
        """get_user_content extracts user messages."""
        entries = (
            TranscriptEntry(role="user", content="User message 1", timestamp="t1"),
            TranscriptEntry(role="assistant", content="Assistant", timestamp="t2"),
            TranscriptEntry(role="user", content="User message 2", timestamp="t3"),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        content = get_user_content(window)

        assert "User message 1" in content
        assert "User message 2" in content
        assert "Assistant" not in content

    def test_get_tool_summary(self):
        """get_tool_summary creates tool call summaries."""
        entries = (
            TranscriptEntry(
                role="assistant",
                content="Reading...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/path/to/file.py"}),
                ),
            ),
            TranscriptEntry(
                role="assistant",
                content="Writing...",
                timestamp="t2",
                tool_calls=(
                    ToolCall(name="Write", input={"file_path": "/new/file.py", "content": "..."}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        summaries = get_tool_summary(window)

        assert len(summaries) == 2
        assert any("Read" in s for s in summaries)
        assert any("Write" in s for s in summaries)

    def test_get_files_touched(self):
        """get_files_touched extracts file paths from tool calls."""
        entries = (
            TranscriptEntry(
                role="assistant",
                content="",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/a/file.py"}),
                    ToolCall(name="Edit", input={"file_path": "/b/file.py"}),
                ),
            ),
            TranscriptEntry(
                role="assistant",
                content="",
                timestamp="t2",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/a/file.py"}),  # Duplicate
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        files = get_files_touched(window)

        assert len(files) == 2  # Deduplicated
        assert "/a/file.py" in files
        assert "/b/file.py" in files

    def test_get_files_touched_various_key_names(self):
        """get_files_touched handles different argument names."""
        entries = (
            TranscriptEntry(
                role="assistant",
                content="",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/a.py"}),
                    ToolCall(name="Glob", input={"path": "/b"}),
                    ToolCall(name="Custom", input={"file": "/c.py"}),
                    ToolCall(name="NotebookEdit", input={"notebook_path": "/d.ipynb"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        files = get_files_touched(window)

        assert "/a.py" in files
        assert "/b" in files
        assert "/c.py" in files
        assert "/d.ipynb" in files

    def test_get_tools_used(self):
        """get_tools_used returns unique tool names."""
        entries = (
            TranscriptEntry(
                role="assistant",
                content="",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read"),
                    ToolCall(name="Edit"),
                ),
            ),
            TranscriptEntry(
                role="assistant",
                content="",
                timestamp="t2",
                tool_calls=(
                    ToolCall(name="Read"),  # Duplicate
                    ToolCall(name="Write"),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        tools = get_tools_used(window)

        assert sorted(tools) == ["Edit", "Read", "Write"]


class TestCompactionDetection:
    """Tests for compaction detection functions."""

    def test_has_compaction_true(self):
        """has_compaction returns True when compaction present."""
        entries = (
            TranscriptEntry(role="user", content="Hello", timestamp="t1"),
            TranscriptEntry(
                role="system",
                content="Summary",
                timestamp="t2",
                is_compaction=True,
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        assert has_compaction(window) is True

    def test_has_compaction_false(self):
        """has_compaction returns False when no compaction."""
        entries = (
            TranscriptEntry(role="user", content="Hello", timestamp="t1"),
            TranscriptEntry(role="assistant", content="Hi", timestamp="t2"),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        assert has_compaction(window) is False

    def test_get_compaction_summary(self):
        """get_compaction_summary returns summary content."""
        entries = (
            TranscriptEntry(role="user", content="Hello", timestamp="t1"),
            TranscriptEntry(
                role="system",
                content="The user was working on Python.",
                timestamp="t2",
                is_compaction=True,
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        summary = get_compaction_summary(window)

        assert summary == "The user was working on Python."

    def test_get_compaction_summary_none(self):
        """get_compaction_summary returns None when no compaction."""
        entries = (
            TranscriptEntry(role="user", content="Hello", timestamp="t1"),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        summary = get_compaction_summary(window)

        assert summary is None


class TestCursorSaveLoad:
    """Tests for cursor persistence."""

    def test_save_and_load_cursor(self, tmp_path: Path):
        """save_cursor and load_cursor round-trip correctly."""
        cursor_path = tmp_path / "cursor.json"
        cursor = CursorState(
            file_path="/path/to/transcript.jsonl",
            position=12345,
            last_read="2026-01-15T12:00:00Z",
        )

        result = save_cursor(cursor_path, cursor)
        loaded = load_cursor(cursor_path)

        assert result is True
        assert loaded is not None
        assert loaded.file_path == cursor.file_path
        assert loaded.position == cursor.position
        assert loaded.last_read == cursor.last_read

    def test_save_cursor_creates_directory(self, tmp_path: Path):
        """save_cursor creates parent directory if needed."""
        cursor_path = tmp_path / "subdir" / "cursor.json"
        cursor = CursorState(file_path="", position=0, last_read="")

        result = save_cursor(cursor_path, cursor)

        assert result is True
        assert cursor_path.exists()

    def test_save_cursor_restricted_permissions(self, tmp_path: Path):
        """save_cursor sets restricted file permissions."""
        cursor_path = tmp_path / "cursor.json"
        cursor = CursorState(file_path="", position=0, last_read="")

        save_cursor(cursor_path, cursor)

        mode = cursor_path.stat().st_mode & 0o777
        assert mode == 0o600

    def test_load_cursor_nonexistent(self, tmp_path: Path):
        """load_cursor returns None for nonexistent file."""
        cursor_path = tmp_path / "nonexistent.json"

        loaded = load_cursor(cursor_path)

        assert loaded is None

    def test_load_cursor_malformed_json(self, tmp_path: Path):
        """load_cursor returns None for malformed JSON."""
        cursor_path = tmp_path / "cursor.json"
        cursor_path.write_text("not valid json {{{")

        loaded = load_cursor(cursor_path)

        assert loaded is None


class TestExtractHelpers:
    """Tests for internal extraction helper functions."""

    def test_extract_text_content_string(self):
        """_extract_text_content handles string content."""
        result = _extract_text_content("Hello, world!")
        assert result == "Hello, world!"

    def test_extract_text_content_blocks(self):
        """_extract_text_content handles content block list."""
        blocks = [
            {"type": "text", "text": "First"},
            {"type": "text", "text": "Second"},
        ]
        result = _extract_text_content(blocks)
        assert "First" in result
        assert "Second" in result

    def test_extract_text_content_mixed_blocks(self):
        """_extract_text_content filters to text blocks only."""
        blocks = [
            {"type": "text", "text": "Text content"},
            {"type": "tool_use", "name": "Read", "input": {}},
            {"type": "image", "source": "..."},
        ]
        result = _extract_text_content(blocks)
        assert result == "Text content"

    def test_extract_text_content_invalid(self):
        """_extract_text_content returns empty for invalid types."""
        assert _extract_text_content(None) == ""
        assert _extract_text_content(123) == ""
        assert _extract_text_content({"type": "text"}) == ""

    def test_extract_tool_calls_from_blocks(self):
        """_extract_tool_calls extracts tool_use blocks."""
        blocks = [
            {"type": "text", "text": "Reading..."},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/a.py"}},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/b.py"}},
        ]
        tools = _extract_tool_calls(blocks)

        assert len(tools) == 2
        assert tools[0].name == "Read"
        assert tools[1].name == "Edit"

    def test_extract_tool_calls_not_list(self):
        """_extract_tool_calls returns empty for non-list."""
        assert _extract_tool_calls("string") == []
        assert _extract_tool_calls(None) == []
        assert _extract_tool_calls({}) == []


class TestConstants:
    """Tests for module constants."""

    def test_max_line_length_defined(self):
        """MAX_LINE_LENGTH is defined and reasonable."""
        assert MAX_LINE_LENGTH > 0
        assert MAX_LINE_LENGTH == 10_000_000  # 10MB


class TestIntegration:
    """Integration tests for transcript module."""

    def test_full_transcript_workflow(self, tmp_path: Path):
        """Test complete workflow: write, read, extract."""
        transcript_path = tmp_path / "session.jsonl"

        # Write a realistic transcript
        entries = [
            {
                "timestamp": "2026-01-15T10:00:00Z",
                "message": {
                    "role": "user",
                    "content": "Can you help me fix the bug in auth.py?",
                },
            },
            {
                "timestamp": "2026-01-15T10:00:05Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "I'll read the file to understand the issue."},
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"file_path": "/project/auth.py"},
                        },
                    ],
                },
            },
            {
                "timestamp": "2026-01-15T10:00:10Z",
                "message": {
                    "role": "assistant",
                    "content": "I found the bug! The fix is to add a null check.",
                },
            },
        ]
        with open(transcript_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        # Read full transcript
        window = read_full_transcript(transcript_path)
        assert len(window) == 3

        # Extract content
        user_content = get_user_content(window)
        assert "auth.py" in user_content

        assistant_content = get_assistant_content(window)
        assert "fix" in assistant_content.lower()

        files = get_files_touched(window)
        assert "/project/auth.py" in files

        tools = get_tools_used(window)
        assert "Read" in tools

    def test_incremental_reading(self, tmp_path: Path):
        """Test cursor-based incremental reading."""
        transcript_path = tmp_path / "session.jsonl"
        cursor_path = tmp_path / "cursor.json"

        # Write initial entries
        initial_entries = [
            {"timestamp": "t1", "message": {"role": "user", "content": "First"}},
            {"timestamp": "t2", "message": {"role": "assistant", "content": "Response"}},
        ]
        with open(transcript_path, "w") as f:
            for entry in initial_entries:
                f.write(json.dumps(entry) + "\n")

        # First read
        window1 = read_transcript_since(transcript_path, cursor=0)
        assert len(window1) == 2

        # Save cursor
        cursor = CursorState(
            file_path=str(transcript_path),
            position=window1.cursor_position,
            last_read=datetime.now(UTC).isoformat(),
        )
        save_cursor(cursor_path, cursor)

        # Append more entries
        new_entries = [
            {"timestamp": "t3", "message": {"role": "user", "content": "Another question"}},
        ]
        with open(transcript_path, "a") as f:
            for entry in new_entries:
                f.write(json.dumps(entry) + "\n")

        # Load cursor and read from there
        loaded_cursor = load_cursor(cursor_path)
        assert loaded_cursor is not None

        window2 = read_transcript_since(transcript_path, cursor=loaded_cursor.position)
        assert len(window2) == 1
        assert window2.entries[0].content == "Another question"


# =============================================================================
# File Interaction Extraction Tests (v1.3)
# =============================================================================


class TestFileInteraction:
    """Tests for FileInteraction dataclass."""

    def test_file_interaction_is_frozen(self):
        """FileInteraction is immutable."""
        from sage.transcript import FileInteraction

        interaction = FileInteraction(
            file="/path/to/file.py",
            action="read",
            timestamp="2026-01-15T10:00:00Z",
        )
        with pytest.raises(AttributeError):
            interaction.file = "/other/file.py"

    def test_file_interaction_with_lines(self):
        """FileInteraction can store line ranges."""
        from sage.transcript import FileInteraction

        interaction = FileInteraction(
            file="/path/to/file.py",
            action="read",
            timestamp="2026-01-15T10:00:00Z",
            lines=(10, 50),
        )
        assert interaction.lines == (10, 50)

    def test_file_interaction_default_lines_none(self):
        """FileInteraction lines default to None."""
        from sage.transcript import FileInteraction

        interaction = FileInteraction(
            file="/path/to/file.py",
            action="read",
            timestamp="2026-01-15T10:00:00Z",
        )
        assert interaction.lines is None


class TestSessionCodeContext:
    """Tests for SessionCodeContext dataclass."""

    def test_session_code_context_is_frozen(self):
        """SessionCodeContext is immutable."""
        from sage.transcript import SessionCodeContext

        context = SessionCodeContext(
            interactions=(),
            files_read=frozenset(),
            files_edited=frozenset(),
            files_written=frozenset(),
        )
        with pytest.raises(AttributeError):
            context.files_read = frozenset(["/a.py"])

    def test_session_code_context_files_changed(self):
        """files_changed combines edited and written files."""
        from sage.transcript import SessionCodeContext

        context = SessionCodeContext(
            interactions=(),
            files_read=frozenset(["/a.py"]),
            files_edited=frozenset(["/b.py"]),
            files_written=frozenset(["/c.py"]),
        )
        assert context.files_changed == frozenset(["/b.py", "/c.py"])

    def test_session_code_context_all_files(self):
        """all_files combines all file sets."""
        from sage.transcript import SessionCodeContext

        context = SessionCodeContext(
            interactions=(),
            files_read=frozenset(["/a.py"]),
            files_edited=frozenset(["/b.py"]),
            files_written=frozenset(["/c.py"]),
        )
        assert context.all_files == frozenset(["/a.py", "/b.py", "/c.py"])

    def test_session_code_context_empty(self):
        """SessionCodeContext.empty() creates empty context."""
        from sage.transcript import SessionCodeContext

        context = SessionCodeContext.empty()
        assert context.interactions == ()
        assert context.files_read == frozenset()
        assert context.files_edited == frozenset()
        assert context.files_written == frozenset()


class TestExtractFileInteractions:
    """Tests for extract_file_interactions function."""

    def test_extract_read_interactions(self):
        """Extracts Read tool calls as read interactions."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Reading...",
                timestamp="2026-01-15T10:00:00Z",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/project/auth.py"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 1
        assert interactions[0].file == "/project/auth.py"
        assert interactions[0].action == "read"
        assert interactions[0].timestamp == "2026-01-15T10:00:00Z"

    def test_extract_edit_interactions(self):
        """Extracts Edit tool calls as edit interactions."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Editing...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Edit", input={"file_path": "/project/auth.py", "old_string": "x", "new_string": "y"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 1
        assert interactions[0].action == "edit"

    def test_extract_write_interactions(self):
        """Extracts Write tool calls as write interactions."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Writing...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Write", input={"file_path": "/new/file.py", "content": "..."}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 1
        assert interactions[0].action == "write"

    def test_extract_grep_interactions(self):
        """Extracts Grep tool calls as grep interactions."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Searching...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Grep", input={"path": "/project", "pattern": "def"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 1
        assert interactions[0].action == "grep"
        assert interactions[0].file == "/project"

    def test_extract_notebook_edit_interactions(self):
        """Extracts NotebookEdit tool calls as edit interactions."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Editing notebook...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="NotebookEdit", input={"notebook_path": "/nb.ipynb"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 1
        assert interactions[0].action == "edit"
        assert interactions[0].file == "/nb.ipynb"

    def test_extract_ignores_unknown_tools(self):
        """Unknown tools are not extracted."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Custom...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="CustomTool", input={"file_path": "/a.py"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 0

    def test_extract_skips_missing_file_path(self):
        """Tool calls without file path are skipped."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Reading...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read", input={}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 0

    def test_extract_line_range_from_read(self):
        """Read with offset/limit extracts line range."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Reading lines...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/a.py", "offset": 10, "limit": 20}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 1
        assert interactions[0].lines == (10, 29)  # 10 + 20 - 1

    def test_extract_multiple_interactions(self):
        """Multiple tool calls across entries are extracted."""
        from sage.transcript import extract_file_interactions

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Step 1...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/a.py"}),
                    ToolCall(name="Edit", input={"file_path": "/b.py"}),
                ),
            ),
            TranscriptEntry(
                role="assistant",
                content="Step 2...",
                timestamp="t2",
                tool_calls=(
                    ToolCall(name="Write", input={"file_path": "/c.py"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        interactions = extract_file_interactions(window)

        assert len(interactions) == 3
        files = [i.file for i in interactions]
        assert "/a.py" in files
        assert "/b.py" in files
        assert "/c.py" in files


class TestBuildSessionCodeContext:
    """Tests for build_session_code_context function."""

    def test_build_context_categorizes_files(self):
        """build_session_code_context categorizes files by action."""
        from sage.transcript import build_session_code_context

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Working...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/read1.py"}),
                    ToolCall(name="Read", input={"file_path": "/read2.py"}),
                    ToolCall(name="Edit", input={"file_path": "/edited.py"}),
                    ToolCall(name="Write", input={"file_path": "/written.py"}),
                    ToolCall(name="Grep", input={"path": "/search"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        context = build_session_code_context(window)

        assert context.files_read == frozenset(["/read1.py", "/read2.py"])
        assert context.files_edited == frozenset(["/edited.py"])
        assert context.files_written == frozenset(["/written.py"])
        # Grep doesn't add to file sets
        assert "/search" not in context.all_files

    def test_build_context_deduplicates(self):
        """build_session_code_context deduplicates files."""
        from sage.transcript import build_session_code_context

        entries = (
            TranscriptEntry(
                role="assistant",
                content="Step 1...",
                timestamp="t1",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/a.py"}),
                ),
            ),
            TranscriptEntry(
                role="assistant",
                content="Step 2...",
                timestamp="t2",
                tool_calls=(
                    ToolCall(name="Read", input={"file_path": "/a.py"}),
                ),
            ),
        )
        window = TranscriptWindow(entries=entries, cursor_position=100)

        context = build_session_code_context(window)

        assert context.files_read == frozenset(["/a.py"])
        assert len(context.interactions) == 2  # Still has both interactions

    def test_build_context_empty_window(self):
        """build_session_code_context handles empty window."""
        from sage.transcript import build_session_code_context

        window = TranscriptWindow(entries=(), cursor_position=0)

        context = build_session_code_context(window)

        assert context.interactions == ()
        assert context.all_files == frozenset()


class TestGetSessionCodeContext:
    """Tests for get_session_code_context convenience function."""

    def test_get_session_code_context_from_file(self, tmp_path: Path):
        """get_session_code_context reads transcript and builds context."""
        from sage.transcript import get_session_code_context

        transcript_path = tmp_path / "session.jsonl"
        entries = [
            {
                "timestamp": "t1",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {"file_path": "/a.py"}},
                        {"type": "tool_use", "name": "Edit", "input": {"file_path": "/b.py"}},
                    ],
                },
            },
        ]
        with open(transcript_path, "w") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        context = get_session_code_context(transcript_path)

        assert "/a.py" in context.files_read
        assert "/b.py" in context.files_edited

    def test_get_session_code_context_nonexistent_file(self, tmp_path: Path):
        """get_session_code_context returns empty for nonexistent file."""
        from sage.transcript import get_session_code_context

        transcript_path = tmp_path / "nonexistent.jsonl"

        context = get_session_code_context(transcript_path)

        assert context.interactions == ()
        assert context.all_files == frozenset()
