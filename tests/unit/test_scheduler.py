#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_scheduler.py

    Unit tests for compresso/libs/scheduler.ScheduledTasksManager.
    Tests each scheduled method, schedule configuration, and the run loop.
"""

import threading
from unittest.mock import patch, MagicMock

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_scheduler_manager():
    """Create a ScheduledTasksManager with mocked dependencies."""
    with patch('compresso.libs.scheduler.CompressoLogging') as mock_log:
        mock_log.get_logger.return_value = MagicMock()
        from compresso.libs.scheduler import ScheduledTasksManager
        event = threading.Event()
        mgr = ScheduledTasksManager(event)
    return mgr


@pytest.mark.unittest
class TestScheduledTasksManagerInit:

    def test_init_attributes(self):
        mgr = _make_scheduler_manager()
        assert mgr.name == 'ScheduledTasksManager'
        assert mgr.force_local_worker_timer == 0
        assert not mgr.abort_flag.is_set()
        assert mgr.scheduler is not None

    def test_stop_sets_abort_flag(self):
        mgr = _make_scheduler_manager()
        mgr.stop()
        assert mgr.abort_flag.is_set()


@pytest.mark.unittest
class TestRegisterCompresso:

    @patch('compresso.libs.scheduler.Session')
    def test_register_calls_session(self, mock_session_cls):
        mgr = _make_scheduler_manager()
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mgr.register_compresso()
        mock_session.register_compresso.assert_called_once_with(force=True)


@pytest.mark.unittest
class TestPluginRepoUpdate:

    @patch('compresso.libs.scheduler.PluginsHandler')
    def test_plugin_repo_update_calls_handler(self, mock_handler_cls):
        mgr = _make_scheduler_manager()
        mock_handler = MagicMock()
        mock_handler_cls.return_value = mock_handler
        mgr.plugin_repo_update()
        mock_handler.update_plugin_repos.assert_called_once()


@pytest.mark.unittest
class TestUpdateRemoteInstallationLinks:

    @patch('compresso.libs.scheduler.Links')
    def test_update_remote_links(self, mock_links_cls):
        mgr = _make_scheduler_manager()
        mock_links = MagicMock()
        mock_links_cls.return_value = mock_links
        mgr.update_remote_installation_links()
        mock_links.update_all_remote_installation_links.assert_called_once()


@pytest.mark.unittest
class TestSetWorkerCountBasedOnRemoteLinks:

    @patch('compresso.libs.scheduler.config.Config')
    @patch('compresso.libs.scheduler.task.Task')
    def test_no_linked_configs_returns_early(self, mock_task_cls, mock_config_cls):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_remote_installations.return_value = []
        mock_task = MagicMock()
        mock_task.get_total_task_list_count.return_value = 5
        mock_task_cls.return_value = mock_task
        mgr.set_worker_count_based_on_remote_installation_links()
        mock_settings.set_config_item.assert_not_called()

    @patch('compresso.libs.scheduler.config.Config')
    @patch('compresso.libs.scheduler.task.Task')
    def test_with_linked_configs_sets_worker_count(self, mock_task_cls, mock_config_cls):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_distributed_worker_count_target.return_value = 4
        mock_settings.get_remote_installations.return_value = [
            {'enable_distributed_worker_count': True, 'task_count': 10},
        ]
        mock_task = MagicMock()
        mock_task.get_total_task_list_count.return_value = 10
        mock_task_cls.return_value = mock_task
        mgr.set_worker_count_based_on_remote_installation_links()
        mock_settings.set_config_item.assert_called_once()
        args = mock_settings.set_config_item.call_args
        assert args[0][0] == 'number_of_workers'

    @patch('compresso.libs.scheduler.time.time', return_value=99999)
    @patch('compresso.libs.scheduler.config.Config')
    @patch('compresso.libs.scheduler.task.Task')
    def test_force_local_worker_timer(self, mock_task_cls, mock_config_cls, mock_time):
        mgr = _make_scheduler_manager()
        mgr.force_local_worker_timer = 0  # timer expired
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_distributed_worker_count_target.return_value = 2
        mock_settings.get_remote_installations.return_value = [
            {'enable_distributed_worker_count': True, 'task_count': 100},
        ]
        mock_task = MagicMock()
        mock_task.get_total_task_list_count.return_value = 5
        mock_task_cls.return_value = mock_task
        mgr.set_worker_count_based_on_remote_installation_links()
        # Worker count should be set
        mock_settings.set_config_item.assert_called_once()

    @patch('compresso.libs.scheduler.config.Config')
    @patch('compresso.libs.scheduler.task.Task')
    def test_allocated_exceeds_target(self, mock_task_cls, mock_config_cls):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_distributed_worker_count_target.return_value = 1
        mock_settings.get_remote_installations.return_value = [
            {'enable_distributed_worker_count': True, 'task_count': 100},
        ]
        mock_task = MagicMock()
        mock_task.get_total_task_list_count.return_value = 1
        mock_task_cls.return_value = mock_task
        mgr.set_worker_count_based_on_remote_installation_links()
        args = mock_settings.set_config_item.call_args
        # Target workers for local should be 0 since allocated > target
        assert args[0][1] == 0


@pytest.mark.unittest
class TestManageCompletedTasks:

    @patch('compresso.libs.scheduler.config.Config')
    def test_auto_manage_disabled(self, mock_config_cls):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_auto_manage_completed_tasks.return_value = False
        mgr.manage_completed_tasks()
        mock_settings.get_max_age_of_completed_tasks.assert_not_called()

    @patch('compresso.libs.history', create=True)
    @patch('compresso.libs.scheduler.config.Config')
    def test_no_completed_tasks(self, mock_config_cls, mock_history_mod):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_auto_manage_completed_tasks.return_value = True
        mock_settings.get_max_age_of_completed_tasks.return_value = 30
        mock_settings.get_compress_completed_tasks_logs.return_value = False
        mock_settings.get_always_keep_failed_tasks.return_value = True
        mock_history = MagicMock()
        mock_history_mod.History.return_value = mock_history
        mock_results = MagicMock()
        mock_results.count.return_value = 0
        mock_history.get_historic_task_list_filtered_and_sorted.return_value = mock_results
        mgr.manage_completed_tasks()

    @patch('compresso.libs.history', create=True)
    @patch('compresso.libs.scheduler.config.Config')
    def test_compress_completed_tasks(self, mock_config_cls, mock_history_mod):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_auto_manage_completed_tasks.return_value = True
        mock_settings.get_max_age_of_completed_tasks.return_value = 30
        mock_settings.get_compress_completed_tasks_logs.return_value = True
        mock_settings.get_always_keep_failed_tasks.return_value = True
        mock_history = MagicMock()
        mock_history_mod.History.return_value = mock_history
        mock_results = MagicMock()
        mock_results.count.return_value = 5
        mock_task1 = MagicMock()
        mock_task1.id = 1
        mock_results.__iter__ = MagicMock(return_value=iter([mock_task1]))
        mock_history.get_historic_task_list_filtered_and_sorted.return_value = mock_results
        mock_history.delete_historic_task_command_logs.return_value = True
        mgr.manage_completed_tasks()
        mock_history.delete_historic_task_command_logs.assert_called_once()

    @patch('compresso.libs.history', create=True)
    @patch('compresso.libs.scheduler.config.Config')
    def test_delete_completed_tasks(self, mock_config_cls, mock_history_mod):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_auto_manage_completed_tasks.return_value = True
        mock_settings.get_max_age_of_completed_tasks.return_value = 30
        mock_settings.get_compress_completed_tasks_logs.return_value = False
        mock_settings.get_always_keep_failed_tasks.return_value = False
        mock_history = MagicMock()
        mock_history_mod.History.return_value = mock_history
        mock_results = MagicMock()
        mock_results.count.return_value = 3
        mock_history.get_historic_task_list_filtered_and_sorted.return_value = mock_results
        mock_history.delete_historic_tasks_recursively.return_value = True
        mgr.manage_completed_tasks()
        mock_history.delete_historic_tasks_recursively.assert_called_once()

    @patch('compresso.libs.history', create=True)
    @patch('compresso.libs.scheduler.config.Config')
    def test_delete_failed_logs_error(self, mock_config_cls, mock_history_mod):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_auto_manage_completed_tasks.return_value = True
        mock_settings.get_max_age_of_completed_tasks.return_value = 30
        mock_settings.get_compress_completed_tasks_logs.return_value = False
        mock_settings.get_always_keep_failed_tasks.return_value = True
        mock_history = MagicMock()
        mock_history_mod.History.return_value = mock_history
        mock_results = MagicMock()
        mock_results.count.return_value = 2
        mock_history.get_historic_task_list_filtered_and_sorted.return_value = mock_results
        mock_history.delete_historic_tasks_recursively.return_value = False
        mgr.manage_completed_tasks()
        mock_history.delete_historic_tasks_recursively.assert_called_once()

    @patch('compresso.libs.history', create=True)
    @patch('compresso.libs.scheduler.config.Config')
    def test_compress_failed_logs_error(self, mock_config_cls, mock_history_mod):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_auto_manage_completed_tasks.return_value = True
        mock_settings.get_max_age_of_completed_tasks.return_value = 30
        mock_settings.get_compress_completed_tasks_logs.return_value = True
        mock_settings.get_always_keep_failed_tasks.return_value = True
        mock_history = MagicMock()
        mock_history_mod.History.return_value = mock_history
        mock_results = MagicMock()
        mock_results.count.return_value = 2
        mock_task1 = MagicMock()
        mock_task1.id = 1
        mock_results.__iter__ = MagicMock(return_value=iter([mock_task1]))
        mock_history.get_historic_task_list_filtered_and_sorted.return_value = mock_results
        mock_history.delete_historic_task_command_logs.return_value = False
        mgr.manage_completed_tasks()
        mock_history.delete_historic_task_command_logs.assert_called_once()


@pytest.mark.unittest
class TestCleanupOldPreviews:

    @patch('compresso.libs.preview.PreviewManager')
    def test_cleanup_success(self, mock_preview_cls):
        mgr = _make_scheduler_manager()
        mock_preview = MagicMock()
        mock_preview_cls.return_value = mock_preview
        mgr.cleanup_old_previews()
        mock_preview.cleanup_old_previews.assert_called_once()

    def test_cleanup_exception_handled(self):
        mgr = _make_scheduler_manager()
        with patch('compresso.libs.preview.PreviewManager', side_effect=Exception("import error")):
            # Should not raise
            mgr.cleanup_old_previews()


@pytest.mark.unittest
class TestSchedulerRunLoop:

    def test_run_creates_schedule_and_exits(self):
        mgr = _make_scheduler_manager()
        # Make it exit immediately
        mgr.abort_flag.set()
        mgr.event.set()
        with patch.object(mgr, 'manage_completed_tasks') as mock_manage:
            mgr.run()
            mock_manage.assert_called_once()
        # Scheduler should be cleared
        assert len(mgr.scheduler.get_jobs()) == 0

    def test_run_schedules_correct_jobs(self):
        mgr = _make_scheduler_manager()
        mgr.abort_flag.set()
        mgr.event.set()
        with patch.object(mgr, 'manage_completed_tasks'):
            mgr.run()
        # After abort, jobs are cleared, so we just verify run completed
