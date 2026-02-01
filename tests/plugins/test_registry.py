"""Tests for plugin registry."""

from pathlib import Path

import pytest
import yaml

from sage.plugins.events import CompactionDetected, DaemonStarted
from sage.plugins.registry import (
    BUILTIN_PLUGIN_NAMES,
    PluginConfig,
    get_enabled_plugins,
    get_plugins_for_event,
    load_plugin_config,
    save_plugin_config,
)


@pytest.fixture
def temp_sage_dir(tmp_path: Path, monkeypatch):
    """Create a temporary .sage directory for testing."""
    sage_dir = tmp_path / ".sage"
    sage_dir.mkdir()

    monkeypatch.setattr("sage.plugins.registry.SAGE_DIR", sage_dir)
    monkeypatch.setattr("sage.plugins.registry.PLUGINS_CONFIG_FILE", sage_dir / "plugins.yaml")

    return sage_dir


class TestBuiltinPluginNames:
    """Tests for BUILTIN_PLUGIN_NAMES constant."""

    def test_is_frozenset(self):
        """Names are immutable."""
        assert isinstance(BUILTIN_PLUGIN_NAMES, frozenset)

    def test_contains_expected_plugins(self):
        """Names contain expected built-in plugins."""
        assert "recovery" in BUILTIN_PLUGIN_NAMES
        assert "checkpoint-queue" in BUILTIN_PLUGIN_NAMES

    def test_no_dangerous_names(self):
        """Names don't contain dangerous plugin names."""
        dangerous = {"exec", "eval", "shell", "system"}
        assert BUILTIN_PLUGIN_NAMES.isdisjoint(dangerous)


class TestPluginConfig:
    """Tests for PluginConfig dataclass."""

    def test_default_values(self):
        """Config has sensible defaults."""
        config = PluginConfig()

        assert config.enabled is True
        assert config.priority == 100
        assert config.settings == {}

    def test_custom_values(self):
        """Config accepts custom values."""
        config = PluginConfig(
            enabled=False,
            priority=50,
            settings={"threshold": 0.5},
        )

        assert config.enabled is False
        assert config.priority == 50
        assert config.settings == {"threshold": 0.5}

    def test_is_frozen(self):
        """Config is immutable."""
        config = PluginConfig()

        with pytest.raises(AttributeError):
            config.enabled = False


class TestLoadPluginConfig:
    """Tests for load_plugin_config function."""

    def test_returns_defaults_when_file_missing(self, temp_sage_dir: Path):
        """Returns defaults for all built-in plugins when no config file."""
        configs = load_plugin_config()

        assert len(configs) == len(BUILTIN_PLUGIN_NAMES)
        for name in BUILTIN_PLUGIN_NAMES:
            assert name in configs
            assert configs[name].enabled is True
            assert configs[name].priority == 100

    def test_parses_valid_yaml(self, temp_sage_dir: Path):
        """Parses valid YAML config file."""
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text(
            yaml.safe_dump(
                {
                    "plugins": {
                        "recovery": {
                            "enabled": False,
                            "priority": 50,
                            "settings": {"threshold": 0.3},
                        }
                    }
                }
            )
        )

        configs = load_plugin_config()

        assert configs["recovery"].enabled is False
        assert configs["recovery"].priority == 50
        assert configs["recovery"].settings == {"threshold": 0.3}

    def test_rejects_unknown_plugin_names(self, temp_sage_dir: Path):
        """Ignores unknown plugin names in config."""
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text(
            yaml.safe_dump(
                {
                    "plugins": {
                        "evil-plugin": {
                            "enabled": True,
                        }
                    }
                }
            )
        )

        configs = load_plugin_config()

        assert "evil-plugin" not in configs
        # Built-in plugins still have defaults
        assert "recovery" in configs

    def test_handles_invalid_yaml(self, temp_sage_dir: Path):
        """Returns defaults on invalid YAML."""
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text("not: valid: yaml: {{")

        configs = load_plugin_config()

        # Should still return defaults
        assert "recovery" in configs
        assert configs["recovery"].enabled is True

    def test_handles_non_dict_root(self, temp_sage_dir: Path):
        """Returns defaults if YAML root is not a dict."""
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text("- item1\n- item2")

        configs = load_plugin_config()

        # Should still return defaults
        assert "recovery" in configs

    def test_handles_non_dict_plugins(self, temp_sage_dir: Path):
        """Returns defaults if 'plugins' key is not a dict."""
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text(yaml.safe_dump({"plugins": ["a", "b"]}))

        configs = load_plugin_config()

        # Should still return defaults
        assert "recovery" in configs

    def test_handles_invalid_field_types(self, temp_sage_dir: Path):
        """Uses defaults for invalid field types."""
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text(
            yaml.safe_dump(
                {
                    "plugins": {
                        "recovery": {
                            "enabled": "not-a-bool",
                            "priority": "not-an-int",
                            "settings": "not-a-dict",
                        }
                    }
                }
            )
        )

        configs = load_plugin_config()

        # Should use defaults for invalid fields
        assert configs["recovery"].enabled is True
        assert configs["recovery"].priority == 100
        assert configs["recovery"].settings == {}


class TestSavePluginConfig:
    """Tests for save_plugin_config function."""

    def test_saves_to_file(self, temp_sage_dir: Path):
        """Saves config to YAML file."""
        configs = {
            "recovery": PluginConfig(enabled=False, priority=50),
        }

        path = save_plugin_config(configs)

        assert path.exists()
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["plugins"]["recovery"]["enabled"] is False
        assert data["plugins"]["recovery"]["priority"] == 50

    def test_creates_parent_directory(self, tmp_path: Path, monkeypatch):
        """Creates parent directory if it doesn't exist."""
        sage_dir = tmp_path / "nested" / ".sage"
        monkeypatch.setattr("sage.plugins.registry.SAGE_DIR", sage_dir)
        monkeypatch.setattr("sage.plugins.registry.PLUGINS_CONFIG_FILE", sage_dir / "plugins.yaml")

        configs = {"recovery": PluginConfig()}

        path = save_plugin_config(configs)

        assert path.exists()
        assert path.parent == sage_dir

    def test_rejects_unknown_plugins(self, temp_sage_dir: Path):
        """Does not save unknown plugin names."""
        configs = {
            "recovery": PluginConfig(),
            "evil-plugin": PluginConfig(),
        }

        path = save_plugin_config(configs)

        with open(path) as f:
            data = yaml.safe_load(f)
        assert "evil-plugin" not in data["plugins"]
        assert "recovery" in data["plugins"]


class TestGetEnabledPlugins:
    """Tests for get_enabled_plugins function."""

    def test_returns_enabled_plugins(self, temp_sage_dir: Path):
        """Returns only enabled plugins."""
        # All plugins enabled by default
        plugins = get_enabled_plugins()

        # Should have at least the built-in plugins
        names = [p.name for p in plugins]
        assert "recovery" in names

    def test_respects_enabled_flag(self, temp_sage_dir: Path):
        """Disabled plugins are not returned."""
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text(
            yaml.safe_dump(
                {
                    "plugins": {
                        "recovery": {"enabled": False},
                    }
                }
            )
        )

        plugins = get_enabled_plugins()

        names = [p.name for p in plugins]
        assert "recovery" not in names

    def test_sorts_by_priority(self, temp_sage_dir: Path):
        """Plugins are sorted by priority (lower first)."""
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text(
            yaml.safe_dump(
                {
                    "plugins": {
                        "recovery": {"priority": 200},
                        "checkpoint-queue": {"priority": 50},
                    }
                }
            )
        )

        plugins = get_enabled_plugins()

        names = [p.name for p in plugins]
        assert names.index("checkpoint-queue") < names.index("recovery")


class TestGetPluginsForEvent:
    """Tests for get_plugins_for_event function."""

    def test_filters_by_event_type(self, temp_sage_dir: Path):
        """Returns only plugins that subscribe to event type."""
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/path/to/file.jsonl",
        )

        plugins = get_plugins_for_event(event)

        # Recovery plugin subscribes to CompactionDetected
        names = [p.name for p in plugins]
        assert "recovery" in names

    def test_checkpoint_queue_for_daemon_started(self, temp_sage_dir: Path):
        """Checkpoint queue plugin handles DaemonStarted."""
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/file.jsonl",
            pid=12345,
        )

        plugins = get_plugins_for_event(event)

        names = [p.name for p in plugins]
        assert "checkpoint-queue" in names

    def test_empty_for_no_subscribers(self, temp_sage_dir: Path):
        """Returns empty list if no plugins subscribe."""
        # Disable all plugins
        config_file = temp_sage_dir / "plugins.yaml"
        config_file.write_text(
            yaml.safe_dump(
                {
                    "plugins": {
                        "recovery": {"enabled": False},
                        "checkpoint-queue": {"enabled": False},
                        "session": {"enabled": False},
                    }
                }
            )
        )

        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/path/to/file.jsonl",
        )

        plugins = get_plugins_for_event(event)

        assert plugins == []
