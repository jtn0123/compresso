#!/usr/bin/env python3

"""
tests.integration.test_file_pipeline_failures.py

Failure-path companion to ``test_file_pipeline.py``. That module proves the
happy paths and two rollback cases; this one drives the real
``PostProcessor.post_process_file()`` through the ways a move goes wrong on a
real machine — the disk fills up, the destination is not writable, the user
deletes the source mid-encode, the plugin writes something that is not a file.

The invariant under test is always the same and always the one that matters for
a tool that replaces people's media: **when the move cannot complete, the
original file is still there, unchanged, and no partial output is left behind
pretending to be a finished encode.**

Errors are injected by patching the file primitives rather than by using real
permissions, so the suite behaves identically on Linux, macOS, and Windows.
"""

import errno
import os
import shutil
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest

PP = "compresso.libs.postprocessor"

ORIGINAL_BYTES = b"PRECIOUS-ORIGINAL-CONTENT"
ENCODED_BYTES = b"NEWLY-ENCODED-OUTPUT"


def _make_postprocessor():
    """Create a PostProcessor with config + logging mocked, everything else real."""
    with (
        patch(f"{PP}.config.Config"),
        patch(f"{PP}.CompressoLogging") as mock_logging,
    ):
        mock_logging.get_logger.return_value = MagicMock()
        from compresso.libs.postprocessor import PostProcessor

        postprocessor = PostProcessor({}, MagicMock(), threading.Event())
    postprocessor.logger = MagicMock()
    return postprocessor


def _task(cache_path, source_abspath, dest_abspath, task_id=1):
    """A mock current_task exposing just what post_process_file (local) needs."""
    task = MagicMock()
    task.get_task_library_id.return_value = 1
    task.get_cache_path.return_value = cache_path
    task.get_source_data.return_value = {"abspath": source_abspath, "basename": os.path.basename(source_abspath)}
    task.get_destination_data.return_value = {"abspath": dest_abspath, "basename": os.path.basename(dest_abspath)}
    task.get_task_id.return_value = task_id
    task.get_task_type.return_value = "local"
    task.get_task_success.return_value = True
    task.get_start_time.return_value = 0
    task.get_finish_time.return_value = 1
    task.task.success = True
    return task


def _disk_full(*_args, **_kwargs):
    raise OSError(errno.ENOSPC, "No space left on device")


@pytest.mark.integrationtest
class TestFileMoveFailurePaths:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix="compresso_integ_failures_")
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
        with open(path, "wb") as handle:
            handle.write(content)
        return path

    def _run(self, postprocessor):
        """Run post_process_file() with no enabled plugins (default file movement)."""
        with patch(f"{PP}.PluginsHandler") as mock_plugins:
            mock_plugins.return_value.get_enabled_plugin_modules_by_type.return_value = []
            postprocessor.post_process_file()

    def _assert_source_intact(self, source):
        assert os.path.exists(source), "the original must survive a failed move"
        with open(source, "rb") as handle:
            assert handle.read() == ORIGINAL_BYTES, "the original's content must be untouched"

    def _assert_no_artifacts(self, source, dest):
        assert not os.path.exists(f"{dest}.compresso.part"), "no staging file may be orphaned beside the destination"
        assert not os.path.exists(f"{source}.compresso.bak"), "no backup file may be left behind"

    def test_disk_full_during_staging_leaves_the_original_alone(self):
        """ENOSPC while staging the encode: nothing is destroyed, nothing is published."""
        source = self._write(os.path.join(self.library, "movie.mkv"), ORIGINAL_BYTES)
        dest = os.path.join(self.library, "movie.mp4")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), ENCODED_BYTES)

        postprocessor = _make_postprocessor()
        postprocessor.current_task = _task(cache, source, dest)

        with patch(f"{PP}.shutil.move", side_effect=_disk_full):
            self._run(postprocessor)

        self._assert_source_intact(source)
        assert not os.path.exists(dest), "a failed staging copy must not publish a destination"
        self._assert_no_artifacts(source, dest)

    def test_destination_not_writable_leaves_the_original_alone(self):
        """A read-only destination directory must not cost the user their source."""
        source = self._write(os.path.join(self.library, "movie.mkv"), ORIGINAL_BYTES)
        dest = os.path.join(self.library, "movie.mp4")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), ENCODED_BYTES)

        postprocessor = _make_postprocessor()
        postprocessor.current_task = _task(cache, source, dest)

        def denied(*_args, **_kwargs):
            raise PermissionError(errno.EACCES, "Permission denied")

        with patch(f"{PP}.shutil.move", side_effect=denied):
            self._run(postprocessor)

        self._assert_source_intact(source)
        assert not os.path.exists(dest)
        self._assert_no_artifacts(source, dest)

    def test_failure_after_staging_restores_the_source(self):
        """The encode is staged, then the final rename fails.

        The source was already moved aside at this point, so recovery — not just
        "don't delete" — is what protects the library.
        """
        source = self._write(os.path.join(self.library, "movie.mkv"), ORIGINAL_BYTES)
        dest = os.path.join(self.library, "movie.mp4")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), ENCODED_BYTES)

        postprocessor = _make_postprocessor()
        postprocessor.current_task = _task(cache, source, dest)

        real_move = shutil.move

        def fail_final_rename(src, dst, *args, **kwargs):
            if str(src).endswith(".compresso.part"):
                raise OSError(errno.EIO, "simulated I/O error publishing the encode")
            return real_move(src, dst, *args, **kwargs)

        with patch(f"{PP}.shutil.move", side_effect=fail_final_rename):
            self._run(postprocessor)

        assert not os.path.exists(dest), "a half-published encode must not be left as the destination"
        self._assert_no_artifacts(source, dest)
        assert os.path.exists(source) or os.path.exists(cache), (
            "the encode must remain recoverable from either the source path or the task cache"
        )

    def test_source_deleted_during_encode_does_not_publish_a_phantom_destination(self):
        """The user deletes the file while it is being encoded."""
        source = os.path.join(self.library, "movie.mkv")
        dest = os.path.join(self.library, "movie.mp4")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), ENCODED_BYTES)

        postprocessor = _make_postprocessor()
        postprocessor.event.set()  # skip the diagnostic wait on a missing input
        postprocessor.current_task = _task(cache, source, dest)
        self._run(postprocessor)

        # Compresso may legitimately publish the finished encode here, but it must
        # never leave a partial staging file masquerading as the result.
        assert not os.path.exists(f"{dest}.compresso.part")
        if os.path.exists(dest):
            with open(dest, "rb") as handle:
                assert handle.read() == ENCODED_BYTES, "a published destination must hold the complete encode"

    def test_directory_where_the_encode_should_be_fails_safely(self):
        """A plugin leaves a directory at the cache path instead of a file."""
        source = self._write(os.path.join(self.library, "movie.mkv"), ORIGINAL_BYTES)
        dest = os.path.join(self.library, "movie.mp4")
        cache = os.path.join(self.cache, "movie-out.mp4")
        os.makedirs(cache)

        postprocessor = _make_postprocessor()
        postprocessor.event.set()
        postprocessor.current_task = _task(cache, source, dest)
        self._run(postprocessor)

        self._assert_source_intact(source)
        assert not os.path.isfile(dest), "a directory must never be published as an encoded file"

    def test_retry_after_a_failed_move_succeeds_cleanly(self):
        """A transient failure must leave the task retryable, not wedged."""
        source = self._write(os.path.join(self.library, "movie.mkv"), ORIGINAL_BYTES)
        dest = os.path.join(self.library, "movie.mp4")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), ENCODED_BYTES)

        failing = _make_postprocessor()
        failing.current_task = _task(cache, source, dest)
        with patch(f"{PP}.shutil.move", side_effect=_disk_full):
            self._run(failing)

        self._assert_source_intact(source)
        assert os.path.exists(cache), "the encode must survive in the cache so the task can be retried"

        # The disk frees up and the same task runs again.
        retry = _make_postprocessor()
        retry.current_task = _task(cache, source, dest)
        self._run(retry)

        assert os.path.exists(dest), "the retry must publish the encode"
        with open(dest, "rb") as handle:
            assert handle.read() == ENCODED_BYTES
        assert not os.path.exists(source), "the retry must complete the replacement"
        self._assert_no_artifacts(source, dest)
