#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_foreman_extended.py

    Extended unit tests for compresso/libs/foreman.Foreman.
    Does NOT duplicate tests in test_foreman.py.

    Covers:
    - configuration_changed() hash comparison
    - validate_worker_config() plugin compatibility checks
    - manage_event_schedules() schedule repetition types
    - run_task() pause/resume/count dispatch
    - init_worker_threads() worker thread lifecycle
    - remove_stale_available_remote_managers() staleness check
    - remove_stopped_remote_task_manager_threads() cleanup dead threads
    - fetch_available_remote_installation() library name filtering (edge cases)
"""

import threading
from datetime import datetime, timedelta

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_foreman():
    """Create a Foreman instance with mocked dependencies."""
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


# ------------------------------------------------------------------
# configuration_changed()
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestConfigurationChanged:

    def test_returns_true_when_config_hash_differs(self):
        foreman = _make_foreman()
        # Restore the real method
        from compresso.libs.foreman import Foreman
        foreman.configuration_changed = Foreman.configuration_changed.__get__(foreman, Foreman)
        # Mock get_current_library_configuration to return deterministic data
        foreman.get_current_library_configuration = MagicMock(return_value={'plugin_a': {'enabled': True}})
        # First call sets the hash
        result1 = foreman.configuration_changed()
        assert result1 is True
        # Same config - should return False
        result2 = foreman.configuration_changed()
        assert result2 is False

    def test_returns_true_when_config_changes(self):
        foreman = _make_foreman()
        from compresso.libs.foreman import Foreman
        foreman.configuration_changed = Foreman.configuration_changed.__get__(foreman, Foreman)
        foreman.get_current_library_configuration = MagicMock(return_value={'plugin_a': {'enabled': True}})
        foreman.configuration_changed()
        # Change config
        foreman.get_current_library_configuration.return_value = {'plugin_a': {'enabled': False}}
        result = foreman.configuration_changed()
        assert result is True

    def test_returns_false_when_hash_unchanged(self):
        foreman = _make_foreman()
        from compresso.libs.foreman import Foreman
        foreman.configuration_changed = Foreman.configuration_changed.__get__(foreman, Foreman)
        foreman.get_current_library_configuration = MagicMock(return_value={'x': 1})
        foreman.configuration_changed()
        # Call again with same config
        result = foreman.configuration_changed()
        assert result is False


# ------------------------------------------------------------------
# validate_worker_config()
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestValidateWorkerConfig:

    @patch('compresso.libs.foreman.Library')
    @patch('compresso.libs.foreman.FrontendPushMessages')
    @patch('compresso.libs.foreman.PluginsHandler')
    def test_invalid_when_incompatible_plugins(self, mock_ph_cls, mock_fpm_cls, mock_lib_cls):
        foreman = _make_foreman()
        mock_ph = MagicMock()
        mock_ph.get_incompatible_enabled_plugins.return_value = ['bad_plugin']
        mock_ph_cls.return_value = mock_ph
        foreman.links = MagicMock()
        foreman.links.within_enabled_link_limits.return_value = True
        foreman.configuration_changed = MagicMock(return_value=False)
        mock_lib_cls.within_library_count_limits.return_value = True
        result = foreman.validate_worker_config()
        assert result is False

    @patch('compresso.libs.foreman.Library')
    @patch('compresso.libs.foreman.FrontendPushMessages')
    @patch('compresso.libs.foreman.PluginsHandler')
    def test_invalid_when_link_limits_exceeded(self, mock_ph_cls, mock_fpm_cls, mock_lib_cls):
        foreman = _make_foreman()
        mock_ph = MagicMock()
        mock_ph.get_incompatible_enabled_plugins.return_value = []
        mock_ph_cls.return_value = mock_ph
        foreman.links = MagicMock()
        foreman.links.within_enabled_link_limits.return_value = False
        foreman.configuration_changed = MagicMock(return_value=False)
        mock_lib_cls.within_library_count_limits.return_value = True
        result = foreman.validate_worker_config()
        assert result is False

    @patch('compresso.libs.foreman.Library')
    @patch('compresso.libs.foreman.FrontendPushMessages')
    @patch('compresso.libs.foreman.PluginsHandler')
    def test_invalid_when_configuration_changed(self, mock_ph_cls, mock_fpm_cls, mock_lib_cls):
        foreman = _make_foreman()
        mock_ph = MagicMock()
        mock_ph.get_incompatible_enabled_plugins.return_value = []
        mock_ph_cls.return_value = mock_ph
        foreman.links = MagicMock()
        foreman.links.within_enabled_link_limits.return_value = True
        foreman.configuration_changed = MagicMock(return_value=True)
        mock_lib_cls.within_library_count_limits.return_value = True
        result = foreman.validate_worker_config()
        assert result is False

    @patch('compresso.libs.foreman.Library')
    @patch('compresso.libs.foreman.FrontendPushMessages')
    @patch('compresso.libs.foreman.PluginsHandler')
    def test_invalid_when_library_limits_exceeded(self, mock_ph_cls, mock_fpm_cls, mock_lib_cls):
        foreman = _make_foreman()
        mock_ph = MagicMock()
        mock_ph.get_incompatible_enabled_plugins.return_value = []
        mock_ph_cls.return_value = mock_ph
        foreman.links = MagicMock()
        foreman.links.within_enabled_link_limits.return_value = True
        foreman.configuration_changed = MagicMock(return_value=False)
        mock_lib_cls.within_library_count_limits.return_value = False
        result = foreman.validate_worker_config()
        assert result is False

    @patch('compresso.libs.foreman.Library')
    @patch('compresso.libs.foreman.FrontendPushMessages')
    @patch('compresso.libs.foreman.PluginsHandler')
    def test_valid_when_all_checks_pass(self, mock_ph_cls, mock_fpm_cls, mock_lib_cls):
        foreman = _make_foreman()
        mock_ph = MagicMock()
        mock_ph.get_incompatible_enabled_plugins.return_value = []
        mock_ph_cls.return_value = mock_ph
        foreman.links = MagicMock()
        foreman.links.within_enabled_link_limits.return_value = True
        foreman.configuration_changed = MagicMock(return_value=False)
        mock_lib_cls.within_library_count_limits.return_value = True
        result = foreman.validate_worker_config()
        assert result is True


# ------------------------------------------------------------------
# run_task()
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestRunTask:

    def test_pause_task_pauses_all_workers(self):
        foreman = _make_foreman()
        foreman.pause_all_worker_threads = MagicMock()
        mock_wg = MagicMock()
        mock_wg.get_id.return_value = 'group-1'
        foreman.run_task('12:00', 'pause', 0, mock_wg)
        foreman.pause_all_worker_threads.assert_called_once_with(worker_group_id='group-1')
        assert foreman.last_schedule_run == '12:00'

    def test_resume_task_resumes_all_workers(self):
        foreman = _make_foreman()
        foreman.resume_all_worker_threads = MagicMock()
        mock_wg = MagicMock()
        mock_wg.get_id.return_value = 'group-2'
        foreman.run_task('13:00', 'resume', 0, mock_wg)
        foreman.resume_all_worker_threads.assert_called_once_with(worker_group_id='group-2')

    def test_count_task_sets_worker_count_and_saves(self):
        foreman = _make_foreman()
        mock_wg = MagicMock()
        mock_wg.get_id.return_value = 'group-3'
        foreman.run_task('14:00', 'count', 5, mock_wg)
        mock_wg.set_number_of_workers.assert_called_once_with(5)
        mock_wg.save.assert_called_once()


# ------------------------------------------------------------------
# manage_event_schedules()
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestManageEventSchedulesExtended:

    def _setup_foreman_with_schedule(self, repetition, day_of_week, time_now, schedule_time=None):
        """Helper to set up foreman with a single worker group schedule."""
        if schedule_time is None:
            schedule_time = time_now

        foreman = _make_foreman()
        foreman.last_schedule_run = 'XX:XX'  # Force run
        foreman.run_task = MagicMock()

        mock_wg_instance = MagicMock()
        mock_wg_instance.get_worker_event_schedules.return_value = [
            {
                'schedule_time': schedule_time,
                'repetition': repetition,
                'schedule_task': 'pause',
                'schedule_worker_count': 0,
            }
        ]

        with patch('compresso.libs.foreman.WorkerGroup') as mock_wg_cls, \
             patch('compresso.libs.foreman.datetime') as mock_dt:
            mock_today = MagicMock()
            mock_today.weekday.return_value = day_of_week
            mock_today.strftime.return_value = time_now
            mock_dt.today.return_value = mock_today

            mock_wg_cls.get_all_worker_groups.return_value = [{'id': 'g1'}]
            mock_wg_cls.return_value = mock_wg_instance

            foreman.manage_event_schedules()

        return foreman

    def test_daily_schedule_runs_any_day(self):
        foreman = self._setup_foreman_with_schedule('daily', 3, '08:00')  # Thursday
        foreman.run_task.assert_called_once()

    def test_weekday_schedule_runs_on_monday(self):
        foreman = self._setup_foreman_with_schedule('weekday', 0, '09:00')  # Monday
        foreman.run_task.assert_called_once()

    def test_weekday_schedule_skips_saturday(self):
        foreman = self._setup_foreman_with_schedule('weekday', 5, '09:00')  # Saturday
        foreman.run_task.assert_not_called()

    def test_weekday_schedule_skips_sunday(self):
        foreman = self._setup_foreman_with_schedule('weekday', 6, '09:00')  # Sunday
        foreman.run_task.assert_not_called()

    def test_weekend_schedule_runs_on_saturday(self):
        foreman = self._setup_foreman_with_schedule('weekend', 5, '10:00')  # Saturday
        foreman.run_task.assert_called_once()

    def test_weekend_schedule_runs_on_sunday(self):
        foreman = self._setup_foreman_with_schedule('weekend', 6, '10:00')  # Sunday
        foreman.run_task.assert_called_once()

    def test_weekend_schedule_skips_weekday(self):
        foreman = self._setup_foreman_with_schedule('weekend', 2, '10:00')  # Wednesday
        foreman.run_task.assert_not_called()

    def test_specific_day_schedule_runs_on_matching_day(self):
        foreman = self._setup_foreman_with_schedule('friday', 4, '11:00')  # Friday
        foreman.run_task.assert_called_once()

    def test_specific_day_schedule_skips_non_matching_day(self):
        foreman = self._setup_foreman_with_schedule('friday', 0, '11:00')  # Monday
        foreman.run_task.assert_not_called()

    def test_skips_when_time_matches_last_run(self):
        foreman = _make_foreman()
        foreman.last_schedule_run = '08:00'
        foreman.run_task = MagicMock()
        with patch('compresso.libs.foreman.WorkerGroup') as mock_wg_cls, \
             patch('compresso.libs.foreman.datetime') as mock_dt:
            mock_today = MagicMock()
            mock_today.strftime.return_value = '08:00'
            mock_dt.today.return_value = mock_today
            foreman.manage_event_schedules()
        foreman.run_task.assert_not_called()

    def test_skips_schedule_without_time(self):
        foreman = _make_foreman()
        foreman.last_schedule_run = 'XX:XX'
        foreman.run_task = MagicMock()
        mock_wg_instance = MagicMock()
        mock_wg_instance.get_worker_event_schedules.return_value = [
            {'schedule_time': '', 'repetition': 'daily', 'schedule_task': 'pause'}
        ]
        with patch('compresso.libs.foreman.WorkerGroup') as mock_wg_cls, \
             patch('compresso.libs.foreman.datetime') as mock_dt:
            mock_today = MagicMock()
            mock_today.weekday.return_value = 0
            mock_today.strftime.return_value = '08:00'
            mock_dt.today.return_value = mock_today
            mock_wg_cls.get_all_worker_groups.return_value = [{'id': 'g1'}]
            mock_wg_cls.return_value = mock_wg_instance
            foreman.manage_event_schedules()
        foreman.run_task.assert_not_called()


# ------------------------------------------------------------------
# init_worker_threads()
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestInitWorkerThreads:

    @patch('compresso.libs.foreman.WorkerGroup')
    def test_spawns_new_workers(self, mock_wg_cls):
        foreman = _make_foreman()
        foreman.worker_threads = {}
        foreman.start_worker_thread = MagicMock()
        mock_wg_cls.get_all_worker_groups.return_value = [
            {'id': 'g1', 'name': 'Default', 'number_of_workers': 2}
        ]
        foreman.init_worker_threads()
        assert foreman.start_worker_thread.call_count == 2

    @patch('compresso.libs.foreman.WorkerGroup')
    def test_removes_dead_threads(self, mock_wg_cls):
        foreman = _make_foreman()
        dead_thread = MagicMock()
        dead_thread.is_alive.return_value = False
        foreman.worker_threads = {'w-0': dead_thread}
        foreman.start_worker_thread = MagicMock()
        mock_wg_cls.get_all_worker_groups.return_value = []
        foreman.init_worker_threads()
        assert 'w-0' not in foreman.worker_threads

    @patch('compresso.libs.foreman.WorkerGroup')
    def test_removes_excess_idle_workers(self, mock_wg_cls):
        foreman = _make_foreman()
        idle_thread = MagicMock()
        idle_thread.is_alive.return_value = True
        idle_thread.idle = True
        idle_thread.worker_group_id = 'g1'
        idle_thread.name = 'Default-Worker-3'
        # Worker at index 2 (0-based) should be removed when only 2 workers configured
        foreman.worker_threads = {'Default-2': idle_thread}
        foreman.start_worker_thread = MagicMock()
        foreman.mark_worker_thread_as_redundant = MagicMock()
        mock_wg_cls.get_all_worker_groups.return_value = [
            {'id': 'g1', 'name': 'Default', 'number_of_workers': 2}
        ]
        foreman.init_worker_threads()
        foreman.mark_worker_thread_as_redundant.assert_called_with('Default-2')


# ------------------------------------------------------------------
# remove_stale_available_remote_managers()
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestRemoveStaleAvailableRemoteManagers:

    def test_removes_stale_managers(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1|M0': {
                'created': datetime.now() - timedelta(seconds=60),
            },
        }
        foreman.remote_task_manager_threads = {}
        foreman.remove_stale_available_remote_managers()
        assert 'uuid-1|M0' not in foreman.available_remote_managers

    def test_keeps_fresh_managers(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1|M0': {
                'created': datetime.now() - timedelta(seconds=5),
            },
        }
        foreman.remote_task_manager_threads = {}
        foreman.remove_stale_available_remote_managers()
        assert 'uuid-1|M0' in foreman.available_remote_managers

    def test_skips_managers_with_active_threads(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1|M0': {
                'created': datetime.now() - timedelta(seconds=60),
            },
        }
        foreman.remote_task_manager_threads = {'uuid-1|M0': MagicMock()}
        foreman.remove_stale_available_remote_managers()
        # Should still be there because it's in remote_task_manager_threads
        assert 'uuid-1|M0' in foreman.available_remote_managers


# ------------------------------------------------------------------
# remove_stopped_remote_task_manager_threads()
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestRemoveStoppedRemoteTaskManagerThreads:

    def test_removes_dead_threads(self):
        foreman = _make_foreman()
        dead_thread = MagicMock()
        dead_thread.is_alive.return_value = False
        foreman.remote_task_manager_threads = {'thread-1': dead_thread}
        foreman.remove_stopped_remote_task_manager_threads()
        assert 'thread-1' not in foreman.remote_task_manager_threads

    def test_keeps_alive_threads(self):
        foreman = _make_foreman()
        alive_thread = MagicMock()
        alive_thread.is_alive.return_value = True
        foreman.remote_task_manager_threads = {'thread-1': alive_thread}
        foreman.remove_stopped_remote_task_manager_threads()
        assert 'thread-1' in foreman.remote_task_manager_threads

    def test_handles_empty_thread_list(self):
        foreman = _make_foreman()
        foreman.remote_task_manager_threads = {}
        foreman.remove_stopped_remote_task_manager_threads()
        assert foreman.remote_task_manager_threads == {}


# ------------------------------------------------------------------
# fetch_available_remote_installation() - edge cases
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFetchAvailableRemoteInstallationExtended:

    def test_returns_first_match_with_none_library_name(self):
        """When library_name is None, any installation matches."""
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1|M0': {'address': '10.0.0.1', 'library_names': ['Movies']},
            'uuid-2|M0': {'address': '10.0.0.2', 'library_names': ['TV']},
        }
        foreman.remote_task_manager_threads = {}
        inst_id, inst_info = foreman.fetch_available_remote_installation(library_name=None)
        assert inst_id == 'uuid-1|M0'

    def test_returns_none_when_library_name_not_found(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1|M0': {'address': '10.0.0.1', 'library_names': ['Movies']},
        }
        foreman.remote_task_manager_threads = {}
        inst_id, inst_info = foreman.fetch_available_remote_installation(library_name='Music')
        assert inst_id is None
        assert inst_info == {}

    def test_skips_installations_already_in_thread_manager(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1|M0': {'address': '10.0.0.1', 'library_names': ['Movies']},
            'uuid-2|M0': {'address': '10.0.0.2', 'library_names': ['Movies']},
        }
        foreman.remote_task_manager_threads = {'uuid-1|M0': MagicMock()}
        inst_id, _ = foreman.fetch_available_remote_installation(library_name='Movies')
        assert inst_id == 'uuid-2|M0'


# ------------------------------------------------------------------
# Pause / Resume worker threads
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestPauseResumeWorkerThreads:

    def test_pause_worker_thread_sets_flag(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.paused_flag = threading.Event()
        foreman.worker_threads = {'w-0': mock_thread}
        result = foreman.pause_worker_thread('w-0')
        assert result is True
        assert mock_thread.paused_flag.is_set()

    def test_pause_worker_thread_nonexistent_returns_false(self):
        foreman = _make_foreman()
        foreman.worker_threads = {}
        result = foreman.pause_worker_thread('w-99')
        assert result is False

    def test_resume_worker_thread_clears_flag(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.paused_flag = threading.Event()
        mock_thread.paused_flag.set()
        foreman.worker_threads = {'w-0': mock_thread}
        result = foreman.resume_worker_thread('w-0')
        assert result is True
        assert not mock_thread.paused_flag.is_set()

    def test_resume_removes_from_paused_list(self):
        foreman = _make_foreman()
        mock_thread = MagicMock()
        mock_thread.paused_flag = threading.Event()
        mock_thread.paused_flag.set()
        foreman.worker_threads = {'w-0': mock_thread}
        foreman.paused_worker_threads = ['w-0']
        foreman.resume_worker_thread('w-0')
        assert 'w-0' not in foreman.paused_worker_threads

    def test_pause_all_with_worker_group_filter(self):
        foreman = _make_foreman()
        thread_g1 = MagicMock()
        thread_g1.paused_flag = threading.Event()
        thread_g1.worker_group_id = 'g1'
        thread_g2 = MagicMock()
        thread_g2.paused_flag = threading.Event()
        thread_g2.worker_group_id = 'g2'
        foreman.worker_threads = {'w-0': thread_g1, 'w-1': thread_g2}
        foreman.pause_all_worker_threads(worker_group_id='g1')
        assert thread_g1.paused_flag.is_set()
        assert not thread_g2.paused_flag.is_set()


# ------------------------------------------------------------------
# get_total_worker_count
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetTotalWorkerCount:

    @patch('compresso.libs.foreman.WorkerGroup')
    def test_sums_all_worker_groups(self, mock_wg_cls):
        foreman = _make_foreman()
        mock_wg_cls.get_all_worker_groups.return_value = [
            {'id': 'g1', 'number_of_workers': 3},
            {'id': 'g2', 'number_of_workers': 2},
        ]
        count = foreman.get_total_worker_count()
        assert count == 5

    @patch('compresso.libs.foreman.WorkerGroup')
    def test_returns_zero_when_no_groups(self, mock_wg_cls):
        foreman = _make_foreman()
        mock_wg_cls.get_all_worker_groups.return_value = []
        count = foreman.get_total_worker_count()
        assert count == 0


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
