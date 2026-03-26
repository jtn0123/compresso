#!/usr/bin/env python3

"""
tests.unit.test_flow_features.py

Unit tests for the Flow pipeline features:
- Codec-based filtering (Feature A)
- Size guardrails (Feature B)
- Per-library replacement policy (Feature C)
- Library analysis helpers (Feature D)
- Library model flow field getters/setters

"""

import json
import os
import shutil
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest

# =====================================================================
# Helpers
# =====================================================================


def _make_postprocessor(abort_immediately=False):
    """Create a PostProcessor with mocked dependencies."""
    with (
        patch("compresso.libs.postprocessor.config.Config"),
        patch("compresso.libs.postprocessor.CompressoLogging") as mock_logging,
    ):
        mock_logger = MagicMock()
        mock_logging.get_logger.return_value = mock_logger

        from compresso.libs.postprocessor import PostProcessor

        data_queues = {}
        task_queue = MagicMock()
        event = threading.Event()
        pp = PostProcessor(data_queues, task_queue, event)
        if abort_immediately:
            pp.abort_flag.set()
        return pp


def _make_mock_task(
    task_type="local",
    success=True,
    library_id=1,
    task_id="task-1",
    source_abspath="/test/video.mkv",
    cache_path="/cache/output.mkv",
    dest_abspath=None,
    source_size=1000000,
):
    """Create a mock task with sensible defaults."""
    mock_task = MagicMock()
    mock_task.get_task_type.return_value = task_type
    mock_task.task.success = success
    mock_task.task.source_size = source_size
    mock_task.get_task_library_id.return_value = library_id
    mock_task.get_task_id.return_value = task_id
    mock_task.get_cache_path.return_value = cache_path
    mock_task.get_source_data.return_value = {
        "abspath": source_abspath,
        "basename": os.path.basename(source_abspath),
    }
    mock_task.get_source_abspath.return_value = source_abspath
    mock_task.get_destination_data.return_value = {
        "abspath": dest_abspath or source_abspath,
        "basename": os.path.basename(dest_abspath or source_abspath),
    }
    return mock_task


# =====================================================================
# Feature A: Library model — codec field getters/setters
# =====================================================================


@pytest.mark.unittest
class TestLibraryCodecFields:
    """Tests for Library.get/set_target_codecs() and get/set_skip_codecs()."""

    def _make_library(self):
        mock_model = MagicMock()
        mock_model.target_codecs = ""
        mock_model.skip_codecs = ""
        with patch("compresso.libs.library.Libraries") as mock_libs:
            mock_libs.get_or_none.return_value = mock_model
            from compresso.libs.library import Library

            lib = Library.__new__(Library)
            lib.model = mock_model
        return lib

    def test_get_target_codecs_empty(self):
        lib = self._make_library()
        assert lib.get_target_codecs() == []

    def test_set_target_codecs_list(self):
        lib = self._make_library()
        lib.set_target_codecs(["h264", "mpeg4"])
        assert json.loads(lib.model.target_codecs) == ["h264", "mpeg4"]

    def test_get_target_codecs_roundtrip(self):
        lib = self._make_library()
        lib.set_target_codecs(["h264", "vp8"])
        result = lib.get_target_codecs()
        assert result == ["h264", "vp8"]

    def test_set_target_codecs_empty_list(self):
        lib = self._make_library()
        lib.set_target_codecs([])
        assert lib.model.target_codecs == "[]"
        assert lib.get_target_codecs() == []

    def test_set_target_codecs_none(self):
        lib = self._make_library()
        lib.set_target_codecs(None)
        assert lib.model.target_codecs == ""

    def test_get_target_codecs_malformed_json(self):
        lib = self._make_library()
        lib.model.target_codecs = "not json"
        assert lib.get_target_codecs() == []

    def test_get_skip_codecs_empty(self):
        lib = self._make_library()
        assert lib.get_skip_codecs() == []

    def test_set_skip_codecs_list(self):
        lib = self._make_library()
        lib.set_skip_codecs(["hevc", "av1"])
        assert json.loads(lib.model.skip_codecs) == ["hevc", "av1"]

    def test_get_skip_codecs_roundtrip(self):
        lib = self._make_library()
        lib.set_skip_codecs(["hevc", "vp9"])
        result = lib.get_skip_codecs()
        assert result == ["hevc", "vp9"]

    def test_get_skip_codecs_malformed_json(self):
        lib = self._make_library()
        lib.model.skip_codecs = "{broken}"
        assert lib.get_skip_codecs() == []


# =====================================================================
# Feature B: Library model — guardrail field getters/setters
# =====================================================================


@pytest.mark.unittest
class TestLibraryGuardrailFields:
    """Tests for Library guardrail getters/setters with bounds validation."""

    def _make_library(self):
        mock_model = MagicMock()
        mock_model.size_guardrail_enabled = False
        mock_model.size_guardrail_min_pct = 20
        mock_model.size_guardrail_max_pct = 80
        from compresso.libs.library import Library

        lib = Library.__new__(Library)
        lib.model = mock_model
        return lib

    def test_guardrail_enabled_default_false(self):
        lib = self._make_library()
        assert lib.get_size_guardrail_enabled() is False

    def test_set_guardrail_enabled_true(self):
        lib = self._make_library()
        lib.set_size_guardrail_enabled(True)
        assert lib.model.size_guardrail_enabled is True

    def test_set_guardrail_enabled_truthy(self):
        lib = self._make_library()
        lib.set_size_guardrail_enabled(1)
        assert lib.model.size_guardrail_enabled is True

    def test_min_pct_default(self):
        lib = self._make_library()
        assert lib.get_size_guardrail_min_pct() == 20

    def test_set_min_pct_valid(self):
        lib = self._make_library()
        lib.set_size_guardrail_min_pct(30)
        assert lib.model.size_guardrail_min_pct == 30

    def test_set_min_pct_clamped_below(self):
        lib = self._make_library()
        lib.set_size_guardrail_min_pct(1)
        assert lib.model.size_guardrail_min_pct == 5

    def test_set_min_pct_clamped_above(self):
        lib = self._make_library()
        lib.set_size_guardrail_min_pct(99)
        assert lib.model.size_guardrail_min_pct == 95

    def test_max_pct_default(self):
        lib = self._make_library()
        assert lib.get_size_guardrail_max_pct() == 80

    def test_set_max_pct_valid(self):
        lib = self._make_library()
        lib.set_size_guardrail_max_pct(90)
        assert lib.model.size_guardrail_max_pct == 90

    def test_set_max_pct_clamped_below(self):
        lib = self._make_library()
        lib.set_size_guardrail_max_pct(30)
        assert lib.model.size_guardrail_max_pct == 50

    def test_set_max_pct_clamped_above(self):
        lib = self._make_library()
        lib.set_size_guardrail_max_pct(150)
        assert lib.model.size_guardrail_max_pct == 100


# =====================================================================
# Feature C: Library model — replacement policy getters/setters
# =====================================================================


@pytest.mark.unittest
class TestLibraryReplacementPolicy:
    """Tests for Library replacement policy getters/setters."""

    def _make_library(self):
        mock_model = MagicMock()
        mock_model.replacement_policy = ""
        from compresso.libs.library import Library

        lib = Library.__new__(Library)
        lib.model = mock_model
        return lib

    def test_default_empty(self):
        lib = self._make_library()
        assert lib.get_replacement_policy() == ""

    def test_set_replace(self):
        lib = self._make_library()
        lib.set_replacement_policy("replace")
        assert lib.model.replacement_policy == "replace"

    def test_set_approval_required(self):
        lib = self._make_library()
        lib.set_replacement_policy("approval_required")
        assert lib.model.replacement_policy == "approval_required"

    def test_set_keep_both(self):
        lib = self._make_library()
        lib.set_replacement_policy("keep_both")
        assert lib.model.replacement_policy == "keep_both"

    def test_set_empty_string_for_global_fallback(self):
        lib = self._make_library()
        lib.set_replacement_policy("")
        assert lib.model.replacement_policy == ""

    def test_set_none_becomes_empty(self):
        lib = self._make_library()
        lib.set_replacement_policy(None)
        assert lib.model.replacement_policy == ""

    def test_set_invalid_policy_becomes_empty(self):
        lib = self._make_library()
        lib.set_replacement_policy("delete_everything")
        assert lib.model.replacement_policy == ""

    def test_set_invalid_policy_case_sensitive(self):
        lib = self._make_library()
        lib.set_replacement_policy("Replace")
        assert lib.model.replacement_policy == ""


# =====================================================================
# Feature A: Codec pre-filter in FileTest
# =====================================================================


@pytest.mark.unittest
class TestCodecPreFilter:
    """Tests for the codec pre-filter in FileTest.should_file_be_added_to_task_list()."""

    def _make_filetest(self):
        with (
            patch("compresso.libs.filetest.config.Config"),
            patch("compresso.libs.filetest.CompressoLogging") as mock_logging,
            patch("compresso.libs.filetest.PluginsHandler"),
        ):
            mock_logging.get_logger.return_value = MagicMock()
            from compresso.libs.filetest import FileTest

            ft = FileTest.__new__(FileTest)
            ft.settings = MagicMock()
            ft.logger = MagicMock()
            ft.library_id = 1
            ft.plugin_handler = MagicMock()
            ft.plugin_modules = []
            ft.failed_paths = []
            ft.file_failed_in_history = MagicMock(return_value=False)
            ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        return ft

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_skip_codec_returns_false(self, mock_lib_class, mock_extract):
        """File with codec in skip list should be rejected."""
        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = []
        mock_lib.get_skip_codecs.return_value = ["hevc", "av1"]
        mock_lib_class.return_value = mock_lib

        mock_extract.return_value = {"codec": "hevc", "resolution": "1080p", "container": "mkv"}

        ft = self._make_filetest()
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mkv")
        assert result is False
        assert any(i["id"] == "codec_skip" for i in issues)

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_target_codec_not_matched_returns_false(self, mock_lib_class, mock_extract):
        """File with codec NOT in target list should be rejected."""
        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = ["h264", "mpeg4"]
        mock_lib.get_skip_codecs.return_value = []
        mock_lib_class.return_value = mock_lib

        mock_extract.return_value = {"codec": "hevc", "resolution": "1080p", "container": "mkv"}

        ft = self._make_filetest()
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mkv")
        assert result is False
        assert any(i["id"] == "codec_target" for i in issues)

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_target_codec_matched_continues(self, mock_lib_class, mock_extract):
        """File with codec in target list should NOT be rejected by the filter."""
        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = ["h264"]
        mock_lib.get_skip_codecs.return_value = []
        mock_lib_class.return_value = mock_lib

        mock_extract.return_value = {"codec": "h264", "resolution": "1080p", "container": "mkv"}

        ft = self._make_filetest()
        # With no plugins configured, the result should be None (no decision)
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mkv")
        # Not rejected by codec filter — result depends on plugins (None = no decision)
        assert result is None

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_no_codecs_configured_passes_through(self, mock_lib_class, mock_extract):
        """When no target/skip codecs configured, filter is skipped entirely."""
        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = []
        mock_lib.get_skip_codecs.return_value = []
        mock_lib_class.return_value = mock_lib

        ft = self._make_filetest()
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mkv")
        # extract_media_metadata should not even be called
        mock_extract.assert_not_called()
        assert result is None

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_codec_filter_case_insensitive(self, mock_lib_class, mock_extract):
        """Codec comparison should be case-insensitive."""
        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = ["H264"]
        mock_lib.get_skip_codecs.return_value = []
        mock_lib_class.return_value = mock_lib

        mock_extract.return_value = {"codec": "h264", "resolution": "1080p", "container": "mkv"}

        ft = self._make_filetest()
        result, _, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mkv")
        # Should pass — h264 matches H264 case-insensitively
        assert result is None

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_estimated_codec_stripped(self, mock_lib_class, mock_extract):
        """Estimated codec hint (e.g. 'h264 (estimated)') should have suffix stripped."""
        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = []
        mock_lib.get_skip_codecs.return_value = ["h264"]
        mock_lib_class.return_value = mock_lib

        mock_extract.return_value = {"codec": "h264 (estimated)", "resolution": "", "container": "mp4"}

        ft = self._make_filetest()
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mp4")
        assert result is False
        assert any(i["id"] == "codec_skip" for i in issues)

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata", side_effect=Exception("probe error"))
    @patch("compresso.libs.library.Library")
    def test_probe_failure_falls_through(self, mock_lib_class, mock_extract):
        """If ffprobe fails, the file should fall through to plugins."""
        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = ["h264"]
        mock_lib.get_skip_codecs.return_value = []
        mock_lib_class.return_value = mock_lib

        ft = self._make_filetest()
        result, _, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mkv")
        assert result is None  # Falls through to plugin loop

    @patch("compresso.libs.library.Library", side_effect=Exception("no library"))
    def test_library_lookup_failure_falls_through(self, mock_lib_class):
        """If Library() raises, the file should fall through to normal flow."""
        ft = self._make_filetest()
        result, _, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mkv")
        assert result is None

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_empty_codec_in_metadata_falls_through(self, mock_lib_class, mock_extract):
        """If extracted codec is empty, codec filter should not reject."""
        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = ["h264"]
        mock_lib.get_skip_codecs.return_value = []
        mock_lib_class.return_value = mock_lib

        mock_extract.return_value = {"codec": "", "resolution": "", "container": "mkv"}

        ft = self._make_filetest()
        result, _, _, _ = ft.should_file_be_added_to_task_list("/test/movie.mkv")
        # Empty codec should not match target filter — falls through
        assert result is None


# =====================================================================
# Feature B: Size guardrails in PostProcessor
# =====================================================================


@pytest.mark.unittest
class TestSizeGuardrails:
    """Tests for size guardrail check in _handle_processed_task()."""

    def _run_guardrail(self, source_size, output_size, min_pct=20, max_pct=80, guardrail_enabled=True, policy="replace"):
        """Helper: run _handle_processed_task with a guardrail config, return the task mock."""
        pp = _make_postprocessor()
        pp._stage_for_approval = MagicMock()
        pp._finalize_local_task = MagicMock()
        pp._finalize_local_task_keep_both = MagicMock()

        mock_lib = MagicMock()
        mock_lib.get_size_guardrail_enabled.return_value = guardrail_enabled
        mock_lib.get_size_guardrail_min_pct.return_value = min_pct
        mock_lib.get_size_guardrail_max_pct.return_value = max_pct
        mock_lib.get_replacement_policy.return_value = policy

        tmpdir = tempfile.mkdtemp(prefix="compresso_test_guardrail_")
        cache_file = os.path.join(tmpdir, "output.mkv")
        with open(cache_file, "wb") as f:
            f.write(b"x" * output_size)

        mock_task = _make_mock_task(source_size=source_size, cache_path=cache_file)
        pp.current_task = mock_task

        with (
            patch("compresso.libs.postprocessor.PluginsHandler"),
            patch("compresso.libs.postprocessor.Library", return_value=mock_lib),
        ):
            pp._handle_processed_task()

        shutil.rmtree(tmpdir, ignore_errors=True)
        return pp, mock_task

    def test_guardrail_rejects_too_small(self):
        """Output at 10% of source (below 20% min) should be rejected."""
        pp, task = self._run_guardrail(source_size=1000000, output_size=100000)
        assert task.task.success is False
        pp._finalize_local_task.assert_called_once()

    def test_guardrail_rejects_too_large(self):
        """Output at 90% of source (above 80% max) should be rejected."""
        pp, task = self._run_guardrail(source_size=1000000, output_size=900000)
        assert task.task.success is False
        pp._finalize_local_task.assert_called_once()

    def test_guardrail_passes_in_range(self):
        """Output at 50% of source (within 20-80%) should pass."""
        pp, task = self._run_guardrail(source_size=1000000, output_size=500000)
        assert task.task.success is True
        pp._finalize_local_task.assert_called_once()

    def test_guardrail_passes_at_min_boundary(self):
        """Output at exactly 20% should pass."""
        pp, task = self._run_guardrail(source_size=1000000, output_size=200000)
        assert task.task.success is True

    def test_guardrail_passes_at_max_boundary(self):
        """Output at exactly 80% should pass."""
        pp, task = self._run_guardrail(source_size=1000000, output_size=800000)
        assert task.task.success is True

    def test_guardrail_disabled_skips_check(self):
        """When guardrail is disabled, even a tiny output should pass."""
        pp, task = self._run_guardrail(
            source_size=1000000,
            output_size=100,
            guardrail_enabled=False,
        )
        assert task.task.success is True

    def test_guardrail_custom_thresholds(self):
        """Custom min=50, max=90: output at 40% should be rejected."""
        pp, task = self._run_guardrail(
            source_size=1000000,
            output_size=400000,
            min_pct=50,
            max_pct=90,
        )
        assert task.task.success is False

    def test_guardrail_zero_source_size_skips(self):
        """Zero source size should skip guardrail check (no division by zero)."""
        pp, task = self._run_guardrail(
            source_size=0,
            output_size=500000,
        )
        # Should pass because source_size=0 causes the guardrail to be skipped
        assert task.task.success is True

    def test_guardrail_missing_cache_file_skips(self):
        """If cache file doesn't exist, guardrail should be skipped."""
        pp = _make_postprocessor()
        pp._finalize_local_task = MagicMock()

        mock_lib = MagicMock()
        mock_lib.get_size_guardrail_enabled.return_value = True
        mock_lib.get_size_guardrail_min_pct.return_value = 20
        mock_lib.get_size_guardrail_max_pct.return_value = 80
        mock_lib.get_replacement_policy.return_value = "replace"

        mock_task = _make_mock_task(
            source_size=1000000,
            cache_path="/nonexistent/path/output.mkv",
        )
        pp.current_task = mock_task

        with (
            patch("compresso.libs.postprocessor.PluginsHandler"),
            patch("compresso.libs.postprocessor.Library", return_value=mock_lib),
        ):
            pp._handle_processed_task()

        # Should pass because cache path doesn't exist
        assert mock_task.task.success is True


# =====================================================================
# Feature C: Per-library replacement policy in PostProcessor
# =====================================================================


@pytest.mark.unittest
class TestReplacementPolicy:
    """Tests for per-library replacement policy in _handle_processed_task()."""

    def _run_with_policy(self, policy, success=True, global_approval=False):
        pp = _make_postprocessor()
        pp.settings.get_approval_required.return_value = global_approval
        pp._stage_for_approval = MagicMock()
        pp._finalize_local_task = MagicMock()
        pp._finalize_local_task_keep_both = MagicMock()

        mock_lib = MagicMock()
        mock_lib.get_size_guardrail_enabled.return_value = False
        mock_lib.get_replacement_policy.return_value = policy

        mock_task = _make_mock_task(success=success)
        pp.current_task = mock_task

        with (
            patch("compresso.libs.postprocessor.PluginsHandler"),
            patch("compresso.libs.postprocessor.Library", return_value=mock_lib),
        ):
            pp._handle_processed_task()

        return pp

    def test_policy_replace_calls_finalize(self):
        pp = self._run_with_policy("replace")
        pp._finalize_local_task.assert_called_once()
        pp._stage_for_approval.assert_not_called()
        pp._finalize_local_task_keep_both.assert_not_called()

    def test_policy_approval_required_stages(self):
        pp = self._run_with_policy("approval_required")
        pp._stage_for_approval.assert_called_once()
        pp._finalize_local_task.assert_not_called()

    def test_policy_keep_both_calls_keep_both(self):
        pp = self._run_with_policy("keep_both")
        pp._finalize_local_task_keep_both.assert_called_once()
        pp._stage_for_approval.assert_not_called()

    def test_empty_policy_falls_back_to_global_replace(self):
        """Empty policy + global approval=False → replace."""
        pp = self._run_with_policy("", global_approval=False)
        pp._finalize_local_task.assert_called_once()
        pp._stage_for_approval.assert_not_called()

    def test_empty_policy_falls_back_to_global_approval(self):
        """Empty policy + global approval=True → approval_required."""
        pp = self._run_with_policy("", global_approval=True)
        pp._stage_for_approval.assert_called_once()
        pp._finalize_local_task.assert_not_called()

    def test_failed_task_always_finalizes(self):
        """Failed task should always call _finalize_local_task regardless of policy."""
        pp = self._run_with_policy("approval_required", success=False)
        pp._finalize_local_task.assert_called_once()
        pp._stage_for_approval.assert_not_called()

    def test_failed_task_with_keep_both_still_finalizes(self):
        """Failed task with keep_both should finalize normally."""
        pp = self._run_with_policy("keep_both", success=False)
        pp._finalize_local_task.assert_called_once()
        pp._finalize_local_task_keep_both.assert_not_called()

    def test_library_lookup_failure_falls_back_to_global(self):
        """If Library() raises, should fall back to global setting."""
        pp = _make_postprocessor()
        pp.settings.get_approval_required.return_value = False
        pp._finalize_local_task = MagicMock()
        pp._stage_for_approval = MagicMock()

        mock_task = _make_mock_task(success=True)
        pp.current_task = mock_task

        with (
            patch("compresso.libs.postprocessor.PluginsHandler"),
            patch("compresso.libs.postprocessor.Library", side_effect=Exception("no lib")),
        ):
            pp._handle_processed_task()

        pp._finalize_local_task.assert_called_once()


# =====================================================================
# Feature C: _finalize_local_task_keep_both path adjustment
# =====================================================================


@pytest.mark.unittest
class TestFinalizeKeepBoth:
    """Tests for PostProcessor._finalize_local_task_keep_both()."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="compresso_test_keepboth_")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_adds_codec_suffix_when_same_path(self):
        """When dest == source, should rename dest to include codec suffix."""
        pp = _make_postprocessor()
        pp._finalize_local_task = MagicMock()

        source_path = os.path.join(self.tmpdir, "movie.mkv")
        cache_path = os.path.join(self.tmpdir, "cache_output.mkv")
        with open(cache_path, "w") as f:
            f.write("data")

        mock_task = MagicMock()
        mock_task.get_source_data.return_value = {"abspath": source_path, "basename": "movie.mkv"}
        mock_task.get_destination_data.return_value = {"abspath": source_path, "basename": "movie.mkv"}
        mock_task.get_cache_path.return_value = cache_path
        pp.current_task = mock_task

        with patch("compresso.libs.postprocessor.extract_media_metadata", return_value={"codec": "hevc"}):
            pp._finalize_local_task_keep_both()

        # Should have changed the destination path
        mock_task.set_destination_path.assert_called_once()
        new_path = mock_task.set_destination_path.call_args[0][0]
        assert "hevc" in new_path
        assert new_path.endswith(".mkv")
        pp._finalize_local_task.assert_called_once()

    def test_handles_collision(self):
        """When the codec-suffixed path already exists, should add a counter."""
        pp = _make_postprocessor()
        pp._finalize_local_task = MagicMock()

        source_path = os.path.join(self.tmpdir, "movie.mkv")
        existing_path = os.path.join(self.tmpdir, "movie.hevc.mkv")
        cache_path = os.path.join(self.tmpdir, "cache_output.mkv")
        with open(existing_path, "w") as f:
            f.write("existing")
        with open(cache_path, "w") as f:
            f.write("data")

        mock_task = MagicMock()
        mock_task.get_source_data.return_value = {"abspath": source_path, "basename": "movie.mkv"}
        mock_task.get_destination_data.return_value = {"abspath": source_path, "basename": "movie.mkv"}
        mock_task.get_cache_path.return_value = cache_path
        pp.current_task = mock_task

        with patch("compresso.libs.postprocessor.extract_media_metadata", return_value={"codec": "hevc"}):
            pp._finalize_local_task_keep_both()

        new_path = mock_task.set_destination_path.call_args[0][0]
        assert "hevc.1" in new_path

    def test_different_paths_no_rename(self):
        """When dest != source, should not rename (just finalize)."""
        pp = _make_postprocessor()
        pp._finalize_local_task = MagicMock()

        mock_task = MagicMock()
        mock_task.get_source_data.return_value = {"abspath": "/src/movie.mkv", "basename": "movie.mkv"}
        mock_task.get_destination_data.return_value = {"abspath": "/dst/movie.hevc.mkv", "basename": "movie.hevc.mkv"}
        mock_task.get_cache_path.return_value = "/cache/output.mkv"
        pp.current_task = mock_task

        pp._finalize_local_task_keep_both()

        mock_task.set_destination_path.assert_not_called()
        pp._finalize_local_task.assert_called_once()

    def test_metadata_failure_uses_transcoded(self):
        """If extract_media_metadata raises, should use 'transcoded' as suffix."""
        pp = _make_postprocessor()
        pp._finalize_local_task = MagicMock()

        source_path = os.path.join(self.tmpdir, "movie.mkv")
        cache_path = os.path.join(self.tmpdir, "cache.mkv")
        with open(cache_path, "w") as f:
            f.write("data")

        mock_task = MagicMock()
        mock_task.get_source_data.return_value = {"abspath": source_path, "basename": "movie.mkv"}
        mock_task.get_destination_data.return_value = {"abspath": source_path, "basename": "movie.mkv"}
        mock_task.get_cache_path.return_value = cache_path
        pp.current_task = mock_task

        with patch("compresso.libs.postprocessor.extract_media_metadata", side_effect=Exception("no probe")):
            pp._finalize_local_task_keep_both()

        new_path = mock_task.set_destination_path.call_args[0][0]
        assert "transcoded" in new_path


# =====================================================================
# Feature D: Library analysis helpers
# =====================================================================


@pytest.mark.unittest
class TestLibraryAnalysisLookupSavings:
    """Tests for library_analysis._lookup_savings()."""

    def _call(self, historical, codec, resolution):
        from compresso.webserver.helpers.library_analysis import _lookup_savings

        return _lookup_savings(historical, codec, resolution)

    def test_exact_match_high_confidence(self):
        historical = {
            ("h264", "1080p"): {"avg_savings_pct": 45.0, "count": 25},
        }
        pct, count, confidence = self._call(historical, "h264", "1080p")
        assert pct == 45.0
        assert count == 25
        assert confidence == "high"

    def test_exact_match_medium_confidence(self):
        historical = {
            ("h264", "1080p"): {"avg_savings_pct": 45.0, "count": 10},
        }
        _, _, confidence = self._call(historical, "h264", "1080p")
        assert confidence == "medium"

    def test_exact_match_low_confidence(self):
        historical = {
            ("h264", "1080p"): {"avg_savings_pct": 45.0, "count": 3},
        }
        _, _, confidence = self._call(historical, "h264", "1080p")
        assert confidence == "low"

    def test_codec_only_fallback(self):
        """When exact (codec, resolution) not found, falls back to codec average."""
        historical = {
            ("h264", "720p"): {"avg_savings_pct": 40.0, "count": 10},
            ("h264", "4K"): {"avg_savings_pct": 60.0, "count": 10},
        }
        pct, count, confidence = self._call(historical, "h264", "1080p")
        # Weighted average: (40*10 + 60*10) / 20 = 50
        assert pct == 50.0
        assert count == 20
        assert confidence == "medium"

    def test_no_data_returns_zero(self):
        """When no historical data at all, returns 0 savings and 'none' confidence."""
        pct, count, confidence = self._call({}, "h264", "1080p")
        assert pct == 0
        assert count == 0
        assert confidence == "none"

    def test_codec_fallback_low_count(self):
        """Codec fallback with < 5 samples should be 'low' confidence."""
        historical = {
            ("mpeg4", "720p"): {"avg_savings_pct": 55.0, "count": 3},
        }
        _, _, confidence = self._call(historical, "mpeg4", "1080p")
        assert confidence == "low"

    def test_different_codec_not_included_in_fallback(self):
        """Fallback should only use entries with matching codec."""
        historical = {
            ("hevc", "1080p"): {"avg_savings_pct": 20.0, "count": 50},
        }
        pct, count, confidence = self._call(historical, "h264", "1080p")
        assert pct == 0
        assert count == 0
        assert confidence == "none"


@pytest.mark.unittest
class TestLibraryAnalysisGetStatus:
    """Tests for library_analysis.get_analysis_status()."""

    @patch("compresso.webserver.helpers.library_analysis.LibraryAnalysisCache")
    @patch("compresso.webserver.helpers.library_analysis._active_analyses", {})
    def test_no_cache_returns_none_status(self, mock_cache_class):
        mock_cache_class.get_or_none.return_value = None
        from compresso.webserver.helpers.library_analysis import get_analysis_status

        result = get_analysis_status(99)
        assert result["status"] == "none"
        assert result["results"] is None

    @patch("compresso.webserver.helpers.library_analysis.LibraryAnalysisCache")
    @patch("compresso.webserver.helpers.library_analysis._active_analyses", {})
    def test_cached_result_returned(self, mock_cache_class):
        mock_cache = MagicMock()
        mock_cache.analysis_json = json.dumps({"groups": [], "total_files": 10})
        mock_cache.file_count = 10
        mock_cache.version = 3
        mock_cache_class.get_or_none.return_value = mock_cache
        from compresso.webserver.helpers.library_analysis import get_analysis_status

        result = get_analysis_status(1)
        assert result["status"] == "complete"
        assert result["version"] == 3
        assert result["results"]["total_files"] == 10

    @patch("compresso.webserver.helpers.library_analysis.LibraryAnalysisCache")
    def test_running_analysis_returns_progress(self, mock_cache_class):
        from compresso.webserver.helpers import library_analysis

        # Manually inject a running analysis
        old = dict(library_analysis._active_analyses)
        library_analysis._active_analyses[42] = {
            "status": "running",
            "progress": {"checked": 50, "total": 100},
        }
        try:
            result = library_analysis.get_analysis_status(42)
            assert result["status"] == "running"
            assert result["progress"]["checked"] == 50
        finally:
            library_analysis._active_analyses.clear()
            library_analysis._active_analyses.update(old)

    @patch("compresso.webserver.helpers.library_analysis.LibraryAnalysisCache")
    @patch("compresso.webserver.helpers.library_analysis._active_analyses", {})
    def test_malformed_cache_json_returns_empty(self, mock_cache_class):
        mock_cache = MagicMock()
        mock_cache.analysis_json = "not valid json"
        mock_cache.file_count = 0
        mock_cache.version = 1
        mock_cache_class.get_or_none.return_value = mock_cache
        from compresso.webserver.helpers.library_analysis import get_analysis_status

        result = get_analysis_status(1)
        assert result["status"] == "complete"
        assert result["results"] == {}


# =====================================================================
# Feature D: API endpoints
# =====================================================================


@pytest.mark.unittest
class TestCompressionApiAnalysis:
    """Tests for library-analysis API endpoints."""

    # We test at the handler level using the existing ApiTestBase pattern


@pytest.mark.unittest
class TestAnalysisApiEndpoints:
    """Endpoint-level tests for analysis and optimization-progress."""

    from tests.unit.api_test_base import ApiTestBase

    class _AnalysisApiTest(ApiTestBase):
        __test__ = True
        from compresso.webserver.api_v2.compression_api import ApiCompressionHandler

        handler_class = ApiCompressionHandler

    def test_start_analysis_missing_library_id(self):
        test = self._AnalysisApiTest("runTest")
        test.setUp()
        try:
            resp = test.post_json("/compression/library-analysis", {})
            assert resp.code in (400, 500)
        finally:
            test.tearDown()

    @patch("compresso.webserver.api_v2.compression_api.validate_library_exists", return_value=True)
    @patch("compresso.webserver.helpers.library_analysis.start_analysis")
    def test_start_analysis_success(self, mock_start, _mock_validate):
        mock_start.return_value = {"status": "running", "progress": {"checked": 0, "total": 100}}
        test = self._AnalysisApiTest("runTest")
        test.setUp()
        try:
            resp = test.post_json("/compression/library-analysis", {"library_id": 1})
            assert resp.code == 200
            data = test.parse_response(resp)
            assert data["status"] == "running"
        finally:
            test.tearDown()

    @patch("compresso.webserver.api_v2.compression_api.validate_library_exists", return_value=True)
    @patch("compresso.webserver.helpers.library_analysis.get_analysis_status")
    def test_get_analysis_status_success(self, mock_status, _mock_validate):
        mock_status.return_value = {
            "status": "complete",
            "progress": {"checked": 100, "total": 100},
            "version": 2,
            "results": {"groups": [], "total_files": 100},
        }
        test = self._AnalysisApiTest("runTest")
        test.setUp()
        try:
            resp = test.post_json("/compression/library-analysis/status", {"library_id": 1})
            assert resp.code == 200
            data = test.parse_response(resp)
            assert data["status"] == "complete"
            assert data["version"] == 2
        finally:
            test.tearDown()

    @patch("compresso.libs.unmodels.compressionstats.CompressionStats")
    @patch("compresso.libs.unmodels.libraryanalysiscache.LibraryAnalysisCache")
    def test_optimization_progress(self, mock_cache_class, mock_stats_class):
        mock_stats_class.select.return_value.count.return_value = 50

        mock_cache_entry = MagicMock()
        mock_cache_entry.file_count = 200
        mock_cache_class.select.return_value = [mock_cache_entry]

        # Patch the unmodels namespace so the inline import finds mocks
        with patch.dict(
            "compresso.libs.unmodels.__dict__",
            {
                "CompressionStats": mock_stats_class,
                "LibraryAnalysisCache": mock_cache_class,
            },
        ):
            test = self._AnalysisApiTest("runTest")
            test.setUp()
            try:
                resp = test.get_json("/compression/optimization-progress")
                assert resp.code == 200
                data = test.parse_response(resp)
                assert data["processed_files"] == 50
                assert data["total_files"] == 200
                assert data["percent"] == 25.0
            finally:
                test.tearDown()

    @patch("compresso.libs.unmodels.compressionstats.CompressionStats")
    @patch("compresso.libs.unmodels.libraryanalysiscache.LibraryAnalysisCache")
    def test_optimization_progress_no_analysis(self, mock_cache_class, mock_stats_class):
        """When no analysis cache exists, total_files falls back to processed count."""
        mock_stats_class.select.return_value.count.return_value = 30
        mock_cache_class.select.return_value = []

        with patch.dict(
            "compresso.libs.unmodels.__dict__",
            {
                "CompressionStats": mock_stats_class,
                "LibraryAnalysisCache": mock_cache_class,
            },
        ):
            test = self._AnalysisApiTest("runTest")
            test.setUp()
            try:
                resp = test.get_json("/compression/optimization-progress")
                assert resp.code == 200
                data = test.parse_response(resp)
                assert data["total_files"] == 30
                assert data["processed_files"] == 30
                assert data["percent"] == 100.0
            finally:
                test.tearDown()


# =====================================================================
# Feature B+C combined: guardrail rejection with different policies
# =====================================================================


@pytest.mark.unittest
class TestGuardrailWithPolicy:
    """Guardrail rejection should override all policies."""

    def _run(self, policy, output_pct):
        pp = _make_postprocessor()
        pp.settings.get_approval_required.return_value = False
        pp._stage_for_approval = MagicMock()
        pp._finalize_local_task = MagicMock()
        pp._finalize_local_task_keep_both = MagicMock()

        mock_lib = MagicMock()
        mock_lib.get_size_guardrail_enabled.return_value = True
        mock_lib.get_size_guardrail_min_pct.return_value = 20
        mock_lib.get_size_guardrail_max_pct.return_value = 80
        mock_lib.get_replacement_policy.return_value = policy

        tmpdir = tempfile.mkdtemp(prefix="compresso_test_combined_")
        cache_file = os.path.join(tmpdir, "output.mkv")
        source_size = 1000000
        output_size = int(source_size * output_pct / 100)
        with open(cache_file, "wb") as f:
            f.write(b"x" * output_size)

        mock_task = _make_mock_task(source_size=source_size, cache_path=cache_file)
        pp.current_task = mock_task

        with (
            patch("compresso.libs.postprocessor.PluginsHandler"),
            patch("compresso.libs.postprocessor.Library", return_value=mock_lib),
        ):
            pp._handle_processed_task()

        shutil.rmtree(tmpdir, ignore_errors=True)
        return pp, mock_task

    def test_guardrail_rejects_even_with_approval_policy(self):
        """Output too small with approval_required policy → rejected, finalized (not staged)."""
        pp, task = self._run("approval_required", output_pct=5)
        assert task.task.success is False
        pp._finalize_local_task.assert_called_once()
        pp._stage_for_approval.assert_not_called()

    def test_guardrail_rejects_even_with_keep_both_policy(self):
        """Output too large with keep_both policy → rejected, finalized normally."""
        pp, task = self._run("keep_both", output_pct=95)
        assert task.task.success is False
        pp._finalize_local_task.assert_called_once()
        pp._finalize_local_task_keep_both.assert_not_called()

    def test_guardrail_passes_then_approval(self):
        """Output in range with approval_required → staged for approval."""
        pp, task = self._run("approval_required", output_pct=50)
        assert task.task.success is True
        pp._stage_for_approval.assert_called_once()

    def test_guardrail_passes_then_keep_both(self):
        """Output in range with keep_both → keep_both finalize."""
        pp, task = self._run("keep_both", output_pct=50)
        assert task.task.success is True
        pp._finalize_local_task_keep_both.assert_called_once()


# =====================================================================
# Settings helper: save_library_config with flow fields
# =====================================================================


@pytest.mark.unittest
class TestSettingsHelperFlowFields:
    """Tests for save_library_config() persisting flow fields."""

    @patch("compresso.webserver.helpers.settings.PluginExecutor")
    @patch("compresso.webserver.helpers.settings.plugins")
    @patch("compresso.webserver.helpers.settings.Library")
    @patch("compresso.webserver.helpers.settings.logger")
    def test_saves_codec_fields(self, mock_logger, mock_lib_class, mock_plugins, mock_pe):
        mock_lib = MagicMock()
        mock_lib.get_name.return_value = "Test"
        mock_lib.get_path.return_value = "/test"
        mock_lib.get_locked.return_value = False
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_scanner.return_value = False
        mock_lib.get_enable_inotify.return_value = False
        mock_lib.get_priority_score.return_value = 0
        mock_lib.get_tags.return_value = []
        mock_lib.save.return_value = True
        mock_lib_class.return_value = mock_lib
        mock_plugins.get_plugin_types_with_flows.return_value = []

        from compresso.webserver.helpers.settings import save_library_config

        save_library_config(
            1,
            library_config={
                "target_codecs": ["h264", "mpeg4"],
                "skip_codecs": ["hevc"],
            },
        )

        mock_lib.set_target_codecs.assert_called_once_with(["h264", "mpeg4"])
        mock_lib.set_skip_codecs.assert_called_once_with(["hevc"])

    @patch("compresso.webserver.helpers.settings.PluginExecutor")
    @patch("compresso.webserver.helpers.settings.plugins")
    @patch("compresso.webserver.helpers.settings.Library")
    @patch("compresso.webserver.helpers.settings.logger")
    def test_saves_guardrail_fields(self, mock_logger, mock_lib_class, mock_plugins, mock_pe):
        mock_lib = MagicMock()
        mock_lib.get_name.return_value = "Test"
        mock_lib.get_path.return_value = "/test"
        mock_lib.get_locked.return_value = False
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_scanner.return_value = False
        mock_lib.get_enable_inotify.return_value = False
        mock_lib.get_priority_score.return_value = 0
        mock_lib.get_tags.return_value = []
        mock_lib.save.return_value = True
        mock_lib_class.return_value = mock_lib
        mock_plugins.get_plugin_types_with_flows.return_value = []

        from compresso.webserver.helpers.settings import save_library_config

        save_library_config(
            1,
            library_config={
                "size_guardrail_enabled": True,
                "size_guardrail_min_pct": 30,
                "size_guardrail_max_pct": 90,
            },
        )

        mock_lib.set_size_guardrail_enabled.assert_called_once_with(True)
        mock_lib.set_size_guardrail_min_pct.assert_called_once_with(30)
        mock_lib.set_size_guardrail_max_pct.assert_called_once_with(90)

    @patch("compresso.webserver.helpers.settings.PluginExecutor")
    @patch("compresso.webserver.helpers.settings.plugins")
    @patch("compresso.webserver.helpers.settings.Library")
    @patch("compresso.webserver.helpers.settings.logger")
    def test_saves_replacement_policy(self, mock_logger, mock_lib_class, mock_plugins, mock_pe):
        mock_lib = MagicMock()
        mock_lib.get_name.return_value = "Test"
        mock_lib.get_path.return_value = "/test"
        mock_lib.get_locked.return_value = False
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_scanner.return_value = False
        mock_lib.get_enable_inotify.return_value = False
        mock_lib.get_priority_score.return_value = 0
        mock_lib.get_tags.return_value = []
        mock_lib.save.return_value = True
        mock_lib_class.return_value = mock_lib
        mock_plugins.get_plugin_types_with_flows.return_value = []

        from compresso.webserver.helpers.settings import save_library_config

        save_library_config(
            1,
            library_config={
                "replacement_policy": "keep_both",
            },
        )

        mock_lib.set_replacement_policy.assert_called_once_with("keep_both")

    @patch("compresso.webserver.helpers.settings.PluginExecutor")
    @patch("compresso.webserver.helpers.settings.plugins")
    @patch("compresso.webserver.helpers.settings.Library")
    @patch("compresso.webserver.helpers.settings.logger")
    def test_omitted_flow_fields_not_overwritten(self, mock_logger, mock_lib_class, mock_plugins, mock_pe):
        """If flow fields are not in library_config, existing values should be preserved."""
        mock_lib = MagicMock()
        mock_lib.get_name.return_value = "Test"
        mock_lib.get_path.return_value = "/test"
        mock_lib.get_locked.return_value = False
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_scanner.return_value = False
        mock_lib.get_enable_inotify.return_value = False
        mock_lib.get_priority_score.return_value = 0
        mock_lib.get_tags.return_value = []
        mock_lib.save.return_value = True
        mock_lib_class.return_value = mock_lib
        mock_plugins.get_plugin_types_with_flows.return_value = []

        from compresso.webserver.helpers.settings import save_library_config

        save_library_config(
            1,
            library_config={
                "name": "Updated Name",
            },
        )

        # Flow setters should NOT be called since fields were omitted
        mock_lib.set_target_codecs.assert_not_called()
        mock_lib.set_skip_codecs.assert_not_called()
        mock_lib.set_size_guardrail_enabled.assert_not_called()
        mock_lib.set_replacement_policy.assert_not_called()


# =====================================================================
# Compression schemas validation
# =====================================================================


@pytest.mark.unittest
class TestCompressionSchemas:
    """Tests for new Marshmallow schemas."""

    def test_library_analysis_request_schema_requires_library_id(self):
        from compresso.webserver.api_v2.schema.compression_schemas import LibraryAnalysisRequestSchema

        schema = LibraryAnalysisRequestSchema()
        errors = schema.validate({})
        assert "library_id" in errors

    def test_library_analysis_request_schema_valid(self):
        from compresso.webserver.api_v2.schema.compression_schemas import LibraryAnalysisRequestSchema

        schema = LibraryAnalysisRequestSchema()
        result = schema.load({"library_id": 1})
        assert result["library_id"] == 1

    def test_optimization_progress_schema_loads(self):
        from compresso.webserver.api_v2.schema.compression_schemas import OptimizationProgressSchema

        schema = OptimizationProgressSchema()
        data = schema.dump(
            {
                "success": True,
                "total_files": 100,
                "processed_files": 50,
                "percent": 50.0,
            }
        )
        assert data["percent"] == 50.0

    def test_library_analysis_status_schema_allows_null_results(self):
        from compresso.webserver.api_v2.schema.compression_schemas import LibraryAnalysisStatusSchema

        schema = LibraryAnalysisStatusSchema()
        data = schema.dump(
            {
                "success": True,
                "status": "none",
                "progress": {},
                "version": 0,
                "results": None,
            }
        )
        assert data["results"] is None


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
