#!/usr/bin/env python3

"""
    tests.unit.test_v1_apis.py

    Unit tests for v1 API handlers:
    - BaseApiHandler routing
    - ApiFilebrowserHandler
    - ApiHistoryHandler
    - ApiPendingHandler
    - ApiPluginsHandler
    - ApiSessionHandler
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_request(uri="/api/v1/test", method="GET", body=b"{}"):
    req = MagicMock()
    req.uri = uri
    req.method = method
    req.body = body
    return req


@pytest.mark.unittest
class TestBaseApiHandler:

    def test_handle_404(self):
        from compresso.webserver.api_v1.base_api_handler import BaseApiHandler
        handler = BaseApiHandler.__new__(BaseApiHandler)
        handler.set_status = MagicMock()
        handler.write = MagicMock()
        handler.handle_404()
        handler.set_status.assert_called_with(404)
        handler.write.assert_called_with('404 Not Found')

    def test_action_route_no_match(self):
        from compresso.webserver.api_v1.base_api_handler import BaseApiHandler
        handler = BaseApiHandler.__new__(BaseApiHandler)
        handler.routes = []
        handler.request = _mock_request(uri="/api/v1/nonexistent")
        handler.set_status = MagicMock()
        handler.write = MagicMock()
        handler.action_route()
        handler.set_status.assert_called_with(404)

    def test_action_route_method_filter(self):
        from compresso.webserver.api_v1.base_api_handler import BaseApiHandler
        handler = BaseApiHandler.__new__(BaseApiHandler)
        handler.routes = [
            {
                "supported_methods": ["POST"],
                "call_method": "test_method",
                "path_pattern": r"/api/v1/test",
            },
        ]
        handler.request = _mock_request(uri="/api/v1/test", method="GET")
        handler.set_status = MagicMock()
        handler.write = MagicMock()
        handler.action_route()
        handler.set_status.assert_called_with(404)

    def test_action_route_exact_match(self):
        from compresso.webserver.api_v1.base_api_handler import BaseApiHandler
        handler = BaseApiHandler.__new__(BaseApiHandler)
        handler.test_method = MagicMock()
        handler.routes = [
            {
                "supported_methods": ["GET"],
                "call_method": "test_method",
                "path_pattern": r"/api/v1/test",
            },
        ]
        handler.request = _mock_request(uri="/api/v1/test", method="GET")
        handler.action_route()
        handler.test_method.assert_called_once()


@pytest.mark.unittest
class TestFilebrowserFetchPathData:

    def test_fetch_path_data_directories_only(self, tmp_path):
        from compresso.webserver.api_v1.filebrowser_api import ApiFilebrowserHandler
        handler = ApiFilebrowserHandler.__new__(ApiFilebrowserHandler)
        handler.logger = MagicMock()

        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (tmp_path / "file.txt").write_text("content")

        result = handler.fetch_path_data(str(tmp_path), "directories")
        assert result['success'] is True
        assert len(result['directories']) >= 1
        assert result['files'] == []

    def test_fetch_path_data_files_only(self, tmp_path):
        from compresso.webserver.api_v1.filebrowser_api import ApiFilebrowserHandler
        handler = ApiFilebrowserHandler.__new__(ApiFilebrowserHandler)

        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")

        result = handler.fetch_path_data(str(tmp_path), "files")
        assert result['directories'] == []
        assert len(result['files']) == 2

    def test_fetch_path_data_all(self, tmp_path):
        from compresso.webserver.api_v1.filebrowser_api import ApiFilebrowserHandler
        handler = ApiFilebrowserHandler.__new__(ApiFilebrowserHandler)

        subdir = tmp_path / "mydir"
        subdir.mkdir()
        (tmp_path / "myfile.txt").write_text("x")

        result = handler.fetch_path_data(str(tmp_path), "all")
        assert len(result['directories']) >= 1
        assert len(result['files']) >= 1

    def test_fetch_directories_nonexistent_path(self):
        from compresso.webserver.api_v1.filebrowser_api import ApiFilebrowserHandler
        handler = ApiFilebrowserHandler.__new__(ApiFilebrowserHandler)
        result = handler.fetch_directories("/nonexistent/path/12345")
        assert len(result) == 1
        assert result[0]['name'] == '/'

    def test_fetch_files_nonexistent_path(self):
        from compresso.webserver.api_v1.filebrowser_api import ApiFilebrowserHandler
        handler = ApiFilebrowserHandler.__new__(ApiFilebrowserHandler)
        result = handler.fetch_files("/nonexistent/path/12345")
        assert result == []

    def test_fetch_directories_includes_parent(self, tmp_path):
        from compresso.webserver.api_v1.filebrowser_api import ApiFilebrowserHandler
        handler = ApiFilebrowserHandler.__new__(ApiFilebrowserHandler)
        subdir = tmp_path / "child"
        subdir.mkdir()
        result = handler.fetch_directories(str(subdir))
        parent_entries = [d for d in result if d['name'] == '..']
        assert len(parent_entries) == 1


@pytest.mark.unittest
class TestHistoryHandler:

    def test_delete_historic_tasks(self):
        from compresso.webserver.api_v1.history_api import ApiHistoryHandler
        handler = ApiHistoryHandler.__new__(ApiHistoryHandler)
        handler.config = MagicMock()
        mock_history = MagicMock()
        mock_history.delete_historic_tasks_recursively.return_value = True
        with patch('compresso.webserver.api_v1.history_api.history.History', return_value=mock_history):
            result = handler.delete_historic_tasks([1, 2])
        assert result is True

    def test_fetch_by_id_is_noop(self):
        from compresso.webserver.api_v1.history_api import ApiHistoryHandler
        handler = ApiHistoryHandler.__new__(ApiHistoryHandler)
        # fetch_by_id is a pass/TODO - should not raise
        handler.fetch_by_id()


@pytest.mark.unittest
class TestPendingHandler:

    def test_delete_pending_tasks(self):
        from compresso.webserver.api_v1.pending_api import ApiPendingHandler
        handler = ApiPendingHandler.__new__(ApiPendingHandler)
        mock_task = MagicMock()
        mock_task.delete_tasks_recursively.return_value = True
        with patch('compresso.webserver.api_v1.pending_api.task.Task', return_value=mock_task):
            result = handler.delete_pending_tasks([1])
        assert result is True

    def test_reorder_pending_tasks(self):
        from compresso.webserver.api_v1.pending_api import ApiPendingHandler
        handler = ApiPendingHandler.__new__(ApiPendingHandler)
        mock_task = MagicMock()
        mock_task.reorder_tasks.return_value = 1
        with patch('compresso.webserver.api_v1.pending_api.task.Task', return_value=mock_task):
            result = handler.reorder_pending_tasks([1], "top")
        assert result == 1

    def test_add_tasks_is_noop(self):
        from compresso.webserver.api_v1.pending_api import ApiPendingHandler
        handler = ApiPendingHandler.__new__(ApiPendingHandler)
        handler.add_tasks_to_pending_tasks_list()


@pytest.mark.unittest
class TestPluginsApiHandler:

    def test_get_plugin_list(self):
        from compresso.webserver.api_v1.plugins_api import ApiPluginsHandler
        handler = ApiPluginsHandler.__new__(ApiPluginsHandler)
        handler.write = MagicMock()
        mock_plugins = MagicMock()
        mock_plugins.get_installable_plugins_list.return_value = [{"plugin_id": "p1"}]
        with patch('compresso.webserver.api_v1.plugins_api.PluginsHandler', return_value=mock_plugins):
            handler.get_plugin_list()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True
        assert len(written['plugins']) == 1

    def test_install_plugin_success(self):
        from compresso.webserver.api_v1.plugins_api import ApiPluginsHandler
        handler = ApiPluginsHandler.__new__(ApiPluginsHandler)
        handler.write = MagicMock()
        handler.get_argument = MagicMock(return_value='test_plugin')
        mock_plugins = MagicMock()
        mock_plugins.install_plugin_by_id.return_value = True
        with patch('compresso.webserver.api_v1.plugins_api.PluginsHandler', return_value=mock_plugins):
            handler.install_plugin_by_id()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True

    def test_install_plugin_failure(self):
        from compresso.webserver.api_v1.plugins_api import ApiPluginsHandler
        handler = ApiPluginsHandler.__new__(ApiPluginsHandler)
        handler.write = MagicMock()
        handler.get_argument = MagicMock(return_value='bad_plugin')
        mock_plugins = MagicMock()
        mock_plugins.install_plugin_by_id.return_value = False
        with patch('compresso.webserver.api_v1.plugins_api.PluginsHandler', return_value=mock_plugins):
            handler.install_plugin_by_id()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is False

    def test_update_repos_success(self):
        from compresso.webserver.api_v1.plugins_api import ApiPluginsHandler
        handler = ApiPluginsHandler.__new__(ApiPluginsHandler)
        handler.write = MagicMock()
        mock_plugins = MagicMock()
        mock_plugins.update_plugin_repos.return_value = True
        with patch('compresso.webserver.api_v1.plugins_api.PluginsHandler', return_value=mock_plugins):
            handler.update_repos()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True

    def test_update_repos_failure(self):
        from compresso.webserver.api_v1.plugins_api import ApiPluginsHandler
        handler = ApiPluginsHandler.__new__(ApiPluginsHandler)
        handler.write = MagicMock()
        mock_plugins = MagicMock()
        mock_plugins.update_plugin_repos.return_value = False
        with patch('compresso.webserver.api_v1.plugins_api.PluginsHandler', return_value=mock_plugins):
            handler.update_repos()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is False

    def test_get_repo_list_success(self):
        from compresso.webserver.api_v1.plugins_api import ApiPluginsHandler
        handler = ApiPluginsHandler.__new__(ApiPluginsHandler)
        handler.write = MagicMock()
        mock_plugins = MagicMock()
        mock_plugins.get_plugin_repos.return_value = [
            {"path": "default"},
            {"path": "https://custom.repo"},
        ]
        mock_plugins.get_default_repo.return_value = "default"
        with patch('compresso.webserver.api_v1.plugins_api.PluginsHandler', return_value=mock_plugins):
            handler.get_repo_list()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True
        assert len(written['repos']) == 1

    def test_get_repo_list_exception(self):
        from compresso.webserver.api_v1.plugins_api import ApiPluginsHandler
        handler = ApiPluginsHandler.__new__(ApiPluginsHandler)
        handler.write = MagicMock()
        with patch('compresso.webserver.api_v1.plugins_api.PluginsHandler', side_effect=Exception("db error")):
            handler.get_repo_list()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is False


@pytest.mark.unittest
class TestSessionApiHandler:

    def _make_handler(self):
        from compresso.webserver.api_v1.session_api import ApiSessionHandler
        handler = ApiSessionHandler.__new__(ApiSessionHandler)
        handler.write = MagicMock()
        handler.session = MagicMock()
        handler.session.get_installation_uuid.return_value = 'test-uuid'
        return handler

    def test_get_sign_out_url_success(self):
        handler = self._make_handler()
        handler.session.get_sign_out_url.return_value = 'https://example.com/sign-out'
        handler.get_sign_out_url()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True
        assert written['data']['url'] == 'https://example.com/sign-out'

    def test_get_sign_out_url_failure(self):
        handler = self._make_handler()
        handler.session.get_sign_out_url.return_value = None
        handler.get_sign_out_url()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is False

    def test_get_patreon_login_url_success(self):
        handler = self._make_handler()
        handler.session.get_patreon_login_url.return_value = 'https://patreon.com/oauth'
        handler.get_patreon_login_url()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True

    def test_get_patreon_login_url_failure(self):
        handler = self._make_handler()
        handler.session.get_patreon_login_url.return_value = None
        handler.get_patreon_login_url()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is False

    def test_get_github_login_url_success(self):
        handler = self._make_handler()
        handler.session.get_github_login_url.return_value = 'https://github.com/oauth'
        handler.get_github_login_url()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True

    def test_get_github_login_url_failure(self):
        handler = self._make_handler()
        handler.session.get_github_login_url.return_value = None
        handler.get_github_login_url()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is False

    def test_get_discord_login_url_success(self):
        handler = self._make_handler()
        handler.session.get_discord_login_url.return_value = 'https://discord.com/oauth'
        handler.get_discord_login_url()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True

    def test_get_discord_login_url_failure(self):
        handler = self._make_handler()
        handler.session.get_discord_login_url.return_value = None
        handler.get_discord_login_url()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is False

    def test_get_patreon_page_success(self):
        handler = self._make_handler()
        handler.session.get_patreon_sponsor_page.return_value = {"sponsor_page": "<html>page</html>"}
        handler.get_patreon_page()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is True
        assert written['data']['sponsor_page'] == '<html>page</html>'

    def test_get_patreon_page_failure(self):
        handler = self._make_handler()
        handler.session.get_patreon_sponsor_page.return_value = None
        handler.get_patreon_page()
        written = json.loads(handler.write.call_args[0][0])
        assert written['success'] is False
