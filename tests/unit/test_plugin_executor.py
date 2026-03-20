#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_plugin_executor.py

    Unit tests for compresso.libs.unplugins.executor.PluginExecutor.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, mock_open

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture
def mock_logger():
    with patch('compresso.libs.unplugins.executor.CompressoLogging') as mock_logging:
        mock_logging.get_logger.return_value = MagicMock()
        yield mock_logging


@pytest.fixture
def executor(mock_logger):
    with patch('compresso.libs.unplugins.executor.common') as mock_common:
        mock_common.get_home_dir.return_value = '/fake/home'
        from compresso.libs.unplugins.executor import PluginExecutor
        return PluginExecutor()


@pytest.fixture
def executor_custom_dir(mock_logger):
    from compresso.libs.unplugins.executor import PluginExecutor
    return PluginExecutor(plugins_directory='/custom/plugins')


@pytest.mark.unittest
class TestPluginExecutorInit:

    def test_init_default_plugins_directory(self, mock_logger):
        with patch('compresso.libs.unplugins.executor.common') as mock_common:
            mock_common.get_home_dir.return_value = '/fake/home'
            from compresso.libs.unplugins.executor import PluginExecutor
            pe = PluginExecutor()
            expected = os.path.join('/fake/home', '.compresso', 'plugins')
            assert pe.plugins_directory == expected

    def test_init_custom_plugins_directory(self, executor_custom_dir):
        assert executor_custom_dir.plugins_directory == '/custom/plugins'

    def test_init_sets_plugin_types_list(self, executor):
        assert isinstance(executor.plugin_types, list)
        assert len(executor.plugin_types) > 0
        for pt in executor.plugin_types:
            assert 'id' in pt
            assert 'has_flow' in pt


@pytest.mark.unittest
class TestGetPluginDirectory:

    def test_returns_path_string(self, executor):
        result = executor._PluginExecutor__get_plugin_directory('my_plugin')
        assert result == os.path.join(executor.plugins_directory, 'my_plugin')

    def test_different_plugin_ids(self, executor):
        r1 = executor._PluginExecutor__get_plugin_directory('plugin_a')
        r2 = executor._PluginExecutor__get_plugin_directory('plugin_b')
        assert r1 != r2
        assert r1.endswith('plugin_a')
        assert r2.endswith('plugin_b')


@pytest.mark.unittest
class TestGetAllPluginTypes:

    def test_returns_list(self, executor):
        result = executor.get_all_plugin_types()
        assert isinstance(result, list)

    def test_contains_worker_process(self, executor):
        ids = [pt['id'] for pt in executor.get_all_plugin_types()]
        assert 'worker.process' in ids

    def test_contains_expected_keys(self, executor):
        for pt in executor.get_all_plugin_types():
            assert 'id' in pt
            assert 'has_flow' in pt


@pytest.mark.unittest
class TestGetAllPluginTypesInPlugin:

    def test_returns_plugin_types_for_module(self, executor):
        mock_module = MagicMock()
        mock_module.on_worker_process = MagicMock()

        mock_type_meta = MagicMock()
        mock_type_meta.plugin_runner.return_value = 'on_worker_process'

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'get_plugin_type_meta', return_value=mock_type_meta):
            result = executor.get_all_plugin_types_in_plugin('test_plugin')
            assert isinstance(result, list)

    def test_returns_empty_when_no_runners(self, executor):
        mock_module = MagicMock(spec=[])

        mock_type_meta = MagicMock()
        mock_type_meta.plugin_runner.return_value = 'nonexistent_runner'

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'get_plugin_type_meta', return_value=mock_type_meta):
            result = executor.get_all_plugin_types_in_plugin('test_plugin')
            assert result == []


@pytest.mark.unittest
class TestExecutePluginRunner:

    def test_success_returns_true(self, executor):
        mock_runner = MagicMock()
        mock_module = MagicMock()
        mock_module.on_worker_process = mock_runner

        mock_type_meta = MagicMock()
        mock_type_meta.plugin_runner.return_value = 'on_worker_process'

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'get_plugin_type_meta', return_value=mock_type_meta), \
             patch('compresso.libs.unplugins.executor.TaskDataStore'), \
             patch('compresso.libs.unplugins.executor.CompressoFileMetadata'):
            data = {'path': '/test/file.mkv'}
            result = executor.execute_plugin_runner(data, 'test_plugin', 'worker.process')
            assert result is True

    def test_returns_false_when_no_module(self, executor):
        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=None):
            data = {'path': '/test/file.mkv'}
            result = executor.execute_plugin_runner(data, 'test_plugin', 'worker.process')
            assert result is False

    def test_returns_false_when_no_runner(self, executor):
        mock_module = MagicMock(spec=[])

        mock_type_meta = MagicMock()
        mock_type_meta.plugin_runner.return_value = 'nonexistent_runner'

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'get_plugin_type_meta', return_value=mock_type_meta), \
             patch('compresso.libs.unplugins.executor.TaskDataStore'), \
             patch('compresso.libs.unplugins.executor.CompressoFileMetadata'):
            data = {'path': '/test/file.mkv'}
            result = executor.execute_plugin_runner(data, 'test_plugin', 'worker.process')
            assert result is False

    def test_returns_false_on_exception(self, executor):
        mock_runner = MagicMock(side_effect=Exception("test error"))
        mock_module = MagicMock()
        mock_module.on_worker_process = mock_runner

        mock_type_meta = MagicMock()
        mock_type_meta.plugin_runner.return_value = 'on_worker_process'

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'get_plugin_type_meta', return_value=mock_type_meta), \
             patch('compresso.libs.unplugins.executor.TaskDataStore'), \
             patch('compresso.libs.unplugins.executor.CompressoFileMetadata'):
            data = {'path': '/test/file.mkv'}
            result = executor.execute_plugin_runner(data, 'test_plugin', 'worker.process')
            assert result is False


@pytest.mark.unittest
class TestGetPluginSettings:

    def test_returns_settings_and_form(self, executor):
        mock_settings_instance = MagicMock()
        mock_settings_instance.get_form_settings.return_value = {'form': 'data'}
        mock_settings_instance.get_setting.return_value = {'key1': 'val1'}

        mock_module = MagicMock()
        mock_module.Settings.return_value = mock_settings_instance

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module):
            settings, form = executor.get_plugin_settings('test_plugin')
            assert settings == {'key1': 'val1'}
            assert form == {'form': 'data'}

    def test_returns_empty_when_no_settings_class(self, executor):
        mock_module = MagicMock(spec=[])

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module):
            settings, form = executor.get_plugin_settings('test_plugin')
            assert settings == {}
            assert form == {}

    def test_with_library_id(self, executor):
        mock_settings_instance = MagicMock()
        mock_settings_instance.get_form_settings.return_value = {}
        mock_settings_instance.get_setting.return_value = {}

        mock_module = MagicMock()
        mock_module.Settings.return_value = mock_settings_instance

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module):
            executor.get_plugin_settings('test_plugin', library_id=5)
            mock_module.Settings.assert_called_once_with(library_id=5)


@pytest.mark.unittest
class TestSavePluginSettings:

    def test_save_success(self, executor):
        mock_settings_instance = MagicMock()
        mock_settings_instance.set_setting.return_value = True

        mock_module = MagicMock()
        mock_module.Settings.return_value = mock_settings_instance

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'reload_plugin_module'):
            result = executor.save_plugin_settings('test_plugin', {'key1': 'val1'})
            assert result is True

    def test_save_failure(self, executor):
        mock_settings_instance = MagicMock()
        mock_settings_instance.set_setting.return_value = False

        mock_module = MagicMock()
        mock_module.Settings.return_value = mock_settings_instance

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'reload_plugin_module'):
            result = executor.save_plugin_settings('test_plugin', {'key1': 'val1'})
            assert result is False

    def test_save_with_library_id(self, executor):
        mock_settings_instance = MagicMock()
        mock_settings_instance.set_setting.return_value = True

        mock_module = MagicMock()
        mock_module.Settings.return_value = mock_settings_instance

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'reload_plugin_module'):
            executor.save_plugin_settings('test_plugin', {'k': 'v'}, library_id=3)
            mock_module.Settings.assert_called_once_with(library_id=3)


@pytest.mark.unittest
class TestResetPluginSettings:

    def test_reset_success(self, executor):
        mock_settings_instance = MagicMock()
        mock_settings_instance.reset_settings_to_defaults.return_value = True

        mock_module = MagicMock()
        mock_module.Settings.return_value = mock_settings_instance

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module):
            result = executor.reset_plugin_settings('test_plugin')
            assert result is True

    def test_reset_with_library_id(self, executor):
        mock_settings_instance = MagicMock()
        mock_settings_instance.reset_settings_to_defaults.return_value = True

        mock_module = MagicMock()
        mock_module.Settings.return_value = mock_settings_instance

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module):
            result = executor.reset_plugin_settings('test_plugin', library_id=2)
            assert result is True
            mock_module.Settings.assert_called_once_with(library_id=2)


@pytest.mark.unittest
class TestGetPluginChangelog:

    def test_returns_lines_when_file_exists(self, executor):
        changelog_content = "# v1.0\n- Initial release\n"
        with patch('compresso.libs.unplugins.executor.os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=changelog_content)):
            result = executor.get_plugin_changelog('test_plugin')
            assert isinstance(result, list)
            assert len(result) > 0

    def test_returns_empty_when_no_file(self, executor):
        with patch('compresso.libs.unplugins.executor.os.path.exists', return_value=False):
            result = executor.get_plugin_changelog('test_plugin')
            assert result == []


@pytest.mark.unittest
class TestGetPluginLongDescription:

    def test_returns_lines_when_file_exists(self, executor):
        desc_content = "# My Plugin\nThis does things.\n"
        with patch('compresso.libs.unplugins.executor.os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=desc_content)):
            result = executor.get_plugin_long_description('test_plugin')
            assert isinstance(result, list)
            assert len(result) > 0

    def test_returns_empty_when_no_file(self, executor):
        with patch('compresso.libs.unplugins.executor.os.path.exists', return_value=False):
            result = executor.get_plugin_long_description('test_plugin')
            assert result == []


@pytest.mark.unittest
class TestTestPluginRunner:

    def test_returns_errors_list(self, executor):
        mock_module = MagicMock()
        mock_type_meta = MagicMock()
        mock_type_meta.get_test_data.return_value = {'test': 'data'}
        mock_type_meta.modify_test_data.return_value = {'test': 'data'}
        mock_type_meta.run_data_schema_tests.return_value = []

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'get_plugin_type_meta', return_value=mock_type_meta):
            errors = executor.test_plugin_runner('test_plugin', 'worker.process')
            assert errors == []

    def test_returns_errors_on_exception(self, executor):
        with patch.object(executor, '_PluginExecutor__load_plugin_module', side_effect=Exception("fail")):
            errors = executor.test_plugin_runner('test_plugin', 'worker.process')
            assert len(errors) == 1
            assert 'Exception' in errors[0]


@pytest.mark.unittest
class TestTestPluginSettings:

    def test_returns_errors_and_settings(self, executor):
        with patch.object(executor, 'get_plugin_settings', return_value=({'key': 'val'}, {})):
            errors, settings = executor.test_plugin_settings('test_plugin')
            assert errors == []
            assert settings == {'key': 'val'}

    def test_catches_exception(self, executor):
        with patch.object(executor, 'get_plugin_settings', side_effect=Exception("bad")):
            errors, settings = executor.test_plugin_settings('test_plugin')
            assert len(errors) == 1
            assert settings == {}


@pytest.mark.unittest
class TestBuildPluginDataFromPluginListFilteredByPluginType:

    def test_filters_plugins_by_type(self, executor):
        mock_module = MagicMock()
        mock_module.on_worker_process = MagicMock()

        mock_type_meta = MagicMock()
        mock_type_meta.plugin_runner.return_value = 'on_worker_process'

        plugins_list = [
            {
                'plugin_id': 'test_plugin',
                'name': 'Test Plugin',
                'author': 'Test',
                'version': '1.0',
                'icon': '',
                'description': 'A test',
            }
        ]

        with patch.object(executor, '_PluginExecutor__load_plugin_module', return_value=mock_module), \
             patch.object(executor, 'get_plugin_type_meta', return_value=mock_type_meta), \
             patch('compresso.libs.unplugins.executor.plugin_types') as mock_pt:
            mock_pt.get_all_plugin_types.return_value = {'worker.process': {}}
            result = executor.build_plugin_data_from_plugin_list_filtered_by_plugin_type(
                plugins_list, 'worker.process'
            )
            assert len(result) == 1
            assert result[0]['plugin_id'] == 'test_plugin'

    def test_returns_empty_for_invalid_type(self, executor):
        with patch('compresso.libs.unplugins.executor.plugin_types') as mock_pt:
            mock_pt.get_all_plugin_types.return_value = {}
            result = executor.build_plugin_data_from_plugin_list_filtered_by_plugin_type(
                [], 'invalid.type'
            )
            assert result == []
