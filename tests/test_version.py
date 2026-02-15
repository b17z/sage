"""Tests for version checking functionality."""

import json
import time
from unittest.mock import MagicMock, patch


class TestCheckForUpdates:
    """Tests for check_for_updates function."""

    def test_returns_false_when_current(self, tmp_path, monkeypatch):
        """Should return (False, None) when already on latest."""
        from sage import __version__

        # Mock SAGE_DIR
        monkeypatch.setattr("sage.config.SAGE_DIR", tmp_path)

        # Mock urllib to return current version
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "info": {"version": __version__}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            from sage import check_for_updates
            update_available, latest = check_for_updates()

        assert update_available is False
        assert latest is None

    def test_returns_true_when_outdated(self, tmp_path, monkeypatch):
        """Should return (True, latest_version) when update available."""
        # Mock SAGE_DIR
        monkeypatch.setattr("sage.config.SAGE_DIR", tmp_path)

        # Mock urllib to return newer version
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "info": {"version": "99.0.0"}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            from sage import check_for_updates
            update_available, latest = check_for_updates()

        assert update_available is True
        assert latest == "99.0.0"

    def test_returns_false_on_network_error(self, tmp_path, monkeypatch):
        """Should return (False, None) on network failure."""
        # Mock SAGE_DIR
        monkeypatch.setattr("sage.config.SAGE_DIR", tmp_path)

        with patch("urllib.request.urlopen", side_effect=Exception("Network error")):
            from sage import check_for_updates
            update_available, latest = check_for_updates()

        assert update_available is False
        assert latest is None

    def test_uses_cache_when_valid(self, tmp_path, monkeypatch):
        """Should use cached result within 24 hours."""
        # Mock SAGE_DIR
        monkeypatch.setattr("sage.config.SAGE_DIR", tmp_path)

        # Write a valid cache
        cache_path = tmp_path / ".version_cache.json"
        cache_path.write_text(json.dumps({
            "latest_version": "99.0.0",
            "checked_at": time.time(),  # Now
        }))

        # urlopen should NOT be called
        with patch("urllib.request.urlopen") as mock_urlopen:
            from sage import check_for_updates
            update_available, latest = check_for_updates()

        mock_urlopen.assert_not_called()
        assert update_available is True
        assert latest == "99.0.0"

    def test_ignores_expired_cache(self, tmp_path, monkeypatch):
        """Should fetch from PyPI when cache is expired."""
        # Mock SAGE_DIR
        monkeypatch.setattr("sage.config.SAGE_DIR", tmp_path)

        # Write an expired cache (25 hours old)
        cache_path = tmp_path / ".version_cache.json"
        cache_path.write_text(json.dumps({
            "latest_version": "99.0.0",
            "checked_at": time.time() - 90000,  # 25 hours ago
        }))

        # Mock urllib to return current version
        from sage import __version__
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "info": {"version": __version__}
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            from sage import check_for_updates
            update_available, latest = check_for_updates()

        mock_urlopen.assert_called_once()
        assert update_available is False


class TestVersionInHealth:
    """Tests for version check in sage_health."""

    def test_health_shows_update_available(self, tmp_path, monkeypatch):
        """sage_health should show update available warning."""
        from sage import mcp_server

        monkeypatch.setattr("sage.config.SAGE_DIR", tmp_path)
        monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", tmp_path / "checkpoints")
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", tmp_path / "knowledge")
        monkeypatch.setattr("sage.tasks.TASKS_DIR", tmp_path / "tasks")
        monkeypatch.setattr(mcp_server, "_PROJECT_ROOT", None)

        with patch("sage.check_for_updates", return_value=(True, "99.0.0")):
            result = mcp_server.sage_health()

        assert "Update available" in result
        assert "99.0.0" in result
        assert "pip install --upgrade claude-sage" in result

    def test_health_shows_latest_when_current(self, tmp_path, monkeypatch):
        """sage_health should show 'latest' when on current version."""
        from sage import mcp_server

        monkeypatch.setattr("sage.config.SAGE_DIR", tmp_path)
        monkeypatch.setattr("sage.checkpoint.CHECKPOINTS_DIR", tmp_path / "checkpoints")
        monkeypatch.setattr("sage.knowledge.KNOWLEDGE_DIR", tmp_path / "knowledge")
        monkeypatch.setattr("sage.tasks.TASKS_DIR", tmp_path / "tasks")
        monkeypatch.setattr(mcp_server, "_PROJECT_ROOT", None)

        with patch("sage.check_for_updates", return_value=(False, None)):
            result = mcp_server.sage_health()

        assert "(latest)" in result


class TestStartupCheck:
    """Tests for startup update check."""

    def test_startup_check_does_not_crash(self, tmp_path, monkeypatch):
        """Startup check should never crash, even on errors."""
        from sage.mcp_server import _check_for_updates_on_startup

        with patch("sage.check_for_updates", side_effect=Exception("Boom")):
            # Should not raise
            _check_for_updates_on_startup()

    def test_startup_check_logs_warning(self, tmp_path, monkeypatch, caplog):
        """Startup check should log warning when update available."""
        import logging

        from sage.mcp_server import _check_for_updates_on_startup

        with patch("sage.check_for_updates", return_value=(True, "99.0.0")):
            with caplog.at_level(logging.WARNING):
                _check_for_updates_on_startup()

        assert "Update available" in caplog.text
        assert "99.0.0" in caplog.text
