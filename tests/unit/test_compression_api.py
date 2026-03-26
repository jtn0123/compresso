#!/usr/bin/env python3

"""
tests.unit.test_compression_api.py

Tests for the compression stats API handler endpoints.

"""

from unittest.mock import patch

import pytest

from compresso.webserver.api_v2.compression_api import ApiCompressionHandler
from tests.unit.api_test_base import ApiTestBase

VALIDATE_LIB = "compresso.webserver.api_v2.compression_api.validate_library_exists"


@pytest.mark.unittest
class TestCompressionApiStats(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_compression_stats_paginated")
    def test_get_stats_success(self, mock_stats, _mock_validate):
        mock_stats.return_value = {
            "recordsTotal": 10,
            "recordsFiltered": 5,
            "results": [],
        }
        resp = self.post_json("/compression/stats", {"start": 0, "length": 10})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["recordsTotal"] == 10

    def test_get_stats_invalid_json(self):
        resp = self.fetch(
            "/compresso/api/v2/compression/stats",
            method="POST",
            body="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_compression_stats_paginated")
    def test_get_stats_internal_error(self, mock_stats, _mock_validate):
        mock_stats.side_effect = Exception("DB error")
        resp = self.post_json("/compression/stats", {"start": 0, "length": 10})
        assert resp.code == 500


@pytest.mark.unittest
class TestCompressionApiSummary(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_compression_summary")
    def test_get_summary_success(self, mock_summary, _mock_validate):
        mock_summary.return_value = {
            "total_source_size": 1000000,
            "total_destination_size": 500000,
            "file_count": 10,
            "avg_ratio": 0.5,
            "space_saved": 500000,
            "per_library": [],
        }
        resp = self.get_json("/compression/summary")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["file_count"] == 10


@pytest.mark.unittest
class TestCompressionApiDistributions(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_codec_distribution")
    def test_codec_distribution_success(self, mock_dist, _mock_validate):
        mock_dist.return_value = {
            "source_codecs": [{"codec": "hevc", "count": 5}],
            "destination_codecs": [{"codec": "h264", "count": 5}],
        }
        resp = self.get_json("/compression/codec-distribution")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["success"] is True

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_resolution_distribution")
    def test_resolution_distribution_success(self, mock_dist, _mock_validate):
        mock_dist.return_value = [{"resolution": "1920x1080", "count": 10}]
        resp = self.get_json("/compression/resolution-distribution")
        assert resp.code == 200

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_container_distribution")
    def test_container_distribution_success(self, mock_dist, _mock_validate):
        mock_dist.return_value = {
            "source_containers": [{"container": "mkv", "count": 5}],
            "destination_containers": [{"container": "mp4", "count": 5}],
        }
        resp = self.get_json("/compression/container-distribution")
        assert resp.code == 200

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_pending_estimate")
    def test_pending_estimate_success(self, mock_est, _mock_validate):
        mock_est.return_value = {
            "pending_count": 5,
            "estimated_source_size": 5000000,
            "estimated_savings": 2500000,
        }
        resp = self.get_json("/compression/pending-estimate")
        assert resp.code == 200


@pytest.mark.unittest
class TestCompressionApiTimeline(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_space_saved_over_time")
    def test_timeline_success(self, mock_timeline, _mock_validate):
        mock_timeline.return_value = [
            {"date": "2024-01-01", "space_saved": 100000, "file_count": 5},
        ]
        resp = self.get_json("/compression/timeline")
        assert resp.code == 200

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.compression_stats.get_space_saved_over_time")
    def test_timeline_internal_error(self, mock_timeline, _mock_validate):
        mock_timeline.side_effect = Exception("DB error")
        resp = self.get_json("/compression/timeline")
        assert resp.code == 500
