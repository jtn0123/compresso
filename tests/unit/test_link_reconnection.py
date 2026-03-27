#!/usr/bin/env python3

"""
tests.unit.test_link_reconnection.py

Unit tests for installation_link.Links reconnection and backoff logic:
- _record_link_success sets status to 'connected' and resets failures
- _record_link_failure increments failures and calculates backoff
- _record_link_failure sets 'reconnecting' for <= 10 failures
- _record_link_failure sets 'disconnected' for > 10 failures
- _should_skip_link returns True during backoff window
- _should_skip_link returns False after backoff expires
- Exponential backoff caps at 300 seconds
- get_all_link_statuses returns all tracked statuses
- Success after reconnecting triggers notification
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType

LINK_MOD = "compresso.libs.installation_link"


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_links():
    """Create a Links instance with mocked dependencies."""
    with (
        patch(f"{LINK_MOD}.config.Config"),
        patch(f"{LINK_MOD}.session.Session"),
        patch(f"{LINK_MOD}.CompressoLogging") as mock_logging,
    ):
        mock_logger = MagicMock()
        mock_logging.get_logger.return_value = mock_logger

        from compresso.libs.installation_link import Links

        links = Links()
        return links


# ------------------------------------------------------------------
# TestRecordLinkSuccess
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestRecordLinkSuccess:
    def test_sets_status_to_connected(self):
        links = _make_links()
        links._record_link_success("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["status"] == "connected"

    def test_resets_consecutive_failures(self):
        links = _make_links()
        # Simulate prior failures
        links._link_status["uuid-1"] = {
            "status": "reconnecting",
            "last_seen": None,
            "consecutive_failures": 5,
            "next_retry": time.time() + 100,
        }
        links._record_link_success("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["consecutive_failures"] == 0
        assert status["next_retry"] == 0

    def test_sets_last_seen_timestamp(self):
        links = _make_links()
        before = time.time()
        links._record_link_success("uuid-1")
        after = time.time()

        status = links.get_link_status("uuid-1")
        assert before <= status["last_seen"] <= after

    @patch("compresso.libs.frontend_push_messages.FrontendPushMessages")
    def test_success_after_reconnecting_triggers_notification(self, mock_fpm_cls):
        links = _make_links()
        # Set up as reconnecting
        links._link_status["uuid-1"] = {
            "status": "reconnecting",
            "last_seen": None,
            "consecutive_failures": 3,
            "next_retry": time.time() + 50,
        }

        mock_fpm = MagicMock()
        mock_fpm_cls.return_value = mock_fpm

        links._record_link_success("uuid-1")

        mock_fpm.update.assert_called_once()
        call_data = mock_fpm.update.call_args[0][0]
        assert call_data["type"] == "success"
        assert "reconnected" in call_data["message"]

    def test_success_from_connected_does_not_trigger_notification(self):
        links = _make_links()
        links._link_status["uuid-1"] = {
            "status": "connected",
            "last_seen": time.time(),
            "consecutive_failures": 0,
            "next_retry": 0,
        }
        # Should not raise or attempt notification
        links._record_link_success("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["status"] == "connected"


# ------------------------------------------------------------------
# TestRecordLinkFailure
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestRecordLinkFailure:
    def test_increments_consecutive_failures(self):
        links = _make_links()
        links._record_link_failure("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["consecutive_failures"] == 1

    def test_multiple_failures_increment(self):
        links = _make_links()
        for _ in range(5):
            links._record_link_failure("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["consecutive_failures"] == 5

    def test_sets_reconnecting_for_few_failures(self):
        links = _make_links()
        links._record_link_failure("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["status"] == "reconnecting"

    def test_sets_reconnecting_at_ten_failures(self):
        links = _make_links()
        # Set up with 9 failures so next makes it 10
        links._link_status["uuid-1"] = {
            "status": "reconnecting",
            "last_seen": None,
            "consecutive_failures": 9,
            "next_retry": 0,
        }
        links._record_link_failure("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["consecutive_failures"] == 10
        assert status["status"] == "reconnecting"

    def test_sets_disconnected_after_ten_failures(self):
        links = _make_links()
        # Set up with 10 failures so next makes it 11
        links._link_status["uuid-1"] = {
            "status": "reconnecting",
            "last_seen": None,
            "consecutive_failures": 10,
            "next_retry": 0,
        }
        links._record_link_failure("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["consecutive_failures"] == 11
        assert status["status"] == "disconnected"

    def test_calculates_next_retry_in_future(self):
        links = _make_links()
        before = time.time()
        links._record_link_failure("uuid-1")

        status = links.get_link_status("uuid-1")
        assert status["next_retry"] > before


# ------------------------------------------------------------------
# TestShouldSkipLink
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestShouldSkipLink:
    def test_returns_true_during_backoff_window(self):
        links = _make_links()
        links._link_status["uuid-1"] = {
            "status": "reconnecting",
            "last_seen": None,
            "consecutive_failures": 2,
            "next_retry": time.time() + 9999,
        }
        assert links._should_skip_link("uuid-1") is True

    def test_returns_false_after_backoff_expires(self):
        links = _make_links()
        links._link_status["uuid-1"] = {
            "status": "reconnecting",
            "last_seen": None,
            "consecutive_failures": 2,
            "next_retry": time.time() - 1,
        }
        assert links._should_skip_link("uuid-1") is False

    def test_returns_false_for_unknown_link(self):
        links = _make_links()
        assert links._should_skip_link("uuid-unknown") is False

    def test_returns_false_when_next_retry_is_zero(self):
        links = _make_links()
        links._link_status["uuid-1"] = {
            "status": "connected",
            "last_seen": time.time(),
            "consecutive_failures": 0,
            "next_retry": 0,
        }
        assert links._should_skip_link("uuid-1") is False


# ------------------------------------------------------------------
# TestExponentialBackoff
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestExponentialBackoff:
    def test_backoff_caps_at_300_seconds(self):
        links = _make_links()
        # Set up with many failures
        links._link_status["uuid-1"] = {
            "status": "disconnected",
            "last_seen": None,
            "consecutive_failures": 50,
            "next_retry": 0,
        }
        before = time.time()
        links._record_link_failure("uuid-1")

        status = links.get_link_status("uuid-1")
        backoff = status["next_retry"] - before
        assert backoff <= 301  # Allow 1 second tolerance for timing

    def test_backoff_increases_with_failures(self):
        links = _make_links()
        backoffs = []
        for i in range(6):
            links._link_status["uuid-1"] = {
                "status": "reconnecting",
                "last_seen": None,
                "consecutive_failures": i,
                "next_retry": 0,
            }
            before = time.time()
            links._record_link_failure("uuid-1")
            status = links.get_link_status("uuid-1")
            backoff = status["next_retry"] - before
            backoffs.append(backoff)

        # Each backoff should be >= the previous (exponential growth, capped)
        for j in range(1, len(backoffs)):
            assert backoffs[j] >= backoffs[j - 1] or backoffs[j] >= 299


# ------------------------------------------------------------------
# TestGetAllLinkStatuses
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetAllLinkStatuses:
    def test_returns_all_tracked_statuses(self):
        links = _make_links()
        links._record_link_success("uuid-1")
        links._record_link_failure("uuid-2")

        statuses = links.get_all_link_statuses()
        assert "uuid-1" in statuses
        assert "uuid-2" in statuses
        assert statuses["uuid-1"]["status"] == "connected"
        assert statuses["uuid-2"]["status"] == "reconnecting"

    def test_returns_empty_dict_when_no_links(self):
        links = _make_links()
        statuses = links.get_all_link_statuses()
        assert statuses == {}

    def test_returns_copy_not_reference(self):
        links = _make_links()
        links._record_link_success("uuid-1")
        statuses = links.get_all_link_statuses()
        statuses["uuid-new"] = {"fake": True}
        # Modifying the return value should not affect internal state
        assert "uuid-new" not in links.get_all_link_statuses()


# ------------------------------------------------------------------
# TestGetLinkStatus
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetLinkStatus:
    def test_returns_default_for_unknown_uuid(self):
        links = _make_links()
        status = links.get_link_status("uuid-unknown")
        assert status["status"] == "unknown"
        assert status["last_seen"] is None
        assert status["consecutive_failures"] == 0
        assert status["next_retry"] == 0


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
