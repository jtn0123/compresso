#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_plugins_handler.py

    Unit tests for compresso.libs.plugins.PluginsHandler.
"""

import hashlib
import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture
def mock_deps():
    """Mock all external dependencies for PluginsHandler."""
    with patch('compresso.libs.plugins.config') as mock_config, \
         patch('compresso.libs.plugins.CompressoLogging') as mock_logging, \
         patch('compresso.libs.plugins.common') as mock_common, \
         patch('compresso.libs.plugins.Session') as mock_session, \
         patch('compresso.libs.plugins.FrontendPushMessages'), \
         patch('compresso.libs.plugins.Library'), \
         patch('compresso.libs.plugins.PluginRepos') as mock_repos, \
         patch('compresso.libs.plugins.Plugins') as mock_plugins, \
         patch('compresso.libs.plugins.EnabledPlugins') as mock_ep, \
         patch('compresso.libs.plugins.LibraryPluginFlow') as mock_lpf, \
         patch('compresso.libs.plugins.PluginExecutor') as mock_pe:
        mock_config_inst = MagicMock()
        mock_config_inst.get_plugins_path.return_value = '/fake/plugins'
        mock_config_inst.get_userdata_path.return_value = '/fake/userdata'
        mock_config.Config.return_value = mock_config_inst
        mock_logging.get_logger.return_value = MagicMock()
        yield {
            'config': mock_config,
            'config_inst': mock_config_inst,
            'logging': mock_logging,
            'common': mock_common,
            'session': mock_session,
            'repos_model': mock_repos,
            'plugins_model': mock_plugins,
            'enabled_plugins': mock_ep,
            'library_plugin_flow': mock_lpf,
            'plugin_executor': mock_pe,
        }


@pytest.fixture
def handler(mock_deps):
    from compresso.libs.plugins import PluginsHandler
    return PluginsHandler()


@pytest.mark.unittest
class TestPluginsHandlerInit:

    def test_init_sets_settings(self, handler, mock_deps):
        assert handler.settings is not None

    def test_init_sets_logger(self, handler):
        assert handler.logger is not None

    def test_version_is_set(self, handler):
        assert isinstance(handler.version, int)
        assert handler.version >= 1


@pytest.mark.unittest
class TestGetPluginRepoId:

    def test_returns_md5_hash(self):
        from compresso.libs.plugins import PluginsHandler
        result = PluginsHandler.get_plugin_repo_id("https://example.com/repo")
        expected = int(hashlib.md5("https://example.com/repo".encode('utf8')).hexdigest(), 16)
        assert result == expected

    def test_different_paths_produce_different_ids(self):
        from compresso.libs.plugins import PluginsHandler
        id1 = PluginsHandler.get_plugin_repo_id("repo_a")
        id2 = PluginsHandler.get_plugin_repo_id("repo_b")
        assert id1 != id2

    def test_same_path_produces_same_id(self):
        from compresso.libs.plugins import PluginsHandler
        id1 = PluginsHandler.get_plugin_repo_id("same_path")
        id2 = PluginsHandler.get_plugin_repo_id("same_path")
        assert id1 == id2


@pytest.mark.unittest
class TestGetRepoCacheFile:

    def test_returns_path_with_repo_id(self, handler):
        with patch('compresso.libs.plugins.os.path.exists', return_value=True):
            result = handler.get_repo_cache_file(12345)
            assert 'repo-12345.json' in result

    def test_creates_directory_if_missing(self, handler):
        with patch('compresso.libs.plugins.os.path.exists', return_value=False), \
             patch('compresso.libs.plugins.os.makedirs') as mock_mkdirs:
            handler.get_repo_cache_file(12345)
            mock_mkdirs.assert_called_once()


@pytest.mark.unittest
class TestGetPluginPath:

    def test_returns_path_with_plugin_id(self, handler):
        with patch('compresso.libs.plugins.os.path.exists', return_value=True):
            result = handler.get_plugin_path('my_plugin')
            assert 'my_plugin' in result

    def test_creates_directory_if_missing(self, handler):
        with patch('compresso.libs.plugins.os.path.exists', return_value=False), \
             patch('compresso.libs.plugins.os.makedirs') as mock_mkdirs:
            handler.get_plugin_path('my_plugin')
            mock_mkdirs.assert_called_once()


@pytest.mark.unittest
class TestGetPluginDownloadCachePath:

    def test_returns_zip_path(self, handler):
        result = handler.get_plugin_download_cache_path('my_plugin', '1.0.0')
        assert result.endswith('my_plugin-1.0.0.zip')


@pytest.mark.unittest
class TestGetDefaultRepo:

    def test_returns_default(self):
        from compresso.libs.plugins import PluginsHandler
        assert PluginsHandler.get_default_repo() == "default"


@pytest.mark.unittest
class TestGetPluginRepos:

    def test_returns_list_with_default(self, handler, mock_deps):
        mock_query = MagicMock()
        mock_query.order_by.return_value = []
        mock_deps['repos_model'].select.return_value = mock_query
        result = handler.get_plugin_repos()
        assert isinstance(result, list)
        assert result[0]['path'] == 'default'

    def test_includes_db_repos(self, handler, mock_deps):
        mock_repo = MagicMock()
        mock_repo.model_to_dict.return_value = {'path': 'https://custom.repo'}

        mock_query = MagicMock()
        mock_query.order_by.return_value = [mock_repo]
        mock_deps['repos_model'].select.return_value = mock_query

        result = handler.get_plugin_repos()
        paths = [r['path'] for r in result]
        assert 'default' in paths
        assert any(p == 'https://custom.repo' for p in paths)


@pytest.mark.unittest
class TestSetPluginRepos:

    def test_validates_and_saves(self, handler, mock_deps):
        with patch.object(handler, 'fetch_remote_repo_data', return_value={'some': 'data'}):
            mock_deps['repos_model'].delete.return_value.execute = MagicMock()
            mock_deps['repos_model'].insert_many.return_value.execute = MagicMock()
            result = handler.set_plugin_repos(['https://repo1.com'])
            assert result is True

    def test_returns_false_on_invalid_repo(self, handler):
        with patch.object(handler, 'fetch_remote_repo_data', return_value=None):
            result = handler.set_plugin_repos(['https://bad-repo.com'])
            assert result is False


@pytest.mark.unittest
class TestFetchRemoteRepoData:

    def test_fetches_data(self, handler, mock_deps):
        mock_session_inst = MagicMock()
        mock_session_inst.get_installation_uuid.return_value = 'test-uuid'
        mock_session_inst.get_supporter_level.return_value = 0
        mock_session_inst.api_get.return_value = ({'plugins': []}, 200)
        mock_deps['session'].return_value = mock_session_inst

        result = handler.fetch_remote_repo_data('default')
        assert result == {'plugins': []}

    def test_retries_on_401(self, handler, mock_deps):
        mock_session_inst = MagicMock()
        mock_session_inst.get_installation_uuid.return_value = 'test-uuid'
        mock_session_inst.get_supporter_level.return_value = 0
        mock_session_inst.api_get.side_effect = [
            ({'error': 'auth'}, 401),
            ({'plugins': []}, 200),
        ]
        mock_deps['session'].return_value = mock_session_inst

        handler.fetch_remote_repo_data('default')
        mock_session_inst.register_compresso.assert_called_once()


@pytest.mark.unittest
class TestUpdatePluginRepos:

    def test_updates_repos(self, handler, mock_deps):
        with patch.object(handler, 'get_plugin_repos', return_value=[{'path': 'default'}]), \
             patch.object(handler, 'fetch_remote_repo_data', return_value={'repo': {}}), \
             patch.object(handler, 'get_repo_cache_file', return_value='/fake/repo-cache.json'), \
             patch('compresso.libs.plugins.os.path.exists', return_value=True), \
             patch('builtins.open', MagicMock()):
            result = handler.update_plugin_repos()
            assert result is True
