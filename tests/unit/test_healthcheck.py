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
import time

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
    def test_10_or_fewer_error_lines_still_healthy(self, mock_exists, mock_run):
        """10 or fewer error lines with returncode 0 → still healthy."""
        error_lines = '\n'.join(['warning {}'.format(i) for i in range(5)])
        mock_run.return_value = MagicMock(returncode=0, stderr=error_lines)
        mgr = self._make_manager()
        ok, err = mgr.thorough_check('/test/file.mkv')
        assert ok is True
        assert err == ''

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
        time.sleep(0.5)

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def setup_method(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.delete().execute()
        time.sleep(0.1)

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    def _seed_row(self, abspath, library_id=1):
        """Pre-seed a HealthStatus row so check_file's get_or_create finds it."""
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.create(abspath=abspath, library_id=library_id, status='unchecked')
        time.sleep(0.1)

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
        time.sleep(0.1)

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
        time.sleep(0.1)

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
        time.sleep(0.1)
        mgr.check_file('/test/update.mkv', library_id=1, mode='quick')
        time.sleep(0.1)
        count = HealthStatus.select().where(HealthStatus.abspath == '/test/update.mkv').count()
        assert count == 1

    @patch.object(
        __import__('unmanic.libs.healthcheck', fromlist=['HealthCheckManager']).HealthCheckManager,
        'quick_check', return_value=(False, 'error')
    )
    def test_repeated_failures_increment_error_count(self, mock_quick):
        self._seed_row('/test/errors.mkv')
        mgr = self._make_manager()
        result1 = mgr.check_file('/test/errors.mkv', library_id=1, mode='quick')
        time.sleep(0.1)
        result2 = mgr.check_file('/test/errors.mkv', library_id=1, mode='quick')
        assert result2['error_count'] == 2


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
        time.sleep(0.5)

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def setup_method(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.delete().execute()
        time.sleep(0.1)

    def _make_manager(self):
        from unmanic.libs.healthcheck import HealthCheckManager
        return HealthCheckManager()

    def test_empty_db_returns_all_zeros(self):
        mgr = self._make_manager()
        summary = mgr.get_health_summary()
        assert summary['healthy'] == 0
        assert summary['corrupted'] == 0
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
        assert summary['unchecked'] == 1
        assert summary['total'] == 4

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
        time.sleep(0.5)

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def setup_method(self):
        from unmanic.libs.unmodels import HealthStatus
        HealthStatus.delete().execute()
        time.sleep(0.1)

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


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
