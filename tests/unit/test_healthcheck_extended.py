#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_healthcheck_extended.py

    Extended unit tests for compresso.libs.healthcheck.HealthCheckManager.
    Tests worker management methods: set_worker_count, cancel_scan,
    _scan_worker, and edge cases of _run_library_scan.
"""

import os
import queue
import threading
import time

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.healthcheck import HealthCheckManager


@pytest.fixture(autouse=True)
def reset_healthcheck_class_state():
    """Reset class-level state between tests."""
    with HealthCheckManager._lock:
        HealthCheckManager._scanning = False
        HealthCheckManager._cancel_event.clear()
        HealthCheckManager._scan_progress = {
            'total': 0,
            'checked': 0,
            'library_id': None,
            'worker_count': 0,
            'max_workers': 1,
            'workers': {},
            'start_time': None,
            'files_per_second': 0.0,
            'eta_seconds': 0,
        }
        HealthCheckManager._worker_count_requested = 1
    with HealthCheckManager._file_locks_lock:
        HealthCheckManager._file_locks.clear()
    yield
    with HealthCheckManager._lock:
        HealthCheckManager._scanning = False
        HealthCheckManager._cancel_event.clear()
        HealthCheckManager._worker_count_requested = 1


# ------------------------------------------------------------------
# set_worker_count
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestSetWorkerCount:

    def test_set_valid_count(self):
        HealthCheckManager.set_worker_count(4)
        assert HealthCheckManager.get_worker_count() == 4

    def test_clamps_to_minimum_1(self):
        HealthCheckManager.set_worker_count(0)
        assert HealthCheckManager.get_worker_count() == 1

    def test_clamps_negative_to_1(self):
        HealthCheckManager.set_worker_count(-5)
        assert HealthCheckManager.get_worker_count() == 1

    def test_clamps_to_maximum_16(self):
        HealthCheckManager.set_worker_count(100)
        assert HealthCheckManager.get_worker_count() == 16

    def test_set_exact_max(self):
        HealthCheckManager.set_worker_count(16)
        assert HealthCheckManager.get_worker_count() == 16

    def test_set_exact_min(self):
        HealthCheckManager.set_worker_count(1)
        assert HealthCheckManager.get_worker_count() == 1


# ------------------------------------------------------------------
# cancel_scan
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCancelScan:

    def test_cancel_when_not_scanning_returns_false(self):
        result = HealthCheckManager.cancel_scan()
        assert result is False

    def test_cancel_when_scanning_returns_true(self):
        with HealthCheckManager._lock:
            HealthCheckManager._scanning = True
        result = HealthCheckManager.cancel_scan()
        assert result is True
        assert HealthCheckManager._cancel_event.is_set()

    def test_cancel_sets_event(self):
        with HealthCheckManager._lock:
            HealthCheckManager._scanning = True
        HealthCheckManager.cancel_scan()
        assert HealthCheckManager._cancel_event.is_set()


# ------------------------------------------------------------------
# is_scanning / get_scan_progress
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestScanningState:

    def test_is_scanning_default_false(self):
        assert HealthCheckManager.is_scanning() is False

    def test_is_scanning_when_set(self):
        HealthCheckManager._scanning = True
        assert HealthCheckManager.is_scanning() is True

    def test_get_scan_progress_returns_copy(self):
        progress = HealthCheckManager.get_scan_progress()
        progress['total'] = 999
        # Original should be unchanged
        assert HealthCheckManager._scan_progress['total'] == 0

    def test_get_scan_progress_has_expected_keys(self):
        progress = HealthCheckManager.get_scan_progress()
        expected_keys = {'total', 'checked', 'library_id', 'worker_count',
                         'max_workers', 'workers', 'start_time',
                         'files_per_second', 'eta_seconds'}
        assert set(progress.keys()) == expected_keys


# ------------------------------------------------------------------
# _scan_worker
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestScanWorker:

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_scan_worker_processes_files(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        file_queue = queue.Queue()
        file_queue.put('/test/file1.mkv')
        file_queue.put('/test/file2.mkv')

        checked_files = []

        with patch.object(mgr, 'check_file', side_effect=lambda fp, **kw: checked_files.append(fp)):
            HealthCheckManager._scan_progress['start_time'] = time.time()
            HealthCheckManager._scan_progress['total'] = 2
            mgr._scan_worker(0, file_queue, library_id=1, mode='quick')

        assert len(checked_files) == 2
        assert '/test/file1.mkv' in checked_files
        assert '/test/file2.mkv' in checked_files

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_scan_worker_respects_cancel_event(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        file_queue = queue.Queue()
        for i in range(100):
            file_queue.put(f'/test/file{i}.mkv')

        HealthCheckManager._cancel_event.set()

        with patch.object(mgr, 'check_file') as mock_check:
            mgr._scan_worker(0, file_queue, library_id=1, mode='quick')
            # Should not process any files since cancel is set
            assert mock_check.call_count == 0

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_scan_worker_handles_check_file_exception(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        file_queue = queue.Queue()
        file_queue.put('/test/error_file.mkv')
        file_queue.put('/test/good_file.mkv')

        call_count = [0]

        def side_effect(fp, **kw):
            call_count[0] += 1
            if 'error_file' in fp:
                raise Exception("Check failed")

        with patch.object(mgr, 'check_file', side_effect=side_effect):
            HealthCheckManager._scan_progress['start_time'] = time.time()
            HealthCheckManager._scan_progress['total'] = 2
            mgr._scan_worker(0, file_queue, library_id=1, mode='quick')

        # Both files should have been attempted
        assert call_count[0] == 2

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_scan_worker_updates_progress(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        file_queue = queue.Queue()
        file_queue.put('/test/file1.mkv')

        HealthCheckManager._scan_progress['start_time'] = time.time() - 1
        HealthCheckManager._scan_progress['total'] = 1

        with patch.object(mgr, 'check_file'):
            mgr._scan_worker(0, file_queue, library_id=1, mode='quick')

        assert HealthCheckManager._scan_progress['checked'] == 1
        assert HealthCheckManager._scan_progress['files_per_second'] > 0

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_scan_worker_registers_and_clears_worker_status(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        file_queue = queue.Queue()
        # Empty queue so worker exits immediately after registration

        HealthCheckManager._scan_progress['start_time'] = time.time()
        HealthCheckManager._scan_progress['total'] = 0

        mgr._scan_worker(5, file_queue, library_id=1, mode='quick')

        # Worker should have set its final status to idle
        assert HealthCheckManager._scan_progress['workers'][5]['status'] == 'idle'


# ------------------------------------------------------------------
# _run_library_scan edge cases
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestRunLibraryScan:

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_run_library_scan_library_not_found(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        with patch('compresso.libs.healthcheck.HealthCheckManager._scanning', True):
            with patch('compresso.libs.unmodels.Libraries') as mock_lib:
                mock_lib.get_by_id.side_effect = Exception("Not found")
                mgr._run_library_scan(999, 'quick')

        # Should have set _scanning to False in finally block
        assert HealthCheckManager._scanning is False

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_run_library_scan_empty_library(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        mock_library = MagicMock()
        mock_library.path = '/empty/library'

        with patch('compresso.libs.unmodels.Libraries') as mock_lib_cls:
            mock_lib_cls.get_by_id.return_value = mock_library
            with patch('os.walk', return_value=[]):
                HealthCheckManager._scanning = True
                mgr._run_library_scan(1, 'quick')

        assert HealthCheckManager._scanning is False
        progress = HealthCheckManager.get_scan_progress()
        assert progress['total'] == 0

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_run_library_scan_filters_media_extensions(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        mock_library = MagicMock()
        mock_library.path = '/media/library'

        walk_result = [
            ('/media/library', [], ['video.mkv', 'audio.mp3', 'movie.mp4', 'readme.txt', 'clip.avi']),
        ]

        checked_files = []

        with patch('compresso.libs.unmodels.Libraries') as mock_lib_cls:
            mock_lib_cls.get_by_id.return_value = mock_library
            with patch('os.walk', return_value=walk_result):
                with patch.object(mgr, 'check_file', side_effect=lambda fp, **kw: checked_files.append(fp)):
                    HealthCheckManager._scanning = True
                    mgr._run_library_scan(1, 'quick')

        # Should only include .mkv, .mp4, .avi (not .mp3, .txt)
        assert len(checked_files) == 3
        extensions = {os.path.splitext(f)[1] for f in checked_files}
        assert '.txt' not in extensions
        assert '.mp3' not in extensions

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_schedule_library_scan_returns_false_when_already_scanning(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()
        with HealthCheckManager._lock:
            HealthCheckManager._scanning = True
        result = mgr.schedule_library_scan(1, mode='quick')
        assert result is False

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_schedule_library_scan_returns_true_when_not_scanning(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        with patch.object(mgr, '_run_library_scan'):
            result = mgr.schedule_library_scan(1, mode='quick')
            assert result is True
            assert HealthCheckManager._scanning is True

        # Clean up
        HealthCheckManager._scanning = False

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_run_library_scan_clears_file_locks_on_completion(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()

        # Pre-populate file locks
        with HealthCheckManager._file_locks_lock:
            HealthCheckManager._file_locks['/test/old.mkv'] = threading.Lock()

        mock_library = MagicMock()
        mock_library.path = '/empty'

        with patch('compresso.libs.unmodels.Libraries') as mock_lib_cls:
            mock_lib_cls.get_by_id.return_value = mock_library
            with patch('os.walk', return_value=[]):
                HealthCheckManager._scanning = True
                mgr._run_library_scan(1, 'quick')

        with HealthCheckManager._file_locks_lock:
            assert len(HealthCheckManager._file_locks) == 0


# ------------------------------------------------------------------
# _get_file_lock
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetFileLock:

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_returns_lock_for_path(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()
        lock = mgr._get_file_lock('/test/file.mkv')
        assert isinstance(lock, type(threading.Lock()))

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_returns_same_lock_for_same_path(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()
        lock1 = mgr._get_file_lock('/test/same.mkv')
        lock2 = mgr._get_file_lock('/test/same.mkv')
        assert lock1 is lock2

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_returns_different_locks_for_different_paths(self, mock_get_logger):
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()
        lock1 = mgr._get_file_lock('/test/file1.mkv')
        lock2 = mgr._get_file_lock('/test/file2.mkv')
        assert lock1 is not lock2

    @patch('compresso.libs.logs.CompressoLogging.get_logger')
    def test_file_lock_cleaned_up_after_check_file(self, mock_get_logger):
        """Verify that per-file locks are removed after check_file completes to prevent memory leaks."""
        mock_get_logger.return_value = MagicMock()
        mgr = HealthCheckManager()
        filepath = '/test/cleanup_test.mkv'

        with patch.object(mgr, 'quick_check', return_value=(True, '')), \
             patch('compresso.libs.healthcheck.HealthStatus') as MockHS:
            mock_health = MagicMock()
            MockHS.get_or_create.return_value = (mock_health, True)
            mgr.check_file(filepath, library_id=1, mode='quick')

        # Lock should have been cleaned up
        assert filepath not in HealthCheckManager._file_locks
