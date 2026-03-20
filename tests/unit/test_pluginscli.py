#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_pluginscli.py

    Unit tests for compresso.libs.unplugins.pluginscli.
"""

import os
import sys
import types
import pytest
from unittest.mock import patch, MagicMock, Mock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture(autouse=True)
def mock_inquirer():
    """Mock the inquirer module which may not be installed in test env."""
    mock_inq = types.ModuleType('inquirer')
    mock_inq.List = Mock(side_effect=lambda *args, **kwargs: {'args': args, 'kwargs': kwargs})
    mock_inq.Text = Mock(side_effect=lambda *args, **kwargs: {'args': args, 'kwargs': kwargs})
    mock_inq.Checkbox = Mock(side_effect=lambda *args, **kwargs: {'args': args, 'kwargs': kwargs})
    mock_inq.prompt = Mock(return_value=None)
    mod_key = 'compresso.libs.unplugins.pluginscli'
    with patch.dict(sys.modules, {'inquirer': mock_inq}):
        # Force re-import of pluginscli if it was cached without inquirer
        sys.modules.pop(mod_key, None)
        yield mock_inq
    # Clean up cached module after test
    sys.modules.pop(mod_key, None)


def _import_pluginscli():
    """Helper to import pluginscli with inquirer mocked."""
    from compresso.libs.unplugins import pluginscli
    return pluginscli


@pytest.mark.unittest
class TestPrintTable:

    def test_prints_table_data(self, capsys):
        pluginscli = _import_pluginscli()
        table_data = [
            {'name': 'Plugin A', 'version': '1.0'},
            {'name': 'Plugin B', 'version': '2.0'},
        ]
        pluginscli.print_table(table_data)
        captured = capsys.readouterr()
        assert 'Plugin A' in captured.out
        assert 'Plugin B' in captured.out

    def test_prints_with_col_list(self, capsys):
        pluginscli = _import_pluginscli()
        table_data = [
            {'name': 'Plugin A', 'version': '1.0', 'author': 'Alice'},
        ]
        pluginscli.print_table(table_data, col_list=['name', 'version'])
        captured = capsys.readouterr()
        assert 'Plugin A' in captured.out

    def test_handles_none_values(self, capsys):
        pluginscli = _import_pluginscli()
        table_data = [
            {'name': None, 'version': '1.0'},
        ]
        pluginscli.print_table(table_data)
        captured = capsys.readouterr()
        assert '1.0' in captured.out


@pytest.mark.unittest
class TestPluginsCLIInit:

    def test_initialization(self):
        pluginscli = _import_pluginscli()

        with patch.object(pluginscli, 'config') as mock_config, \
             patch.object(pluginscli, 'CompressoLogging') as mock_logging, \
             patch.object(pluginscli, 'common') as mock_common, \
             patch.object(pluginscli, 'set_shared_manager') as mock_set_mgr, \
             patch.object(pluginscli, 'kill_all_plugin_processes'), \
             patch.object(pluginscli, 'TaskDataStore'), \
             patch('multiprocessing.Manager') as mock_mgr_cls:
            mock_config.Config.return_value = MagicMock()
            mock_common.get_home_dir.return_value = '/fake/home'
            mock_logging.get_logger.return_value = MagicMock()
            mock_mgr_instance = MagicMock()
            mock_mgr_cls.return_value = mock_mgr_instance

            cli = pluginscli.PluginsCLI(plugins_directory='/custom/plugins')

            assert cli.plugins_directory == '/custom/plugins'
            mock_set_mgr.assert_called_once_with(mock_mgr_instance)

    def test_initialization_default_directory(self):
        pluginscli = _import_pluginscli()

        with patch.object(pluginscli, 'config') as mock_config, \
             patch.object(pluginscli, 'CompressoLogging') as mock_logging, \
             patch.object(pluginscli, 'common') as mock_common, \
             patch.object(pluginscli, 'set_shared_manager'), \
             patch.object(pluginscli, 'kill_all_plugin_processes'), \
             patch.object(pluginscli, 'TaskDataStore'), \
             patch('multiprocessing.Manager') as mock_mgr_cls:
            mock_config.Config.return_value = MagicMock()
            mock_common.get_home_dir.return_value = '/fake/home'
            mock_logging.get_logger.return_value = MagicMock()
            mock_mgr_cls.return_value = MagicMock()

            cli = pluginscli.PluginsCLI()

            expected = os.path.join('/fake/home', '.compresso', 'plugins')
            assert cli.plugins_directory == expected


@pytest.mark.unittest
class TestNormalizePluginId:

    def test_sanitizes_special_characters(self):
        pluginscli = _import_pluginscli()
        result = pluginscli.PluginsCLI._normalize_plugin_id('My Plugin!@#v2')
        assert result == 'my_plugin_v2'

    def test_converts_to_lowercase(self):
        pluginscli = _import_pluginscli()
        result = pluginscli.PluginsCLI._normalize_plugin_id('MyPlugin')
        assert result == 'myplugin'

    def test_replaces_spaces_with_underscore(self):
        pluginscli = _import_pluginscli()
        result = pluginscli.PluginsCLI._normalize_plugin_id('my plugin name')
        assert result == 'my_plugin_name'

    def test_already_valid_id(self):
        pluginscli = _import_pluginscli()
        result = pluginscli.PluginsCLI._normalize_plugin_id('valid_plugin_id_123')
        assert result == 'valid_plugin_id_123'

    def test_empty_string(self):
        pluginscli = _import_pluginscli()
        result = pluginscli.PluginsCLI._normalize_plugin_id('')
        assert result == ''


@pytest.mark.unittest
class TestOrderPluginTypeDetails:

    def test_orders_by_priority(self):
        pluginscli = _import_pluginscli()
        details = [
            {'runner': 'on_worker_process'},
            {'runner': 'on_library_management_file_test'},
            {'runner': 'render_frontend_panel'},
        ]
        result = pluginscli.PluginsCLI._order_plugin_type_details(details)
        runners = [d['runner'] for d in result]
        assert runners.index('on_library_management_file_test') < runners.index('on_worker_process')
        assert runners.index('on_worker_process') < runners.index('render_frontend_panel')

    def test_emit_runners_after_known(self):
        pluginscli = _import_pluginscli()
        details = [
            {'runner': 'emit_some_event'},
            {'runner': 'on_library_management_file_test'},
        ]
        result = pluginscli.PluginsCLI._order_plugin_type_details(details)
        runners = [d['runner'] for d in result]
        assert runners.index('on_library_management_file_test') < runners.index('emit_some_event')

    def test_unknown_runners_come_last(self):
        pluginscli = _import_pluginscli()
        details = [
            {'runner': 'unknown_runner'},
            {'runner': 'on_worker_process'},
        ]
        result = pluginscli.PluginsCLI._order_plugin_type_details(details)
        runners = [d['runner'] for d in result]
        assert runners.index('on_worker_process') < runners.index('unknown_runner')

    def test_empty_list(self):
        pluginscli = _import_pluginscli()
        result = pluginscli.PluginsCLI._order_plugin_type_details([])
        assert result == []


@pytest.mark.unittest
class TestGetPluginTypeChoices:

    def test_returns_choices_and_details(self):
        pluginscli = _import_pluginscli()

        with patch.object(pluginscli, 'config') as mock_config, \
             patch.object(pluginscli, 'CompressoLogging') as mock_logging, \
             patch.object(pluginscli, 'common') as mock_common, \
             patch.object(pluginscli, 'set_shared_manager'), \
             patch.object(pluginscli, 'kill_all_plugin_processes'), \
             patch.object(pluginscli, 'TaskDataStore'), \
             patch('multiprocessing.Manager') as mock_mgr_cls, \
             patch.object(pluginscli, 'plugin_types') as mock_pt:
            mock_config.Config.return_value = MagicMock()
            mock_common.get_home_dir.return_value = '/fake/home'
            mock_logging.get_logger.return_value = MagicMock()
            mock_mgr_cls.return_value = MagicMock()

            mock_pt.get_all_plugin_types.return_value = {
                'worker.process': {
                    'name': 'Worker - Processing file',
                    'runner': 'on_worker_process',
                    'runner_docstring': 'Process a file',
                },
            }

            cli = pluginscli.PluginsCLI(plugins_directory='/fake/plugins')
            choices, by_name, by_runner = cli._get_plugin_type_choices()

            assert 'Worker - Processing file' in choices
            assert 'Worker - Processing file' in by_name
            assert 'on_worker_process' in by_runner
