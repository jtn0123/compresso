#!/usr/bin/env python3

"""
    tests.unit.test_foreman_deep.py

    Deep unit tests for compresso/libs/foreman.py
    covering the run loop, worker management, remote task handling,
    hand_task_to_workers, postprocessor_queue_full, and more.
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_foreman():
    with patch('compresso.libs.foreman.WorkerGroup'), \
         patch('compresso.libs.foreman.installation_link'), \
         patch('compresso.libs.foreman.PluginsHandler'), \
         patch('compresso.libs.foreman.CompressoLogging'), \
         patch('compresso.libs.foreman.Library'), \
         patch('compresso.libs.foreman.FrontendPushMessages'), \
         patch('compresso.libs.foreman.Foreman.configuration_changed', return_value=False):
        from compresso.libs.foreman import Foreman
        settings = MagicMock()
        settings.get_remote_installations.return_value = []
        data_queues = {}
        task_queue = MagicMock()
        event = MagicMock()
        foreman = Foreman(data_queues, settings, task_queue, event)
        return foreman


# ==================================================================
# Foreman.stop
# ==================================================================

@pytest.mark.unittest
class TestForemanStop:

    def test_stop_sets_abort_flag(self):
        foreman = _make_foreman()
        foreman.stop()
        assert foreman.abort_flag.is_set()

    def test_stop_clears_paused_threads(self):
        foreman = _make_foreman()
        foreman.paused_worker_threads = ['w-0', 'w-1']
        foreman.stop()
        assert foreman.paused_worker_threads == []

    def test_stop_marks_all_workers_redundant(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.redundant_flag = threading.Event()
        foreman.worker_threads = {'w-0': mock_thread}
        foreman.stop()
        assert mock_thread.redundant_flag.is_set()

    def test_stop_marks_all_remote_managers_redundant(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.redundant_flag = threading.Event()
        foreman.remote_task_manager_threads = {'rt-0': mock_thread}
        foreman.stop()
        assert mock_thread.redundant_flag.is_set()


# ==================================================================
# Foreman.save_current_config
# ==================================================================

@pytest.mark.unittest
class TestSaveCurrentConfig:

    def test_saves_settings(self):
        foreman = _make_foreman()
        foreman.save_current_config(settings={'key': 'val'})
        assert foreman.current_config['settings'] == {'key': 'val'}

    def test_saves_hash(self):
        foreman = _make_foreman()
        foreman.save_current_config(settings_hash='abc123')
        assert foreman.current_config['settings_hash'] == 'abc123'

    def test_saves_both(self):
        foreman = _make_foreman()
        foreman.save_current_config(settings={'a': 1}, settings_hash='xyz')
        assert foreman.current_config['settings'] == {'a': 1}
        assert foreman.current_config['settings_hash'] == 'xyz'


# ==================================================================
# Foreman.get_current_library_configuration
# ==================================================================

@pytest.mark.unittest
class TestGetCurrentLibraryConfiguration:

    @patch('compresso.libs.foreman.Library')
    def test_returns_plugin_settings(self, mock_lib_cls):
        foreman = _make_foreman()
        mock_lib_cls.get_all_libraries.return_value = [{'id': 1}]
        mock_lib_instance = MagicMock()
        mock_lib_instance.get_enabled_plugins.return_value = [
            {'plugin_id': 'p1', 'settings': {'s': 1}}
        ]
        mock_lib_instance.get_plugin_flow.return_value = ['p1']
        mock_lib_cls.return_value = mock_lib_instance
        result = foreman.get_current_library_configuration()
        assert 1 in result
        assert len(result[1]['enabled_plugins']) == 1

    @patch('compresso.libs.foreman.Library')
    def test_handles_exception_for_library(self, mock_lib_cls):
        foreman = _make_foreman()
        mock_lib_cls.get_all_libraries.return_value = [{'id': 1}]
        mock_lib_cls.side_effect = Exception("DB error")
        result = foreman.get_current_library_configuration()
        assert result == {}


# ==================================================================
# Foreman.check_for_idle_workers
# ==================================================================

@pytest.mark.unittest
class TestCheckForIdleWorkers:

    def test_returns_true_when_idle_worker_exists(self):
        foreman = _make_foreman()
        thread = MagicMock()
        thread.idle = True
        thread.is_alive.return_value = True
        thread.paused = False
        foreman.worker_threads = {'w-0': thread}
        assert foreman.check_for_idle_workers() is True

    def test_returns_false_when_no_idle_workers(self):
        foreman = _make_foreman()
        thread = MagicMock()
        thread.idle = False
        thread.is_alive.return_value = True
        thread.paused = False
        foreman.worker_threads = {'w-0': thread}
        assert foreman.check_for_idle_workers() is False

    def test_returns_false_when_idle_but_paused(self):
        foreman = _make_foreman()
        thread = MagicMock()
        thread.idle = True
        thread.is_alive.return_value = True
        thread.paused = True
        foreman.worker_threads = {'w-0': thread}
        assert foreman.check_for_idle_workers() is False

    def test_returns_false_when_idle_but_dead(self):
        foreman = _make_foreman()
        thread = MagicMock()
        thread.idle = True
        thread.is_alive.return_value = False
        thread.paused = False
        foreman.worker_threads = {'w-0': thread}
        assert foreman.check_for_idle_workers() is False

    def test_returns_false_when_empty(self):
        foreman = _make_foreman()
        foreman.worker_threads = {}
        assert foreman.check_for_idle_workers() is False


# ==================================================================
# Foreman.check_for_idle_remote_workers
# ==================================================================

@pytest.mark.unittest
class TestCheckForIdleRemoteWorkers:

    def test_returns_true_when_available(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {'uuid-1': {}}
        assert foreman.check_for_idle_remote_workers() is True

    def test_returns_false_when_empty(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {}
        assert foreman.check_for_idle_remote_workers() is False


# ==================================================================
# Foreman.get_available_remote_library_names
# ==================================================================

@pytest.mark.unittest
class TestGetAvailableRemoteLibraryNames:

    def test_returns_unique_library_names(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1|M0': {'library_names': ['Movies', 'TV']},
            'uuid-2|M0': {'library_names': ['Movies', 'Music']},
        }
        names = foreman.get_available_remote_library_names()
        assert sorted(names) == ['Movies', 'Music', 'TV']

    def test_returns_empty_when_no_managers(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {}
        assert foreman.get_available_remote_library_names() == []


# ==================================================================
# Foreman.fetch_available_worker_ids
# ==================================================================

@pytest.mark.unittest
class TestFetchAvailableWorkerIds:

    def test_returns_idle_alive_unpaused_ids(self):
        foreman = _make_foreman()
        t1 = MagicMock()
        t1.idle = True
        t1.is_alive.return_value = True
        t1.paused = False
        t1.thread_id = 'w-0'
        t2 = MagicMock()
        t2.idle = False
        t2.is_alive.return_value = True
        t2.paused = False
        t2.thread_id = 'w-1'
        foreman.worker_threads = {'w-0': t1, 'w-1': t2}
        ids = foreman.fetch_available_worker_ids()
        assert ids == ['w-0']

    def test_excludes_paused_workers(self):
        foreman = _make_foreman()
        t = MagicMock()
        t.idle = True
        t.is_alive.return_value = True
        t.paused = True
        t.thread_id = 'w-0'
        foreman.worker_threads = {'w-0': t}
        assert foreman.fetch_available_worker_ids() == []


# ==================================================================
# Foreman.terminate_worker_thread
# ==================================================================

@pytest.mark.unittest
class TestTerminateWorkerThread:

    def test_terminates_existing_worker(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.redundant_flag = threading.Event()
        foreman.worker_threads = {'w-0': mock_thread}
        result = foreman.terminate_worker_thread('w-0')
        assert result is True
        assert mock_thread.redundant_flag.is_set()

    def test_returns_false_for_nonexistent(self):
        foreman = _make_foreman()
        foreman.worker_threads = {}
        result = foreman.terminate_worker_thread('w-99')
        assert result is False


# ==================================================================
# Foreman.terminate_all_worker_threads
# ==================================================================

@pytest.mark.unittest
class TestTerminateAllWorkerThreads:

    def test_terminates_all(self):
        foreman = _make_foreman()
        t1 = MagicMock()
        t1.redundant_flag = threading.Event()
        t2 = MagicMock()
        t2.redundant_flag = threading.Event()
        foreman.worker_threads = {'w-0': t1, 'w-1': t2}
        # terminate_worker_thread calls mark_worker_thread_as_redundant
        # which calls redundant_flag.set()
        result = foreman.terminate_all_worker_threads()
        assert result is True


# ==================================================================
# Foreman.hand_task_to_workers (local)
# ==================================================================

@pytest.mark.unittest
class TestHandTaskToWorkersLocal:

    def test_assigns_task_to_local_worker(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        foreman.worker_threads = {'w-0': mock_thread}

        mock_item = MagicMock()
        mock_item.get_task_type.return_value = 'local'
        mock_item.get_task_library_id.return_value = 1
        mock_item.get_task_id.return_value = 42
        mock_item.get_source_data.return_value = {}

        with patch('compresso.libs.foreman.PluginsHandler'):
            result = foreman.hand_task_to_workers(mock_item, local=True, worker_id='w-0')

        assert result is True
        mock_thread.set_task.assert_called_once_with(mock_item)

    def test_skips_dead_worker(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        foreman.worker_threads = {'w-0': mock_thread}

        mock_item = MagicMock()
        result = foreman.hand_task_to_workers(mock_item, local=True, worker_id='w-0')
        assert result is True  # Returns True but no task set
        mock_thread.set_task.assert_not_called()

    def test_does_not_run_events_for_remote_task(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        foreman.worker_threads = {'w-0': mock_thread}

        mock_item = MagicMock()
        mock_item.get_task_type.return_value = 'remote'

        with patch('compresso.libs.foreman.PluginsHandler') as mock_ph_cls:
            foreman.hand_task_to_workers(mock_item, local=True, worker_id='w-0')
            mock_ph_cls.return_value.run_event_plugins_for_plugin_type.assert_not_called()


# ==================================================================
# Foreman.hand_task_to_workers (remote)
# ==================================================================

@pytest.mark.unittest
class TestHandTaskToWorkersRemote:

    @patch('compresso.libs.foreman.installation_link')
    def test_remote_success(self, mock_link):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_link.RemoteTaskManager.return_value = mock_thread
        foreman.available_remote_managers = {
            'uuid-1|M0': {'address': '10.0.0.1', 'library_names': ['Movies']},
        }
        foreman.remote_task_manager_threads = {}

        mock_item = MagicMock()
        result = foreman.hand_task_to_workers(mock_item, local=False, library_name='Movies')
        assert result is True

    def test_remote_failure_when_no_manager(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {}
        mock_item = MagicMock()
        result = foreman.hand_task_to_workers(mock_item, local=False, library_name='Movies')
        assert result is False


# ==================================================================
# Foreman.postprocessor_queue_full
# ==================================================================

@pytest.mark.unittest
class TestPostprocessorQueueFull:

    @patch('compresso.libs.foreman.FrontendPushMessages')
    @patch('compresso.libs.foreman.WorkerGroup')
    def test_returns_true_when_full(self, mock_wg, mock_fpm_cls):
        foreman = _make_foreman()
        mock_wg.get_all_worker_groups.return_value = [{'number_of_workers': 1}]
        foreman.available_remote_managers = {}
        foreman.remote_task_manager_threads = {}
        foreman.task_queue.list_processed_tasks.return_value = [1, 2, 3, 4, 5]
        result = foreman.postprocessor_queue_full()
        assert result is True

    @patch('compresso.libs.foreman.FrontendPushMessages')
    @patch('compresso.libs.foreman.WorkerGroup')
    def test_returns_false_when_not_full(self, mock_wg, mock_fpm_cls):
        foreman = _make_foreman()
        mock_wg.get_all_worker_groups.return_value = [{'number_of_workers': 5}]
        foreman.available_remote_managers = {}
        foreman.remote_task_manager_threads = {}
        foreman.task_queue.list_processed_tasks.return_value = [1]
        result = foreman.postprocessor_queue_full()
        assert result is False


# ==================================================================
# Foreman.resume_all_worker_threads with filters
# ==================================================================

@pytest.mark.unittest
class TestResumeAllWorkerThreadsFilters:

    def test_resume_only_recorded_paused(self):
        foreman = _make_foreman()
        t1 = MagicMock()
        t1.paused_flag = threading.Event()
        t1.paused_flag.set()
        t1.worker_group_id = 'g1'
        t2 = MagicMock()
        t2.paused_flag = threading.Event()
        t2.paused_flag.set()
        t2.worker_group_id = 'g1'
        foreman.worker_threads = {'w-0': t1, 'w-1': t2}
        foreman.paused_worker_threads = ['w-0']
        foreman.resume_all_worker_threads(recorded_paused_only=True)
        assert not t1.paused_flag.is_set()
        assert t2.paused_flag.is_set()

    def test_resume_with_group_filter(self):
        foreman = _make_foreman()
        t1 = MagicMock()
        t1.paused_flag = threading.Event()
        t1.paused_flag.set()
        t1.worker_group_id = 'g1'
        t2 = MagicMock()
        t2.paused_flag = threading.Event()
        t2.paused_flag.set()
        t2.worker_group_id = 'g2'
        foreman.worker_threads = {'w-0': t1, 'w-1': t2}
        foreman.resume_all_worker_threads(worker_group_id='g1')
        assert not t1.paused_flag.is_set()
        assert t2.paused_flag.is_set()


# ==================================================================
# Foreman.pause_worker_thread with record_paused
# ==================================================================

@pytest.mark.unittest
class TestPauseWorkerThreadRecordPaused:

    def test_records_paused_worker(self):
        foreman = _make_foreman()
        t = MagicMock()
        t.paused_flag = threading.Event()
        foreman.worker_threads = {'w-0': t}
        foreman.pause_worker_thread('w-0', record_paused=True)
        assert 'w-0' in foreman.paused_worker_threads

    def test_does_not_record_duplicates(self):
        foreman = _make_foreman()
        t = MagicMock()
        t.paused_flag = threading.Event()
        foreman.worker_threads = {'w-0': t}
        foreman.paused_worker_threads = ['w-0']
        foreman.pause_worker_thread('w-0', record_paused=True)
        assert foreman.paused_worker_threads.count('w-0') == 1


# ==================================================================
# Foreman.get_all_worker_status / get_worker_status
# ==================================================================

@pytest.mark.unittest
class TestGetWorkerStatus:

    def test_get_all_worker_status(self):
        foreman = _make_foreman()
        t1 = MagicMock()
        t1.get_status.return_value = {'id': '0', 'idle': True}
        t2 = MagicMock()
        t2.get_status.return_value = {'id': '1', 'idle': False}
        foreman.worker_threads = {'w-0': t1, 'w-1': t2}
        result = foreman.get_all_worker_status()
        assert len(result) == 2

    def test_get_worker_status_by_id(self):
        foreman = _make_foreman()
        t1 = MagicMock()
        t1.get_status.return_value = {'id': '0', 'name': 'W-1'}
        foreman.worker_threads = {0: t1}
        result = foreman.get_worker_status(0)
        assert result['name'] == 'W-1'

    def test_get_worker_status_not_found(self):
        foreman = _make_foreman()
        foreman.worker_threads = {}
        result = foreman.get_worker_status(99)
        assert result == {}


# ==================================================================
# Foreman.link_manager_tread_heartbeat
# ==================================================================

@pytest.mark.unittest
class TestLinkManagerHeartbeat:

    def test_skips_when_recent(self):
        foreman = _make_foreman()
        foreman.link_heartbeat_last_run = time.time()
        foreman.terminate_unlinked_remote_task_manager_threads = MagicMock()
        foreman.link_manager_tread_heartbeat()
        foreman.terminate_unlinked_remote_task_manager_threads.assert_not_called()

    def test_runs_when_stale(self):
        foreman = _make_foreman()
        foreman.link_heartbeat_last_run = 0
        foreman.terminate_unlinked_remote_task_manager_threads = MagicMock()
        foreman.remove_stopped_remote_task_manager_threads = MagicMock()
        foreman.remove_stale_available_remote_managers = MagicMock()
        foreman.update_remote_worker_availability_status = MagicMock()
        foreman.link_manager_tread_heartbeat()
        foreman.terminate_unlinked_remote_task_manager_threads.assert_called_once()
        foreman.remove_stopped_remote_task_manager_threads.assert_called_once()
        foreman.remove_stale_available_remote_managers.assert_called_once()
        foreman.update_remote_worker_availability_status.assert_called_once()
        assert foreman.link_heartbeat_last_run > 0


# ==================================================================
# Foreman.update_remote_worker_availability_status
# ==================================================================

@pytest.mark.unittest
class TestUpdateRemoteWorkerAvailability:

    def test_adds_available_slots(self):
        foreman = _make_foreman()
        foreman.links = MagicMock()
        foreman.links.check_remote_installation_for_available_workers.return_value = {
            'uuid-1': {
                'address': '10.0.0.1', 'auth': 'None', 'username': '', 'password': '',
                'library_names': ['Movies'], 'available_slots': 2
            }
        }
        foreman.available_remote_managers = {}
        foreman.remote_task_manager_threads = {}
        foreman.update_remote_worker_availability_status()
        assert len(foreman.available_remote_managers) == 2

    def test_skips_existing_managers(self):
        foreman = _make_foreman()
        foreman.links = MagicMock()
        foreman.links.check_remote_installation_for_available_workers.return_value = {
            'uuid-1': {
                'address': '10.0.0.1', 'auth': 'None', 'username': '', 'password': '',
                'library_names': ['Movies'], 'available_slots': 1
            }
        }
        foreman.available_remote_managers = {'uuid-1|M0': {}}
        foreman.remote_task_manager_threads = {}
        foreman.update_remote_worker_availability_status()
        # Should not add a duplicate
        assert len(foreman.available_remote_managers) == 1


# ==================================================================
# Foreman.start_worker_thread
# ==================================================================

@pytest.mark.unittest
class TestStartWorkerThread:

    @patch('compresso.libs.foreman.Worker')
    def test_starts_and_stores_thread(self, mock_worker_cls):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_worker_cls.return_value = mock_thread
        foreman.start_worker_thread('w-0', 'TestGroup-Worker-1', 'g-1')
        mock_thread.start.assert_called_once()
        assert 'w-0' in foreman.worker_threads
        assert foreman.worker_threads['w-0'] is mock_thread


# ==================================================================
# Foreman.get_tags_configured_for_worker
# ==================================================================

@pytest.mark.unittest
class TestGetTagsConfiguredForWorker:

    @patch('compresso.libs.foreman.WorkerGroup')
    def test_returns_tags(self, mock_wg_cls):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.worker_group_id = 'g-1'
        foreman.worker_threads = {'w-0': mock_thread}
        mock_wg = MagicMock()
        mock_wg.get_tags.return_value = ['tag1', 'tag2']
        mock_wg_cls.return_value = mock_wg
        tags = foreman.get_tags_configured_for_worker('w-0')
        assert tags == ['tag1', 'tag2']


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
