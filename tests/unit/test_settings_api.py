#!/usr/bin/env python3

"""
tests.unit.test_settings_api.py

Tests for the settings API handler endpoints.

"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.webserver.api_v2.settings_api import ApiSettingsHandler
from tests.unit.api_test_base import ApiTestBase


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


SETTINGS_API = "compresso.webserver.api_v2.settings_api"


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_initialize)
class TestSettingsApiRead(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    def test_read_settings(self):
        """GET /settings/read returns 200 with settings key."""
        resp = self.get_json("/settings/read")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "settings" in data
        assert data["settings"]["debugging"] is False

    @patch(SETTINGS_API + ".config.Config")
    def test_write_settings(self, _mock_config_cls):
        """POST /settings/write with valid settings returns 200."""
        resp = self.post_json(
            "/settings/write",
            {
                "settings": {"debugging": True, "ui_port": 9999},
            },
        )
        assert resp.code == 200

    @patch("compresso.libs.system.System")
    def test_read_configuration(self, mock_system_cls):
        """GET /settings/configuration returns 200 with configuration key."""
        mock_system = MagicMock()
        mock_system.info.return_value = {
            "python_version": "3.11.0",
            "platform": "Linux",
        }
        mock_system_cls.return_value = mock_system
        resp = self.get_json("/settings/configuration")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "configuration" in data

    @patch(SETTINGS_API + ".Library")
    def test_read_libraries(self, mock_library_cls):
        """GET /settings/libraries returns 200 with libraries key."""
        mock_library_cls.get_all_libraries.return_value = [
            {
                "id": 1,
                "name": "Movies",
                "path": "/movies",
                "locked": False,
                "enable_remote_only": False,
                "enable_scanner": True,
                "enable_inotify": False,
                "tags": [],
            },
        ]
        resp = self.get_json("/settings/libraries")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "libraries" in data
        assert len(data["libraries"]) == 1

    @patch(SETTINGS_API + ".Links")
    def test_link_read(self, mock_links_cls):
        """POST /settings/link/read returns 200 with link config."""
        mock_links = MagicMock()
        mock_links.read_remote_installation_link_config.return_value = {
            "address": "10.0.0.2:8888",
            "auth": "None",
            "username": "",
            "password": "",
            "available": True,
            "name": "Remote",
            "version": "1.0.0",
            "last_updated": 1636166593.0,
            "enable_receiving_tasks": False,
            "enable_sending_tasks": False,
            "enable_task_preloading": False,
            "preloading_count": 0,
            "enable_checksum_validation": False,
            "enable_config_missing_libraries": False,
            "enable_distributed_worker_count": False,
            "distributed_worker_count_target": 0,
        }
        mock_links_cls.return_value = mock_links
        resp = self.post_json(
            "/settings/link/read",
            {
                "uuid": "7cd35429-76ab-4a29-8649-8c91236b5f8b",
            },
        )
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "link_config" in data

    @patch(SETTINGS_API + ".Links")
    def test_link_write(self, mock_links_cls):
        """POST /settings/link/write returns 200 on success."""
        mock_links = MagicMock()
        mock_links_cls.return_value = mock_links
        resp = self.post_json(
            "/settings/link/write",
            {
                "link_config": {
                    "address": "10.0.0.2:8888",
                    "auth": "None",
                    "username": "",
                    "password": "",
                    "available": True,
                    "name": "Remote",
                    "version": "1.0.0",
                    "last_updated": 1636166593.0,
                    "enable_receiving_tasks": False,
                    "enable_sending_tasks": False,
                    "enable_task_preloading": False,
                    "preloading_count": 0,
                    "enable_checksum_validation": False,
                    "enable_config_missing_libraries": False,
                    "enable_distributed_worker_count": False,
                },
                "distributed_worker_count_target": 0,
            },
        )
        assert resp.code == 200
