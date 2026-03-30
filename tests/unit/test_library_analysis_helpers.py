#!/usr/bin/env python3

"""
tests.unit.test_library_analysis_helpers.py

Comprehensive unit tests for compresso/webserver/helpers/library_analysis.py.
Targets uncovered lines 105-286 and 294-329 (the _run_analysis background
worker and the _get_historical_savings DB query).
"""

import json
import threading
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

ANALYSIS_MODULE = "compresso.webserver.helpers.library_analysis"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_meta(codec="h264", resolution="1920x1080"):
    return {"codec": codec, "resolution": resolution}


def _make_probe_data(duration=60.0, bit_rate="5000000"):
    return {"format": {"duration": str(duration), "bit_rate": bit_rate}}


# ---------------------------------------------------------------------------
# _run_analysis — file-walking and grouping (lines 105-176)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunAnalysisFileWalking:
    """Tests for the os.walk / ffprobe portion of _run_analysis."""

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_single_media_file_grouped_correctly(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """A single .mkv file is probed and ends up in one result group."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["movie.mkv"])]
        mock_getsize.return_value = 1_000_000_000
        mock_meta.return_value = _make_meta("h264", "1920x1080")
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        mock_cache_model.get_or_create.return_value = (MagicMock(), True)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert info["status"] == "complete"
        assert info["progress"]["total"] == 1
        assert info["progress"]["checked"] == 1

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_non_media_files_are_skipped(self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model):
        """Files with non-media extensions must not be probed."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["notes.txt", "cover.jpg", "movie.mkv"])]
        mock_getsize.return_value = 500_000_000
        mock_meta.return_value = _make_meta()
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []
        mock_cache_model.get_or_create.return_value = (MagicMock(), True)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        # Only the .mkv triggers a metadata probe
        assert mock_meta.call_count == 1
        assert info["progress"]["total"] == 1

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_all_media_extensions_are_included(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """All 14 recognised media extensions must be picked up."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        media_files = [
            "a.mp4",
            "b.mkv",
            "c.avi",
            "d.mov",
            "e.wmv",
            "f.flv",
            "g.webm",
            "h.m4v",
            "i.ts",
            "j.mpg",
            "k.mpeg",
            "l.m2ts",
            "m.vob",
            "n.ogv",
            "o.3gp",
        ]
        mock_walk.return_value = [("/media", [], media_files)]
        mock_getsize.return_value = 100_000_000
        mock_meta.return_value = _make_meta()
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []
        mock_cache_model.get_or_create.return_value = (MagicMock(), True)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert info["progress"]["total"] == len(media_files)
        assert mock_meta.call_count == len(media_files)

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_empty_directory_produces_zero_files(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """An empty library dir results in total=0 and complete status."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], [])]
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []
        mock_cache_model.get_or_create.return_value = (MagicMock(), True)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert info["status"] == "complete"
        assert info["progress"]["total"] == 0
        assert mock_meta.call_count == 0

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_codec_estimated_suffix_stripped(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """'(estimated)' suffix should be stripped from codec names."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["file.mkv"])]
        mock_getsize.return_value = 100_000
        mock_meta.return_value = {"codec": "H264 (estimated)", "resolution": "1280x720"}
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved_json = {}

        def capture_get_or_create(library_id, defaults):
            saved_json.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture_get_or_create

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        groups = saved_json.get("groups", [])
        assert len(groups) == 1
        assert groups[0]["codec"] == "h264"

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_failed_probe_skips_file_but_increments_checked(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """A file that raises during metadata extraction is skipped but
        progress.checked still advances."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["bad.mkv", "good.mkv"])]
        mock_getsize.return_value = 500_000
        # First call raises, second succeeds
        mock_meta.side_effect = [RuntimeError("ffprobe failed"), _make_meta()]
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []
        mock_cache_model.get_or_create.return_value = (MagicMock(), True)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert info["progress"]["checked"] == 2
        assert info["status"] == "complete"

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_multiple_files_same_codec_resolution_grouped_together(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """Three files with the same (codec, resolution) share one group."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["a.mkv", "b.mkv", "c.mkv"])]
        mock_getsize.return_value = 1_000_000
        mock_meta.return_value = _make_meta("hevc", "3840x2160")
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert len(saved["groups"]) == 1
        assert saved["groups"][0]["count"] == 3
        assert saved["groups"][0]["total_size_bytes"] == 3_000_000


# ---------------------------------------------------------------------------
# _run_analysis — bitrate calculation (lines 148-158)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunAnalysisBitrate:
    """Tests for the inline bitrate-from-probe logic."""

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_bitrate_calculated_from_probe_bit_rate(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """When probe_data provides bit_rate, avg_bitrate_mbps should be set."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["movie.mp4"])]
        mock_getsize.return_value = 1_000_000_000
        mock_meta.return_value = _make_meta()
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        probe_data = _make_probe_data(duration=100.0, bit_rate="20000000")

        with patch("compresso.libs.ffprobe_utils.probe_file", return_value=probe_data):
            info = {"status": "running", "progress": {"checked": 0, "total": 0}}
            _run_analysis(1, "/media", info)

        assert saved["groups"][0]["avg_bitrate_mbps"] == pytest.approx(20.0, abs=0.1)

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_bitrate_falls_back_to_size_over_duration_when_no_bit_rate_field(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """When probe_data has duration but no bit_rate, derive from size."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        file_size = 500_000_000  # bytes
        duration = 100.0  # seconds
        expected_mbps = file_size * 8 / duration / 1_000_000  # = 40.0

        mock_walk.return_value = [("/media", [], ["movie.mp4"])]
        mock_getsize.return_value = file_size
        mock_meta.return_value = _make_meta()
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        probe_data = {"format": {"duration": str(duration)}}  # no bit_rate key

        with patch("compresso.libs.ffprobe_utils.probe_file", return_value=probe_data):
            info = {"status": "running", "progress": {"checked": 0, "total": 0}}
            _run_analysis(1, "/media", info)

        assert saved["groups"][0]["avg_bitrate_mbps"] == pytest.approx(expected_mbps, abs=0.1)

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_bitrate_is_zero_when_probe_raises(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """A probe exception must not crash the analysis; bitrate stays 0."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["movie.mp4"])]
        mock_getsize.return_value = 200_000_000
        mock_meta.return_value = _make_meta()
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        with patch("compresso.libs.ffprobe_utils.probe_file", side_effect=RuntimeError("timeout")):
            info = {"status": "running", "progress": {"checked": 0, "total": 0}}
            _run_analysis(1, "/media", info)

        assert saved["groups"][0]["avg_bitrate_mbps"] == 0.0

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_bitrate_is_zero_when_duration_is_zero(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """When probe returns duration=0, bitrate should remain 0."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["movie.mp4"])]
        mock_getsize.return_value = 100_000_000
        mock_meta.return_value = _make_meta()
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        probe_data = {"format": {"duration": "0", "bit_rate": "8000000"}}

        with patch("compresso.libs.ffprobe_utils.probe_file", return_value=probe_data):
            info = {"status": "running", "progress": {"checked": 0, "total": 0}}
            _run_analysis(1, "/media", info)

        assert saved["groups"][0]["avg_bitrate_mbps"] == 0.0


# ---------------------------------------------------------------------------
# _run_analysis — skip-codecs / "already optimal" path (lines 205-220)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunAnalysisSkipCodecs:
    """Tests for the skip-codecs / already_optimal branch."""

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_files_in_skip_codecs_marked_optimal(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """Files whose codec is in skip_codecs must have confidence='optimal'
        and zero estimated savings."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["movie.mkv"])]
        mock_getsize.return_value = 2_000_000_000
        mock_meta.return_value = _make_meta("hevc", "1920x1080")
        mock_hist.return_value = {("h264", "1920x1080"): {"avg_savings_pct": 40.0, "count": 30}}
        mock_lib_cls.return_value.get_skip_codecs.return_value = ["hevc"]

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        group = saved["groups"][0]
        assert group["confidence"] == "optimal"
        assert group["estimated_savings_pct"] == 0
        assert group["estimated_savings_bytes"] == 0
        assert saved["already_optimal"] == 1

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_skip_codecs_exception_defaults_to_empty(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """If Library.get_skip_codecs() raises, the list should default to []
        and analysis should still complete successfully."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["movie.mkv"])]
        mock_getsize.return_value = 1_000_000
        mock_meta.return_value = _make_meta("h264", "1080p")
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.side_effect = Exception("DB error")
        mock_cache_model.get_or_create.return_value = (MagicMock(), True)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert info["status"] == "complete"


# ---------------------------------------------------------------------------
# _run_analysis — result aggregation and sorting (lines 182-243)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunAnalysisAggregation:
    """Tests for total counters, savings estimation, and sort order."""

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_total_counters_sum_all_groups(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """total_files and total_size_bytes must aggregate across all groups."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        files = ["a.mkv", "b.mkv", "c.mp4"]
        mock_walk.return_value = [("/media", [], files)]
        mock_getsize.return_value = 1_000_000
        mock_meta.side_effect = [
            _make_meta("h264", "1080p"),
            _make_meta("h264", "1080p"),
            _make_meta("hevc", "720p"),
        ]
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert saved["total_files"] == 3
        assert saved["total_size_bytes"] == 3_000_000
        assert len(saved["groups"]) == 2

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_groups_sorted_by_estimated_savings_descending(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """Result groups should be sorted with highest estimated savings first."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["a.mkv", "b.mp4"])]
        mock_getsize.return_value = 1_000_000_000
        mock_meta.side_effect = [
            _make_meta("mpeg2", "720p"),  # low savings
            _make_meta("h264", "1080p"),  # higher savings
        ]
        mock_hist.return_value = {
            ("mpeg2", "720p"): {"avg_savings_pct": 10.0, "count": 5},
            ("h264", "1080p"): {"avg_savings_pct": 50.0, "count": 25},
        }
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        savings = [g["estimated_savings_bytes"] for g in saved["groups"]]
        assert savings == sorted(savings, reverse=True)

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_result_has_last_run_iso_string(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """results['last_run'] must be a parseable ISO-8601 datetime string."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], [])]
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        # Should not raise
        datetime.fromisoformat(saved["last_run"])

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_historical_savings_applied_to_group(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """estimated_savings_bytes should reflect historical savings percentage."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        file_size = 1_000_000_000  # 1 GB
        savings_pct = 40.0

        mock_walk.return_value = [("/media", [], ["movie.mkv"])]
        mock_getsize.return_value = file_size
        mock_meta.return_value = _make_meta("h264", "1920x1080")
        mock_hist.return_value = {("h264", "1920x1080"): {"avg_savings_pct": savings_pct, "count": 30}}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        saved = {}

        def capture(library_id, defaults):
            saved.update(json.loads(defaults["analysis_json"]))
            return MagicMock(), True

        mock_cache_model.get_or_create.side_effect = capture

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        expected_savings = int(file_size * savings_pct / 100)
        assert saved["groups"][0]["estimated_savings_bytes"] == expected_savings
        assert saved["total_estimated_savings_bytes"] == expected_savings


# ---------------------------------------------------------------------------
# _run_analysis — cache persistence (lines 254-269)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunAnalysisCachePersistence:
    """Tests for the get_or_create / update path."""

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_new_cache_entry_created_when_none_exists(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """get_or_create is called exactly once with library_id and defaults."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], [])]
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        mock_cache = MagicMock()
        mock_cache_model.get_or_create.return_value = (mock_cache, True)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(42, "/media", info)

        mock_cache_model.get_or_create.assert_called_once()
        call_kwargs = mock_cache_model.get_or_create.call_args
        assert call_kwargs[1]["library_id"] == 42 or call_kwargs[0][0] == 42

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_existing_cache_entry_is_updated_not_recreated(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """When created=False the existing record's fields are updated and saved."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], [])]
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        existing_cache = MagicMock()
        existing_cache.version = 5
        mock_cache_model.get_or_create.return_value = (existing_cache, False)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        existing_cache.save.assert_called_once()
        assert existing_cache.version == 6  # incremented

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch(ANALYSIS_MODULE + ".extract_media_metadata")
    @patch("os.path.getsize")
    @patch("os.walk")
    def test_cache_updated_with_correct_file_count(
        self, mock_walk, mock_getsize, mock_meta, mock_hist, mock_lib_cls, mock_cache_model
    ):
        """file_count on the existing cache record is set to total_files."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.return_value = [("/media", [], ["a.mkv", "b.mkv"])]
        mock_getsize.return_value = 100_000
        mock_meta.return_value = _make_meta()
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []

        existing_cache = MagicMock()
        existing_cache.version = 1
        mock_cache_model.get_or_create.return_value = (existing_cache, False)

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert existing_cache.file_count == 2


# ---------------------------------------------------------------------------
# _run_analysis — error handling and cleanup (lines 274-286)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunAnalysisErrorHandling:
    """Tests for exception handling and the cleanup thread."""

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch("os.walk")
    def test_unexpected_exception_sets_error_status(self, mock_walk, mock_hist, mock_lib_cls, mock_cache_model):
        """An unhandled exception during analysis must set status='error'."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.side_effect = PermissionError("no access")

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert info["status"] == "error"
        assert "no access" in info["error"]

    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch("os.walk")
    def test_error_info_contains_exception_message(self, mock_walk, mock_hist, mock_lib_cls, mock_cache_model):
        """info['error'] must contain the exception message string."""
        from compresso.webserver.helpers.library_analysis import _run_analysis

        mock_walk.side_effect = ValueError("something broke badly")

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        _run_analysis(1, "/media", info)

        assert info.get("error") == "something broke badly"

    @patch(ANALYSIS_MODULE + "._active_analyses", {})
    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    @patch(ANALYSIS_MODULE + ".Library")
    @patch(ANALYSIS_MODULE + "._get_historical_savings")
    @patch("os.walk")
    def test_cleanup_thread_is_started_after_completion(self, mock_walk, mock_hist, mock_lib_cls, mock_cache_model):
        """The finally block must spawn a cleanup daemon thread."""
        from compresso.webserver.helpers import library_analysis

        mock_walk.return_value = [("/media", [], [])]
        mock_hist.return_value = {}
        mock_lib_cls.return_value.get_skip_codecs.return_value = []
        mock_cache_model.get_or_create.return_value = (MagicMock(), True)

        spawned = []
        original_thread = threading.Thread

        def tracking_thread(*args, **kwargs):
            t = original_thread(*args, **kwargs)
            spawned.append(t)
            return t

        info = {"status": "running", "progress": {"checked": 0, "total": 0}}
        with patch(ANALYSIS_MODULE + ".threading.Thread", side_effect=tracking_thread):
            library_analysis._run_analysis(1, "/media", info)

        # At least one thread is the cleanup thread (target=cleanup)
        assert len(spawned) >= 1


# ---------------------------------------------------------------------------
# _get_historical_savings (lines 294-329)
# ---------------------------------------------------------------------------


def _make_stats_mock(rows):
    """
    Build a mock CompressionStats class whose fluent query chain
    (.select().where().group_by()) ultimately yields the given row dicts.

    The peewee .where() call evaluates model-field expressions like
    ``CompressionStats.source_size > 0`` on the class itself.  To avoid
    MagicMock comparison errors we configure __gt__ / __lt__ on the field
    attributes to return a plain truthy sentinel instead.
    """
    mock_query = MagicMock()
    mock_query.dicts.return_value = rows

    # The fluent chain terminates at .group_by()
    chain = MagicMock()
    chain.where.return_value = chain
    chain.group_by.return_value = mock_query

    mock_stats = MagicMock()
    mock_stats.select.return_value = chain

    # Peewee field descriptors are accessed as class attributes; their
    # comparison operators produce Expression objects.  We make them
    # return a truthy MagicMock so the .where() call doesn't error out.
    for attr in ("source_size", "destination_size", "source_codec", "source_resolution", "id"):
        field_mock = MagicMock()
        field_mock.__gt__ = lambda self, other: MagicMock()
        field_mock.__lt__ = lambda self, other: MagicMock()
        setattr(mock_stats, attr, field_mock)

    return mock_stats


@pytest.mark.unittest
class TestGetHistoricalSavings:
    """Tests for the DB-backed savings aggregation query."""

    @patch(ANALYSIS_MODULE + ".CompressionStats")
    def test_returns_empty_dict_on_db_exception(self, mock_stats_model):
        """A DB error must be swallowed and return {}."""
        from compresso.webserver.helpers.library_analysis import _get_historical_savings

        mock_stats_model.select.side_effect = Exception("connection lost")
        result = _get_historical_savings()
        assert result == {}

    def test_savings_pct_calculated_correctly(self):
        """savings_pct = ((avg_source - avg_dest) / avg_source) * 100."""
        from compresso.webserver.helpers.library_analysis import _get_historical_savings

        rows = [
            {
                "source_codec": "H264",
                "source_resolution": "1920x1080",
                "avg_source": 1_000_000_000,
                "avg_dest": 600_000_000,
                "cnt": 10,
            }
        ]
        mock_stats = _make_stats_mock(rows)

        with patch(ANALYSIS_MODULE + ".CompressionStats", mock_stats):
            result = _get_historical_savings()

        assert ("h264", "1920x1080") in result
        entry = result[("h264", "1920x1080")]
        assert entry["avg_savings_pct"] == pytest.approx(40.0, abs=0.01)
        assert entry["count"] == 10

    def test_codec_lowercased_in_result_key(self):
        """Codec names from the DB should be normalised to lowercase."""
        from compresso.webserver.helpers.library_analysis import _get_historical_savings

        rows = [
            {
                "source_codec": "HEVC",
                "source_resolution": "3840x2160",
                "avg_source": 2_000_000_000,
                "avg_dest": 1_000_000_000,
                "cnt": 5,
            }
        ]
        mock_stats = _make_stats_mock(rows)

        with patch(ANALYSIS_MODULE + ".CompressionStats", mock_stats):
            result = _get_historical_savings()

        assert ("hevc", "3840x2160") in result

    def test_row_with_zero_avg_source_is_excluded(self):
        """Rows where avg_source=0 must be silently skipped."""
        from compresso.webserver.helpers.library_analysis import _get_historical_savings

        rows = [
            {
                "source_codec": "h264",
                "source_resolution": "1080p",
                "avg_source": 0,
                "avg_dest": 0,
                "cnt": 5,
            }
        ]
        mock_stats = _make_stats_mock(rows)

        with patch(ANALYSIS_MODULE + ".CompressionStats", mock_stats):
            result = _get_historical_savings()

        assert result == {}

    def test_row_with_zero_count_is_excluded(self):
        """Rows where cnt=0 must be silently skipped."""
        from compresso.webserver.helpers.library_analysis import _get_historical_savings

        rows = [
            {
                "source_codec": "h264",
                "source_resolution": "1080p",
                "avg_source": 500_000_000,
                "avg_dest": 200_000_000,
                "cnt": 0,
            }
        ]
        mock_stats = _make_stats_mock(rows)

        with patch(ANALYSIS_MODULE + ".CompressionStats", mock_stats):
            result = _get_historical_savings()

        assert result == {}

    def test_multiple_rows_produce_multiple_entries(self):
        """Two rows with different (codec, resolution) produce two entries."""
        from compresso.webserver.helpers.library_analysis import _get_historical_savings

        rows = [
            {
                "source_codec": "h264",
                "source_resolution": "1080p",
                "avg_source": 1_000_000,
                "avg_dest": 600_000,
                "cnt": 20,
            },
            {
                "source_codec": "mpeg2",
                "source_resolution": "720p",
                "avg_source": 2_000_000,
                "avg_dest": 500_000,
                "cnt": 8,
            },
        ]
        mock_stats = _make_stats_mock(rows)

        with patch(ANALYSIS_MODULE + ".CompressionStats", mock_stats):
            result = _get_historical_savings()

        assert len(result) == 2
        assert ("h264", "1080p") in result
        assert ("mpeg2", "720p") in result

    def test_none_codec_resolved_to_empty_string(self):
        """A NULL source_codec (None) in the DB should become an empty string key."""
        from compresso.webserver.helpers.library_analysis import _get_historical_savings

        rows = [
            {
                "source_codec": None,
                "source_resolution": "1080p",
                "avg_source": 1_000_000,
                "avg_dest": 700_000,
                "cnt": 3,
            }
        ]
        mock_stats = _make_stats_mock(rows)

        with patch(ANALYSIS_MODULE + ".CompressionStats", mock_stats):
            result = _get_historical_savings()

        assert ("", "1080p") in result


# ---------------------------------------------------------------------------
# _lookup_savings — extended edge-cases (builds on existing tests)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestLookupSavingsEdgeCases:
    """Edge-case tests for _lookup_savings not covered by the existing file."""

    def test_fallback_codec_low_confidence_when_total_count_lt_5(self):
        """Codec-only fallback with <5 total samples is 'low' confidence."""
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        historical = {
            ("vp9", "1280x720"): {"avg_savings_pct": 30.0, "count": 2},
            ("vp9", "1920x1080"): {"avg_savings_pct": 20.0, "count": 2},
        }
        pct, count, confidence = _lookup_savings(historical, "vp9", "3840x2160")
        # total_count = 4 → "low"
        assert confidence == "low"
        assert count == 4

    def test_exact_match_boundary_at_count_5_is_medium(self):
        """Exactly 5 samples → medium confidence."""
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        historical = {("av1", "1920x1080"): {"avg_savings_pct": 55.0, "count": 5}}
        _, _, confidence = _lookup_savings(historical, "av1", "1920x1080")
        assert confidence == "medium"

    def test_exact_match_boundary_at_count_20_is_high(self):
        """Exactly 20 samples → high confidence."""
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        historical = {("av1", "1920x1080"): {"avg_savings_pct": 55.0, "count": 20}}
        _, _, confidence = _lookup_savings(historical, "av1", "1920x1080")
        assert confidence == "high"

    def test_fallback_weighted_average_correctness(self):
        """Codec-only fallback must weight by sample count."""
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        historical = {
            ("h264", "480p"): {"avg_savings_pct": 10.0, "count": 10},  # 100 total
            ("h264", "1080p"): {"avg_savings_pct": 90.0, "count": 10},  # 900 total
        }
        pct, count, confidence = _lookup_savings(historical, "h264", "720p")
        # weighted: (10*10 + 90*10) / 20 = 1000/20 = 50
        assert pct == pytest.approx(50.0, abs=0.01)
        assert count == 20

    def test_empty_historical_returns_none_confidence(self):
        """_lookup_savings on an empty dict must return (0, 0, 'none')."""
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        pct, count, confidence = _lookup_savings({}, "h264", "1920x1080")
        assert (pct, count, confidence) == (0, 0, "none")


# ---------------------------------------------------------------------------
# get_analysis_status — JSON decode error branch (line 90-91)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetAnalysisStatusEdgeCases:
    @patch(ANALYSIS_MODULE + "._active_analyses", {})
    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    def test_invalid_json_in_cache_returns_empty_results(self, mock_cache_model):
        """Corrupt analysis_json should be silently replaced with {}."""
        from compresso.webserver.helpers.library_analysis import get_analysis_status

        mock_cache = MagicMock()
        mock_cache.analysis_json = "NOT-VALID-JSON{{{"
        mock_cache.file_count = 10
        mock_cache.version = 2
        mock_cache_model.get_or_none.return_value = mock_cache

        result = get_analysis_status(5)
        assert result["status"] == "complete"
        assert result["results"] == {}

    @patch(ANALYSIS_MODULE + "._active_analyses", {})
    @patch(ANALYSIS_MODULE + ".LibraryAnalysisCache")
    def test_none_analysis_json_returns_empty_results(self, mock_cache_model):
        """None analysis_json (e.g. NULL in DB) must not raise."""
        from compresso.webserver.helpers.library_analysis import get_analysis_status

        mock_cache = MagicMock()
        mock_cache.analysis_json = None
        mock_cache.file_count = 0
        mock_cache.version = 1
        mock_cache_model.get_or_none.return_value = mock_cache

        result = get_analysis_status(7)
        assert result["status"] == "complete"
        assert result["results"] == {}
