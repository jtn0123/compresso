#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_config_extended.py

    Extended unit tests for compresso.config.Config.
    Covers environment variable import, settings file import,
    large library safe defaults, config dict methods, and path generation.
"""

import json
import os

import pytest
from unittest.mock import patch

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_config(tmp_path, env_vars=None, settings_data=None, **kwargs):
    """Create a Config with controlled paths and optional env/settings."""
    config_path = str(tmp_path / 'config')
    os.makedirs(config_path, exist_ok=True)

    if settings_data:
        with open(os.path.join(config_path, 'settings.json'), 'w') as f:
            json.dump(settings_data, f)

    env = env_vars or {}
    with patch.dict(os.environ, env, clear=False):
        with patch('compresso.config.common') as mock_common:
            mock_common.get_home_dir.return_value = str(tmp_path)
            mock_common.get_default_library_path.return_value = str(tmp_path / 'library')
            mock_common.get_default_cache_path.return_value = str(tmp_path / 'cache')
            mock_common.json_dump_to_file.return_value = {'success': True, 'errors': []}
            with patch('compresso.config.CompressoLogging'):
                with patch('compresso.config.metadata') as mock_meta:
                    mock_meta.read_version_string.return_value = '1.0.0-test'
                    from compresso.config import Config
                    c = Config(config_path=config_path, **kwargs)
    return c


@pytest.mark.unittest
class TestConfigInit:

    def test_default_values(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.ui_port == 8888
        assert c.debugging is False
        assert c.ssl_enabled is False

    def test_config_path_override(self, tmp_path):
        config_path = str(tmp_path / 'custom_config')
        os.makedirs(config_path, exist_ok=True)
        c = _make_config(tmp_path)
        assert c.get_config_path() is not None


@pytest.mark.unittest
class TestConfigDictMethods:

    def test_get_config_as_dict(self, tmp_path):
        c = _make_config(tmp_path)
        d = c.get_config_as_dict()
        assert isinstance(d, dict)
        assert 'ui_port' in d
        assert 'debugging' in d

    def test_get_config_keys(self, tmp_path):
        c = _make_config(tmp_path)
        keys = c.get_config_keys()
        assert 'ui_port' in keys
        assert 'config_path' in keys


@pytest.mark.unittest
class TestSetConfigItem:

    def test_set_known_key(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_config_item('ui_port', 9999, save_settings=False)
        assert c.ui_port == 9999

    def test_set_unknown_key_logs_warning(self, tmp_path):
        c = _make_config(tmp_path)
        # Should not raise, just log warning
        c.set_config_item('totally_unknown_key', 'value', save_settings=False)
        assert not hasattr(c, 'totally_unknown_key') or c.__dict__.get('totally_unknown_key') is None

    def test_set_config_item_with_setter(self, tmp_path):
        c = _make_config(tmp_path)
        with patch('compresso.config.CompressoLogging'):
            c.set_config_item('debugging', True, save_settings=False)
        assert c.debugging is True


@pytest.mark.unittest
class TestSetBulkConfigItems:

    def test_bulk_set(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_bulk_config_items({
            'ui_port': 7777,
            'follow_symlinks': False,
        }, save_settings=False)
        assert c.ui_port == 7777
        assert c.follow_symlinks is False

    def test_bulk_set_ignores_unknown(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_bulk_config_items({
            'unknown_field': 'value',
            'ui_port': 6666,
        }, save_settings=False)
        assert c.ui_port == 6666


@pytest.mark.unittest
class TestGetConfigItem:

    def test_get_existing_getter(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_config_item('ui_port') == c.ui_port

    def test_get_nonexistent_returns_none(self, tmp_path):
        c = _make_config(tmp_path)
        result = c.get_config_item('nonexistent_setting')
        assert result is None


@pytest.mark.unittest
class TestImportFromEnv:

    def test_env_override(self, tmp_path):
        c = _make_config(tmp_path, env_vars={'ui_port': '7070'})
        assert c.ui_port == '7070' or c.ui_port == 7070

    def test_env_does_not_override_non_config_keys(self, tmp_path):
        c = _make_config(tmp_path, env_vars={'RANDOM_ENV_VAR': 'nope'})
        assert not hasattr(c, 'RANDOM_ENV_VAR')


@pytest.mark.unittest
class TestImportFromFile:

    def test_settings_file_loaded(self, tmp_path):
        c = _make_config(tmp_path, settings_data={'follow_symlinks': False})
        assert c.follow_symlinks is False

    def test_missing_settings_file_ok(self, tmp_path):
        c = _make_config(tmp_path)
        # Should not raise
        assert c.ui_port == 8888


@pytest.mark.unittest
class TestLargeLibrarySafeDefaults:

    def test_safe_defaults_enabled(self, tmp_path):
        c = _make_config(tmp_path, settings_data={'large_library_safe_defaults': True})
        assert c.get_large_library_safe_defaults() is True

    def test_safe_defaults_disabled(self, tmp_path):
        c = _make_config(tmp_path, settings_data={'large_library_safe_defaults': False})
        assert c.get_large_library_safe_defaults() is False

    def test_safe_defaults_string_true(self, tmp_path):
        c = _make_config(tmp_path)
        c.large_library_safe_defaults = 'true'
        assert c.get_large_library_safe_defaults() is True

    def test_safe_defaults_string_false(self, tmp_path):
        c = _make_config(tmp_path)
        c.large_library_safe_defaults = 'false'
        assert c.get_large_library_safe_defaults() is False


@pytest.mark.unittest
class TestSSLSettings:

    def test_ssl_enabled_bool(self, tmp_path):
        c = _make_config(tmp_path)
        c.ssl_enabled = True
        assert c.get_ssl_enabled() is True

    def test_ssl_enabled_string(self, tmp_path):
        c = _make_config(tmp_path)
        c.ssl_enabled = 'true'
        assert c.get_ssl_enabled() is True
        c.ssl_enabled = 'false'
        assert c.get_ssl_enabled() is False

    def test_ssl_cert_and_key(self, tmp_path):
        c = _make_config(tmp_path)
        c.ssl_certfilepath = '/path/to/cert.pem'
        c.ssl_keyfilepath = '/path/to/key.pem'
        assert c.get_ssl_certfilepath() == '/path/to/cert.pem'
        assert c.get_ssl_keyfilepath() == '/path/to/key.pem'


@pytest.mark.unittest
class TestPathGetters:

    def test_get_log_path(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_log_path() is not None

    def test_get_plugins_path(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_plugins_path() is not None

    def test_get_userdata_path(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_userdata_path() is not None

    def test_get_cache_path(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_cache_path() is not None

    def test_set_cache_path_empty_resets(self, tmp_path):
        c = _make_config(tmp_path)
        c.get_cache_path()
        c.set_cache_path("")
        assert c.get_cache_path() != ""


@pytest.mark.unittest
class TestApprovalSettings:

    def test_approval_required_bool(self, tmp_path):
        c = _make_config(tmp_path)
        c.approval_required = False
        assert c.get_approval_required() is False

    def test_approval_required_string(self, tmp_path):
        c = _make_config(tmp_path)
        c.approval_required = 'true'
        assert c.get_approval_required() is True

    def test_staging_path_reset(self, tmp_path):
        c = _make_config(tmp_path)
        c.set_staging_path("")
        assert 'staging' in c.get_staging_path()


@pytest.mark.unittest
class TestStartupAndWorkerCap:

    def test_startup_readiness_timeout(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_startup_readiness_timeout_seconds() >= 1

    def test_default_worker_cap(self, tmp_path):
        c = _make_config(tmp_path)
        assert c.get_default_worker_cap() >= 1

    def test_worker_cap_minimum_is_1(self, tmp_path):
        c = _make_config(tmp_path)
        c.default_worker_cap = 0
        assert c.get_default_worker_cap() == 1


@pytest.mark.unittest
class TestRemoteInstallations:

    def test_get_remote_installations(self, tmp_path):
        c = _make_config(tmp_path)
        c.remote_installations = [{'address': 'http://node2'}]
        c.distributed_worker_count_target = 5
        result = c.get_remote_installations()
        assert len(result) == 1
        assert result[0]['distributed_worker_count_target'] == 5


@pytest.mark.unittest
class TestReadVersion:

    def test_read_version(self, tmp_path):
        c = _make_config(tmp_path)
        with patch('compresso.config.metadata') as mock_meta:
            mock_meta.read_version_string.return_value = '2.0.0'
            assert c.read_version() == '2.0.0'


@pytest.mark.unittest
class TestLogBufferRetention:

    def test_set_log_buffer_retention_valid(self, tmp_path):
        c = _make_config(tmp_path)
        with patch('compresso.config.CompressoLogging'):
            c.set_log_buffer_retention(7)
        assert c.log_buffer_retention == 7

    def test_set_log_buffer_retention_invalid_raises(self, tmp_path):
        c = _make_config(tmp_path)
        with pytest.raises(ValueError):
            c.set_log_buffer_retention("not_a_number")


@pytest.mark.unittest
class TestReadSystemLogs:

    def test_reads_log_file_with_context_manager(self, tmp_path):
        c = _make_config(tmp_path)
        log_dir = tmp_path / '.compresso' / 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_file = log_dir / 'compresso.log'
        log_file.write_text("line1\nline2\nline3\nline4\nline5\n")
        c.log_path = str(log_dir)
        result = c.read_system_logs()
        assert result == ['line1', 'line2', 'line3', 'line4', 'line5']

    def test_reads_limited_lines(self, tmp_path):
        c = _make_config(tmp_path)
        log_dir = tmp_path / '.compresso' / 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_file = log_dir / 'compresso.log'
        log_file.write_text("line1\nline2\nline3\nline4\nline5\n")
        c.log_path = str(log_dir)
        result = c.read_system_logs(lines=2)
        assert result == ['line4', 'line5']

    def test_reads_empty_log_file(self, tmp_path):
        c = _make_config(tmp_path)
        log_dir = tmp_path / '.compresso' / 'logs'
        os.makedirs(log_dir, exist_ok=True)
        log_file = log_dir / 'compresso.log'
        log_file.write_text("")
        c.log_path = str(log_dir)
        result = c.read_system_logs()
        assert result == []


@pytest.mark.unittest
class TestConstructorArgs:

    def test_port_override(self, tmp_path):
        c = _make_config(tmp_path, port=5555)
        assert c.ui_port == 5555

    def test_address_override(self, tmp_path):
        c = _make_config(tmp_path, address='0.0.0.0')
        assert c.ui_address == '0.0.0.0'
