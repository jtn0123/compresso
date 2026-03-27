#!/usr/bin/env python3

"""
tests.unit.test_helpers_library_analysis.py

Tests for the library analysis helper functions.

"""

import json
from unittest.mock import MagicMock, patch

import pytest

ANALYSIS_MODULE = "compresso.webserver.helpers.library_analysis"


@pytest.mark.unittest
class TestGetAnalysisStatus:
    @patch(ANALYSIS_MODULE + "._active_analyses", {})
    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    def test_status_none_when_no_cache(self, mock_cache_model):
        from compresso.webserver.helpers.library_analysis import get_analysis_status

        mock_cache_model.get_or_none.return_value = None
        result = get_analysis_status(99)
        assert result["status"] == "none"
        assert result["results"] is None
        assert result["version"] == 0

    @patch(
        ANALYSIS_MODULE + "._active_analyses",
        {
            1: {"status": "running", "progress": {"checked": 5, "total": 10}},
        },
    )
    def test_status_running(self):
        from compresso.webserver.helpers.library_analysis import get_analysis_status

        result = get_analysis_status(1)
        assert result["status"] == "running"
        assert result["progress"]["checked"] == 5

    @patch(ANALYSIS_MODULE + "._active_analyses", {})
    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    def test_status_complete_from_cache(self, mock_cache_model):
        from compresso.webserver.helpers.library_analysis import get_analysis_status

        mock_cache = MagicMock()
        mock_cache.analysis_json = json.dumps({"groups": [], "total_files": 50})
        mock_cache.file_count = 50
        mock_cache.version = 3
        mock_cache_model.get_or_none.return_value = mock_cache
        mock_cache_model.library_id = MagicMock()

        result = get_analysis_status(1)
        assert result["status"] == "complete"
        assert result["version"] == 3
        assert result["results"]["total_files"] == 50


@pytest.mark.unittest
class TestStartAnalysis:
    @patch(ANALYSIS_MODULE + ".threading")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._active_analyses", {})
    def test_start_analysis_creates_thread(self, mock_library_cls, mock_threading):
        from compresso.webserver.helpers.library_analysis import start_analysis

        mock_lib = MagicMock()
        mock_lib.get_path.return_value = "/media/movies"
        mock_library_cls.return_value = mock_lib

        result = start_analysis(1)
        assert result["status"] == "running"
        mock_threading.Thread.assert_called_once()
        mock_threading.Thread.return_value.start.assert_called_once()

    @patch(ANALYSIS_MODULE + "._analyses_lock", MagicMock())
    @patch(
        ANALYSIS_MODULE + "._active_analyses",
        {
            1: {"status": "running", "progress": {"checked": 3, "total": 10}},
        },
    )
    def test_start_analysis_already_running(self):
        from compresso.webserver.helpers.library_analysis import start_analysis

        result = start_analysis(1)
        assert result["status"] == "running"
        assert result["progress"]["checked"] == 3


@pytest.mark.unittest
class TestLookupSavings:
    def test_exact_match_high_confidence(self):
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        historical = {
            ("h264", "1920x1080"): {"avg_savings_pct": 45.0, "count": 25},
        }
        pct, count, confidence = _lookup_savings(historical, "h264", "1920x1080")
        assert pct == 45.0
        assert count == 25
        assert confidence == "high"

    def test_exact_match_medium_confidence(self):
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        historical = {
            ("hevc", "3840x2160"): {"avg_savings_pct": 30.0, "count": 10},
        }
        pct, count, confidence = _lookup_savings(historical, "hevc", "3840x2160")
        assert confidence == "medium"

    def test_exact_match_low_confidence(self):
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        historical = {
            ("mpeg2", "720x480"): {"avg_savings_pct": 60.0, "count": 3},
        }
        pct, count, confidence = _lookup_savings(historical, "mpeg2", "720x480")
        assert confidence == "low"

    def test_fallback_codec_only(self):
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        historical = {
            ("h264", "1920x1080"): {"avg_savings_pct": 40.0, "count": 10},
            ("h264", "1280x720"): {"avg_savings_pct": 50.0, "count": 10},
        }
        pct, count, confidence = _lookup_savings(historical, "h264", "3840x2160")
        assert pct == 45.0  # weighted average: (40*10 + 50*10) / 20
        assert count == 20
        assert confidence == "medium"

    def test_no_data_returns_zeros(self):
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        pct, count, confidence = _lookup_savings({}, "vp9", "1920x1080")
        assert pct == 0
        assert count == 0
        assert confidence == "none"
