#!/usr/bin/env python3

"""
    tests.unit.test_webserver_plugins.py

    Unit tests for compresso.webserver.plugins module.
"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


PLUGINS_MOD = 'compresso.webserver.plugins'


# ------------------------------------------------------------------
# TestGetPluginByPath
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetPluginByPath:
    """Tests for get_plugin_by_path()."""

    @patch(f'{PLUGINS_MOD}.plugins.get_enabled_plugin_data_panels')
    def test_finds_data_panel_plugin(self, mock_get_panels):
        from compresso.webserver.plugins import get_plugin_by_path
        mock_get_panels.return_value = [
            {'plugin_id': 'my_panel', 'name': 'My Panel'},
            {'plugin_id': 'other_panel', 'name': 'Other'},
        ]
        # Path splits: ['', 'x', 'data_panel', 'my_panel', ...] => [2]='data_panel', [3]='my_panel'
        result = get_plugin_by_path('/x/data_panel/my_panel/some/path')
        assert result is not None
        assert result['plugin_id'] == 'my_panel'

    @patch(f'{PLUGINS_MOD}.plugins.get_enabled_plugin_plugin_apis')
    def test_finds_plugin_api(self, mock_get_apis):
        from compresso.webserver.plugins import get_plugin_by_path
        mock_get_apis.return_value = [
            {'plugin_id': 'my_api', 'name': 'My API'},
        ]
        # Path splits: ['', 'x', 'plugin_api', 'my_api', ...] => [2]='plugin_api', [3]='my_api'
        result = get_plugin_by_path('/x/plugin_api/my_api/endpoint')
        assert result is not None
        assert result['plugin_id'] == 'my_api'

    @patch(f'{PLUGINS_MOD}.plugins.get_enabled_plugin_data_panels')
    def test_returns_none_for_unknown_plugin(self, mock_get_panels):
        from compresso.webserver.plugins import get_plugin_by_path
        mock_get_panels.return_value = [
            {'plugin_id': 'my_panel', 'name': 'My Panel'},
        ]
        result = get_plugin_by_path('/x/data_panel/unknown_plugin/path')
        assert result is None

    @patch(f'{PLUGINS_MOD}.plugins.get_enabled_plugin_plugin_apis')
    def test_returns_none_for_unknown_api(self, mock_get_apis):
        from compresso.webserver.plugins import get_plugin_by_path
        mock_get_apis.return_value = []
        result = get_plugin_by_path('/x/plugin_api/missing/path')
        assert result is None


# ------------------------------------------------------------------
# TestDataPanelRequestHandler
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestDataPanelRequestHandler:
    """Tests for DataPanelRequestHandler."""

    def _make_handler(self, path='/compresso/panel/data_panel/test_plugin/index.html',
                      uri='/compresso/panel/data_panel/test_plugin/index.html',
                      query='', arguments=None):
        from compresso.webserver.plugins import DataPanelRequestHandler

        app = MagicMock()
        app.ui_methods = {}
        app.ui_modules = {}
        request = MagicMock()
        request.connection = MagicMock()
        request.path = path
        request.uri = uri
        request.query = query
        request.arguments = arguments or {}

        handler = DataPanelRequestHandler(app, request)
        return handler

    @patch(f'{PLUGINS_MOD}.plugins.exec_data_panels_plugin_runner', return_value=True)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_handle_panel_request_success(self, mock_get_plugin, mock_exec):
        handler = self._make_handler()
        mock_get_plugin.return_value = {'plugin_id': 'test_plugin'}
        handler.render_data = MagicMock()

        handler.handle_panel_request()

        mock_exec.assert_called_once()
        handler.render_data.assert_called_once()

    @patch(f'{PLUGINS_MOD}.get_plugin_by_path', return_value=None)
    def test_handle_panel_request_not_found(self, mock_get_plugin):
        handler = self._make_handler()
        handler.set_status = MagicMock()
        handler.write = MagicMock()

        handler.handle_panel_request()

        handler.set_status.assert_called_with(404)
        handler.write.assert_called_with('404 Not Found')

    @patch(f'{PLUGINS_MOD}.plugins.exec_data_panels_plugin_runner', return_value=False)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_handle_panel_request_plugin_failure(self, mock_get_plugin, mock_exec):
        handler = self._make_handler()
        mock_get_plugin.return_value = {'plugin_id': 'test_plugin'}
        handler.render_data = MagicMock()

        handler.handle_panel_request()

        # Should still render data even on plugin failure
        handler.render_data.assert_called_once()

    def test_render_data(self):
        handler = self._make_handler()
        handler.set_header = MagicMock()
        handler.write = MagicMock()

        handler.render_data({'content_type': 'text/html', 'content': '<h1>test</h1>'})

        handler.set_header.assert_called_with("Content-Type", 'text/html')
        handler.write.assert_called_with('<h1>test</h1>')

    @patch(f'{PLUGINS_MOD}.plugins.exec_data_panels_plugin_runner', return_value=True)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_get_method_calls_handle(self, mock_get_plugin, mock_exec):
        handler = self._make_handler()
        mock_get_plugin.return_value = {'plugin_id': 'test_plugin'}
        handler.render_data = MagicMock()

        handler.get('/some/path')

        handler.render_data.assert_called_once()


# ------------------------------------------------------------------
# TestPluginAPIRequestHandler
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestPluginAPIRequestHandler:
    """Tests for PluginAPIRequestHandler."""

    def _make_handler(self, path='/compresso/panel/plugin_api/test_api/endpoint',
                      uri='/compresso/panel/plugin_api/test_api/endpoint',
                      query='', arguments=None, method='GET', body=b''):
        from compresso.webserver.plugins import PluginAPIRequestHandler

        app = MagicMock()
        app.ui_methods = {}
        app.ui_modules = {}
        request = MagicMock()
        request.connection = MagicMock()
        request.path = path
        request.uri = uri
        request.query = query
        request.arguments = arguments or {}
        request.method = method
        request.body = body

        handler = PluginAPIRequestHandler(app, request)
        return handler

    @patch(f'{PLUGINS_MOD}.plugins.exec_plugin_api_plugin_runner', return_value=True)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_handle_panel_request_success(self, mock_get_plugin, mock_exec):
        handler = self._make_handler()
        mock_get_plugin.return_value = {'plugin_id': 'test_api'}
        handler.render_data = MagicMock()

        handler.handle_panel_request()

        mock_exec.assert_called_once()
        handler.render_data.assert_called_once()

    @patch(f'{PLUGINS_MOD}.get_plugin_by_path', return_value=None)
    def test_handle_panel_request_not_found(self, mock_get_plugin):
        handler = self._make_handler()
        handler.set_status = MagicMock()
        handler.get_status = MagicMock(return_value=404)
        handler.write = MagicMock()
        handler._reason = "Not Found"

        handler.handle_panel_request()

        handler.set_status.assert_called_with(404, reason="404 Not Found")

    @patch(f'{PLUGINS_MOD}.plugins.exec_plugin_api_plugin_runner', side_effect=Exception("plugin crash"))
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_handle_panel_request_plugin_exception(self, mock_get_plugin, mock_exec):
        handler = self._make_handler()
        mock_get_plugin.return_value = {'plugin_id': 'test_api'}
        handler.set_status = MagicMock()
        handler.get_status = MagicMock(return_value=500)
        handler.write = MagicMock()
        handler._reason = "Error"

        handler.handle_panel_request()

        handler.set_status.assert_called()

    @patch(f'{PLUGINS_MOD}.plugins.exec_plugin_api_plugin_runner', return_value=False)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_handle_panel_request_runner_false(self, mock_get_plugin, mock_exec):
        handler = self._make_handler()
        mock_get_plugin.return_value = {'plugin_id': 'test_api'}
        handler.render_data = MagicMock()

        handler.handle_panel_request()

        # Still renders data
        handler.render_data.assert_called_once()

    def test_render_data_sets_content_type_and_status(self):
        handler = self._make_handler()
        handler.set_header = MagicMock()
        handler.set_status = MagicMock()
        handler.write = MagicMock()

        handler.render_data({
            'content_type': 'application/json',
            'content': {'key': 'value'},
            'status': 200,
        })

        handler.set_header.assert_called_with("Content-Type", 'application/json')
        handler.set_status.assert_called_with(200)
        handler.write.assert_called_with({'key': 'value'})

    @patch(f'{PLUGINS_MOD}.plugins.exec_plugin_api_plugin_runner', return_value=True)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_get_method(self, mock_get_plugin, mock_exec):
        handler = self._make_handler()
        mock_get_plugin.return_value = {'plugin_id': 'test_api'}
        handler.render_data = MagicMock()
        handler.get('/path')
        handler.render_data.assert_called_once()

    @patch(f'{PLUGINS_MOD}.plugins.exec_plugin_api_plugin_runner', return_value=True)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_post_method(self, mock_get_plugin, mock_exec):
        handler = self._make_handler(method='POST')
        mock_get_plugin.return_value = {'plugin_id': 'test_api'}
        handler.render_data = MagicMock()
        handler.post('/path')
        handler.render_data.assert_called_once()

    @patch(f'{PLUGINS_MOD}.plugins.exec_plugin_api_plugin_runner', return_value=True)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_delete_method(self, mock_get_plugin, mock_exec):
        handler = self._make_handler(method='DELETE')
        mock_get_plugin.return_value = {'plugin_id': 'test_api'}
        handler.render_data = MagicMock()
        handler.delete('/path')
        handler.render_data.assert_called_once()

    @patch(f'{PLUGINS_MOD}.plugins.exec_plugin_api_plugin_runner', return_value=True)
    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    def test_put_method(self, mock_get_plugin, mock_exec):
        handler = self._make_handler(method='PUT')
        mock_get_plugin.return_value = {'plugin_id': 'test_api'}
        handler.render_data = MagicMock()
        handler.put('/path')
        handler.render_data.assert_called_once()


# ------------------------------------------------------------------
# TestPluginStaticFileHandler
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestPluginStaticFileHandler:
    """Tests for PluginStaticFileHandler."""

    @patch(f'{PLUGINS_MOD}.get_plugin_by_path')
    @patch(f'{PLUGINS_MOD}.tornado.web.StaticFileHandler.initialize')
    def test_initialize_with_plugin(self, mock_super_init, mock_get_plugin):
        from compresso.webserver.plugins import PluginStaticFileHandler

        mock_get_plugin.return_value = {
            'plugin_id': 'test_plugin',
            'plugin_path': '/plugins/test_plugin',
        }

        app = MagicMock()
        app.ui_methods = {}
        app.ui_modules = {}
        request = MagicMock()
        request.connection = MagicMock()
        request.path = '/compresso/panel/data_panel/test_plugin/static/file.js'

        handler = PluginStaticFileHandler.__new__(PluginStaticFileHandler)
        handler.application = app
        handler.request = request
        handler.initialize(path='/default/path')

        mock_super_init.assert_called_once()
        call_args = mock_super_init.call_args
        assert 'static' in call_args[0][0] or 'static' in str(call_args)

    @patch(f'{PLUGINS_MOD}.get_plugin_by_path', return_value=None)
    @patch(f'{PLUGINS_MOD}.tornado.web.StaticFileHandler.initialize')
    def test_initialize_without_plugin(self, mock_super_init, mock_get_plugin):
        from compresso.webserver.plugins import PluginStaticFileHandler

        app = MagicMock()
        app.ui_methods = {}
        app.ui_modules = {}
        request = MagicMock()
        request.connection = MagicMock()
        request.path = '/compresso/panel/data_panel/unknown/static/file.js'

        handler = PluginStaticFileHandler.__new__(PluginStaticFileHandler)
        handler.application = app
        handler.request = request
        handler.initialize(path='/default/path')

        # Should use the default path
        mock_super_init.assert_called_once_with('/default/path', None)


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
