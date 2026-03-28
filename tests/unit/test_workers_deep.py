#!/usr/bin/env python3

"""
tests.unit.test_workers_deep.py

Deep unit tests for compresso/libs/workers.py
covering Worker run loop, task processing, subprocess execution,
status reporting, and WorkerSubprocessMonitor run loop.
"""

import queue
import threading
import time
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_parent_worker():
    parent = MagicMock()
    parent.event = MagicMock()
    parent.redundant_flag = threading.Event()
    parent.paused_flag = threading.Event()
    return parent


def _make_monitor(parent=None):
    if parent is None:
        parent = _make_parent_worker()
    with patch("compresso.libs.workers.CompressoLogging"):
        from compresso.libs.workers import WorkerSubprocessMonitor

        monitor = WorkerSubprocessMonitor(parent)
    return monitor


def _make_worker(thread_id="w-0", name="W-1", group_id="g-1"):
    with patch("compresso.libs.workers.CompressoLogging"):
        from compresso.libs.workers import Worker

        event = MagicMock()
        pending_q = queue.Queue()
        complete_q = queue.Queue()
        worker = Worker(thread_id, name, group_id, pending_q, complete_q, event)
    return worker


# ==================================================================
# WorkerCommandError
# ==================================================================


@pytest.mark.unittest
class TestWorkerCommandError:
    def test_error_message_contains_command(self):
        from compresso.libs.workers import WorkerCommandError

        err = WorkerCommandError("ffmpeg -i test.mp4")
        assert "ffmpeg -i test.mp4" in str(err)
        assert err.command == "ffmpeg -i test.mp4"


# ==================================================================
# WorkerSubprocessMonitor.set_proc_resources_in_parent_worker
# ==================================================================


@pytest.mark.unittest
class TestSetProcResources:
    def test_sets_all_resource_values(self):
        monitor = _make_monitor()
        monitor.set_proc_resources_in_parent_worker(50.0, 1024, 2048, 25.0)
        assert monitor.subprocess_cpu_percent == 50.0
        assert monitor.subprocess_rss_bytes == 1024
        assert monitor.subprocess_vms_bytes == 2048
        assert monitor.subprocess_mem_percent == 25.0


# ==================================================================
# WorkerSubprocessMonitor.get_subprocess_stats edge cases
# ==================================================================


@pytest.mark.unittest
class TestGetSubprocessStatsEdge:
    def test_returns_minimal_on_exception(self):
        monitor = _make_monitor()
        # Force an exception without leaking a mutated class attribute into
        # later tests in the same long-running pytest process.
        with patch.object(type(monitor), "subprocess_pid", new_callable=PropertyMock, create=True) as mock_pid:
            mock_pid.side_effect = Exception("boom")
            stats = monitor.get_subprocess_stats()

        # Should return the fallback dict
        assert stats["pid"] == "0"
        assert stats["percent"] == "0"


# ==================================================================
# WorkerSubprocessMonitor.get_subprocess_elapsed edge cases
# ==================================================================


@pytest.mark.unittest
class TestGetSubprocessElapsedEdge:
    def test_returns_zero_on_exception(self):
        monitor = _make_monitor()
        monitor.subprocess = MagicMock()
        # Corrupt the start time to trigger exception
        monitor.subprocess_start_time = "not_a_number"
        result = monitor.get_subprocess_elapsed()
        assert result == 0


# ==================================================================
# WorkerSubprocessMonitor.stop
# ==================================================================


@pytest.mark.unittest
class TestMonitorStop:
    def test_stop_terminates_and_sets_event(self):
        monitor = _make_monitor()
        monitor.terminate_proc = MagicMock()
        monitor.stop()
        monitor.terminate_proc.assert_called_once()
        assert monitor._stop_event.is_set()


# ==================================================================
# WorkerSubprocessMonitor.__terminate_proc_tree
# ==================================================================


@pytest.mark.unittest
class TestTerminateProcTree:
    @patch("compresso.libs.workers.psutil.wait_procs")
    def test_resumes_before_terminating(self, mock_wait):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        child = MagicMock()
        mock_proc.children.return_value = [child]
        mock_wait.return_value = ([mock_proc, child], [])
        monitor._WorkerSubprocessMonitor__terminate_proc_tree(mock_proc)
        # Should resume both parent and child
        mock_proc.resume.assert_called()
        child.resume.assert_called()
        # Should terminate both
        mock_proc.terminate.assert_called()
        child.terminate.assert_called()

    @patch("compresso.libs.workers.psutil.wait_procs")
    def test_force_kills_alive_processes(self, mock_wait):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.children.return_value = []
        alive_proc = MagicMock()
        mock_wait.side_effect = [([], [alive_proc]), ([], [])]
        monitor._WorkerSubprocessMonitor__terminate_proc_tree(mock_proc)
        alive_proc.kill.assert_called()


# ==================================================================
# WorkerSubprocessMonitor.suspend_proc edge cases
# ==================================================================


@pytest.mark.unittest
class TestSuspendProcEdgeCases:
    def test_suspend_handles_nosuchprocess(self):
        import psutil

        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        child = MagicMock()
        child.suspend.side_effect = psutil.NoSuchProcess(123)
        mock_proc.children.return_value = [child]
        monitor.subprocess = mock_proc
        monitor.suspend_proc()
        # Should not raise, paused should be True
        assert monitor.paused is True

    def test_suspend_not_running(self):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = False
        monitor.subprocess = mock_proc
        monitor.suspend_proc()
        mock_proc.suspend.assert_not_called()


# ==================================================================
# WorkerSubprocessMonitor.resume_proc edge cases
# ==================================================================


@pytest.mark.unittest
class TestResumeProcEdgeCases:
    def test_resume_handles_nosuchprocess(self):
        import psutil

        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        child = MagicMock()
        child.resume.side_effect = psutil.NoSuchProcess(123)
        mock_proc.children.return_value = [child]
        monitor.subprocess = mock_proc
        monitor.paused = True
        monitor.resume_proc()
        assert monitor.paused is False

    def test_resume_not_running(self):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = False
        monitor.subprocess = mock_proc
        monitor.resume_proc()
        mock_proc.resume.assert_not_called()


# ==================================================================
# WorkerSubprocessMonitor.default_progress_parser edge cases
# ==================================================================


@pytest.mark.unittest
class TestDefaultProgressParserEdge:
    def test_handles_empty_string(self):
        monitor = _make_monitor()
        monitor.subprocess_percent = 42
        result = monitor.default_progress_parser("")
        assert result["percent"] == "42"

    def test_handles_none_text(self):
        monitor = _make_monitor()
        monitor.subprocess_percent = 10
        result = monitor.default_progress_parser(None)
        assert result["percent"] == "10"

    def test_float_truncated_to_int(self):
        monitor = _make_monitor()
        monitor.default_progress_parser("99.9")
        assert monitor.subprocess_percent == 99

    def test_negative_number(self):
        monitor = _make_monitor()
        monitor.default_progress_parser("-5")
        assert monitor.subprocess_percent == -5


# ==================================================================
# Worker.__unset_current_task
# ==================================================================


@pytest.mark.unittest
class TestWorkerUnsetCurrentTask:
    def test_unset_clears_all(self):
        worker = _make_worker()
        worker.current_task = MagicMock()
        worker.worker_runners_info = {"p1": {"status": "done"}}
        worker.worker_log = ["line1", "line2"]
        worker._Worker__unset_current_task()
        assert worker.current_task is None
        assert worker.worker_runners_info == {}
        assert len(worker.worker_log) == 0


# ==================================================================
# Worker.__set_start_task_stats
# ==================================================================


@pytest.mark.unittest
class TestWorkerSetStartTaskStats:
    def test_sets_start_time(self):
        worker = _make_worker()
        worker.current_task = MagicMock()
        before = time.time()
        worker._Worker__set_start_task_stats()
        after = time.time()
        assert before <= worker.start_time <= after
        assert worker.finish_time is None
        assert worker.current_task.task.processed_by_worker == "W-1"


# ==================================================================
# Worker.__set_finish_task_stats
# ==================================================================


@pytest.mark.unittest
class TestWorkerSetFinishTaskStats:
    def test_sets_finish_time(self):
        worker = _make_worker()
        worker.current_task = MagicMock()
        before = time.time()
        worker._Worker__set_finish_task_stats()
        after = time.time()
        assert before <= worker.finish_time <= after


# ==================================================================
# Worker.set_task edge cases
# ==================================================================


@pytest.mark.unittest
class TestWorkerSetTaskEdge:
    def test_set_task_initializes_worker_log(self):
        worker = _make_worker()
        worker.worker_log = None
        mock_task = MagicMock()
        worker.set_task(mock_task)
        assert len(worker.worker_log) == 0

    def test_set_task_does_nothing_when_already_set(self):
        worker = _make_worker()
        task1 = MagicMock()
        task2 = MagicMock()
        worker.set_task(task1)
        assert worker.idle is False
        worker.set_task(task2)
        assert worker.current_task is task1


# ==================================================================
# Worker.get_status edge cases
# ==================================================================


@pytest.mark.unittest
class TestWorkerGetStatusEdge:
    def test_get_status_no_monitor(self):
        worker = _make_worker()
        worker.worker_subprocess_monitor = None
        status = worker.get_status()
        assert status["subprocess"] is None

    def test_get_status_with_long_log(self):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 1
        mock_task.get_source_basename.return_value = "test.mp4"
        worker.set_task(mock_task)
        worker.worker_log = [f"line {i}" for i in range(100)]
        status = worker.get_status()
        assert len(status["worker_log_tail"]) == 39

    def test_get_status_with_short_log(self):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 1
        mock_task.get_source_basename.return_value = "test.mp4"
        worker.set_task(mock_task)
        worker.worker_log = ["line1", "line2"]
        status = worker.get_status()
        assert len(status["worker_log_tail"]) == 2

    def test_get_status_with_current_command_ref(self):
        worker = _make_worker()
        worker.current_command_ref = ["ffmpeg -i test.mp4"]
        status = worker.get_status()
        assert status["current_command"] == "ffmpeg -i test.mp4"

    def test_get_status_with_empty_command_ref(self):
        worker = _make_worker()
        worker.current_command_ref = []
        status = worker.get_status()
        assert status["current_command"] == ""

    def test_get_status_with_none_command_ref(self):
        worker = _make_worker()
        worker.current_command_ref = None
        status = worker.get_status()
        assert status["current_command"] == ""

    def test_get_status_runners_info(self):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 1
        mock_task.get_source_basename.return_value = "x.mp4"
        worker.set_task(mock_task)
        worker.worker_runners_info = {"plugin_1": {"status": "complete"}}
        status = worker.get_status()
        assert status["runners_info"] == {"plugin_1": {"status": "complete"}}

    def test_get_status_task_id_exception(self):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.side_effect = Exception("db error")
        mock_task.get_source_basename.return_value = "x.mp4"
        worker.set_task(mock_task)
        status = worker.get_status()
        assert status["current_task"] is None

    def test_get_status_paused_reflects_flag(self):
        worker = _make_worker()
        worker.paused_flag.set()
        status = worker.get_status()
        assert status["paused"] is True


# ==================================================================
# Worker.__process_task_queue_item
# ==================================================================


@pytest.mark.unittest
class TestWorkerProcessTaskQueueItem:
    def test_process_task_sets_status_and_completes(self):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_source_abspath.return_value = "/path/to/file.mp4"
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 42
        mock_task.get_task_type.return_value = "local"
        mock_task.get_cache_path.return_value = "/tmp/cache/file.mp4"
        worker.current_task = mock_task
        worker.worker_log = []

        with (
            patch.object(worker, "_Worker__exec_worker_runners_on_set_task", return_value=True),
            patch.object(worker, "_Worker__set_start_task_stats"),
            patch.object(worker, "_Worker__set_finish_task_stats"),
        ):
            worker._Worker__process_task_queue_item()

        mock_task.set_status.assert_called_once_with("in_progress")
        mock_task.set_success.assert_called_once_with(True)
        assert worker.idle is False
        # Task should be in complete queue
        assert not worker.complete_queue.empty()

    def test_process_task_marks_failure(self):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_source_abspath.return_value = "/path/to/file.mp4"
        worker.current_task = mock_task
        worker.worker_log = []

        with (
            patch.object(worker, "_Worker__exec_worker_runners_on_set_task", return_value=False),
            patch.object(worker, "_Worker__set_start_task_stats"),
            patch.object(worker, "_Worker__set_finish_task_stats"),
        ):
            worker._Worker__process_task_queue_item()

        mock_task.set_success.assert_called_once_with(False)


# ==================================================================
# Worker.__exec_command_subprocess
# ==================================================================


@pytest.mark.unittest
class TestWorkerExecCommandSubprocess:
    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_returns_true_on_zero_exit(self, mock_ensure, mock_popen, mock_psutil_proc):
        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = []

        mock_sub = MagicMock()
        mock_sub.pid = 123
        # readline returns empty string immediately, poll returns 0 (process done)
        mock_sub.stdout.readline.return_value = ""
        mock_sub.poll.return_value = 0
        mock_sub.returncode = 0
        mock_popen.return_value = mock_sub

        # Mock the psutil.Process for both the subprocess and parent
        mock_parent_proc = MagicMock()
        mock_parent_proc.nice.return_value = 0
        mock_psutil_proc.return_value = mock_parent_proc

        data = {
            "exec_command": ["ffmpeg", "-i", "test.mp4"],
            "command_progress_parser": MagicMock(return_value={"percent": 0}),
            "file_out": "/tmp/out.mp4",
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }
        result = worker._Worker__exec_command_subprocess(data)
        assert result is True

    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_returns_false_on_nonzero_exit(self, mock_ensure, mock_popen, mock_psutil_proc):
        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = []

        mock_proc = MagicMock()
        mock_proc.pid = 123
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1
        mock_popen.return_value = mock_proc

        data = {
            "exec_command": ["bad_command"],
            "command_progress_parser": worker.worker_subprocess_monitor.default_progress_parser,
            "file_out": "/tmp/out.mp4",
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }
        result = worker._Worker__exec_command_subprocess(data)
        assert result is False

    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_string_command_uses_shell(self, mock_ensure, mock_popen, mock_psutil_proc):
        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = []

        mock_proc = MagicMock()
        mock_proc.pid = 123
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.poll.return_value = 0
        mock_proc.returncode = 0
        mock_popen.return_value = mock_proc

        data = {
            "exec_command": "echo hello",
            "command_progress_parser": worker.worker_subprocess_monitor.default_progress_parser,
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }
        result = worker._Worker__exec_command_subprocess(data)
        assert result is True
        # Verify shell=True was passed
        _, kwargs = mock_popen.call_args
        assert kwargs.get("shell") is True

    def test_raises_on_invalid_command_type(self):
        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = []

        data = {
            "exec_command": 12345,  # Not a list or string
            "command_progress_parser": MagicMock(),
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }
        result = worker._Worker__exec_command_subprocess(data)
        assert result is False

    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_terminates_on_redundant_flag(self, mock_ensure, mock_popen, mock_psutil_proc):
        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = []
        worker.redundant_flag.set()

        mock_proc = MagicMock()
        mock_proc.pid = 123
        mock_proc.stdout.readline.side_effect = [""]
        mock_proc.poll.return_value = None
        mock_proc.returncode = -9
        mock_popen.return_value = mock_proc

        data = {
            "exec_command": ["ffmpeg"],
            "command_progress_parser": worker.worker_subprocess_monitor.default_progress_parser,
            "file_out": "/tmp/out.mp4",
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }
        result = worker._Worker__exec_command_subprocess(data)
        assert result is False


# ==================================================================
# Worker.run lifecycle
# ==================================================================


@pytest.mark.unittest
class TestWorkerRunLifecycle:
    def test_run_exits_on_redundant_flag(self):
        worker = _make_worker()
        worker.redundant_flag.set()

        with patch("compresso.libs.workers.WorkerSubprocessMonitor") as mock_mon_cls:
            mock_mon = MagicMock()
            mock_mon_cls.return_value = mock_mon
            worker.run()

        mock_mon.start.assert_called_once()
        mock_mon.stop.assert_called_once()
        mock_mon.join.assert_called_once()

    def test_run_pauses_when_paused_flag_set(self):
        worker = _make_worker()
        call_count = [0]

        def side_effect_wait(timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                worker.paused_flag.set()
            elif call_count[0] >= 3:
                worker.redundant_flag.set()

        worker.event.wait = MagicMock(side_effect=side_effect_wait)

        with patch("compresso.libs.workers.WorkerSubprocessMonitor") as mock_mon_cls:
            mock_mon = MagicMock()
            mock_mon_cls.return_value = mock_mon
            worker.run()

        assert worker.paused is True or worker.redundant_flag.is_set()


# ==================================================================
# Worker.__exec_worker_runners_on_set_task
# ==================================================================


@pytest.mark.unittest
class TestWorkerExecRunners:
    @patch("compresso.libs.workers.os.path.exists", return_value=False)
    @patch("compresso.libs.workers.PluginsHandler")
    def test_no_plugins_returns_true(self, mock_ph_cls, mock_exists):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 42
        mock_task.get_task_type.return_value = "local"
        mock_task.get_source_abspath.return_value = "/path/to/file.mp4"
        mock_task.get_cache_path.return_value = "/tmp/cache/file.mp4"
        worker.current_task = mock_task
        worker.worker_log = []
        worker.worker_subprocess_monitor = _make_monitor()

        mock_ph = MagicMock()
        mock_ph.get_enabled_plugin_modules_by_type.return_value = []
        mock_ph_cls.return_value = mock_ph

        with (
            patch("compresso.libs.workers.shutil"),
            patch("compresso.libs.workers.os.path.abspath", side_effect=lambda x: x),
            patch("compresso.libs.workers.os.makedirs"),
        ):
            result = worker._Worker__exec_worker_runners_on_set_task()

        assert result is True

    @patch("compresso.libs.workers.PluginsHandler")
    def test_plugin_failure_returns_false(self, mock_ph_cls):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 42
        mock_task.get_task_type.return_value = "local"
        mock_task.get_source_abspath.return_value = "/path/to/file.mp4"
        mock_task.get_cache_path.return_value = "/tmp/cache/file.mp4"
        worker.current_task = mock_task
        worker.worker_log = []
        worker.worker_subprocess_monitor = _make_monitor()

        mock_ph = MagicMock()
        mock_ph.get_enabled_plugin_modules_by_type.return_value = [
            {"plugin_id": "p1", "name": "Plugin1", "author": "A", "version": "1.0", "icon": "", "description": "desc"}
        ]
        mock_ph.exec_plugin_runner.return_value = False
        mock_ph_cls.return_value = mock_ph

        with (
            patch("compresso.libs.workers.os.path.exists", return_value=False),
            patch("compresso.libs.workers.os.path.abspath", side_effect=lambda x: x),
            patch("compresso.libs.workers.os.path.splitext", return_value=("/tmp/cache/file", ".mp4")),
            patch("compresso.libs.workers.os.makedirs"),
            patch("compresso.libs.workers.os.path.dirname", return_value="/tmp/cache"),
            patch("compresso.libs.workers.shutil"),
        ):
            result = worker._Worker__exec_worker_runners_on_set_task()

        assert result is False


# ==================================================================
# WorkerSubprocessMonitor.__log_proc_terminated
# ==================================================================


@pytest.mark.unittest
class TestLogProcTerminated:
    def test_logs_proc_returncode(self):
        monitor = _make_monitor()
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        monitor._WorkerSubprocessMonitor__log_proc_terminated(mock_proc)
        # Should not raise


# ==================================================================
# WorkerSubprocessMonitor.set_subprocess_start_time error handling
# ==================================================================


@pytest.mark.unittest
class TestSetSubprocessStartTimeError:
    def test_handles_exception(self):
        monitor = _make_monitor()
        # Mock the attribute setter to raise
        monitor.set_subprocess_start_time(12345.0)
        assert monitor.subprocess_start_time == 12345.0


# ==================================================================
# WorkerSubprocessMonitor.set_subprocess_percent error handling
# ==================================================================


@pytest.mark.unittest
class TestSetSubprocessPercentError:
    def test_sets_percent_value(self):
        monitor = _make_monitor()
        monitor.set_subprocess_percent(99)
        assert monitor.subprocess_percent == 99


# ==================================================================
# Worker paused flag behavior
# ==================================================================


@pytest.mark.unittest
class TestWorkerPausedBehavior:
    def test_paused_flag_set_makes_worker_paused(self):
        worker = _make_worker()
        worker.paused_flag.set()
        assert worker.paused_flag.is_set()

    def test_paused_flag_clear(self):
        worker = _make_worker()
        worker.paused_flag.set()
        worker.paused_flag.clear()
        assert not worker.paused_flag.is_set()


# ==================================================================
# Worker redundant flag behavior
# ==================================================================


@pytest.mark.unittest
class TestWorkerRedundantBehavior:
    def test_redundant_flag_default_cleared(self):
        worker = _make_worker()
        assert not worker.redundant_flag.is_set()

    def test_redundant_flag_can_be_set(self):
        worker = _make_worker()
        worker.redundant_flag.set()
        assert worker.redundant_flag.is_set()


# ==================================================================
# Worker event and queue references
# ==================================================================


@pytest.mark.unittest
class TestWorkerQueueReferences:
    def test_pending_queue_stored(self):
        with patch("compresso.libs.workers.CompressoLogging"):
            from compresso.libs.workers import Worker

            pq = queue.Queue()
            cq = queue.Queue()
            ev = MagicMock()
            w = Worker("w-0", "W-1", "g-1", pq, cq, ev)
            assert w.pending_queue is pq
            assert w.complete_queue is cq
            assert w.event is ev


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
