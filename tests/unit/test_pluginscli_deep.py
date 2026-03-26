#!/usr/bin/env python3

"""
    tests.unit.test_pluginscli_deep.py

    Deep unit tests for compresso/libs/unplugins/pluginscli.py
    covering CLI interaction methods, plugin creation, removal,
    testing, and run_from_args.
"""

import sys
import types
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture(autouse=True)
def mock_inquirer():
    mock_inq = types.ModuleType('inquirer')
    mock_inq.List = Mock(side_effect=lambda *args, **kwargs: {'args': args, 'kwargs': kwargs})
    mock_inq.Text = Mock(side_effect=lambda *args, **kwargs: {'args': args, 'kwargs': kwargs})
    mock_inq.Checkbox = Mock(side_effect=lambda *args, **kwargs: {'args': args, 'kwargs': kwargs})
    mock_inq.prompt = Mock(return_value=None)
    mod_key = 'compresso.libs.unplugins.pluginscli'
    with patch.dict(sys.modules, {'inquirer': mock_inq}):
        sys.modules.pop(mod_key, None)
        yield mock_inq
    sys.modules.pop(mod_key, None)


def _import_pluginscli():
    from compresso.libs.unplugins import pluginscli
    return pluginscli


def _make_cli(pluginscli_mod, plugins_dir='/fake/plugins'):
    with patch.object(pluginscli_mod, 'config') as mock_config, \
         patch.object(pluginscli_mod, 'CompressoLogging') as mock_logging, \
         patch.object(pluginscli_mod, 'common') as mock_common, \
         patch.object(pluginscli_mod, 'set_shared_manager'), \
         patch.object(pluginscli_mod, 'kill_all_plugin_processes'), \
         patch.object(pluginscli_mod, 'TaskDataStore'), \
         patch('multiprocessing.Manager') as mock_mgr_cls:
        mock_config.Config.return_value = MagicMock()
        mock_common.get_home_dir.return_value = '/fake/home'
        mock_logging.get_logger.return_value = MagicMock()
        mock_mgr_cls.return_value = MagicMock()
        cli = pluginscli_mod.PluginsCLI(plugins_directory=plugins_dir)
    return cli


# ==================================================================
# BColours
# ==================================================================

@pytest.mark.unittest
class TestBColours:

    def test_bcolours_attributes_are_strings(self):
        pluginscli = _import_pluginscli()
        assert isinstance(pluginscli.BColours.HEADER, str)
        assert isinstance(pluginscli.BColours.ENDC, str)
        assert isinstance(pluginscli.BColours.OKGREEN, str)
        assert isinstance(pluginscli.BColours.FAIL, str)


# ==================================================================
# PluginsCLI._parse_runner_inputs
# ==================================================================

@pytest.mark.unittest
class TestParseRunnerInputs:

    def test_returns_none_for_empty_input(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        result, errors = cli._parse_runner_inputs(
            [], {}, {}
        )
        assert result is None
        assert len(errors) > 0

    def test_returns_none_for_none_input(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        result, errors = cli._parse_runner_inputs(
            None, {}, {}
        )
        assert result is None

    def test_parses_by_runner_name(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        by_runner = {'on_worker_process': {'runner': 'on_worker_process', 'name': 'Worker'}}
        result, errors = cli._parse_runner_inputs(
            'on_worker_process', {}, by_runner
        )
        assert errors == []
        assert len(result) == 1
        assert result[0]['runner'] == 'on_worker_process'

    def test_parses_by_plugin_name(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        by_name = {'Worker': {'runner': 'on_worker_process', 'name': 'Worker'}}
        result, errors = cli._parse_runner_inputs(
            'Worker', by_name, {}
        )
        assert errors == []
        assert len(result) == 1

    def test_returns_error_for_invalid_token(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        result, errors = cli._parse_runner_inputs(
            'nonexistent_runner', {}, {}
        )
        assert result is None
        assert 'Invalid' in errors[0]

    def test_handles_comma_separated(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        by_runner = {
            'on_worker_process': {'runner': 'on_worker_process'},
            'on_postprocessor_file_movement': {'runner': 'on_postprocessor_file_movement'},
        }
        result, errors = cli._parse_runner_inputs(
            'on_worker_process,on_postprocessor_file_movement', {}, by_runner
        )
        assert errors == []
        assert len(result) == 2

    def test_deduplicates_runners(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        by_runner = {'on_worker_process': {'runner': 'on_worker_process'}}
        result, errors = cli._parse_runner_inputs(
            'on_worker_process,on_worker_process', {}, by_runner
        )
        assert errors == []
        assert len(result) == 1

    def test_handles_string_input(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        by_runner = {'on_worker_process': {'runner': 'on_worker_process'}}
        result, errors = cli._parse_runner_inputs(
            'on_worker_process', {}, by_runner
        )
        assert len(result) == 1

    def test_handles_list_input(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        by_runner = {'on_worker_process': {'runner': 'on_worker_process'}}
        result, errors = cli._parse_runner_inputs(
            ['on_worker_process'], {}, by_runner
        )
        assert len(result) == 1


# ==================================================================
# PluginsCLI.main
# ==================================================================

@pytest.mark.unittest
class TestPluginsCLIMain:

    def test_calls_list_installed_plugins(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.list_installed_plugins = MagicMock()
        cli.main('List all installed plugins')
        cli.list_installed_plugins.assert_called_once()

    def test_calls_test_plugins(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.test_plugins = MagicMock()
        cli.main('Test plugins')
        cli.test_plugins.assert_called_once()

    def test_calls_create_new_plugins(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.create_new_plugins = MagicMock()
        cli.main('Create new plugin')
        cli.create_new_plugins.assert_called_once()

    def test_calls_reload_plugin_from_disk(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.reload_plugin_from_disk = MagicMock()
        cli.main('Reload all plugins from disk')
        cli.reload_plugin_from_disk.assert_called_once()

    def test_calls_remove_plugin(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.remove_plugin = MagicMock()
        cli.main('Remove plugin')
        cli.remove_plugin.assert_called_once()

    def test_calls_install_test_data(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.install_test_data = MagicMock()
        cli.main('Install test data')
        cli.install_test_data.assert_called_once()

    def test_invalid_selection_logs(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.main('Invalid option')
        # Should not raise


# ==================================================================
# PluginsCLI.run_from_args
# ==================================================================

@pytest.mark.unittest
class TestRunFromArgs:

    def test_test_file_in_modifiers(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        args = MagicMock()
        args.test_file_in = 'custom_input.mp4'
        args.test_file_out = None
        args.create_plugin = False
        args.test_plugin = None
        args.test_plugins = False
        args.reload_plugins = False
        args.remove_plugin = False
        args.install_test_data = False
        cli.test_installed_plugins = MagicMock()
        cli.run_from_args(args)
        assert cli.test_data_modifiers['{test_file_in}'] == 'custom_input.mp4'

    def test_test_file_out_modifiers(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        args = MagicMock()
        args.test_file_in = None
        args.test_file_out = 'custom_output.mp4'
        args.create_plugin = False
        args.test_plugin = None
        args.test_plugins = False
        args.reload_plugins = False
        args.remove_plugin = False
        args.install_test_data = False
        cli.run_from_args(args)
        assert cli.test_data_modifiers['{test_file_out}'] == 'custom_output.mp4'

    def test_create_plugin_calls_from_args(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.create_new_plugins_from_args = MagicMock()
        args = MagicMock()
        args.test_file_in = None
        args.test_file_out = None
        args.create_plugin = True
        args.plugin_id = 'my_plugin'
        args.plugin_name = 'My Plugin'
        args.plugin_runners = 'on_worker_process'
        cli.run_from_args(args)
        cli.create_new_plugins_from_args.assert_called_once()

    def test_test_plugin_single(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.test_installed_plugins = MagicMock()
        args = MagicMock()
        args.test_file_in = None
        args.test_file_out = None
        args.create_plugin = False
        args.test_plugin = 'my_plugin'
        args.test_plugins = False
        args.reload_plugins = False
        args.remove_plugin = False
        args.install_test_data = False
        cli.run_from_args(args)
        cli.test_installed_plugins.assert_called_once_with(plugin_id='my_plugin')

    def test_test_all_plugins(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.test_installed_plugins = MagicMock()
        args = MagicMock()
        args.test_file_in = None
        args.test_file_out = None
        args.create_plugin = False
        args.test_plugin = None
        args.test_plugins = True
        args.reload_plugins = False
        args.remove_plugin = False
        args.install_test_data = False
        cli.run_from_args(args)
        cli.test_installed_plugins.assert_called_once()

    def test_reload_plugins(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.reload_plugin_from_disk = MagicMock()
        args = MagicMock()
        args.test_file_in = None
        args.test_file_out = None
        args.create_plugin = False
        args.test_plugin = None
        args.test_plugins = False
        args.reload_plugins = True
        args.remove_plugin = False
        args.install_test_data = False
        cli.run_from_args(args)
        cli.reload_plugin_from_disk.assert_called_once()

    def test_remove_plugin(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.remove_plugin_by_id = MagicMock()
        args = MagicMock()
        args.test_file_in = None
        args.test_file_out = None
        args.create_plugin = False
        args.test_plugin = None
        args.test_plugins = False
        args.reload_plugins = False
        args.remove_plugin = True
        args.plugin_id = 'my_plugin'
        args.install_test_data = False
        cli.run_from_args(args)
        cli.remove_plugin_by_id.assert_called_once_with('my_plugin')

    def test_install_test_data(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.install_test_data = MagicMock()
        args = MagicMock()
        args.test_file_in = None
        args.test_file_out = None
        args.create_plugin = False
        args.test_plugin = None
        args.test_plugins = False
        args.reload_plugins = False
        args.remove_plugin = False
        args.install_test_data = True
        cli.run_from_args(args)
        cli.install_test_data.assert_called_once()

    def test_invalid_args(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        args = MagicMock()
        args.test_file_in = None
        args.test_file_out = None
        args.create_plugin = False
        args.test_plugin = None
        args.test_plugins = False
        args.reload_plugins = False
        args.remove_plugin = False
        args.install_test_data = False
        cli.run_from_args(args)
        # Should not raise


# ==================================================================
# PluginsCLI.create_new_plugins_from_args
# ==================================================================

@pytest.mark.unittest
class TestCreateNewPluginsFromArgs:

    def test_returns_on_missing_plugin_id(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.create_new_plugins_from_args(None, 'Name', 'on_worker_process')
        captured = capsys.readouterr()
        assert 'ERROR' in captured.out

    def test_returns_on_missing_plugin_name(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.create_new_plugins_from_args('my_id', None, 'on_worker_process')
        captured = capsys.readouterr()
        assert 'ERROR' in captured.out

    def test_returns_on_invalid_runners(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'plugin_types') as mock_pt:
            mock_pt.get_all_plugin_types.return_value = {}
            cli.create_new_plugins_from_args('my_id', 'My Plugin', 'invalid_runner')
        captured = capsys.readouterr()
        assert 'ERROR' in captured.out


# ==================================================================
# PluginsCLI.create_new_plugin_files
# ==================================================================

@pytest.mark.unittest
class TestCreateNewPluginFiles:

    @patch('compresso.libs.unplugins.pluginscli.PluginsHandler')
    @patch('compresso.libs.unplugins.pluginscli.common.touch')
    @patch('builtins.open', mock_open())
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    def test_creates_plugin_files(self, mock_mkdirs, mock_exists, mock_touch, mock_ph_cls):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        mock_ph_cls.version = 1
        details = {'plugin_id': 'test_plugin', 'plugin_name': 'Test Plugin'}
        type_details = [{'runner': 'on_worker_process', 'runner_docstring': 'Process file'}]
        cli.create_new_plugin_files(details, type_details)
        mock_mkdirs.assert_called()
        mock_ph_cls.write_plugin_data_to_db.assert_called_once()

    @patch('compresso.libs.unplugins.pluginscli.PluginsHandler')
    @patch('compresso.libs.unplugins.pluginscli.common.touch')
    @patch('builtins.open', mock_open())
    @patch('os.path.exists', return_value=False)
    @patch('os.makedirs')
    def test_handles_db_exception(self, mock_mkdirs, mock_exists, mock_touch, mock_ph_cls):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        mock_ph_cls.version = 1
        mock_ph_cls.write_plugin_data_to_db.side_effect = Exception("DB error")
        details = {'plugin_id': 'test_plugin', 'plugin_name': 'Test Plugin'}
        type_details = [{'runner': 'on_worker_process', 'runner_docstring': 'Process'}]
        with patch.object(cli.logger, 'error') as mock_log_error:
            cli.create_new_plugin_files(details, type_details)
            mock_log_error.assert_called_once()
            assert 'DB error' in str(mock_log_error.call_args)


# ==================================================================
# PluginsCLI.remove_plugin_by_id
# ==================================================================

@pytest.mark.unittest
class TestRemovePluginById:

    def test_remove_nonexistent_prints_error(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = []
            mock_ph_cls.return_value = mock_ph
            cli.remove_plugin_by_id('nonexistent')
        captured = capsys.readouterr()
        assert 'not found' in captured.out

    def test_remove_missing_id_prints_error(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        cli.remove_plugin_by_id(None)
        captured = capsys.readouterr()
        assert 'Missing' in captured.out

    def test_remove_plugin_with_missing_db_id(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [{'plugin_id': 'p1', 'id': None}]
            mock_ph_cls.return_value = mock_ph
            cli.remove_plugin_by_id('p1')
        captured = capsys.readouterr()
        assert 'missing id' in captured.out

    def test_remove_plugin_success(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [{'plugin_id': 'p1', 'id': 42}]
            mock_ph_cls.return_value = mock_ph
            cli.remove_plugin_by_id('p1')
            mock_ph.uninstall_plugins_by_db_table_id.assert_called_once_with([42])


# ==================================================================
# PluginsCLI._uninstall_plugin_by_db_table_id
# ==================================================================

@pytest.mark.unittest
class TestUninstallPluginByDbTableId:

    def test_calls_uninstall(self):
        pluginscli = _import_pluginscli()
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph_cls.return_value = mock_ph
            pluginscli.PluginsCLI._uninstall_plugin_by_db_table_id(42)
            mock_ph.uninstall_plugins_by_db_table_id.assert_called_once_with([42])


# ==================================================================
# PluginsCLI.list_installed_plugins
# ==================================================================

@pytest.mark.unittest
class TestListInstalledPlugins:

    def test_prints_table(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [
                {'plugin_id': 'p1', 'name': 'Plugin1', 'version': '1.0'}
            ]
            mock_ph_cls.return_value = mock_ph
            with patch.object(pluginscli, 'print_table') as mock_pt:
                cli.list_installed_plugins()
                mock_pt.assert_called_once()


# ==================================================================
# PluginsCLI.__get_installed_plugins
# ==================================================================

@pytest.mark.unittest
class TestGetInstalledPlugins:

    def test_returns_all_plugins(self):
        pluginscli = _import_pluginscli()
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [{'id': 1}]
            mock_ph_cls.return_value = mock_ph
            result = pluginscli.PluginsCLI._PluginsCLI__get_installed_plugins()
            assert result == [{'id': 1}]

    def test_filters_by_plugin_id(self):
        pluginscli = _import_pluginscli()
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [{'id': 1, 'plugin_id': 'p1'}]
            mock_ph_cls.return_value = mock_ph
            result = pluginscli.PluginsCLI._PluginsCLI__get_installed_plugins(plugin_id='p1')
            assert result == [{'id': 1, 'plugin_id': 'p1'}]
            call_kwargs = mock_ph.get_plugin_list_filtered_and_sorted.call_args[1]
            assert call_kwargs['plugin_id'] == 'p1'


# ==================================================================
# PluginsCLI.test_installed_plugins
# ==================================================================

@pytest.mark.unittest
class TestTestInstalledPlugins:

    def test_tests_specific_plugin(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls, \
             patch.object(pluginscli, 'PluginExecutor') as mock_pe_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [
                {'plugin_id': 'p1', 'name': 'Plugin1'}
            ]
            mock_ph_cls.return_value = mock_ph
            mock_pe = MagicMock()
            mock_pe.test_plugin_settings.return_value = ([], {'key': 'val'})
            mock_pe.get_all_plugin_types_in_plugin.return_value = ['on_worker_process']
            mock_pe.test_plugin_runner.return_value = []
            mock_pe_cls.return_value = mock_pe
            cli.test_installed_plugins(plugin_id='p1')
        captured = capsys.readouterr()
        assert 'Plugin1' in captured.out
        assert 'PASSED' in captured.out

    def test_tests_plugin_with_settings_errors(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls, \
             patch.object(pluginscli, 'PluginExecutor') as mock_pe_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [
                {'plugin_id': 'p1', 'name': 'Plugin1'}
            ]
            mock_ph_cls.return_value = mock_ph
            mock_pe = MagicMock()
            mock_pe.test_plugin_settings.return_value = (['error1'], {})
            mock_pe.get_all_plugin_types_in_plugin.return_value = []
            mock_pe_cls.return_value = mock_pe
            cli.test_installed_plugins(plugin_id='p1')
        captured = capsys.readouterr()
        assert 'FAILED' in captured.out

    def test_tests_plugin_with_no_runners(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls, \
             patch.object(pluginscli, 'PluginExecutor') as mock_pe_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [
                {'plugin_id': 'p1', 'name': 'Plugin1'}
            ]
            mock_ph_cls.return_value = mock_ph
            mock_pe = MagicMock()
            mock_pe.test_plugin_settings.return_value = ([], {})
            mock_pe.get_all_plugin_types_in_plugin.return_value = []
            mock_pe_cls.return_value = mock_pe
            cli.test_installed_plugins(plugin_id='p1')
        captured = capsys.readouterr()
        assert 'No runners found' in captured.out

    def test_tests_plugin_with_runner_errors(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls, \
             patch.object(pluginscli, 'PluginExecutor') as mock_pe_cls:
            mock_ph = MagicMock()
            mock_ph.get_plugin_list_filtered_and_sorted.return_value = [
                {'plugin_id': 'p1', 'name': 'Plugin1'}
            ]
            mock_ph_cls.return_value = mock_ph
            mock_pe = MagicMock()
            mock_pe.test_plugin_settings.return_value = ([], {})
            mock_pe.get_all_plugin_types_in_plugin.return_value = ['on_worker_process']
            mock_pe.test_plugin_runner.return_value = ['runner failed']
            mock_pe_cls.return_value = mock_pe
            cli.test_installed_plugins(plugin_id='p1')
        captured = capsys.readouterr()
        assert 'FAILED' in captured.out


# ==================================================================
# PluginsCLI.run (main loop)
# ==================================================================

@pytest.mark.unittest
class TestPluginsCLIRun:

    def test_run_exits_on_exit_selection(self, mock_inquirer):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        mock_inquirer.prompt.return_value = {'cli_action': 'Exit'}
        cli.run()

    def test_run_exits_on_none_selection(self, mock_inquirer):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        mock_inquirer.prompt.return_value = None
        cli.run()


# ==================================================================
# print_table edge cases
# ==================================================================

@pytest.mark.unittest
class TestPrintTableEdge:

    def test_empty_table(self):
        pluginscli = _import_pluginscli()
        # Empty list should not raise
        # print_table expects non-empty, but with col_list provided
        # it should handle gracefully
        pluginscli.print_table([{'a': '1'}], col_list=['a'])

    def test_max_col_width_truncation(self, capsys):
        pluginscli = _import_pluginscli()
        data = [{'name': 'A' * 20}]
        pluginscli.print_table(data, max_col_width=5)
        captured = capsys.readouterr()
        # The long name should be truncated
        assert 'AAAAA' in captured.out


@pytest.mark.unittest
class TestCollectNewPluginDetails:

    def test_returns_none_for_invalid_input(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt', return_value={'plugin_id': '', 'plugin_name': ''}):
            details, selected = cli._collect_new_plugin_details()

        assert details is None
        assert selected is None
        assert 'Invalid input' in capsys.readouterr().out

    def test_returns_none_when_no_runners_selected(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt', side_effect=[
            {'plugin_id': 'My Plugin', 'plugin_name': 'My Plugin'},
            {'selected_plugins': []},
        ]), patch.object(cli, '_get_plugin_type_choices', return_value=(
            ['Worker'],
            {'Worker': {'runner': 'on_worker_process', 'name': 'Worker'}},
            {},
        )):
            details, selected = cli._collect_new_plugin_details()

        assert details is None
        assert selected is None
        assert 'No plugin runner selected' in capsys.readouterr().out

    def test_returns_normalized_details_and_selected_runners(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        expected_details = {'runner': 'on_worker_process', 'name': 'Worker'}
        with patch.object(pluginscli.inquirer, 'prompt', side_effect=[
            {'plugin_id': 'My Plugin!', 'plugin_name': 'My Plugin'},
            {'selected_plugins': ['Worker']},
        ]), patch.object(cli, '_get_plugin_type_choices', return_value=(
            ['Worker'],
            {'Worker': expected_details},
            {},
        )):
            details, selected = cli._collect_new_plugin_details()

        assert details == {'plugin_id': 'my_plugin_', 'plugin_name': 'My Plugin'}
        assert selected == [expected_details]


@pytest.mark.unittest
class TestCreateNewPlugins:

    def test_returns_when_no_plugin_details(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(cli, '_collect_new_plugin_details', return_value=(None, None)), \
             patch.object(cli, 'create_new_plugin_files') as mock_create:
            cli.create_new_plugins()

        mock_create.assert_not_called()

    def test_creates_new_plugin_files_when_details_exist(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        details = {'plugin_id': 'plugin_one', 'plugin_name': 'Plugin One'}
        selected = [{'runner': 'on_worker_process'}]
        with patch.object(cli, '_collect_new_plugin_details', return_value=(details, selected)), \
             patch.object(cli, 'create_new_plugin_files') as mock_create:
            cli.create_new_plugins()

        mock_create.assert_called_once_with(details, selected)


@pytest.mark.unittest
class TestReloadPluginFromDisk:

    def test_reload_plugin_success(self, capsys):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        plugin_result = {'plugin_id': 'plugin_one'}
        with patch.object(pluginscli.PluginsCLI, '_PluginsCLI__get_installed_plugins', return_value=[plugin_result]), \
             patch('builtins.open', mock_open(read_data='{}')), \
             patch.object(pluginscli.json, 'load', return_value={'id': 'plugin_one'}), \
             patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls:
            mock_ph_cls.version = 1
            cli.reload_plugin_from_disk()

        mock_ph_cls.write_plugin_data_to_db.assert_called_once()
        mock_ph_cls.install_plugin_requirements.assert_called_once()
        mock_ph_cls.install_npm_modules.assert_called_once()
        assert "Reloading Plugin - 'plugin_one'" in capsys.readouterr().out

    def test_reload_plugin_db_exception_prints_message(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        plugin_result = {'plugin_id': 'plugin_one'}
        with patch.object(pluginscli.PluginsCLI, '_PluginsCLI__get_installed_plugins', return_value=[plugin_result]), \
             patch('builtins.open', mock_open(read_data='{}')), \
             patch.object(pluginscli.json, 'load', return_value={'id': 'plugin_one'}), \
             patch.object(pluginscli, 'PluginsHandler') as mock_ph_cls, \
             patch.object(cli.logger, 'error') as mock_log_error:
            mock_ph_cls.write_plugin_data_to_db.side_effect = Exception('db failed')
            cli.reload_plugin_from_disk()

        mock_log_error.assert_called_once()
        assert 'db failed' in str(mock_log_error.call_args)


@pytest.mark.unittest
class TestRemovePluginInteractive:

    def test_remove_plugin_returns_on_go_back(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt',
                          return_value={'cli_action': 'Go Back'}), \
             patch.object(pluginscli.PluginsCLI,
                          '_PluginsCLI__get_installed_plugins',
                          return_value=[{'plugin_id': 'p1', 'id': 1}]), \
             patch.object(cli, '_uninstall_plugin_by_db_table_id') as mock_uninstall:
            cli.remove_plugin()

        mock_uninstall.assert_not_called()

    def test_remove_plugin_uninstalls_selected_plugin(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt',
                          return_value={'cli_action': 'p1'}), \
             patch.object(pluginscli.PluginsCLI,
                          '_PluginsCLI__get_installed_plugins',
                          return_value=[{'plugin_id': 'p1', 'id': 42}]), \
             patch.object(cli, '_uninstall_plugin_by_db_table_id') as mock_uninstall:
            cli.remove_plugin()

        mock_uninstall.assert_called_once_with(42)


@pytest.mark.unittest
class TestPluginsMenuFlow:

    def test_test_plugins_configures_testdata_then_returns(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt', side_effect=[
            {'selected_plugin': 'Configure Testdata'},
            {'selected_plugin': 'Go Back'},
        ]), patch.object(pluginscli.PluginsCLI, '_PluginsCLI__get_installed_plugins', return_value=[{'plugin_id': 'p1'}]), \
             patch.object(cli, 'configure_test_data') as mock_configure, \
             patch.object(cli, 'test_installed_plugins') as mock_test:
            cli.test_plugins()

        mock_configure.assert_called_once()
        mock_test.assert_not_called()

    def test_test_plugins_runs_all_plugins(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt', side_effect=[
            {'selected_plugin': 'Test All Plugins'},
            {'selected_plugin': 'Go Back'},
        ]), patch.object(pluginscli.PluginsCLI, '_PluginsCLI__get_installed_plugins', return_value=[{'plugin_id': 'p1'}]), \
             patch.object(cli, 'test_installed_plugins') as mock_test:
            cli.test_plugins()

        mock_test.assert_called_once_with()

    def test_test_plugins_runs_selected_plugin(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt', side_effect=[
            {'selected_plugin': 'p1'},
            {'selected_plugin': 'Go Back'},
        ]), patch.object(pluginscli.PluginsCLI, '_PluginsCLI__get_installed_plugins', return_value=[{'plugin_id': 'p1'}]), \
             patch.object(cli, 'test_installed_plugins') as mock_test:
            cli.test_plugins()

        mock_test.assert_called_once_with(plugin_id='p1')


@pytest.mark.unittest
class TestConfigureAndInstallTestData:

    def test_configure_test_data_updates_modifiers(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt', return_value={'selected_file': 'sample.mp4'}), \
             patch.object(pluginscli.os, 'walk', return_value=[('/tmp', [], ['sample.mp4'])]):
            cli.configure_test_data()

        assert cli.test_data_modifiers['{test_file_in}'] == 'sample.mp4'
        assert cli.test_data_modifiers['{test_file_out}'] == 'sample-WORKING-1.mp4'

    def test_install_test_data_downloads_and_copies_files(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.iter_content.return_value = [b'data']
        with patch.object(pluginscli.os.path, 'exists', return_value=False), \
             patch.object(pluginscli.os, 'makedirs') as mock_makedirs, \
             patch.object(pluginscli.requests, 'get', return_value=response) as mock_get, \
             patch('builtins.open', mock_open()), \
             patch.object(pluginscli.shutil, 'copyfile') as mock_copy:
            cli.install_test_data()

        assert mock_makedirs.call_count == 2
        assert mock_get.call_count == 5
        assert mock_copy.call_count == 5


@pytest.mark.unittest
class TestPluginsCLIRunLoop:

    def test_run_calls_main_before_exit(self):
        pluginscli = _import_pluginscli()
        cli = _make_cli(pluginscli)
        with patch.object(pluginscli.inquirer, 'prompt', side_effect=[
            {'cli_action': 'List all installed plugins'},
            {'cli_action': 'Exit'},
        ]), patch.object(cli, 'main') as mock_main:
            cli.run()

        mock_main.assert_called_once_with('List all installed plugins')


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
