#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_bundled_plugins.py

    Unit tests for compresso/bundled_plugins/__init__.py:
    - install_bundled_plugins: happy path, exception handling, no plugins to install
    - _version_newer: semver comparisons
    - _copy_plugin: file copying, settings preservation during updates
    - _register_plugin_in_db: database registration
"""

import json
import os
import shutil
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from compresso.bundled_plugins import (
    install_bundled_plugins,
    _version_newer,
    _copy_plugin,
    _register_plugin_in_db,
)


# ------------------------------------------------------------------
# _version_newer
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestVersionNewer:

    def test_returns_true_for_higher_major(self):
        assert _version_newer('2.0.0', '1.0.0') is True

    def test_returns_true_for_higher_minor(self):
        assert _version_newer('1.2.0', '1.1.0') is True

    def test_returns_true_for_higher_patch(self):
        assert _version_newer('1.0.2', '1.0.1') is True

    def test_returns_false_for_equal_versions(self):
        assert _version_newer('1.0.0', '1.0.0') is False

    def test_returns_false_for_lower_major(self):
        assert _version_newer('1.0.0', '2.0.0') is False

    def test_returns_false_for_lower_minor(self):
        assert _version_newer('1.1.0', '1.2.0') is False

    def test_returns_false_for_lower_patch(self):
        assert _version_newer('1.0.1', '1.0.2') is False

    def test_zero_version_is_not_newer_than_zero(self):
        assert _version_newer('0.0.0', '0.0.0') is False

    def test_any_version_is_newer_than_zero(self):
        assert _version_newer('0.0.1', '0.0.0') is True

    def test_returns_true_for_higher_major_despite_lower_minor(self):
        assert _version_newer('2.0.0', '1.9.9') is True

    def test_returns_false_for_lower_major_despite_higher_minor(self):
        assert _version_newer('1.9.9', '2.0.0') is False

    def test_handles_invalid_new_version_string(self):
        # Invalid version parses to [0], so not newer than 1.0.0
        assert _version_newer('invalid', '1.0.0') is False

    def test_handles_invalid_old_version_string(self):
        # Old version parses to [0], so 1.0.0 is newer
        assert _version_newer('1.0.0', 'invalid') is True

    def test_handles_both_versions_invalid(self):
        # Both parse to [0], so equal — not newer
        assert _version_newer('bad', 'also_bad') is False

    def test_handles_none_new_version(self):
        # AttributeError on None.split() falls back to [0]
        assert _version_newer(None, '1.0.0') is False

    def test_handles_none_old_version(self):
        assert _version_newer('1.0.0', None) is True

    def test_single_digit_versions(self):
        # "2" parses to [2], "1" parses to [1]
        assert _version_newer('2', '1') is True

    def test_different_length_versions(self):
        # [1, 0, 0, 1] > [1, 0, 0]
        assert _version_newer('1.0.0.1', '1.0.0') is True


# ------------------------------------------------------------------
# _copy_plugin
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCopyPlugin:

    def test_copies_plugin_to_new_directory(self):
        """Fresh install: source is copied to a non-existent target."""
        source = tempfile.mkdtemp(prefix='bp_src_')
        target = os.path.join(tempfile.mkdtemp(prefix='bp_parent_'), 'target_plugin')
        try:
            # Create source files
            with open(os.path.join(source, 'plugin.py'), 'w') as f:
                f.write('# plugin code')
            with open(os.path.join(source, 'info.json'), 'w') as f:
                json.dump({'id': 'test', 'version': '1.0.0'}, f)

            _copy_plugin(source, target)

            assert os.path.isdir(target)
            assert os.path.exists(os.path.join(target, 'plugin.py'))
            assert os.path.exists(os.path.join(target, 'info.json'))
        finally:
            shutil.rmtree(source, ignore_errors=True)
            shutil.rmtree(os.path.dirname(target), ignore_errors=True)

    def test_preserves_settings_files_during_update(self):
        """Update: user settings files are preserved across the copy."""
        source = tempfile.mkdtemp(prefix='bp_src_')
        target = tempfile.mkdtemp(prefix='bp_tgt_')
        try:
            # Create source files (new version)
            with open(os.path.join(source, 'plugin.py'), 'w') as f:
                f.write('# new plugin code')
            with open(os.path.join(source, 'info.json'), 'w') as f:
                json.dump({'id': 'test', 'version': '2.0.0'}, f)

            # Create existing target with user settings
            with open(os.path.join(target, 'plugin.py'), 'w') as f:
                f.write('# old plugin code')
            user_settings = {'custom_key': 'custom_value'}
            with open(os.path.join(target, 'settings.json'), 'w') as f:
                json.dump(user_settings, f)
            with open(os.path.join(target, 'settings_library1.json'), 'w') as f:
                json.dump({'library': 'config'}, f)

            _copy_plugin(source, target)

            # Plugin code should be updated
            with open(os.path.join(target, 'plugin.py')) as f:
                assert f.read() == '# new plugin code'

            # Settings files should be preserved
            with open(os.path.join(target, 'settings.json')) as f:
                assert json.load(f) == user_settings
            with open(os.path.join(target, 'settings_library1.json')) as f:
                assert json.load(f) == {'library': 'config'}
        finally:
            shutil.rmtree(source, ignore_errors=True)
            shutil.rmtree(target, ignore_errors=True)

    def test_non_settings_files_are_not_preserved(self):
        """Files that do not match settings*.json are replaced, not preserved."""
        source = tempfile.mkdtemp(prefix='bp_src_')
        target = tempfile.mkdtemp(prefix='bp_tgt_')
        try:
            with open(os.path.join(source, 'plugin.py'), 'w') as f:
                f.write('# new')

            # Old target has a non-settings file
            with open(os.path.join(target, 'old_data.txt'), 'w') as f:
                f.write('should be removed')
            with open(os.path.join(target, 'plugin.py'), 'w') as f:
                f.write('# old')

            _copy_plugin(source, target)

            assert not os.path.exists(os.path.join(target, 'old_data.txt'))
            with open(os.path.join(target, 'plugin.py')) as f:
                assert f.read() == '# new'
        finally:
            shutil.rmtree(source, ignore_errors=True)
            shutil.rmtree(target, ignore_errors=True)

    def test_files_not_matching_settings_pattern_are_not_preserved(self):
        """Only files matching settings*.json are preserved, not other json files."""
        source = tempfile.mkdtemp(prefix='bp_src_')
        target = tempfile.mkdtemp(prefix='bp_tgt_')
        try:
            with open(os.path.join(source, 'plugin.py'), 'w') as f:
                f.write('# new')

            # A json file that does not start with 'settings'
            with open(os.path.join(target, 'config.json'), 'w') as f:
                json.dump({'old': True}, f)

            _copy_plugin(source, target)

            assert not os.path.exists(os.path.join(target, 'config.json'))
        finally:
            shutil.rmtree(source, ignore_errors=True)
            shutil.rmtree(target, ignore_errors=True)


# ------------------------------------------------------------------
# _register_plugin_in_db
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestRegisterPluginInDb:

    @patch('compresso.bundled_plugins.Plugins', create=True)
    def test_inserts_new_plugin(self, mock_plugins_cls):
        """When plugin does not exist, it should be inserted."""
        # Patch the import inside _register_plugin_in_db
        mock_plugins = MagicMock()
        mock_plugins.get_or_none.return_value = None

        plugin_info = {
            'id': 'test_plugin',
            'name': 'Test Plugin',
            'author': 'Tester',
            'version': '1.0.0',
            'tags': 'test,unit',
            'description': 'A test plugin',
            'icon': 'icon.png',
        }

        with patch('compresso.bundled_plugins._register_plugin_in_db.__module__', 'compresso.bundled_plugins'):
            with patch.dict('sys.modules', {}):
                with patch(
                    'compresso.libs.unmodels.plugins.Plugins'
                ) as mock_db_plugins:
                    mock_db_plugins.get_or_none.return_value = None
                    _register_plugin_in_db(plugin_info, '/plugins/test_plugin')
                    mock_db_plugins.insert.assert_called_once()
                    mock_db_plugins.insert.return_value.execute.assert_called_once()

    @patch('compresso.libs.unmodels.plugins.Plugins')
    def test_updates_existing_plugin(self, mock_db_plugins):
        """When plugin already exists, it should be updated."""
        mock_db_plugins.get_or_none.return_value = MagicMock()  # existing record

        plugin_info = {
            'id': 'test_plugin',
            'name': 'Test Plugin',
            'author': 'Tester',
            'version': '2.0.0',
            'tags': 'test',
            'description': 'Updated plugin',
            'icon': '',
        }
        _register_plugin_in_db(plugin_info, '/plugins/test_plugin')
        mock_db_plugins.update.assert_called_once()
        (mock_db_plugins.update.return_value
         .where.return_value
         .execute.assert_called_once())

    @patch('compresso.libs.unmodels.plugins.Plugins')
    def test_handles_missing_info_fields_gracefully(self, mock_db_plugins):
        """Missing fields in plugin_info should default to empty strings."""
        mock_db_plugins.get_or_none.return_value = None

        plugin_info = {'id': 'minimal_plugin'}
        _register_plugin_in_db(plugin_info, '/plugins/minimal_plugin')
        mock_db_plugins.insert.assert_called_once()

    @patch('compresso.libs.unmodels.plugins.Plugins')
    def test_catches_database_exception_without_raising(self, mock_db_plugins):
        """Database errors should be caught and logged, not raised."""
        mock_db_plugins.get_or_none.side_effect = Exception('DB connection failed')

        plugin_info = {'id': 'broken_plugin'}
        # Should not raise
        _register_plugin_in_db(plugin_info, '/plugins/broken_plugin')

    @patch('compresso.bundled_plugins.logger')
    @patch('compresso.libs.unmodels.plugins.Plugins')
    def test_logs_warning_on_database_exception(self, mock_db_plugins, mock_logger):
        """Database errors should produce a warning log."""
        mock_db_plugins.get_or_none.side_effect = Exception('DB error')

        plugin_info = {'id': 'error_plugin'}
        _register_plugin_in_db(plugin_info, '/plugins/error_plugin')
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert 'Could not register' in warning_msg


# ------------------------------------------------------------------
# install_bundled_plugins
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestInstallBundledPlugins:

    def test_creates_plugins_directory_if_missing(self):
        """If the plugins_path does not exist, it should be created."""
        plugins_path = os.path.join(tempfile.mkdtemp(prefix='bp_'), 'plugins')
        try:
            assert not os.path.exists(plugins_path)
            with patch('compresso.bundled_plugins.os.listdir', return_value=[]):
                install_bundled_plugins(plugins_path)
            assert os.path.isdir(plugins_path)
        finally:
            shutil.rmtree(os.path.dirname(plugins_path), ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_installs_new_plugin_when_target_missing(self, mock_copy, mock_register):
        """A bundled plugin should be installed when not present in target."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')
        plugin_name = 'my_plugin'
        plugin_dir = os.path.join(source_dir, plugin_name)
        os.makedirs(plugin_dir)

        info = {'id': 'my_plugin', 'name': 'My Plugin', 'version': '1.0.0'}
        with open(os.path.join(plugin_dir, 'info.json'), 'w') as f:
            json.dump(info, f)

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            mock_copy.assert_called_once_with(
                plugin_dir,
                os.path.join(plugins_path, 'my_plugin'),
            )
            mock_register.assert_called_once_with(
                info,
                os.path.join(plugins_path, 'my_plugin'),
            )
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_installs_when_bundled_version_is_newer(self, mock_copy, mock_register):
        """A bundled plugin should be installed when its version is newer."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')
        plugin_name = 'upgradeable'
        plugin_dir = os.path.join(source_dir, plugin_name)
        os.makedirs(plugin_dir)

        new_info = {'id': 'upgradeable', 'version': '2.0.0'}
        with open(os.path.join(plugin_dir, 'info.json'), 'w') as f:
            json.dump(new_info, f)

        # Create existing older version in target
        target_dir = os.path.join(plugins_path, 'upgradeable')
        os.makedirs(target_dir)
        old_info = {'id': 'upgradeable', 'version': '1.0.0'}
        with open(os.path.join(target_dir, 'info.json'), 'w') as f:
            json.dump(old_info, f)

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            mock_copy.assert_called_once()
            mock_register.assert_called_once()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_skips_when_bundled_version_is_not_newer(self, mock_copy, mock_register):
        """A bundled plugin should NOT be installed when the existing version is the same or newer."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')
        plugin_name = 'current'
        plugin_dir = os.path.join(source_dir, plugin_name)
        os.makedirs(plugin_dir)

        info = {'id': 'current', 'version': '1.0.0'}
        with open(os.path.join(plugin_dir, 'info.json'), 'w') as f:
            json.dump(info, f)

        # Create existing same-version in target
        target_dir = os.path.join(plugins_path, 'current')
        os.makedirs(target_dir)
        with open(os.path.join(target_dir, 'info.json'), 'w') as f:
            json.dump(info, f)

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            mock_copy.assert_not_called()
            mock_register.assert_not_called()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_installs_when_target_exists_but_info_json_missing(self, mock_copy, mock_register):
        """If target dir exists but has no info.json, should install."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')
        plugin_name = 'broken_target'
        plugin_dir = os.path.join(source_dir, plugin_name)
        os.makedirs(plugin_dir)

        info = {'id': 'broken_target', 'version': '1.0.0'}
        with open(os.path.join(plugin_dir, 'info.json'), 'w') as f:
            json.dump(info, f)

        # Create target dir without info.json
        target_dir = os.path.join(plugins_path, 'broken_target')
        os.makedirs(target_dir)

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            mock_copy.assert_called_once()
            mock_register.assert_called_once()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_skips_non_directory_entries(self, mock_copy, mock_register):
        """Regular files in BUNDLED_PLUGINS_DIR should be skipped."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')

        # Create a regular file (not a directory)
        with open(os.path.join(source_dir, '__init__.py'), 'w') as f:
            f.write('# module init')

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            mock_copy.assert_not_called()
            mock_register.assert_not_called()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_skips_directory_without_info_json(self, mock_copy, mock_register):
        """A subdirectory without info.json should be skipped."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')
        # Create a subdirectory without info.json
        os.makedirs(os.path.join(source_dir, 'no_info_plugin'))

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            mock_copy.assert_not_called()
            mock_register.assert_not_called()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_uses_entry_name_when_id_missing_from_info(self, mock_copy, mock_register):
        """When info.json has no 'id', the directory name should be used as plugin_id."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')
        plugin_name = 'fallback_name'
        plugin_dir = os.path.join(source_dir, plugin_name)
        os.makedirs(plugin_dir)

        info = {'name': 'No ID Plugin', 'version': '1.0.0'}
        with open(os.path.join(plugin_dir, 'info.json'), 'w') as f:
            json.dump(info, f)

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            # Target should use the directory name as the plugin_id
            expected_target = os.path.join(plugins_path, plugin_name)
            mock_copy.assert_called_once_with(plugin_dir, expected_target)
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_no_bundled_plugins_to_install(self, mock_copy, mock_register):
        """When BUNDLED_PLUGINS_DIR has no plugin subdirectories, nothing happens."""
        source_dir = tempfile.mkdtemp(prefix='bp_empty_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            mock_copy.assert_not_called()
            mock_register.assert_not_called()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_installs_multiple_plugins(self, mock_copy, mock_register):
        """Multiple bundled plugins should each be processed."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')

        for name in ['plugin_a', 'plugin_b']:
            pdir = os.path.join(source_dir, name)
            os.makedirs(pdir)
            with open(os.path.join(pdir, 'info.json'), 'w') as f:
                json.dump({'id': name, 'version': '1.0.0'}, f)

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            assert mock_copy.call_count == 2
            assert mock_register.call_count == 2
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)

    @patch('compresso.bundled_plugins._register_plugin_in_db')
    @patch('compresso.bundled_plugins._copy_plugin')
    def test_existing_version_defaults_to_zero_when_missing(self, mock_copy, mock_register):
        """When existing info.json has no 'version' field, it defaults to '0.0.0'."""
        source_dir = tempfile.mkdtemp(prefix='bp_src_')
        plugins_path = tempfile.mkdtemp(prefix='bp_plugins_')
        plugin_name = 'no_ver'
        plugin_dir = os.path.join(source_dir, plugin_name)
        os.makedirs(plugin_dir)

        info = {'id': 'no_ver', 'version': '1.0.0'}
        with open(os.path.join(plugin_dir, 'info.json'), 'w') as f:
            json.dump(info, f)

        # Existing target has info.json without version
        target_dir = os.path.join(plugins_path, 'no_ver')
        os.makedirs(target_dir)
        with open(os.path.join(target_dir, 'info.json'), 'w') as f:
            json.dump({'id': 'no_ver'}, f)  # no version field

        try:
            with patch(
                'compresso.bundled_plugins.BUNDLED_PLUGINS_DIR', source_dir
            ):
                install_bundled_plugins(plugins_path)

            # 1.0.0 is newer than default 0.0.0, so should install
            mock_copy.assert_called_once()
            mock_register.assert_called_once()
        finally:
            shutil.rmtree(source_dir, ignore_errors=True)
            shutil.rmtree(plugins_path, ignore_errors=True)


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
