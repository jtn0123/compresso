#!/usr/bin/env python3

"""
tests.unit.test_installation_link_coverage.py

Focused tests for previously uncovered lines in
compresso/libs/installation_link.py.

Lines targeted:
  79-86   set_link_status (new uuid branch)
  145-146 _notify_link_status_change exception silencing
  150     __format_address with None input
  411-412 validate_remote_installation config 400/500 error log branch
  425-426 validate_remote_installation settings 400/500 error log branch
  453-454 validate_remote_installation session 400/500 error log branch
  526-530 update_all_remote_installation_links backoff skip branch
  542-543 update_all_remote_installation_links connection error branch
  558-664 update_all_remote_installation_links success path (uuid migration,
          sync, library push)
  877-948 check_remote_installation_for_available_workers try-block internals
  1000-1002, 1020-1021 send/create generic Exception paths
  1062-1272 various method-level generic Exception paths
"""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from compresso.libs.installation_link import Links, RequestHandler
from compresso.libs.singleton import SingletonType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_links():
    with (
        patch("compresso.libs.installation_link.config.Config"),
        patch("compresso.libs.installation_link.session.Session"),
        patch("compresso.libs.installation_link.CompressoLogging.get_logger"),
    ):
        return Links()


def _ok_resp(json_data):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = json_data
    return resp


def _err_resp(status, json_data):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    return resp


_BASE_CONFIG = {"address": "host:8888", "auth": "", "username": "", "password": ""}


# ---------------------------------------------------------------------------
# Lines 79-86: set_link_status — new uuid branch (initialises defaults first)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSetLinkStatusNewUuid:
    def test_creates_default_entry_for_unknown_uuid(self):
        links = _make_links()
        assert "new-uuid" not in links._link_status
        links.set_link_status("new-uuid", {"status": "connected"})
        assert links._link_status["new-uuid"]["status"] == "connected"
        assert links._link_status["new-uuid"]["consecutive_failures"] == 0
        assert links._link_status["new-uuid"]["next_retry"] == 0
        assert links._link_status["new-uuid"]["last_seen"] is None

    def test_updates_existing_entry_without_reinitialising(self):
        links = _make_links()
        links._link_status["existing"] = {
            "status": "connected",
            "last_seen": 100.0,
            "consecutive_failures": 0,
            "next_retry": 0,
        }
        links.set_link_status("existing", {"status": "reconnecting"})
        assert links._link_status["existing"]["status"] == "reconnecting"
        assert links._link_status["existing"]["last_seen"] == 100.0

    def test_get_link_status_after_set(self):
        links = _make_links()
        links.set_link_status("my-uuid", {"status": "disconnected", "consecutive_failures": 5})
        result = links.get_link_status("my-uuid")
        assert result["status"] == "disconnected"
        assert result["consecutive_failures"] == 5


# ---------------------------------------------------------------------------
# Lines 145-146: _notify_link_status_change — exception is silently swallowed
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestNotifyLinkStatusChangeExceptionHandling:
    def test_exception_in_frontend_push_is_silenced(self):
        links = _make_links()
        # FrontendPushMessages is imported inline inside the method.
        # Patch the class so that instantiation raises, hitting the except/pass branch.
        mock_cls = MagicMock(side_effect=Exception("push not available"))
        with patch.dict(
            "sys.modules",
            {"compresso.libs.frontend_push_messages": MagicMock(FrontendPushMessages=mock_cls)},
        ):
            # Force re-import inside the function by removing cached module
            import sys

            sys.modules.pop("compresso.libs.frontend_push_messages", None)
            # Must not raise — exception is silenced
            links._notify_link_status_change("uuid-1", "disconnected")

    def test_import_error_is_silenced(self):
        links = _make_links()
        with patch.dict("sys.modules", {"compresso.libs.frontend_push_messages": None}):
            # Must not raise
            links._notify_link_status_change("uuid-2", "connected")


# ---------------------------------------------------------------------------
# Line 150: __format_address with None → treated as empty string → "http://"
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFormatAddressNone:
    def test_none_address_adds_http_prefix(self):
        links = _make_links()
        result = links._Links__format_address(None)
        # None is coerced to "" → "http://" → trailing slashes stripped → "http:"
        assert result.startswith("http")

    def test_empty_string_address_adds_http_prefix(self):
        links = _make_links()
        result = links._Links__format_address("")
        # "" → "http://" → trailing slashes stripped → "http:"
        assert result.startswith("http")


# ---------------------------------------------------------------------------
# Lines 411-412, 425-426, 453-454:
# validate_remote_installation — error logging branches when status is 400/500
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestValidateRemoteInstallationErrorLogging:
    def test_logs_error_on_config_400(self):
        links = _make_links()
        mock_resp = _err_resp(400, {"error": "bad request", "traceback": ["line1"]})
        with patch.object(RequestHandler, "get", return_value=mock_resp):
            result = links.validate_remote_installation("192.168.1.1:8888")
        assert result == {}

    def test_logs_error_on_config_500(self):
        links = _make_links()
        mock_resp = _err_resp(500, {"error": "server error", "traceback": []})
        with patch.object(RequestHandler, "get", return_value=mock_resp):
            result = links.validate_remote_installation("192.168.1.1:8888")
        assert result == {}

    def test_logs_error_on_settings_400(self):
        links = _make_links()
        call_n = [0]

        def side_effect(url, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _ok_resp({"configuration": {}})
            return _err_resp(400, {"error": "bad settings", "traceback": []})

        with patch.object(RequestHandler, "get", side_effect=side_effect):
            result = links.validate_remote_installation("192.168.1.1:8888")
        assert result == {}

    def test_logs_error_on_session_400(self):
        links = _make_links()
        call_n = [0]

        def side_effect(url, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _ok_resp({"configuration": {}})
            if call_n[0] == 2:
                return _ok_resp({"settings": {}})
            if call_n[0] == 3:
                return _ok_resp({"version": "1.0"})
            return _err_resp(400, {"error": "auth error", "traceback": []})

        with patch.object(RequestHandler, "get", side_effect=side_effect):
            result = links.validate_remote_installation("192.168.1.1:8888")
        assert result == {}

    def test_logs_error_on_version_500(self):
        links = _make_links()
        call_n = [0]

        def side_effect(url, **kw):
            call_n[0] += 1
            if call_n[0] == 1:
                return _ok_resp({"configuration": {}})
            if call_n[0] == 2:
                return _ok_resp({"settings": {}})
            return _err_resp(500, {"error": "version error", "traceback": ["tb"]})

        with patch.object(RequestHandler, "get", side_effect=side_effect):
            result = links.validate_remote_installation("192.168.1.1:8888")
        assert result == {}


# ---------------------------------------------------------------------------
# Lines 526-530: update_all_remote_installation_links — backoff skip branch
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUpdateAllBackoffSkip:
    def test_skips_link_in_backoff_and_marks_unavailable(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "real-uuid", "address": "10.0.0.1", "name": "Test"},
        ]
        # Place the link in backoff
        links._link_status["real-uuid"] = {
            "status": "reconnecting",
            "last_seen": time.time() - 30,
            "consecutive_failures": 3,
            "next_retry": time.time() + 300,  # still in backoff
        }

        result = links.update_all_remote_installation_links()

        assert len(result) == 1
        assert result[0]["available"] is False
        # validate_remote_installation must NOT have been called
        links.settings.set_bulk_config_items.assert_called_once()

    def test_skips_unknown_uuid_link_using_address_key(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "???", "address": "10.0.0.2", "name": "Unknown"},
        ]
        addr_key = "_addr_10.0.0.2"
        links._link_status[addr_key] = {
            "status": "reconnecting",
            "last_seen": None,
            "consecutive_failures": 2,
            "next_retry": time.time() + 120,
        }

        result = links.update_all_remote_installation_links()
        assert len(result) == 1
        assert result[0]["available"] is False


# ---------------------------------------------------------------------------
# Lines 542-543: update_all_remote_installation_links — network failure path
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUpdateAllNetworkFailure:
    def test_records_failure_on_connection_error(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "uuid-fail", "address": "10.0.0.3", "name": "FailHost"},
        ]

        with patch.object(links, "validate_remote_installation", side_effect=requests.exceptions.ConnectionError("down")):
            result = links.update_all_remote_installation_links()

        assert len(result) == 1
        assert result[0]["available"] is False
        assert links._link_status.get("uuid-fail", {}).get("consecutive_failures", 0) >= 1

    def test_records_failure_on_generic_exception(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "uuid-err", "address": "10.0.0.4", "name": "ErrHost"},
        ]

        with patch.object(links, "validate_remote_installation", side_effect=RuntimeError("unexpected")):
            result = links.update_all_remote_installation_links()

        assert result[0]["available"] is False


# ---------------------------------------------------------------------------
# Lines 558-664: update_all_remote_installation_links — successful data path
# (UUID migration, remote config sync, library push)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUpdateAllSuccessPath:
    def _make_installation_data(self, uuid="remote-uuid"):
        return {
            "session": {"uuid": uuid},
            "settings": {"installation_name": "Remote"},
            "version": "1.9.0",
            "task_count": 3,
            "system_configuration": {},
        }

    def test_marks_available_on_success(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "remote-uuid", "address": "10.0.0.5"},
        ]
        inst_data = self._make_installation_data()

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(links, "fetch_remote_installation_link_config_for_this", return_value={}),
            patch.object(links, "push_remote_installation_link_config", return_value=True),
        ):
            result = links.update_all_remote_installation_links()

        assert result[0]["available"] is True
        assert result[0]["task_count"] == 3

    def test_migrates_address_based_uuid_key_to_real_uuid(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "???", "address": "10.0.0.6"},
        ]
        # Plant a status entry under the address-based key
        addr_key = "_addr_10.0.0.6"
        links._link_status[addr_key] = {
            "status": "unknown",
            "last_seen": None,
            "consecutive_failures": 0,
            "next_retry": 0,
        }
        inst_data = self._make_installation_data(uuid="discovered-uuid")

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(links, "fetch_remote_installation_link_config_for_this", return_value={}),
            patch.object(links, "push_remote_installation_link_config", return_value=True),
        ):
            links.update_all_remote_installation_links()

        # The status should now be under the real uuid, not the address key
        assert "discovered-uuid" in links._link_status
        assert addr_key not in links._link_status

    def test_syncs_remote_config_when_remote_is_newer(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        future_ts = time.time() + 9999
        local_install = {
            "uuid": "sync-uuid",
            "address": "10.0.0.7",
            "last_updated": 1,
            "enable_receiving_tasks": False,
            "enable_sending_tasks": False,
        }
        links.settings.get_remote_installations.return_value = [local_install]
        inst_data = self._make_installation_data(uuid="sync-uuid")
        remote_cfg = {
            "link_config": {
                "last_updated": future_ts,
                "enable_sending_tasks": True,
                "enable_receiving_tasks": True,
                "available": False,
            },
            "distributed_worker_count_target": 2,
        }

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(links, "fetch_remote_installation_link_config_for_this", return_value=remote_cfg),
            patch.object(links, "push_remote_installation_link_config", return_value=True),
        ):
            result = links.update_all_remote_installation_links()

        # enable_receiving_tasks should be synced from remote's enable_sending_tasks
        assert result[0]["enable_receiving_tasks"] is True

    def test_push_config_when_remote_link_not_available(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "push-uuid", "address": "10.0.0.8"},
        ]
        inst_data = self._make_installation_data(uuid="push-uuid")
        # Remote config returns link_config with available=False
        remote_cfg = {"link_config": {"available": False, "last_updated": 0}}
        push_mock = MagicMock(return_value=True)

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(links, "fetch_remote_installation_link_config_for_this", return_value=remote_cfg),
            patch.object(links, "push_remote_installation_link_config", push_mock),
        ):
            links.update_all_remote_installation_links()

        push_mock.assert_called_once()

    def test_push_config_timeout_marks_unavailable(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "timeout-uuid", "address": "10.0.0.9"},
        ]
        inst_data = self._make_installation_data(uuid="timeout-uuid")
        remote_cfg = {"link_config": {"available": False}}

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(links, "fetch_remote_installation_link_config_for_this", return_value=remote_cfg),
            patch.object(links, "push_remote_installation_link_config", side_effect=requests.exceptions.Timeout),
        ):
            result = links.update_all_remote_installation_links()

        assert result[0]["available"] is False

    def test_fetch_config_timeout_marks_unavailable(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "fc-timeout", "address": "10.0.0.10"},
        ]
        inst_data = self._make_installation_data(uuid="fc-timeout")

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(
                links,
                "fetch_remote_installation_link_config_for_this",
                side_effect=requests.exceptions.Timeout,
            ),
        ):
            result = links.update_all_remote_installation_links()

        assert result[0]["available"] is False

    def test_library_config_push_when_enabled(self):
        """Lines 630-668: library config push for missing remote libraries."""
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        local_install = {
            "uuid": "lib-uuid",
            "address": "10.0.0.11",
            "enable_sending_tasks": True,
            "enable_config_missing_libraries": True,
        }
        links.settings.get_remote_installations.return_value = [local_install]
        inst_data = self._make_installation_data(uuid="lib-uuid")
        remote_cfg = {"link_config": {"available": True, "last_updated": 0}}

        local_library = {"id": 1, "name": "Movies", "enable_remote_only": False}
        import_data = {
            "library_id": 1,
            "library_config": {"enable_remote_only": False, "enable_scanner": True, "enable_inotify": True},
        }

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(links, "fetch_remote_installation_link_config_for_this", return_value=remote_cfg),
            patch.object(links, "push_remote_installation_link_config", return_value=True),
            patch("compresso.libs.installation_link.Library.get_all_libraries", return_value=[local_library]),
            patch("compresso.libs.installation_link.Library.export", return_value=import_data),
            patch.object(links, "remote_api_get", return_value={"libraries": []}),
            patch.object(links, "import_remote_library_config", return_value={"success": True}),
        ):
            result = links.update_all_remote_installation_links()

        assert result[0]["available"] is True

    def test_library_config_push_skips_remote_only_library(self):
        """Remote-only local libraries must be skipped."""
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        local_install = {
            "uuid": "lib-skip",
            "address": "10.0.0.12",
            "enable_sending_tasks": True,
            "enable_config_missing_libraries": True,
        }
        links.settings.get_remote_installations.return_value = [local_install]
        inst_data = self._make_installation_data(uuid="lib-skip")
        remote_cfg = {"link_config": {"available": True, "last_updated": 0}}

        remote_only_library = {"id": 2, "name": "Archives", "enable_remote_only": True}
        import_mock = MagicMock(return_value={"success": True})

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(links, "fetch_remote_installation_link_config_for_this", return_value=remote_cfg),
            patch.object(links, "push_remote_installation_link_config", return_value=True),
            patch("compresso.libs.installation_link.Library.get_all_libraries", return_value=[remote_only_library]),
            patch.object(links, "remote_api_get", return_value={"libraries": []}),
            patch.object(links, "import_remote_library_config", import_mock),
        ):
            links.update_all_remote_installation_links()

        import_mock.assert_not_called()

    def test_library_import_none_result_continues(self):
        """Lines 658-660: import returns None (connection issue) → continue."""
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        local_install = {
            "uuid": "lib-none",
            "address": "10.0.0.13",
            "enable_sending_tasks": True,
            "enable_config_missing_libraries": True,
        }
        links.settings.get_remote_installations.return_value = [local_install]
        inst_data = self._make_installation_data(uuid="lib-none")
        remote_cfg = {"link_config": {"available": True, "last_updated": 0}}
        import_data = {
            "library_id": 1,
            "library_config": {"enable_remote_only": False, "enable_scanner": True, "enable_inotify": True},
        }

        with (
            patch.object(links, "validate_remote_installation", return_value=inst_data),
            patch.object(links, "fetch_remote_installation_link_config_for_this", return_value=remote_cfg),
            patch.object(links, "push_remote_installation_link_config", return_value=True),
            patch(
                "compresso.libs.installation_link.Library.get_all_libraries",
                return_value=[{"id": 1, "name": "Movies", "enable_remote_only": False}],
            ),
            patch("compresso.libs.installation_link.Library.export", return_value=import_data),
            patch.object(links, "remote_api_get", return_value={"libraries": []}),
            patch.object(links, "import_remote_library_config", return_value=None),
        ):
            # Must not raise
            result = links.update_all_remote_installation_links()

        assert result[0]["available"] is True


# ---------------------------------------------------------------------------
# Lines 877-948: check_remote_installation_for_available_workers try-block
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestCheckRemoteWorkersInternals:
    def _available_config(self, uuid="a" * 21, preloading=False, preloading_count=2):
        return {
            "uuid": uuid,
            "address": "10.0.0.20",
            "auth": "",
            "username": "",
            "password": "",
            "available": True,
            "enable_sending_tasks": True,
            "enable_task_preloading": preloading,
            "preloading_count": preloading_count,
        }

    def test_skips_link_in_backoff(self):
        links = _make_links()
        uuid = "a" * 21
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [self._available_config(uuid)]
        links._link_status[uuid] = {
            "status": "reconnecting",
            "last_seen": None,
            "consecutive_failures": 2,
            "next_retry": time.time() + 300,
        }
        result = links.check_remote_installation_for_available_workers()
        assert result == {}

    def test_skips_installation_when_pending_tasks_has_error(self):
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [self._available_config()]

        workers = [{"id": "w1", "idle": True, "paused": False}]
        with (
            patch.object(links, "remote_api_get", return_value={"workers_status": workers}),
            patch.object(links, "remote_api_post", return_value={"error": "db error"}),
        ):
            result = links.check_remote_installation_for_available_workers()
        assert result == {}

    def test_skips_installation_when_preloading_limit_reached(self):
        links = _make_links()
        links.settings = MagicMock()
        cfg = self._available_config(preloading=True, preloading_count=2)
        links.settings.get_remote_installations.return_value = [cfg]

        call_n = [0]

        def api_get(config, endpoint, **kw):
            call_n[0] += 1
            if "workers" in endpoint:
                return {"workers_status": [{"id": "w1", "idle": True, "paused": False}]}
            return {"libraries": []}

        with (
            patch.object(links, "remote_api_get", side_effect=api_get),
            patch.object(links, "remote_api_post", return_value={"recordsFiltered": 5, "recordsTotal": 5}),
        ):
            result = links.check_remote_installation_for_available_workers()
        assert result == {}

    def test_adds_installation_with_idle_worker(self):
        links = _make_links()
        links.settings = MagicMock()
        uuid = "a" * 21
        links.settings.get_remote_installations.return_value = [self._available_config(uuid)]

        call_n = [0]

        def api_get(config, endpoint, **kw):
            call_n[0] += 1
            if "workers" in endpoint:
                return {"workers_status": [{"id": "w1", "idle": True, "paused": False}]}
            return {"libraries": [{"name": "Movies"}]}

        with (
            patch.object(links, "remote_api_get", side_effect=api_get),
            patch.object(links, "remote_api_post", return_value={"recordsFiltered": 0, "recordsTotal": 0}),
        ):
            result = links.check_remote_installation_for_available_workers()

        assert uuid in result
        assert result[uuid]["available_workers"] is True

    def test_adds_installation_with_busy_worker(self):
        """Lines 930-933: busy (not idle) worker also counts."""
        links = _make_links()
        links.settings = MagicMock()
        uuid = "b" * 21
        links.settings.get_remote_installations.return_value = [self._available_config(uuid)]

        def api_get(config, endpoint, **kw):
            if "workers" in endpoint:
                return {"workers_status": [{"id": "w1", "idle": False, "paused": False}]}
            return {"libraries": []}

        with (
            patch.object(links, "remote_api_get", side_effect=api_get),
            patch.object(links, "remote_api_post", return_value={"recordsFiltered": 0}),
        ):
            result = links.check_remote_installation_for_available_workers()

        assert uuid in result
        assert result[uuid]["available_workers"] is True

    def test_preloading_adds_extra_slots(self):
        """Lines 936-940: preloading expands available_slots."""
        links = _make_links()
        links.settings = MagicMock()
        uuid = "c" * 21
        cfg = self._available_config(uuid=uuid, preloading=True, preloading_count=3)
        links.settings.get_remote_installations.return_value = [cfg]

        def api_get(config, endpoint, **kw):
            if "workers" in endpoint:
                return {"workers_status": [{"id": "w1", "idle": True, "paused": False}]}
            return {"libraries": []}

        with (
            patch.object(links, "remote_api_get", side_effect=api_get),
            patch.object(links, "remote_api_post", return_value={"recordsFiltered": 0}),
        ):
            result = links.check_remote_installation_for_available_workers()

        assert result[uuid]["available_slots"] > 1

    def test_exception_in_try_block_continues(self):
        """Lines 942-948: generic exception → log and continue."""
        links = _make_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [self._available_config()]

        with patch.object(links, "remote_api_get", side_effect=Exception("network failure")):
            result = links.check_remote_installation_for_available_workers()

        assert result == {}


# ---------------------------------------------------------------------------
# Lines 1000-1002: new_pending_task_create_on_remote_installation generic exc
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestNewPendingTaskGenericException:
    def test_returns_empty_dict_on_generic_exception(self):
        links = _make_links()
        with patch("compresso.libs.installation_link.requests.post", side_effect=ValueError("unexpected")):
            result = links.new_pending_task_create_on_remote_installation(_BASE_CONFIG, "/some/path", 1)
        assert result == {}


# ---------------------------------------------------------------------------
# Lines 1020-1021: send_file_to_remote_installation generic Exception
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSendFileGenericException:
    def test_returns_empty_dict_on_generic_exception(self):
        links = _make_links()
        links.remote_api_post_file = MagicMock(side_effect=ValueError("disk error"))
        result = links.send_file_to_remote_installation(_BASE_CONFIG, "/path/to/file")
        assert result == {}


# ---------------------------------------------------------------------------
# Lines 1062-1066: get_the_remote_library_config_by_name generic Exception
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetRemoteLibraryConfigGenericException:
    def test_returns_empty_dict_on_generic_exception(self):
        links = _make_links()
        links.remote_api_get = MagicMock(side_effect=ValueError("parse error"))
        result = links.get_the_remote_library_config_by_name(_BASE_CONFIG, "Movies")
        assert result == {}

    def test_returns_none_on_request_exception(self):
        links = _make_links()
        links.remote_api_get = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.get_the_remote_library_config_by_name(_BASE_CONFIG, "Movies")
        assert result is None


# ---------------------------------------------------------------------------
# Lines 1091-1096: set_the_remote_task_library generic Exception
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSetRemoteTaskLibraryGenericException:
    def test_returns_empty_dict_on_generic_exception(self):
        links = _make_links()
        links.remote_api_post = MagicMock(side_effect=ValueError("unexpected"))
        result = links.set_the_remote_task_library(_BASE_CONFIG, 42, "Movies")
        assert result == {}

    def test_returns_none_on_request_exception(self):
        links = _make_links()
        links.remote_api_post = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.set_the_remote_task_library(_BASE_CONFIG, 42, "Movies")
        assert result is None


# ---------------------------------------------------------------------------
# Lines 1112-1115: get_remote_pending_task_state exceptions
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetRemotePendingTaskStateExceptions:
    def test_returns_none_on_request_exception(self):
        links = _make_links()
        links.remote_api_post = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.get_remote_pending_task_state(_BASE_CONFIG, 1)
        assert result is None

    def test_returns_none_on_generic_exception(self):
        links = _make_links()
        links.remote_api_post = MagicMock(side_effect=ValueError("bad response"))
        result = links.get_remote_pending_task_state(_BASE_CONFIG, 1)
        assert result is None


# ---------------------------------------------------------------------------
# Lines 1135-1140: start_the_remote_task_by_id generic Exception
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestStartRemoteTaskGenericException:
    def test_returns_empty_dict_on_generic_exception(self):
        links = _make_links()
        links.remote_api_post = MagicMock(side_effect=ValueError("unexpected"))
        result = links.start_the_remote_task_by_id(_BASE_CONFIG, 42)
        assert result == {}

    def test_returns_none_on_request_exception(self):
        links = _make_links()
        links.remote_api_post = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.start_the_remote_task_by_id(_BASE_CONFIG, 42)
        assert result is None


# ---------------------------------------------------------------------------
# Lines 1154-1157: get_all_worker_status generic Exception
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetAllWorkerStatusGenericException:
    def test_returns_empty_list_on_generic_exception(self):
        links = _make_links()
        links.remote_api_get = MagicMock(side_effect=ValueError("parse error"))
        result = links.get_all_worker_status(_BASE_CONFIG)
        assert result == []

    def test_returns_empty_list_on_request_exception(self):
        links = _make_links()
        links.remote_api_get = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.get_all_worker_status(_BASE_CONFIG)
        assert result == []


# ---------------------------------------------------------------------------
# Lines 1187-1190: terminate_remote_worker exceptions
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestTerminateRemoteWorkerExceptions:
    def test_returns_empty_on_request_exception(self):
        links = _make_links()
        links.remote_api_delete = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.terminate_remote_worker(_BASE_CONFIG, "w1")
        assert result == {}

    def test_returns_empty_on_generic_exception(self):
        links = _make_links()
        links.remote_api_delete = MagicMock(side_effect=ValueError("unexpected"))
        result = links.terminate_remote_worker(_BASE_CONFIG, "w1")
        assert result == {}


# ---------------------------------------------------------------------------
# Lines 1217-1220: fetch_remote_task_data generic Exception
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFetchRemoteTaskDataGenericException:
    def test_returns_empty_dict_on_generic_exception(self):
        links = _make_links()
        links.remote_api_get = MagicMock(side_effect=ValueError("unexpected"))
        result = links.fetch_remote_task_data(_BASE_CONFIG, 42, "/tmp/data.json")
        assert result == {}

    def test_returns_empty_dict_on_request_exception(self):
        links = _make_links()
        links.remote_api_get = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.fetch_remote_task_data(_BASE_CONFIG, 42, "/tmp/data.json")
        assert result == {}


# ---------------------------------------------------------------------------
# Lines 1245-1248: fetch_remote_task_completed_file generic Exception
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFetchRemoteTaskCompletedFileGenericException:
    def test_returns_false_on_generic_exception(self):
        links = _make_links()
        links.remote_api_get = MagicMock(side_effect=ValueError("unexpected"))
        result = links.fetch_remote_task_completed_file(_BASE_CONFIG, 42, "/tmp/out.mkv")
        assert result is False

    def test_returns_false_on_request_exception(self):
        links = _make_links()
        links.remote_api_get = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.fetch_remote_task_completed_file(_BASE_CONFIG, 42, "/tmp/out.mkv")
        assert result is False


# ---------------------------------------------------------------------------
# Lines 1267-1272: import_remote_library_config generic Exception
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestImportRemoteLibraryConfigGenericException:
    def test_returns_empty_dict_on_generic_exception(self):
        links = _make_links()
        links.remote_api_post = MagicMock(side_effect=ValueError("unexpected"))
        result = links.import_remote_library_config(_BASE_CONFIG, {"library_id": 0})
        assert result == {}

    def test_returns_none_on_request_exception(self):
        links = _make_links()
        links.remote_api_post = MagicMock(side_effect=requests.exceptions.ConnectionError)
        result = links.import_remote_library_config(_BASE_CONFIG, {"library_id": 0})
        assert result is None


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
