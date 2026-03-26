#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_queue_eta.py

    Unit tests for compresso/webserver/helpers/queue_eta.py:
    - estimate_queue_eta: ETA estimation across various scenarios
    - _get_avg_task_duration: historical average calculation
    - _get_pending_tasks_count: pending count query
"""

import datetime

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType

MODULE = 'compresso.webserver.helpers.queue_eta'


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_foreman(workers=None):
    """Create a mock foreman returning the given worker status list."""
    foreman = MagicMock()
    foreman.get_all_worker_status.return_value = workers or []
    return foreman


def _make_worker(worker_id, idle=True, paused=False, eta_seconds=None):
    """Build a worker status dict matching Worker.get_status() shape."""
    subprocess_stats = None
    if not idle:
        subprocess_stats = {
            'pid': '1234',
            'percent': '50',
            'elapsed': 60,
            'cpu_percent': '80',
            'mem_percent': '10',
            'rss_bytes': '1024',
            'vms_bytes': '2048',
            'eta_seconds': eta_seconds,
            'encoding_fps': 30.0,
            'encoding_speed': 1.5,
        }
    return {
        'id':              str(worker_id),
        'name':            'Worker-{}'.format(worker_id),
        'idle':            idle,
        'paused':          paused,
        'current_task':    None if idle else 'task-{}'.format(worker_id),
        'current_file':    '' if idle else 'file-{}.mp4'.format(worker_id),
        'subprocess':      subprocess_stats,
    }


# ------------------------------------------------------------------
# estimate_queue_eta - empty queue
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestEstimateQueueEtaEmptyQueue:

    @patch(MODULE + '._get_pending_tasks_count', return_value=0)
    @patch(MODULE + '._get_avg_task_duration', return_value=(0, 0))
    def test_empty_queue_no_workers(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        foreman = _make_foreman([])
        result = estimate_queue_eta(foreman)
        assert result['active_workers_eta_seconds'] == 0
        assert result['pending_tasks_count'] == 0
        assert result['total_queue_eta_seconds'] == 0
        assert result['eta_confidence'] == 'low'
        assert result['total_workers'] == 0

    @patch(MODULE + '._get_pending_tasks_count', return_value=0)
    @patch(MODULE + '._get_avg_task_duration', return_value=(120.0, 15))
    def test_empty_queue_idle_workers(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [_make_worker(1, idle=True), _make_worker(2, idle=True)]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        assert result['active_workers_eta_seconds'] == 0
        assert result['pending_tasks_count'] == 0
        assert result['total_queue_eta_seconds'] == 0
        assert result['eta_confidence'] == 'high'
        assert result['busy_workers'] == 0


# ------------------------------------------------------------------
# estimate_queue_eta - no history (low confidence)
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestEstimateQueueEtaNoHistory:

    @patch(MODULE + '._get_pending_tasks_count', return_value=5)
    @patch(MODULE + '._get_avg_task_duration', return_value=(0, 0))
    def test_no_history_returns_low_confidence(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [_make_worker(1, idle=True)]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        assert result['eta_confidence'] == 'low'
        assert result['estimated_per_task_seconds'] == 0
        # With no avg duration, pending ETA portion is 0
        assert result['total_queue_eta_seconds'] == 0

    @patch(MODULE + '._get_pending_tasks_count', return_value=10)
    @patch(MODULE + '._get_avg_task_duration', return_value=(60.0, 2))
    def test_two_history_items_is_low_confidence(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        foreman = _make_foreman([_make_worker(1, idle=True)])
        result = estimate_queue_eta(foreman)
        assert result['eta_confidence'] == 'low'


# ------------------------------------------------------------------
# estimate_queue_eta - single worker with known ETA
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestEstimateQueueEtaSingleWorker:

    @patch(MODULE + '._get_pending_tasks_count', return_value=4)
    @patch(MODULE + '._get_avg_task_duration', return_value=(100.0, 20))
    def test_single_busy_worker_with_eta(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [_make_worker(1, idle=False, eta_seconds=50)]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        assert result['active_workers_eta_seconds'] == 50
        assert result['busy_workers'] == 1
        assert result['pending_tasks_count'] == 4
        assert result['estimated_per_task_seconds'] == 100.0
        # pending_eta = (4 * 100) / 1 = 400
        # total = 50 + 400 = 450
        assert result['total_queue_eta_seconds'] == 450
        assert result['eta_confidence'] == 'high'

    @patch(MODULE + '._get_pending_tasks_count', return_value=0)
    @patch(MODULE + '._get_avg_task_duration', return_value=(100.0, 20))
    def test_single_busy_worker_no_pending(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [_make_worker(1, idle=False, eta_seconds=30)]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        # Only the active worker ETA matters
        assert result['total_queue_eta_seconds'] == 30

    @patch(MODULE + '._get_pending_tasks_count', return_value=3)
    @patch(MODULE + '._get_avg_task_duration', return_value=(60.0, 5))
    def test_single_worker_medium_confidence(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [_make_worker(1, idle=False, eta_seconds=20)]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        assert result['eta_confidence'] == 'medium'


# ------------------------------------------------------------------
# estimate_queue_eta - multiple workers
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestEstimateQueueEtaMultipleWorkers:

    @patch(MODULE + '._get_pending_tasks_count', return_value=6)
    @patch(MODULE + '._get_avg_task_duration', return_value=(120.0, 30))
    def test_two_busy_workers_takes_max_eta(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [
            _make_worker(1, idle=False, eta_seconds=40),
            _make_worker(2, idle=False, eta_seconds=80),
        ]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        # Max of active ETAs
        assert result['active_workers_eta_seconds'] == 80
        # pending_eta = (6 * 120) / 2 = 360
        assert result['total_queue_eta_seconds'] == 80 + 360
        assert result['busy_workers'] == 2
        assert result['total_workers'] == 2

    @patch(MODULE + '._get_pending_tasks_count', return_value=10)
    @patch(MODULE + '._get_avg_task_duration', return_value=(100.0, 50))
    def test_mix_of_busy_and_idle_workers(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [
            _make_worker(1, idle=False, eta_seconds=60),
            _make_worker(2, idle=True),
            _make_worker(3, idle=False, eta_seconds=30),
        ]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        assert result['active_workers_eta_seconds'] == 60
        assert result['busy_workers'] == 2
        # All 3 workers available (none paused), so pending_eta = (10*100)/3 = 333
        expected_pending_eta = int((10 * 100) / 3)
        assert result['total_queue_eta_seconds'] == 60 + expected_pending_eta

    @patch(MODULE + '._get_pending_tasks_count', return_value=8)
    @patch(MODULE + '._get_avg_task_duration', return_value=(200.0, 12))
    def test_busy_worker_with_no_eta_in_subprocess(self, mock_avg, mock_pending):
        """A busy worker whose subprocess has eta_seconds=None should not contribute to active ETAs."""
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [
            _make_worker(1, idle=False, eta_seconds=None),
            _make_worker(2, idle=False, eta_seconds=100),
        ]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        assert result['active_workers_eta_seconds'] == 100
        assert result['busy_workers'] == 2


# ------------------------------------------------------------------
# estimate_queue_eta - paused workers
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestEstimateQueueEtaPausedWorkers:

    @patch(MODULE + '._get_pending_tasks_count', return_value=4)
    @patch(MODULE + '._get_avg_task_duration', return_value=(100.0, 10))
    def test_paused_workers_not_counted_as_available(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [
            _make_worker(1, idle=False, eta_seconds=50),
            _make_worker(2, idle=True, paused=True),
        ]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        assert result['paused_workers'] == 1
        # Only 1 available worker (worker 2 is paused)
        # pending_eta = (4 * 100) / 1 = 400
        assert result['total_queue_eta_seconds'] == 50 + 400

    @patch(MODULE + '._get_pending_tasks_count', return_value=4)
    @patch(MODULE + '._get_avg_task_duration', return_value=(100.0, 10))
    def test_all_workers_paused(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        workers = [
            _make_worker(1, idle=True, paused=True),
            _make_worker(2, idle=True, paused=True),
        ]
        foreman = _make_foreman(workers)
        result = estimate_queue_eta(foreman)
        assert result['paused_workers'] == 2
        assert result['active_workers_eta_seconds'] == 0
        # All paused, available_workers falls back to 1
        # pending_eta = (4 * 100) / 1 = 400
        assert result['total_queue_eta_seconds'] == 400


# ------------------------------------------------------------------
# estimate_queue_eta - foreman error handling
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestEstimateQueueEtaErrorHandling:

    @patch(MODULE + '._get_pending_tasks_count', return_value=0)
    @patch(MODULE + '._get_avg_task_duration', return_value=(0, 0))
    def test_foreman_exception_returns_safe_defaults(self, mock_avg, mock_pending):
        from compresso.webserver.helpers.queue_eta import estimate_queue_eta
        foreman = MagicMock()
        foreman.get_all_worker_status.side_effect = RuntimeError("foreman down")
        result = estimate_queue_eta(foreman)
        assert result['total_workers'] == 0
        assert result['active_workers_eta_seconds'] == 0
        assert result['total_queue_eta_seconds'] == 0


# ------------------------------------------------------------------
# _get_avg_task_duration
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetAvgTaskDuration:

    def test_with_completed_tasks(self):
        from compresso.webserver.helpers.queue_eta import _get_avg_task_duration
        # Build mock model
        mock_model = MagicMock()
        now = datetime.datetime(2025, 1, 1, 12, 0, 0)
        task1 = MagicMock()
        task1.start_time = now - datetime.timedelta(seconds=120)
        task1.finish_time = now
        task2 = MagicMock()
        task2.start_time = now - datetime.timedelta(seconds=60)
        task2.finish_time = now
        # Chain the peewee query mock
        mock_query = MagicMock()
        mock_model.select.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = [task1, task2]
        # Also mock the model's attributes for the query builder
        mock_model.start_time = MagicMock()
        mock_model.finish_time = MagicMock()
        mock_model.task_success = MagicMock()

        avg, count = _get_avg_task_duration(completed_tasks_model=mock_model)
        assert count == 2
        assert avg == 90.0  # (120 + 60) / 2

    def test_with_no_completed_tasks(self):
        from compresso.webserver.helpers.queue_eta import _get_avg_task_duration
        mock_model = MagicMock()
        mock_query = MagicMock()
        mock_model.select.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = []
        mock_model.start_time = MagicMock()
        mock_model.finish_time = MagicMock()
        mock_model.task_success = MagicMock()

        avg, count = _get_avg_task_duration(completed_tasks_model=mock_model)
        assert count == 0
        assert avg == 0

    def test_skips_zero_duration_tasks(self):
        from compresso.webserver.helpers.queue_eta import _get_avg_task_duration
        mock_model = MagicMock()
        now = datetime.datetime(2025, 1, 1, 12, 0, 0)
        task1 = MagicMock()
        task1.start_time = now
        task1.finish_time = now  # zero duration
        task2 = MagicMock()
        task2.start_time = now - datetime.timedelta(seconds=80)
        task2.finish_time = now
        mock_query = MagicMock()
        mock_model.select.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = [task1, task2]
        mock_model.start_time = MagicMock()
        mock_model.finish_time = MagicMock()
        mock_model.task_success = MagicMock()

        avg, count = _get_avg_task_duration(completed_tasks_model=mock_model)
        assert count == 1
        assert avg == 80.0


# ------------------------------------------------------------------
# _get_pending_tasks_count
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetPendingTasksCount:

    @patch('compresso.libs.unmodels.Tasks')
    def test_returns_pending_count(self, mock_tasks_model):
        from compresso.webserver.helpers.queue_eta import _get_pending_tasks_count
        mock_query = MagicMock()
        mock_tasks_model.select.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.count.return_value = 7
        assert _get_pending_tasks_count() == 7

    @patch('compresso.libs.unmodels.Tasks')
    def test_returns_zero_on_error(self, mock_tasks_model):
        from compresso.webserver.helpers.queue_eta import _get_pending_tasks_count
        mock_tasks_model.select.side_effect = Exception("DB error")
        result = _get_pending_tasks_count()
        assert result == 0


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
