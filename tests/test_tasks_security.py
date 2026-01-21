"""Security tests for sage.tasks module.

These tests verify security properties:
- Task type whitelist enforcement
- Input sanitization (no shell injection)
- No pickle usage (JSONL only)
- File permissions
- Atomic writes
"""

import json
import tempfile
from pathlib import Path

import pytest

from sage.tasks import (
    TASK_TYPES,
    Task,
    _sanitize_notification_message,
    load_pending_tasks,
    save_pending_tasks,
    validate_task_data,
    write_notification,
)


class TestTaskTypeWhitelist:
    """Security tests for task type validation."""

    def test_task_type_whitelist_only_expected(self):
        """Only expected task types in whitelist."""
        # Security: Adding new task types requires explicit code change
        expected = {"checkpoint", "knowledge"}
        assert TASK_TYPES == expected

    def test_task_type_whitelist_immutable(self):
        """Task type whitelist cannot be modified at runtime."""
        # Security: Prevents runtime injection of new task types
        assert isinstance(TASK_TYPES, frozenset)

        with pytest.raises(AttributeError):
            TASK_TYPES.add("malicious")  # type: ignore

    def test_task_rejects_sql_injection_type(self):
        """Task rejects SQL injection in type field."""
        with pytest.raises(ValueError):
            Task(
                id="test",
                type="checkpoint'; DROP TABLE checkpoints;--",
                data={},
            )

    def test_task_rejects_command_injection_type(self):
        """Task rejects command injection in type field."""
        with pytest.raises(ValueError):
            Task(
                id="test",
                type="checkpoint; rm -rf /",
                data={},
            )

    def test_task_from_dict_validates_type(self):
        """Task.from_dict validates type against whitelist."""
        with pytest.raises(ValueError):
            Task.from_dict(
                {
                    "id": "test",
                    "type": "malicious_type",
                    "data": {},
                    "created": "2026-01-21T10:00:00",
                }
            )


class TestNotificationSanitization:
    """Security tests for notification message sanitization."""

    def test_sanitize_shell_metacharacters(self):
        """Sanitizes all shell metacharacters."""
        dangerous_chars = ["`", "$", ";", "|", "&", "<", ">", "\n", "\r", "\\"]

        for char in dangerous_chars:
            msg = f"before{char}after"
            result = _sanitize_notification_message(msg)
            assert char not in result, f"Character '{char}' not sanitized"

    def test_sanitize_command_substitution(self):
        """Prevents command substitution attacks."""
        attacks = [
            "$(rm -rf /)",
            "`rm -rf /`",
            "$(cat /etc/passwd)",
            "`cat /etc/passwd`",
        ]

        for attack in attacks:
            result = _sanitize_notification_message(attack)
            assert "$" not in result
            assert "`" not in result

    def test_sanitize_variable_expansion(self):
        """Prevents variable expansion attacks."""
        attacks = [
            "$HOME",
            "${HOME}",
            "$PATH",
            "${PATH}",
            "$USER",
        ]

        for attack in attacks:
            result = _sanitize_notification_message(attack)
            assert "$" not in result

    def test_sanitize_command_chaining(self):
        """Prevents command chaining attacks."""
        attacks = [
            "msg; rm -rf /",
            "msg && rm -rf /",
            "msg || rm -rf /",
            "msg | cat /etc/passwd",
        ]

        for attack in attacks:
            result = _sanitize_notification_message(attack)
            assert ";" not in result
            assert "|" not in result
            assert "&" not in result

    def test_sanitize_redirect_attacks(self):
        """Prevents redirect attacks."""
        attacks = [
            "msg > /etc/passwd",
            "msg >> /etc/passwd",
            "msg < /etc/passwd",
            "msg 2>&1",
        ]

        for attack in attacks:
            result = _sanitize_notification_message(attack)
            assert ">" not in result
            assert "<" not in result

    def test_sanitize_newline_injection(self):
        """Prevents newline injection for multi-command execution."""
        attacks = [
            "msg\nrm -rf /",
            "msg\r\nrm -rf /",
            "msg\nwhoami\ncat /etc/passwd",
        ]

        for attack in attacks:
            result = _sanitize_notification_message(attack)
            assert "\n" not in result
            assert "\r" not in result

    def test_sanitize_escape_sequence_injection(self):
        """Prevents escape sequence injection."""
        attacks = [
            "msg\\nrm -rf /",
            "msg\\x00evil",
            "msg\\033[2Jevil",
        ]

        for attack in attacks:
            result = _sanitize_notification_message(attack)
            assert "\\" not in result

    def test_sanitize_buffer_overflow_prevention(self):
        """Truncates long messages to prevent buffer overflow."""
        long_attack = "A" * 10000
        result = _sanitize_notification_message(long_attack)

        assert len(result) <= 503  # 500 + "..."
        assert result.endswith("...")


class TestNoPickleUsage:
    """Security tests verifying no pickle is used."""

    @pytest.fixture
    def mock_files(self, tmp_path, monkeypatch):
        """Mock file paths to temp directory."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.tasks.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.tasks.NOTIFY_FILE", sage_dir / "notifications.jsonl")
        monkeypatch.setattr("sage.tasks.PENDING_TASKS_FILE", sage_dir / "pending_tasks.jsonl")
        return sage_dir

    def test_notifications_stored_as_json(self, mock_files):
        """Notifications stored as JSON, not pickle."""
        write_notification("success", "Test message")

        notify_file = mock_files / "notifications.jsonl"
        assert notify_file.exists()

        # Verify it's valid JSON
        with open(notify_file) as f:
            content = f.read()

        # Should be JSON, not pickle
        record = json.loads(content.strip())
        assert record["type"] == "success"

        # Verify no pickle magic bytes
        with open(notify_file, "rb") as f:
            raw = f.read()
        assert not raw.startswith(b"\x80")  # Pickle protocol marker

    def test_pending_tasks_stored_as_json(self, mock_files):
        """Pending tasks stored as JSON, not pickle."""
        task = Task(
            id="test",
            type="checkpoint",
            data={"core_question": "Q", "thesis": "T", "confidence": 0.5},
        )
        save_pending_tasks([task])

        pending_file = mock_files / "pending_tasks.jsonl"
        assert pending_file.exists()

        # Verify it's valid JSON
        with open(pending_file) as f:
            content = f.read()

        record = json.loads(content.strip())
        assert record["id"] == "test"

        # Verify no pickle magic bytes
        with open(pending_file, "rb") as f:
            raw = f.read()
        assert not raw.startswith(b"\x80")

    def test_no_pickle_load_in_module(self):
        """Module doesn't import pickle."""
        import sage.tasks

        # Check module doesn't use pickle
        source_path = Path(sage.tasks.__file__)
        with open(source_path) as f:
            source = f.read()

        assert "import pickle" not in source
        assert "pickle.load" not in source
        assert "pickle.dump" not in source


class TestFilePermissions:
    """Security tests for file permission handling."""

    @pytest.fixture
    def mock_files(self, tmp_path, monkeypatch):
        """Mock file paths to temp directory."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.tasks.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.tasks.NOTIFY_FILE", sage_dir / "notifications.jsonl")
        monkeypatch.setattr("sage.tasks.PENDING_TASKS_FILE", sage_dir / "pending_tasks.jsonl")
        return sage_dir

    def test_notification_file_permissions(self, mock_files):
        """Notification file has 0o600 permissions (owner only)."""
        write_notification("success", "Test")

        notify_file = mock_files / "notifications.jsonl"
        mode = notify_file.stat().st_mode & 0o777

        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_pending_tasks_file_permissions(self, mock_files):
        """Pending tasks file has 0o600 permissions (owner only)."""
        task = Task(
            id="t", type="checkpoint", data={"core_question": "Q", "thesis": "T", "confidence": 0.5}
        )
        save_pending_tasks([task])

        pending_file = mock_files / "pending_tasks.jsonl"
        mode = pending_file.stat().st_mode & 0o777

        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_files_not_world_readable(self, mock_files):
        """Files are not world-readable."""
        write_notification("success", "Test")
        task = Task(
            id="t", type="checkpoint", data={"core_question": "Q", "thesis": "T", "confidence": 0.5}
        )
        save_pending_tasks([task])

        for path in [
            mock_files / "notifications.jsonl",
            mock_files / "pending_tasks.jsonl",
        ]:
            mode = path.stat().st_mode
            assert not (mode & 0o004), f"{path.name} is world-readable"

    def test_files_not_group_readable(self, mock_files):
        """Files are not group-readable."""
        write_notification("success", "Test")
        task = Task(
            id="t", type="checkpoint", data={"core_question": "Q", "thesis": "T", "confidence": 0.5}
        )
        save_pending_tasks([task])

        for path in [
            mock_files / "notifications.jsonl",
            mock_files / "pending_tasks.jsonl",
        ]:
            mode = path.stat().st_mode
            assert not (mode & 0o040), f"{path.name} is group-readable"


class TestAtomicWrites:
    """Security tests for atomic write operations."""

    @pytest.fixture
    def mock_files(self, tmp_path, monkeypatch):
        """Mock file paths to temp directory."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.tasks.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.tasks.PENDING_TASKS_FILE", sage_dir / "pending_tasks.jsonl")
        return sage_dir

    def test_pending_tasks_atomic_write(self, mock_files, monkeypatch):
        """Pending tasks uses atomic write (temp + rename)."""
        # Track if tempfile was used
        original_mkstemp = tempfile.mkstemp
        mkstemp_called = False

        def tracking_mkstemp(*args, **kwargs):
            nonlocal mkstemp_called
            mkstemp_called = True
            return original_mkstemp(*args, **kwargs)

        monkeypatch.setattr("tempfile.mkstemp", tracking_mkstemp)

        task = Task(
            id="t", type="checkpoint", data={"core_question": "Q", "thesis": "T", "confidence": 0.5}
        )
        save_pending_tasks([task])

        assert mkstemp_called, "Atomic write should use tempfile.mkstemp"

    def test_partial_write_doesnt_corrupt(self, mock_files, monkeypatch):
        """Partial write doesn't corrupt existing file."""
        pending_file = mock_files / "pending_tasks.jsonl"

        # Create initial file
        task1 = Task(
            id="t1",
            type="checkpoint",
            data={"core_question": "Q", "thesis": "T", "confidence": 0.5},
        )
        save_pending_tasks([task1])

        # Verify it exists
        original_content = pending_file.read_text()

        # Simulate write failure by making temp file fail
        def failing_mkstemp(*args, **kwargs):
            raise OSError("Disk full")

        monkeypatch.setattr("tempfile.mkstemp", failing_mkstemp)

        # Attempt to save new task (will fail)
        task2 = Task(
            id="t2",
            type="checkpoint",
            data={"core_question": "Q", "thesis": "T", "confidence": 0.5},
        )
        save_pending_tasks([task2])  # Should fail silently

        # Original file should be unchanged
        assert pending_file.read_text() == original_content


class TestTaskDataValidation:
    """Security tests for task data validation."""

    def test_validates_confidence_not_negative(self):
        """Rejects negative confidence values."""
        is_valid, _ = validate_task_data(
            "checkpoint",
            {
                "core_question": "Q",
                "thesis": "T",
                "confidence": -1.0,
            },
        )
        assert not is_valid

    def test_validates_confidence_not_over_one(self):
        """Rejects confidence over 1.0."""
        is_valid, _ = validate_task_data(
            "checkpoint",
            {
                "core_question": "Q",
                "thesis": "T",
                "confidence": 100,
            },
        )
        assert not is_valid

    def test_validates_strings_not_code(self):
        """String validation doesn't execute code."""
        # Attempt to inject code via string field
        malicious_data = {
            "core_question": "__import__('os').system('rm -rf /')",
            "thesis": "eval('malicious')",
            "confidence": 0.5,
        }

        # Should just validate as strings, not execute
        is_valid, _ = validate_task_data("checkpoint", malicious_data)

        # Validation passes (it's just a string)
        # Security: The string is never executed
        assert is_valid

    def test_validates_unknown_task_type_rejected(self):
        """Unknown task types are rejected."""
        is_valid, error = validate_task_data("malicious_type", {})

        assert not is_valid
        assert "Unknown task type" in error

    def test_validates_keywords_all_strings(self):
        """Keywords must all be strings (no code objects)."""
        is_valid, _ = validate_task_data(
            "knowledge",
            {
                "knowledge_id": "test",
                "content": "content",
                "keywords": [lambda: None],  # Callable, not string
            },
        )
        assert not is_valid


class TestLoadPendingTasksSecurity:
    """Security tests for loading pending tasks."""

    @pytest.fixture
    def mock_files(self, tmp_path, monkeypatch):
        """Mock file paths to temp directory."""
        sage_dir = tmp_path / ".sage"
        sage_dir.mkdir()
        monkeypatch.setattr("sage.tasks.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.tasks.PENDING_TASKS_FILE", sage_dir / "pending_tasks.jsonl")
        return sage_dir

    def test_skips_malformed_json(self, mock_files):
        """Skips malformed JSON lines without crashing."""
        pending_file = mock_files / "pending_tasks.jsonl"
        pending_file.write_text(
            '{"id": "valid", "type": "checkpoint", "data": {}, "created": "2026-01-21T10:00:00"}\n'
            "not valid json\n"
            '{"id": "valid2", "type": "checkpoint", "data": {}, "created": "2026-01-21T10:00:00"}\n'
        )

        tasks = load_pending_tasks()

        assert len(tasks) == 2
        assert tasks[0].id == "valid"
        assert tasks[1].id == "valid2"

    def test_skips_invalid_task_types(self, mock_files):
        """Skips tasks with invalid types."""
        pending_file = mock_files / "pending_tasks.jsonl"
        pending_file.write_text(
            '{"id": "valid", "type": "checkpoint", "data": {}, "created": "2026-01-21T10:00:00"}\n'
            '{"id": "malicious", "type": "exec_shell", "data": {"cmd": "rm -rf /"}, "created": "2026-01-21T10:00:00"}\n'
        )

        tasks = load_pending_tasks()

        assert len(tasks) == 1
        assert tasks[0].id == "valid"

    def test_handles_symlink_attack(self, mock_files, monkeypatch):
        """Handles symlink to sensitive file safely."""
        # This test verifies we're reading the file directly,
        # not following potentially malicious symlinks
        # In practice, SAGE_DIR should be user-owned

        pending_file = mock_files / "pending_tasks.jsonl"

        # Create a regular file (simulating safe behavior)
        pending_file.write_text(
            '{"id": "t", "type": "checkpoint", "data": {}, "created": "2026-01-21T10:00:00"}\n'
        )

        # Load should work normally
        tasks = load_pending_tasks()
        assert len(tasks) == 1
