#!/usr/bin/env python3

"""
tests.unit.test_frontend_push_messages.py

Unit tests for compresso.libs.frontend_push_messages.FrontendPushMessages.
"""

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singleton():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_item(item_id="msg-1", msg_type="info", code="test_code", message="Test message", timeout=5000):
    return {
        "id": item_id,
        "type": msg_type,
        "code": code,
        "message": message,
        "timeout": timeout,
    }


@pytest.mark.unittest
class TestFrontendPushMessagesInit:
    def test_creates_instance(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        assert fpm is not None

    def test_singleton_returns_same_instance(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm1 = FrontendPushMessages()
        fpm2 = FrontendPushMessages()
        assert fpm1 is fpm2

    def test_init_creates_empty_all_items_set(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        assert isinstance(fpm.all_items, set)
        assert len(fpm.all_items) == 0


@pytest.mark.unittest
class TestFrontendPushMessagesValidation:
    def test_missing_id_raises(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item = {"type": "info", "code": "c", "message": "m", "timeout": 0}
        with pytest.raises(Exception, match="Missing key: 'id'"):
            fpm.add(item)

    def test_missing_type_raises(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item = {"id": "1", "code": "c", "message": "m", "timeout": 0}
        with pytest.raises(Exception, match="Missing key: 'type'"):
            fpm.add(item)

    def test_missing_code_raises(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item = {"id": "1", "type": "info", "message": "m", "timeout": 0}
        with pytest.raises(Exception, match="Missing key: 'code'"):
            fpm.add(item)

    def test_missing_message_raises(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item = {"id": "1", "type": "info", "code": "c", "timeout": 0}
        with pytest.raises(Exception, match="Missing key: 'message'"):
            fpm.add(item)

    def test_missing_timeout_raises(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item = {"id": "1", "type": "info", "code": "c", "message": "m"}
        with pytest.raises(Exception, match="Missing key: 'timeout'"):
            fpm.add(item)

    def test_invalid_type_raises(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item = _make_item(msg_type="invalid")
        with pytest.raises(Exception, match="must be in"):
            fpm.add(item)

    @pytest.mark.parametrize("msg_type", ["error", "warning", "success", "info", "status"])
    def test_valid_types_accepted(self, msg_type):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item = _make_item(msg_type=msg_type)
        fpm.add(item)  # Should not raise
        assert len(fpm.get_all_items()) == 1


@pytest.mark.unittest
class TestFrontendPushMessagesAdd:
    def test_add_single_item(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item = _make_item()
        fpm.add(item)
        items = fpm.get_all_items()
        assert len(items) == 1
        assert items[0]["id"] == "msg-1"

    def test_add_deduplicates_by_id(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="dup"))
        fpm.add(_make_item(item_id="dup", message="Different message"))
        items = fpm.get_all_items()
        assert len(items) == 1
        assert items[0]["message"] == "Test message"

    def test_add_multiple_distinct_items(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="a"))
        fpm.add(_make_item(item_id="b"))
        fpm.add(_make_item(item_id="c"))
        assert len(fpm.get_all_items()) == 3

    def test_add_tracks_id_in_all_items_set(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="tracked"))
        assert "tracked" in fpm.all_items


@pytest.mark.unittest
class TestFrontendPushMessagesGetAllItems:
    def test_get_all_items_returns_all(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="1"))
        fpm.add(_make_item(item_id="2"))
        items = fpm.get_all_items()
        assert len(items) == 2

    def test_get_all_items_is_non_destructive(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="persist"))
        items1 = fpm.get_all_items()
        items2 = fpm.get_all_items()
        assert len(items1) == 1
        assert len(items2) == 1

    def test_get_all_items_empty_queue(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        assert fpm.get_all_items() == []


@pytest.mark.unittest
class TestFrontendPushMessagesRemoveItem:
    def test_remove_existing_item(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="remove-me"))
        fpm.add(_make_item(item_id="keep-me"))
        fpm.remove_item("remove-me")
        items = fpm.get_all_items()
        assert len(items) == 1
        assert items[0]["id"] == "keep-me"

    def test_remove_clears_from_all_items_set(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="gone"))
        fpm.remove_item("gone")
        assert "gone" not in fpm.all_items

    def test_remove_nonexistent_item_does_not_error(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="exists"))
        fpm.remove_item("nonexistent")
        assert len(fpm.get_all_items()) == 1

    def test_remove_allows_re_adding_same_id(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="cycle"))
        fpm.remove_item("cycle")
        fpm.add(_make_item(item_id="cycle", message="Re-added"))
        items = fpm.get_all_items()
        assert len(items) == 1
        assert items[0]["message"] == "Re-added"


@pytest.mark.unittest
class TestFrontendPushMessagesReadAllItems:
    def test_read_all_items_returns_copy(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="read-1"))
        result = fpm.read_all_items()
        assert isinstance(result, list)
        assert len(result) == 1

    def test_read_all_items_is_non_destructive(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="rd"))
        fpm.read_all_items()
        assert len(fpm.get_all_items()) == 1


@pytest.mark.unittest
class TestFrontendPushMessagesUpdate:
    def test_update_replaces_existing_item(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="upd", message="Original"))
        fpm.update(_make_item(item_id="upd", message="Updated"))
        items = fpm.get_all_items()
        assert len(items) == 1
        assert items[0]["message"] == "Updated"

    def test_update_adds_new_item_if_not_found(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.update(_make_item(item_id="new-upd", message="Brand new"))
        items = fpm.get_all_items()
        assert len(items) == 1
        assert items[0]["message"] == "Brand new"

    def test_update_validates_item(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        with pytest.raises(Exception, match="Missing key"):
            fpm.update({"id": "1"})

    def test_update_preserves_other_items(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        fpm.add(_make_item(item_id="keep"))
        fpm.add(_make_item(item_id="change", message="Old"))
        fpm.update(_make_item(item_id="change", message="New"))
        items = fpm.get_all_items()
        assert len(items) == 2
        ids = {i["id"] for i in items}
        assert ids == {"keep", "change"}


@pytest.mark.unittest
class TestFrontendPushMessagesRequeueItems:
    def test_requeue_items_adds_back(self):
        from compresso.libs.frontend_push_messages import FrontendPushMessages

        fpm = FrontendPushMessages()
        item1 = _make_item(item_id="rq1")
        item2 = _make_item(item_id="rq2")
        fpm.requeue_items([item1, item2])
        items = fpm.get_all_items()
        assert len(items) == 2
