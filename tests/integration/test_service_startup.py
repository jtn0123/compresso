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

    lifecycle = {
        'task_queue_ids': set(),
        'data_queue_ids': set(),
    }

    def fake_post_processor(self, data_queues, task_queue):
        lifecycle['task_queue_ids'].add(id(task_queue))
        lifecycle['data_queue_ids'].add(id(data_queues))
        return append_dummy_thread(self, 'PostProcessor')

    def fake_foreman(self, data_queues, settings, task_queue):
        lifecycle['task_queue_ids'].add(id(task_queue))
        lifecycle['data_queue_ids'].add(id(data_queues))
        return append_dummy_thread(self, 'Foreman')

    def fake_handler(self, data_queues, task_queue):
        lifecycle['task_queue_ids'].add(id(task_queue))
        lifecycle['data_queue_ids'].add(id(data_queues))
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
        lifecycle['task_queue_ids'].clear()
        lifecycle['data_queue_ids'].clear()
        settings = configure_settings()
        service = RootService()
        service.startup_state.reset()
        service.startup_state.mark_ready('config_loaded', detail=config_dir)
        service.startup_state.mark_ready('startup_validation', detail='validated')
        service.startup_state.mark_ready('db_ready', detail=config_dir)

        service.start_threads(settings)
        snapshot = service.wait_for_startup_readiness(settings)

        assert snapshot['ready'] is True
        assert len(lifecycle['task_queue_ids']) == 1
        assert len(lifecycle['data_queue_ids']) == 1
        service.stop_threads()
        assert service.threads == []


@pytest.mark.integrationtest
def test_root_service_readiness_fails_when_ui_server_never_becomes_ready(monkeypatch):
    base_dir = tempfile.mkdtemp(prefix='unmanic_tests_service_')
    config_dir = os.path.join(base_dir, 'config')
    cache_dir = os.path.join(base_dir, 'cache')
    library_dir = os.path.join(base_dir, 'library')
    os.makedirs(config_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(library_dir, exist_ok=True)

    reset_singletons()
    settings = config.Config(config_path=config_dir)
    settings.set_config_item('cache_path', cache_dir, save_settings=False)
    settings.set_config_item('library_path', library_dir, save_settings=False)
    settings.set_config_item('startup_readiness_timeout_seconds', 1, save_settings=False)

    monkeypatch.setattr(RootService, 'initial_register_unmanic', lambda self: None)
    monkeypatch.setattr(RootService, 'start_post_processor', lambda self, data_queues, task_queue: append_dummy_thread(self, 'PostProcessor'))
    monkeypatch.setattr(RootService, 'start_foreman', lambda self, data_queues, settings, task_queue: append_dummy_thread(self, 'Foreman'))
    monkeypatch.setattr(RootService, 'start_handler', lambda self, data_queues, task_queue: append_dummy_thread(self, 'TaskHandler'))
    monkeypatch.setattr(RootService, 'start_library_scanner_manager', lambda self, data_queues: append_dummy_thread(self, 'LibraryScannerManager'))
    monkeypatch.setattr(RootService, 'start_inotify_watch_manager', lambda self, data_queues, settings: append_dummy_thread(self, 'EventMonitorManager'))
    monkeypatch.setattr(RootService, 'start_ui_server', lambda self, data_queues, foreman: append_dummy_thread(self, 'UIServer'))
    monkeypatch.setattr(RootService, 'start_scheduled_tasks_manager', lambda self: append_dummy_thread(self, 'ScheduledTasksManager'))
    monkeypatch.setattr(RootService, 'start_resource_logger', lambda self: append_dummy_thread(self, 'RootServiceResourceLogger'))

    service = RootService()
    service.startup_state.reset()
    service.startup_state.mark_ready('config_loaded', detail=config_dir)
    service.startup_state.mark_ready('startup_validation', detail='validated')
    service.startup_state.mark_ready('db_ready', detail=config_dir)

    service.start_threads(settings)
    with pytest.raises(RuntimeError, match='Startup readiness check failed'):
        service.wait_for_startup_readiness(settings)
    snapshot = service.startup_state.snapshot()
    assert snapshot['ready'] is False
    assert snapshot['stages']['ui_server_ready'] is False
    service.stop_threads()


@pytest.mark.integrationtest
def test_verify_thread_started_marks_partial_startup_failure():
    service = RootService()
    dead_thread = DummyThread('DeadThread')
    dead_thread.stop()

    with pytest.raises(RuntimeError, match='WORKER_THREAD_STARTUP_FAILED'):
        service._verify_thread_started('DeadThread', dead_thread, timeout=0.1)

    snapshot = service.startup_state.snapshot()
    assert snapshot['ready'] is False
    assert snapshot['errors'][0]['stage'] == 'threads_ready'
