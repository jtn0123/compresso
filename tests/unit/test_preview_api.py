#!/usr/bin/env python3

"""
    tests.unit.test_preview_api.py

    Tests for the preview API handler endpoints.

"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.webserver.api_v2.preview_api import ApiPreviewHandler
from tests.unit.api_test_base import ApiTestBase

VALIDATE_LIB = 'compresso.webserver.helpers.healthcheck.validate_library_exists'


@pytest.mark.unittest
class TestPreviewApiCreate(ApiTestBase):
    __test__ = True
    handler_class = ApiPreviewHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch('compresso.webserver.api_v2.preview_api.PreviewManager')
    @patch('compresso.libs.unmodels.Libraries')
    @patch('compresso.config.Config')
    def test_create_preview_success(self, mock_config_class, mock_libs, mock_pm_class, _mock_validate):
        # Mock allowed roots to include the source path
        mock_lib = MagicMock()
        mock_lib.path = '/test'
        mock_libs.select.return_value = [mock_lib]
        mock_cfg = MagicMock()
        mock_cfg.get_cache_path.return_value = '/tmp/cache'
        mock_config_class.return_value = mock_cfg

        mock_pm = MagicMock()
        mock_pm.create_preview.return_value = 'abc123'
        mock_pm_class.return_value = mock_pm
        resp = self.post_json('/preview/create', {
            'source_path': '/test/video.mkv',
            'start_time': 10,
            'duration': 5,
            'library_id': 1,
        })
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['job_id'] == 'abc123'

    @patch(VALIDATE_LIB, return_value=True)
    @patch('compresso.webserver.api_v2.preview_api.PreviewManager')
    def test_create_preview_value_error(self, mock_pm_class, _mock_validate):
        mock_pm = MagicMock()
        mock_pm.create_preview.side_effect = ValueError("Source file does not exist")
        mock_pm_class.return_value = mock_pm
        resp = self.post_json('/preview/create', {
            'source_path': '/nonexistent.mkv',
        })
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch('compresso.webserver.api_v2.preview_api.PreviewManager')
    def test_create_preview_runtime_error(self, mock_pm_class, _mock_validate):
        mock_pm = MagicMock()
        mock_pm.create_preview.side_effect = RuntimeError("Already running")
        mock_pm_class.return_value = mock_pm
        resp = self.post_json('/preview/create', {
            'source_path': '/test/video.mkv',
        })
        assert resp.code == 400

    def test_create_preview_missing_source(self):
        resp = self.post_json('/preview/create', {})
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=ValueError("Library with ID 999 does not exist"))
    def test_create_preview_invalid_library(self, _mock_validate):
        resp = self.post_json('/preview/create', {
            'source_path': '/test/video.mkv',
            'library_id': 999,
        })
        assert resp.code == 400


@pytest.mark.unittest
class TestPreviewApiStatus(ApiTestBase):
    __test__ = True
    handler_class = ApiPreviewHandler

    @patch('compresso.webserver.api_v2.preview_api.PreviewManager')
    def test_get_status_success(self, mock_pm_class):
        mock_pm = MagicMock()
        mock_pm.get_job_status.return_value = {
            'job_id': 'abc123',
            'status': 'ready',
            'error': None,
            'source_url': '/compresso/preview/abc123/source_web.mp4',
            'encoded_url': '/compresso/preview/abc123/encoded.mp4',
            'source_size': 5000,
            'encoded_size': 3000,
            'source_codec': 'hevc',
            'encoded_codec': 'h264',
            'vmaf_score': 92.5,
            'ssim_score': 0.98,
        }
        mock_pm_class.return_value = mock_pm
        resp = self.post_json('/preview/status', {'job_id': 'abc123'})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['status'] == 'ready'
        assert data['job_id'] == 'abc123'
        assert data['source_url'] == '/compresso/preview/abc123/source_web.mp4'
        assert data['encoded_url'] == '/compresso/preview/abc123/encoded.mp4'
        assert data['source_size'] == 5000
        assert data['encoded_size'] == 3000
        assert data['source_codec'] == 'hevc'
        assert data['encoded_codec'] == 'h264'
        assert data['vmaf_score'] == 92.5
        assert data['ssim_score'] == 0.98

    @patch('compresso.webserver.api_v2.preview_api.PreviewManager')
    def test_get_status_not_found(self, mock_pm_class):
        mock_pm = MagicMock()
        mock_pm.get_job_status.return_value = None
        mock_pm_class.return_value = mock_pm
        resp = self.post_json('/preview/status', {'job_id': 'nonexistent'})
        assert resp.code == 400

    def test_get_status_missing_job_id(self):
        resp = self.post_json('/preview/status', {})
        assert resp.code == 400


@pytest.mark.unittest
class TestPreviewApiCleanup(ApiTestBase):
    __test__ = True
    handler_class = ApiPreviewHandler

    @patch('compresso.webserver.api_v2.preview_api.PreviewManager')
    def test_cleanup_success(self, mock_pm_class):
        mock_pm = MagicMock()
        mock_pm_class.return_value = mock_pm
        resp = self.post_json('/preview/cleanup', {'job_id': 'abc123'})
        assert resp.code == 200

    def test_cleanup_missing_job_id(self):
        resp = self.post_json('/preview/cleanup', {})
        assert resp.code == 400


@pytest.mark.unittest
class TestPreviewApiPathValidation(ApiTestBase):
    __test__ = True
    handler_class = ApiPreviewHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch('compresso.webserver.api_v2.preview_api.PreviewManager')
    @patch('compresso.libs.unmodels.Libraries')
    @patch('compresso.config.Config')
    def test_create_preview_path_outside_library_rejected(self, mock_config_class, mock_libs,
                                                           mock_pm_class, _mock_validate):
        """source_path outside allowed roots should return 400."""
        # Mock Libraries to return a specific path
        mock_lib = MagicMock()
        mock_lib.path = '/media/movies'
        mock_libs.select.return_value = [mock_lib]

        mock_cfg = MagicMock()
        mock_cfg.get_cache_path.return_value = '/tmp/compresso_cache'
        mock_config_class.return_value = mock_cfg

        resp = self.post_json('/preview/create', {
            'source_path': '/etc/passwd',
            'library_id': 1,
        })
        assert resp.code == 400
