#!/usr/bin/env python3

"""
tests.unit.test_workers_coverage.py

Focused coverage tests for compresso/libs/workers.py targeting
the specific uncovered lines:
  100-116  : Worker.run() — paused=False path + inner task loop + exception handlers
  148-149  : get_status() — current_command_ref exception handler
  168      : get_status() — get_task_id() AttributeError/KeyError/TypeError handler
  175-178  : get_status() — get_source_basename() exception handlers
  186-187  : get_status() — worker_log exception handler
  192-193  : get_status() — runners_info exception handler
  226-233  : __process_task_queue_item() — encoding speed from subprocess monitor
  353      : __exec_worker_runners_on_set_task() — break when overall_success already False
  399-402  : runner thread monitoring — redundant_flag check while alive
  406-410  : runner thread shutdown — redundant_flag detected after plugin thread
  428-513  : exec_command path, file move logic, repeat loop, no-exec path
  569-575  : final move OSError path
  672      : __exec_command_subprocess() — Windows priority path (os.name == 'nt')
  676-677  : __exec_command_subprocess() — psutil priority exception handler
  687-693  : __exec_command_subprocess() — paused flag inner loop
  705-715  : __exec_command_subprocess() — progress parsing + exception in parser
  721-723  : __exec_command_subprocess() — communicate() timeout handler
"""

import queue
import subprocess
import threading
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


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


def _make_plugin_module(plugin_id="p1"):
    return {
        "plugin_id": plugin_id,
        "name": f"Plugin {plugin_id}",
        "author": "Author",
        "version": "1.0",
        "icon": "",
        "description": "desc",
    }


# ---------------------------------------------------------------------------
# Lines 100-116: Worker.run() — paused=False path + inner task processing loop
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestWorkerRunNotPausedPath:
    """Cover lines 100-103: the paused=False branch + idle=True in run()."""

    def test_run_sets_paused_false_and_idle_true_before_exit(self):
        """After the paused flag clears, run() sets paused=False and idle=True."""
        worker = _make_worker()
        call_count = [0]

        def side_effect(timeout=None):
            call_count[0] += 1
            if call_count[0] >= 2:
                worker.redundant_flag.set()

        worker.event.wait = MagicMock(side_effect=side_effect)

        with patch("compresso.libs.workers.WorkerSubprocessMonitor") as mock_mon_cls:
            mock_mon = MagicMock()
            mock_mon_cls.return_value = mock_mon
            worker.run()

        assert worker.paused is False
        assert worker.redundant_flag.is_set()

    def test_run_inner_task_loop_processes_current_task(self):
        """Lines 106-116: inner while loop executes when current_task is set."""
        worker = _make_worker()
        processed = []

        def fake_process():
            processed.append(True)
            # Clear the task to exit the inner while loop
            worker.current_task = None

        call_count = [0]

        def side_effect(timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                # First outer wait — set a task so the inner loop runs
                worker.current_task = MagicMock()
            elif call_count[0] >= 4:
                worker.redundant_flag.set()

        worker.event.wait = MagicMock(side_effect=side_effect)

        with (
            patch("compresso.libs.workers.WorkerSubprocessMonitor") as mock_mon_cls,
            patch.object(worker, "_Worker__process_task_queue_item", side_effect=fake_process),
        ):
            mock_mon = MagicMock()
            mock_mon_cls.return_value = mock_mon
            worker.run()

        assert processed, "Inner task loop should have called __process_task_queue_item"

    def test_run_inner_loop_handles_queue_empty_exception(self):
        """Line 112-113: queue.Empty is caught and the inner loop continues."""
        worker = _make_worker()
        call_count = [0]
        exception_raised = []

        def fake_process():
            exception_raised.append(True)
            worker.current_task = None
            raise queue.Empty()

        def side_effect(timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                worker.current_task = MagicMock()
            elif call_count[0] >= 5:
                worker.redundant_flag.set()
                worker.current_task = None

        worker.event.wait = MagicMock(side_effect=side_effect)

        with (
            patch("compresso.libs.workers.WorkerSubprocessMonitor") as mock_mon_cls,
            patch.object(worker, "_Worker__process_task_queue_item", side_effect=fake_process),
        ):
            mock_mon = MagicMock()
            mock_mon_cls.return_value = mock_mon
            worker.run()

        assert exception_raised

    def test_run_inner_loop_handles_generic_exception(self):
        """Lines 114-116: generic Exception is caught without crashing run()."""
        worker = _make_worker()
        call_count = [0]
        exception_raised = []

        def fake_process():
            exception_raised.append(True)
            worker.current_task = None
            raise RuntimeError("unexpected error")

        def side_effect(timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                worker.current_task = MagicMock()
            elif call_count[0] >= 5:
                worker.redundant_flag.set()
                worker.current_task = None

        worker.event.wait = MagicMock(side_effect=side_effect)

        with (
            patch("compresso.libs.workers.WorkerSubprocessMonitor") as mock_mon_cls,
            patch.object(worker, "_Worker__process_task_queue_item", side_effect=fake_process),
        ):
            mock_mon = MagicMock()
            mock_mon_cls.return_value = mock_mon
            worker.run()

        assert exception_raised


# ---------------------------------------------------------------------------
# Lines 148-149: get_status() — current_command_ref raises AttributeError/TypeError
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetStatusCurrentCommandRefException:
    def test_attribute_error_on_command_ref_is_caught(self):
        """Line 148-149: IndexError when accessing current_command_ref[-1]."""
        worker = _make_worker()
        # A truthy object that raises IndexError on [-1] access
        bad_ref = MagicMock()
        bad_ref.__bool__ = lambda self: True
        bad_ref.__getitem__ = MagicMock(side_effect=IndexError("bad"))
        worker.current_command_ref = bad_ref
        # Should not raise
        status = worker.get_status()
        assert status["current_command"] == ""

    def test_type_error_on_command_ref_is_caught(self):
        """Line 148-149: TypeError is caught gracefully."""
        worker = _make_worker()
        bad_ref = MagicMock()
        bad_ref.__bool__ = lambda self: True
        bad_ref.__getitem__ = MagicMock(side_effect=TypeError("bad type"))
        worker.current_command_ref = bad_ref
        status = worker.get_status()
        assert status["current_command"] == ""


# ---------------------------------------------------------------------------
# Line 168: get_status() — get_task_id() raises AttributeError/KeyError/TypeError
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetStatusTaskIdExceptions:
    def test_attribute_error_in_get_task_id_is_caught(self):
        """Line 168: AttributeError in get_task_id() leaves current_task as None."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.side_effect = AttributeError("no attr")
        mock_task.get_source_basename.return_value = "file.mp4"
        worker.set_task(mock_task)
        status = worker.get_status()
        assert status["current_task"] is None

    def test_key_error_in_get_task_id_is_caught(self):
        """Line 168: KeyError in get_task_id() leaves current_task as None."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.side_effect = KeyError("missing")
        mock_task.get_source_basename.return_value = "file.mp4"
        worker.set_task(mock_task)
        status = worker.get_status()
        assert status["current_task"] is None

    def test_type_error_in_get_task_id_is_caught(self):
        """Line 168: TypeError in get_task_id() leaves current_task as None."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.side_effect = TypeError("bad type")
        mock_task.get_source_basename.return_value = "file.mp4"
        worker.set_task(mock_task)
        status = worker.get_status()
        assert status["current_task"] is None


# ---------------------------------------------------------------------------
# Lines 175-178: get_status() — get_source_basename() exception handlers
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetStatusSourceBasenameExceptions:
    def test_attribute_error_in_get_source_basename_is_caught(self):
        """Line 175-176: AttributeError in get_source_basename() is caught."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 1
        mock_task.get_source_basename.side_effect = AttributeError("no attr")
        worker.set_task(mock_task)
        status = worker.get_status()
        assert status["current_file"] == ""

    def test_unexpected_exception_in_get_source_basename_is_caught(self):
        """Line 177-178: Generic Exception in get_source_basename() is caught."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 1
        mock_task.get_source_basename.side_effect = RuntimeError("unexpected")
        worker.set_task(mock_task)
        status = worker.get_status()
        assert status["current_file"] == ""


# ---------------------------------------------------------------------------
# Lines 186-187: get_status() — worker_log exception handler
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetStatusWorkerLogException:
    def test_type_error_in_worker_log_is_caught(self):
        """Lines 186-187: TypeError when iterating worker_log is caught."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 1
        mock_task.get_source_basename.return_value = "x.mp4"
        worker.set_task(mock_task)
        # Replace worker_log with something that raises on len()
        bad_log = MagicMock()
        bad_log.__bool__ = lambda self: True
        bad_log.__len__ = MagicMock(side_effect=TypeError("bad len"))
        worker.worker_log = bad_log
        status = worker.get_status()
        assert status["worker_log_tail"] == []


# ---------------------------------------------------------------------------
# Lines 192-193: get_status() — runners_info exception handler
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetStatusRunnersInfoException:
    def test_attribute_error_in_runners_info_is_caught(self):
        """Lines 192-193: AttributeError in runners_info access is caught."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 1
        mock_task.get_source_basename.return_value = "x.mp4"
        worker.set_task(mock_task)
        worker.worker_log = deque(maxlen=500)

        # Make worker_runners_info a property that raises
        def _raise_attr(self):
            raise AttributeError("no attr")

        with patch.object(type(worker), "worker_runners_info", new_callable=lambda: property(_raise_attr)):
            status = worker.get_status()
        assert status["runners_info"] == {}


# ---------------------------------------------------------------------------
# Lines 226-233: __process_task_queue_item() — encoding speed stats branch
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestProcessTaskEncodingSpeedStats:
    def test_encoding_speed_stats_stored_when_monitor_present(self):
        """Lines 226-233: encoding speed is stored on task.statistics when monitor is set."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_source_abspath.return_value = "/tmp/file.mp4"
        mock_task.statistics = {}
        worker.current_task = mock_task
        worker.worker_log = deque(maxlen=500)

        mock_monitor = _make_monitor()
        mock_monitor.get_encoding_speed_stats = MagicMock(return_value={"avg_encoding_fps": 25.0, "encoding_speed_ratio": 1.5})
        mock_monitor.get_subprocess_elapsed = MagicMock(return_value=120)
        mock_monitor.reset_encoding_speed_stats = MagicMock()
        worker.worker_subprocess_monitor = mock_monitor

        with (
            patch.object(worker, "_Worker__exec_worker_runners_on_set_task", return_value=True),
            patch.object(worker, "_Worker__set_start_task_stats"),
            patch.object(worker, "_Worker__set_finish_task_stats"),
        ):
            worker._Worker__process_task_queue_item()

        assert mock_task.statistics["encoding_speed"]["avg_encoding_fps"] == 25.0
        assert mock_task.statistics["encoding_speed"]["encoding_speed_ratio"] == 1.5
        assert mock_task.statistics["encoding_speed"]["encoding_duration_seconds"] == 120
        mock_monitor.reset_encoding_speed_stats.assert_called_once()

    def test_encoding_speed_stats_zero_when_monitor_is_none(self):
        """Lines 234-239: encoding speed falls back to zeros when monitor is None."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_source_abspath.return_value = "/tmp/file.mp4"
        mock_task.statistics = {}
        worker.current_task = mock_task
        worker.worker_log = deque(maxlen=500)
        worker.worker_subprocess_monitor = None

        with (
            patch.object(worker, "_Worker__exec_worker_runners_on_set_task", return_value=True),
            patch.object(worker, "_Worker__set_start_task_stats"),
            patch.object(worker, "_Worker__set_finish_task_stats"),
        ):
            worker._Worker__process_task_queue_item()

        assert mock_task.statistics["encoding_speed"]["avg_encoding_fps"] == 0
        assert mock_task.statistics["encoding_speed"]["encoding_speed_ratio"] == 0
        assert mock_task.statistics["encoding_speed"]["encoding_duration_seconds"] == 0


# ---------------------------------------------------------------------------
# Line 353: __exec_worker_runners_on_set_task() — break on overall_success=False
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecRunnerBreakOnFailure:
    def test_second_plugin_skipped_when_first_fails(self):
        """Line 353: If overall_success is False entering a plugin iteration, we break."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 42
        mock_task.get_task_type.return_value = "local"
        mock_task.get_source_abspath.return_value = "/path/file.mp4"
        mock_task.get_cache_path.return_value = "/tmp/cache/file.mp4"
        worker.current_task = mock_task
        worker.worker_log = deque(maxlen=500)
        worker.worker_subprocess_monitor = _make_monitor()

        plugin1 = _make_plugin_module("p1")
        plugin2 = _make_plugin_module("p2")

        exec_call_count = [0]

        def fake_exec_plugin(data, runner_id, plugin_type):
            exec_call_count[0] += 1
            return False  # first plugin fails

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [plugin1, plugin2]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
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

        # Only one plugin should have been called — the second is skipped by line 353 break
        assert exec_call_count[0] == 1
        assert result is False


# ---------------------------------------------------------------------------
# Lines 399-402, 406-410: redundant_flag during plugin thread execution
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecRunnerRedundantFlagDuringThread:
    def test_redundant_flag_aborts_during_thread_monitoring(self):
        """Lines 399-410: redundant_flag set while monitoring runner thread marks failure.

        The plugin thread must still be alive when the monitoring loop checks the redundant
        flag. We use a threading.Event to hold the plugin thread until the monitoring loop
        has seen it alive, then we let the thread finish after setting the flag.
        """
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 42
        mock_task.get_task_type.return_value = "local"
        mock_task.get_source_abspath.return_value = "/path/file.mp4"
        mock_task.get_cache_path.return_value = "/tmp/cache/file.mp4"
        worker.current_task = mock_task
        worker.worker_log = deque(maxlen=500)
        worker.worker_subprocess_monitor = _make_monitor()

        plugin1 = _make_plugin_module("p1")

        # plugin_started signals when plugin is running; release_plugin lets it finish
        plugin_started = threading.Event()
        release_plugin = threading.Event()

        def blocking_plugin(data, runner_id, plugin_type):
            plugin_started.set()
            release_plugin.wait(timeout=5)
            return True

        # Patch event.wait so that the first call (timeout=0.2 in monitoring loop)
        # sets the redundant flag and releases the plugin thread.
        event_wait_count = [0]

        def fake_event_wait(timeout=None):
            event_wait_count[0] += 1
            # After a brief wait, trigger redundant flag and unblock the plugin
            worker.redundant_flag.set()
            release_plugin.set()

        worker.event.wait = MagicMock(side_effect=fake_event_wait)

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [plugin1]
            mock_ph.exec_plugin_runner.side_effect = blocking_plugin
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
        # The log should contain the termination message
        assert any("WORKER TERMINATED" in str(entry) for entry in worker.worker_log)


# ---------------------------------------------------------------------------
# Lines 428-513: exec_command path, no-exec path, file move, repeat flag
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecRunnerWithExecCommand:
    def _setup_worker_with_one_plugin(self, plugin_id="p1"):
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 42
        mock_task.get_task_type.return_value = "local"
        mock_task.get_source_abspath.return_value = "/src/file.mp4"
        mock_task.get_cache_path.return_value = "/tmp/cache/file.mp4"
        worker.current_task = mock_task
        worker.worker_log = deque(maxlen=500)
        worker.worker_subprocess_monitor = _make_monitor()
        return worker

    def test_exec_command_success_updates_file_in(self):
        """Lines 432-483: exec_command triggers subprocess; on success file_in advances."""
        worker = self._setup_worker_with_one_plugin()

        def fake_exec_plugin(data, runner_id, plugin_type):
            data["exec_command"] = ["echo", "hello"]
            data["file_out"] = "/tmp/output.mp4"
            return True

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [_make_plugin_module()]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
            mock_ph_cls.return_value = mock_ph

            with (
                patch.object(worker, "_Worker__exec_command_subprocess", return_value=True) as mock_exec,
                patch("compresso.libs.workers.os.path.exists", return_value=True),
                patch("compresso.libs.workers.os.path.abspath", side_effect=lambda x: x),
                patch("compresso.libs.workers.os.path.splitext", return_value=("/tmp/cache/file", ".mp4")),
                patch("compresso.libs.workers.os.makedirs"),
                patch("compresso.libs.workers.os.path.dirname", return_value="/tmp/cache"),
                patch("compresso.libs.workers.shutil"),
            ):
                result = worker._Worker__exec_worker_runners_on_set_task()

        assert result is True
        mock_exec.assert_called_once()

    def test_exec_command_failure_marks_overall_failure(self):
        """Lines 484-489: subprocess failure sets overall_success=False."""
        worker = self._setup_worker_with_one_plugin()

        def fake_exec_plugin(data, runner_id, plugin_type):
            data["exec_command"] = ["bad_cmd"]
            data["file_out"] = "/tmp/output.mp4"
            return True

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [_make_plugin_module()]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
            mock_ph_cls.return_value = mock_ph

            with (
                patch.object(worker, "_Worker__exec_command_subprocess", return_value=False),
                patch("compresso.libs.workers.os.path.exists", return_value=False),
                patch("compresso.libs.workers.os.path.abspath", side_effect=lambda x: x),
                patch("compresso.libs.workers.os.path.splitext", return_value=("/tmp/cache/file", ".mp4")),
                patch("compresso.libs.workers.os.makedirs"),
                patch("compresso.libs.workers.os.path.dirname", return_value="/tmp/cache"),
                patch("compresso.libs.workers.shutil"),
            ):
                result = worker._Worker__exec_worker_runners_on_set_task()

        assert result is False

    def test_no_exec_command_logs_no_command_message(self):
        """Lines 490-495: plugin returns no exec_command — logs appropriate message."""
        worker = self._setup_worker_with_one_plugin()

        def fake_exec_plugin(data, runner_id, plugin_type):
            # Do NOT set exec_command
            data["exec_command"] = []
            return True

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [_make_plugin_module()]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
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

        # Overall should succeed (no command = still "success" path)
        assert result is True
        assert any("did not request" in str(entry) for entry in worker.worker_log)

    def test_exec_command_with_null_file_out_uses_file_in(self):
        """Lines 460-463: file_out=None after success — file_in stays as-is."""
        worker = self._setup_worker_with_one_plugin()

        def fake_exec_plugin(data, runner_id, plugin_type):
            data["exec_command"] = ["echo", "hello"]
            data["file_out"] = None  # plugin signals in-place modification
            return True

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [_make_plugin_module()]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
            mock_ph_cls.return_value = mock_ph

            with (
                patch.object(worker, "_Worker__exec_command_subprocess", return_value=True),
                patch("compresso.libs.workers.os.path.exists", return_value=False),
                patch("compresso.libs.workers.os.path.abspath", side_effect=lambda x: x),
                patch("compresso.libs.workers.os.path.splitext", return_value=("/tmp/cache/file", ".mp4")),
                patch("compresso.libs.workers.os.makedirs"),
                patch("compresso.libs.workers.os.path.dirname", return_value="/tmp/cache"),
                patch("compresso.libs.workers.shutil"),
            ):
                result = worker._Worker__exec_worker_runners_on_set_task()

        assert result is True

    def test_exec_command_redundant_flag_after_subprocess(self):
        """Lines 440-452: redundant flag set after subprocess marks failure."""
        worker = self._setup_worker_with_one_plugin()

        def fake_exec_plugin(data, runner_id, plugin_type):
            data["exec_command"] = ["echo", "hello"]
            data["file_out"] = "/tmp/out.mp4"
            return True

        def fake_exec_subprocess(data):
            worker.redundant_flag.set()
            return False

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [_make_plugin_module()]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
            mock_ph_cls.return_value = mock_ph

            with (
                patch.object(worker, "_Worker__exec_command_subprocess", side_effect=fake_exec_subprocess),
                patch("compresso.libs.workers.os.path.exists", return_value=False),
                patch("compresso.libs.workers.os.path.abspath", side_effect=lambda x: x),
                patch("compresso.libs.workers.os.path.splitext", return_value=("/tmp/cache/file", ".mp4")),
                patch("compresso.libs.workers.os.makedirs"),
                patch("compresso.libs.workers.os.path.dirname", return_value="/tmp/cache"),
                patch("compresso.libs.workers.shutil"),
            ):
                result = worker._Worker__exec_worker_runners_on_set_task()

        assert result is False
        assert any("WORKER TERMINATED" in str(entry) for entry in worker.worker_log)

    def test_repeat_flag_runs_plugin_twice(self):
        """Lines 509-513: repeat=True causes another pass through the same plugin."""
        worker = self._setup_worker_with_one_plugin()
        call_count = [0]

        def fake_exec_plugin(data, runner_id, plugin_type):
            call_count[0] += 1
            data["exec_command"] = []
            # Set repeat on first call, clear on second
            data["repeat"] = call_count[0] == 1
            return True

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [_make_plugin_module()]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
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

        assert call_count[0] == 2
        assert result is True

    def test_file_out_current_file_out_tracking(self):
        """Lines 497-503: current_file_out follows file_out when it exists."""
        worker = self._setup_worker_with_one_plugin()

        def fake_exec_plugin(data, runner_id, plugin_type):
            data["exec_command"] = ["echo", "hello"]
            data["file_out"] = "/tmp/existing_output.mp4"
            return True

        def mock_exists(path):
            return path == "/tmp/existing_output.mp4"

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [_make_plugin_module()]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
            mock_ph_cls.return_value = mock_ph

            with (
                patch.object(worker, "_Worker__exec_command_subprocess", return_value=True),
                patch("compresso.libs.workers.os.path.exists", side_effect=mock_exists),
                patch("compresso.libs.workers.os.path.abspath", side_effect=lambda x: x),
                patch("compresso.libs.workers.os.path.splitext", return_value=("/tmp/cache/file", ".mp4")),
                patch("compresso.libs.workers.os.makedirs"),
                patch("compresso.libs.workers.os.path.dirname", return_value="/tmp/cache"),
                patch("compresso.libs.workers.shutil"),
            ):
                result = worker._Worker__exec_worker_runners_on_set_task()

        assert result is True


# ---------------------------------------------------------------------------
# Lines 569-575: final move OSError handler
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecRunnerFinalMoveError:
    def test_os_error_in_final_move_returns_false(self):
        """Lines 569-575: OSError during shutil.move sets overall_success=False."""
        worker = _make_worker()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 42
        mock_task.get_task_type.return_value = "local"
        mock_task.get_source_abspath.return_value = "/src/original.mp4"
        mock_task.get_cache_path.return_value = "/tmp/cache/file.mp4"
        worker.current_task = mock_task
        worker.worker_log = deque(maxlen=500)
        worker.worker_subprocess_monitor = _make_monitor()

        def fake_exec_plugin(data, runner_id, plugin_type):
            data["exec_command"] = []  # No exec, so file doesn't actually move
            return True

        with patch("compresso.libs.workers.PluginsHandler") as mock_ph_cls:
            mock_ph = MagicMock()
            mock_ph.get_enabled_plugin_modules_by_type.return_value = [_make_plugin_module()]
            mock_ph.exec_plugin_runner.side_effect = fake_exec_plugin
            mock_ph_cls.return_value = mock_ph

            with (
                patch("compresso.libs.workers.os.path.exists", return_value=True),
                patch("compresso.libs.workers.os.path.abspath", side_effect=lambda x: x),
                patch("compresso.libs.workers.os.path.splitext", return_value=("/tmp/cache/file", ".mp4")),
                patch("compresso.libs.workers.os.makedirs"),
                patch("compresso.libs.workers.os.path.dirname", return_value="/tmp/cache"),
                # shutil.copyfile raises OSError to trigger the error path
                patch("compresso.libs.workers.shutil.copyfile", side_effect=OSError("disk full")),
                patch("compresso.libs.workers.shutil.move", side_effect=OSError("disk full")),
            ):
                result = worker._Worker__exec_worker_runners_on_set_task()

        assert result is False


# ---------------------------------------------------------------------------
# Lines 672: __exec_command_subprocess() — Windows priority path
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecCommandSubprocessPriority:
    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_windows_nice_priority_is_set(self, mock_ensure, mock_popen, mock_psutil_proc):
        """Line 672: On Windows (os.name='nt'), proc.nice() is called with BELOW_NORMAL."""
        import psutil

        # BELOW_NORMAL_PRIORITY_CLASS only exists on Windows; mock it for cross-platform tests
        below_normal = getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000)

        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = deque(maxlen=500)

        mock_sub = MagicMock()
        mock_sub.pid = 123
        mock_sub.stdout.readline.return_value = ""
        mock_sub.poll.return_value = 0
        mock_sub.returncode = 0
        mock_popen.return_value = mock_sub

        mock_proc = MagicMock()
        mock_psutil_proc.return_value = mock_proc

        data = {
            "exec_command": ["echo", "hi"],
            "command_progress_parser": MagicMock(return_value={"percent": 0}),
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }

        with (
            patch("compresso.libs.workers.os.name", "nt"),
            patch("compresso.libs.workers.psutil.BELOW_NORMAL_PRIORITY_CLASS", below_normal, create=True),
        ):
            result = worker._Worker__exec_command_subprocess(data)

        assert result is True
        mock_proc.nice.assert_called_with(below_normal)

    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_priority_exception_is_caught_and_logged(self, mock_ensure, mock_popen, mock_psutil_proc):
        """Lines 676-677: psutil.AccessDenied during nice() is caught without failure."""
        import psutil

        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = deque(maxlen=500)

        mock_sub = MagicMock()
        mock_sub.pid = 123
        mock_sub.stdout.readline.return_value = ""
        mock_sub.poll.return_value = 0
        mock_sub.returncode = 0
        mock_popen.return_value = mock_sub

        mock_proc = MagicMock()
        mock_proc.nice.side_effect = psutil.AccessDenied(pid=123)
        mock_psutil_proc.return_value = mock_proc

        data = {
            "exec_command": ["echo", "hi"],
            "command_progress_parser": MagicMock(return_value={"percent": 0}),
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }

        with patch("compresso.libs.workers.os.name", "posix"):
            result = worker._Worker__exec_command_subprocess(data)

        # Despite the AccessDenied, the command should still complete successfully
        assert result is True

    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_no_such_process_on_nice_is_caught(self, mock_ensure, mock_popen, mock_psutil_proc):
        """Lines 676-677: psutil.NoSuchProcess during nice() is caught."""
        import psutil

        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = deque(maxlen=500)

        mock_sub = MagicMock()
        mock_sub.pid = 123
        mock_sub.stdout.readline.return_value = ""
        mock_sub.poll.return_value = 0
        mock_sub.returncode = 0
        mock_popen.return_value = mock_sub

        mock_proc = MagicMock()
        mock_proc.nice.side_effect = psutil.NoSuchProcess(pid=123)
        mock_psutil_proc.return_value = mock_proc

        data = {
            "exec_command": ["echo"],
            "command_progress_parser": MagicMock(return_value={"percent": 0}),
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }

        with patch("compresso.libs.workers.os.name", "posix"):
            result = worker._Worker__exec_command_subprocess(data)

        assert result is True


# ---------------------------------------------------------------------------
# Lines 687-693: __exec_command_subprocess() — paused flag inner loop
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecCommandSubprocessPausedFlag:
    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_paused_flag_suspends_subprocess_loop(self, mock_ensure, mock_popen, mock_psutil_proc):
        """Lines 687-693: when paused_flag is set, the inner pause loop runs."""
        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = deque(maxlen=500)

        call_count = [0]

        def readline_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                # Trigger the paused path
                worker.paused_flag.set()
                return "some output line"
            elif call_count[0] == 2:
                # Resume and return empty to end the loop
                worker.paused_flag.clear()
                return ""
            return ""

        def poll_side_effect():
            if call_count[0] >= 2:
                return 0
            return None

        mock_sub = MagicMock()
        mock_sub.pid = 123
        mock_sub.stdout.readline.side_effect = readline_side_effect
        mock_sub.poll.side_effect = poll_side_effect
        mock_sub.returncode = 0
        mock_popen.return_value = mock_sub

        mock_proc = MagicMock()
        mock_psutil_proc.return_value = mock_proc

        event_wait_count = [0]

        def event_wait_side_effect(timeout=None):
            event_wait_count[0] += 1
            # After a few inner-pause-loop waits, clear the paused flag
            if event_wait_count[0] >= 2:
                worker.paused_flag.clear()

        worker.event.wait = MagicMock(side_effect=event_wait_side_effect)

        data = {
            "exec_command": ["echo", "test"],
            "command_progress_parser": MagicMock(return_value={"percent": 50}),
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }

        result = worker._Worker__exec_command_subprocess(data)
        # The inner pause loop was entered (event.wait was called)
        assert event_wait_count[0] >= 1
        assert result is True


# ---------------------------------------------------------------------------
# Lines 705-715: progress parsing + exception in parser
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecCommandSubprocessProgressParsing:
    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_progress_parser_exception_is_caught(self, mock_ensure, mock_popen, mock_psutil_proc):
        """Lines 712-715: ValueError from progress parser is caught without crashing."""
        worker = _make_worker()
        worker.worker_subprocess_monitor = _make_monitor()
        worker.worker_log = deque(maxlen=500)

        read_count = [0]

        def readline_side_effect():
            read_count[0] += 1
            if read_count[0] == 1:
                return "75.0"
            return ""

        def poll_side_effect():
            return 0 if read_count[0] >= 2 else None

        mock_sub = MagicMock()
        mock_sub.pid = 123
        mock_sub.stdout.readline.side_effect = readline_side_effect
        mock_sub.poll.side_effect = poll_side_effect
        mock_sub.returncode = 0
        mock_popen.return_value = mock_sub
        mock_psutil_proc.return_value = MagicMock()

        def bad_parser(line_text):
            raise ValueError("bad value")

        data = {
            "exec_command": ["echo", "test"],
            "command_progress_parser": bad_parser,
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }
        result = worker._Worker__exec_command_subprocess(data)
        # Despite parser exception, the command should complete normally
        assert result is True

    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_progress_parser_updates_subprocess_percent(self, mock_ensure, mock_popen, mock_psutil_proc):
        """Lines 709-711: progress dict returned by parser calls set_subprocess_percent."""
        worker = _make_worker()
        monitor = _make_monitor()
        # Track calls to set_subprocess_percent before unset_proc resets it to 0
        recorded_percents = []
        original_set = monitor.set_subprocess_percent

        def tracking_set_percent(value):
            recorded_percents.append(value)
            original_set(value)

        monitor.set_subprocess_percent = tracking_set_percent
        worker.worker_subprocess_monitor = monitor
        worker.worker_log = deque(maxlen=500)

        read_count = [0]

        def readline_side_effect():
            read_count[0] += 1
            if read_count[0] == 1:
                return "progress line"
            return ""

        def poll_side_effect():
            return 0 if read_count[0] >= 2 else None

        mock_sub = MagicMock()
        mock_sub.pid = 123
        mock_sub.stdout.readline.side_effect = readline_side_effect
        mock_sub.poll.side_effect = poll_side_effect
        mock_sub.returncode = 0
        mock_popen.return_value = mock_sub
        mock_psutil_proc.return_value = MagicMock()

        def parser(line_text):
            return {"percent": 42}

        data = {
            "exec_command": ["echo", "test"],
            "command_progress_parser": parser,
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }
        result = worker._Worker__exec_command_subprocess(data)
        assert result is True
        # set_subprocess_percent was called with the value from the parser
        assert 42 in recorded_percents


# ---------------------------------------------------------------------------
# Lines 721-723: communicate() timeout handler
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecCommandSubprocessCommunicateTimeout:
    @patch("compresso.libs.workers.psutil.Process")
    @patch("compresso.libs.workers.subprocess.Popen")
    @patch("compresso.libs.workers.common.ensure_dir")
    def test_communicate_timeout_triggers_terminate(self, mock_ensure, mock_popen, mock_psutil_proc):
        """Lines 721-723: TimeoutExpired in communicate() calls terminate_proc()."""
        worker = _make_worker()
        monitor = _make_monitor()
        monitor.terminate_proc = MagicMock()
        worker.worker_subprocess_monitor = monitor
        worker.worker_log = deque(maxlen=500)

        mock_sub = MagicMock()
        mock_sub.pid = 123
        mock_sub.stdout.readline.return_value = ""
        mock_sub.poll.return_value = 0
        mock_sub.returncode = 0
        mock_sub.communicate.side_effect = subprocess.TimeoutExpired(cmd="echo", timeout=30)
        mock_popen.return_value = mock_sub
        mock_psutil_proc.return_value = MagicMock()

        data = {
            "exec_command": ["echo", "test"],
            "command_progress_parser": MagicMock(return_value={"percent": 0}),
            "file_out": None,
            "file_in": "/tmp/in.mp4",
            "current_command": [],
        }

        worker._Worker__exec_command_subprocess(data)
        # terminate_proc should have been called at least once (from timeout handler)
        assert monitor.terminate_proc.call_count >= 1


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
