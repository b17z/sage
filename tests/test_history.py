"""Tests for sage.history module."""

from pathlib import Path
from unittest.mock import patch
import json
import stat

import pytest

from sage.history import (
    HistoryEntry,
    append_entry,
    calculate_usage,
    create_entry,
    get_recent_context,
    read_history,
)


@pytest.fixture
def mock_history_dir(tmp_path: Path):
    """Create a temporary history directory."""
    skill_dir = tmp_path / ".sage" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)

    with patch("sage.history.get_history_path", return_value=skill_dir / "history.jsonl"):
        yield skill_dir


class TestCreateEntry:
    """Tests for create_entry function."""

    def test_creates_entry_with_timestamp(self):
        """Entry has ISO timestamp."""
        entry = create_entry(
            entry_type="ask",
            query="test query",
            model="claude-sonnet",
            tokens_in=100,
            tokens_out=50,
        )

        assert entry.ts is not None
        assert "T" in entry.ts  # ISO format

    def test_calculates_cost(self):
        """Entry calculates estimated cost."""
        entry = create_entry(
            entry_type="ask",
            query="test",
            model="claude-sonnet",
            tokens_in=1000,
            tokens_out=500,
        )

        # Cost should be non-zero for non-zero tokens
        assert entry.cost > 0

    def test_includes_optional_fields(self):
        """Optional fields are preserved."""
        entry = create_entry(
            entry_type="research",
            query="test",
            model="claude-sonnet",
            tokens_in=100,
            tokens_out=50,
            searches=5,
            depth="deep",
            session="session-123",
        )

        assert entry.searches == 5
        assert entry.depth == "deep"
        assert entry.session == "session-123"


class TestAppendAndReadHistory:
    """Tests for append_entry and read_history functions."""

    def test_append_creates_file(self, mock_history_dir: Path):
        """Appending to non-existent file creates it."""
        entry = create_entry(
            entry_type="ask",
            query="test query",
            model="claude-sonnet",
            tokens_in=100,
            tokens_out=50,
        )

        append_entry("test-skill", entry)

        history_path = mock_history_dir / "history.jsonl"
        assert history_path.exists()

    def test_append_writes_json(self, mock_history_dir: Path):
        """Entries are written as valid JSON."""
        entry = create_entry(
            entry_type="ask",
            query="test query",
            model="claude-sonnet",
            tokens_in=100,
            tokens_out=50,
        )

        append_entry("test-skill", entry)

        history_path = mock_history_dir / "history.jsonl"
        content = history_path.read_text()
        data = json.loads(content.strip())

        assert data["query"] == "test query"
        assert data["tokens_in"] == 100

    def test_read_returns_entries(self, mock_history_dir: Path):
        """Read returns appended entries."""
        entry1 = create_entry("ask", "query 1", "model", 100, 50)
        entry2 = create_entry("ask", "query 2", "model", 200, 100)

        append_entry("test-skill", entry1)
        append_entry("test-skill", entry2)

        entries = read_history("test-skill")

        assert len(entries) == 2
        # Most recent first
        assert entries[0].query == "query 2"
        assert entries[1].query == "query 1"

    def test_read_with_limit(self, mock_history_dir: Path):
        """Read respects limit parameter."""
        for i in range(10):
            entry = create_entry("ask", f"query {i}", "model", 100, 50)
            append_entry("test-skill", entry)

        entries = read_history("test-skill", limit=3)

        assert len(entries) == 3

    def test_read_empty_file_returns_empty_list(self, mock_history_dir: Path):
        """Reading non-existent history returns empty list."""
        entries = read_history("test-skill")

        assert entries == []

    def test_file_permissions_restricted(self, mock_history_dir: Path):
        """History file has restricted permissions."""
        entry = create_entry("ask", "sensitive query", "model", 100, 50)
        append_entry("test-skill", entry)

        history_path = mock_history_dir / "history.jsonl"
        mode = history_path.stat().st_mode

        # Owner read/write only
        assert mode & stat.S_IRWXG == 0  # No group access
        assert mode & stat.S_IRWXO == 0  # No other access


class TestCalculateUsage:
    """Tests for calculate_usage function."""

    def test_empty_history_returns_zeros(self, mock_history_dir: Path):
        """Empty history returns zero usage."""
        usage = calculate_usage("test-skill")

        assert usage["tokens_in"] == 0
        assert usage["cost"] == 0.0
        assert usage["entries"] == 0

    def test_sums_tokens_and_cost(self, mock_history_dir: Path):
        """Usage sums tokens across entries."""
        entry1 = create_entry("ask", "q1", "model", 100, 50)
        entry2 = create_entry("ask", "q2", "model", 200, 100)

        append_entry("test-skill", entry1)
        append_entry("test-skill", entry2)

        usage = calculate_usage("test-skill", days=7)

        assert usage["tokens_in"] == 300
        assert usage["tokens_out"] == 150
        assert usage["entries"] == 2


class TestGetRecentContext:
    """Tests for get_recent_context function."""

    def test_returns_formatted_context(self, mock_history_dir: Path):
        """Returns simplified context format."""
        entry = create_entry("ask", "test query", "model", 100, 50)
        append_entry("test-skill", entry)

        context = get_recent_context("test-skill")

        assert len(context) == 1
        assert context[0]["query"] == "test query"
        assert context[0]["type"] == "ask"
        assert "ts" in context[0]


class TestHistoryEdgeCases:
    """Edge case tests for history module."""

    def test_handles_malformed_json_line(self, mock_history_dir: Path):
        """Malformed JSON lines cause error (no silent corruption)."""
        # First write a valid entry
        entry = create_entry("ask", "query", "model", 100, 50)
        append_entry("test-skill", entry)

        # Then append malformed JSON
        history_path = mock_history_dir / "history.jsonl"
        with open(history_path, "a") as f:
            f.write("not valid json at all\n")

        with pytest.raises(json.JSONDecodeError):
            read_history("test-skill")

    def test_handles_empty_lines(self, mock_history_dir: Path):
        """Empty lines in file are skipped."""
        entry = create_entry("ask", "query", "model", 100, 50)
        append_entry("test-skill", entry)

        # Add empty lines
        history_path = mock_history_dir / "history.jsonl"
        content = history_path.read_text()
        history_path.write_text(content + "\n\n\n")

        entries = read_history("test-skill")

        assert len(entries) == 1

    def test_none_values_excluded_from_json(self, mock_history_dir: Path):
        """None values are not written to JSON."""
        entry = create_entry("ask", "query", "model", 100, 50)  # response=None

        append_entry("test-skill", entry)

        history_path = mock_history_dir / "history.jsonl"
        content = history_path.read_text()
        data = json.loads(content.strip())

        assert "response" not in data  # None excluded
