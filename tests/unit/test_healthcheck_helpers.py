#!/usr/bin/env python3

"""
tests.unit.test_healthcheck_helpers.py

Unit tests for compresso.webserver.helpers.healthcheck helper functions.
"""

from unittest.mock import MagicMock, patch

import pytest

# ------------------------------------------------------------------
# TestValidateLibraryExists
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestValidateLibraryExists:
    def test_none_library_id_returns_true(self):
        from compresso.webserver.helpers.healthcheck import validate_library_exists

        assert validate_library_exists(None) is True

    @patch("compresso.libs.unmodels.Libraries")
    def test_valid_library_returns_true(self, mock_libraries):
        mock_libraries.get_by_id.return_value = MagicMock()
        from compresso.webserver.helpers.healthcheck import validate_library_exists

        assert validate_library_exists(1) is True

    @patch("compresso.libs.unmodels.Libraries")
    def test_invalid_library_raises_value_error(self, mock_libraries):
        mock_libraries.get_by_id.side_effect = Exception("not found")
        from compresso.webserver.helpers.healthcheck import validate_library_exists

        with pytest.raises(ValueError, match="does not exist"):
            validate_library_exists(999)


# ------------------------------------------------------------------
# TestCheckSingleFile
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestCheckSingleFile:
    @patch("compresso.webserver.helpers.healthcheck.HealthCheckManager")
    def test_delegates_to_manager(self, mock_mgr_cls):
        mock_mgr = mock_mgr_cls.return_value
        mock_mgr.check_file.return_value = {"status": "healthy"}

        from compresso.webserver.helpers.healthcheck import check_single_file

        result = check_single_file("/test/file.mkv", library_id=2, mode="thorough")

        mock_mgr.check_file.assert_called_once_with("/test/file.mkv", library_id=2, mode="thorough")
        assert result == {"status": "healthy"}


# ------------------------------------------------------------------
# TestScanLibrary
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestScanLibrary:
    @patch("compresso.webserver.helpers.healthcheck.HealthCheckManager")
    def test_delegates_to_manager(self, mock_mgr_cls):
        mock_mgr = mock_mgr_cls.return_value
        mock_mgr.schedule_library_scan.return_value = True

        from compresso.webserver.helpers.healthcheck import scan_library

        result = scan_library(1, mode="thorough")

        mock_mgr.schedule_library_scan.assert_called_once_with(1, mode="thorough")
        assert result is True


# ------------------------------------------------------------------
# TestGetHealthSummary
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetHealthSummary:
    @patch("compresso.webserver.helpers.healthcheck.HealthCheckManager")
    def test_returns_summary(self, mock_mgr_cls):
        expected = {"healthy": 10, "unhealthy": 2}
        mock_mgr_cls.return_value.get_health_summary.return_value = expected

        from compresso.webserver.helpers.healthcheck import get_health_summary

        result = get_health_summary(library_id=1)
        assert result == expected


# ------------------------------------------------------------------
# TestGetScanProgress
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetScanProgress:
    @patch("compresso.webserver.helpers.healthcheck.HealthCheckManager")
    def test_returns_scanning_and_progress(self, mock_mgr_cls):
        mock_mgr_cls.is_scanning.return_value = True
        mock_mgr_cls.get_scan_progress.return_value = 0.5

        from compresso.webserver.helpers.healthcheck import get_scan_progress

        result = get_scan_progress()
        assert result == {"scanning": True, "progress": 0.5}


# ------------------------------------------------------------------
# TestCancelScan
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestCancelScan:
    @patch("compresso.webserver.helpers.healthcheck.HealthCheckManager")
    def test_delegates_cancel(self, mock_mgr_cls):
        mock_mgr_cls.cancel_scan.return_value = True

        from compresso.webserver.helpers.healthcheck import cancel_scan

        result = cancel_scan()
        assert result is True


# ------------------------------------------------------------------
# TestSetScanWorkers
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestSetScanWorkers:
    @patch("compresso.webserver.helpers.healthcheck.HealthCheckManager")
    def test_sets_and_returns_count(self, mock_mgr_cls):
        mock_mgr_cls.get_worker_count.return_value = 4

        from compresso.webserver.helpers.healthcheck import set_scan_workers

        result = set_scan_workers(4)

        mock_mgr_cls.set_worker_count.assert_called_once_with(4)
        assert result == 4


# ------------------------------------------------------------------
# TestGetScanWorkers
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetScanWorkers:
    @patch("compresso.webserver.helpers.healthcheck.HealthCheckManager")
    def test_returns_worker_info(self, mock_mgr_cls):
        mock_mgr_cls.get_worker_count.return_value = 2
        mock_mgr_cls.is_scanning.return_value = False
        mock_mgr_cls.get_scan_progress.return_value = 0.0

        from compresso.webserver.helpers.healthcheck import get_scan_workers

        result = get_scan_workers()
        assert result == {"worker_count": 2, "scanning": False, "progress": 0.0}


# ------------------------------------------------------------------
# TestGetStartupReadiness
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetStartupReadiness:
    @patch("compresso.webserver.helpers.healthcheck.StartupState")
    def test_returns_snapshot(self, mock_startup_cls):
        expected = {"ready": True, "services": {}}
        mock_startup_cls.return_value.snapshot.return_value = expected

        from compresso.webserver.helpers.healthcheck import get_startup_readiness

        result = get_startup_readiness()
        assert result == expected
