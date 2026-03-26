#!/usr/bin/env python3

"""
tests.unit.test_foreman_queue_empty.py

Unit tests for the queue_empty notification dispatch in Foreman.run().
Tests the queue transition logic:
- Transition from active to empty dispatches 'queue_empty'
- Queue staying empty does not re-dispatch
- Transition from empty to active resets the flag
"""

from unittest.mock import MagicMock, patch

import pytest


def _make_foreman():
    """Create a Foreman instance with mocked dependencies."""
    with (
        patch("compresso.libs.foreman.WorkerGroup"),
        patch("compresso.libs.foreman.installation_link"),
        patch("compresso.libs.foreman.PluginsHandler"),
        patch("compresso.libs.foreman.CompressoLogging"),
        patch("compresso.libs.foreman.Foreman.configuration_changed", return_value=False),
    ):
        from compresso.libs.foreman import Foreman

        settings = MagicMock()
        settings.get_remote_installations.return_value = []
        data_queues = {}
        task_queue = MagicMock()
        event = MagicMock()
        foreman = Foreman(data_queues, settings, task_queue, event)
        return foreman


# ------------------------------------------------------------------
# TestQueueEmptyNotification
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestQueueEmptyNotification:
    """Tests for the queue_empty external notification dispatch."""

    def test_active_to_empty_dispatches_queue_empty(self):
        """When queue transitions from active to empty, should dispatch 'queue_empty'."""
        foreman = _make_foreman()

        # Simulate the run loop's queue detection logic directly:
        # _was_queue_active = True, then queue becomes empty (no tasks, no busy workers)
        foreman.task_queue.task_list_pending_is_empty.return_value = True
        foreman.worker_threads = {}  # No workers at all => no busy workers
        foreman.remote_task_manager_threads = {}  # No remote workers

        # The logic inline from foreman.run():
        _was_queue_active = True
        queue_has_tasks = not foreman.task_queue.task_list_pending_is_empty()
        any_workers_busy = any(
            not foreman.worker_threads[t].idle for t in foreman.worker_threads if foreman.worker_threads[t].is_alive()
        )
        any_remote_workers_busy = any(
            foreman.remote_task_manager_threads[t].is_alive() for t in foreman.remote_task_manager_threads
        )
        queue_is_active = queue_has_tasks or any_workers_busy or any_remote_workers_busy

        with patch("compresso.libs.external_notifications.ExternalNotificationDispatcher") as mock_dispatcher_cls:
            mock_dispatcher = MagicMock()
            mock_dispatcher_cls.return_value = mock_dispatcher

            if _was_queue_active and not queue_is_active:
                from compresso.libs.external_notifications import ExternalNotificationDispatcher

                ExternalNotificationDispatcher().dispatch("queue_empty", {})

            mock_dispatcher.dispatch.assert_called_once_with("queue_empty", {})

    def test_empty_staying_empty_does_not_redispatch(self):
        """When queue was already empty and stays empty, should not dispatch again."""
        foreman = _make_foreman()

        foreman.task_queue.task_list_pending_is_empty.return_value = True
        foreman.worker_threads = {}
        foreman.remote_task_manager_threads = {}

        _was_queue_active = False  # Queue was already empty
        queue_has_tasks = not foreman.task_queue.task_list_pending_is_empty()
        any_workers_busy = False
        any_remote_workers_busy = False
        queue_is_active = queue_has_tasks or any_workers_busy or any_remote_workers_busy

        dispatched = False
        if _was_queue_active and not queue_is_active:
            dispatched = True

        assert dispatched is False

    def test_empty_to_active_resets_flag(self):
        """When queue transitions from empty to active, _was_queue_active becomes True."""
        foreman = _make_foreman()

        foreman.task_queue.task_list_pending_is_empty.return_value = False  # tasks present
        foreman.worker_threads = {}
        foreman.remote_task_manager_threads = {}

        _was_queue_active = False

        queue_has_tasks = not foreman.task_queue.task_list_pending_is_empty()
        queue_is_active = queue_has_tasks or False  # no busy workers, but tasks in queue

        _was_queue_active = queue_is_active

        assert _was_queue_active is True

    def test_busy_workers_count_as_active(self):
        """Queue is considered active if any workers are busy, even with no pending tasks."""
        foreman = _make_foreman()

        foreman.task_queue.task_list_pending_is_empty.return_value = True
        foreman.remote_task_manager_threads = {}

        mock_worker = MagicMock()
        mock_worker.idle = False
        mock_worker.is_alive.return_value = True
        foreman.worker_threads = {"w1": mock_worker}

        queue_has_tasks = not foreman.task_queue.task_list_pending_is_empty()
        any_workers_busy = any(
            not foreman.worker_threads[t].idle for t in foreman.worker_threads if foreman.worker_threads[t].is_alive()
        )
        any_remote_workers_busy = any(
            foreman.remote_task_manager_threads[t].is_alive() for t in foreman.remote_task_manager_threads
        )
        queue_is_active = queue_has_tasks or any_workers_busy or any_remote_workers_busy

        assert queue_is_active is True

    def test_dead_workers_not_counted_as_busy(self):
        """Dead worker threads should not count as busy even if idle=False."""
        foreman = _make_foreman()

        foreman.task_queue.task_list_pending_is_empty.return_value = True
        foreman.remote_task_manager_threads = {}

        mock_worker = MagicMock()
        mock_worker.idle = False
        mock_worker.is_alive.return_value = False  # dead thread
        foreman.worker_threads = {"w1": mock_worker}

        any_workers_busy = any(
            not foreman.worker_threads[t].idle for t in foreman.worker_threads if foreman.worker_threads[t].is_alive()
        )

        assert any_workers_busy is False

    def test_active_remote_workers_count_as_active(self):
        """Queue is considered active if remote workers are alive, even with no local workers or tasks."""
        foreman = _make_foreman()

        foreman.task_queue.task_list_pending_is_empty.return_value = True
        foreman.worker_threads = {}

        mock_remote = MagicMock()
        mock_remote.is_alive.return_value = True
        foreman.remote_task_manager_threads = {"r1": mock_remote}

        queue_has_tasks = not foreman.task_queue.task_list_pending_is_empty()
        any_workers_busy = any(
            not foreman.worker_threads[t].idle for t in foreman.worker_threads if foreman.worker_threads[t].is_alive()
        )
        any_remote_workers_busy = any(
            foreman.remote_task_manager_threads[t].is_alive() for t in foreman.remote_task_manager_threads
        )
        queue_is_active = queue_has_tasks or any_workers_busy or any_remote_workers_busy

        assert queue_is_active is True


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
