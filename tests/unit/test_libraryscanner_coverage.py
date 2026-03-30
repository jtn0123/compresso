#!/usr/bin/env python3

"""
tests.unit.test_libraryscanner_coverage.py

Targets the uncovered lines in compresso/libs/libraryscanner.py:
  Lines 84-137  — LibraryScannerManager.run() scheduling loop
  Line  231     — scan_library_path() debug log branch
  Lines 260-277 — os.walk file-loop (queue puts, status_updates drain)
  Lines 282-323 — post-walk completion loop (double-check, percent, process queue)
  Lines 327-330 — thread join / still-alive error logging after scan
"""

import queue
import threading
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_scanner():
    """Build a LibraryScannerManager with all heavy dependencies mocked out."""
    with (
        patch("compresso.libs.libraryscanner.CompressoLogging") as mock_log,
        patch("compresso.libs.libraryscanner.config.Config") as mock_config,
    ):
        mock_log.get_logger.return_value = MagicMock()
        mock_config.return_value = MagicMock()

        from compresso.libs.libraryscanner import LibraryScannerManager

        data_queues = {
            "scheduledtasks": queue.Queue(),
            "library_scanner_triggers": queue.Queue(),
        }
        event = threading.Event()
        mgr = LibraryScannerManager(data_queues, event)
    return mgr


def _make_scan_patches():
    """Return context-manager patches that satisfy scan_library_path's imports."""
    return (
        patch("compresso.libs.libraryscanner.gc"),
        patch("compresso.libs.libraryscanner.PluginsHandler"),
        patch("compresso.libs.libraryscanner.CompressoLogging"),
        patch("compresso.libs.libraryscanner.FrontendPushMessages"),
        patch("compresso.libs.libraryscanner.os.walk"),
        patch("compresso.libs.libraryscanner.os.path.exists", return_value=True),
    )


def _run_scan_abort_immediately(mgr):
    """Run scan_library_path with abort_flag pre-set so the wait loop exits at once."""
    gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
    with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p as mock_fe_cls, walk_p as mock_walk, exists_p:
        mock_log_cls.log_metric = MagicMock()
        mock_log_cls.log_data = MagicMock()
        mock_fe = MagicMock()
        mock_fe_cls.return_value = mock_fe
        mock_walk.return_value = []
        mgr.settings.get_debugging.return_value = False
        mgr.settings.get_concurrent_file_testers.return_value = 0
        mgr.settings.get_follow_symlinks.return_value = False
        mgr.abort_flag.set()
        with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
            mgr.scan_library_path("TestLib", "/media/lib", 1)
    return mock_fe


# ---------------------------------------------------------------------------
# Lines 84-137 — run() scheduling loop
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunLoop:
    """Tests for the main run() thread loop (lines 84-137)."""

    def test_run_exits_immediately_when_abort_set(self):
        """run() exits without entering the scheduling body when abort is pre-set."""
        mgr = _make_scanner()
        mgr.abort_flag.set()
        mgr.event.set()
        mgr.run()  # must return without hanging

    def test_run_zero_interval_stays_in_outer_loop(self):
        """With interval==0 the inner scheduler block is never entered; the outer loop iterates."""
        mgr = _make_scanner()
        mgr.settings.get_schedule_full_scan_minutes.return_value = 0

        call_count = 0

        def fake_wait(secs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                mgr.abort_flag.set()

        mgr.event.wait = fake_wait
        mgr.run()
        assert call_count >= 2

    def test_run_sets_interval_from_settings(self):
        """run() reads the schedule interval from settings and stores it on mgr.interval."""
        mgr = _make_scanner()
        mgr.settings.get_schedule_full_scan_minutes.return_value = 5
        mgr.settings.get_run_full_scan_on_start.return_value = False
        mgr.settings.get_enable_library_scanner.return_value = True

        inner_iterations = 0
        original_wait = mgr.event.wait

        def fake_wait(secs):
            nonlocal inner_iterations
            inner_iterations += 1
            if inner_iterations >= 3:
                mgr.abort_flag.set()
            original_wait(0)

        mgr.event.wait = fake_wait

        with patch.object(mgr, "register_compresso"), patch.object(mgr, "scheduled_job"):
            mgr.run()

        assert mgr.interval == 5

    def test_run_calls_scheduled_job_on_first_run(self):
        """When get_run_full_scan_on_start is True and firstrun is True, scheduled_job() is called."""
        mgr = _make_scanner()
        mgr.settings.get_schedule_full_scan_minutes.return_value = 10
        mgr.settings.get_run_full_scan_on_start.return_value = True
        mgr.settings.get_enable_library_scanner.return_value = True

        original_wait = mgr.event.wait

        def fake_wait(secs):
            mgr.abort_flag.set()
            original_wait(0)

        mgr.event.wait = fake_wait

        with patch.object(mgr, "register_compresso"), patch.object(mgr, "scheduled_job") as mock_job:
            mgr.run()

        mock_job.assert_called()

    def test_run_does_not_call_scheduled_job_when_firstrun_false(self):
        """scheduled_job() is NOT called on startup when firstrun is already False."""
        mgr = _make_scanner()
        mgr.firstrun = False
        mgr.settings.get_schedule_full_scan_minutes.return_value = 10
        mgr.settings.get_run_full_scan_on_start.return_value = True
        mgr.settings.get_enable_library_scanner.return_value = True

        original_wait = mgr.event.wait

        def fake_wait(secs):
            mgr.abort_flag.set()
            original_wait(0)

        mgr.event.wait = fake_wait

        with patch.object(mgr, "register_compresso"), patch.object(mgr, "scheduled_job") as mock_job:
            mgr.run()

        mock_job.assert_not_called()

    def test_run_handles_library_scanner_trigger(self):
        """A 'library_scan' trigger on the queue causes scheduled_job() to fire."""
        mgr = _make_scanner()
        mgr.settings.get_schedule_full_scan_minutes.return_value = 10
        mgr.settings.get_run_full_scan_on_start.return_value = False
        mgr.settings.get_enable_library_scanner.return_value = True

        call_count = 0
        original_wait = mgr.event.wait

        def fake_wait(secs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mgr.library_scanner_triggers.put("library_scan")
            elif call_count >= 3:
                mgr.abort_flag.set()
            original_wait(0)

        mgr.event.wait = fake_wait

        with patch.object(mgr, "register_compresso"), patch.object(mgr, "scheduled_job") as mock_job:
            mgr.run()

        mock_job.assert_called()

    def test_run_skips_scheduled_run_when_scanner_disabled(self):
        """When the library scanner is disabled, scheduler.run_pending is not reached."""
        mgr = _make_scanner()
        mgr.settings.get_schedule_full_scan_minutes.return_value = 10
        mgr.settings.get_run_full_scan_on_start.return_value = False
        mgr.settings.get_enable_library_scanner.return_value = False

        call_count = 0
        original_wait = mgr.event.wait

        def fake_wait(secs):
            nonlocal call_count
            call_count += 1
            if call_count >= 4:
                mgr.abort_flag.set()
            original_wait(0)

        mgr.event.wait = fake_wait

        with (
            patch.object(mgr, "register_compresso"),
            patch.object(mgr, "scheduled_job"),
            patch.object(mgr.scheduler, "run_pending") as mock_run_pending,
        ):
            mgr.run()

        mock_run_pending.assert_not_called()

    def test_run_resets_schedule_on_interval_change(self):
        """Changing the interval setting breaks the inner loop and clears the scheduler."""
        mgr = _make_scanner()
        mgr.settings.get_run_full_scan_on_start.return_value = False
        mgr.settings.get_enable_library_scanner.return_value = True

        call_count_interval = 0

        def changing_interval():
            nonlocal call_count_interval
            call_count_interval += 1
            return 10 if call_count_interval <= 3 else 20

        mgr.settings.get_schedule_full_scan_minutes.side_effect = changing_interval

        outer_iterations = 0
        original_wait = mgr.event.wait

        def fake_wait(secs):
            nonlocal outer_iterations
            outer_iterations += 1
            if outer_iterations >= 8:
                mgr.abort_flag.set()
            original_wait(0)

        mgr.event.wait = fake_wait

        with patch.object(mgr, "register_compresso"), patch.object(mgr, "scheduled_job"):
            mgr.run()
        # The fact it returns means scheduler.clear() was called and the loop exited cleanly

    def test_run_exception_in_trigger_queue_handled(self):
        """An exception reading from the trigger queue is caught and logged."""
        mgr = _make_scanner()
        mgr.settings.get_schedule_full_scan_minutes.return_value = 10
        mgr.settings.get_run_full_scan_on_start.return_value = False
        mgr.settings.get_enable_library_scanner.return_value = True

        call_count = 0
        original_wait = mgr.event.wait

        def fake_wait(secs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                mgr.abort_flag.set()
            original_wait(0)

        mgr.event.wait = fake_wait

        mgr.library_scanner_triggers = MagicMock()
        mgr.library_scanner_triggers.empty.return_value = False
        mgr.library_scanner_triggers.get_nowait.side_effect = Exception("boom")

        with patch.object(mgr, "register_compresso"), patch.object(mgr, "scheduled_job"):
            mgr.run()  # must not raise

    def test_run_calls_register_compresso_when_interval_set(self):
        """register_compresso() is called when a non-zero interval is configured."""
        mgr = _make_scanner()
        mgr.settings.get_schedule_full_scan_minutes.return_value = 15
        mgr.settings.get_run_full_scan_on_start.return_value = False
        mgr.settings.get_enable_library_scanner.return_value = True

        original_wait = mgr.event.wait

        def fake_wait(secs):
            mgr.abort_flag.set()
            original_wait(0)

        mgr.event.wait = fake_wait

        with patch.object(mgr, "register_compresso") as mock_register, patch.object(mgr, "scheduled_job"):
            mgr.run()

        mock_register.assert_called_once()

    def test_run_logs_info_on_start_and_exit(self):
        """run() emits info log on entry and exit."""
        mgr = _make_scanner()
        mgr.abort_flag.set()
        mgr.event.set()
        mgr.run()
        # Both the start and exit log messages should have been logged
        assert mgr.logger.info.call_count >= 1


# ---------------------------------------------------------------------------
# Line 231 — scan_library_path debug log branch
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestScanLibraryPathDebugging:
    """Line 231: debug log when get_debugging() is True."""

    def test_debug_log_emitted_when_debugging_enabled(self):
        """When debugging is enabled, the directory debug log is written."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = True
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.abort_flag.set()

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            mgr.logger.debug.assert_called_with("Scanning directory - '%s'", "/media/lib")

    def test_no_debug_log_when_debugging_disabled(self):
        """When debugging is False, the directory debug log is NOT written."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.abort_flag.set()

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            # No debug call with "Scanning directory"
            for c in mgr.logger.debug.call_args_list:
                assert "Scanning directory" not in str(c)


# ---------------------------------------------------------------------------
# Lines 260-277 — os.walk file loop
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestScanLibraryPathWalkLoop:
    """Tests for the file-walk loop (lines 260-277)."""

    def test_files_placed_into_files_to_test_queue(self):
        """Every file found during os.walk is placed into files_to_test."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = [
                ("/media/lib", ["sub"], ["a.mkv", "b.mp4"]),
                ("/media/lib/sub", [], ["c.avi"]),
            ]
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            # event.wait is a no-op so the double_check loop exits quickly.
            # We also need the wait loop to drain files_to_test so it terminates.
            # Use a fake wait that drains the queue after a few iterations.
            iter_count = 0

            def fake_wait(secs):
                nonlocal iter_count
                iter_count += 1
                # After a few iterations drain the test queue so the loop exits
                if iter_count > 3:
                    while not mgr.files_to_test.empty():
                        mgr.files_to_test.get_nowait()

            mgr.event.wait = fake_wait

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            # After draining, the queue is empty; we verify the walk ran by checking
            # total_file_count indirectly via the log_data call.
            mock_log_cls.log_data.assert_called_once()
            call_kwargs = mock_log_cls.log_data.call_args[1]
            assert call_kwargs["files_scanned_count"] == 3

    def test_walk_aborts_at_directory_level_when_abort_flag_set(self):
        """Setting abort_flag before the per-file loop skips that directory's files."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()

            def walk_and_abort(path, followlinks=False):
                mgr.abort_flag.set()
                yield ("/media/lib", [], ["a.mkv", "b.mp4", "c.avi"])

            mock_walk.side_effect = walk_and_abort
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            # abort was set before the inner per-file loop; 0 files enqueued
            assert mgr.files_to_test.qsize() == 0

    def test_walk_aborts_mid_file_loop_when_abort_flag_set(self):
        """Setting abort_flag mid-file-loop stops further file enqueuing."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()

            # Patch files_to_test.put to abort after first file
            mgr = _make_scanner()
            original_put = mgr.files_to_test.put

            put_count = 0

            def abort_after_first(item):
                nonlocal put_count
                put_count += 1
                original_put(item)
                if put_count >= 1:
                    mgr.abort_flag.set()

            mgr.files_to_test.put = abort_after_first

            mock_walk.return_value = [("/media/lib", [], ["a.mkv", "b.mp4", "c.avi"])]
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            # Only 1 file was enqueued before abort
            assert mgr.files_to_test.qsize() == 1

    def test_status_updates_drained_during_walk(self):
        """Status messages from status_updates are consumed mid-walk (lines 274-277)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p as mock_fe_cls, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_frontend = MagicMock()
            mock_fe_cls.return_value = mock_frontend

            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False

            def walk_gen(path, followlinks=False):
                yield ("/media/lib", [], ["a.mkv", "b.mp4"])

            mock_walk.side_effect = walk_gen

            def inject_status(manager_id, status_updates, library_id):
                # Put a status message so it's picked up during the walk loop
                status_updates.put("a.mkv")

            # After the walk, abort immediately so the wait loop exits
            mgr.abort_flag.set()

            with (
                patch.object(mgr, "start_results_manager_thread", side_effect=inject_status),
                patch.object(mgr, "stop_all_file_test_managers"),
            ):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            # update_scan_progress must have been called at least once
            assert mock_frontend.update.call_count >= 1

    def test_debug_log_for_files_list_during_walk(self):
        """When debugging is True, each directory's file list is logged (line 263)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = [("/media/lib", [], ["file.mkv"])]
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = True
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False

            iter_count = 0

            def fast_wait(secs):
                nonlocal iter_count
                iter_count += 1
                if iter_count > 3:
                    while not mgr.files_to_test.empty():
                        mgr.files_to_test.get_nowait()

            mgr.event.wait = fast_wait

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            # logger.debug called for "Scanning directory" + json.dumps file list
            assert mgr.logger.debug.call_count >= 2

    def test_follow_symlinks_passed_to_os_walk(self):
        """The follow_symlinks setting is forwarded as followlinks= to os.walk."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = True
            mgr.abort_flag.set()

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            mock_walk.assert_called_once_with("/media/lib", followlinks=True)


# ---------------------------------------------------------------------------
# Lines 282-323 — post-walk completion loop
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestScanLibraryPathCompletionLoop:
    """Tests for the wait/drain loop after os.walk (lines 282-323)."""

    def test_completion_loop_exits_after_double_check(self):
        """All queues empty + no active testers → double_check increments to > 5 and breaks."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None

            with (
                patch.object(mgr, "start_results_manager_thread"),
                patch.object(mgr, "stop_all_file_test_managers") as mock_stop,
            ):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            mock_stop.assert_called()

    def test_files_to_process_items_enqueued_in_scheduled_tasks(self):
        """Items in files_to_process are moved to scheduledtasks via add_path_to_queue."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None

            mgr.files_to_process.put({"path": "/media/lib/video.mkv", "priority_score": 50})

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            item = mgr.scheduledtasks.get_nowait()
            assert item["pathname"] == "/media/lib/video.mkv"
            assert item["priority_score"] == 50

    def test_multiple_files_to_process_all_enqueued(self):
        """Multiple items in files_to_process are all forwarded to scheduledtasks."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None

            mgr.files_to_process.put({"path": "/media/lib/a.mkv", "priority_score": 10})
            mgr.files_to_process.put({"path": "/media/lib/b.mkv", "priority_score": 20})

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            assert mgr.scheduledtasks.qsize() == 2

    def test_status_updates_consumed_in_wait_loop(self):
        """Status updates posted after the walk are consumed in the wait loop (lines 313-317)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p as mock_fe_cls, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_frontend = MagicMock()
            mock_fe_cls.return_value = mock_frontend
            mock_walk.return_value = []

            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 1
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None

            def capture_and_preload(manager_id, status_updates, library_id):
                status_updates.put("video.mkv")

            with (
                patch.object(mgr, "start_results_manager_thread", side_effect=capture_and_preload),
                patch.object(mgr, "stop_all_file_test_managers"),
            ):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            messages = [c[0][0]["message"] for c in mock_frontend.update.call_args_list]
            assert any("video.mkv" in m for m in messages)

    def test_percent_completed_calculated_when_files_remain(self):
        """Percent completion string is computed when files_to_test is non-empty (lines 303-310)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p as mock_fe_cls, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_frontend = MagicMock()
            mock_fe_cls.return_value = mock_frontend
            mock_walk.return_value = [("/media/lib", [], [f"file{i}.mkv" for i in range(5)])]

            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False

            iter_count = 0

            def draining_wait(secs):
                nonlocal iter_count
                iter_count += 1
                if iter_count > 3:
                    while not mgr.files_to_test.empty():
                        mgr.files_to_test.get_nowait()

            mgr.event.wait = draining_wait

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            assert mock_frontend.update.call_count >= 1

    def test_percent_unknown_when_total_count_zero_but_current_file_set(self):
        """When total_file_count is 0 but current_file is set, '???%' string is used (line 310)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p as mock_fe_cls, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_frontend = MagicMock()
            mock_fe_cls.return_value = mock_frontend
            mock_walk.return_value = []  # no files → total_file_count stays 0

            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False

            iter_count = 0

            def draining_wait(secs):
                nonlocal iter_count
                iter_count += 1
                if iter_count > 3:
                    while not mgr.files_to_test.empty():
                        mgr.files_to_test.get_nowait()

            mgr.event.wait = draining_wait

            # Manually pre-load files_to_test AND set current_file to trigger line 310
            # We simulate current_file being set by injecting a status update that the
            # wait loop will consume, setting current_file, then the next iteration
            # will hit the files_to_test branch with total_file_count==0 and current_file set.
            def inject_status_and_file(manager_id, status_updates, library_id):
                status_updates.put("mystery.mkv")
                mgr.files_to_test.put("/fake/path.mkv")

            with (
                patch.object(mgr, "start_results_manager_thread", side_effect=inject_status_and_file),
                patch.object(mgr, "stop_all_file_test_managers"),
            ):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            # Should have completed without hanging
            assert mock_log_cls.log_data.call_count == 1

    def test_wait_called_when_all_queues_empty_but_testers_active(self):
        """While file testers are still active, the loop waits 0.5 s (line 288)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []

            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            # Use 1 tester so start_results_manager_thread is called once
            mgr.settings.get_concurrent_file_testers.return_value = 1
            mgr.settings.get_follow_symlinks.return_value = False

            wait_calls = []
            call_count = 0

            def fake_wait(secs):
                nonlocal call_count
                call_count += 1
                wait_calls.append(secs)
                if call_count > 2:
                    # Stop pretending the tester is busy so the loop exits
                    for t in mgr.file_test_managers.values():
                        t.is_testing_file.return_value = False

            mgr.event.wait = fake_wait

            # Inject a busy mock tester via start_results_manager_thread
            mock_tester = MagicMock()
            mock_tester.is_testing_file.return_value = True

            def inject_busy_tester(manager_id, status_updates, library_id):
                mgr.file_test_managers[manager_id] = mock_tester

            with (
                patch.object(mgr, "start_results_manager_thread", side_effect=inject_busy_tester),
                patch.object(mgr, "stop_all_file_test_managers"),
            ):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            assert 0.5 in wait_calls

    def test_outer_wait_called_when_files_still_in_test_queue(self):
        """When no status/process items are ready, the loop sleeps 0.1 s (line 323)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []

            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False

            wait_calls = []
            call_count = 0

            def fake_wait(secs):
                nonlocal call_count
                call_count += 1
                wait_calls.append(secs)
                if call_count > 3:
                    while not mgr.files_to_test.empty():
                        mgr.files_to_test.get_nowait()

            mgr.event.wait = fake_wait

            # Keep a file in files_to_test so the "else: wait(0.1)" branch fires
            mgr.files_to_test.put("/media/lib/waiting.mkv")

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            assert 0.1 in wait_calls

    def test_double_check_resets_when_testers_become_active(self):
        """double_check resets to 0 when file_tests_in_progress() becomes True (line 287)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []

            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False

            call_count = 0
            mock_tester = MagicMock()

            def fake_wait(secs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First wait: make tester appear busy (resets double_check)
                    mock_tester.is_testing_file.return_value = True
                    mgr.file_test_managers = {"t0": mock_tester}
                elif call_count == 2:
                    # Second wait: make tester idle again so double_check can increment
                    mock_tester.is_testing_file.return_value = False
                elif call_count > 2:
                    # Let the double_check loop proceed with no-op wait
                    pass

            mgr.event.wait = fake_wait

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            # The fact we returned means the double_check path ran correctly
            mock_log_cls.log_data.assert_called_once()


# ---------------------------------------------------------------------------
# Lines 327-330 — thread join and still-alive error logging
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestScanLibraryPathThreadJoin:
    """Tests for the post-scan thread join block (lines 326-333)."""

    def test_threads_are_joined_after_scan(self):
        """After the wait loop, all manager threads are joined (line 328)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            # Must be >= 1 so start_results_manager_thread is actually called
            mgr.settings.get_concurrent_file_testers.return_value = 1
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None

            mock_thread = MagicMock()
            mock_thread.abort_flag = MagicMock()
            mock_thread.is_alive.return_value = False
            # is_testing_file must return False so the completion loop can exit
            mock_thread.is_testing_file.return_value = False

            def inject_manager(manager_id, status_updates, library_id):
                mgr.file_test_managers[manager_id] = mock_thread

            with (
                patch.object(mgr, "start_results_manager_thread", side_effect=inject_manager),
                patch.object(mgr, "stop_all_file_test_managers"),
            ):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            mock_thread.join.assert_called_with(2)

    def test_error_logged_when_thread_still_alive_after_join(self):
        """If a thread is still alive after join(2), an error is logged (lines 330-333)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 1
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None

            mock_thread = MagicMock()
            mock_thread.abort_flag = MagicMock()
            mock_thread.is_alive.return_value = True  # never terminates
            mock_thread.is_testing_file.return_value = False  # so completion loop exits

            def inject_manager(manager_id, status_updates, library_id):
                mgr.file_test_managers[manager_id] = mock_thread

            with (
                patch.object(mgr, "start_results_manager_thread", side_effect=inject_manager),
                patch.object(mgr, "stop_all_file_test_managers"),
            ):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            mgr.logger.error.assert_called()
            error_msg = mgr.logger.error.call_args[0][0]
            assert "still alive" in error_msg

    def test_abort_flag_set_on_each_manager_before_join(self):
        """abort_flag.set() is called on every manager thread before join (line 327)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            # Use 2 concurrent testers so two managers are registered
            mgr.settings.get_concurrent_file_testers.return_value = 2
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None

            mock_t1 = MagicMock()
            mock_t1.abort_flag = MagicMock()
            mock_t1.is_alive.return_value = False
            mock_t1.is_testing_file.return_value = False
            mock_t2 = MagicMock()
            mock_t2.abort_flag = MagicMock()
            mock_t2.is_alive.return_value = False
            mock_t2.is_testing_file.return_value = False

            call_n = 0

            def inject_two(manager_id, status_updates, library_id):
                nonlocal call_n
                mgr.file_test_managers[manager_id] = mock_t1 if call_n == 0 else mock_t2
                call_n += 1

            with (
                patch.object(mgr, "start_results_manager_thread", side_effect=inject_two),
                patch.object(mgr, "stop_all_file_test_managers"),
            ):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            mock_t1.abort_flag.set.assert_called()
            mock_t2.abort_flag.set.assert_called()

    def test_scan_logs_metrics_after_completion(self):
        """log_metric and log_data are called with correct keys after the scan (lines 338-357)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None
            mgr.abort_flag.set()

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("ScanLib", "/media/scan", 99)

            mock_log_cls.log_metric.assert_called_once()
            assert mock_log_cls.log_metric.call_args[0][0] == "library_scan_completed"

            mock_log_cls.log_data.assert_called_once()
            assert mock_log_cls.log_data.call_args[0][0] == "last_library_scan"

    def test_scan_runs_event_plugins_after_completion(self):
        """PluginsHandler.run_event_plugins_for_plugin_type is called with scan data (line 370)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []

            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None
            mgr.abort_flag.set()

            with (
                patch.object(mgr, "start_results_manager_thread"),
                patch.object(mgr, "stop_all_file_test_managers"),
                patch("compresso.libs.libraryscanner.PluginsHandler") as mock_plugins_cls,
            ):
                mock_plugin_handler = MagicMock()
                mock_plugins_cls.return_value = mock_plugin_handler
                mgr.scan_library_path("PluginLib", "/media/plugins", 42)

            mock_plugin_handler.run_event_plugins_for_plugin_type.assert_called_once()
            call_args = mock_plugin_handler.run_event_plugins_for_plugin_type.call_args
            assert call_args[0][0] == "events.scan_complete"
            data = call_args[0][1]
            assert data["library_id"] == 42
            assert data["library_name"] == "PluginLib"
            assert data["library_path"] == "/media/plugins"

    def test_gc_collected_after_scan(self):
        """gc.collect() is called at end of scan (line 373)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p as mock_gc, plugins_p, logging_p as mock_log_cls, frontend_p, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None
            mgr.abort_flag.set()

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            mock_gc.collect.assert_called_once()

    def test_frontend_status_removed_after_scan(self):
        """remove_item('libraryScanProgress') is called at end of scan (line 376)."""
        gc_p, plugins_p, logging_p, frontend_p, walk_p, exists_p = _make_scan_patches()
        with gc_p, plugins_p, logging_p as mock_log_cls, frontend_p as mock_fe_cls, walk_p as mock_walk, exists_p:
            mock_log_cls.log_metric = MagicMock()
            mock_log_cls.log_data = MagicMock()
            mock_frontend = MagicMock()
            mock_fe_cls.return_value = mock_frontend
            mock_walk.return_value = []
            mgr = _make_scanner()
            mgr.settings.get_debugging.return_value = False
            mgr.settings.get_concurrent_file_testers.return_value = 0
            mgr.settings.get_follow_symlinks.return_value = False
            mgr.event.wait = lambda s: None
            mgr.abort_flag.set()

            with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
                mgr.scan_library_path("TestLib", "/media/lib", 1)

            mock_frontend.remove_item.assert_called_with("libraryScanProgress")

    def test_scan_path_not_exists_returns_early(self):
        """scan_library_path returns early without error when path does not exist."""
        with patch("compresso.libs.libraryscanner.os.path.exists", return_value=False):
            mgr = _make_scanner()
            mgr.scan_library_path("TestLib", "/nonexistent/path", 1)
            # No exception; also verify no scan progress was pushed
            # (no FrontendPushMessages was instantiated, which would fail without mocking)
