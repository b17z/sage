"""Tests for plugin base classes."""

from typing import ClassVar

import pytest

from sage.plugins.base import (
    ALLOWED_ACTION_TYPES,
    BasePlugin,
    PluginAction,
    PluginResult,
)
from sage.plugins.events import CompactionDetected, DaemonStarted, WatcherEvent


class TestPluginAction:
    """Tests for PluginAction dataclass."""

    def test_creates_with_valid_type(self):
        """Action can be created with allowed action type."""
        action = PluginAction(action_type="log", parameters={"message": "test"})

        assert action.action_type == "log"
        assert action.parameters == {"message": "test"}

    def test_rejects_invalid_type(self):
        """Action rejects unknown action types."""
        with pytest.raises(ValueError, match="Invalid action type"):
            PluginAction(action_type="evil_action", parameters={})

    def test_is_frozen(self):
        """Action is immutable."""
        action = PluginAction(action_type="log", parameters={})

        with pytest.raises(AttributeError):
            action.action_type = "save_recovery"

    def test_default_parameters(self):
        """Action has empty dict as default parameters."""
        action = PluginAction(action_type="log")
        assert action.parameters == {}

    def test_all_allowed_types_valid(self):
        """All allowed action types can be used."""
        for action_type in ALLOWED_ACTION_TYPES:
            action = PluginAction(action_type=action_type)
            assert action.action_type == action_type

    def test_save_recovery_type(self):
        """save_recovery action type is allowed."""
        action = PluginAction(
            action_type="save_recovery",
            parameters={"transcript_path": "/path/to/file.jsonl"},
        )
        assert action.action_type == "save_recovery"

    def test_write_marker_type(self):
        """write_marker action type is allowed."""
        action = PluginAction(
            action_type="write_marker",
            parameters={"reason": "post_compaction"},
        )
        assert action.action_type == "write_marker"

    def test_queue_for_injection_type(self):
        """queue_for_injection action type is allowed."""
        action = PluginAction(
            action_type="queue_for_injection",
            parameters={"checkpoint_id": "test-id"},
        )
        assert action.action_type == "queue_for_injection"


class TestPluginResult:
    """Tests for PluginResult dataclass."""

    def test_empty_result(self):
        """empty() creates result with no actions."""
        result = PluginResult.empty()
        assert result.actions == ()

    def test_single_action(self):
        """single() creates result with one action."""
        action = PluginAction(action_type="log", parameters={"message": "test"})
        result = PluginResult.single(action)

        assert len(result.actions) == 1
        assert result.actions[0] == action

    def test_from_actions(self):
        """from_actions() creates result with multiple actions."""
        action1 = PluginAction(action_type="log", parameters={"message": "first"})
        action2 = PluginAction(action_type="log", parameters={"message": "second"})

        result = PluginResult.from_actions(action1, action2)

        assert len(result.actions) == 2
        assert result.actions[0] == action1
        assert result.actions[1] == action2

    def test_is_frozen(self):
        """Result is immutable."""
        result = PluginResult.empty()

        with pytest.raises(AttributeError):
            result.actions = ()

    def test_actions_is_tuple(self):
        """Actions are stored as tuple for immutability."""
        action = PluginAction(action_type="log", parameters={})
        result = PluginResult.single(action)

        assert isinstance(result.actions, tuple)


class TestAllowedActionTypes:
    """Tests for the ALLOWED_ACTION_TYPES whitelist."""

    def test_is_frozenset(self):
        """Whitelist is immutable."""
        assert isinstance(ALLOWED_ACTION_TYPES, frozenset)

    def test_contains_expected_types(self):
        """Whitelist contains all expected action types."""
        expected = {
            "log",
            "save_recovery",
            "write_marker",
            "queue_for_injection",
            "start_session",
            "end_session",
        }
        assert ALLOWED_ACTION_TYPES == expected

    def test_no_dangerous_types(self):
        """Whitelist does not contain dangerous action types."""
        dangerous = {"exec", "eval", "shell", "run", "execute", "system", "os"}
        assert ALLOWED_ACTION_TYPES.isdisjoint(dangerous)


class ConcreteTestPlugin(BasePlugin):
    """Concrete plugin for testing."""

    name: ClassVar[str] = "test-plugin"
    subscribes_to: ClassVar[tuple[type, ...]] = (CompactionDetected,)

    def handle(self, event: WatcherEvent) -> PluginResult:
        return PluginResult.single(
            PluginAction(action_type="log", parameters={"message": "handled"})
        )


class TestBasePlugin:
    """Tests for BasePlugin abstract class."""

    def test_concrete_plugin_has_name(self):
        """Concrete plugin has name attribute."""
        plugin = ConcreteTestPlugin()
        assert plugin.name == "test-plugin"

    def test_concrete_plugin_has_subscribes_to(self):
        """Concrete plugin has subscribes_to attribute."""
        plugin = ConcreteTestPlugin()
        assert plugin.subscribes_to == (CompactionDetected,)

    def test_handle_returns_result(self):
        """handle() returns a PluginResult."""
        plugin = ConcreteTestPlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/path/to/file.jsonl",
        )

        result = plugin.handle(event)

        assert isinstance(result, PluginResult)
        assert len(result.actions) == 1

    def test_accepts_event_matches_subscribes_to(self):
        """accepts_event() returns True for subscribed event types."""
        plugin = ConcreteTestPlugin()
        event = CompactionDetected(
            timestamp="2024-01-01T00:00:00Z",
            summary="test",
            transcript_path="/path/to/file.jsonl",
        )

        assert plugin.accepts_event(event) is True

    def test_accepts_event_rejects_other_types(self):
        """accepts_event() returns False for non-subscribed event types."""
        plugin = ConcreteTestPlugin()
        event = DaemonStarted(
            timestamp="2024-01-01T00:00:00Z",
            transcript_path="/path/to/file.jsonl",
            pid=12345,
        )

        assert plugin.accepts_event(event) is False

    def test_configure_default_does_nothing(self):
        """Default configure() does nothing."""
        plugin = ConcreteTestPlugin()
        # Should not raise
        plugin.configure({"some_setting": "value"})
