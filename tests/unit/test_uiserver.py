#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_uiserver.py

    Unit tests for compresso/libs/uiserver.
    Tests CompressoDataQueues, CompressoRunningThreads singletons,
    UIServer configuration, route setup, and server lifecycle.
"""

import queue
from unittest.mock import patch, MagicMock

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.mark.unittest
class TestCompressoDataQueues:

    def test_set_and_get_queues(self):
        from compresso.libs.uiserver import CompressoDataQueues
        udq = CompressoDataQueues()
        queues = {'scheduledtasks': queue.Queue(), 'inotifytasks': queue.Queue()}
        udq.set_compresso_data_queues(queues)
        result = udq.get_compresso_data_queues()
        assert result is queues

    def test_singleton_behavior(self):
        from compresso.libs.uiserver import CompressoDataQueues
        q1 = CompressoDataQueues()
        q2 = CompressoDataQueues()
        assert q1 is q2

    def test_default_empty(self):
        from compresso.libs.uiserver import CompressoDataQueues
        udq = CompressoDataQueues()
        assert udq.get_compresso_data_queues() == {}


@pytest.mark.unittest
class TestCompressoRunningThreads:

    def test_set_and_get_thread(self):
        from compresso.libs.uiserver import CompressoRunningThreads
        urt = CompressoRunningThreads()
        mock_foreman = MagicMock()
        urt.set_compresso_running_threads({'foreman': mock_foreman})
        assert urt.get_compresso_running_thread('foreman') is mock_foreman

    def test_get_nonexistent_thread(self):
        from compresso.libs.uiserver import CompressoRunningThreads
        urt = CompressoRunningThreads()
        urt.set_compresso_running_threads({})
        assert urt.get_compresso_running_thread('nonexistent') is None

    def test_singleton_behavior(self):
        from compresso.libs.uiserver import CompressoRunningThreads
        t1 = CompressoRunningThreads()
        t2 = CompressoRunningThreads()
        assert t1 is t2


def _make_uiserver(developer=False):
    """Create a UIServer with mocked dependencies."""
    with patch('compresso.libs.uiserver.config.Config') as mock_config, \
         patch('compresso.libs.uiserver.CompressoLogging') as mock_log, \
         patch('compresso.libs.uiserver.CompressoDataQueues'), \
         patch('compresso.libs.uiserver.CompressoRunningThreads'), \
         patch('compresso.libs.uiserver.common'):
        mock_settings = MagicMock()
        mock_settings.get_log_path.return_value = ''
        mock_config.return_value = mock_settings
        mock_log.get_logger.return_value = MagicMock()

        from compresso.libs.uiserver import UIServer
        data_queues = {'inotifytasks': queue.Queue()}
        foreman = MagicMock()
        server = UIServer(data_queues, foreman, developer)
    return server


@pytest.mark.unittest
class TestUIServerInit:

    def test_init_attributes(self):
        server = _make_uiserver()
        assert server.started is False
        assert server.developer is False
        assert server.io_loop is None
        assert server.server is None

    def test_init_developer_mode(self):
        server = _make_uiserver(developer=True)
        assert server.developer is True


@pytest.mark.unittest
class TestUIServerStop:

    def test_stop_not_started(self):
        server = _make_uiserver()
        server.started = False
        server.io_loop = None
        server.stop()  # Should not raise

    def test_stop_when_started(self):
        server = _make_uiserver()
        server.started = True
        mock_loop = MagicMock()
        server.io_loop = mock_loop
        server.stop()
        assert server.started is False
        mock_loop.add_callback.assert_called_once()
        mock_loop.close.assert_called_once_with(True)


@pytest.mark.unittest
class TestUIServerLog:

    def test_log_info(self):
        server = _make_uiserver()
        with patch('compresso.libs.uiserver.common.format_message', return_value='formatted'):
            server._log('test message')
            server.logger.info.assert_called_with('formatted')

    def test_log_error(self):
        server = _make_uiserver()
        with patch('compresso.libs.uiserver.common.format_message', return_value='error msg'):
            server._log('err', level='error')
            server.logger.error.assert_called_with('error msg')


@pytest.mark.unittest
class TestUIServerUpdateTornadoSettings:

    def test_developer_mode_settings(self):
        server = _make_uiserver(developer=True)
        from compresso.libs.uiserver import tornado_settings
        original_autoreload = tornado_settings.get('autoreload')
        server.update_tornado_settings()
        assert tornado_settings['autoreload'] is True
        assert tornado_settings['serve_traceback'] is True
        # Restore
        tornado_settings['autoreload'] = original_autoreload
        tornado_settings.pop('serve_traceback', None)

    def test_non_developer_mode_settings(self):
        server = _make_uiserver(developer=False)
        from compresso.libs.uiserver import tornado_settings
        original = tornado_settings.get('autoreload')
        server.update_tornado_settings()
        # Non-developer mode doesn't modify autoreload
        tornado_settings['autoreload'] = original


@pytest.mark.unittest
class TestUIServerSetLogging:

    def test_set_logging_no_log_path(self):
        server = _make_uiserver()
        server.config.get_log_path.return_value = ''
        server.set_logging()  # Should not raise or create file handlers

    @patch('compresso.libs.uiserver.os.path.exists', return_value=True)
    @patch('compresso.libs.uiserver.logging.handlers.TimedRotatingFileHandler')
    @patch('compresso.libs.uiserver.logging.getLogger')
    def test_set_logging_with_path_non_developer(self, mock_get_logger, mock_handler_cls,
                                                   mock_exists):
        server = _make_uiserver(developer=False)
        server.config.get_log_path.return_value = '/tmp/compresso_logs'
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        server.set_logging()
        assert mock_get_logger.call_count >= 3  # tornado.access, tornado.application, tornado.general

    @patch('compresso.libs.uiserver.os.path.exists', return_value=False)
    @patch('compresso.libs.uiserver.os.makedirs')
    @patch('compresso.libs.uiserver.logging.handlers.TimedRotatingFileHandler')
    @patch('compresso.libs.uiserver.logging.getLogger')
    def test_set_logging_creates_directory(self, mock_get_logger, mock_handler_cls,
                                            mock_makedirs, mock_exists):
        server = _make_uiserver(developer=True)
        server.config.get_log_path.return_value = '/tmp/new_log_path'
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger
        server.set_logging()
        mock_makedirs.assert_called_once_with('/tmp/new_log_path')


@pytest.mark.unittest
class TestUIServerMakeWebApp:

    @patch('compresso.libs.uiserver.os.makedirs')
    @patch('swagger_ui.tornado_api_doc')
    def test_make_web_app_returns_application(self, mock_swagger, mock_makedirs):
        server = _make_uiserver(developer=False)
        server.config.get_cache_path.return_value = '/tmp/cache'
        with patch('compresso.libs.uiserver.tornado.web.Application') as mock_app_cls:
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            result = server.make_web_app()
            assert result is mock_app
            mock_swagger.assert_called_once()

    @patch('compresso.libs.uiserver.os.makedirs')
    @patch('swagger_ui.tornado_api_doc')
    def test_make_web_app_developer_mode(self, mock_swagger, mock_makedirs):
        server = _make_uiserver(developer=True)
        server.config.get_cache_path.return_value = '/tmp/cache'
        mock_gen = MagicMock(return_value=[])
        with patch('compresso.libs.uiserver.tornado.web.Application') as mock_app_cls, \
             patch.dict('sys.modules', {'compresso.webserver.api_v2.schema.swagger': MagicMock(generate_swagger_file=mock_gen)}):
            mock_app = MagicMock()
            mock_app_cls.return_value = mock_app
            server.make_web_app()
            mock_gen.assert_called_once()


@pytest.mark.unittest
class TestTornadoSettingsModule:

    def test_public_directory_exists_or_is_set(self):
        from compresso.libs.uiserver import public_directory, tornado_settings
        assert isinstance(public_directory, str)
        assert 'template_loader' in tornado_settings
        assert 'static_css' in tornado_settings
        assert 'static_js' in tornado_settings
