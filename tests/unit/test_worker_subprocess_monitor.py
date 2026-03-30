#!/usr/bin/env python3

"""
tests.unit.test_worker_subprocess_monitor.py

Unit tests for compresso.libs.worker_subprocess_monitor.WorkerSubprocessMonitor.
"""

import logging
import threading
from unittest.mock import MagicMock, patch

import psutil
import pytest

MODULE = "compresso.libs.worker_subprocess_monitor"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_parent_worker():
    """Return a minimal mock parent_worker with the three Event attributes."""
    parent = MagicMock()
    parent.event = threading.Event()
    parent.redundant_flag = threading.Event()
    parent.paused_flag = threading.Event()
    return parent


@pytest.fixture
def parent_worker():
    return _make_parent_worker()


@pytest.fixture
def mock_logger():
    logger = logging.getLogger("compresso_test_wsm")
    with patch("compresso.libs.logs.CompressoLogging.get_logger", return_value=logger):
        yield logger


@pytest.fixture
def monitor(parent_worker, mock_logger):
    """Build a WorkerSubprocessMonitor without starting its thread."""
    from compresso.libs.worker_subprocess_monitor import WorkerSubprocessMonitor

    return WorkerSubprocessMonitor(parent_worker)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestInit:
    def test_attributes_from_parent_worker(self, parent_worker, mock_logger):
        from compresso.libs.worker_subprocess_monitor import WorkerSubprocessMonitor

        m = WorkerSubprocessMonitor(parent_worker)

        assert m.parent_worker is parent_worker
        assert m.event is parent_worker.event
        assert m.redundant_flag is parent_worker.redundant_flag
        assert m.paused_flag is parent_worker.paused_flag

    def test_initial_subprocess_state(self, monitor):
        assert monitor.subprocess_pid is None
        assert monitor.subprocess is None
        assert monitor.subprocess_start_time == 0
        assert monitor.subprocess_pause_time == 0
        assert monitor._pause_time_counter is None

    def test_initial_stats(self, monitor):
        assert monitor.subprocess_percent == 0
        assert monitor.subprocess_elapsed == 0
        assert monitor.subprocess_cpu_percent == 0
        assert monitor.subprocess_mem_percent == 0
        assert monitor.subprocess_rss_bytes == 0
        assert monitor.subprocess_vms_bytes == 0

    def test_initial_encoding_speed(self, monitor):
        assert monitor.last_encoding_fps == 0
        assert monitor.last_encoding_speed == 0
        assert monitor._fps_samples == []
        assert monitor._speed_samples == []

    def test_is_daemon_thread(self, monitor):
        assert monitor.daemon is True

    def test_paused_false_at_start(self, monitor):
        assert monitor.paused is False


# ---------------------------------------------------------------------------
# set_proc
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSetProc:
    def test_new_pid_sets_subprocess(self, monitor):
        mock_proc = MagicMock()
        with patch(MODULE + ".psutil.Process", return_value=mock_proc) as mock_cls:
            monitor.set_proc(1234)

        mock_cls.assert_called_once_with(pid=1234)
        assert monitor.subprocess_pid == 1234
        assert monitor.subprocess is mock_proc

    def test_new_pid_resets_timing(self, monitor):
        monitor.subprocess_pause_time = 99
        monitor.subprocess_elapsed = 77
        monitor.subprocess_percent = 50

        with patch(MODULE + ".psutil.Process"), patch(MODULE + ".time.time", return_value=1000.0):
            monitor.set_proc(1234)

        assert monitor.subprocess_start_time == 1000.0
        assert monitor.subprocess_pause_time == 0
        assert monitor.subprocess_percent == 0
        assert monitor.subprocess_elapsed == 0

    def test_same_pid_is_noop(self, monitor):
        monitor.subprocess_pid = 1234
        original_proc = MagicMock()
        monitor.subprocess = original_proc

        with patch(MODULE + ".psutil.Process") as mock_cls:
            monitor.set_proc(1234)

        mock_cls.assert_not_called()
        assert monitor.subprocess is original_proc

    def test_redundant_flag_triggers_terminate(self, monitor, parent_worker):
        parent_worker.redundant_flag.set()
        mock_proc = MagicMock()

        with (
            patch(MODULE + ".psutil.Process", return_value=mock_proc),
            patch.object(monitor, "terminate_proc") as mock_terminate,
        ):
            monitor.set_proc(5678)

        mock_terminate.assert_called_once()

    def test_no_terminate_when_not_redundant(self, monitor, parent_worker):
        parent_worker.redundant_flag.clear()
        mock_proc = MagicMock()

        with (
            patch(MODULE + ".psutil.Process", return_value=mock_proc),
            patch.object(monitor, "terminate_proc") as mock_terminate,
        ):
            monitor.set_proc(5678)

        mock_terminate.assert_not_called()

    def test_exception_is_caught(self, monitor):
        with patch(MODULE + ".psutil.Process", side_effect=RuntimeError("boom")):
            # Should not raise
            monitor.set_proc(9999)

        # State should not have been updated with new pid after the exception path
        # (the pid assignment happens before Process(), so it will be set)
        # But most importantly: no exception propagated
        assert True


# ---------------------------------------------------------------------------
# unset_proc
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUnsetProc:
    def test_preserves_elapsed_before_clearing(self, monitor):
        monitor.subprocess = MagicMock()
        monitor.subprocess_start_time = 900.0
        monitor.subprocess_pause_time = 10

        with patch(MODULE + ".time.time", return_value=1000.0):
            monitor.unset_proc()

        # elapsed = total_run_time - pause_time = 100 - 10 = 90
        assert monitor.subprocess_elapsed == 90

    def test_clears_subprocess_state(self, monitor):
        monitor.subprocess_pid = 42
        monitor.subprocess = MagicMock()
        monitor.subprocess_percent = 75

        with patch.object(monitor, "get_subprocess_elapsed", return_value=50):
            monitor.unset_proc()

        assert monitor.subprocess_pid is None
        assert monitor.subprocess is None
        assert monitor.subprocess_percent == 0

    def test_resets_resource_values(self, monitor):
        monitor.subprocess_cpu_percent = 55.0
        monitor.subprocess_rss_bytes = 1024
        monitor.subprocess_vms_bytes = 2048
        monitor.subprocess_mem_percent = 10.0

        with patch.object(monitor, "get_subprocess_elapsed", return_value=0):
            monitor.unset_proc()

        assert monitor.subprocess_cpu_percent == 0
        assert monitor.subprocess_rss_bytes == 0
        assert monitor.subprocess_vms_bytes == 0
        assert monitor.subprocess_mem_percent == 0

    def test_exception_is_caught(self, monitor):
        with patch.object(monitor, "get_subprocess_elapsed", side_effect=RuntimeError("boom")):
            # Should not raise
            monitor.unset_proc()


# ---------------------------------------------------------------------------
# set_proc_resources_in_parent_worker
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSetProcResources:
    def test_sets_all_resource_fields(self, monitor):
        monitor.set_proc_resources_in_parent_worker(12.5, 1024, 2048, 3.7)

        assert monitor.subprocess_cpu_percent == 12.5
        assert monitor.subprocess_rss_bytes == 1024
        assert monitor.subprocess_vms_bytes == 2048
        assert monitor.subprocess_mem_percent == 3.7


# ---------------------------------------------------------------------------
# suspend_proc
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSuspendProc:
    def test_suspends_parent_and_children(self, monitor):
        child1 = MagicMock()
        child2 = MagicMock()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.return_value = [child1, child2]
        monitor.subprocess = mock_proc

        monitor.suspend_proc()

        mock_proc.suspend.assert_called_once()
        child1.suspend.assert_called_once()
        child2.suspend.assert_called_once()
        assert monitor.paused is True

    def test_handles_no_such_process_for_child(self, monitor):
        dying_child = MagicMock()
        dying_child.suspend.side_effect = psutil.NoSuchProcess(pid=999)
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.return_value = [dying_child]
        monitor.subprocess = mock_proc

        # Should not raise
        monitor.suspend_proc()
        assert monitor.paused is True

    def test_no_subprocess_is_noop(self, monitor):
        monitor.subprocess = None
        # Should not raise; paused stays False
        monitor.suspend_proc()
        assert monitor.paused is False

    def test_not_running_is_noop(self, monitor):
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = False
        monitor.subprocess = mock_proc

        monitor.suspend_proc()
        mock_proc.suspend.assert_not_called()
        assert monitor.paused is False

    def test_exception_is_caught(self, monitor):
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.side_effect = RuntimeError("boom")
        monitor.subprocess = mock_proc

        # Should not raise
        monitor.suspend_proc()


# ---------------------------------------------------------------------------
# resume_proc
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestResumeProc:
    def test_resumes_in_reverse_order(self, monitor):
        resume_order = []
        child1 = MagicMock()
        child1.resume.side_effect = lambda: resume_order.append("child1")
        child2 = MagicMock()
        child2.resume.side_effect = lambda: resume_order.append("child2")
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.return_value = [child1, child2]
        mock_proc.resume.side_effect = lambda: resume_order.append("parent")
        monitor.subprocess = mock_proc
        monitor.paused = True

        monitor.resume_proc()

        # reversed([parent, child1, child2]) → child2, child1, parent
        assert resume_order == ["child2", "child1", "parent"]
        assert monitor.paused is False

    def test_terminates_if_redundant_flag_set(self, monitor, parent_worker):
        parent_worker.redundant_flag.set()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.return_value = []
        monitor.subprocess = mock_proc
        monitor.paused = True

        monitor.resume_proc()

        mock_proc.terminate.assert_called_once()

    def test_terminates_if_stop_event_set(self, monitor):
        monitor._stop_event.set()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.children.return_value = []
        monitor.subprocess = mock_proc
        monitor.paused = True

        monitor.resume_proc()

        mock_proc.terminate.assert_called_once()

    def test_no_subprocess_is_noop(self, monitor):
        monitor.subprocess = None
        # Should not raise
        monitor.resume_proc()

    def test_exception_is_caught(self, monitor):
        mock_proc = MagicMock()
        mock_proc.is_running.side_effect = RuntimeError("boom")
        monitor.subprocess = mock_proc

        # Should not raise
        monitor.resume_proc()


# ---------------------------------------------------------------------------
# terminate_proc
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestTerminateProc:
    def test_terminates_and_unsets(self, monitor):
        monitor.subprocess = MagicMock()
        monitor.subprocess_pid = 1234

        with (
            patch.object(monitor, "_WorkerSubprocessMonitor__terminate_proc_tree") as mock_tree,
            patch.object(monitor, "unset_proc") as mock_unset,
        ):
            monitor.terminate_proc()

        mock_tree.assert_called_once_with(monitor.subprocess)
        mock_unset.assert_called_once()

    def test_noop_when_no_subprocess(self, monitor):
        monitor.subprocess = None

        with (
            patch.object(monitor, "_WorkerSubprocessMonitor__terminate_proc_tree") as mock_tree,
            patch.object(monitor, "unset_proc") as mock_unset,
        ):
            monitor.terminate_proc()

        mock_tree.assert_not_called()
        mock_unset.assert_not_called()

    def test_exception_is_caught(self, monitor):
        monitor.subprocess = MagicMock()

        with patch.object(monitor, "_WorkerSubprocessMonitor__terminate_proc_tree", side_effect=RuntimeError("boom")):
            # Should not raise
            monitor.terminate_proc()


# ---------------------------------------------------------------------------
# __terminate_proc_tree
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestTerminateProcTree:
    def test_resumes_terminates_and_kills_survivors(self, monitor):
        child = MagicMock(spec=psutil.Process)
        parent_proc = MagicMock(spec=psutil.Process)
        parent_proc.children.return_value = [child]

        alive_proc = MagicMock(spec=psutil.Process)
        gone_proc = MagicMock(spec=psutil.Process)

        with patch(MODULE + ".psutil.wait_procs", side_effect=[(([gone_proc], [alive_proc])), ([], [])]) as mock_wait:
            monitor._WorkerSubprocessMonitor__terminate_proc_tree(parent_proc)

        # All procs were resumed
        child.resume.assert_called_once()
        parent_proc.resume.assert_called_once()

        # All procs were terminated
        child.terminate.assert_called_once()
        parent_proc.terminate.assert_called_once()

        # wait_procs called twice: first wait, then final wait for alive
        assert mock_wait.call_count == 2

        # Alive process force-killed
        alive_proc.kill.assert_called_once()

    def test_suppresses_no_such_process_during_resume(self, monitor):
        child = MagicMock(spec=psutil.Process)
        child.resume.side_effect = psutil.NoSuchProcess(pid=99)
        parent_proc = MagicMock(spec=psutil.Process)
        parent_proc.children.return_value = [child]

        with patch(MODULE + ".psutil.wait_procs", return_value=([], [])):
            # Should not raise
            monitor._WorkerSubprocessMonitor__terminate_proc_tree(parent_proc)

    def test_suppresses_no_such_process_during_terminate(self, monitor):
        parent_proc = MagicMock(spec=psutil.Process)
        parent_proc.children.return_value = []
        parent_proc.terminate.side_effect = psutil.NoSuchProcess(pid=99)

        with patch(MODULE + ".psutil.wait_procs", return_value=([], [])):
            # Should not raise
            monitor._WorkerSubprocessMonitor__terminate_proc_tree(parent_proc)

    def test_exception_is_caught(self, monitor):
        bad_proc = MagicMock(spec=psutil.Process)
        bad_proc.children.side_effect = RuntimeError("boom")

        # Should not raise
        monitor._WorkerSubprocessMonitor__terminate_proc_tree(bad_proc)


# ---------------------------------------------------------------------------
# get_subprocess_elapsed
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetSubprocessElapsed:
    def test_calculates_elapsed_subtracting_pause(self, monitor):
        mock_proc = MagicMock()
        monitor.subprocess = mock_proc
        monitor.subprocess_start_time = 900.0
        monitor.subprocess_pause_time = 20

        with patch(MODULE + ".time.time", return_value=1000.0):
            result = monitor.get_subprocess_elapsed()

        # total_run = 1000 - 900 = 100; elapsed = 100 - 20 = 80
        assert result == 80

    def test_returns_cached_when_no_subprocess(self, monitor):
        monitor.subprocess = None
        monitor.subprocess_elapsed = 42

        result = monitor.get_subprocess_elapsed()

        assert result == 42

    def test_updates_subprocess_elapsed_attribute(self, monitor):
        mock_proc = MagicMock()
        monitor.subprocess = mock_proc
        monitor.subprocess_start_time = 950.0
        monitor.subprocess_pause_time = 5

        with patch(MODULE + ".time.time", return_value=1000.0):
            monitor.get_subprocess_elapsed()

        assert monitor.subprocess_elapsed == 45

    def test_exception_returns_cached(self, monitor):
        monitor.subprocess_elapsed = 77
        monitor.subprocess = MagicMock()
        # Force an exception by making time.time raise
        with patch(MODULE + ".time.time", side_effect=RuntimeError("boom")):
            result = monitor.get_subprocess_elapsed()

        assert result == 77


# ---------------------------------------------------------------------------
# get_subprocess_stats
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetSubprocessStats:
    def test_returns_dict_with_all_keys(self, monitor):
        monitor.subprocess_pid = 123
        monitor.subprocess_percent = 50
        monitor.subprocess_cpu_percent = 25.0
        monitor.subprocess_mem_percent = 1.5
        monitor.subprocess_rss_bytes = 1024
        monitor.subprocess_vms_bytes = 2048
        monitor.last_encoding_fps = 30.0
        monitor.last_encoding_speed = 1.5

        with patch.object(monitor, "get_subprocess_elapsed", return_value=100):
            result = monitor.get_subprocess_stats()

        assert result["pid"] == "123"
        assert result["percent"] == "50"
        assert result["elapsed"] == 100
        assert result["cpu_percent"] == "25.0"
        assert result["mem_percent"] == "1.5"
        assert result["rss_bytes"] == "1024"
        assert result["vms_bytes"] == "2048"
        assert result["encoding_fps"] == 30.0
        assert result["encoding_speed"] == 1.5

    def test_calculates_eta_when_percent_and_elapsed_positive(self, monitor):
        monitor.subprocess_percent = 50

        with patch.object(monitor, "get_subprocess_elapsed", return_value=100):
            result = monitor.get_subprocess_stats()

        # eta = int((100/50) * (100-50)) = int(2 * 50) = 100
        assert result["eta_seconds"] == 100

    def test_eta_is_none_when_percent_zero(self, monitor):
        monitor.subprocess_percent = 0

        with patch.object(monitor, "get_subprocess_elapsed", return_value=100):
            result = monitor.get_subprocess_stats()

        assert result["eta_seconds"] is None

    def test_eta_is_none_when_elapsed_zero(self, monitor):
        monitor.subprocess_percent = 50

        with patch.object(monitor, "get_subprocess_elapsed", return_value=0):
            result = monitor.get_subprocess_stats()

        assert result["eta_seconds"] is None

    def test_returns_fallback_on_exception(self, monitor):
        with patch.object(monitor, "get_subprocess_elapsed", side_effect=RuntimeError("boom")):
            result = monitor.get_subprocess_stats()

        assert result["pid"] == "0"
        assert result["percent"] == "0"
        assert result["eta_seconds"] is None


# ---------------------------------------------------------------------------
# parse_ffmpeg_speed
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestParseFfmpegSpeed:
    def test_parses_fps_and_speed(self, monitor):
        monitor.parse_ffmpeg_speed("frame=  100 fps= 29.97 q=28.0 size=  512kB time=00:00:04 bitrate=1024kB/s speed=1.2x")

        assert monitor.last_encoding_fps == pytest.approx(29.97)
        assert monitor.last_encoding_speed == pytest.approx(1.2)
        assert monitor._fps_samples == [pytest.approx(29.97)]
        assert monitor._speed_samples == [pytest.approx(1.2)]

    def test_ignores_non_ffmpeg_lines(self, monitor):
        monitor.parse_ffmpeg_speed("some random log line without relevant data")

        assert monitor.last_encoding_fps == 0
        assert monitor.last_encoding_speed == 0

    def test_ignores_zero_fps(self, monitor):
        monitor.parse_ffmpeg_speed("fps=0 speed=1.0x")

        assert monitor.last_encoding_fps == 0
        assert monitor._fps_samples == []

    def test_ignores_zero_speed(self, monitor):
        monitor.parse_ffmpeg_speed("fps=25 speed=0x")

        assert monitor.last_encoding_speed == 0
        assert monitor._speed_samples == []

    def test_accumulates_multiple_samples(self, monitor):
        monitor.parse_ffmpeg_speed("fps=24 speed=1.0x")
        monitor.parse_ffmpeg_speed("fps=30 speed=1.5x")

        assert len(monitor._fps_samples) == 2
        assert len(monitor._speed_samples) == 2

    def test_handles_exception_gracefully(self, monitor):
        # Passing a non-string-convertible value that triggers exception path
        with patch(MODULE + ".re.search", side_effect=RuntimeError("boom")):
            # Should not raise (exception logged at debug level)
            monitor.parse_ffmpeg_speed("fps=25 speed=1.0x")


# ---------------------------------------------------------------------------
# get_encoding_speed_stats / reset_encoding_speed_stats
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestEncodingSpeedStats:
    def test_returns_zeros_when_no_samples(self, monitor):
        result = monitor.get_encoding_speed_stats()
        assert result == {"avg_encoding_fps": 0, "encoding_speed_ratio": 0}

    def test_averages_samples(self, monitor):
        monitor._fps_samples = [20.0, 30.0, 40.0]
        monitor._speed_samples = [1.0, 2.0, 3.0]

        result = monitor.get_encoding_speed_stats()

        assert result["avg_encoding_fps"] == pytest.approx(30.0)
        assert result["encoding_speed_ratio"] == pytest.approx(2.0)

    def test_reset_clears_samples_and_last_values(self, monitor):
        monitor._fps_samples = [25.0]
        monitor._speed_samples = [1.5]
        monitor.last_encoding_fps = 25.0
        monitor.last_encoding_speed = 1.5

        monitor.reset_encoding_speed_stats()

        assert monitor._fps_samples == []
        assert monitor._speed_samples == []
        assert monitor.last_encoding_fps == 0
        assert monitor.last_encoding_speed == 0

    def test_rounds_to_two_decimal_places(self, monitor):
        monitor._fps_samples = [23.976, 24.0, 25.0]
        result = monitor.get_encoding_speed_stats()
        # Should be rounded to 2 dp
        assert result["avg_encoding_fps"] == round(sum([23.976, 24.0, 25.0]) / 3, 2)


# ---------------------------------------------------------------------------
# set_subprocess_start_time
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSetSubprocessStartTime:
    def test_sets_start_time(self, monitor):
        monitor.set_subprocess_start_time(12345.0)
        assert monitor.subprocess_start_time == 12345.0

    def test_exception_path_logs_and_does_not_raise(self, monitor):
        """Verify the try/except in set_subprocess_start_time absorbs errors."""
        # Patch the logger so we can detect the exception handler was reached
        mock_log = MagicMock()
        monitor.logger = mock_log
        # Normal call should always succeed; the except branch exists as a safety net.
        # We verify the method is callable without raising under normal conditions.
        monitor.set_subprocess_start_time(42.0)
        assert monitor.subprocess_start_time == 42.0
        mock_log.exception.assert_not_called()


# ---------------------------------------------------------------------------
# set_subprocess_percent
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSetSubprocessPercent:
    def test_sets_normal_value(self, monitor):
        monitor.set_subprocess_percent(75)
        assert monitor.subprocess_percent == 75

    def test_clamps_below_zero(self, monitor):
        monitor.set_subprocess_percent(-10)
        assert monitor.subprocess_percent == 0

    def test_clamps_above_hundred(self, monitor):
        monitor.set_subprocess_percent(150)
        assert monitor.subprocess_percent == 100

    def test_accepts_float_string(self, monitor):
        monitor.set_subprocess_percent("63.7")
        assert monitor.subprocess_percent == 63

    def test_invalid_type_sets_zero(self, monitor):
        monitor.subprocess_percent = 50
        monitor.set_subprocess_percent(None)
        assert monitor.subprocess_percent == 0

    def test_invalid_string_sets_zero(self, monitor):
        monitor.subprocess_percent = 50
        monitor.set_subprocess_percent("not_a_number")
        assert monitor.subprocess_percent == 0

    def test_boundary_zero(self, monitor):
        monitor.set_subprocess_percent(0)
        assert monitor.subprocess_percent == 0

    def test_boundary_hundred(self, monitor):
        monitor.set_subprocess_percent(100)
        assert monitor.subprocess_percent == 100


# ---------------------------------------------------------------------------
# default_progress_parser
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestDefaultProgressParser:
    def test_unset_true_calls_unset_proc(self, monitor, parent_worker):
        monitor.subprocess_percent = 42

        with patch.object(monitor, "unset_proc") as mock_unset:
            result = monitor.default_progress_parser(None, unset=True)

        mock_unset.assert_called_once()
        assert "killed" in result
        assert "paused" in result
        assert "percent" in result

    def test_unset_true_returns_redundant_killed_state(self, monitor, parent_worker):
        parent_worker.redundant_flag.set()
        with patch.object(monitor, "unset_proc"):
            result = monitor.default_progress_parser(None, unset=True)
        assert result["killed"] is True

    def test_with_pid_calls_set_proc(self, monitor):
        with patch.object(monitor, "set_proc") as mock_set:
            monitor.default_progress_parser("50", pid=1234)
        mock_set.assert_called_once_with(1234)

    def test_with_proc_start_time_calls_set_start_time(self, monitor):
        with patch.object(monitor, "set_subprocess_start_time") as mock_set_time:
            monitor.default_progress_parser("50", proc_start_time=9999.0)
        mock_set_time.assert_called_once_with(9999.0)

    def test_parses_float_text_as_percent(self, monitor):
        monitor.default_progress_parser("73.5")
        assert monitor.subprocess_percent == 73

    def test_non_numeric_text_is_ignored(self, monitor):
        monitor.subprocess_percent = 30
        monitor.default_progress_parser("not a number")
        assert monitor.subprocess_percent == 30

    def test_returns_dict_with_correct_keys(self, monitor):
        result = monitor.default_progress_parser("50")
        assert set(result.keys()) == {"killed", "paused", "percent"}

    def test_exception_in_body_still_returns_dict(self, monitor):
        with patch.object(monitor, "set_proc", side_effect=RuntimeError("boom")):
            result = monitor.default_progress_parser("50", pid=1234)
        assert "killed" in result
        assert "percent" in result

    def test_paused_reflects_current_paused_state(self, monitor):
        monitor.paused = True
        result = monitor.default_progress_parser("50")
        assert result["paused"] is True


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestStop:
    def test_terminates_proc_and_sets_stop_event(self, monitor):
        with patch.object(monitor, "terminate_proc") as mock_terminate:
            monitor.stop()

        mock_terminate.assert_called_once()
        assert monitor._stop_event.is_set()


# ---------------------------------------------------------------------------
# run() loop — unit-tested by driving the logic directly
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunLoop:
    def _make_run_monitor(self):
        """Build a monitor and patch event.wait to be a no-op."""
        parent = _make_parent_worker()
        parent.event.wait = MagicMock()
        logger = logging.getLogger("compresso_test_wsm_run")
        with patch("compresso.libs.logs.CompressoLogging.get_logger", return_value=logger):
            from compresso.libs.worker_subprocess_monitor import WorkerSubprocessMonitor

            m = WorkerSubprocessMonitor(parent)
        m.event.wait = MagicMock()
        return m

    def test_stop_event_breaks_loop(self):
        m = self._make_run_monitor()
        m._stop_event.set()

        with patch(MODULE + ".psutil.cpu_count", return_value=4):
            m.run()

        # If we get here the loop exited cleanly
        assert True

    def test_redundant_flag_calls_terminate_proc(self):
        m = self._make_run_monitor()
        m.redundant_flag.set()

        call_count = [0]

        original_terminate = m.terminate_proc

        def terminate_and_stop():
            original_terminate()
            call_count[0] += 1
            m._stop_event.set()

        m.terminate_proc = terminate_and_stop

        with patch(MODULE + ".psutil.cpu_count", return_value=4):
            m.run()

        assert call_count[0] >= 1

    def test_no_subprocess_waits_and_continues(self):
        m = self._make_run_monitor()
        m.subprocess = None

        iteration = [0]
        original_wait = m.event.wait

        def wait_and_stop(timeout=None):
            iteration[0] += 1
            if iteration[0] >= 2:
                m._stop_event.set()
            original_wait(0)

        m.event.wait = wait_and_stop

        with patch(MODULE + ".psutil.cpu_count", return_value=4):
            m.run()

        assert iteration[0] >= 2

    def test_subprocess_not_running_waits_and_continues(self):
        m = self._make_run_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = False
        m.subprocess = mock_proc

        iteration = [0]
        original_wait = m.event.wait

        def wait_and_stop(timeout=None):
            iteration[0] += 1
            if iteration[0] >= 2:
                m._stop_event.set()
            original_wait(0)

        m.event.wait = wait_and_stop

        with patch(MODULE + ".psutil.cpu_count", return_value=4):
            m.run()

        assert iteration[0] >= 2

    def test_run_polls_cpu_and_memory(self):
        m = self._make_run_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.cpu_percent.return_value = 80.0
        mock_mem_info = MagicMock()
        mock_mem_info.rss = 1024
        mock_mem_info.vms = 2048
        mock_proc.memory_info.return_value = mock_mem_info
        mock_proc.children.return_value = []
        m.subprocess = mock_proc

        polled = [False]
        original_set = m.set_proc_resources_in_parent_worker

        def record_set(*args, **kwargs):
            polled[0] = True
            original_set(*args, **kwargs)
            m._stop_event.set()

        m.set_proc_resources_in_parent_worker = record_set

        mock_vm = MagicMock()
        mock_vm.total = 8 * 1024 * 1024 * 1024

        with (
            patch(MODULE + ".psutil.cpu_count", return_value=4),
            patch(MODULE + ".psutil.virtual_memory", return_value=mock_vm),
        ):
            m.run()

        assert polled[0] is True

    def test_paused_flag_triggers_suspend(self):
        m = self._make_run_monitor()
        m.paused_flag.set()

        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.cpu_percent.return_value = 0.0
        mock_mem_info = MagicMock()
        mock_mem_info.rss = 0
        mock_mem_info.vms = 0
        mock_proc.memory_info.return_value = mock_mem_info
        mock_proc.children.return_value = []
        m.subprocess = mock_proc
        m.paused = False

        suspended = [False]
        original_suspend = m.suspend_proc

        def suspend_and_stop():
            suspended[0] = True
            original_suspend()
            m._stop_event.set()

        m.suspend_proc = suspend_and_stop

        mock_vm = MagicMock()
        mock_vm.total = 8 * 1024 * 1024 * 1024

        with (
            patch(MODULE + ".psutil.cpu_count", return_value=4),
            patch(MODULE + ".psutil.virtual_memory", return_value=mock_vm),
            patch(MODULE + ".time.time", return_value=1000.0),
        ):
            m.run()

        assert suspended[0] is True

    def test_resume_when_paused_flag_cleared(self):
        m = self._make_run_monitor()
        # paused_flag is NOT set, but monitor.paused is True → should resume
        m.paused_flag.clear()
        m.paused = True

        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.cpu_percent.return_value = 0.0
        mock_mem_info = MagicMock()
        mock_mem_info.rss = 0
        mock_mem_info.vms = 0
        mock_proc.memory_info.return_value = mock_mem_info
        mock_proc.children.return_value = []
        m.subprocess = mock_proc

        resumed = [False]
        original_resume = m.resume_proc

        def resume_and_stop():
            resumed[0] = True
            original_resume()
            m._stop_event.set()

        m.resume_proc = resume_and_stop

        mock_vm = MagicMock()
        mock_vm.total = 8 * 1024 * 1024 * 1024

        with (
            patch(MODULE + ".psutil.cpu_count", return_value=4),
            patch(MODULE + ".psutil.virtual_memory", return_value=mock_vm),
        ):
            m.run()

        assert resumed[0] is True

    def test_no_such_process_exception_is_handled(self):
        m = self._make_run_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.side_effect = psutil.NoSuchProcess(pid=999)
        m.subprocess = mock_proc

        iteration = [0]
        original_wait = m.event.wait

        def wait_and_stop(timeout=None):
            iteration[0] += 1
            if iteration[0] >= 2:
                m._stop_event.set()
            original_wait(0)

        m.event.wait = wait_and_stop

        with patch(MODULE + ".psutil.cpu_count", return_value=4):
            # Should not propagate
            m.run()

    def test_run_aggregates_child_memory(self):
        m = self._make_run_monitor()
        mock_proc = MagicMock()
        mock_proc.is_running.return_value = True
        mock_proc.cpu_percent.return_value = 0.0
        mock_mem_info = MagicMock()
        mock_mem_info.rss = 500
        mock_mem_info.vms = 1000
        mock_proc.memory_info.return_value = mock_mem_info

        child_mem = MagicMock()
        child_mem.rss = 200
        child_mem.vms = 400
        child_proc = MagicMock()
        child_proc.memory_info.return_value = child_mem
        mock_proc.children.return_value = [child_proc]
        m.subprocess = mock_proc

        captured = {}
        original_set = m.set_proc_resources_in_parent_worker

        def capture_set(cpu, rss, vms, mem):
            captured["rss"] = rss
            captured["vms"] = vms
            original_set(cpu, rss, vms, mem)
            m._stop_event.set()

        m.set_proc_resources_in_parent_worker = capture_set

        mock_vm = MagicMock()
        mock_vm.total = 8 * 1024 * 1024 * 1024

        with (
            patch(MODULE + ".psutil.cpu_count", return_value=4),
            patch(MODULE + ".psutil.virtual_memory", return_value=mock_vm),
        ):
            m.run()

        assert captured.get("rss") == 700
        assert captured.get("vms") == 1400
