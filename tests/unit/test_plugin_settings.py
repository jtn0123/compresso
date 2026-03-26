#!/usr/bin/env python3

"""
    tests.unit.test_plugin_settings.py

    Unit tests for compresso.libs.unplugins.settings.PluginSettings.
"""

import json
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


class FakeSettings:
    """A concrete subclass of PluginSettings for testing."""


def _make_settings_class(**kwargs):
    """Create a PluginSettings subclass with given settings/form_settings."""
    from compresso.libs.unplugins.settings import PluginSettings

    class TestSettings(PluginSettings):
        settings = kwargs.get('settings', {'opt1': 'default1', 'opt2': 42})
        form_settings = kwargs.get('form_settings', {'display': 'input'})

    # Fake out __module__ so get_plugin_directory works
    TestSettings.__module__ = 'fake_plugin.plugin'
    return TestSettings


@pytest.mark.unittest
class TestPluginSettingsInit:

    def test_init_no_library_id(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            assert instance.library_id is None

    def test_init_with_library_id_int(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls(library_id=5)
            assert instance.library_id == 5

    def test_init_with_library_id_string(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls(library_id='10')
            assert instance.library_id == 10

    def test_init_with_invalid_library_id_raises(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            with pytest.raises(Exception, match="Library ID needs to be an integer"):
                cls(library_id='not_a_number')


@pytest.mark.unittest
class TestGetPluginDirectory:

    def test_returns_directory_path(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            # Mock the module file location
            fake_module = MagicMock()
            fake_module.__file__ = os.path.join('/plugins', 'my_plugin', 'plugin.py')
            with patch.dict('sys.modules', {'fake_plugin.plugin': fake_module}):
                result = instance.get_plugin_directory()
                assert os.path.basename(result) == 'my_plugin'


@pytest.mark.unittest
class TestGetProfileDirectory:

    def test_returns_userdata_path(self):
        cls = _make_settings_class()
        mock_config = MagicMock()
        mock_config_instance = MagicMock()
        mock_config_instance.get_userdata_path.return_value = '/userdata'
        mock_config.return_value = mock_config_instance

        with patch('compresso.libs.unplugins.settings.config') as cfg:
            cfg.Config = mock_config
            instance = cls()
            fake_module = MagicMock()
            fake_module.__file__ = '/plugins/my_plugin/plugin.py'
            with patch.dict('sys.modules', {'fake_plugin.plugin': fake_module}), \
                 patch('os.path.exists', return_value=True):
                result = instance.get_profile_directory()
                assert 'my_plugin' in result


@pytest.mark.unittest
class TestGetFormSettings:

    def test_returns_form_settings_dict(self):
        cls = _make_settings_class(form_settings={'field1': 'text'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            result = instance.get_form_settings()
            assert result == {'field1': 'text'}


@pytest.mark.unittest
class TestGetSetting:

    def test_returns_all_settings_when_key_is_none(self):
        cls = _make_settings_class(settings={'opt1': 'val1', 'opt2': 'val2'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            # Mock the import of configured settings
            settings_data = json.dumps({'opt1': 'configured1', 'opt2': 'configured2'})
            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', return_value=True), \
                 patch('builtins.open', mock_open(read_data=settings_data)):
                result = instance.get_setting()
                assert isinstance(result, dict)
                assert 'opt1' in result

    def test_returns_specific_key(self):
        cls = _make_settings_class(settings={'opt1': 'val1'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            settings_data = json.dumps({'opt1': 'configured1'})
            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', return_value=True), \
                 patch('builtins.open', mock_open(read_data=settings_data)):
                result = instance.get_setting(key='opt1')
                assert result == 'configured1'

    def test_handles_json_decode_error(self):
        cls = _make_settings_class(settings={'opt1': 'default'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', return_value=True), \
                 patch('builtins.open', mock_open(read_data='not json{')):
                # Should not raise, falls back to defaults
                result = instance.get_setting()
                assert result is not None


@pytest.mark.unittest
class TestSetSetting:

    def test_set_valid_key(self):
        cls = _make_settings_class(settings={'opt1': 'default'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            settings_data = json.dumps({'opt1': 'default'})
            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', return_value=True), \
                 patch('builtins.open', mock_open(read_data=settings_data)):
                result = instance.set_setting('opt1', 'new_value')
                assert result is True

    def test_set_invalid_key_returns_false(self):
        cls = _make_settings_class(settings={'opt1': 'default'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            settings_data = json.dumps({'opt1': 'default'})
            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', return_value=True), \
                 patch('builtins.open', mock_open(read_data=settings_data)):
                result = instance.set_setting('nonexistent', 'value')
                assert result is False


@pytest.mark.unittest
class TestGetDefaultSetting:

    def test_returns_all_defaults(self):
        cls = _make_settings_class(settings={'opt1': 'def1', 'opt2': 'def2'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            result = instance.get_default_setting()
            assert result == {'opt1': 'def1', 'opt2': 'def2'}

    def test_returns_single_default(self):
        cls = _make_settings_class(settings={'opt1': 'def1'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            result = instance.get_default_setting(key='opt1')
            assert result == 'def1'

    def test_returns_none_for_missing_key(self):
        cls = _make_settings_class(settings={'opt1': 'def1'})
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            result = instance.get_default_setting(key='missing')
            assert result is None


@pytest.mark.unittest
class TestResetSettingsToDefaults:

    def test_reset_removes_file(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', side_effect=[True, True, False]), \
                 patch('os.path.basename', return_value='settings.json'), \
                 patch('os.remove') as mock_remove:
                result = instance.reset_settings_to_defaults()
                assert result is True
                mock_remove.assert_called_once()

    def test_reset_library_with_no_library_file_returns_false(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls(library_id=5)
            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', side_effect=[False, False, False]), \
                 patch('os.path.basename', return_value='settings.json'):
                result = instance.reset_settings_to_defaults()
                assert result is False


@pytest.mark.unittest
class TestSettingsFilePath:

    def test_global_settings_path(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls()
            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', return_value=False):
                path = instance._PluginSettings__get_plugin_settings_file()
                assert path.endswith('settings.json')
                assert 'fake' in path and 'profile' in path

    def test_library_specific_settings_path(self):
        cls = _make_settings_class()
        with patch('compresso.libs.unplugins.settings.config'):
            instance = cls(library_id=7)

            def fake_exists(p):
                # The migration check: profile/settings.json exists, plugin/settings.json does not
                # Then library-specific settings.7.json exists
                if 'settings.7.json' in p:
                    return True
                if p.endswith('settings.json'):
                    return True
                return False

            with patch.object(instance, 'get_plugin_directory', return_value='/fake/plugin'), \
                 patch.object(instance, 'get_profile_directory', return_value='/fake/profile'), \
                 patch('os.path.exists', side_effect=fake_exists):
                path = instance._PluginSettings__get_plugin_settings_file()
                assert 'settings.7.json' in path
