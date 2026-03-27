#!/usr/bin/env python3

"""
tests.unit.test_config_notification_channels.py

Unit tests for Config notification_channels getter/setter:
- get_notification_channels returns empty list by default
- set_notification_channels persists the list
- Invalid data handled gracefully
"""

import pytest

from compresso.config import Config

# ------------------------------------------------------------------
# TestConfigNotificationChannels
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestConfigNotificationChannels:
    def _make_bare_config(self):
        """Create a bare Config object bypassing __init__ to test getter/setter logic only."""
        obj = object.__new__(Config)
        obj.notification_channels = []
        return obj

    def test_get_returns_empty_list_by_default(self):
        obj = self._make_bare_config()
        result = obj.get_notification_channels()
        assert result == []
        assert isinstance(result, list)

    def test_set_persists_list(self):
        obj = self._make_bare_config()
        channels = [
            {
                "type": "discord",
                "name": "test",
                "url": "https://discord.com/webhook",
                "triggers": ["task_completed"],
                "enabled": True,
            },
        ]
        obj.set_notification_channels(channels)
        result = obj.get_notification_channels()
        assert len(result) == 1
        assert result[0]["type"] == "discord"

    def test_set_multiple_channels(self):
        obj = self._make_bare_config()
        channels = [
            {"type": "discord", "name": "ch1", "url": "https://discord.com/1", "triggers": [], "enabled": True},
            {"type": "slack", "name": "ch2", "url": "https://slack.com/2", "triggers": [], "enabled": False},
            {"type": "webhook", "name": "ch3", "url": "https://example.com", "triggers": [], "enabled": True},
        ]
        obj.set_notification_channels(channels)
        result = obj.get_notification_channels()
        assert len(result) == 3

    def test_set_non_list_resets_to_empty(self):
        obj = self._make_bare_config()
        obj.set_notification_channels("not a list")
        result = obj.get_notification_channels()
        assert result == []

    def test_set_none_resets_to_empty(self):
        obj = self._make_bare_config()
        obj.set_notification_channels(None)
        result = obj.get_notification_channels()
        assert result == []

    def test_set_dict_resets_to_empty(self):
        obj = self._make_bare_config()
        obj.set_notification_channels({"type": "discord"})
        result = obj.get_notification_channels()
        assert result == []

    def test_get_returns_copy_not_reference(self):
        obj = self._make_bare_config()
        obj.set_notification_channels([{"name": "test"}])
        result = obj.get_notification_channels()
        result.append({"name": "injected"})
        # Internal state should not be affected
        assert len(obj.get_notification_channels()) == 1

    def test_get_handles_corrupted_attribute(self):
        """If notification_channels is somehow not a list, get should return []."""
        obj = self._make_bare_config()
        obj.notification_channels = "corrupted_string_value"
        result = obj.get_notification_channels()
        assert result == []

    def test_get_handles_none_attribute(self):
        obj = self._make_bare_config()
        obj.notification_channels = None
        result = obj.get_notification_channels()
        assert result == []

    def test_set_empty_list(self):
        obj = self._make_bare_config()
        obj.set_notification_channels([{"name": "will be cleared"}])
        obj.set_notification_channels([])
        result = obj.get_notification_channels()
        assert result == []


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
