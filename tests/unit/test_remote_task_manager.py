#!/usr/bin/env python3

"""
tests.unit.test_remote_task_manager.py

Unit tests for compresso.libs.remote_task_manager.RemoteTaskManager.
Covers __init__, get_info, _log, run, and all private runtime methods
via name-mangling access (_RemoteTaskManager__method_name).
"""

import queue
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_installation_info(**overrides):
    info = {
        "address": "http://remote:8001",
        "remote_address": "http://remote:8001",
        "installation_uuid": "test-uuid-1234",
        "enable_checksum_validation": False,
        "enable_remote_only": False,
    }
    info.update(overrides)
    return info


def _make_manager(installation_info=None, pending_queue=None, complete_queue=None, event=None):
    """Construct a RemoteTaskManager with all heavy dependencies mocked out."""
    if installation_info is None:
        installation_info = _make_installation_info()
    if pending_queue is None:
        pending_queue = queue.Queue()
    if complete_queue is None:
        complete_queue = queue.Queue()
    if event is None:
        event = threading.Event()

    with (
        patch("compresso.libs.remote_task_manager.Links"),
        patch("compresso.libs.remote_task_manager.CompressoLogging"),
    ):
        from compresso.libs.remote_task_manager import RemoteTaskManager

        mgr = RemoteTaskManager(
            thread_id=1,
            name="TestRemoteWorker",
            installation_info=installation_info,
            pending_queue=pending_queue,
            complete_queue=complete_queue,
            event=event,
        )
    return mgr


def _make_task(abspath="/data/library/video.mkv", library_id=1, task_id=42, task_type="standard"):
    """Return a fully-mocked task object."""
    task = MagicMock()
    task.get_source_abspath.return_value = abspath
    task.get_task_library_id.return_value = library_id
    task.get_task_id.return_value = task_id
    task.get_task_type.return_value = task_type
    task.get_source_data.return_value = {}
    task.get_cache_path.return_value = "/tmp/compresso/compresso_file_conversion-abcde-1234567890/video.mkv"
    task.task = MagicMock()
    task.cache_path = "/tmp/compresso/compresso_file_conversion-abcde-1234567890/video.mkv"
    return task


# ===========================================================================
# TestInit
# ===========================================================================


@pytest.mark.unittest
class TestInit:
    def test_thread_id_stored(self):
        mgr = _make_manager()
        assert mgr.thread_id == 1

    def test_name_stored(self):
        mgr = _make_manager()
        assert mgr.name == "TestRemoteWorker"

    def test_installation_info_stored(self):
        info = _make_installation_info()
        mgr = _make_manager(installation_info=info)
        assert mgr.installation_info is info

    def test_pending_queue_stored(self):
        pq = queue.Queue()
        mgr = _make_manager(pending_queue=pq)
        assert mgr.pending_queue is pq

    def test_complete_queue_stored(self):
        cq = queue.Queue()
        mgr = _make_manager(complete_queue=cq)
        assert mgr.complete_queue is cq

    def test_event_stored(self):
        ev = threading.Event()
        mgr = _make_manager(event=ev)
        assert mgr.event is ev

    def test_redundant_flag_is_threading_event_cleared(self):
        mgr = _make_manager()
        assert isinstance(mgr.redundant_flag, threading.Event)
        assert not mgr.redundant_flag.is_set()

    def test_paused_flag_is_threading_event_cleared(self):
        mgr = _make_manager()
        assert isinstance(mgr.paused_flag, threading.Event)
        assert not mgr.paused_flag.is_set()

    def test_links_attribute_created(self):
        mgr = _make_manager()
        assert mgr.links is not None

    def test_logger_created(self):
        mgr = _make_manager()
        assert mgr.logger is not None

    def test_class_level_defaults(self):
        mgr = _make_manager()
        assert mgr.current_task is None
        assert mgr.worker_log is None
        assert mgr.worker_subprocess_percent == "0"
        assert mgr.worker_subprocess_elapsed == "0"


# ===========================================================================
# TestGetInfo
# ===========================================================================


@pytest.mark.unittest
class TestGetInfo:
    def test_returns_dict_with_name(self):
        mgr = _make_manager()
        info = mgr.get_info()
        assert info["name"] == "TestRemoteWorker"

    def test_returns_dict_with_installation_info(self):
        inst_info = _make_installation_info()
        mgr = _make_manager(installation_info=inst_info)
        info = mgr.get_info()
        assert info["installation_info"] is inst_info

    def test_returns_exactly_two_keys(self):
        mgr = _make_manager()
        info = mgr.get_info()
        assert set(info.keys()) == {"name", "installation_info"}


# ===========================================================================
# TestLog
# ===========================================================================


@pytest.mark.unittest
class TestLog:
    def test_log_info_calls_logger_info(self):
        mgr = _make_manager()
        mgr.logger = MagicMock()
        with patch("compresso.libs.remote_task_manager.common") as mock_common:
            mock_common.format_message.return_value = "formatted"
            mgr._log("hello")
        mgr.logger.info.assert_called_once_with("formatted")

    def test_log_warning_calls_logger_warning(self):
        mgr = _make_manager()
        mgr.logger = MagicMock()
        with patch("compresso.libs.remote_task_manager.common") as mock_common:
            mock_common.format_message.return_value = "warn msg"
            mgr._log("warn", level="warning")
        mgr.logger.warning.assert_called_once_with("warn msg")

    def test_log_passes_message2_to_format_message(self):
        mgr = _make_manager()
        mgr.logger = MagicMock()
        with patch("compresso.libs.remote_task_manager.common") as mock_common:
            mock_common.format_message.return_value = "combined"
            mgr._log("msg", "detail")
        mock_common.format_message.assert_called_once_with("msg", "detail")


# ===========================================================================
# TestRun
# ===========================================================================


@pytest.mark.unittest
class TestRun:
    def test_run_empty_queue_logs_warning(self):
        pq = queue.Queue()  # empty
        mgr = _make_manager(pending_queue=pq)
        mgr._log = MagicMock()
        mgr.run()
        warning_calls = [c for c in mgr._log.call_args_list if c.kwargs.get("level") == "warning"]
        assert len(warning_calls) >= 1

    def test_run_calls_set_current_task_and_process(self):
        task = _make_task()
        pq = queue.Queue()
        pq.put(task)
        mgr = _make_manager(pending_queue=pq)
        mgr._RemoteTaskManager__set_current_task = MagicMock()
        mgr._RemoteTaskManager__process_task_queue_item = MagicMock()
        mgr.run()
        mgr._RemoteTaskManager__set_current_task.assert_called_once_with(task)
        mgr._RemoteTaskManager__process_task_queue_item.assert_called_once()

    def test_run_exception_with_current_task_marks_failed_and_completes(self):
        task = _make_task()
        pq = queue.Queue()
        pq.put(task)
        cq = queue.Queue()
        mgr = _make_manager(pending_queue=pq, complete_queue=cq)

        def raise_after_set(t):
            mgr.current_task = task
            raise RuntimeError("processing error")

        mgr._RemoteTaskManager__set_current_task = raise_after_set
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()
        mgr._RemoteTaskManager__unset_current_task = MagicMock()
        mgr.run()

        task.set_success.assert_called_once_with(False)
        mgr._RemoteTaskManager__write_failure_to_worker_log.assert_called_once()
        assert not cq.empty()

    def test_run_exception_no_current_task_requeues_next_task(self):
        task = _make_task()
        pq = queue.Queue()
        pq.put(task)
        mgr = _make_manager(pending_queue=pq)

        def raise_before_set(t):
            raise RuntimeError("pre-set error")

        mgr._RemoteTaskManager__set_current_task = raise_before_set
        mgr._log = MagicMock()
        mgr.run()

        # task should be back in the queue
        assert not pq.empty()
        assert pq.get_nowait() is task

    def test_run_exception_requeue_failure_logs_error(self):
        task = _make_task()
        pq = MagicMock()
        pq.get_nowait.return_value = task
        pq.put.side_effect = Exception("queue full")
        mgr = _make_manager(pending_queue=pq)

        def raise_before_set(t):
            raise RuntimeError("boom")

        mgr._RemoteTaskManager__set_current_task = raise_before_set
        mgr._log = MagicMock()
        mgr.run()

        error_calls = [c for c in mgr._log.call_args_list if c.kwargs.get("level") == "error"]
        assert len(error_calls) >= 1


# ===========================================================================
# TestSetCurrentTask
# ===========================================================================


@pytest.mark.unittest
class TestSetCurrentTask:
    def test_sets_current_task(self):
        mgr = _make_manager()
        task = _make_task()
        with patch("compresso.libs.remote_task_manager.PluginsHandler") as mock_ph_cls:
            mock_ph_cls.return_value = MagicMock()
            mgr._RemoteTaskManager__set_current_task(task)
        assert mgr.current_task is task

    def test_initialises_worker_log_to_empty_list(self):
        mgr = _make_manager()
        task = _make_task()
        with patch("compresso.libs.remote_task_manager.PluginsHandler"):
            mgr._RemoteTaskManager__set_current_task(task)
        assert mgr.worker_log == []

    def test_calls_event_plugin_runner(self):
        mgr = _make_manager()
        task = _make_task()
        with patch("compresso.libs.remote_task_manager.PluginsHandler") as mock_ph_cls:
            mock_handler = MagicMock()
            mock_ph_cls.return_value = mock_handler
            mgr._RemoteTaskManager__set_current_task(task)
        mock_handler.run_event_plugins_for_plugin_type.assert_called_once()
        args = mock_handler.run_event_plugins_for_plugin_type.call_args
        assert args[0][0] == "events.task_scheduled"

    def test_event_data_includes_remote_schedule_type(self):
        mgr = _make_manager()
        task = _make_task()
        captured = {}
        with patch("compresso.libs.remote_task_manager.PluginsHandler") as mock_ph_cls:
            mock_handler = MagicMock()
            mock_ph_cls.return_value = mock_handler
            mock_handler.run_event_plugins_for_plugin_type.side_effect = lambda ptype, data: captured.update(data)
            mgr._RemoteTaskManager__set_current_task(task)
        assert captured.get("task_schedule_type") == "remote"


# ===========================================================================
# TestUnsetCurrentTask
# ===========================================================================


@pytest.mark.unittest
class TestUnsetCurrentTask:
    def test_clears_current_task(self):
        mgr = _make_manager()
        mgr.current_task = _make_task()
        mgr._RemoteTaskManager__unset_current_task()
        assert mgr.current_task is None

    def test_clears_worker_runners_info(self):
        mgr = _make_manager()
        mgr.worker_runners_info = {"key": "value"}
        mgr._RemoteTaskManager__unset_current_task()
        assert mgr.worker_runners_info == {}

    def test_clears_worker_log(self):
        mgr = _make_manager()
        mgr.worker_log = ["some log line"]
        mgr._RemoteTaskManager__unset_current_task()
        assert mgr.worker_log == []


# ===========================================================================
# TestProcessTaskQueueItem
# ===========================================================================


@pytest.mark.unittest
class TestProcessTaskQueueItem:
    def _setup(self, success=True):
        mgr = _make_manager()
        task = _make_task()
        mgr.current_task = task
        cq = queue.Queue()
        mgr.complete_queue = cq
        mgr._RemoteTaskManager__set_start_task_stats = MagicMock()
        mgr._RemoteTaskManager__set_finish_task_stats = MagicMock()
        mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor = MagicMock(return_value=success)
        mgr._RemoteTaskManager__unset_current_task = MagicMock()
        return mgr, task, cq

    def test_resets_progress_fields(self):
        mgr, task, _ = self._setup()
        mgr.worker_subprocess_percent = "50"
        mgr.worker_subprocess_elapsed = "120"
        mgr._RemoteTaskManager__process_task_queue_item()
        assert mgr.worker_subprocess_percent == "0"
        assert mgr.worker_subprocess_elapsed == "0"

    def test_sets_status_in_progress(self):
        mgr, task, _ = self._setup()
        mgr._RemoteTaskManager__process_task_queue_item()
        task.set_status.assert_called_once_with("in_progress")

    def test_calls_start_and_finish_stats(self):
        mgr, task, _ = self._setup()
        mgr._RemoteTaskManager__process_task_queue_item()
        mgr._RemoteTaskManager__set_start_task_stats.assert_called_once()
        mgr._RemoteTaskManager__set_finish_task_stats.assert_called_once()

    def test_sets_success_true_on_success(self):
        mgr, task, _ = self._setup(success=True)
        mgr._RemoteTaskManager__process_task_queue_item()
        task.set_success.assert_called_once_with(True)

    def test_sets_success_false_on_failure(self):
        mgr, task, _ = self._setup(success=False)
        mgr._RemoteTaskManager__process_task_queue_item()
        task.set_success.assert_called_once_with(False)

    def test_puts_task_in_complete_queue(self):
        mgr, task, cq = self._setup()
        mgr._RemoteTaskManager__process_task_queue_item()
        assert not cq.empty()
        assert cq.get_nowait() is task

    def test_calls_unset_current_task(self):
        mgr, task, _ = self._setup()
        mgr._RemoteTaskManager__process_task_queue_item()
        mgr._RemoteTaskManager__unset_current_task.assert_called_once()


# ===========================================================================
# TestSetStartTaskStats
# ===========================================================================


@pytest.mark.unittest
class TestSetStartTaskStats:
    def test_sets_start_time(self):
        mgr = _make_manager()
        mgr.current_task = _make_task()
        before = time.time()
        mgr._RemoteTaskManager__set_start_task_stats()
        assert mgr.start_time >= before

    def test_clears_finish_time(self):
        mgr = _make_manager()
        mgr.current_task = _make_task()
        mgr.finish_time = 999.0
        mgr._RemoteTaskManager__set_start_task_stats()
        assert mgr.finish_time is None

    def test_sets_task_processed_by_worker(self):
        mgr = _make_manager()
        task = _make_task()
        mgr.current_task = task
        mgr._RemoteTaskManager__set_start_task_stats()
        assert task.task.processed_by_worker == "TestRemoteWorker"


# ===========================================================================
# TestSetFinishTaskStats
# ===========================================================================


@pytest.mark.unittest
class TestSetFinishTaskStats:
    def test_sets_finish_time(self):
        mgr = _make_manager()
        mgr.current_task = _make_task()
        before = time.time()
        mgr._RemoteTaskManager__set_finish_task_stats()
        assert mgr.finish_time >= before

    def test_copies_finish_time_to_task(self):
        mgr = _make_manager()
        task = _make_task()
        mgr.current_task = task
        mgr._RemoteTaskManager__set_finish_task_stats()
        assert task.task.finish_time == mgr.finish_time


# ===========================================================================
# TestWriteFailureToWorkerLog
# ===========================================================================


@pytest.mark.unittest
class TestWriteFailureToWorkerLog:
    def test_appends_failure_header(self):
        mgr = _make_manager()
        mgr.current_task = _make_task()
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log()
        combined = "".join(mgr.worker_log)
        assert "REMOTE TASK FAILED" in combined

    def test_mentions_worker_name_in_log(self):
        mgr = _make_manager()
        mgr.current_task = _make_task()
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log()
        combined = "".join(mgr.worker_log)
        assert "TestRemoteWorker" in combined

    def test_calls_save_command_log(self):
        mgr = _make_manager()
        task = _make_task()
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log()
        task.save_command_log.assert_called_once()
        passed_log = task.save_command_log.call_args[0][0]
        assert isinstance(passed_log, list)


# ===========================================================================
# TestSendTaskToRemoteWorkerAndMonitor — file/library guard
# ===========================================================================


@pytest.mark.unittest
class TestSendTaskFileGuards:
    def test_returns_false_when_file_missing(self, tmp_path):
        mgr = _make_manager()
        task = _make_task(abspath=str(tmp_path / "missing.mkv"))
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr._RemoteTaskManager__write_failure_to_worker_log.assert_called_once()

    def test_returns_false_when_library_fetch_fails(self, tmp_path):
        src = tmp_path / "video.mkv"
        src.write_bytes(b"\x00" * 8)
        mgr = _make_manager()
        task = _make_task(abspath=str(src))
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        with patch("compresso.libs.remote_task_manager.Library", side_effect=Exception("db gone")):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr._RemoteTaskManager__write_failure_to_worker_log.assert_called_once()


# ===========================================================================
# TestSendTaskToRemoteWorkerAndMonitor — remote task creation via path
# ===========================================================================


@pytest.mark.unittest
class TestSendTaskRemotePathCreation:
    def _base_setup(self, tmp_path):
        """Return (mgr, task, mock_library, mock_links) with file on disk."""
        src = tmp_path / "video.mkv"
        src.write_bytes(b"\x00" * 8)

        mgr = _make_manager()
        task = _make_task(abspath=str(src))
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        mock_library = MagicMock()
        mock_library.get_name.return_value = "Movies"
        mock_library.get_path.return_value = str(tmp_path)

        return mgr, task, mock_library

    def test_task_already_exists_returns_false(self, tmp_path):
        mgr, task, mock_library = self._base_setup(tmp_path)
        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": False,
        }
        mgr.links.new_pending_task_create_on_remote_installation.return_value = {"error": "Task already exists for this path"}

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr._RemoteTaskManager__write_failure_to_worker_log.assert_called_once()

    def test_path_not_found_falls_back_to_send_file(self, tmp_path):
        mgr, task, mock_library = self._base_setup(tmp_path)
        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": False,
        }
        mgr.links.new_pending_task_create_on_remote_installation.return_value = {"error": "Path does not exist on remote host"}
        mgr.links.send_file_to_remote_installation.return_value = None  # fail to send

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False

    def test_none_response_falls_back_to_send_file(self, tmp_path):
        mgr, task, mock_library = self._base_setup(tmp_path)
        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": False,
        }
        mgr.links.new_pending_task_create_on_remote_installation.return_value = None
        mgr.links.send_file_to_remote_installation.return_value = None  # fail to send

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False

    def test_enable_remote_only_skips_path_creation(self, tmp_path):
        mgr, task, mock_library = self._base_setup(tmp_path)
        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": True,
        }
        mgr.links.send_file_to_remote_installation.return_value = None  # fail immediately

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        mgr.links.new_pending_task_create_on_remote_installation.assert_not_called()
        assert result is False


# ===========================================================================
# TestSendTaskToRemoteWorkerAndMonitor — file upload (send_file) path
# ===========================================================================


@pytest.mark.unittest
class TestSendTaskFileUpload:
    def _base_setup(self, tmp_path, file_size=512):
        src = tmp_path / "video.mkv"
        src.write_bytes(b"\x00" * file_size)

        mgr = _make_manager()
        task = _make_task(abspath=str(src))
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        mock_library = MagicMock()
        mock_library.get_name.return_value = "Movies"
        mock_library.get_path.return_value = str(tmp_path)

        # Force send_file path
        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": True,
        }

        return mgr, task, mock_library

    def test_upload_failure_returns_false(self, tmp_path):
        mgr, task, mock_library = self._base_setup(tmp_path)
        mgr.links.send_file_to_remote_installation.return_value = None

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr._RemoteTaskManager__write_failure_to_worker_log.assert_called_once()

    def test_checksum_mismatch_after_upload_returns_false(self, tmp_path):
        mgr, task, mock_library = self._base_setup(tmp_path)
        inst_info = _make_installation_info(enable_checksum_validation=True)
        mgr.installation_info = inst_info

        mgr.links.send_file_to_remote_installation.return_value = {"id": 99, "checksum": "BAD_CHECKSUM"}

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.common") as mock_common,
        ):
            mock_common.format_message.side_effect = lambda m, m2="": f"{m} {m2}".strip()
            mock_common.get_file_checksum.return_value = "CORRECT_CHECKSUM"
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr.links.remove_task_from_remote_installation.assert_called_once()

    def test_redundant_flag_exits_upload_loop(self, tmp_path):
        mgr, task, mock_library = self._base_setup(tmp_path, file_size=200_000_001)
        # Acquire lock always returns None so loop waits
        mgr.links.acquire_network_transfer_lock.return_value = None
        # Set redundant flag so loop exits
        mgr.redundant_flag.set()

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        # Loop exits without error because redundant_flag terminates it before upload
        # The result is False because remote_task_id remains None
        assert result is False

    def test_large_file_acquires_lock_before_upload(self, tmp_path):
        # File > 100 MB → should call acquire_network_transfer_lock
        mgr, task, mock_library = self._base_setup(tmp_path, file_size=200_000_001)
        lock_key = "lock-abc"
        mgr.links.acquire_network_transfer_lock.return_value = lock_key
        mgr.links.send_file_to_remote_installation.return_value = None  # fail after lock

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        mgr.links.acquire_network_transfer_lock.assert_called()
        assert result is False

    def test_upload_deadline_exceeded_returns_false(self, tmp_path):
        mgr, task, mock_library = self._base_setup(tmp_path)
        # Make monotonic time always exceed the deadline
        deadline_time = time.monotonic() + 1800

        call_count = 0

        def fake_monotonic():
            nonlocal call_count
            call_count += 1
            # First call (deadline assignment) returns real time; subsequent exceed it
            if call_count <= 2:
                return deadline_time - 1800
            return deadline_time + 1

        mgr.links.acquire_network_transfer_lock.return_value = None  # never acquires lock

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.time.monotonic", side_effect=fake_monotonic),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False


# ===========================================================================
# TestSendTaskToRemoteWorkerAndMonitor — set remote library and start task
# ===========================================================================


@pytest.mark.unittest
class TestSetRemoteLibraryAndStartTask:
    def _setup_past_upload(self, tmp_path):
        """Return manager that has a remote_task_id=5 ready for the post-upload phases."""
        src = tmp_path / "video.mkv"
        src.write_bytes(b"\x00" * 8)

        mgr = _make_manager()
        task = _make_task(abspath=str(src))
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        mock_library = MagicMock()
        mock_library.get_name.return_value = "Movies"
        mock_library.get_path.return_value = str(tmp_path)

        # Path-based creation succeeds immediately
        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": False,
        }
        mgr.links.new_pending_task_create_on_remote_installation.return_value = {"id": 5, "error": ""}

        return mgr, mock_library

    def test_set_library_failure_logs_warning_and_continues(self, tmp_path):
        mgr, mock_library = self._setup_past_upload(tmp_path)
        # set_the_remote_task_library returns no success (library name unmatched)
        mgr.links.set_the_remote_task_library.return_value = {"success": False}
        # Start task fails → triggers return False
        mgr.links.start_the_remote_task_by_id.return_value = {"success": False}

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        # Warning logged, but execution continues to start task
        assert result is False

    def test_set_library_none_retries(self, tmp_path):
        mgr, mock_library = self._setup_past_upload(tmp_path)
        call_count = 0

        def set_lib_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return None  # first call fails (no connection)
            return {"success": True}

        mgr.links.set_the_remote_task_library.side_effect = set_lib_side_effect
        mgr.links.start_the_remote_task_by_id.return_value = {"success": False}

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert call_count >= 2

    def test_start_task_failure_returns_false(self, tmp_path):
        mgr, mock_library = self._setup_past_upload(tmp_path)
        mgr.links.set_the_remote_task_library.return_value = {"success": True}
        mgr.links.start_the_remote_task_by_id.return_value = {"success": False}

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr.links.remove_task_from_remote_installation.assert_called()

    def test_start_task_none_retries(self, tmp_path):
        mgr, mock_library = self._setup_past_upload(tmp_path)
        mgr.links.set_the_remote_task_library.return_value = {"success": True}
        call_count = 0

        def start_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                return None
            return {"success": False}

        mgr.links.start_the_remote_task_by_id.side_effect = start_side_effect

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert call_count >= 2


# ===========================================================================
# TestSendTaskToRemoteWorkerAndMonitor — polling loop
# ===========================================================================


@pytest.mark.unittest
class TestPollingLoop:
    def _setup_polling(self, tmp_path):
        src = tmp_path / "video.mkv"
        src.write_bytes(b"\x00" * 8)

        mgr = _make_manager()
        task = _make_task(abspath=str(src))
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        mock_library = MagicMock()
        mock_library.get_name.return_value = "Movies"
        mock_library.get_path.return_value = str(tmp_path)

        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": False,
        }
        mgr.links.new_pending_task_create_on_remote_installation.return_value = {"id": 5, "error": ""}
        mgr.links.set_the_remote_task_library.return_value = {"success": True}
        mgr.links.start_the_remote_task_by_id.return_value = {"success": True}

        return mgr, mock_library

    def test_task_complete_triggers_download(self, tmp_path):
        mgr, mock_library = self._setup_polling(tmp_path)

        # Polling returns complete immediately
        mgr.links.get_remote_pending_task_state.return_value = {"results": [{"id": 5, "status": "complete"}]}
        # Download path: task_success=False so no file download needed
        mgr.links.fetch_remote_task_data.return_value = {"log": "done", "task_success": False, "task_state": None}

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False  # task_success=False → write failure → False

    def test_redundant_flag_in_polling_loop_returns_false(self, tmp_path):
        mgr, mock_library = self._setup_polling(tmp_path)
        mgr.worker_log = []
        # Set redundant flag so the polling loop exits on first iteration
        mgr.redundant_flag.set()
        mgr.links.get_remote_pending_task_state.return_value = {"results": []}

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False

    def test_task_removed_by_remote_returns_false(self, tmp_path):
        mgr, mock_library = self._setup_polling(tmp_path)

        # First response: task not in list (removed)
        mgr.links.get_remote_pending_task_state.return_value = {"results": [{"id": 999, "status": "in_progress"}]}

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr._RemoteTaskManager__write_failure_to_worker_log.assert_called()

    def test_connection_failure_applies_exponential_backoff(self, tmp_path):
        mgr, mock_library = self._setup_polling(tmp_path)

        poll_count = 0

        # Fail twice then set redundant flag to exit
        def fake_get_state(*args, **kwargs):
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 2:
                mgr.redundant_flag.set()
            return None  # connection failure

        mgr.links.get_remote_pending_task_state.side_effect = fake_get_state
        mgr.worker_log = []

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False

    def test_max_retry_window_exceeded_returns_false(self, tmp_path):
        mgr, mock_library = self._setup_polling(tmp_path)

        # first_failure_time will be set on first None response
        # Manipulate time so the window is immediately exceeded on second check
        real_time = time.time()
        time_calls = [real_time, real_time, real_time + 1900]  # third call exceeds 1800s window

        call_idx = [0]

        def fake_time():
            idx = call_idx[0]
            call_idx[0] += 1
            if idx < len(time_calls):
                return time_calls[idx]
            return real_time + 2000

        mgr.links.get_remote_pending_task_state.return_value = None  # always fail

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.time.time", side_effect=fake_time),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False

    def test_empty_results_list_marks_task_removed(self, tmp_path):
        mgr, mock_library = self._setup_polling(tmp_path)

        mgr.links.get_remote_pending_task_state.return_value = {"results": []}

        with patch("compresso.libs.remote_task_manager.Library", return_value=mock_library):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False


# ===========================================================================
# TestSendTaskToRemoteWorkerAndMonitor — download phase (local path branch)
# ===========================================================================


@pytest.mark.unittest
class TestDownloadPhaseLocalPath:
    def _setup_download(self, tmp_path, abspath_exists=True):
        """Set up manager past polling, task_success=True, abspath either exists or not."""
        src = tmp_path / "video.mkv"
        src.write_bytes(b"\x00" * 8)

        # Cache dir mimics compresso pattern: compresso_file_conversion-abcde-1234567890
        cache_dir = tmp_path / "compresso_file_conversion-abcde-1234567890"
        cache_dir.mkdir()

        # Remote result file sitting in a "remote pending library" directory
        if abspath_exists:
            remote_result = tmp_path / "remote_result-zzzzz-9999999999.mkv"
            remote_result.write_bytes(b"\x01" * 16)
            result_abspath = str(remote_result)
        else:
            result_abspath = str(tmp_path / "remote_result-zzzzz-9999999999.mkv")

        mgr = _make_manager()
        task = _make_task(abspath=str(src))
        task.get_cache_path.return_value = str(cache_dir / "video-abcde-1234567890.mkv")
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        mock_library = MagicMock()
        mock_library.get_name.return_value = "Movies"
        mock_library.get_path.return_value = str(tmp_path)

        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": False,
        }
        mgr.links.new_pending_task_create_on_remote_installation.return_value = {"id": 5, "error": ""}
        mgr.links.set_the_remote_task_library.return_value = {"success": True}
        mgr.links.start_the_remote_task_by_id.return_value = {"success": True}
        mgr.links.get_remote_pending_task_state.return_value = {"results": [{"id": 5, "status": "complete"}]}
        mgr.links.fetch_remote_task_data.return_value = {
            "log": "done",
            "task_success": True,
            "task_label": "remote_result-zzzzz-9999999999.mkv",
            "abspath": result_abspath,
            "checksum": "abc123",
            "task_state": None,
        }

        return mgr, mock_library, str(cache_dir)

    def test_local_abspath_exists_copies_file_successfully(self, tmp_path):
        mgr, mock_library, cache_dir = self._setup_download(tmp_path, abspath_exists=True)

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.TaskDataStore"),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is True

    def test_local_abspath_missing_random_string_returns_false(self, tmp_path):
        mgr, mock_library, cache_dir = self._setup_download(tmp_path, abspath_exists=True)
        # Override task cache path to have NO random string pattern
        mgr.current_task.get_cache_path.return_value = str(tmp_path / "no_pattern_here.mkv")
        mgr.links.fetch_remote_task_data.return_value["abspath"] = str(tmp_path / "remote_result-zzzzz-9999999999.mkv")
        # Make abspath exist
        (tmp_path / "remote_result-zzzzz-9999999999.mkv").write_bytes(b"\x01" * 16)

        # cache_directory will also not have the pattern now
        bad_cache_dir = tmp_path / "nocachepattern"
        bad_cache_dir.mkdir()
        mgr.current_task.get_cache_path.return_value = str(bad_cache_dir / "video.mkv")

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.TaskDataStore"),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False

    def test_copy_failure_returns_false(self, tmp_path):

        mgr, mock_library, cache_dir = self._setup_download(tmp_path, abspath_exists=True)

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.TaskDataStore"),
            patch("compresso.libs.remote_task_manager.shutil.copy", side_effect=FileNotFoundError("gone")),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr._RemoteTaskManager__write_failure_to_worker_log.assert_called()


# ===========================================================================
# TestSendTaskToRemoteWorkerAndMonitor — download phase (network download branch)
# ===========================================================================


@pytest.mark.unittest
class TestDownloadPhaseNetworkDownload:
    def _setup_network_download(self, tmp_path):
        src = tmp_path / "video.mkv"
        src.write_bytes(b"\x00" * 8)

        cache_dir = tmp_path / "compresso_file_conversion-abcde-1234567890"
        cache_dir.mkdir()

        # abspath does NOT exist → triggers network download branch
        result_abspath = str(tmp_path / "nonexistent_remote_result.mkv")

        mgr = _make_manager()
        task = _make_task(abspath=str(src))
        task.get_cache_path.return_value = str(cache_dir / "output-abcde-1234567890.mkv")
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        mock_library = MagicMock()
        mock_library.get_name.return_value = "Movies"
        mock_library.get_path.return_value = str(tmp_path)

        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": False,
        }
        mgr.links.new_pending_task_create_on_remote_installation.return_value = {"id": 5, "error": ""}
        mgr.links.set_the_remote_task_library.return_value = {"success": True}
        mgr.links.start_the_remote_task_by_id.return_value = {"success": True}
        mgr.links.get_remote_pending_task_state.return_value = {"results": [{"id": 5, "status": "complete"}]}
        mgr.links.fetch_remote_task_data.return_value = {
            "log": "done",
            "task_success": True,
            "task_label": "output.mkv",
            "abspath": result_abspath,
            "checksum": "correcthash",
            "task_state": None,
        }

        return mgr, mock_library, str(cache_dir)

    def test_download_success_returns_true(self, tmp_path):
        mgr, mock_library, cache_dir = self._setup_network_download(tmp_path)
        lock_key = "lock-xyz"
        mgr.links.acquire_network_transfer_lock.return_value = lock_key
        mgr.links.fetch_remote_task_completed_file.return_value = True

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.TaskDataStore"),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is True
        mgr.links.remove_task_from_remote_installation.assert_called()

    def test_download_failure_returns_false(self, tmp_path):
        mgr, mock_library, cache_dir = self._setup_network_download(tmp_path)
        lock_key = "lock-xyz"
        mgr.links.acquire_network_transfer_lock.return_value = lock_key
        mgr.links.fetch_remote_task_completed_file.return_value = False

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.TaskDataStore"),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr.links.remove_task_from_remote_installation.assert_called()

    def test_checksum_mismatch_after_download_returns_false(self, tmp_path):
        mgr, mock_library, cache_dir = self._setup_network_download(tmp_path)
        inst_info = _make_installation_info(enable_checksum_validation=True)
        mgr.installation_info = inst_info

        lock_key = "lock-xyz"
        mgr.links.acquire_network_transfer_lock.return_value = lock_key
        mgr.links.fetch_remote_task_completed_file.return_value = True

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.TaskDataStore"),
            patch("compresso.libs.remote_task_manager.common") as mock_common,
        ):
            mock_common.format_message.side_effect = lambda m, m2="": f"{m} {m2}".strip()
            mock_common.get_file_checksum.return_value = "WRONG_HASH"
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr.links.remove_task_from_remote_installation.assert_called()

    def test_redundant_flag_during_download_loop_returns_false(self, tmp_path):
        mgr, mock_library, cache_dir = self._setup_network_download(tmp_path)
        # Lock always unavailable; redundant flag set so loop exits
        mgr.links.acquire_network_transfer_lock.return_value = None
        mgr.redundant_flag.set()

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.TaskDataStore"),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False

    def test_remote_task_data_fetch_failure_returns_false(self, tmp_path):
        src = tmp_path / "video.mkv"
        src.write_bytes(b"\x00" * 8)

        cache_dir = tmp_path / "compresso_file_conversion-abcde-1234567890"
        cache_dir.mkdir()

        mgr = _make_manager()
        task = _make_task(abspath=str(src))
        task.get_cache_path.return_value = str(cache_dir / "output-abcde-1234567890.mkv")
        mgr.current_task = task
        mgr.worker_log = []
        mgr._RemoteTaskManager__write_failure_to_worker_log = MagicMock()

        mock_library = MagicMock()
        mock_library.get_name.return_value = "Movies"
        mock_library.get_path.return_value = str(tmp_path)

        mgr.links.get_the_remote_library_config_by_name.return_value = {
            "id": 7,
            "path": "/remote/lib",
            "enable_remote_only": False,
        }
        mgr.links.new_pending_task_create_on_remote_installation.return_value = {"id": 5, "error": ""}
        mgr.links.set_the_remote_task_library.return_value = {"success": True}
        mgr.links.start_the_remote_task_by_id.return_value = {"success": True}
        mgr.links.get_remote_pending_task_state.return_value = {"results": [{"id": 5, "status": "complete"}]}
        mgr.links.fetch_remote_task_data.return_value = None  # fetch fails

        with (
            patch("compresso.libs.remote_task_manager.Library", return_value=mock_library),
            patch("compresso.libs.remote_task_manager.TaskDataStore"),
        ):
            result = mgr._RemoteTaskManager__send_task_to_remote_worker_and_monitor()

        assert result is False
        mgr._RemoteTaskManager__write_failure_to_worker_log.assert_called()
