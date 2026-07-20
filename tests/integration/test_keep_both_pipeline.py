#!/usr/bin/env python3

"""
tests.integration.test_keep_both_pipeline.py

Integration tests for the 'keep_both' replacement policy — the audit-verified
data-loss path (grade report finding B1). These drive the *real*
PostProcessor._finalize_local_task_keep_both() glue and the *real*
Task.set_destination_path()/get_destination_data() implementation against real
files on disk. A Mock-based task would hide a missing Task method (that is
exactly how the original bug shipped), so the Task object here is the real
class with only its config/logging dependencies stubbed.

The invariant under test: after a keep_both finalization, BOTH files exist —
the untouched original and the encoded output alongside it.
"""

import os
import shutil
import tempfile
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

PP = "compresso.libs.postprocessor"


def _make_postprocessor():
    """Create a PostProcessor with config + logging mocked, everything else real."""
    with (
        patch(f"{PP}.config.Config"),
        patch(f"{PP}.CompressoLogging") as mock_logging,
    ):
        mock_logging.get_logger.return_value = MagicMock()
        from compresso.libs.postprocessor import PostProcessor

        pp = PostProcessor({}, MagicMock(), threading.Event())
    pp.logger = MagicMock()
    return pp


def _real_task(cache_path, source_abspath, task_id=1):
    """A REAL Task instance (not a Mock) with a lightweight model row."""
    with (
        patch("compresso.libs.task.config.Config"),
        patch("compresso.libs.task.CompressoLogging"),
    ):
        from compresso.libs.task import Task

        t = Task()
    t.task = SimpleNamespace(
        id=task_id,
        abspath=source_abspath,
        cache_path=cache_path,
        library_id=1,
        success=True,
        type="local",
    )
    return t


@pytest.mark.integrationtest
class TestKeepBothPipeline:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix="compresso_integ_keep_both_")
        self.library = os.path.join(self.tmp, "library")
        # The cache dir name MUST contain 'compresso_file_conversion' or the
        # post-processor refuses to clean it up (a deliberate safety guard).
        self.cache = os.path.join(self.tmp, "compresso_file_conversion-test")
        os.makedirs(self.library)
        os.makedirs(self.cache)

    def teardown_method(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def _write(path, content):
        with open(path, "wb") as fh:
            fh.write(content)
        return path

    def _run_keep_both(self, pp):
        """Run the real keep_both glue with the file-movement stage as finalization.

        _finalize_local_task normally also persists history/metadata (DB); the
        movement stage is the part that can destroy user data, so finalization
        is narrowed to the real post_process_file() with no plugins enabled.
        """
        with (
            patch(f"{PP}.PluginsHandler") as MockPH,
            patch(f"{PP}.extract_media_metadata", return_value={"codec": "hevc"}),
            patch.object(pp, "_finalize_local_task", side_effect=lambda: pp.post_process_file()),
        ):
            MockPH.return_value.get_enabled_plugin_modules_by_type.return_value = []
            pp._finalize_local_task_keep_both()

    def test_keep_both_preserves_original_and_writes_output_alongside(self):
        """Same-name transcode with keep_both: original survives, output gains codec suffix."""
        source = self._write(os.path.join(self.library, "movie.mp4"), b"PRECIOUS-ORIGINAL")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), b"TRANSCODED-OUTPUT")

        pp = _make_postprocessor()
        pp.current_task = _real_task(cache, source)
        self._run_keep_both(pp)

        expected_output = os.path.join(self.library, "movie.hevc.mp4")
        assert os.path.exists(source), "keep_both must NEVER remove the original file"
        with open(source, "rb") as fh:
            assert fh.read() == b"PRECIOUS-ORIGINAL", "original content must be untouched"
        assert os.path.exists(expected_output), "encoded output must be written alongside the original"
        with open(expected_output, "rb") as fh:
            assert fh.read() == b"TRANSCODED-OUTPUT"
        # The keep-source flag must not leak into subsequent (non-keep_both) tasks
        assert pp._keep_source_file is False

    def test_keep_both_appends_counter_when_suffixed_name_exists(self):
        """A pre-existing codec-suffixed file must not be overwritten either."""
        source = self._write(os.path.join(self.library, "movie.mp4"), b"ORIGINAL")
        prior = self._write(os.path.join(self.library, "movie.hevc.mp4"), b"PRIOR-KEEP-BOTH-RUN")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), b"NEW-TRANSCODE")

        pp = _make_postprocessor()
        pp.current_task = _real_task(cache, source)
        self._run_keep_both(pp)

        expected_output = os.path.join(self.library, "movie.hevc.1.mp4")
        assert os.path.exists(source)
        with open(source, "rb") as fh:
            assert fh.read() == b"ORIGINAL"
        with open(prior, "rb") as fh:
            assert fh.read() == b"PRIOR-KEEP-BOTH-RUN", "earlier keep_both output must not be overwritten"
        assert os.path.exists(expected_output), "new output must gain a de-duplicating counter suffix"
        with open(expected_output, "rb") as fh:
            assert fh.read() == b"NEW-TRANSCODE"

    def test_keep_both_preserves_original_on_container_change(self):
        """Container change (mkv -> mp4): destination already differs from the
        source, which would normally trigger source removal — keep_both must
        suppress it."""
        source = self._write(os.path.join(self.library, "movie.mkv"), b"ORIGINAL-MKV")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), b"TRANSCODED-MP4")

        pp = _make_postprocessor()
        pp.current_task = _real_task(cache, source)
        self._run_keep_both(pp)

        expected_output = os.path.join(self.library, "movie.mp4")
        assert os.path.exists(source), "keep_both must preserve the original on container change"
        with open(source, "rb") as fh:
            assert fh.read() == b"ORIGINAL-MKV"
        assert os.path.exists(expected_output)
        with open(expected_output, "rb") as fh:
            assert fh.read() == b"TRANSCODED-MP4"
