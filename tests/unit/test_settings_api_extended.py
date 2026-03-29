#!/usr/bin/env python3

"""
tests.unit.test_settings_api_extended.py

Extended tests for the settings API handler endpoints not covered
by test_settings_api.py.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v2.settings_api import ApiSettingsHandler
from tests.unit.api_test_base import ApiTestBase


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


SETTINGS_API = "compresso.webserver.api_v2.settings_api"
SETTINGS_LIBRARY_MIXIN = "compresso.webserver.api_v2.settings_library_mixin"
SETTINGS_LINK_MIXIN = "compresso.webserver.api_v2.settings_link_mixin"
SETTINGS_WORKER_GROUPS_MIXIN = "compresso.webserver.api_v2.settings_worker_groups_mixin"


def _mock_initialize(self, **kwargs):
    """Stub out ApiSettingsHandler.initialize to avoid loading real config/session."""
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}
    self.config = MagicMock()
    self.config.get_config_as_dict.return_value = {
        "debugging": False,
        "ui_port": 8888,
        "cache_path": "/tmp/compresso",
    }
    self.config.get_remote_installations.return_value = []


# ------------------------------------------------------------------
# TestSettingsApiWorkerGroups
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_initialize)
class TestSettingsApiWorkerGroups(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f"{SETTINGS_WORKER_GROUPS_MIXIN}.WorkerGroup")
    def test_get_all_worker_groups(self, mock_wg_cls):
        """GET /settings/worker_groups returns 200 with worker_groups key."""
        mock_wg_cls.get_all_worker_groups.return_value = [
            {
                "id": 1,
                "name": "Default",
                "number_of_workers": 3,
                "locked": False,
                "worker_type": "cpu",
                "worker_event_schedules": [],
                "tags": [],
            },
        ]
        resp = self.get_json("/settings/worker_groups")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "worker_groups" in data

    @patch(f"{SETTINGS_WORKER_GROUPS_MIXIN}.WorkerGroup")
    def test_read_worker_group_config(self, mock_wg_cls):
        """POST /settings/worker_group/read returns 200."""
        mock_wg = MagicMock()
        mock_wg.get_id.return_value = 1
        mock_wg.get_locked.return_value = False
        mock_wg.get_name.return_value = "Default"
        mock_wg.get_number_of_workers.return_value = 3
        mock_wg.get_worker_type.return_value = "cpu"
        mock_wg.get_worker_event_schedules.return_value = []
        mock_wg.get_tags.return_value = []
        mock_wg_cls.return_value = mock_wg

        resp = self.post_json("/settings/worker_group/read", {"id": 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data.get("name") == "Default"

    @patch("compresso.webserver.helpers.settings.save_worker_group_config")
    def test_write_worker_group_config(self, mock_save_wg):
        """POST /settings/worker_group/write returns 200."""
        resp = self.post_json(
            "/settings/worker_group/write",
            {
                "id": 1,
                "name": "Default",
                "number_of_workers": 3,
                "worker_type": "cpu",
                "locked": False,
                "worker_event_schedules": [],
                "tags": [],
            },
        )
        assert resp.code == 200
        mock_save_wg.assert_called_once()

    @patch(f"{SETTINGS_WORKER_GROUPS_MIXIN}.WorkerGroup")
    def test_remove_worker_group_success(self, mock_wg_cls):
        """DELETE /settings/worker_group/remove returns 200."""
        mock_wg = MagicMock()
        mock_wg.delete.return_value = True
        mock_wg_cls.return_value = mock_wg

        resp = self.fetch(
            "/compresso/api/v2/settings/worker_group/remove",
            method="DELETE",
            body=json.dumps({"id": 2}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 200

    @patch(f"{SETTINGS_WORKER_GROUPS_MIXIN}.WorkerGroup")
    def test_remove_worker_group_failure(self, mock_wg_cls):
        """DELETE /settings/worker_group/remove returns 500 on failure."""
        mock_wg = MagicMock()
        mock_wg.delete.return_value = False
        mock_wg_cls.return_value = mock_wg

        resp = self.fetch(
            "/compresso/api/v2/settings/worker_group/remove",
            method="DELETE",
            body=json.dumps({"id": 2}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


# ------------------------------------------------------------------
# TestSettingsApiLibraryConfig
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_initialize)
class TestSettingsApiLibraryConfig(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f"{SETTINGS_LIBRARY_MIXIN}.Library")
    def test_read_library_config(self, mock_lib_cls):
        """POST /settings/library/read returns 200 with library config."""
        mock_lib = MagicMock()
        mock_lib.get_id.return_value = 1
        mock_lib.get_name.return_value = "Movies"
        mock_lib.get_path.return_value = "/movies"
        mock_lib.get_locked.return_value = False
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_scanner.return_value = True
        mock_lib.get_enable_inotify.return_value = False
        mock_lib.get_priority_score.return_value = 0
        mock_lib.get_tags.return_value = []
        mock_lib.get_target_codecs.return_value = []
        mock_lib.get_skip_codecs.return_value = []
        mock_lib.get_size_guardrail_enabled.return_value = False
        mock_lib.get_size_guardrail_min_pct.return_value = 10
        mock_lib.get_size_guardrail_max_pct.return_value = 90
        mock_lib.get_replacement_policy.return_value = ""
        mock_lib.get_enabled_plugins.return_value = []
        mock_lib_cls.return_value = mock_lib

        resp = self.post_json("/settings/library/read", {"id": 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "library_config" in data

    def test_read_library_config_new_library(self):
        """POST /settings/library/read with id=0 returns empty template."""
        resp = self.post_json("/settings/library/read", {"id": 0})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["library_config"]["id"] == 0

    @patch("compresso.webserver.helpers.settings.save_library_config", return_value=True)
    def test_write_library_config_success(self, mock_save):
        """POST /settings/library/write returns 200."""
        resp = self.post_json(
            "/settings/library/write",
            {
                "library_config": {
                    "id": 1,
                    "name": "Movies",
                    "path": "/movies",
                    "enable_remote_only": False,
                    "enable_scanner": True,
                    "enable_inotify": False,
                    "priority_score": 0,
                },
                "plugins": {"enabled_plugins": []},
            },
        )
        assert resp.code == 200

    @patch("compresso.webserver.helpers.settings.save_library_config", return_value=False)
    def test_write_library_config_failure(self, mock_save):
        """POST /settings/library/write returns 500 on save failure."""
        resp = self.post_json(
            "/settings/library/write",
            {
                "library_config": {
                    "id": 1,
                    "name": "Movies",
                    "path": "/movies",
                    "enable_remote_only": False,
                    "enable_scanner": True,
                    "enable_inotify": False,
                    "priority_score": 0,
                },
                "plugins": {"enabled_plugins": []},
            },
        )
        assert resp.code == 500

    @patch(f"{SETTINGS_LIBRARY_MIXIN}.Library")
    def test_remove_library_success(self, mock_lib_cls):
        """DELETE /settings/library/remove returns 200."""
        mock_lib = MagicMock()
        mock_lib.delete.return_value = True
        mock_lib_cls.return_value = mock_lib

        resp = self.fetch(
            "/compresso/api/v2/settings/library/remove",
            method="DELETE",
            body=json.dumps({"id": 2}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 200

    @patch(f"{SETTINGS_LIBRARY_MIXIN}.Library")
    def test_remove_library_failure(self, mock_lib_cls):
        """DELETE /settings/library/remove returns 500 on failure."""
        mock_lib = MagicMock()
        mock_lib.delete.return_value = False
        mock_lib_cls.return_value = mock_lib

        resp = self.fetch(
            "/compresso/api/v2/settings/library/remove",
            method="DELETE",
            body=json.dumps({"id": 2}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


# ------------------------------------------------------------------
# TestSettingsApiLibraryExportImport
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_initialize)
class TestSettingsApiLibraryExportImport(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f"{SETTINGS_LIBRARY_MIXIN}.Library")
    def test_export_library_plugin_config(self, mock_lib_cls):
        """POST /settings/library/export returns 200."""
        mock_lib_cls.export.return_value = {
            "plugins": {
                "enabled_plugins": [],
                "plugin_flow": {},
            },
            "library_config": {
                "name": "Movies",
                "path": "/movies",
                "enable_remote_only": False,
                "enable_scanner": True,
                "enable_inotify": False,
                "tags": [],
            },
        }
        resp = self.post_json("/settings/library/export", {"id": 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "plugins" in data

    @patch("compresso.webserver.helpers.settings.save_library_config", return_value=True)
    def test_import_library_plugin_config_success(self, mock_save):
        """POST /settings/library/import returns 200."""
        resp = self.post_json(
            "/settings/library/import",
            {
                "library_id": 1,
                "library_config": {"name": "Movies", "path": "/movies"},
                "plugins": {"enabled_plugins": [], "plugin_flow": {}},
            },
        )
        assert resp.code == 200


# ------------------------------------------------------------------
# TestSettingsApiValidateRemote
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_initialize)
class TestSettingsApiValidateRemote(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f"{SETTINGS_LINK_MIXIN}.Links")
    def test_validate_remote_installation(self, mock_links_cls):
        """POST /settings/link/validate returns 200."""
        mock_links = MagicMock()
        mock_links.validate_remote_installation.return_value = {
            "uuid": "abc-123",
            "name": "Remote Node",
            "version": "1.0.0",
        }
        mock_links_cls.return_value = mock_links

        resp = self.post_json(
            "/settings/link/validate",
            {
                "address": "10.0.0.2:8888",
                "auth": "None",
                "username": "",
                "password": "",
            },
        )
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "installation" in data

    @patch(f"{SETTINGS_LINK_MIXIN}.Links")
    def test_validate_remote_installation_failure(self, mock_links_cls):
        """POST /settings/link/validate returns 500 on failure."""
        mock_links = MagicMock()
        mock_links.validate_remote_installation.side_effect = Exception("Connection refused")
        mock_links_cls.return_value = mock_links

        resp = self.post_json(
            "/settings/link/validate",
            {
                "address": "10.0.0.2:8888",
                "auth": "None",
                "username": "",
                "password": "",
            },
        )
        assert resp.code == 500


# ------------------------------------------------------------------
# TestSettingsApiLinkRemove
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_initialize)
class TestSettingsApiLinkRemove(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f"{SETTINGS_LINK_MIXIN}.Links")
    def test_remove_link_success(self, mock_links_cls):
        """DELETE /settings/link/remove returns 200."""
        mock_links = MagicMock()
        mock_links.delete_remote_installation_link_config.return_value = True
        mock_links_cls.return_value = mock_links

        resp = self.fetch(
            "/compresso/api/v2/settings/link/remove",
            method="DELETE",
            body=json.dumps({"uuid": "abc-123"}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 200

    @patch(f"{SETTINGS_LINK_MIXIN}.Links")
    def test_remove_link_failure(self, mock_links_cls):
        """DELETE /settings/link/remove returns 500 on failure."""
        mock_links = MagicMock()
        mock_links.delete_remote_installation_link_config.return_value = False
        mock_links_cls.return_value = mock_links

        resp = self.fetch(
            "/compresso/api/v2/settings/link/remove",
            method="DELETE",
            body=json.dumps({"uuid": "abc-123"}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


# ------------------------------------------------------------------
# TestSettingsApiEndpointNotFound
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_initialize)
class TestSettingsApiEndpointNotFound(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    def test_unknown_endpoint_returns_404(self):
        """GET /settings/nonexistent returns 404."""
        resp = self.get_json("/settings/nonexistent")
        assert resp.code == 404


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
