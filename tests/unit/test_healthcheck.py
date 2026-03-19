#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_healthcheck.py

    Unit tests for unmanic.libs.healthcheck.HealthCheckManager.
    Tests quick_check, thorough_check, check_file, health_summary,
    paginated health statuses, and schedule_library_scan.

"""

import datetime
import os
import subprocess
import tempfile
import pytest
from unittest.mock import patch, MagicMock

from unmanic.libs.unmodels.lib import Database


# ------------------------------------------------------------------
# TestHealthCheckQuickCheck — no DB needed
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHealthCheckQuickCheck(object):
    """Tests for HealthCheckManager.quick_check()."""

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    @patch('unmanic.libs.healthcheck.probe_file')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=False)
    def test_file_not_found(self, mock_exists, mock_probe):
        mgr = self._make_manager()
        ok, err = mgr.quick_check('/nonexistent/file.mkv')
        assert ok is False
        assert 'File not found' in err

    @patch('unmanic.libs.healthcheck.probe_file', return_value=None)
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_probe_returns_none(self, mock_exists, mock_probe):
        mgr = self._make_manager()
        ok, err = mgr.quick_check('/test/file.mkv')
        assert ok is False
        assert 'ffprobe failed' in err

    @patch('unmanic.libs.healthcheck.probe_file')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_empty_streams(self, mock_exists, mock_probe):
        mock_probe.return_value = {'streams': [], 'format': {}}
        mgr = self._make_manager()
        ok, err = mgr.quick_check('/test/file.mkv')
        assert ok is False
        assert 'No streams' in err

    @patch('unmanic.libs.healthcheck.probe_file')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_zero_duration(self, mock_exists, mock_probe):
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video'}],
            'format': {'duration': '0'},
        }
        mgr = self._make_manager()
        ok, err = mgr.quick_check('/test/file.mkv')
        assert ok is False
        assert 'zero or negative' in err

    @patch('unmanic.libs.healthcheck.probe_file')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_valid_probe_data(self, mock_exists, mock_probe):
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video'}],
            'format': {'duration': '120.5'},
        }
        mgr = self._make_manager()
        ok, err = mgr.quick_check('/test/file.mkv')
        assert ok is True
        assert err == ''

    @patch('unmanic.libs.healthcheck.probe_file')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_missing_duration_still_healthy(self, mock_exists, mock_probe):
        """Missing duration field should still pass (duration check is optional)."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video'}],
            'format': {},
        }
        mgr = self._make_manager()
        ok, err = mgr.quick_check('/test/file.mkv')
        assert ok is True
        assert err == ''


# ------------------------------------------------------------------
# TestHealthCheckThoroughCheck — no DB needed
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHealthCheckThoroughCheck(object):
    """Tests for HealthCheckManager.thorough_check()."""

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=False)
    def test_file_not_found(self, mock_exists):
        mgr = self._make_manager()
        ok, err = mgr.thorough_check('/nonexistent/file.mkv')
        assert ok is False
        assert 'File not found' in err

    @patch('unmanic.libs.healthcheck.subprocess.run')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_ffmpeg_success_no_stderr(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr='')
        mgr = self._make_manager()
        ok, err = mgr.thorough_check('/test/file.mkv')
        assert ok is True
        assert err == ''

    @patch('unmanic.libs.healthcheck.subprocess.run')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_nonzero_returncode(self, mock_exists, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr='Error decoding frame')
        mgr = self._make_manager()
        ok, err = mgr.thorough_check('/test/file.mkv')
        assert ok is False
        assert 'Error decoding frame' in err

    @patch('unmanic.libs.healthcheck.subprocess.run')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_more_than_10_error_lines(self, mock_exists, mock_run):
        """More than 10 error lines in stderr with returncode 0 → corrupted."""
        error_lines = '\n'.join(['error line {}'.format(i) for i in range(15)])
        mock_run.return_value = MagicMock(returncode=0, stderr=error_lines)
        mgr = self._make_manager()
        ok, err = mgr.thorough_check('/test/file.mkv')
        assert ok is False
        assert '15 errors' in err

    @patch('unmanic.libs.healthcheck.subprocess.run')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_10_or_fewer_error_lines_returns_warning(self, mock_exists, mock_run):
        """1-10 error lines with returncode 0 → warning status."""
        error_lines = '\n'.join(['warning {}'.format(i) for i in range(5)])
        mock_run.return_value = MagicMock(returncode=0, stderr=error_lines)
        mgr = self._make_manager()
        status, err = mgr.thorough_check('/test/file.mkv')
        assert status == 'warning'
        assert '5 warning(s)' in err

    @patch('unmanic.libs.healthcheck.subprocess.run')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_timeout_expired(self, mock_exists, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='ffmpeg', timeout=600)
        mgr = self._make_manager()
        ok, err = mgr.thorough_check('/test/file.mkv')
        assert ok is False
        assert 'timed out' in err

    @patch('unmanic.libs.healthcheck.subprocess.run')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_generic_exception(self, mock_exists, mock_run):
        mock_run.side_effect = OSError("ffmpeg not found")
        mgr = self._make_manager()
        ok, err = mgr.thorough_check('/test/file.mkv')
        assert ok is False
        assert 'failed' in err.lower()


# ------------------------------------------------------------------
# DB-backed tests — check_file, health_summary, paginated, schedule_scan
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHealthCheckCheckFile(object):
    """Tests for check_file() — requires DB.

    Uses pre-seeded HealthStatus rows and mocks quick_check/thorough_check
    to avoid sqliteq race conditions with get_or_create.
    """

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='unmanic_tests_healthcheck_')
        self.db_file = os.path.join(self.config_path, 'test_healthcheck.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import HealthStatus
        self.db_connection.create_tables([HealthStatus])
        self.db_connection.execute_sql('SELECT 1')

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def setup_method(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.delete().execute()
        self.db_connection.execute_sql('SELECT 1')

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    def _seed_row(self, abspath, library_id=1):
        """Pre-seed a HealthStatus row so check_file's get_or_create finds it."""
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath=abspath, library_id=library_id, status='unchecked')

    @patch.object(
        __import__('unmanic.libs.healthcheck', fromlist=['HealthCheckManager']).HealthCheckManager,
        'quick_check', return_value=(True, '')
    )
    def test_healthy_result_creates_healthy_row(self, mock_quick):
        from unmanic.libs.unmodels import HealthStatus
        self._seed_row('/test/healthy.mkv')
        mgr = self._make_manager()
        result = mgr.check_file('/test/healthy.mkv', library_id=1, mode='quick')
        assert result['status'] == 'healthy'
        assert result['error_detail'] == ''
        self.db_connection.execute_sql('SELECT 1')

        row = HealthStatus.get(HealthStatus.abspath == '/test/healthy.mkv')
        assert row.status == 'healthy'

    @patch.object(
        __import__('unmanic.libs.healthcheck', fromlist=['HealthCheckManager']).HealthCheckManager,
        'quick_check', return_value=(False, 'No streams found in file')
    )
    def test_corrupted_result_creates_corrupted_row(self, mock_quick):
        from unmanic.libs.unmodels import HealthStatus
        self._seed_row('/test/bad.mkv')
        mgr = self._make_manager()
        result = mgr.check_file('/test/bad.mkv', library_id=1, mode='quick')
        assert result['status'] == 'corrupted'
        assert 'No streams' in result['error_detail']
        self.db_connection.execute_sql('SELECT 1')

        row = HealthStatus.get(HealthStatus.abspath == '/test/bad.mkv')
        assert row.status == 'corrupted'
        assert row.error_detail == 'No streams found in file'

    @patch.object(
        __import__('unmanic.libs.healthcheck', fromlist=['HealthCheckManager']).HealthCheckManager,
        'thorough_check', return_value=(True, '')
    )
    def test_thorough_mode_calls_thorough_check(self, mock_thorough):
        self._seed_row('/test/thorough.mkv')
        mgr = self._make_manager()
        result = mgr.check_file('/test/thorough.mkv', library_id=1, mode='thorough')
        assert result['status'] == 'healthy'
        mock_thorough.assert_called_once_with('/test/thorough.mkv')

    @patch.object(
        __import__('unmanic.libs.healthcheck', fromlist=['HealthCheckManager']).HealthCheckManager,
        'quick_check', return_value=(True, '')
    )
    def test_second_check_updates_not_duplicates(self, mock_quick):
        from unmanic.libs.unmodels import HealthStatus
        self._seed_row('/test/update.mkv')
        mgr = self._make_manager()
        mgr.check_file('/test/update.mkv', library_id=1, mode='quick')
        self.db_connection.execute_sql('SELECT 1')
        mgr.check_file('/test/update.mkv', library_id=1, mode='quick')
        self.db_connection.execute_sql('SELECT 1')
        count = HealthStatus.select().where(HealthStatus.abspath == '/test/update.mkv').count()
        assert count == 1

    @patch.object(
        __import__('unmanic.libs.healthcheck', fromlist=['HealthCheckManager']).HealthCheckManager,
        'quick_check', return_value=(False, 'error')
    )
    def test_repeated_failures_increment_error_count(self, mock_quick):
        self._seed_row('/test/errors.mkv')
        mgr = self._make_manager()
        mgr.check_file('/test/errors.mkv', library_id=1, mode='quick')
        self.db_connection.execute_sql('SELECT 1')
        result2 = mgr.check_file('/test/errors.mkv', library_id=1, mode='quick')
        assert result2['error_count'] == 2

    @patch.object(
        __import__('unmanic.libs.healthcheck', fromlist=['HealthCheckManager']).HealthCheckManager,
        'thorough_check', return_value=('warning', '5 warning(s): line1')
    )
    def test_warning_result_creates_warning_row(self, mock_thorough):
        from unmanic.libs.unmodels import HealthStatus
        self._seed_row('/test/warn.mkv')
        mgr = self._make_manager()
        result = mgr.check_file('/test/warn.mkv', library_id=1, mode='thorough')
        assert result['status'] == 'warning'
        self.db_connection.execute_sql('SELECT 1')

        row = HealthStatus.get(HealthStatus.abspath == '/test/warn.mkv')
        assert row.status == 'warning'
        assert row.error_count >= 1


# ------------------------------------------------------------------
# TestHealthSummary
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHealthSummary(object):
    """Tests for get_health_summary() — requires DB."""

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='unmanic_tests_health_summary_')
        self.db_file = os.path.join(self.config_path, 'test_health_summary.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import HealthStatus
        self.db_connection.create_tables([HealthStatus])
        self.db_connection.execute_sql('SELECT 1')

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def setup_method(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.delete().execute()
        self.db_connection.execute_sql('SELECT 1')

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    def test_empty_db_returns_all_zeros(self):
        mgr = self._make_manager()
        summary = mgr.get_health_summary()
        assert summary['healthy'] == 0
        assert summary['corrupted'] == 0
        assert summary['warning'] == 0
        assert summary['unchecked'] == 0
        assert summary['checking'] == 0
        assert summary['total'] == 0

    def test_mixed_statuses_correct_counts(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/a.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/b.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/c.mkv', status='corrupted', library_id=1)
        HealthStatus.create(abspath='/d.mkv', status='unchecked', library_id=1)

        mgr = self._make_manager()
        summary = mgr.get_health_summary()
        assert summary['healthy'] == 2
        assert summary['corrupted'] == 1
        assert summary['warning'] == 0
        assert summary['unchecked'] == 1
        assert summary['total'] == 4

    def test_warning_status_counted(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/w1.mkv', status='warning', library_id=1)
        HealthStatus.create(abspath='/w2.mkv', status='warning', library_id=1)
        HealthStatus.create(abspath='/h1.mkv', status='healthy', library_id=1)

        mgr = self._make_manager()
        summary = mgr.get_health_summary()
        assert summary['warning'] == 2
        assert summary['healthy'] == 1
        assert summary['total'] == 3

    def test_library_id_filter(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/lib1.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/lib2.mkv', status='corrupted', library_id=2)
        HealthStatus.create(abspath='/lib2b.mkv', status='healthy', library_id=2)

        mgr = self._make_manager()
        summary = mgr.get_health_summary(library_id=2)
        assert summary['corrupted'] == 1
        assert summary['healthy'] == 1
        assert summary['total'] == 2


# ------------------------------------------------------------------
# TestHealthStatusesPaginated
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHealthStatusesPaginated(object):
    """Tests for get_health_statuses_paginated() — requires DB."""

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='unmanic_tests_health_pag_')
        self.db_file = os.path.join(self.config_path, 'test_health_paginated.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import HealthStatus
        self.db_connection.create_tables([HealthStatus])
        self.db_connection.execute_sql('SELECT 1')

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def setup_method(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.delete().execute()
        self.db_connection.execute_sql('SELECT 1')

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    def test_basic_pagination_structure(self):
        from unmanic.libs.unmodels import HealthStatus
        for i in range(5):
            HealthStatus.create(abspath='/file{}.mkv'.format(i), status='healthy', library_id=1)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated(start=0, length=10)
        assert 'recordsTotal' in result
        assert 'recordsFiltered' in result
        assert 'results' in result
        assert result['recordsTotal'] == 5
        assert len(result['results']) == 5

    def test_offset_works(self):
        from unmanic.libs.unmodels import HealthStatus
        for i in range(5):
            HealthStatus.create(abspath='/offset{}.mkv'.format(i), status='healthy', library_id=1)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated(start=3, length=10)
        assert len(result['results']) == 2

    def test_status_filter(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/h.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/c.mkv', status='corrupted', library_id=1)
        HealthStatus.create(abspath='/u.mkv', status='unchecked', library_id=1)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated(status_filter='corrupted')
        assert result['recordsFiltered'] == 1
        assert result['results'][0]['status'] == 'corrupted'

    def test_search_value_filters_by_abspath(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/media/movies/test.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/media/tv/show.mkv', status='healthy', library_id=1)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated(search_value='movies')
        assert result['recordsFiltered'] == 1
        assert 'movies' in result['results'][0]['abspath']

    def test_library_id_filter(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/lib1.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/lib2.mkv', status='healthy', library_id=2)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated(library_id=2)
        assert result['recordsFiltered'] == 1
        assert result['results'][0]['library_id'] == 2

    def test_invalid_order_column_falls_back_to_last_checked(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/ord1.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/ord2.mkv', status='healthy', library_id=1)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated(
            order={'column': 'DROP TABLE', 'dir': 'desc'}
        )
        assert result['recordsTotal'] == 2
        assert len(result['results']) == 2

    def test_valid_order_column_works(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/z_last.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/a_first.mkv', status='healthy', library_id=1)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated(
            order={'column': 'abspath', 'dir': 'asc'}
        )
        assert result['results'][0]['abspath'] == '/a_first.mkv'
        assert result['results'][1]['abspath'] == '/z_last.mkv'

    def test_result_rows_have_expected_keys(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(
            abspath='/keys_test.mkv', status='healthy', library_id=1,
            check_mode='quick', error_detail='', error_count=0,
            last_checked=datetime.datetime.now(),
        )

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated()
        row = result['results'][0]
        expected_keys = ['id', 'abspath', 'library_id', 'status',
                         'check_mode', 'error_detail', 'last_checked', 'error_count']
        for key in expected_keys:
            assert key in row, "Missing key: {}".format(key)


# ------------------------------------------------------------------
# TestScheduleLibraryScan
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestScheduleLibraryScan(object):
    """Tests for schedule_library_scan()."""

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    def teardown_method(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        HealthCheckManager._scanning = False
        HealthCheckManager._worker_count_requested = 1

    @patch('unmanic.libs.healthcheck.threading.Thread')
    def test_first_call_returns_true(self, mock_thread):
        mock_thread.return_value = MagicMock()
        mgr = self._make_manager()
        result = mgr.schedule_library_scan(library_id=1, mode='quick')
        assert result is True
        mock_thread.return_value.start.assert_called_once()

    @patch('unmanic.libs.healthcheck.threading.Thread')
    def test_second_call_while_scanning_returns_false(self, mock_thread):
        mock_thread.return_value = MagicMock()
        mgr = self._make_manager()
        mgr.schedule_library_scan(library_id=1, mode='quick')
        result = mgr.schedule_library_scan(library_id=1, mode='quick')
        assert result is False


    # ------------------------------------------------------------------
    # is_scanning / get_scan_progress (B6)
    # ------------------------------------------------------------------

    @patch('unmanic.libs.healthcheck.threading.Thread')
    def test_is_scanning_reflects_scan_state(self, mock_thread):
        """is_scanning should be True while scanning and False after reset."""
        from unmanic.libs.healthcheck import HealthCheckManager
        mock_thread.return_value = MagicMock()
        mgr = self._make_manager()

        assert HealthCheckManager.is_scanning() is False
        mgr.schedule_library_scan(library_id=1, mode='quick')
        assert HealthCheckManager.is_scanning() is True

        # Reset
        HealthCheckManager._scanning = False
        assert HealthCheckManager.is_scanning() is False

    def test_get_scan_progress_returns_dict(self):
        """get_scan_progress should return a dict with expected keys."""
        from unmanic.libs.healthcheck import HealthCheckManager
        progress = HealthCheckManager.get_scan_progress()
        assert isinstance(progress, dict)


# ------------------------------------------------------------------
# TestHealthCheckWorkers
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHealthCheckWorkers(object):
    """Tests for worker count management and enriched scan progress."""

    def teardown_method(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        HealthCheckManager._worker_count_requested = 1

    def test_set_worker_count_clamps_range(self):
        """set 0 -> get 1, set 100 -> get 16."""
        from unmanic.libs.healthcheck import HealthCheckManager
        HealthCheckManager.set_worker_count(0)
        assert HealthCheckManager.get_worker_count() == 1
        HealthCheckManager.set_worker_count(100)
        assert HealthCheckManager.get_worker_count() == 16
        HealthCheckManager.set_worker_count(4)
        assert HealthCheckManager.get_worker_count() == 4
        # Reset
        HealthCheckManager.set_worker_count(1)

    def test_scan_progress_includes_worker_info(self):
        """Scan progress should include worker-related fields."""
        from unmanic.libs.healthcheck import HealthCheckManager
        progress = HealthCheckManager.get_scan_progress()
        assert 'workers' in progress
        assert 'max_workers' in progress
        assert 'files_per_second' in progress
        assert 'eta_seconds' in progress


# ------------------------------------------------------------------
# TestCancelScan
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCancelScan(object):
    """Tests for cancel_scan()."""

    def teardown_method(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        HealthCheckManager._scanning = False
        HealthCheckManager._cancel_event.clear()
        HealthCheckManager._worker_count_requested = 1

    def test_cancel_when_not_scanning_returns_false(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        result = HealthCheckManager.cancel_scan()
        assert result is False

    @patch('unmanic.libs.healthcheck.threading.Thread')
    def test_cancel_when_scanning_returns_true(self, mock_thread):
        from unmanic.libs.healthcheck import HealthCheckManager
        mock_thread.return_value = MagicMock()
        mgr = HealthCheckManager()
        mgr.schedule_library_scan(library_id=1, mode='quick')
        result = HealthCheckManager.cancel_scan()
        assert result is True
        assert HealthCheckManager._cancel_event.is_set() is True


# ------------------------------------------------------------------
# TestCheckFileEdgeCases
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCheckFileEdgeCases(object):
    """Edge case tests for check_file (Issue #29)."""

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    @patch('unmanic.libs.healthcheck.probe_file')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_zero_byte_file_detected(self, mock_exists, mock_probe):
        """A zero-byte file should return no streams."""
        mock_probe.return_value = {'streams': [], 'format': {'size': '0'}}
        mgr = self._make_manager()
        ok, err = mgr.quick_check('/test/empty.mkv')
        assert ok is False
        assert 'No streams' in err

    @patch('unmanic.libs.healthcheck.probe_file')
    @patch('unmanic.libs.healthcheck.os.path.exists', return_value=True)
    def test_negative_duration_detected(self, mock_exists, mock_probe):
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video'}],
            'format': {'duration': '-1.0'},
        }
        mgr = self._make_manager()
        ok, err = mgr.quick_check('/test/negative_dur.mkv')
        assert ok is False
        assert 'zero or negative' in err


# ------------------------------------------------------------------
# TestHistoryOrderWhitelist
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHistoryOrderWhitelist(object):
    """Tests for get_historic_task_list_filtered_and_sorted column whitelist (Issue #3)."""

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='unmanic_tests_history_order_')
        self.db_file = os.path.join(self.config_path, 'test_history_order.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import CompletedTasks, CompletedTasksCommandLogs
        self.db_connection.create_tables([CompletedTasks, CompletedTasksCommandLogs])
        self.db_connection.execute_sql('SELECT 1')

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def test_invalid_column_does_not_crash(self):
        """Passing __class__ or other invalid column should not crash."""
        from unmanic.libs.history import History
        history = History()
        result = history.get_historic_task_list_filtered_and_sorted(
            order={'column': '__class__', 'dir': 'asc'}
        )
        # Should return without error (empty or with results)
        assert result is not None


# ------------------------------------------------------------------
# TestRecordsTotalRespectsLibraryId (Phase 3B — verifying 2A fix)
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestRecordsTotalRespectsLibraryId(object):
    """Verify recordsTotal respects library_id filter after 2A fix."""

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='unmanic_tests_records_total_')
        self.db_file = os.path.join(self.config_path, 'test_records_total.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import HealthStatus
        self.db_connection.create_tables([HealthStatus])
        self.db_connection.execute_sql('SELECT 1')

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def setup_method(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.delete().execute()
        self.db_connection.execute_sql('SELECT 1')

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    def test_records_total_filtered_by_library_id(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/lib1a.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/lib1b.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/lib2a.mkv', status='healthy', library_id=2)
        HealthStatus.create(abspath='/lib2b.mkv', status='healthy', library_id=2)
        HealthStatus.create(abspath='/lib2c.mkv', status='healthy', library_id=2)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated(library_id=2)
        assert result['recordsTotal'] == 3
        assert result['recordsFiltered'] == 3

    def test_records_total_no_filter_counts_all(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath='/all1.mkv', status='healthy', library_id=1)
        HealthStatus.create(abspath='/all2.mkv', status='corrupted', library_id=2)

        mgr = self._make_manager()
        result = mgr.get_health_statuses_paginated()
        assert result['recordsTotal'] == 2


# ------------------------------------------------------------------
# TestCancelEventThreadSafe (Phase 3B — threading.Event)
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCancelEventThreadSafe(object):
    """Verify _cancel_event is a threading.Event and works correctly."""

    def teardown_method(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        HealthCheckManager._scanning = False
        HealthCheckManager._cancel_event.clear()

    def test_cancel_event_is_threading_event(self):
        import threading
        from unmanic.libs.healthcheck import HealthCheckManager
        assert isinstance(HealthCheckManager._cancel_event, threading.Event)

    def test_cancel_event_set_and_clear(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        assert not HealthCheckManager._cancel_event.is_set()
        HealthCheckManager._cancel_event.set()
        assert HealthCheckManager._cancel_event.is_set()
        HealthCheckManager._cancel_event.clear()
        assert not HealthCheckManager._cancel_event.is_set()


# ------------------------------------------------------------------
# TestGetScanProgressDeepCopy (Phase 3A — verifying Phase 2A fix)
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetScanProgressDeepCopy(object):
    """Verify get_scan_progress returns a deep copy (nested dicts independent)."""

    def teardown_method(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        HealthCheckManager._scan_progress['workers'] = {}

    def test_modifying_returned_workers_does_not_affect_original(self):
        from unmanic.libs.healthcheck import HealthCheckManager

        # Set up some worker data
        with HealthCheckManager._lock:
            HealthCheckManager._scan_progress['workers'] = {
                0: {'status': 'checking', 'current_file': '/test.mkv'}
            }

        progress = HealthCheckManager.get_scan_progress()
        # Mutate the returned dict
        progress['workers'][0]['status'] = 'MUTATED'
        progress['workers'][99] = {'status': 'injected'}

        # Original should be unchanged
        with HealthCheckManager._lock:
            original = HealthCheckManager._scan_progress['workers']
        assert original[0]['status'] == 'checking'
        assert 99 not in original


# ------------------------------------------------------------------
# TestFileLocksClearedAfterScan (Phase 3A — verifying Phase 2E fix)
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFileLocksClearedAfterScan(object):
    """Verify _file_locks is cleared after _run_library_scan completes."""

    def teardown_method(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        HealthCheckManager._scanning = False
        HealthCheckManager._file_locks.clear()

    @patch('unmanic.libs.healthcheck.HealthCheckManager.check_file')
    def test_file_locks_cleared_after_scan(self, mock_check):
        from unmanic.libs.healthcheck import HealthCheckManager

        # Simulate some accumulated file locks
        HealthCheckManager._file_locks = {
            '/old/file1.mkv': MagicMock(),
            '/old/file2.mkv': MagicMock(),
        }

        mgr = HealthCheckManager()

        # Mock the library lookup to return an empty directory
        with patch('unmanic.libs.healthcheck.os.walk', return_value=[]):
            mock_lib = MagicMock()
            mock_lib.path = '/empty/library'
            with patch('unmanic.libs.unmodels.Libraries') as mock_libs:
                mock_libs.get_by_id.return_value = mock_lib
                mgr._run_library_scan(library_id=1, mode='quick')

        # After scan, file locks should be cleared
        assert len(HealthCheckManager._file_locks) == 0


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
