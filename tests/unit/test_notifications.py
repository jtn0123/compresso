#!/usr/bin/env python3

"""
tests.unit.test_notifications.py

Unit tests for compresso.libs.notifications.Notifications class.
"""

import threading

import pytest

from compresso.libs.singleton import SingletonType


def _make_valid_item(**overrides):
    """Build a valid notification item with optional overrides."""
    item = {
        "uuid": "test-uuid-1",
        "type": "info",
        "icon": "info",
        "label": "testLabel",
        "message": "Test message",
        "navigation": {"push": "/test"},
    }
    item.update(overrides)
    return item


def _fresh_notifications():
    """Get a fresh Notifications instance by clearing its singleton cache entry."""
    from compresso.libs.notifications import Notifications

    SingletonType._instances.pop(Notifications, None)
    return Notifications()


@pytest.mark.unittest
class TestNotificationsValidation:
    def setup_method(self):
        self.notif = _fresh_notifications()

    def test_add_raises_on_missing_type_key(self):
        item = {"icon": "x", "label": "x", "message": "x", "navigation": {}}
        with pytest.raises(Exception, match="Missing key: 'type'"):
            self.notif.add(item)

    def test_add_raises_on_missing_icon_key(self):
        item = {"type": "info", "message": "x", "navigation": {}}
        with pytest.raises(Exception, match="Missing key: 'icon'"):
            self.notif.add(item)

    def test_add_raises_on_missing_label_key(self):
        item = {"type": "info", "icon": "x", "message": "x", "navigation": {}}
        with pytest.raises(Exception, match="Missing key: 'label'"):
            self.notif.add(item)

    def test_add_raises_on_missing_message_key(self):
        item = {"type": "info", "icon": "x", "label": "x", "navigation": {}}
        with pytest.raises(Exception, match="Missing key: 'message'"):
            self.notif.add(item)

    def test_add_raises_on_missing_navigation_key(self):
        item = {"type": "info", "icon": "x", "label": "x", "message": "x"}
        with pytest.raises(Exception, match="Missing key: 'navigation'"):
            self.notif.add(item)

    def test_add_raises_on_invalid_type_value(self):
        item = _make_valid_item(type="invalid")
        with pytest.raises(Exception, match="code must be in"):
            self.notif.add(item)

    def test_add_accepts_valid_error_type(self):
        self.notif.add(_make_valid_item(type="error", uuid="e1"))
        assert len(self.notif.read_all_items()) == 1

    def test_add_accepts_valid_warning_type(self):
        self.notif.add(_make_valid_item(type="warning", uuid="w1"))
        assert len(self.notif.read_all_items()) == 1

    def test_add_accepts_valid_success_type(self):
        self.notif.add(_make_valid_item(type="success", uuid="s1"))
        assert len(self.notif.read_all_items()) == 1

    def test_add_accepts_valid_info_type(self):
        self.notif.add(_make_valid_item(type="info", uuid="i1"))
        assert len(self.notif.read_all_items()) == 1


@pytest.mark.unittest
class TestNotificationsAdd:
    def setup_method(self):
        self.notif = _fresh_notifications()

    def test_add_item_appears_in_read_all(self):
        item = _make_valid_item()
        self.notif.add(item)
        items = self.notif.read_all_items()
        assert len(items) == 1
        assert items[0]["uuid"] == "test-uuid-1"

    def test_add_generates_uuid_when_missing(self):
        item = _make_valid_item()
        del item["uuid"]
        self.notif.add(item)
        items = self.notif.read_all_items()
        assert len(items) == 1
        assert "uuid" in items[0]
        assert len(items[0]["uuid"]) > 0

    def test_add_duplicate_uuid_ignored(self):
        item = _make_valid_item(uuid="dup")
        self.notif.add(item)
        self.notif.add(item)
        assert len(self.notif.read_all_items()) == 1

    def test_add_multiple_distinct_items(self):
        for i in range(3):
            self.notif.add(_make_valid_item(uuid=f"item-{i}"))
        assert len(self.notif.read_all_items()) == 3


@pytest.mark.unittest
class TestNotificationsRemove:
    def setup_method(self):
        self.notif = _fresh_notifications()

    def test_remove_existing_item_returns_true(self):
        self.notif.add(_make_valid_item(uuid="rem1"))
        assert self.notif.remove("rem1") is True

    def test_remove_nonexistent_item_returns_false(self):
        assert self.notif.remove("nonexistent") is False

    def test_remove_clears_from_all_items_set(self):
        self.notif.add(_make_valid_item(uuid="rem2"))
        self.notif.remove("rem2")
        # Re-adding should succeed since it was fully removed
        self.notif.add(_make_valid_item(uuid="rem2"))
        assert len(self.notif.read_all_items()) == 1

    def test_remove_only_affects_target_item(self):
        self.notif.add(_make_valid_item(uuid="keep"))
        self.notif.add(_make_valid_item(uuid="remove"))
        self.notif.remove("remove")
        items = self.notif.read_all_items()
        assert len(items) == 1
        assert items[0]["uuid"] == "keep"


@pytest.mark.unittest
class TestNotificationsUpdate:
    def setup_method(self):
        self.notif = _fresh_notifications()

    def test_update_replaces_existing_item(self):
        self.notif.add(_make_valid_item(uuid="upd1", message="original"))
        self.notif.update(_make_valid_item(uuid="upd1", message="updated"))
        items = self.notif.read_all_items()
        assert len(items) == 1
        assert items[0]["message"] == "updated"

    def test_update_adds_if_uuid_not_found(self):
        self.notif.update(_make_valid_item(uuid="new1"))
        items = self.notif.read_all_items()
        assert len(items) == 1
        assert items[0]["uuid"] == "new1"

    def test_update_generates_uuid_when_missing(self):
        item = _make_valid_item()
        del item["uuid"]
        self.notif.update(item)
        items = self.notif.read_all_items()
        assert len(items) == 1
        assert "uuid" in items[0]

    def test_update_preserves_other_items(self):
        self.notif.add(_make_valid_item(uuid="a", message="msg-a"))
        self.notif.add(_make_valid_item(uuid="b", message="msg-b"))
        self.notif.update(_make_valid_item(uuid="a", message="msg-a-updated"))
        items = self.notif.read_all_items()
        assert len(items) == 2
        messages = {i["uuid"]: i["message"] for i in items}
        assert messages["a"] == "msg-a-updated"
        assert messages["b"] == "msg-b"


@pytest.mark.unittest
class TestNotificationsReadAll:
    def setup_method(self):
        self.notif = _fresh_notifications()

    def test_read_all_returns_empty_list_when_empty(self):
        assert self.notif.read_all_items() == []

    def test_read_all_does_not_consume_items(self):
        self.notif.add(_make_valid_item(uuid="persist"))
        assert len(self.notif.read_all_items()) == 1
        assert len(self.notif.read_all_items()) == 1


@pytest.mark.unittest
class TestNotificationsThreadSafety:
    def test_concurrent_adds_no_data_loss(self):
        notif = _fresh_notifications()
        count = 50

        def add_items(start):
            for i in range(start, start + count):
                notif.add(_make_valid_item(uuid=f"thread-{i}"))

        threads = [
            threading.Thread(target=add_items, args=(0,)),
            threading.Thread(target=add_items, args=(count,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        items = notif.read_all_items()
        assert len(items) == count * 2
