"""Tests for sage.tasks module - Task/TaskResult dataclasses and notification system."""

import json
import os
from datetime import datetime

import pytest

from sage.tasks import (
    TASK_TYPES,
    Task,
    TaskResult,
    _sanitize_notification_message,
    cleanup_old_task_files,
    cleanup_task_files,
    clear_notifications,
    clear_pending_tasks,
    generate_task_id,
    get_task_paths,
    is_task_complete,
    load_pending_tasks,
    read_notifications,
    read_task_result,
    save_pending_tasks,
    validate_checkpoint_data,
    validate_knowledge_data,
    validate_task_data,
    write_notification,
    write_task_result,
)


class TestTaskDataclass:
    """Tests for Task dataclass."""

    def test_task_is_frozen(self):
        """Task is immutable (frozen dataclass)."""
        task = Task(
            id="test-123",
            type="checkpoint",
            data={"key": "value"},
        )

        with pytest.raises(AttributeError):
            task.id = "new-id"

    def test_task_valid_types(self):
        """Task accepts valid types."""
        for task_type in TASK_TYPES:
            task = Task(
                id="test",
                type=task_type,
                data={},
            )
            assert task.type == task_type

    def test_task_rejects_invalid_type(self):
        """Task rejects invalid type."""
        with pytest.raises(ValueError) as exc_info:
            Task(
                id="test",
                type="invalid_type",
                data={},
            )

        assert "Invalid task type" in str(exc_info.value)
        assert "invalid_type" in str(exc_info.value)

    def test_task_has_created_timestamp(self):
        """Task has created timestamp by default."""
        before = datetime.now()
        task = Task(id="test", type="checkpoint", data={})
        after = datetime.now()

        assert before <= task.created <= after

    def test_task_to_dict(self):
        """Task serializes to dict."""
        task = Task(
            id="task_123",
            type="knowledge",
            data={"content": "test"},
        )

        d = task.to_dict()

        assert d["id"] == "task_123"
        assert d["type"] == "knowledge"
        assert d["data"] == {"content": "test"}
        assert "created" in d

    def test_task_from_dict(self):
        """Task deserializes from dict."""
        data = {
            "id": "task_456",
            "type": "checkpoint",
            "data": {"thesis": "test"},
            "created": "2026-01-21T10:30:00",
        }

        task = Task.from_dict(data)

        assert task.id == "task_456"
        assert task.type == "checkpoint"
        assert task.data == {"thesis": "test"}
        assert task.created.hour == 10

    def test_task_from_dict_rejects_missing_fields(self):
        """Task.from_dict rejects missing required fields."""
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict({"id": "test"})

        assert "Missing required fields" in str(exc_info.value)

    def test_task_from_dict_rejects_invalid_type(self):
        """Task.from_dict rejects invalid type."""
        with pytest.raises(ValueError) as exc_info:
            Task.from_dict(
                {
                    "id": "test",
                    "type": "invalid",
                    "data": {},
                    "created": "2026-01-21T10:00:00",
                }
            )

        assert "Invalid task type" in str(exc_info.value)

    def test_task_roundtrip(self):
        """Task survives serialization roundtrip."""
        original = Task(
            id="roundtrip-test",
            type="checkpoint",
            data={"core_question": "test?"},
        )

        serialized = original.to_dict()
        restored = Task.from_dict(serialized)

        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.data == original.data


class TestTaskResult:
    """Tests for TaskResult dataclass."""

    def test_task_result_success(self):
        """TaskResult represents success."""
        result = TaskResult(
            task_id="task_123",
            status="success",
            message="Checkpoint saved",
        )

        assert result.status == "success"
        assert result.error is None

    def test_task_result_failed(self):
        """TaskResult represents failure with error."""
        result = TaskResult(
            task_id="task_456",
            status="failed",
            message="Save failed",
            error="Disk full",
        )

        assert result.status == "failed"
        assert result.error == "Disk full"


class TestGenerateTaskId:
    """Tests for task ID generation."""

    def test_generate_task_id_format(self):
        """Task ID has expected format."""
        task_id = generate_task_id()

        assert task_id.startswith("task_")
        parts = task_id.split("_")
        assert len(parts) == 4  # task, date, time, uuid

    def test_generate_task_id_unique(self):
        """Task IDs are unique."""
        ids = [generate_task_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestNotificationSystem:
    """Tests for notification file system."""

    @pytest.fixture
    def mock_notify_file(self, tmp_path, monkeypatch):
        """Mock notification file to temp directory."""
        notify_file = tmp_path / "notifications.jsonl"
        monkeypatch.setattr("sage.tasks.NOTIFY_FILE", notify_file)
        monkeypatch.setattr("sage.tasks.SAGE_DIR", tmp_path)
        return notify_file

    def test_write_notification_creates_file(self, mock_notify_file):
        """write_notification creates JSONL file."""
        write_notification("success", "Test message")

        assert mock_notify_file.exists()

    def test_write_notification_jsonl_format(self, mock_notify_file):
        """Notification is valid JSONL."""
        write_notification("success", "Test message")

        with open(mock_notify_file) as f:
            record = json.loads(f.readline())

        assert record["type"] == "success"
        assert record["msg"] == "Test message"
        assert "ts" in record

    def test_write_notification_appends(self, mock_notify_file):
        """Multiple notifications append to file."""
        write_notification("success", "First")
        write_notification("error", "Second")

        records = read_notifications()

        assert len(records) == 2
        assert records[0]["msg"] == "First"
        assert records[1]["msg"] == "Second"

    def test_write_notification_file_permissions(self, mock_notify_file):
        """Notification file has 0o600 permissions."""
        write_notification("success", "Test")

        mode = mock_notify_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_read_notifications_empty(self, mock_notify_file):
        """read_notifications returns empty list for missing file."""
        records = read_notifications()
        assert records == []

    def test_clear_notifications(self, mock_notify_file):
        """clear_notifications removes file."""
        write_notification("success", "Test")
        assert mock_notify_file.exists()

        clear_notifications()

        assert not mock_notify_file.exists()


class TestNotificationSanitization:
    """Tests for notification message sanitization."""

    def test_sanitize_removes_backticks(self):
        """Sanitizes backticks to prevent shell injection."""
        result = _sanitize_notification_message("Hello `rm -rf /`")
        assert "`" not in result

    def test_sanitize_removes_dollar_signs(self):
        """Sanitizes dollar signs to prevent variable expansion."""
        result = _sanitize_notification_message("$HOME is $(whoami)")
        assert "$" not in result

    def test_sanitize_removes_semicolons(self):
        """Sanitizes semicolons to prevent command chaining."""
        result = _sanitize_notification_message("msg; rm -rf /")
        assert ";" not in result

    def test_sanitize_removes_pipes(self):
        """Sanitizes pipes to prevent piping."""
        result = _sanitize_notification_message("msg | evil")
        assert "|" not in result

    def test_sanitize_removes_ampersands(self):
        """Sanitizes ampersands to prevent background execution."""
        result = _sanitize_notification_message("msg & evil")
        assert "&" not in result

    def test_sanitize_removes_redirects(self):
        """Sanitizes redirects to prevent file overwriting."""
        result = _sanitize_notification_message("msg > /etc/passwd")
        assert ">" not in result
        assert "<" not in result

    def test_sanitize_removes_newlines(self):
        """Sanitizes newlines to prevent multi-line injection."""
        result = _sanitize_notification_message("msg\nrm -rf /")
        assert "\n" not in result
        assert "\r" not in result

    def test_sanitize_removes_backslashes(self):
        """Sanitizes backslashes to prevent escape sequences."""
        result = _sanitize_notification_message("msg\\nrm")
        assert "\\" not in result

    def test_sanitize_truncates_long_messages(self):
        """Truncates messages over 500 characters."""
        long_msg = "A" * 600
        result = _sanitize_notification_message(long_msg)

        assert len(result) == 503  # 500 + "..."
        assert result.endswith("...")

    def test_sanitize_preserves_safe_characters(self):
        """Preserves alphanumeric and common punctuation."""
        safe_msg = "Checkpoint saved: auth-jwt (85% confidence)"
        result = _sanitize_notification_message(safe_msg)

        assert result == safe_msg


class TestPendingTasksPersistence:
    """Tests for pending task save/load."""

    @pytest.fixture
    def mock_pending_file(self, tmp_path, monkeypatch):
        """Mock pending tasks file to temp directory."""
        pending_file = tmp_path / "pending_tasks.jsonl"
        monkeypatch.setattr("sage.tasks.PENDING_TASKS_FILE", pending_file)
        monkeypatch.setattr("sage.tasks.SAGE_DIR", tmp_path)
        return pending_file

    def test_save_pending_tasks_creates_file(self, mock_pending_file):
        """save_pending_tasks creates JSONL file."""
        tasks = [
            Task(id="task_1", type="checkpoint", data={}),
            Task(id="task_2", type="knowledge", data={}),
        ]

        save_pending_tasks(tasks)

        assert mock_pending_file.exists()

    def test_save_pending_tasks_jsonl_format(self, mock_pending_file):
        """Pending tasks stored as valid JSONL."""
        task = Task(id="task_1", type="checkpoint", data={"test": True})
        save_pending_tasks([task])

        with open(mock_pending_file) as f:
            record = json.loads(f.readline())

        assert record["id"] == "task_1"
        assert record["type"] == "checkpoint"

    def test_save_pending_tasks_file_permissions(self, mock_pending_file):
        """Pending tasks file has 0o600 permissions."""
        save_pending_tasks([Task(id="t", type="checkpoint", data={})])

        mode = mock_pending_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_load_pending_tasks_roundtrip(self, mock_pending_file):
        """Tasks survive save/load roundtrip."""
        original = [
            Task(id="task_1", type="checkpoint", data={"thesis": "test"}),
            Task(id="task_2", type="knowledge", data={"content": "data"}),
        ]

        save_pending_tasks(original)
        loaded = load_pending_tasks()

        assert len(loaded) == 2
        assert loaded[0].id == "task_1"
        assert loaded[1].type == "knowledge"

    def test_load_pending_tasks_empty(self, mock_pending_file):
        """load_pending_tasks returns empty list for missing file."""
        tasks = load_pending_tasks()
        assert tasks == []

    def test_load_pending_tasks_skips_invalid(self, mock_pending_file):
        """load_pending_tasks skips invalid records."""
        # Write mix of valid and invalid
        with open(mock_pending_file, "w") as f:
            f.write(
                '{"id": "valid", "type": "checkpoint", "data": {}, "created": "2026-01-21T10:00:00"}\n'
            )
            f.write('{"invalid": "record"}\n')
            f.write(
                '{"id": "valid2", "type": "knowledge", "data": {}, "created": "2026-01-21T10:00:00"}\n'
            )

        tasks = load_pending_tasks()

        assert len(tasks) == 2
        assert tasks[0].id == "valid"
        assert tasks[1].id == "valid2"

    def test_clear_pending_tasks(self, mock_pending_file):
        """clear_pending_tasks removes file."""
        save_pending_tasks([Task(id="t", type="checkpoint", data={})])
        assert mock_pending_file.exists()

        clear_pending_tasks()

        assert not mock_pending_file.exists()

    def test_save_pending_tasks_empty_does_nothing(self, mock_pending_file):
        """Saving empty list doesn't create file."""
        save_pending_tasks([])
        assert not mock_pending_file.exists()


class TestTaskDataValidation:
    """Tests for task data validation."""

    def test_validate_checkpoint_data_valid(self):
        """Valid checkpoint data passes."""
        data = {
            "core_question": "How to auth?",
            "thesis": "Use JWT.",
            "confidence": 0.8,
        }

        is_valid, error = validate_checkpoint_data(data)

        assert is_valid
        assert error == ""

    def test_validate_checkpoint_data_missing_fields(self):
        """Rejects checkpoint missing required fields."""
        data = {"thesis": "Test"}

        is_valid, error = validate_checkpoint_data(data)

        assert not is_valid
        assert "Missing required fields" in error

    def test_validate_checkpoint_data_invalid_confidence_type(self):
        """Rejects non-numeric confidence."""
        data = {
            "core_question": "Q",
            "thesis": "T",
            "confidence": "high",
        }

        is_valid, error = validate_checkpoint_data(data)

        assert not is_valid
        assert "number" in error.lower()

    def test_validate_checkpoint_data_confidence_range(self):
        """Rejects confidence outside 0-1 range."""
        data = {
            "core_question": "Q",
            "thesis": "T",
            "confidence": 1.5,
        }

        is_valid, error = validate_checkpoint_data(data)

        assert not is_valid
        assert "0.0 and 1.0" in error

    def test_validate_checkpoint_data_string_fields(self):
        """Rejects non-string core_question/thesis."""
        data = {
            "core_question": 123,
            "thesis": "T",
            "confidence": 0.5,
        }

        is_valid, error = validate_checkpoint_data(data)

        assert not is_valid
        assert "string" in error.lower()

    def test_validate_knowledge_data_valid(self):
        """Valid knowledge data passes."""
        data = {
            "knowledge_id": "test-id",
            "content": "Test content",
            "keywords": ["test", "keyword"],
        }

        is_valid, error = validate_knowledge_data(data)

        assert is_valid
        assert error == ""

    def test_validate_knowledge_data_missing_fields(self):
        """Rejects knowledge missing required fields."""
        data = {"content": "Test"}

        is_valid, error = validate_knowledge_data(data)

        assert not is_valid
        assert "Missing required fields" in error

    def test_validate_knowledge_data_keywords_list(self):
        """Rejects non-list keywords."""
        data = {
            "knowledge_id": "test",
            "content": "content",
            "keywords": "not-a-list",
        }

        is_valid, error = validate_knowledge_data(data)

        assert not is_valid
        assert "list" in error.lower()

    def test_validate_knowledge_data_keywords_strings(self):
        """Rejects non-string keywords."""
        data = {
            "knowledge_id": "test",
            "content": "content",
            "keywords": ["valid", 123],
        }

        is_valid, error = validate_knowledge_data(data)

        assert not is_valid
        assert "strings" in error.lower()

    def test_validate_task_data_dispatches_to_checkpoint(self):
        """validate_task_data dispatches to checkpoint validator."""
        data = {
            "core_question": "Q",
            "thesis": "T",
            "confidence": 0.5,
        }

        is_valid, error = validate_task_data("checkpoint", data)

        assert is_valid

    def test_validate_task_data_dispatches_to_knowledge(self):
        """validate_task_data dispatches to knowledge validator."""
        data = {
            "knowledge_id": "id",
            "content": "content",
            "keywords": ["kw"],
        }

        is_valid, error = validate_task_data("knowledge", data)

        assert is_valid

    def test_validate_task_data_unknown_type(self):
        """validate_task_data rejects unknown type."""
        is_valid, error = validate_task_data("unknown", {})

        assert not is_valid
        assert "Unknown task type" in error


class TestTaskTypesWhitelist:
    """Tests for task type whitelist security."""

    def test_task_types_is_frozenset(self):
        """TASK_TYPES is immutable."""
        assert isinstance(TASK_TYPES, frozenset)

    def test_task_types_only_expected(self):
        """Only expected task types in whitelist."""
        expected = {"checkpoint", "knowledge"}
        assert TASK_TYPES == expected

    def test_cannot_modify_task_types(self):
        """Cannot add to TASK_TYPES."""
        with pytest.raises(AttributeError):
            TASK_TYPES.add("evil")  # type: ignore


class TestBashWatcherTaskResults:
    """Tests for bash watcher task result files."""

    @pytest.fixture
    def mock_tasks_dir(self, tmp_path, monkeypatch):
        """Mock tasks directory to temp directory."""
        tasks_dir = tmp_path / "tasks"
        monkeypatch.setattr("sage.tasks.TASKS_DIR", tasks_dir)
        monkeypatch.setattr("sage.tasks.SAGE_DIR", tmp_path)
        return tasks_dir

    def test_write_task_result_creates_files(self, mock_tasks_dir):
        """write_task_result creates .result and .done files."""
        write_task_result("task_123", "success", "Test message")

        result_file = mock_tasks_dir / "task_123.result"
        done_file = mock_tasks_dir / "task_123.done"

        assert result_file.exists()
        assert done_file.exists()

    def test_write_task_result_json_format(self, mock_tasks_dir):
        """Task result is valid JSON."""
        write_task_result("task_456", "success", "Checkpoint saved")

        result_file = mock_tasks_dir / "task_456.result"
        with open(result_file) as f:
            data = json.load(f)

        assert data["task_id"] == "task_456"
        assert data["status"] == "success"
        assert data["message"] == "Checkpoint saved"
        assert "ts" in data

    def test_write_task_result_with_error(self, mock_tasks_dir):
        """Task result includes error field for failures."""
        write_task_result("task_789", "failed", "Save failed", error="Disk full")

        result_file = mock_tasks_dir / "task_789.result"
        with open(result_file) as f:
            data = json.load(f)

        assert data["status"] == "failed"
        assert data["error"] == "Disk full"

    def test_write_task_result_file_permissions(self, mock_tasks_dir):
        """Task result files have 0o600 permissions."""
        write_task_result("task-perms", "success", "Test")

        result_file = mock_tasks_dir / "task-perms.result"
        done_file = mock_tasks_dir / "task-perms.done"

        assert result_file.stat().st_mode & 0o777 == 0o600
        assert done_file.stat().st_mode & 0o777 == 0o600

    def test_write_task_result_sanitizes_message(self, mock_tasks_dir):
        """Task result message is sanitized."""
        write_task_result("task-safe", "success", "Test `rm -rf /` $HOME")

        result_file = mock_tasks_dir / "task-safe.result"
        with open(result_file) as f:
            data = json.load(f)

        assert "`" not in data["message"]
        assert "$" not in data["message"]

    def test_read_task_result_returns_data(self, mock_tasks_dir):
        """read_task_result reads result file."""
        write_task_result("task-read", "success", "Test message")

        result = read_task_result("task-read")

        assert result is not None
        assert result["task_id"] == "task-read"
        assert result["status"] == "success"

    def test_read_task_result_missing_returns_none(self, mock_tasks_dir):
        """read_task_result returns None for missing file."""
        result = read_task_result("nonexistent")
        assert result is None

    def test_is_task_complete_true(self, mock_tasks_dir):
        """is_task_complete returns True when .done exists."""
        write_task_result("task-done", "success", "Done")

        assert is_task_complete("task-done") is True

    def test_is_task_complete_false(self, mock_tasks_dir):
        """is_task_complete returns False when .done doesn't exist."""
        assert is_task_complete("task-pending") is False

    def test_cleanup_task_files(self, mock_tasks_dir):
        """cleanup_task_files removes result and done files."""
        write_task_result("task-cleanup", "success", "Test")

        result_file = mock_tasks_dir / "task-cleanup.result"
        done_file = mock_tasks_dir / "task-cleanup.done"
        assert result_file.exists()
        assert done_file.exists()

        cleanup_task_files("task-cleanup")

        assert not result_file.exists()
        assert not done_file.exists()


class TestGetTaskPaths:
    """Tests for task path generation."""

    @pytest.fixture
    def mock_tasks_dir(self, tmp_path, monkeypatch):
        """Mock tasks directory."""
        tasks_dir = tmp_path / "tasks"
        monkeypatch.setattr("sage.tasks.TASKS_DIR", tasks_dir)
        return tasks_dir

    def test_get_task_paths_returns_dict(self, mock_tasks_dir):
        """Returns dict with expected keys."""
        paths = get_task_paths("task_123")

        assert isinstance(paths, dict)
        assert "task_id" in paths
        assert "done_file" in paths
        assert "result_file" in paths

    def test_get_task_paths_contains_task_id(self, mock_tasks_dir):
        """Paths include task ID."""
        paths = get_task_paths("task_123")

        assert paths["task_id"] == "task_123"
        assert "task_123" in paths["done_file"]
        assert "task_123" in paths["result_file"]

    def test_get_task_paths_done_file_extension(self, mock_tasks_dir):
        """Done file has .done extension."""
        paths = get_task_paths("task_456")

        assert paths["done_file"].endswith(".done")

    def test_get_task_paths_result_file_extension(self, mock_tasks_dir):
        """Result file has .result extension."""
        paths = get_task_paths("task_789")

        assert paths["result_file"].endswith(".result")


class TestCleanupOldTaskFiles:
    """Tests for old task file cleanup."""

    @pytest.fixture
    def mock_tasks_dir(self, tmp_path, monkeypatch):
        """Mock tasks directory with some old files."""
        tasks_dir = tmp_path / "tasks"
        tasks_dir.mkdir()
        monkeypatch.setattr("sage.tasks.TASKS_DIR", tasks_dir)
        return tasks_dir

    def test_cleanup_removes_old_files(self, mock_tasks_dir):
        """cleanup_old_task_files removes old files."""
        # Create a file and backdate its mtime
        old_file = mock_tasks_dir / "old-task.result"
        old_file.write_text("{}")
        old_done = mock_tasks_dir / "old-task.done"
        old_done.touch()

        # Backdate files to 48 hours ago
        import time

        old_time = time.time() - (48 * 3600)
        os.utime(old_file, (old_time, old_time))
        os.utime(old_done, (old_time, old_time))

        cleaned = cleanup_old_task_files(max_age_hours=24)

        assert cleaned == 2
        assert not old_file.exists()
        assert not old_done.exists()

    def test_cleanup_keeps_recent_files(self, mock_tasks_dir):
        """cleanup_old_task_files keeps recent files."""
        recent_file = mock_tasks_dir / "recent-task.result"
        recent_file.write_text("{}")
        recent_done = mock_tasks_dir / "recent-task.done"
        recent_done.touch()

        cleaned = cleanup_old_task_files(max_age_hours=24)

        assert cleaned == 0
        assert recent_file.exists()
        assert recent_done.exists()

    def test_cleanup_returns_count(self, mock_tasks_dir):
        """cleanup_old_task_files returns cleanup count."""
        cleaned = cleanup_old_task_files(max_age_hours=24)
        assert cleaned == 0

    def test_cleanup_handles_missing_dir(self, tmp_path, monkeypatch):
        """cleanup_old_task_files handles missing directory."""
        nonexistent = tmp_path / "nonexistent"
        monkeypatch.setattr("sage.tasks.TASKS_DIR", nonexistent)

        cleaned = cleanup_old_task_files()

        assert cleaned == 0
