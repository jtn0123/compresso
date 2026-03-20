#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_workers.py

    Unit tests for compresso/libs/workers.py:
    - WorkerSubprocessMonitor: init, proc management, stats, progress parsing
    - Worker: init, set_task, get_status lifecycle
"""

import threading
import time

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_parent_worker():
    """Create a mock parent worker with the attributes WorkerSubprocessMonitor expects."""
    parent = MagicMock()
    parent.event = MagicMock()
    parent.redundant_flag = threading.Event()
    parent.paused_flag = threading.Event()
    return parent


def _make_monitor(parent=None):
    """Create a WorkerSubprocessMonitor without starting its thread."""
    if parent is None:
        parent = _make_parent_worker()
    with patch('compresso.libs.workers.CompressoLogging'):
        from compresso.libs.workers import WorkerSubprocessMonitor
        monitor = WorkerSubprocessMonitor(parent)
    return monitor


# ------------------------------------------------------------------
# WorkerSubprocessMonitor.__init__
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestWorkerSubprocessMonitorInit:

    def test_init_sets_parent_reference(self):
        parent = _make_parent_worker()
        monitor = _make_monitor(parent)
        assert monitor.parent_worker is parent

    def test_init_subprocess_is_none(self):
        monitor = _make_monitor()
        assert monitor.subprocess is None
        assert monitor.subprocess_pid is None

    def test_init_flags_from_parent(self):
        parent = _make_parent_worker()
        monitor = _make_monitor(parent)
        assert monitor.redundant_flag is parent.redundant_flag
        assert monitor.paused_flag is parent.paused_flag

    def test_init_paused_is_false(self):
        monitor = _make_monitor()
        assert monitor.paused is False

    def test_init_subprocess_stats_are_zero(self):
        monitor = _make_monitor()
        assert monitor.subprocess_percent == 0
        assert monitor.subprocess_elapsed == 0
        assert monitor.subprocess_cpu_percent == 0
        assert monitor.subprocess_mem_percent == 0
        assert monitor.subprocess_rss_bytes == 0
        assert monitor.subprocess_vms_bytes == 0


# ------------------------------------------------------------------
# WorkerSubprocessMonitor.set_proc / unset_proc
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestSetUnsetProc:

    @patch('compresso.libs.workers.psutil.Process')
    def test_set_proc_creates_psutil_process(self, mock_process_cls):
        mock_proc = MagicMock()
        mock_process_cls.return_value = mock_proc
        monitor = _make_monitor()
        monitor.set_proc(1234)
        mock_process_cls.assert_called_once_with(pid=1234)
        assert monitor.subprocess is mock_proc
        assert monitor.subprocess_pid == 1234

    @patch('compresso.libs.workers.psutil.Process')
    def test_set_proc_resets_pause_time(self, mock_process_cls):
        monitor = _make_monitor()
        monitor.subprocess_pause_time = 100
        monitor.set_proc(1234)
        assert monitor.subprocess_pause_time == 0

    @patch('compresso.libs.workers.psutil.Process')
    def test_set_proc_same_pid_does_not_recreate(self, mock_process_cls):
        monitor = _make_monitor()
        monitor.set_proc(1234)
        mock_process_cls.reset_mock()
        monitor.set_proc(1234)
        mock_process_cls.assert_not_called()

    @patch('compresso.libs.workers.psutil.Process')
    def test_set_proc_terminates_if_redundant(self, mock_process_cls):
        parent = _make_parent_worker()
        parent.redundant_flag.set()
        monitor = _make_monitor(parent)
        monitor.terminate_proc = MagicMock()
        monitor.set_proc(1234)
        monitor.terminate_proc.assert_called_once()

    def test_unset_proc_clears_subprocess(self):
        monitor = _make_monitor()
        monitor.subprocess_pid = 999
        monitor.subprocess = MagicMock()
        monitor.subprocess_percent = 50
        monitor.subprocess_elapsed = 120
        monitor.unset_proc()
        assert monitor.subprocess is None
        assert monitor.subprocess_pid is None
        assert monitor.subprocess_percent == 0
        assert monitor.subprocess_elapsed == 0


# ------------------------------------------------------------------
# WorkerSubprocessMonitor.suspend_proc / resume_proc
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestSuspendResumeProc:

    def test_suspend_proc_no_subprocess_does_not_raise(self):
        monitor = _make_monitor()
        monitor.subprocess = None
        monitor.suspend_proc()  # should not raise

    def test_suspend_proc_sets_paused_flag(self):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.return_value = []
        monitor.subprocess = mock_proc
        monitor.suspend_proc()
        assert monitor.paused is True
        mock_proc.suspend.assert_called_once()

    def test_suspend_proc_suspends_children(self):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        child1 = MagicMock()
        child2 = MagicMock()
        mock_proc.children.return_value = [child1, child2]
        monitor.subprocess = mock_proc
        monitor.suspend_proc()
        child1.suspend.assert_called_once()
        child2.suspend.assert_called_once()

    def test_resume_proc_no_subprocess_does_not_raise(self):
        monitor = _make_monitor()
        monitor.subprocess = None
        monitor.resume_proc()  # should not raise

    def test_resume_proc_clears_paused(self):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.return_value = []
        monitor.subprocess = mock_proc
        monitor.paused = True
        monitor.resume_proc()
        assert monitor.paused is False

    def test_resume_proc_terminates_if_redundant(self):
        parent = _make_parent_worker()
        parent.redundant_flag.set()
        monitor = _make_monitor(parent)
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.return_value = []
        monitor.subprocess = mock_proc
        monitor.resume_proc()
        mock_proc.terminate.assert_called()


# ------------------------------------------------------------------
# WorkerSubprocessMonitor.terminate_proc
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestTerminateProc:

    @patch('compresso.libs.workers.psutil.wait_procs', return_value=([], []))
    def test_terminate_proc_calls_tree_terminate(self, mock_wait):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.children.return_value = []
        monitor.subprocess = mock_proc
        monitor.subprocess_pid = 123
        monitor.terminate_proc()
        # After termination subprocess should be unset
        assert monitor.subprocess is None

    def test_terminate_proc_noop_when_no_subprocess(self):
        monitor = _make_monitor()
        monitor.subprocess = None
        monitor.terminate_proc()  # should not raise


# ------------------------------------------------------------------
# WorkerSubprocessMonitor.get_subprocess_elapsed
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetSubprocessElapsed:

    def test_returns_zero_when_no_subprocess(self):
        monitor = _make_monitor()
        monitor.subprocess = None
        assert monitor.get_subprocess_elapsed() == 0

    def test_returns_elapsed_minus_pause_time(self):
        monitor = _make_monitor()
        monitor.subprocess = MagicMock()  # not None
        monitor.subprocess_start_time = time.time() - 100
        monitor.subprocess_pause_time = 20
        elapsed = monitor.get_subprocess_elapsed()
        # Should be approximately 80 (100 total - 20 paused)
        assert 75 <= elapsed <= 85


# ------------------------------------------------------------------
# WorkerSubprocessMonitor.get_subprocess_stats
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetSubprocessStats:

    def test_returns_dict_with_expected_keys(self):
        monitor = _make_monitor()
        monitor.subprocess_pid = 42
        monitor.subprocess_percent = 75
        monitor.subprocess_cpu_percent = 50.0
        monitor.subprocess_mem_percent = 25.0
        monitor.subprocess_rss_bytes = 1024
        monitor.subprocess_vms_bytes = 2048
        stats = monitor.get_subprocess_stats()
        assert stats['pid'] == '42'
        assert stats['percent'] == '75'
        assert stats['cpu_percent'] == '50.0'
        assert stats['mem_percent'] == '25.0'
        assert stats['rss_bytes'] == '1024'
        assert stats['vms_bytes'] == '2048'
        assert 'elapsed' in stats


# ------------------------------------------------------------------
# WorkerSubprocessMonitor.set_subprocess_start_time / set_subprocess_percent
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestSubprocessSetters:

    def test_set_subprocess_start_time(self):
        monitor = _make_monitor()
        monitor.set_subprocess_start_time(12345.0)
        assert monitor.subprocess_start_time == 12345.0

    def test_set_subprocess_percent(self):
        monitor = _make_monitor()
        monitor.set_subprocess_percent(42)
        assert monitor.subprocess_percent == 42


# ------------------------------------------------------------------
# WorkerSubprocessMonitor.default_progress_parser
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestDefaultProgressParser:

    def test_parses_numeric_text_as_percent(self):
        monitor = _make_monitor()
        result = monitor.default_progress_parser('  75.5  ')
        assert result['percent'] == '75'
        assert monitor.subprocess_percent == 75

    def test_non_numeric_text_keeps_old_percent(self):
        monitor = _make_monitor()
        monitor.subprocess_percent = 30
        result = monitor.default_progress_parser('some log text')
        assert result['percent'] == '30'
        assert monitor.subprocess_percent == 30

    @patch('compresso.libs.workers.psutil.Process')
    def test_sets_pid_when_provided(self, mock_process_cls):
        monitor = _make_monitor()
        monitor.default_progress_parser('50', pid=999)
        mock_process_cls.assert_called_once_with(pid=999)

    def test_sets_start_time_when_provided(self):
        monitor = _make_monitor()
        monitor.default_progress_parser('50', proc_start_time=9999.0)
        assert monitor.subprocess_start_time == 9999.0

    def test_unset_calls_unset_proc(self):
        monitor = _make_monitor()
        monitor.unset_proc = MagicMock()
        result = monitor.default_progress_parser('ignored', unset=True)
        monitor.unset_proc.assert_called_once()
        assert 'killed' in result
        assert 'paused' in result

    def test_returns_killed_status_from_redundant_flag(self):
        parent = _make_parent_worker()
        parent.redundant_flag.set()
        monitor = _make_monitor(parent)
        result = monitor.default_progress_parser('50')
        assert result['killed'] is True

    def test_returns_paused_status(self):
        monitor = _make_monitor()
        monitor.paused = True
        result = monitor.default_progress_parser('50')
        assert result['paused'] is True


# ------------------------------------------------------------------
# Worker.__init__
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestWorkerInit:

    @patch('compresso.libs.workers.CompressoLogging')
    def test_worker_init_attributes(self, mock_logging):
        from compresso.libs.workers import Worker
        event = MagicMock()
        pending_q = MagicMock()
        complete_q = MagicMock()
        worker = Worker('w-0', 'TestGroup-Worker-1', 'group-1', pending_q, complete_q, event)
        assert worker.thread_id == 'w-0'
        assert worker.name == 'TestGroup-Worker-1'
        assert worker.worker_group_id == 'group-1'
        assert worker.idle is True
        assert worker.current_task is None
        assert not worker.redundant_flag.is_set()
        assert not worker.paused_flag.is_set()


# ------------------------------------------------------------------
# Worker.set_task
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestWorkerSetTask:

    @patch('compresso.libs.workers.CompressoLogging')
    def test_set_task_marks_not_idle(self, mock_logging):
        from compresso.libs.workers import Worker
        worker = Worker('w-0', 'W-1', 'g-1', MagicMock(), MagicMock(), MagicMock())
        mock_task = MagicMock()
        worker.set_task(mock_task)
        assert worker.current_task is mock_task
        assert worker.idle is False

    @patch('compresso.libs.workers.CompressoLogging')
    def test_set_task_ignores_when_task_already_set(self, mock_logging):
        from compresso.libs.workers import Worker
        worker = Worker('w-0', 'W-1', 'g-1', MagicMock(), MagicMock(), MagicMock())
        task1 = MagicMock()
        task2 = MagicMock()
        worker.set_task(task1)
        worker.set_task(task2)
        assert worker.current_task is task1


# ------------------------------------------------------------------
# Worker.get_status
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestWorkerGetStatus:

    @patch('compresso.libs.workers.CompressoLogging')
    def test_get_status_when_idle(self, mock_logging):
        from compresso.libs.workers import Worker
        worker = Worker('w-0', 'TestWorker', 'g-1', MagicMock(), MagicMock(), MagicMock())
        status = worker.get_status()
        assert status['id'] == 'w-0'
        assert status['name'] == 'TestWorker'
        assert status['idle'] is True
        assert status['paused'] is False
        assert status['current_task'] is None
        assert status['current_file'] == ''

    @patch('compresso.libs.workers.CompressoLogging')
    def test_get_status_includes_subprocess_stats(self, mock_logging):
        from compresso.libs.workers import Worker
        worker = Worker('w-0', 'W-1', 'g-1', MagicMock(), MagicMock(), MagicMock())
        mock_monitor = MagicMock()
        mock_monitor.get_subprocess_stats.return_value = {'pid': '42'}
        worker.worker_subprocess_monitor = mock_monitor
        status = worker.get_status()
        assert status['subprocess'] == {'pid': '42'}

    @patch('compresso.libs.workers.CompressoLogging')
    def test_get_status_with_current_task(self, mock_logging):
        from compresso.libs.workers import Worker
        worker = Worker('w-0', 'W-1', 'g-1', MagicMock(), MagicMock(), MagicMock())
        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 'task-123'
        mock_task.get_source_basename.return_value = 'video.mp4'
        worker.set_task(mock_task)
        status = worker.get_status()
        assert status['current_task'] == 'task-123'
        assert status['current_file'] == 'video.mp4'


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
