#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_settings_api_deep.py

    Deep coverage tests for remaining settings API endpoints not covered
    by test_settings_api.py and test_settings_api_extended.py.
    Covers: error paths, write_settings edge cases, get_system_configuration
    errors, read/write library with exceptions.
"""

import json

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType
from tests.unit.api_test_base import ApiTestBase
from compresso.webserver.api_v2.settings_api import ApiSettingsHandler

SETTINGS_API = 'compresso.webserver.api_v2.settings_api'


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}
    self.config = MagicMock()
    self.config.get_config_as_dict.return_value = {
        'debugging': False,
        'ui_port': 8888,
        'cache_path': '/tmp/compresso',
    }
    self.config.get_remote_installations.return_value = []


# ------------------------------------------------------------------
# Settings read error
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiReadError(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    def test_read_settings_exception(self):
        def _mock_init_error(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.config.get_config_as_dict.side_effect = Exception("error")
        with patch.object(ApiSettingsHandler, 'initialize', _mock_init_error):
            resp = self.get_json('/settings/read')
            assert resp.code == 500


# ------------------------------------------------------------------
# Settings write edge cases
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiWriteEdge(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    def test_write_settings_strips_remote_installations(self):
        resp = self.post_json('/settings/write', {
            'settings': {
                'debugging': True,
                'remote_installations': [{'address': '10.0.0.1'}],
            },
        })
        assert resp.code == 200

    def test_write_settings_exception(self):
        def _mock_init_error(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.config.set_bulk_config_items.side_effect = Exception("save error")
        with patch.object(ApiSettingsHandler, 'initialize', _mock_init_error):
            resp = self.post_json('/settings/write', {
                'settings': {'debugging': True},
            })
            assert resp.code == 500

    def test_write_settings_invalid_json(self):
        resp = self.fetch(
            '/compresso/api/v2/settings/write',
            method='POST',
            body='not json',
            headers={'Content-Type': 'application/json'},
        )
        assert resp.code == 400


# ------------------------------------------------------------------
# System configuration error
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiSysConfigError(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch('compresso.libs.system.System')
    def test_system_config_exception(self, mock_sys_cls):
        mock_sys_cls.side_effect = Exception("system info error")
        resp = self.get_json('/settings/configuration')
        assert resp.code == 500


# ------------------------------------------------------------------
# Worker group error paths
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiWorkerGroupErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f'{SETTINGS_API}.WorkerGroup')
    def test_get_worker_groups_exception(self, mock_wg_cls):
        mock_wg_cls.get_all_worker_groups.side_effect = Exception("error")
        resp = self.get_json('/settings/worker_groups')
        assert resp.code == 500

    @patch(f'{SETTINGS_API}.WorkerGroup')
    def test_read_worker_group_exception(self, mock_wg_cls):
        mock_wg_cls.side_effect = Exception("not found")
        resp = self.post_json('/settings/worker_group/read', {'id': 999})
        assert resp.code == 500

    @patch('compresso.webserver.helpers.settings.save_worker_group_config')
    def test_write_worker_group_exception(self, mock_save):
        mock_save.side_effect = Exception("save error")
        resp = self.post_json('/settings/worker_group/write', {
            'id': 1, 'name': 'Default', 'number_of_workers': 3,
            'worker_type': 'cpu', 'locked': False,
            'worker_event_schedules': [], 'tags': [],
        })
        assert resp.code == 500

    @patch(f'{SETTINGS_API}.WorkerGroup')
    def test_remove_worker_group_exception(self, mock_wg_cls):
        mock_wg_cls.side_effect = Exception("error")
        resp = self.fetch(
            '/compresso/api/v2/settings/worker_group/remove',
            method='DELETE',
            body=json.dumps({'id': 1}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


# ------------------------------------------------------------------
# Library error paths
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiLibraryErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f'{SETTINGS_API}.Library')
    def test_get_libraries_exception(self, mock_lib_cls):
        mock_lib_cls.get_all_libraries.side_effect = Exception("error")
        resp = self.get_json('/settings/libraries')
        assert resp.code == 500

    @patch(f'{SETTINGS_API}.Library')
    def test_read_library_config_exception(self, mock_lib_cls):
        mock_lib_cls.side_effect = Exception("not found")
        resp = self.post_json('/settings/library/read', {'id': 999})
        assert resp.code == 500

    @patch(f'{SETTINGS_API}.Library')
    def test_remove_library_exception(self, mock_lib_cls):
        mock_lib_cls.side_effect = Exception("error")
        resp = self.fetch(
            '/compresso/api/v2/settings/library/remove',
            method='DELETE',
            body=json.dumps({'id': 1}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500


# ------------------------------------------------------------------
# Link error paths
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiLinkErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f'{SETTINGS_API}.Links')
    def test_read_link_config_exception(self, mock_links_cls):
        mock_links_cls.return_value.read_remote_installation_link_config.side_effect = Exception("error")
        resp = self.post_json('/settings/link/read', {'uuid': 'abc-123'})
        assert resp.code == 500

    @patch(f'{SETTINGS_API}.Links')
    def test_write_link_config_exception(self, mock_links_cls):
        mock_links_cls.return_value.update_single_remote_installation_link_config.side_effect = Exception("error")
        resp = self.post_json('/settings/link/write', {
            'link_config': {
                'address': '10.0.0.2:8888',
                'auth': 'None', 'username': '', 'password': '',
                'available': True, 'name': 'Remote', 'version': '1.0.0',
                'last_updated': 1636166593.0,
                'enable_receiving_tasks': False, 'enable_sending_tasks': False,
                'enable_task_preloading': False, 'preloading_count': 0,
                'enable_checksum_validation': False,
                'enable_config_missing_libraries': False,
                'enable_distributed_worker_count': False,
            },
            'distributed_worker_count_target': 0,
        })
        assert resp.code == 500


# ------------------------------------------------------------------
# Library export error
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiExportError(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f'{SETTINGS_API}.Library')
    def test_export_library_exception(self, mock_lib_cls):
        mock_lib_cls.export.side_effect = Exception("export error")
        resp = self.post_json('/settings/library/export', {'id': 1})
        assert resp.code == 500


# ------------------------------------------------------------------
# Library import error
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiImportError(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch('compresso.webserver.helpers.settings.save_library_config')
    def test_import_library_exception(self, mock_save):
        mock_save.side_effect = Exception("import error")
        resp = self.post_json('/settings/library/import', {
            'library_id': 1,
            'library_config': {'name': 'Movies', 'path': '/movies'},
            'plugins': {'enabled_plugins': [], 'plugin_flow': {}},
        })
        assert resp.code == 500


# ------------------------------------------------------------------
# Method not allowed
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiSettingsHandler, 'initialize', _mock_initialize)
class TestSettingsApiMethodNotAllowed(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    def test_get_on_write_endpoint(self):
        """GET on a POST-only endpoint returns 405."""
        resp = self.get_json('/settings/write')
        assert resp.code == 405
