#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_plugins_api_deep.py

    Deep coverage tests for plugins API routes not covered by test_plugins_api_handler.py.
    Covers: installable list, install by ID, plugin flow management, repo operations, panels.
"""

import json

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType
from tests.unit.api_test_base import ApiTestBase
from compresso.webserver.api_v2.plugins_api import ApiPluginsHandler

PLUGINS_HELPERS = 'compresso.webserver.helpers.plugins'


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


def _make_plugin_item(**overrides):
    """Create a plugin metadata dict matching PluginsMetadataInstallableResultsSchema."""
    item = {
        'plugin_id': 'encoder.hevc',
        'name': 'HEVC Encoder',
        'author': 'TestAuthor',
        'description': 'Encode to HEVC',
        'version': '1.0',
        'icon': '',
        'tags': 'video,encoder',
        'status': {'installed': True, 'update_available': False},
    }
    item.update(overrides)
    return item


def _make_flow_item(**overrides):
    """Create a plugin flow data dict matching PluginFlowDataResultsSchema."""
    item = {
        'plugin_id': 'encoder.hevc',
        'name': 'HEVC Encoder',
        'author': 'TestAuthor',
        'description': 'Encode to HEVC',
        'version': '1.0',
        'icon': '',
    }
    item.update(overrides)
    return item


# ------------------------------------------------------------------
# Installable plugins
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPluginsHandler, 'initialize', _mock_initialize)
class TestPluginsApiInstallable(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + '.prepare_installable_plugins_list')
    def test_get_installable_success(self, mock_list):
        mock_list.return_value = [_make_plugin_item()]
        resp = self.get_json('/plugins/installable')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'plugins' in data

    @patch(PLUGINS_HELPERS + '.prepare_installable_plugins_list')
    def test_get_installable_internal_error(self, mock_list):
        mock_list.side_effect = Exception("DB error")
        resp = self.get_json('/plugins/installable')
        assert resp.code == 500


# ------------------------------------------------------------------
# Install plugin by ID
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPluginsHandler, 'initialize', _mock_initialize)
class TestPluginsApiInstallById(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + '.install_plugin_by_id', return_value=True)
    def test_install_plugin_success(self, _mock_install):
        resp = self.post_json('/plugins/install', {'plugin_id': 'encoder.hevc', 'repo_id': 'official'})
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + '.install_plugin_by_id', return_value=False)
    def test_install_plugin_failure(self, _mock_install):
        resp = self.post_json('/plugins/install', {'plugin_id': 'encoder.hevc', 'repo_id': 'official'})
        assert resp.code == 500

    @patch(PLUGINS_HELPERS + '.install_plugin_by_id')
    def test_install_plugin_exception(self, mock_install):
        mock_install.side_effect = Exception("Network error")
        resp = self.post_json('/plugins/install', {'plugin_id': 'bad', 'repo_id': 'official'})
        assert resp.code == 500


# ------------------------------------------------------------------
# Plugin flow types
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPluginsHandler, 'initialize', _mock_initialize)
class TestPluginsApiFlowTypes(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + '.get_plugin_types_with_flows')
    def test_get_flow_types_success(self, mock_types):
        mock_types.return_value = [
            'library_management.file_test',
            'worker.process',
        ]
        resp = self.get_json('/plugins/flow/types')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'results' in data

    @patch(PLUGINS_HELPERS + '.get_plugin_types_with_flows')
    def test_get_flow_types_error(self, mock_types):
        mock_types.side_effect = Exception("error")
        resp = self.get_json('/plugins/flow/types')
        assert resp.code == 500


# ------------------------------------------------------------------
# Plugin flow by type
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPluginsHandler, 'initialize', _mock_initialize)
class TestPluginsApiFlowByType(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + '.get_enabled_plugin_flows_for_plugin_type')
    def test_get_flow_success(self, mock_flow):
        mock_flow.return_value = [_make_flow_item(plugin_id='p1', name='Plugin 1')]
        resp = self.post_json('/plugins/flow', {
            'plugin_type': 'library_management.file_test',
            'library_id': 1,
        })
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'results' in data

    @patch(PLUGINS_HELPERS + '.get_enabled_plugin_flows_for_plugin_type')
    def test_get_flow_error(self, mock_flow):
        mock_flow.side_effect = Exception("flow error")
        resp = self.post_json('/plugins/flow', {
            'plugin_type': 'library_management.file_test',
            'library_id': 1,
        })
        assert resp.code == 500


# ------------------------------------------------------------------
# Save plugin flow
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPluginsHandler, 'initialize', _mock_initialize)
class TestPluginsApiFlowSave(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + '.save_enabled_plugin_flows_for_plugin_type', return_value=True)
    def test_save_flow_success(self, _mock_save):
        resp = self.post_json('/plugins/flow/save', {
            'plugin_type': 'library_management.file_test',
            'library_id': 1,
            'plugin_flow': [_make_flow_item(plugin_id='p1')],
        })
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + '.save_enabled_plugin_flows_for_plugin_type', return_value=False)
    def test_save_flow_failure(self, _mock_save):
        resp = self.post_json('/plugins/flow/save', {
            'plugin_type': 'library_management.file_test',
            'library_id': 1,
            'plugin_flow': [_make_flow_item(plugin_id='p1')],
        })
        assert resp.code == 500


# ------------------------------------------------------------------
# Repo operations
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPluginsHandler, 'initialize', _mock_initialize)
class TestPluginsApiRepos(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + '.prepare_plugin_repos_list')
    def test_get_repo_list_success(self, mock_repos):
        mock_repos.return_value = [{
            'id': 'official', 'name': 'Official', 'icon': '',
            'path': 'https://example.com/repo.json',
        }]
        resp = self.get_json('/plugins/repos/list')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'repos' in data

    @patch(PLUGINS_HELPERS + '.prepare_plugin_repos_list')
    def test_get_repo_list_error(self, mock_repos):
        mock_repos.side_effect = Exception("error")
        resp = self.get_json('/plugins/repos/list')
        assert resp.code == 500

    @patch(PLUGINS_HELPERS + '.save_plugin_repos_list', return_value=True)
    def test_update_repo_list_success(self, _mock_save):
        resp = self.post_json('/plugins/repos/update', {
            'repos_list': ['https://example.com/repo.json'],
        })
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + '.save_plugin_repos_list', return_value=False)
    def test_update_repo_list_failure(self, _mock_save):
        resp = self.post_json('/plugins/repos/update', {
            'repos_list': ['https://example.com/repo.json'],
        })
        assert resp.code == 500

    @patch(PLUGINS_HELPERS + '.reload_plugin_repos_data', return_value=True)
    def test_reload_repo_data_success(self, _mock_reload):
        resp = self.post_json('/plugins/repos/reload', {})
        assert resp.code == 200

    @patch(PLUGINS_HELPERS + '.reload_plugin_repos_data', return_value=False)
    def test_reload_repo_data_failure(self, _mock_reload):
        resp = self.post_json('/plugins/repos/reload', {})
        assert resp.code == 500


# ------------------------------------------------------------------
# Panel plugins
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPluginsHandler, 'initialize', _mock_initialize)
class TestPluginsApiPanels(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + '.get_enabled_plugin_data_panels')
    def test_get_panel_plugins_success(self, mock_panels):
        mock_panels.return_value = [
            _make_flow_item(plugin_id='panel.test', name='Test Panel'),
        ]
        resp = self.get_json('/plugins/panels/enabled')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'results' in data

    @patch(PLUGINS_HELPERS + '.get_enabled_plugin_data_panels')
    def test_get_panel_plugins_error(self, mock_panels):
        mock_panels.side_effect = Exception("error")
        resp = self.get_json('/plugins/panels/enabled')
        assert resp.code == 500
