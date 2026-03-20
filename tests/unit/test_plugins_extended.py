#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_plugins_extended.py

    Extended unit tests for compresso.libs.plugins.PluginsHandler.
    Covers plugin installation/removal, updates, repo management,
    listing/filtering, and version checking.
"""

import json
import os
import zipfile

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_handler(tmp_path):
    """Create a PluginsHandler with mocked settings pointing at tmp_path."""
    with patch('compresso.libs.plugins.config') as mock_config_mod:
        mock_settings = MagicMock()
        mock_settings.get_plugins_path.return_value = str(tmp_path / 'plugins')
        mock_config_mod.Config.return_value = mock_settings
        with patch('compresso.libs.plugins.CompressoLogging'):
            from compresso.libs.plugins import PluginsHandler
            handler = PluginsHandler()
    return handler


@pytest.mark.unittest
class TestPluginRepoId:

    def test_get_plugin_repo_id_returns_int(self):
        from compresso.libs.plugins import PluginsHandler
        result = PluginsHandler.get_plugin_repo_id("https://example.com/repo")
        assert isinstance(result, int)

    def test_get_plugin_repo_id_deterministic(self):
        from compresso.libs.plugins import PluginsHandler
        r1 = PluginsHandler.get_plugin_repo_id("test-repo")
        r2 = PluginsHandler.get_plugin_repo_id("test-repo")
        assert r1 == r2

    def test_get_plugin_repo_id_differs_for_different_paths(self):
        from compresso.libs.plugins import PluginsHandler
        r1 = PluginsHandler.get_plugin_repo_id("repo-a")
        r2 = PluginsHandler.get_plugin_repo_id("repo-b")
        assert r1 != r2


@pytest.mark.unittest
class TestPluginPaths:

    def test_get_repo_cache_file_creates_dir(self, tmp_path):
        handler = _make_handler(tmp_path)
        cache_file = handler.get_repo_cache_file(12345)
        plugins_dir = str(tmp_path / 'plugins')
        assert os.path.isdir(plugins_dir)
        assert cache_file.endswith("repo-12345.json")

    def test_get_plugin_path_creates_dir(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugin_path = handler.get_plugin_path("my_plugin")
        assert os.path.isdir(plugin_path)
        assert plugin_path.endswith("my_plugin")

    def test_get_plugin_download_cache_path(self, tmp_path):
        handler = _make_handler(tmp_path)
        path = handler.get_plugin_download_cache_path("my_plugin", "1.0.0")
        assert path.endswith("my_plugin-1.0.0.zip")


@pytest.mark.unittest
class TestGetDefaultRepo:

    def test_default_repo_value(self):
        from compresso.libs.plugins import PluginsHandler
        assert PluginsHandler.get_default_repo() == "default"


@pytest.mark.unittest
class TestReadRepoData:

    def test_read_repo_data_returns_data_when_file_exists(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / 'plugins'
        plugins_dir.mkdir(parents=True, exist_ok=True)
        repo_data = {"repo": {"name": "test"}, "plugins": []}
        cache_file = plugins_dir / "repo-99.json"
        cache_file.write_text(json.dumps(repo_data))
        with patch.object(handler, 'get_repo_cache_file', return_value=str(cache_file)):
            result = handler.read_repo_data(99)
        assert result == repo_data

    def test_read_repo_data_returns_empty_when_missing(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch.object(handler, 'get_repo_cache_file', return_value=str(tmp_path / "nonexistent.json")):
            result = handler.read_repo_data(99)
        assert result == {}


@pytest.mark.unittest
class TestGetPluginInfo:

    def test_get_plugin_info_returns_data(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / 'plugins'
        plugin_dir = plugins_dir / 'test_plugin'
        plugin_dir.mkdir(parents=True)
        info = {"id": "test_plugin", "version": "1.0", "compatibility": [2]}
        (plugin_dir / 'info.json').write_text(json.dumps(info))
        result = handler.get_plugin_info("test_plugin")
        assert result['id'] == "test_plugin"
        assert result['version'] == "1.0"

    def test_get_plugin_info_returns_empty_when_no_file(self, tmp_path):
        handler = _make_handler(tmp_path)
        result = handler.get_plugin_info("nonexistent_plugin")
        assert result == {}


@pytest.mark.unittest
class TestGetPluginsInRepoData:

    def test_returns_empty_for_empty_repo_data(self, tmp_path):
        handler = _make_handler(tmp_path)
        result = handler.get_plugins_in_repo_data({})
        assert result == []

    def test_filters_incompatible_plugins(self, tmp_path):
        handler = _make_handler(tmp_path)
        repo_data = {
            "repo": {"name": "test-repo", "repo_data_directory": "https://example.com/data"},
            "plugins": [
                {"id": "p1", "name": "Plugin1", "version": "1.0", "compatibility": [1]},
                {"id": "p2", "name": "Plugin2", "version": "2.0", "compatibility": [2]},
            ]
        }
        with patch.object(handler, 'get_plugin_info', return_value={}):
            result = handler.get_plugins_in_repo_data(repo_data)
        ids = [p['plugin_id'] for p in result]
        assert "p1" not in ids
        assert "p2" in ids

    def test_marks_installed_plugin_as_installed(self, tmp_path):
        handler = _make_handler(tmp_path)
        repo_data = {
            "repo": {"name": "test-repo", "repo_data_directory": None},
            "plugins": [
                {"id": "installed_plugin", "name": "Installed", "version": "1.0", "compatibility": [2]},
            ]
        }
        with patch.object(handler, 'get_plugin_info', return_value={"version": "1.0"}):
            result = handler.get_plugins_in_repo_data(repo_data)
        assert result[0]['status']['installed'] is True
        assert result[0]['status']['update_available'] is False

    def test_marks_update_available(self, tmp_path):
        handler = _make_handler(tmp_path)
        repo_data = {
            "repo": {"name": "test-repo", "repo_data_directory": "https://example.com"},
            "plugins": [
                {"id": "old_plugin", "name": "Old", "version": "2.0", "compatibility": [2]},
            ]
        }
        with patch.object(handler, 'get_plugin_info', return_value={"version": "1.0"}):
            with patch.object(handler, 'flag_plugin_for_update_by_id'):
                result = handler.get_plugins_in_repo_data(repo_data)
        assert result[0]['status']['installed'] is True
        assert result[0]['status']['update_available'] is True


@pytest.mark.unittest
class TestGetInstallablePluginsList:

    def test_returns_list_from_repos(self, tmp_path):
        handler = _make_handler(tmp_path)
        fake_plugins = [{"plugin_id": "p1", "name": "P1"}]
        with patch.object(handler, 'get_plugin_repos', return_value=[{"path": "default"}]):
            with patch.object(handler, 'get_plugin_repo_id', return_value=1):
                with patch.object(handler, 'read_repo_data', return_value={}):
                    with patch.object(handler, 'get_plugins_in_repo_data', return_value=fake_plugins):
                        result = handler.get_installable_plugins_list()
        assert len(result) == 1
        assert result[0]['plugin_id'] == "p1"
        assert result[0]['repo_id'] == '1'

    def test_filters_by_repo_id(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch.object(handler, 'get_plugin_repos', return_value=[{"path": "default"}]):
            with patch.object(handler, 'get_plugin_repo_id', return_value=1):
                result = handler.get_installable_plugins_list(filter_repo_id=999)
        assert result == []


@pytest.mark.unittest
class TestReadRemoteChangelog:

    def test_returns_text_on_200(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "# Changelog\n- v1.0"
        with patch('compresso.libs.plugins.requests.get', return_value=mock_resp):
            result = handler.read_remote_changelog_file("https://example.com/changelog.md")
        assert "Changelog" in result

    def test_returns_empty_on_404(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch('compresso.libs.plugins.requests.get', return_value=mock_resp):
            result = handler.read_remote_changelog_file("https://example.com/missing.md")
        assert result == ''


@pytest.mark.unittest
class TestFetchRemoteRepoData:

    def test_fetch_remote_repo_data_success(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_session = MagicMock()
        mock_session.get_installation_uuid.return_value = 'test-uuid'
        mock_session.get_supporter_level.return_value = 0
        mock_session.api_get.return_value = ({"repo": {}, "plugins": []}, 200)
        with patch('compresso.libs.plugins.Session', return_value=mock_session):
            result = handler.fetch_remote_repo_data("default")
        assert result == {"repo": {}, "plugins": []}

    def test_fetch_remote_repo_data_retries_on_401(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_session = MagicMock()
        mock_session.get_installation_uuid.return_value = 'test-uuid'
        mock_session.get_supporter_level.return_value = 0
        mock_session.api_get.side_effect = [
            (None, 401),
            ({"repo": {}, "plugins": []}, 200),
        ]
        with patch('compresso.libs.plugins.Session', return_value=mock_session):
            result = handler.fetch_remote_repo_data("default")
        mock_session.register_compresso.assert_called_once()
        assert result == {"repo": {}, "plugins": []}


@pytest.mark.unittest
class TestUpdatePluginRepos:

    def test_update_plugin_repos_writes_cache(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / 'plugins'
        plugins_dir.mkdir(parents=True, exist_ok=True)
        repo_data = {"repo": {"name": "test"}, "plugins": []}
        with patch.object(handler, 'get_plugin_repos', return_value=[{"path": "default"}]):
            with patch.object(handler, 'fetch_remote_repo_data', return_value=repo_data):
                result = handler.update_plugin_repos()
        assert result is True


@pytest.mark.unittest
class TestInstallPluginById:

    def test_install_plugin_by_id_not_found_returns_false(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch.object(handler, 'get_installable_plugins_list', return_value=[]):
            result = handler.install_plugin_by_id("nonexistent")
        assert result is False

    def test_install_plugin_by_id_download_failure(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugin = {"plugin_id": "test_plugin", "name": "Test", "version": "1.0"}
        with patch.object(handler, 'get_installable_plugins_list', return_value=[plugin]):
            with patch.object(handler, 'download_and_install_plugin', return_value=False):
                result = handler.install_plugin_by_id("test_plugin")
        assert result is False

    def test_install_plugin_by_id_success(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugin = {"plugin_id": "test_plugin", "name": "Test", "version": "1.0"}
        with patch.object(handler, 'get_installable_plugins_list', return_value=[plugin]):
            with patch.object(handler, 'download_and_install_plugin', return_value=True):
                with patch.object(handler, 'write_plugin_data_to_db', return_value=True):
                    with patch.object(handler, 'get_plugin_path', return_value=str(tmp_path / 'plugins' / 'test_plugin')):
                        with patch('compresso.libs.plugins.PluginExecutor') as mock_pe:
                            result = handler.install_plugin_by_id("test_plugin")
        assert result is True


@pytest.mark.unittest
class TestDownloadAndInstallPlugin:

    def test_download_and_install_success(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugin = {"plugin_id": "p1", "name": "P1", "version": "1.0", "package_url": "http://x.com/p.zip"}
        with patch.object(handler, 'download_plugin', return_value=str(tmp_path / 'downloaded.zip')):
            with patch.object(handler, 'install_plugin', return_value={"id": "p1"}):
                with patch('os.path.isfile', return_value=True):
                    with patch('os.remove'):
                        with patch.object(handler, 'notify_site_of_plugin_install'):
                            result = handler.download_and_install_plugin(plugin)
        assert result is True

    def test_download_and_install_exception_returns_false(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugin = {"plugin_id": "p1", "name": "P1", "version": "1.0", "package_url": "http://x.com/p.zip"}
        with patch.object(handler, 'download_plugin', side_effect=Exception("network error")):
            result = handler.download_and_install_plugin(plugin)
        assert result is False


@pytest.mark.unittest
class TestInstallPluginFromPath:

    def test_rejects_non_zip(self, tmp_path):
        handler = _make_handler(tmp_path)
        non_zip = tmp_path / "notazip.txt"
        non_zip.write_text("not a zip")
        result = handler.install_plugin_from_path_on_disk(str(non_zip))
        assert result is False

    def test_installs_valid_zip(self, tmp_path):
        handler = _make_handler(tmp_path)
        # Create a valid zip with info.json
        zip_path = tmp_path / "plugin.zip"
        info = {"id": "zip_plugin", "name": "Zip Plugin", "version": "1.0", "compatibility": [2]}
        with zipfile.ZipFile(str(zip_path), 'w') as zf:
            zf.writestr("info.json", json.dumps(info))

        with patch.object(handler, 'install_plugin', return_value=info):
            with patch.object(handler, 'write_plugin_data_to_db', return_value=True):
                with patch.object(handler, 'get_plugin_path', return_value=str(tmp_path / 'plugins' / 'zip_plugin')):
                    with patch('compresso.libs.plugins.PluginExecutor') as mock_pe:
                        result = handler.install_plugin_from_path_on_disk(str(zip_path))
        assert result is True


@pytest.mark.unittest
class TestNotifySiteOfPluginInstall:

    def test_notify_success(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_session = MagicMock()
        mock_session.get_installation_uuid.return_value = 'uuid'
        mock_session.get_supporter_level.return_value = 0
        mock_session.api_post.return_value = ({"success": True}, 200)
        with patch('compresso.libs.plugins.Session', return_value=mock_session):
            handler.notify_site_of_plugin_install({"plugin_id": "p1", "author": "a", "version": "1"})
        mock_session.api_post.assert_called_once()

    def test_notify_failure_triggers_register(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_session = MagicMock()
        mock_session.get_installation_uuid.return_value = 'uuid'
        mock_session.get_supporter_level.return_value = 0
        mock_session.api_post.return_value = ({"success": False}, 200)
        with patch('compresso.libs.plugins.Session', return_value=mock_session):
            handler.notify_site_of_plugin_install({"plugin_id": "p1", "author": "a", "version": "1"})
        mock_session.register_compresso.assert_called_once()

    def test_notify_exception_returns_false(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_session = MagicMock()
        mock_session.get_installation_uuid.return_value = 'uuid'
        mock_session.get_supporter_level.return_value = 0
        mock_session.api_post.side_effect = Exception("network")
        with patch('compresso.libs.plugins.Session', return_value=mock_session):
            result = handler.notify_site_of_plugin_install({"plugin_id": "p1", "author": "a", "version": "1"})
        assert result is False


@pytest.mark.unittest
class TestSetPluginRepos:

    def test_set_plugin_repos_returns_false_on_invalid_repo(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch.object(handler, 'fetch_remote_repo_data', return_value=None):
            result = handler.set_plugin_repos(["https://bad-url.com"])
        assert result is False

    def test_set_plugin_repos_success(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch.object(handler, 'fetch_remote_repo_data', return_value={"repo": {}}):
            with patch('compresso.libs.plugins.PluginRepos') as mock_pr:
                mock_pr.delete.return_value.execute.return_value = None
                mock_pr.insert_many.return_value.execute.return_value = None
                result = handler.set_plugin_repos(["https://good.com"])
        assert result is True


@pytest.mark.unittest
class TestGetPluginRepos:

    def test_includes_default_repo(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch('compresso.libs.plugins.PluginRepos') as mock_pr:
            mock_repo = MagicMock()
            mock_repo.model_to_dict.return_value = {"path": "custom-repo"}
            mock_pr.select.return_value.order_by.return_value = [mock_repo]
            result = handler.get_plugin_repos()
        assert result[0]['path'] == 'default'
        assert len(result) == 2

    def test_skips_duplicate_default(self, tmp_path):
        handler = _make_handler(tmp_path)
        with patch('compresso.libs.plugins.PluginRepos') as mock_pr:
            mock_repo = MagicMock()
            mock_repo.model_to_dict.return_value = {"path": "default"}
            mock_pr.select.return_value.order_by.return_value = [mock_repo]
            result = handler.get_plugin_repos()
        assert len(result) == 1


@pytest.mark.unittest
class TestInstallPluginRequirements:

    def test_skips_if_no_requirements_file(self, tmp_path):
        from compresso.libs.plugins import PluginsHandler
        with patch('subprocess.call') as mock_call:
            PluginsHandler.install_plugin_requirements(str(tmp_path))
        mock_call.assert_not_called()

    def test_installs_when_requirements_exist(self, tmp_path):
        from compresso.libs.plugins import PluginsHandler
        req_file = tmp_path / 'requirements.txt'
        req_file.write_text("requests>=2.0")
        with patch('subprocess.call') as mock_call:
            PluginsHandler.install_plugin_requirements(str(tmp_path))
        mock_call.assert_called_once()


@pytest.mark.unittest
class TestInstallNpmModules:

    def test_skips_if_no_package_json(self, tmp_path):
        from compresso.libs.plugins import PluginsHandler
        with patch('subprocess.call') as mock_call:
            PluginsHandler.install_npm_modules(str(tmp_path))
        mock_call.assert_not_called()

    def test_runs_npm_when_package_json_exists(self, tmp_path):
        from compresso.libs.plugins import PluginsHandler
        pkg = tmp_path / 'package.json'
        pkg.write_text('{"name": "test"}')
        with patch('subprocess.call') as mock_call:
            PluginsHandler.install_npm_modules(str(tmp_path))
        assert mock_call.call_count == 2


@pytest.mark.unittest
class TestPluginVersion:

    def test_plugin_handler_version_is_2(self):
        from compresso.libs.plugins import PluginsHandler
        assert PluginsHandler.version == 2
