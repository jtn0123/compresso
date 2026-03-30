#!/usr/bin/env python3

"""
tests.unit.test_compression_api_coverage.py

Focused coverage tests for uncovered lines in compression_api.py.

Uncovered lines targeted:
  139-141, 146        - get_compression_stats: ValueError and BaseApiError handlers
  184-196             - get_compression_summary: ValueError, BaseApiError, Exception handlers
  227-235, 241-244    - get_pending_estimate: BaseApiError, Exception; _parse_library_id_arg edge cases
  275-287             - get_codec_distribution: ValueError, BaseApiError, Exception handlers
  316-328             - get_resolution_distribution: ValueError, BaseApiError, Exception handlers
  358-370             - get_container_distribution: ValueError, BaseApiError, Exception handlers
  390, 404-406, 408-411 - get_timeline: invalid interval fallback, ValueError, BaseApiError handlers
  440, 461-463, 468-472 - start_library_analysis: missing library_id ValueError, error handlers
  497, 515-527        - get_library_analysis_status: missing library_id ValueError, error handlers
  567-575             - get_optimization_progress: BaseApiError, Exception handlers
  590-617             - get_encoding_speed_timeline: success path + all error handlers

"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.webserver.api_v2.base_api_handler import BaseApiError
from compresso.webserver.api_v2.compression_api import ApiCompressionHandler
from tests.unit.api_test_base import ApiTestBase

VALIDATE_LIB = "compresso.webserver.api_v2.compression_api.validate_library_exists"
COMPRESSION_STATS = "compresso.webserver.helpers.compression_stats"


# ---------------------------------------------------------------------------
# get_compression_stats — ValueError and BaseApiError branches (139-141, 146)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestCompressionStatsErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, side_effect=ValueError("Library not found"))
    def test_get_stats_value_error_returns_400(self, _mock_validate):
        """ValueError from validate_library_exists triggers 400 (lines 139-141)."""
        resp = self.post_json("/compression/stats", {"start": 0, "length": 10, "library_id": 999})
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=BaseApiError("Bad library"))
    def test_get_stats_base_api_error_returns_400(self, _mock_validate):
        """BaseApiError branch returns 400 (line 146)."""
        resp = self.post_json("/compression/stats", {"start": 0, "length": 10, "library_id": 1})
        assert resp.code == 400


# ---------------------------------------------------------------------------
# get_compression_summary — ValueError, BaseApiError, Exception (184-196)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestCompressionSummaryErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, side_effect=ValueError("Library not found"))
    def test_get_summary_value_error_returns_400(self, _mock_validate):
        """ValueError returns 400 (lines 184-187)."""
        resp = self.get_json("/compression/summary?library_id=999")
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=BaseApiError("Access denied"))
    def test_get_summary_base_api_error_returns_400(self, _mock_validate):
        """BaseApiError returns 400 (lines 188-192)."""
        resp = self.get_json("/compression/summary?library_id=1")
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_compression_summary", side_effect=Exception("DB crash"))
    def test_get_summary_generic_exception_returns_500(self, _mock_summary, _mock_validate):
        """Unhandled exception returns 500 (lines 193-196)."""
        resp = self.get_json("/compression/summary")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# get_pending_estimate — BaseApiError, Exception (227-235)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestPendingEstimateErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(COMPRESSION_STATS + ".get_pending_estimate", side_effect=BaseApiError("Estimate failed"))
    def test_pending_estimate_base_api_error_returns_400(self, _mock_est):
        """BaseApiError returns 400 (lines 227-231)."""
        resp = self.get_json("/compression/pending-estimate")
        assert resp.code == 400

    @patch(COMPRESSION_STATS + ".get_pending_estimate", side_effect=Exception("DB crash"))
    def test_pending_estimate_generic_exception_returns_500(self, _mock_est):
        """Unhandled exception returns 500 (lines 232-235)."""
        resp = self.get_json("/compression/pending-estimate")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# _parse_library_id_arg — non-int value returns None (241-244)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestParseLibraryIdArg(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_compression_summary")
    def test_parse_library_id_non_integer_returns_none(self, mock_summary, _mock_validate):
        """Non-integer library_id query param gracefully returns None (lines 241-244)."""
        mock_summary.return_value = {
            "total_source_size": 0,
            "total_destination_size": 0,
            "file_count": 0,
            "avg_ratio": 0.0,
            "space_saved": 0,
            "per_library": [],
        }
        # Pass a non-integer value; _parse_library_id_arg should catch ValueError and return None
        resp = self.get_json("/compression/summary?library_id=not_a_number")
        assert resp.code == 200
        mock_summary.assert_called_once_with(library_id=None)

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_compression_summary")
    def test_parse_library_id_integer_value_is_passed(self, mock_summary, _mock_validate):
        """Valid integer library_id is parsed and passed to helper (line 242)."""
        mock_summary.return_value = {
            "total_source_size": 100,
            "total_destination_size": 80,
            "file_count": 5,
            "avg_ratio": 0.8,
            "space_saved": 20,
            "per_library": [],
        }
        resp = self.get_json("/compression/summary?library_id=3")
        assert resp.code == 200
        mock_summary.assert_called_once_with(library_id=3)


# ---------------------------------------------------------------------------
# get_codec_distribution — ValueError, BaseApiError, Exception (275-287)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestCodecDistributionErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, side_effect=ValueError("Library not found"))
    def test_codec_distribution_value_error_returns_400(self, _mock_validate):
        """ValueError returns 400 (lines 275-278)."""
        resp = self.get_json("/compression/codec-distribution?library_id=999")
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=BaseApiError("Access denied"))
    def test_codec_distribution_base_api_error_returns_400(self, _mock_validate):
        """BaseApiError returns 400 (lines 279-283)."""
        resp = self.get_json("/compression/codec-distribution?library_id=1")
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_codec_distribution", side_effect=Exception("DB crash"))
    def test_codec_distribution_generic_exception_returns_500(self, _mock_dist, _mock_validate):
        """Unhandled exception returns 500 (lines 284-287)."""
        resp = self.get_json("/compression/codec-distribution")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# get_resolution_distribution — ValueError, BaseApiError, Exception (316-328)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestResolutionDistributionErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, side_effect=ValueError("Library not found"))
    def test_resolution_distribution_value_error_returns_400(self, _mock_validate):
        """ValueError returns 400 (lines 316-319)."""
        resp = self.get_json("/compression/resolution-distribution?library_id=999")
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=BaseApiError("Access denied"))
    def test_resolution_distribution_base_api_error_returns_400(self, _mock_validate):
        """BaseApiError returns 400 (lines 320-324)."""
        resp = self.get_json("/compression/resolution-distribution?library_id=1")
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_resolution_distribution", side_effect=Exception("DB crash"))
    def test_resolution_distribution_generic_exception_returns_500(self, _mock_dist, _mock_validate):
        """Unhandled exception returns 500 (lines 325-328)."""
        resp = self.get_json("/compression/resolution-distribution")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# get_container_distribution — ValueError, BaseApiError, Exception (358-370)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestContainerDistributionErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, side_effect=ValueError("Library not found"))
    def test_container_distribution_value_error_returns_400(self, _mock_validate):
        """ValueError returns 400 (lines 358-361)."""
        resp = self.get_json("/compression/container-distribution?library_id=999")
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=BaseApiError("Access denied"))
    def test_container_distribution_base_api_error_returns_400(self, _mock_validate):
        """BaseApiError returns 400 (lines 362-366)."""
        resp = self.get_json("/compression/container-distribution?library_id=1")
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_container_distribution", side_effect=Exception("DB crash"))
    def test_container_distribution_generic_exception_returns_500(self, _mock_dist, _mock_validate):
        """Unhandled exception returns 500 (lines 367-370)."""
        resp = self.get_json("/compression/container-distribution")
        assert resp.code == 500


# ---------------------------------------------------------------------------
# get_timeline — invalid interval fallback, ValueError, BaseApiError (390, 404-411)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestTimelineErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_space_saved_over_time")
    def test_timeline_invalid_interval_falls_back_to_day(self, mock_timeline, _mock_validate):
        """Invalid interval is coerced to 'day' before calling helper (line 390)."""
        mock_timeline.return_value = []
        resp = self.get_json("/compression/timeline?interval=yearly")
        assert resp.code == 200
        _call_kwargs = mock_timeline.call_args[1]
        assert _call_kwargs.get("interval") == "day"

    @patch(VALIDATE_LIB, side_effect=ValueError("Library not found"))
    def test_timeline_value_error_returns_400(self, _mock_validate):
        """ValueError returns 400 (lines 404-406)."""
        resp = self.get_json("/compression/timeline?library_id=999")
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=BaseApiError("Access denied"))
    def test_timeline_base_api_error_returns_400(self, _mock_validate):
        """BaseApiError returns 400 (lines 408-411)."""
        resp = self.get_json("/compression/timeline?library_id=1")
        assert resp.code == 400


# ---------------------------------------------------------------------------
# start_library_analysis — missing library_id, ValueError, BaseApiError, Exception
# (440, 461-463, 468-472)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestStartLibraryAnalysisErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    def test_start_analysis_missing_library_id_returns_400(self):
        """Missing library_id raises ValueError → 400 (line 440)."""
        # library_id is required by schema so send a dummy non-zero value to pass
        # schema then rely on start_analysis to surface error — but the check
        # happens before library_analysis is called (line 439-440 checks for falsy).
        # The LibraryAnalysisRequestSchema requires library_id as Int, so sending
        # library_id=0 (falsy) should trigger the ValueError branch.
        resp = self.post_json("/compression/library-analysis", {"library_id": 0})
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=ValueError("Library not found"))
    def test_start_analysis_value_error_returns_400(self, _mock_validate):
        """ValueError from validate_library_exists → 400 (lines 461-463)."""
        resp = self.post_json("/compression/library-analysis", {"library_id": 999})
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=BaseApiError("Access denied"))
    def test_start_analysis_base_api_error_returns_400(self, _mock_validate):
        """BaseApiError → 400 (lines 464-468)."""
        resp = self.post_json("/compression/library-analysis", {"library_id": 1})
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.library_analysis.start_analysis", side_effect=Exception("Thread crash"))
    def test_start_analysis_generic_exception_returns_500(self, _mock_start, _mock_validate):
        """Unhandled exception → 500 (lines 469-472)."""
        resp = self.post_json("/compression/library-analysis", {"library_id": 1})
        assert resp.code == 500

    @patch(VALIDATE_LIB, return_value=True)
    @patch("compresso.webserver.helpers.library_analysis.start_analysis")
    def test_start_analysis_success(self, mock_start, _mock_validate):
        """Happy path returns 200 with status field."""
        mock_start.return_value = {"status": "running", "progress": {"checked": 0, "total": 100}}
        resp = self.post_json("/compression/library-analysis", {"library_id": 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["status"] == "running"


# ---------------------------------------------------------------------------
# get_library_analysis_status — missing library_id, ValueError, BaseApiError, Exception
# (497, 515-527)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestLibraryAnalysisStatusErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    def test_get_analysis_status_missing_library_id_returns_400(self):
        """library_id=0 (falsy) raises ValueError → 400 (line 497)."""
        resp = self.post_json("/compression/library-analysis/status", {"library_id": 0})
        assert resp.code == 400

    @patch("compresso.webserver.helpers.library_analysis.get_analysis_status", side_effect=ValueError("Bad id"))
    def test_get_analysis_status_value_error_returns_400(self, _mock_status):
        """ValueError from helper → 400 (lines 515-518)."""
        resp = self.post_json("/compression/library-analysis/status", {"library_id": 1})
        assert resp.code == 400

    @patch("compresso.webserver.helpers.library_analysis.get_analysis_status", side_effect=BaseApiError("Access denied"))
    def test_get_analysis_status_base_api_error_returns_400(self, _mock_status):
        """BaseApiError → 400 (lines 519-523)."""
        resp = self.post_json("/compression/library-analysis/status", {"library_id": 1})
        assert resp.code == 400

    @patch("compresso.webserver.helpers.library_analysis.get_analysis_status", side_effect=Exception("DB crash"))
    def test_get_analysis_status_generic_exception_returns_500(self, _mock_status):
        """Unhandled exception → 500 (lines 524-527)."""
        resp = self.post_json("/compression/library-analysis/status", {"library_id": 1})
        assert resp.code == 500

    @patch("compresso.webserver.helpers.library_analysis.get_analysis_status")
    def test_get_analysis_status_success(self, mock_status):
        """Happy path returns 200 with status/progress/version/results."""
        mock_status.return_value = {
            "status": "complete",
            "progress": {"checked": 100, "total": 100},
            "version": 1,
            "results": {"groups": []},
        }
        resp = self.post_json("/compression/library-analysis/status", {"library_id": 2})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["status"] == "complete"
        assert data["version"] == 1


# ---------------------------------------------------------------------------
# get_optimization_progress — BaseApiError, Exception (567-575)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestOptimizationProgressErrors(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch("compresso.libs.unmodels.CompressionStats")
    @patch("compresso.libs.unmodels.LibraryAnalysisCache")
    def test_optimization_progress_base_api_error_returns_400(self, mock_cache, mock_stats):
        """BaseApiError raised inside the try block → 400 (lines 567-571)."""
        mock_stats.select.return_value.count.side_effect = BaseApiError("DB unavailable")
        resp = self.get_json("/compression/optimization-progress")
        assert resp.code == 400

    @patch("compresso.libs.unmodels.CompressionStats")
    @patch("compresso.libs.unmodels.LibraryAnalysisCache")
    def test_optimization_progress_generic_exception_returns_500(self, mock_cache, mock_stats):
        """Unhandled exception → 500 (lines 572-575)."""
        mock_stats.select.side_effect = Exception("DB crash")
        resp = self.get_json("/compression/optimization-progress")
        assert resp.code == 500

    @patch("compresso.libs.unmodels.CompressionStats")
    @patch("compresso.libs.unmodels.LibraryAnalysisCache")
    def test_optimization_progress_success_with_zero_total(self, mock_cache, mock_stats):
        """When total_files is 0, falls back to processed_files count."""
        mock_stats.select.return_value.count.return_value = 5
        # No LibraryAnalysisCache rows → total_files stays 0 → becomes processed_files
        mock_cache.select.return_value = []
        resp = self.get_json("/compression/optimization-progress")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["processed_files"] == 5
        assert data["total_files"] == 5

    @patch("compresso.libs.unmodels.CompressionStats")
    @patch("compresso.libs.unmodels.LibraryAnalysisCache")
    def test_optimization_progress_success_with_cache(self, mock_cache, mock_stats):
        """When cache has rows, total_files sums their file_count values."""
        mock_stats.select.return_value.count.return_value = 10
        cache_row = MagicMock()
        cache_row.file_count = 50
        mock_cache.select.return_value = [cache_row]
        resp = self.get_json("/compression/optimization-progress")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["processed_files"] == 10
        assert data["total_files"] == 50
        assert data["percent"] == 20.0


# ---------------------------------------------------------------------------
# get_encoding_speed_timeline — success + all error handlers (590-617)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestEncodingSpeedTimeline(ApiTestBase):
    __test__ = True
    handler_class = ApiCompressionHandler

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_encoding_speed_timeline")
    def test_encoding_speed_timeline_success(self, mock_timeline, _mock_validate):
        """Happy path returns 200 with data list (lines 590-604)."""
        mock_timeline.return_value = [
            {"date": "2024-01-01", "avg_fps": 120.5, "file_count": 3},
        ]
        resp = self.get_json("/compression/encoding-speed")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["avg_fps"] == 120.5

    @patch(VALIDATE_LIB, side_effect=ValueError("Library not found"))
    def test_encoding_speed_timeline_value_error_returns_400(self, _mock_validate):
        """ValueError → 400 (lines 605-608)."""
        resp = self.get_json("/compression/encoding-speed?library_id=999")
        assert resp.code == 400

    @patch(VALIDATE_LIB, side_effect=BaseApiError("Access denied"))
    def test_encoding_speed_timeline_base_api_error_returns_400(self, _mock_validate):
        """BaseApiError → 400 (lines 609-613)."""
        resp = self.get_json("/compression/encoding-speed?library_id=1")
        assert resp.code == 400

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_encoding_speed_timeline", side_effect=Exception("DB crash"))
    def test_encoding_speed_timeline_generic_exception_returns_500(self, _mock_timeline, _mock_validate):
        """Unhandled exception → 500 (lines 614-617)."""
        resp = self.get_json("/compression/encoding-speed")
        assert resp.code == 500

    @patch(VALIDATE_LIB, return_value=True)
    @patch(COMPRESSION_STATS + ".get_encoding_speed_timeline")
    def test_encoding_speed_timeline_with_library_id(self, mock_timeline, _mock_validate):
        """library_id query param is parsed and forwarded to helper."""
        mock_timeline.return_value = []
        resp = self.get_json("/compression/encoding-speed?library_id=7")
        assert resp.code == 200
        mock_timeline.assert_called_once_with(library_id=7)
