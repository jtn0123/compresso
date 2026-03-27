#!/usr/bin/env python3

"""
tests.unit.test_plugins_api_handler.py

Tests for the plugins API handler endpoints.

"""

import json
from unittest.mock import MagicMock, patch

import pytest

from compresso.webserver.api_v2.plugins_api import ApiPluginsHandler
from tests.unit.api_test_base import ApiTestBase

PLUGINS_HELPERS = "compresso.webserver.helpers.plugins"


def _mock_initialize(self, **kwargs):
    """Stub out ApiPluginsHandler.initialize to avoid loading real session/queues."""
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


def _make_plugin_setting(**overrides):
    """Create a valid plugin settings item matching PluginsConfigInputItemSchema."""
    item = {
        "key_id": "abc123",
        "key": "crf",
        "value": "23",
        "input_type": "text",
        "label": "CRF Value",
        "description": "Quality setting",
        "tooltip": "Lower is better",
        "select_options": [],
        "slider_options": {},
        "display": "visible",
        "sub_setting": False,
    }
    item.update(overrides)
    return item


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _mock_initialize)
class TestPluginsApiInstalled(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + ".prepare_filtered_plugins")
    def test_get_installed_plugins_success(self, mock_plugins):
        mock_plugins.return_value = {
            "recordsTotal": 3,
            "recordsFiltered": 2,
            "results": [],
        }
        resp = self.post_json("/plugins/installed", {"start": 0, "length": 10})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["recordsTotal"] == 3

    def test_get_installed_plugins_invalid_json(self):
        resp = self.fetch(
            "/compresso/api/v2/plugins/installed",
            method="POST",
            body="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.code == 400

    @patch(PLUGINS_HELPERS + ".prepare_filtered_plugins")
    def test_get_installed_plugins_internal_error(self, mock_plugins):
        mock_plugins.side_effect = Exception("DB error")
        resp = self.post_json("/plugins/installed", {"start": 0, "length": 10})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _mock_initialize)
class TestPluginsApiDeprecated(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    def test_enable_plugins_deprecated(self):
        resp = self.post_json("/plugins/enable", {"id_list": [1]})
        assert resp.code == 410

    def test_disable_plugins_deprecated(self):
        resp = self.post_json("/plugins/disable", {"id_list": [1]})
        assert resp.code == 410


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _mock_initialize)
class TestPluginsApiUpdate(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + ".update_plugins", return_value=True)
    def test_update_plugins_success(self, _mock_update):
        resp = self.post_json("/plugins/update", {"id_list": [1, 2]})
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + ".update_plugins", return_value=False)
    def test_update_plugins_failure(self, _mock_update):
        resp = self.post_json("/plugins/update", {"id_list": [1]})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _mock_initialize)
class TestPluginsApiRemove(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + ".remove_plugins", return_value=True)
    def test_remove_plugins_success(self, _mock_remove):
        resp = self.fetch(
            "/compresso/api/v2/plugins/remove",
            method="DELETE",
            body=json.dumps({"id_list": [1, 2]}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + ".remove_plugins", return_value=False)
    def test_remove_plugins_failure(self, _mock_remove):
        resp = self.fetch(
            "/compresso/api/v2/plugins/remove",
            method="DELETE",
            body=json.dumps({"id_list": [1]}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _mock_initialize)
class TestPluginsApiInfo(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + ".prepare_plugin_info_and_settings")
    def test_get_plugin_info_success(self, mock_info):
        mock_info.return_value = {
            "plugin_id": "encoder.hevc",
            "icon": "",
            "name": "HEVC Encoder",
            "description": "Encode to HEVC",
            "tags": "video",
            "author": "Test",
            "version": "1.0",
            "changelog": "",
            "status": {"installed": True, "update_available": False},
            "settings": [_make_plugin_setting()],
        }
        resp = self.post_json("/plugins/info", {"plugin_id": "encoder.hevc"})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["plugin_id"] == "encoder.hevc"

    @patch(PLUGINS_HELPERS + ".prepare_plugin_info_and_settings")
    def test_get_plugin_info_no_settings(self, mock_info):
        mock_info.return_value = {
            "plugin_id": "encoder.hevc",
            "icon": "",
            "name": "HEVC Encoder",
            "description": "Encode to HEVC",
            "tags": "video",
            "author": "Test",
            "version": "1.0",
            "changelog": "",
            "status": {"installed": True, "update_available": False},
            "settings": [],
        }
        resp = self.post_json("/plugins/info", {"plugin_id": "encoder.hevc"})
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + ".prepare_plugin_info_and_settings")
    def test_get_plugin_info_internal_error(self, mock_info):
        mock_info.side_effect = Exception("Plugin not found")
        resp = self.post_json("/plugins/info", {"plugin_id": "bad.plugin"})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _mock_initialize)
class TestPluginsApiSettings(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + ".update_plugin_settings", return_value=True)
    def test_update_settings_success(self, _mock_update):
        resp = self.post_json(
            "/plugins/settings/update",
            {
                "plugin_id": "encoder.hevc",
                "settings": [_make_plugin_setting()],
            },
        )
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + ".update_plugin_settings", return_value=False)
    def test_update_settings_failure(self, _mock_update):
        resp = self.post_json(
            "/plugins/settings/update",
            {
                "plugin_id": "encoder.hevc",
                "settings": [_make_plugin_setting()],
            },
        )
        assert resp.code == 500

    @patch(PLUGINS_HELPERS + ".reset_plugin_settings", return_value=True)
    def test_reset_settings_success(self, _mock_reset):
        resp = self.post_json(
            "/plugins/settings/reset",
            {
                "plugin_id": "encoder.hevc",
            },
        )
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + ".reset_plugin_settings", return_value=False)
    def test_reset_settings_failure(self, _mock_reset):
        resp = self.post_json(
            "/plugins/settings/reset",
            {
                "plugin_id": "encoder.hevc",
            },
        )
        assert resp.code == 500
