#!/usr/bin/env python3

import json
import os
import tempfile

import pytest

from compresso import config
from compresso.libs.singleton import SingletonType
from compresso.libs.startup import StartupState, validate_startup_environment


def reset_singletons():
    SingletonType._instances.pop(config.Config, None)
    SingletonType._instances.pop(StartupState, None)


@pytest.mark.unittest
def test_safe_defaults_enabled_by_default():
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix='compresso_tests_config_')

    settings = config.Config(config_path=config_path)

    assert settings.get_large_library_safe_defaults() is True
    assert settings.get_default_worker_cap() == 2
    assert settings.get_number_of_workers() == 2


@pytest.mark.unittest
def test_safe_defaults_can_be_disabled_from_config_file():
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix='compresso_tests_config_')
    with open(os.path.join(config_path, 'settings.json'), 'w') as infile:
        json.dump({
            'large_library_safe_defaults': False,
            'number_of_workers': None,
        }, infile)

    settings = config.Config(config_path=config_path)

    assert settings.get_large_library_safe_defaults() is False
    assert settings.get_number_of_workers() is None


@pytest.mark.unittest
def test_settings_file_overrides_environment_but_constructor_args_override_both(monkeypatch):
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix='compresso_tests_config_')
    with open(os.path.join(config_path, 'settings.json'), 'w') as infile:
        json.dump({
            'ui_port': 9001,
            'enable_library_scanner': True,
        }, infile)

    monkeypatch.setenv('ui_port', '9000')

    settings = config.Config(config_path=config_path, port=9002)

    assert settings.get_ui_port() == 9002
    assert settings.get_enable_library_scanner() is True


@pytest.mark.unittest
def test_safe_defaults_only_fill_unset_values():
    reset_singletons()
    config_path = tempfile.mkdtemp(prefix='compresso_tests_config_')
    with open(os.path.join(config_path, 'settings.json'), 'w') as infile:
        json.dump({
            'number_of_workers': 6,
            'concurrent_file_testers': 4,
        }, infile)

    settings = config.Config(config_path=config_path)

    assert settings.get_number_of_workers() == 6
    assert settings.get_concurrent_file_testers() == 4


@pytest.mark.unittest
def test_validate_startup_environment_rejects_missing_library():
    reset_singletons()
    base_dir = tempfile.mkdtemp(prefix='compresso_tests_startup_')
    config_dir = os.path.join(base_dir, 'config')
    cache_dir = os.path.join(base_dir, 'cache')
    missing_library = os.path.join(base_dir, 'library')

    settings = config.Config(config_path=config_dir)
    settings.set_config_item('cache_path', cache_dir, save_settings=False)
    settings.set_config_item('library_path', missing_library, save_settings=False)

    with pytest.raises(RuntimeError, match="library path"):
        validate_startup_environment(settings)


@pytest.mark.unittest
def test_validate_startup_environment_rejects_invalid_cache_path():
    reset_singletons()
    base_dir = tempfile.mkdtemp(prefix='compresso_tests_startup_')
    config_dir = os.path.join(base_dir, 'config')
    library_dir = os.path.join(base_dir, 'library')
    os.makedirs(library_dir, exist_ok=True)

    settings = config.Config(config_path=config_dir)
    settings.set_config_item('library_path', library_dir, save_settings=False)
    settings.set_config_item('cache_path', os.path.abspath(os.sep), save_settings=False)

    with pytest.raises(RuntimeError, match="cache path"):
        validate_startup_environment(settings)


@pytest.mark.unittest
def test_startup_readiness_requires_all_stages():
    reset_singletons()
    startup_state = StartupState()
    startup_state.reset()

    for stage in StartupState.REQUIRED_STAGES:
        startup_state.mark_ready(stage, detail=stage)

    snapshot = startup_state.snapshot()

    assert snapshot['ready'] is True
    assert all(snapshot['stages'].values())


@pytest.mark.unittest
def test_startup_readiness_reports_errors():
    reset_singletons()
    startup_state = StartupState()
    startup_state.reset()
    startup_state.mark_ready('config_loaded', detail='ok')
    startup_state.mark_error('ui_server_ready', 'bind failed')

    snapshot = startup_state.snapshot()

    assert snapshot['ready'] is False
    assert snapshot['stages']['ui_server_ready'] is False
    assert snapshot['errors'][0]['stage'] == 'ui_server_ready'
