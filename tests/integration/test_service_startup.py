#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile

import pytest

from unmanic import config
from unmanic.libs.singleton import SingletonType
from unmanic.libs.startup import StartupState
from unmanic.service import RootService


class DummyThread(object):
    def __init__(self, name):
        self.name = name
        self._alive = True

    def is_alive(self):
        return self._alive

    def stop(self):
        self._alive = False

    def join(self, timeout=None):
        self._alive = False


def reset_singletons():
    SingletonType._instances.pop(config.Config, None)
    SingletonType._instances.pop(StartupState, None)


def append_dummy_thread(service, name):
    thread = DummyThread(name)
    service.threads.append({
        'name':   name,
        'thread': thread,
    })
    return thread


@pytest.mark.integrationtest
def test_root_service_can_start_and_stop_twice_with_temp_paths(monkeypatch):
    base_dir = tempfile.mkdtemp(prefix='unmanic_tests_service_')
    config_dir = os.path.join(base_dir, 'config')
    cache_dir = os.path.join(base_dir, 'cache')
    library_dir = os.path.join(base_dir, 'library')
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(library_dir, exist_ok=True)

    def configure_settings():
        reset_singletons()
        settings = config.Config(config_path=config_dir)
        settings.set_config_item('cache_path', cache_dir, save_settings=False)
        settings.set_config_item('library_path', library_dir, save_settings=False)
        settings.set_config_item('startup_readiness_timeout_seconds', 2, save_settings=False)
        return settings

    def fake_register(self):
        return None

    def fake_post_processor(self, data_queues, task_queue):
        return append_dummy_thread(self, 'PostProcessor')

    def fake_foreman(self, data_queues, settings, task_queue):
        return append_dummy_thread(self, 'Foreman')

    def fake_handler(self, data_queues, task_queue):
        return append_dummy_thread(self, 'TaskHandler')

    def fake_library_scanner(self, data_queues):
        return append_dummy_thread(self, 'LibraryScannerManager')

    def fake_inotify(self, data_queues, settings):
        return append_dummy_thread(self, 'EventMonitorManager')

    def fake_ui_server(self, data_queues, foreman):
        StartupState().mark_ready('ui_server_ready', detail='127.0.0.1:8888')
        return append_dummy_thread(self, 'UIServer')

    def fake_scheduler(self):
        return append_dummy_thread(self, 'ScheduledTasksManager')

    def fake_resource_logger(self):
        return append_dummy_thread(self, 'RootServiceResourceLogger')

    monkeypatch.setattr(RootService, 'initial_register_unmanic', fake_register)
    monkeypatch.setattr(RootService, 'start_post_processor', fake_post_processor)
    monkeypatch.setattr(RootService, 'start_foreman', fake_foreman)
    monkeypatch.setattr(RootService, 'start_handler', fake_handler)
    monkeypatch.setattr(RootService, 'start_library_scanner_manager', fake_library_scanner)
    monkeypatch.setattr(RootService, 'start_inotify_watch_manager', fake_inotify)
    monkeypatch.setattr(RootService, 'start_ui_server', fake_ui_server)
    monkeypatch.setattr(RootService, 'start_scheduled_tasks_manager', fake_scheduler)
    monkeypatch.setattr(RootService, 'start_resource_logger', fake_resource_logger)

    for _ in range(2):
        settings = configure_settings()
        service = RootService()
        service.startup_state.reset()
        service.startup_state.mark_ready('config_loaded', detail=config_dir)
        service.startup_state.mark_ready('startup_validation', detail='validated')
        service.startup_state.mark_ready('db_ready', detail=config_dir)

        service.start_threads(settings)
        snapshot = service.wait_for_startup_readiness(settings)

        assert snapshot['ready'] is True
        service.stop_threads()
        assert service.threads == []
