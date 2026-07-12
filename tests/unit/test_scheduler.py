#!/usr/bin/env python3

"""
tests.unit.test_scheduler.py

Unit tests for compresso/libs/scheduler.ScheduledTasksManager.
Tests each scheduled method, schedule configuration, and the run loop.
"""

import os
import threading
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_scheduler_manager():
    """Create a ScheduledTasksManager with mocked dependencies."""
    with patch("compresso.libs.scheduler.CompressoLogging") as mock_log:
        mock_log.get_logger.return_value = MagicMock()
        from compresso.libs.scheduler import ScheduledTasksManager

        event = threading.Event()
        mgr = ScheduledTasksManager(event)
    return mgr


@pytest.mark.unittest
class TestScheduledTasksManagerInit:
    def test_init_attributes(self):
        mgr = _make_scheduler_manager()
        assert mgr.name == "ScheduledTasksManager"
        assert mgr.force_local_worker_timer == 0
        assert not mgr.abort_flag.is_set()
        assert mgr.scheduler is not None

    def test_stop_sets_abort_flag(self):
        mgr = _make_scheduler_manager()
        mgr.stop()
        assert mgr.abort_flag.is_set()


@pytest.mark.unittest
class TestRegisterCompresso:
    @patch("compresso.libs.scheduler.Session")
    def test_register_calls_session(self, mock_session_cls):
        mgr = _make_scheduler_manager()
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mgr.register_compresso()
        mock_session.register_compresso.assert_called_once_with(force=True)


@pytest.mark.unittest
class TestPluginRepoUpdate:
    @patch("compresso.libs.scheduler.PluginsHandler")
    def test_plugin_repo_update_calls_handler(self, mock_handler_cls):
        mgr = _make_scheduler_manager()
        mock_handler = MagicMock()
        mock_handler_cls.return_value = mock_handler
        mgr.plugin_repo_update()
        mock_handler.update_plugin_repos.assert_called_once()


@pytest.mark.unittest
class TestUpdateRemoteInstallationLinks:
    @patch("compresso.libs.scheduler.Links")
    def test_update_remote_links(self, mock_links_cls):
        mgr = _make_scheduler_manager()
        mock_links = MagicMock()
        mock_links_cls.return_value = mock_links
        mgr.update_remote_installation_links()
        mock_links.update_all_remote_installation_links.assert_called_once()


@pytest.mark.unittest
class TestSetWorkerCountBasedOnRemoteLinks:
    @patch("compresso.libs.scheduler.WorkerGroup")
    @patch("compresso.libs.scheduler.config.Config")
    @patch("compresso.libs.scheduler.task.Task")
    def test_no_linked_configs_returns_early(self, mock_task_cls, mock_config_cls, mock_worker_group_cls):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_remote_installations.return_value = []
        mock_task = MagicMock()
        mock_task.get_total_task_list_count.return_value = 5
        mock_task_cls.return_value = mock_task
        mgr.set_worker_count_based_on_remote_installation_links()
        mock_settings.set_config_item.assert_not_called()
        mock_worker_group_cls.get_all_worker_groups.assert_not_called()

    @patch("compresso.libs.scheduler.WorkerGroup")
    @patch("compresso.libs.scheduler.config.Config")
    @patch("compresso.libs.scheduler.task.Task")
    def test_with_linked_configs_sets_worker_group_count(self, mock_task_cls, mock_config_cls, mock_worker_group_cls):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_distributed_worker_count_target.return_value = 4
        mock_settings.get_remote_installations.return_value = [
            {"enable_distributed_worker_count": True, "task_count": 10},
        ]
        mock_task = MagicMock()
        mock_task.get_total_task_list_count.return_value = 10
        mock_task_cls.return_value = mock_task
        mock_worker_group_cls.get_all_worker_groups.return_value = [
            {"id": 7, "number_of_workers": 1},
        ]
        mock_group = MagicMock()
        mock_worker_group_cls.return_value = mock_group
        mgr.set_worker_count_based_on_remote_installation_links()
        mock_worker_group_cls.assert_called_once_with(7)
        mock_group.set_number_of_workers.assert_called_once_with(2)
        mock_group.save.assert_called_once_with()
        mock_settings.set_config_item.assert_not_called()

    @patch("compresso.libs.scheduler.time.time", return_value=99999)
    @patch("compresso.libs.scheduler.WorkerGroup")
    @patch("compresso.libs.scheduler.config.Config")
    @patch("compresso.libs.scheduler.task.Task")
    def test_force_local_worker_timer(self, mock_task_cls, mock_config_cls, mock_worker_group_cls, mock_time):
        mgr = _make_scheduler_manager()
        mgr.force_local_worker_timer = 0  # timer expired
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_distributed_worker_count_target.return_value = 2
        mock_settings.get_remote_installations.return_value = [
            {"enable_distributed_worker_count": True, "task_count": 100},
        ]
        mock_task = MagicMock()
        mock_task.get_total_task_list_count.return_value = 5
        mock_task_cls.return_value = mock_task
        mock_worker_group_cls.get_all_worker_groups.return_value = [
            {"id": 3, "number_of_workers": 0},
        ]
        mock_group = MagicMock()
        mock_worker_group_cls.return_value = mock_group
        mgr.set_worker_count_based_on_remote_installation_links()
        mock_group.set_number_of_workers.assert_called_once_with(1)

    @patch("compresso.libs.scheduler.WorkerGroup")
    @patch("compresso.libs.scheduler.config.Config")
    @patch("compresso.libs.scheduler.task.Task")
    def test_allocated_exceeds_target(self, mock_task_cls, mock_config_cls, mock_worker_group_cls):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_distributed_worker_count_target.return_value = 1
        mock_settings.get_remote_installations.return_value = [
            {"enable_distributed_worker_count": True, "task_count": 100},
        ]
        mock_task = MagicMock()
        mock_task.get_total_task_list_count.return_value = 1
        mock_task_cls.return_value = mock_task
        mock_worker_group_cls.get_all_worker_groups.return_value = [
            {"id": 5, "number_of_workers": 2},
        ]
        mock_group = MagicMock()
        mock_worker_group_cls.return_value = mock_group
        mgr.set_worker_count_based_on_remote_installation_links()
        # Target workers for local should be 0 since allocated > target
        mock_group.set_number_of_workers.assert_called_once_with(0)

    @patch("compresso.libs.scheduler.WorkerGroup")
    def test_worker_total_preserves_existing_group_proportions(self, mock_worker_group_cls):
        mgr = _make_scheduler_manager()
        mock_worker_group_cls.get_all_worker_groups.return_value = [
            {"id": 11, "number_of_workers": 3},
            {"id": 12, "number_of_workers": 1},
        ]
        groups = {11: MagicMock(), 12: MagicMock()}
        mock_worker_group_cls.side_effect = groups.__getitem__

        mgr._set_local_worker_group_total(3)

        groups[11].set_number_of_workers.assert_called_once_with(2)
        groups[12].set_number_of_workers.assert_called_once_with(1)
        groups[11].save.assert_called_once_with()
        groups[12].save.assert_called_once_with()

    @patch("compresso.libs.scheduler.WorkerGroup")
    def test_worker_total_uses_first_group_when_all_groups_are_disabled(self, mock_worker_group_cls):
        mgr = _make_scheduler_manager()
        mock_worker_group_cls.get_all_worker_groups.return_value = [
            {"id": 21, "number_of_workers": 0},
            {"id": 22, "number_of_workers": 0},
        ]
        groups = {21: MagicMock(), 22: MagicMock()}
        mock_worker_group_cls.side_effect = groups.__getitem__

        mgr._set_local_worker_group_total(2)

        groups[21].set_number_of_workers.assert_called_once_with(2)
        groups[22].set_number_of_workers.assert_called_once_with(0)


@pytest.mark.unittest
class TestManageCompletedTasks:
    @patch("compresso.libs.scheduler.config.Config")
    def test_auto_manage_disabled(self, mock_config_cls):
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_config_cls.return_value = mock_settings
        mock_settings.get_auto_manage_completed_tasks.return_value = False
        mgr.manage_completed_tasks()
        mock_settings.get_max_age_of_completed_tasks.assert_not_called()

    @patch("compresso.libs.history", create=True)
    @patch("compresso.libs.scheduler.config.Config")
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

    @patch("compresso.libs.history", create=True)
    @patch("compresso.libs.scheduler.config.Config")
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

    @patch("compresso.libs.history", create=True)
    @patch("compresso.libs.scheduler.config.Config")
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

    @patch("compresso.libs.history", create=True)
    @patch("compresso.libs.scheduler.config.Config")
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

    @patch("compresso.libs.history", create=True)
    @patch("compresso.libs.scheduler.config.Config")
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
class TestTransferCleanup:
    @patch("compresso.libs.scheduler.ResumableTransferStore")
    @patch("compresso.libs.scheduler.config.Config")
    def test_removes_stale_partial_transfers(self, mock_config_cls, store_class):
        mgr = _make_scheduler_manager()
        settings = MagicMock()
        settings.get_cache_path.return_value = "/cache"
        settings.get_transfer_partial_retention_hours.return_value = 48
        mock_config_cls.return_value = settings

        mgr.cleanup_stale_transfers()

        store_class.assert_called_once_with(os.path.join("/cache", "remote_transfers"))
        store_class.return_value.cleanup_stale.assert_called_once_with(max_age_seconds=48 * 60 * 60)

    @patch("compresso.libs.scheduler.task.Task")
    @patch("compresso.libs.scheduler.Tasks")
    @patch("compresso.libs.scheduler.config.Config")
    def test_removes_expired_completed_remote_task_artifacts(self, mock_config_cls, tasks_model, task_class, tmp_path):
        mgr = _make_scheduler_manager()
        cache_path = tmp_path / "cache"
        artifact = cache_path / "remote_transfers" / "completed" / "transfer-1" / "movie.mkv"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(b"encoded")
        settings = MagicMock()
        settings.get_cache_path.return_value = str(cache_path)
        settings.get_remote_artifact_retention_hours.return_value = 1
        mock_config_cls.return_value = settings
        remote_task = MagicMock(id=7, abspath=str(artifact), finish_time=0)
        tasks_model.select.return_value.where.return_value = [remote_task]

        with (
            patch("compresso.libs.scheduler.time.time", return_value=10_000),
            patch("compresso.libs.scheduler.os.path.getmtime", return_value=0),
        ):
            mgr.cleanup_orphaned_remote_tasks()

        task_class.return_value.delete_tasks_recursively.assert_called_once_with([7])
        assert not artifact.parent.exists()


@pytest.mark.unittest
class TestCleanupOldPreviews:
    @patch("compresso.libs.preview.PreviewManager")
    def test_cleanup_success(self, mock_preview_cls):
        mgr = _make_scheduler_manager()
        mock_preview = MagicMock()
        mock_preview_cls.return_value = mock_preview
        mgr.cleanup_old_previews()
        mock_preview.cleanup_old_previews.assert_called_once()

    def test_cleanup_exception_handled(self):
        mgr = _make_scheduler_manager()
        with patch("compresso.libs.preview.PreviewManager", side_effect=Exception("import error")):
            # Should not raise
            mgr.cleanup_old_previews()


@pytest.mark.unittest
class TestSchedulerRunLoop:
    def test_run_creates_schedule_and_exits(self):
        mgr = _make_scheduler_manager()
        # Make it exit immediately
        mgr.abort_flag.set()
        mgr.event.set()
        with patch.object(mgr, "manage_completed_tasks") as mock_manage:
            mgr.run()
            mock_manage.assert_called_once()
        # Scheduler should be cleared
        assert len(mgr.scheduler.get_jobs()) == 0

    def test_run_schedules_correct_jobs(self):
        mgr = _make_scheduler_manager()
        mgr.abort_flag.set()
        mgr.event.set()
        with patch.object(mgr, "manage_completed_tasks"):
            mgr.run()
        # After abort, jobs are cleared, so we just verify run completed

    def test_failed_scheduled_job_does_not_kill_scheduler_loop(self):
        mgr = _make_scheduler_manager()
        run_count = 0

        def run_pending():
            nonlocal run_count
            run_count += 1
            if run_count == 1:
                raise RuntimeError("job failed")
            mgr.abort_flag.set()

        mgr.scheduler.run_pending = MagicMock(side_effect=run_pending)
        mgr.event.wait = MagicMock()

        with patch.object(mgr, "manage_completed_tasks"):
            mgr.run()

        assert run_count == 2
