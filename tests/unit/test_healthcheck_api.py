#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_healthcheck_api.py

    Tests for the healthcheck API handler endpoints.
    Mocks helper functions, not the handler itself.

"""

import pytest
from unittest.mock import patch

from tests.unit.api_test_base import ApiTestBase
from unmanic.webserver.api_v2.healthcheck_api import ApiHealthcheckHandler

VALIDATE_LIB = 'unmanic.webserver.helpers.healthcheck.validate_library_exists'


@pytest.mark.unittest
class TestHealthcheckApiScan(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch('unmanic.webserver.helpers.healthcheck.check_single_file')
    def test_scan_file_success(self, mock_check, _mock_validate):
        mock_check.return_value = {
            'abspath': '/test/file.mkv',
            'status': 'healthy',
            'check_mode': 'quick',
            'error_detail': '',
            'last_checked': '2024-01-01 00:00:00',
            'error_count': 0,
        }
        resp = self.post_json('/healthcheck/scan', {'file_path': '/test/file.mkv'})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['success'] is True
        assert data['status'] == 'healthy'

    def test_scan_file_invalid_json(self):
        resp = self.fetch(
            '/unmanic/api/v2/healthcheck/scan',
            method='POST',
            body='not json',
            headers={'Content-Type': 'application/json'},
        )
        assert resp.code == 400

    def test_scan_file_missing_required_field(self):
        resp = self.post_json('/healthcheck/scan', {'mode': 'quick'})
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch('unmanic.webserver.helpers.healthcheck.check_single_file')
    def test_scan_file_internal_error(self, mock_check, _mock_validate):
        mock_check.side_effect = Exception("Database error")
        resp = self.post_json('/healthcheck/scan', {'file_path': '/test/file.mkv'})
        assert resp.code == 500

    @patch(VALIDATE_LIB, side_effect=ValueError("Library with ID 999 does not exist"))
    def test_scan_file_invalid_library(self, _mock_validate):
        resp = self.post_json('/healthcheck/scan', {'file_path': '/test/file.mkv', 'library_id': 999})
        assert resp.code == 400


@pytest.mark.unittest
class TestHealthcheckApiScanLibrary(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch('unmanic.webserver.helpers.healthcheck.scan_library')
    def test_scan_library_started(self, mock_scan, _mock_validate):
        mock_scan.return_value = True
        resp = self.post_json('/healthcheck/scan-library', {'library_id': 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['started'] is True

    @patch(VALIDATE_LIB, return_value=True)
    @patch('unmanic.webserver.helpers.healthcheck.scan_library')
    def test_scan_library_already_running(self, mock_scan, _mock_validate):
        mock_scan.return_value = False
        resp = self.post_json('/healthcheck/scan-library', {'library_id': 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['started'] is False

    def test_scan_library_missing_library_id(self):
        resp = self.post_json('/healthcheck/scan-library', {})
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=ValueError("Library with ID 999 does not exist"))
    def test_scan_library_invalid_library(self, _mock_validate):
        resp = self.post_json('/healthcheck/scan-library', {'library_id': 999})
        assert resp.code == 400


@pytest.mark.unittest
class TestHealthcheckApiSummary(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch('unmanic.webserver.helpers.healthcheck.get_scan_progress')
    @patch('unmanic.webserver.helpers.healthcheck.get_health_summary')
    def test_get_summary_success(self, mock_summary, mock_progress):
        mock_summary.return_value = {
            'healthy': 10, 'corrupted': 2, 'warning': 1,
            'unchecked': 5, 'checking': 0, 'total': 18,
        }
        mock_progress.return_value = {'scanning': False, 'progress': {}}
        resp = self.get_json('/healthcheck/summary')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['total'] == 18

    @patch('unmanic.webserver.helpers.healthcheck.get_scan_progress')
    @patch('unmanic.webserver.helpers.healthcheck.get_health_summary')
    def test_get_summary_with_library_filter(self, mock_summary, mock_progress):
        mock_summary.return_value = {
            'healthy': 5, 'corrupted': 0, 'warning': 0,
            'unchecked': 0, 'checking': 0, 'total': 5,
        }
        mock_progress.return_value = {'scanning': False, 'progress': {}}
        resp = self.get_json('/healthcheck/summary?library_id=2')
        assert resp.code == 200
        mock_summary.assert_called_with(library_id=2)


@pytest.mark.unittest
class TestHealthcheckApiStatus(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch('unmanic.webserver.helpers.healthcheck.get_health_statuses_paginated')
    def test_get_status_list_success(self, mock_paginated):
        mock_paginated.return_value = {
            'recordsTotal': 5,
            'recordsFiltered': 3,
            'results': [{'id': 1, 'abspath': '/a.mkv', 'status': 'healthy',
                         'library_id': 1, 'check_mode': 'quick',
                         'error_detail': '', 'last_checked': '', 'error_count': 0}],
        }
        resp = self.post_json('/healthcheck/status', {'start': 0, 'length': 10})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['recordsTotal'] == 5

    def test_get_status_list_invalid_json(self):
        resp = self.fetch(
            '/unmanic/api/v2/healthcheck/status',
            method='POST',
            body='{{bad',
            headers={'Content-Type': 'application/json'},
        )
        assert resp.code == 400


@pytest.mark.unittest
class TestHealthcheckApiCancelScan(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch('unmanic.webserver.helpers.healthcheck.cancel_scan')
    def test_cancel_scan_success(self, mock_cancel):
        mock_cancel.return_value = True
        resp = self.post_json('/healthcheck/cancel-scan', {})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'cancellation requested' in data['message']

    @patch('unmanic.webserver.helpers.healthcheck.cancel_scan')
    def test_cancel_scan_not_running(self, mock_cancel):
        mock_cancel.return_value = False
        resp = self.post_json('/healthcheck/cancel-scan', {})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'No scan' in data['message']


@pytest.mark.unittest
class TestHealthcheckApiWorkers(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch('unmanic.webserver.helpers.healthcheck.get_scan_workers')
    def test_get_workers_success(self, mock_workers):
        mock_workers.return_value = {
            'worker_count': 4, 'scanning': False, 'progress': {},
        }
        resp = self.get_json('/healthcheck/workers')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['worker_count'] == 4

    @patch('unmanic.webserver.helpers.healthcheck.get_scan_workers')
    @patch('unmanic.webserver.helpers.healthcheck.set_scan_workers')
    def test_set_workers_success(self, mock_set, mock_get):
        mock_set.return_value = 8
        mock_get.return_value = {
            'worker_count': 8, 'scanning': False, 'progress': {},
        }
        resp = self.post_json('/healthcheck/workers', {'worker_count': 8})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['worker_count'] == 8

    def test_set_workers_missing_count(self):
        resp = self.post_json('/healthcheck/workers', {})
        assert resp.code == 400


@pytest.mark.unittest
class TestHealthcheckApiReadiness(ApiTestBase):
    __test__ = True
    handler_class = ApiHealthcheckHandler

    @patch('unmanic.webserver.helpers.healthcheck.get_startup_readiness')
    def test_get_readiness_success(self, mock_readiness):
        mock_readiness.return_value = {
            'ready': True,
            'stages': {
                'config_loaded': True,
                'startup_validation': True,
                'db_ready': True,
                'threads_ready': True,
                'ui_server_ready': True,
            },
            'details': {'ui_server_ready': '0.0.0.0:8888'},
            'errors': [],
        }

        resp = self.get_json('/healthcheck/readiness')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['success'] is True
        assert data['ready'] is True

    @patch('unmanic.webserver.helpers.healthcheck.get_startup_readiness')
    def test_get_readiness_not_ready(self, mock_readiness):
        mock_readiness.return_value = {
            'ready': False,
            'stages': {
                'config_loaded': True,
                'startup_validation': True,
                'db_ready': True,
                'threads_ready': True,
                'ui_server_ready': False,
            },
            'details': {'ui_server_ready': 'bind failed'},
            'errors': [{'stage': 'ui_server_ready', 'message': 'bind failed'}],
        }

        resp = self.get_json('/healthcheck/readiness')
        assert resp.code == 503
        data = self.parse_response(resp)
        assert data['success'] is False
        assert data['ready'] is False
