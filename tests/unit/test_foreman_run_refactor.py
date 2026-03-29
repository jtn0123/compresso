#!/usr/bin/env python3

"""
tests.unit.test_foreman_run_refactor.py

Tests for the extracted helper methods from Foreman.run().
"""

import queue
import threading
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.foreman import Foreman


def _make_foreman():
    """Create a Foreman with mocked dependencies."""
    data_queues = {}
    settings = MagicMock()
    task_queue = MagicMock()
    event = threading.Event()

    with patch.object(Foreman, "__init__", lambda self, *a, **kw: None):
        fm = Foreman.__new__(Foreman)

    fm.settings = settings
    fm.event = event
    fm.task_queue = task_queue
    fm.data_queues = data_queues
    fm.logger = MagicMock()
    fm.workers_pending_task_queue = queue.Queue(maxsize=1)
    fm.remote_workers_pending_task_queue = queue.Queue(maxsize=1)
    fm.complete_queue = queue.Queue()
    fm.worker_threads = {}
    fm.paused_worker_threads = []
    fm.remote_task_manager_threads = {}
    fm.abort_flag = threading.Event()
    fm.abort_flag.clear()
    return fm


@pytest.mark.unittest
class TestDrainCompletedTasks:
    def test_drains_all_completed(self):
        fm = _make_foreman()
        task1, task2 = MagicMock(), MagicMock()
        fm.complete_queue.put(task1)
        fm.complete_queue.put(task2)

        fm._drain_completed_tasks()

        task1.set_status.assert_called_once_with("processed")
        task2.set_status.assert_called_once_with("processed")
        assert fm.complete_queue.empty()

    def test_handles_empty_queue(self):
        fm = _make_foreman()
        fm._drain_completed_tasks()  # should not raise

    def test_logs_exception_on_bad_task(self):
        fm = _make_foreman()
        bad_task = MagicMock()
        bad_task.set_status.side_effect = AttributeError("no status")
        fm.complete_queue.put(bad_task)

        fm._drain_completed_tasks()

        fm.logger.exception.assert_called_once()

    def test_stops_on_abort(self):
        fm = _make_foreman()
        fm.complete_queue.put(MagicMock())
        fm.abort_flag.set()

        fm._drain_completed_tasks()

        assert not fm.complete_queue.empty()  # task not consumed because abort was set


@pytest.mark.unittest
class TestSyncAndValidateWorkers:
    def test_valid_config_returns_true(self):
        fm = _make_foreman()
        fm.init_worker_threads = MagicMock()
        fm.validate_worker_config = MagicMock(return_value=True)
        fm.resume_all_worker_threads = MagicMock()

        assert fm._sync_and_validate_workers() is True
        fm.init_worker_threads.assert_called_once()

    def test_invalid_config_pauses_and_returns_false(self):
        fm = _make_foreman()
        fm.init_worker_threads = MagicMock()
        fm.validate_worker_config = MagicMock(return_value=False)
        fm.pause_all_worker_threads = MagicMock()

        assert fm._sync_and_validate_workers() is False
        fm.pause_all_worker_threads.assert_called_once_with(record_paused=True)

    def test_resumes_paused_workers_on_valid_config(self):
        fm = _make_foreman()
        fm.init_worker_threads = MagicMock()
        fm.validate_worker_config = MagicMock(return_value=True)
        fm.resume_all_worker_threads = MagicMock()
        fm.paused_worker_threads = ["w1", "w2"]

        fm._sync_and_validate_workers()

        fm.resume_all_worker_threads.assert_called_once_with(recorded_paused_only=True)
        assert fm.paused_worker_threads == []


@pytest.mark.unittest
class TestCheckQueueIdleTransition:
    def test_active_to_idle_dispatches_notification(self):
        fm = _make_foreman()
        fm.task_queue.task_list_pending_is_empty.return_value = True

        with patch("compresso.libs.foreman.ExternalNotificationDispatcher", create=True) as mock_cls:
            # Patch at the import location used by the method
            with patch(
                "compresso.libs.external_notifications.ExternalNotificationDispatcher"
            ) as mock_dispatcher_cls:
                mock_dispatcher = MagicMock()
                mock_dispatcher_cls.return_value = mock_dispatcher

                result = fm._check_queue_idle_transition(was_active=True)

                assert result is False
                mock_dispatcher.dispatch.assert_called_once_with("queue_empty", {})

    def test_idle_to_idle_does_not_dispatch(self):
        fm = _make_foreman()
        fm.task_queue.task_list_pending_is_empty.return_value = True

        result = fm._check_queue_idle_transition(was_active=False)

        assert result is False  # still idle, no dispatch

    def test_active_queue_returns_true(self):
        fm = _make_foreman()
        fm.task_queue.task_list_pending_is_empty.return_value = False

        result = fm._check_queue_idle_transition(was_active=False)

        assert result is True


@pytest.mark.unittest
class TestFindAndAssignPendingTask:
    def test_returns_early_when_queue_empty(self):
        fm = _make_foreman()
        fm.task_queue.task_list_pending_is_empty.return_value = True

        result = fm._find_and_assign_pending_task(allow_local_check=True)

        assert result is True  # unchanged

    def test_returns_early_when_aborted(self):
        fm = _make_foreman()
        fm.abort_flag.set()

        result = fm._find_and_assign_pending_task(allow_local_check=True)

        assert result is True

    def test_skips_when_pending_queues_full(self):
        fm = _make_foreman()
        fm.task_queue.task_list_pending_is_empty.return_value = False
        fm.link_manager_tread_heartbeat = MagicMock()
        fm.workers_pending_task_queue.put("task")  # fill the queue

        result = fm._find_and_assign_pending_task(allow_local_check=True)

        assert result is True  # unchanged, skipped assignment

    def test_all_workers_busy_waits_and_returns(self):
        fm = _make_foreman()
        fm.task_queue.task_list_pending_is_empty.return_value = False
        fm.link_manager_tread_heartbeat = MagicMock()
        fm.check_for_idle_workers = MagicMock(return_value=False)
        fm.check_for_idle_remote_workers = MagicMock(return_value=False)

        result = fm._find_and_assign_pending_task(allow_local_check=True)

        assert result is True  # reset to True when all busy

    def test_local_worker_no_matching_task_disables_local_check(self):
        fm = _make_foreman()
        fm.task_queue.task_list_pending_is_empty.return_value = False
        fm.link_manager_tread_heartbeat = MagicMock()
        fm.check_for_idle_workers = MagicMock(return_value=True)
        fm.fetch_available_worker_ids = MagicMock(return_value=["w1"])
        fm.get_tags_configured_for_worker = MagicMock(return_value=[])
        fm.task_queue.get_next_pending_tasks.return_value = None
        fm.postprocessor_queue_full = MagicMock(return_value=False)

        result = fm._find_and_assign_pending_task(allow_local_check=True)

        assert result is False  # disabled local check for next iteration
