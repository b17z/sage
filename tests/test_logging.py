"""Tests for sage.logging module.

Tests cover:
- Sensitive data sanitization (API keys, tokens, secrets)
- Path sanitization (home directory replacement)
- Content field redaction
- Log file permissions
- JSON formatting
- Convenience logging functions
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unittest.mock import patch

from sage.logging import (
    REDACTED_FIELDS,
    SecureJSONFormatter,
    _contains_sensitive_data,
    _sanitize_path,
    _sanitize_value,
    get_logger,
    log_checkpoint_saved,
    log_config_loaded,
    log_event,
    log_knowledge_saved,
    log_task_completed,
    log_task_failed,
    log_task_queued,
    log_task_started,
)


class TestSanitizePath:
    """Tests for path sanitization."""

    def test_replaces_home_directory(self):
        """Home directory should be replaced with ~."""
        home = os.path.expanduser("~")
        path = f"{home}/some/path/file.txt"
        result = _sanitize_path(path)
        assert result == "~/some/path/file.txt"
        assert home not in result

    def test_preserves_non_home_paths(self):
        """Paths not under home should remain unchanged."""
        path = "/tmp/some/file.txt"
        result = _sanitize_path(path)
        assert result == "/tmp/some/file.txt"

    def test_handles_path_objects(self):
        """Should handle Path objects."""
        home = Path.home()
        path = home / "test" / "file.py"
        result = _sanitize_path(path)
        assert result == "~/test/file.py"

    def test_handles_exact_home_path(self):
        """Should handle the home directory itself."""
        home = os.path.expanduser("~")
        result = _sanitize_path(home)
        assert result == "~"


class TestContainsSensitiveData:
    """Tests for sensitive data detection."""

    def test_detects_api_keys(self):
        """Should detect API key patterns."""
        # Pattern expects sk- followed by 20+ alphanumeric chars
        assert _contains_sensitive_data("sk-abcdefghijklmnopqrstuvwxyz1234")
        assert _contains_sensitive_data("my key is sk-12345678901234567890")

    def test_detects_api_key_mentions(self):
        """Should detect mentions of api_key."""
        assert _contains_sensitive_data("set the api_key value")
        assert _contains_sensitive_data("API-KEY is required")

    def test_detects_token_mentions(self):
        """Should detect token-related strings."""
        assert _contains_sensitive_data("access token required")
        assert _contains_sensitive_data("TOKEN_VALUE")

    def test_detects_secret_mentions(self):
        """Should detect secret-related strings."""
        assert _contains_sensitive_data("client_secret value")
        assert _contains_sensitive_data("SECRET_KEY")

    def test_detects_password_mentions(self):
        """Should detect password-related strings."""
        assert _contains_sensitive_data("password: hunter2")
        assert _contains_sensitive_data("PASSWORD_HASH")

    def test_detects_credential_mentions(self):
        """Should detect credential-related strings."""
        assert _contains_sensitive_data("credential file path")
        assert _contains_sensitive_data("CREDENTIAL_PATH")

    def test_allows_normal_strings(self):
        """Should allow normal strings without sensitive patterns."""
        assert not _contains_sensitive_data("hello world")
        assert not _contains_sensitive_data("checkpoint saved successfully")
        assert not _contains_sensitive_data("task_20260121_143052_a1b2c3d4")

    def test_handles_non_strings(self):
        """Should return False for non-strings."""
        assert not _contains_sensitive_data(123)
        assert not _contains_sensitive_data(None)
        assert not _contains_sensitive_data(["list"])


class TestSanitizeValue:
    """Tests for value sanitization."""

    def test_redacts_known_sensitive_fields(self):
        """Known sensitive fields should be redacted."""
        for field in ["thesis", "content", "query", "api_key", "token", "secret"]:
            result = _sanitize_value(field, "some value")
            assert "[REDACTED:" in result
            assert "some value" not in result

    def test_redacts_with_length_info(self):
        """Redacted strings should include length."""
        result = _sanitize_value("thesis", "A" * 50)
        assert "[REDACTED:50 chars]" in result

    def test_redacts_list_fields(self):
        """Redacted lists should show type."""
        result = _sanitize_value("sources", [{"id": "1"}, {"id": "2"}])
        assert "[REDACTED:list]" in result

    def test_redacts_dict_fields(self):
        """Redacted dicts should show type."""
        result = _sanitize_value("tensions", {"a": 1, "b": 2})
        assert "[REDACTED:dict]" in result

    def test_detects_sensitive_in_value(self):
        """Should detect sensitive data in values."""
        result = _sanitize_value("config", "api_key=sk-12345678901234567890")
        assert "[REDACTED:sensitive]" in result

    def test_sanitizes_paths_in_values(self):
        """Paths in string values should be sanitized."""
        home = os.path.expanduser("~")
        result = _sanitize_value("file", f"{home}/project/file.py")
        assert "~" in result
        assert home not in result

    def test_truncates_long_strings(self):
        """Long strings should be truncated."""
        long_value = "x" * 500
        result = _sanitize_value("description", long_value)
        assert "...[truncated:" in result
        assert len(result) < len(long_value)

    def test_preserves_short_strings(self):
        """Short strings should be preserved."""
        result = _sanitize_value("status", "success")
        assert result == "success"

    def test_handles_nested_dicts(self):
        """Nested dicts should be recursively sanitized."""
        data = {
            "outer": {
                "thesis": "secret thesis",
                "normal": "value",
            }
        }
        result = _sanitize_value("data", data)
        assert "[REDACTED:" in result["outer"]["thesis"]
        assert result["outer"]["normal"] == "value"

    def test_handles_lists(self):
        """Lists should be sanitized."""
        data = ["item1", "item2", "item3"]
        result = _sanitize_value("items", data)
        assert result == ["item1", "item2", "item3"]

    def test_truncates_long_lists(self):
        """Long lists should be truncated."""
        data = list(range(50))
        result = _sanitize_value("items", data)
        assert "[list:50 items]" in result

    def test_handles_path_objects(self):
        """Path objects should be sanitized."""
        path = Path.home() / "project" / "file.py"
        result = _sanitize_value("path", path)
        assert result == "~/project/file.py"


class TestSecureJSONFormatter:
    """Tests for SecureJSONFormatter."""

    def test_formats_as_json(self):
        """Output should be valid JSON."""
        formatter = SecureJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["message"] == "Test message"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test"
        assert "ts" in parsed

    def test_includes_extra_fields(self):
        """Extra fields should be included and sanitized."""
        formatter = SecureJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Task completed",
            args=(),
            exc_info=None,
        )
        record.task_id = "task_123"
        record.duration_ms = 150
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["task_id"] == "task_123"
        assert parsed["duration_ms"] == 150

    def test_sanitizes_extra_fields(self):
        """Extra fields should be sanitized."""
        formatter = SecureJSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Checkpoint saved",
            args=(),
            exc_info=None,
        )
        record.thesis = "This is the secret thesis content"
        result = formatter.format(record)
        parsed = json.loads(result)
        assert "[REDACTED:" in parsed["thesis"]
        assert "secret thesis" not in result

    def test_includes_exception_info(self):
        """Exception info should be included."""
        formatter = SecureJSONFormatter()
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["error"]["type"] == "ValueError"
        assert "Test error" in parsed["error"]["message"]


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_logger(self):
        """Should return a logger instance."""
        logger = get_logger("test.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "test.module"

    def test_logger_has_handler(self):
        """Logger should have file handler attached."""
        logger = get_logger("test.handler")
        # At least one handler should be present
        assert len(logger.handlers) > 0


class TestLogEvent:
    """Tests for log_event function."""

    def test_logs_event(self):
        """Should log event with extra fields."""
        with patch("sage.logging.get_logger") as mock_get_logger:
            mock_logger = mock_get_logger.return_value
            log_event("test_event", task_id="task_123", status="success")
            mock_logger.info.assert_called()


class TestConvenienceFunctions:
    """Tests for convenience logging functions."""

    def test_log_task_queued(self):
        """Should log task queued event."""
        with patch("sage.logging.log_event") as mock_log:
            log_task_queued("task_123", "checkpoint")
            mock_log.assert_called_once_with(
                "task_queued", task_id="task_123", task_type="checkpoint"
            )

    def test_log_task_started(self):
        """Should log task started event."""
        with patch("sage.logging.log_event") as mock_log:
            log_task_started("task_123", "knowledge")
            mock_log.assert_called_once_with(
                "task_started", task_id="task_123", task_type="knowledge"
            )

    def test_log_task_completed(self):
        """Should log task completed event."""
        with patch("sage.logging.log_event") as mock_log:
            log_task_completed("task_123", "checkpoint", 150)
            mock_log.assert_called_once_with(
                "task_completed",
                task_id="task_123",
                task_type="checkpoint",
                duration_ms=150,
            )

    def test_log_task_failed(self):
        """Should log task failed event with truncated error."""
        with patch("sage.logging.log_event") as mock_log:
            log_task_failed("task_123", "checkpoint", "Short error")
            mock_log.assert_called_once_with(
                "task_failed",
                level="ERROR",
                task_id="task_123",
                task_type="checkpoint",
                error="Short error",
            )

    def test_log_task_failed_truncates_long_error(self):
        """Should truncate long error messages."""
        with patch("sage.logging.log_event") as mock_log:
            long_error = "x" * 500
            log_task_failed("task_123", "checkpoint", long_error)
            call_args = mock_log.call_args
            assert len(call_args.kwargs["error"]) == 200

    def test_log_checkpoint_saved(self):
        """Should log checkpoint saved event."""
        with patch("sage.logging.log_event") as mock_log:
            log_checkpoint_saved("cp_abc123", "synthesis")
            mock_log.assert_called_once_with(
                "checkpoint_saved",
                checkpoint_id="cp_abc123",
                trigger="synthesis",
            )

    def test_log_knowledge_saved(self):
        """Should log knowledge saved event."""
        with patch("sage.logging.log_event") as mock_log:
            log_knowledge_saved("jwt-auth", "knowledge")
            mock_log.assert_called_once_with(
                "knowledge_saved",
                knowledge_id="jwt-auth",
                item_type="knowledge",
            )

    def test_log_config_loaded(self):
        """Should log config loaded event."""
        with patch("sage.logging.log_event") as mock_log:
            home = os.path.expanduser("~")
            log_config_loaded(f"{home}/project")
            mock_log.assert_called_once()
            # Path should be sanitized
            call_args = mock_log.call_args
            assert "~" in call_args.kwargs["project_path"]

    def test_log_config_loaded_none(self):
        """Should handle None project path."""
        with patch("sage.logging.log_event") as mock_log:
            log_config_loaded(None)
            mock_log.assert_called_once_with(
                "config_loaded",
                project_path=None,
            )


class TestRedactedFieldsCompleteness:
    """Tests that all sensitive fields are covered."""

    def test_content_fields_redacted(self):
        """All content-related fields should be in REDACTED_FIELDS."""
        content_fields = {
            "thesis",
            "content",
            "query",
            "message",
            "reasoning_trace",
            "key_evidence",
            "sources",
            "tensions",
            "unique_contributions",
            "open_questions",
        }
        assert content_fields.issubset(REDACTED_FIELDS)

    def test_secret_fields_redacted(self):
        """All secret-related fields should be in REDACTED_FIELDS."""
        secret_fields = {"api_key", "token", "secret", "password"}
        assert secret_fields.issubset(REDACTED_FIELDS)


class TestLogFilePermissions:
    """Tests for log file security."""

    def test_log_directory_created_with_secure_permissions(self):
        """Log directory should have restricted permissions."""
        from sage.logging import LOGS_DIR, _ensure_log_dir

        _ensure_log_dir()

        if LOGS_DIR.exists():
            mode = LOGS_DIR.stat().st_mode
            # Check no group/other permissions (0o077 mask)
            assert (mode & 0o077) == 0, "Log directory should not have group/other permissions"
