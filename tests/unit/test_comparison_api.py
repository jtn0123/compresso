#!/usr/bin/env python3

from unittest.mock import patch

import pytest

from compresso.webserver.api_v2.comparison_api import ApiComparisonHandler
from tests.unit.api_test_base import ApiTestBase

MOCK_STATUS = {
    "batch_uuid": "batch-1",
    "source_path": "/media/movie.mkv",
    "source_size": 1000,
    "source_url": "/compresso/preview/bakeoff/batch-1/source_reference.mp4",
    "library_id": 1,
    "start_time": 0,
    "duration": 10,
    "status": "completed",
    "progress": 100,
    "winner_candidate_id": None,
    "full_encode_task_id": None,
    "error": None,
    "candidates": [
        {
            "id": 1,
            "candidate_uuid": "candidate-1",
            "profile_key": "x265_crf_22",
            "profile_label": "x265 CRF 22",
            "encoder": "libx265",
            "codec": "hevc",
            "status": "completed",
            "progress": 100,
            "output_path": "/cache/candidate.mp4",
            "output_url": "/compresso/preview/bakeoff/batch-1/candidate.mp4",
            "output_size": 600,
            "source_size": 1000,
            "size_saved_bytes": 400,
            "size_saved_percent": 40,
            "vmaf_score": 95,
            "ssim_score": 0.98,
            "error": None,
        }
    ],
}


@pytest.mark.unittest
class TestComparisonApi(ApiTestBase):
    __test__ = True
    handler_class = ApiComparisonHandler

    @patch("compresso.webserver.api_v2.comparison_api.ComparisonManager.get_profiles")
    def test_profiles_reports_local_availability(self, get_profiles):
        get_profiles.return_value = [
            {
                "key": "x265_crf_22",
                "label": "x265 CRF 22",
                "description": "HEVC",
                "encoder": "libx265",
                "codec": "hevc",
                "crf": 22,
                "preset": "medium",
                "hardware": False,
                "available": True,
            }
        ]

        response = self.get_json("/comparison/profiles")

        assert response.code == 200
        assert self.parse_response(response)["profiles"][0]["available"] is True

    @patch("compresso.webserver.helpers.healthcheck.validate_library_exists", return_value=True)
    @patch("compresso.webserver.api_v2.comparison_api.validate_preview_source_path", return_value="/media/movie.mkv")
    @patch("compresso.webserver.api_v2.comparison_api.ComparisonManager")
    def test_create_returns_persistent_batch_id(self, manager_class, _validate_path, _validate_library):
        manager_class.return_value.create_batch.return_value = "batch-1"

        response = self.post_json(
            "/comparison/create",
            {
                "source_path": "/media/movie.mkv",
                "library_id": 1,
                "start_time": 5,
                "duration": 10,
                "profile_keys": ["x265_crf_22", "svt_av1_crf_30"],
            },
        )

        assert response.code == 200
        assert self.parse_response(response)["batch_uuid"] == "batch-1"
        _validate_path.assert_called_once_with("/media/movie.mkv", library_id=1, allow_cache=False)

    def test_create_requires_two_profiles(self):
        response = self.post_json(
            "/comparison/create",
            {"source_path": "/media/movie.mkv", "profile_keys": ["x265_crf_22"]},
        )

        assert response.code == 400

    @patch("compresso.webserver.api_v2.comparison_api.ComparisonManager")
    def test_status_returns_candidate_progress_and_metrics(self, manager_class):
        manager_class.return_value.get_batch_status.return_value = dict(MOCK_STATUS)

        response = self.post_json("/comparison/status", {"batch_uuid": "batch-1"})

        assert response.code == 200
        data = self.parse_response(response)
        assert data["candidates"][0]["progress"] == 100
        assert data["candidates"][0]["vmaf_score"] == 95

    @patch("compresso.webserver.api_v2.comparison_api.ComparisonManager")
    def test_winner_can_queue_full_encode(self, manager_class):
        status = dict(MOCK_STATUS)
        status["full_encode_task_id"] = 42
        manager_class.return_value.select_winner.return_value = status

        response = self.post_json(
            "/comparison/winner",
            {
                "batch_uuid": "batch-1",
                "candidate_uuid": "candidate-1",
                "queue_full_encode": True,
            },
        )

        assert response.code == 200
        assert self.parse_response(response)["full_encode_task_id"] == 42
        manager_class.return_value.select_winner.assert_called_once_with("batch-1", "candidate-1", queue_full_encode=True)
