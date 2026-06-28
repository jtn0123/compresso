#!/usr/bin/env python3

"""
tests.integration.test_file_pipeline.py

End-to-end integration tests for the post-processor's file-movement pipeline —
the most data-loss-critical path in Compresso. These drive the *real*
PostProcessor.post_process_file() (with its real __copy_file, .compresso.part
staging, FileOperationTracker rollback, and source removal) against real files
on disk, asserting the invariants that protect a user's library:

  * a successful transcode replaces the original (rename or in-place);
  * the original source is NEVER deleted when the move fails.

Only the task model and the plugin handler are mocked (no plugins are enabled,
so Compresso's default file movement runs); all file operations are real. No
ffmpeg/video fixture is required — small byte payloads are enough to prove the
move/copy/delete behaviour.
"""

import os
import shutil
import tempfile
import threading
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


@pytest.mark.integrationtest
class TestFileMovePipeline:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp(prefix="compresso_integ_pipeline_")
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

    def _run(self, pp):
        with patch(f"{PP}.PluginsHandler") as MockPH:
            MockPH.return_value.get_enabled_plugin_modules_by_type.return_value = []
            pp.post_process_file()

    def test_replaces_source_when_extension_changes(self):
        """Transcode to a new container: dest is created, original is removed, no artifacts left."""
        source = self._write(os.path.join(self.library, "movie.mkv"), b"ORIGINAL-SOURCE")
        dest = os.path.join(self.library, "movie.mp4")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), b"TRANSCODED-OUTPUT")

        pp = _make_postprocessor()
        pp.current_task = _task(cache, source, dest)
        self._run(pp)

        assert os.path.exists(dest), "destination (new extension) must exist"
        with open(dest, "rb") as fh:
            assert fh.read() == b"TRANSCODED-OUTPUT"
        assert not os.path.exists(source), "original source must be removed after a rename-replace"
        # No staging/backup artifacts may survive a successful, committed run.
        assert not os.path.exists(dest + ".compresso.part")
        assert not os.path.exists(source + ".compresso.bak")
        # Cache directory is cleaned up.
        assert not os.path.exists(self.cache)

    def test_overwrites_source_in_place_same_name(self):
        """Same container/name: the original is replaced in place and never left as a stale copy."""
        path = os.path.join(self.library, "movie.mp4")
        self._write(path, b"ORIGINAL")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), b"NEW-ENCODED")

        pp = _make_postprocessor()
        # source abspath == destination abspath -> in-place replacement.
        pp.current_task = _task(cache, path, path)
        self._run(pp)

        assert os.path.exists(path), "in-place file must still exist"
        with open(path, "rb") as fh:
            assert fh.read() == b"NEW-ENCODED", "in-place file must hold the encoded content"
        assert not os.path.exists(path + ".compresso.bak")
        assert not os.path.exists(self.cache)

    def test_source_preserved_when_output_missing(self):
        """Defensive: task flagged success but the cache output is gone.

        The move must fail, the source must NOT be deleted, and no destination
        should be created. This is the invariant that guards against data loss.
        """
        source = self._write(os.path.join(self.library, "movie.mkv"), b"PRECIOUS-ORIGINAL")
        dest = os.path.join(self.library, "movie.mp4")
        missing_cache = os.path.join(self.cache, "does-not-exist.mp4")

        pp = _make_postprocessor()
        pp.event.set()  # skip the 1s diagnostic wait on a missing input file
        pp.current_task = _task(missing_cache, source, dest)
        self._run(pp)

        assert os.path.exists(source), "source must be preserved when the transcode output is missing"
        with open(source, "rb") as fh:
            assert fh.read() == b"PRECIOUS-ORIGINAL", "source content must be untouched"
        assert not os.path.exists(dest), "no destination should be created on failure"

    def test_preexisting_destination_restored_when_final_move_fails(self):
        """Overwrite scenario: if the final move fails after the existing dest was
        backed up, rollback must restore the original destination file."""
        # source != dest so a move (not in-place copy) is attempted, and dest pre-exists.
        source = self._write(os.path.join(self.library, "movie.mkv"), b"NEW-SOURCE")
        dest = self._write(os.path.join(self.library, "movie.mp4"), b"EXISTING-DESTINATION")
        cache = self._write(os.path.join(self.cache, "movie-out.mp4"), b"TRANSCODED")

        pp = _make_postprocessor()
        pp.current_task = _task(cache, source, dest)

        # Let the cache->part move and the safe_remove(dest) backup happen, then
        # fail the final part->dest rename so rollback must restore the dest backup.
        real_move = shutil.move

        def flaky_move(src, dst, *args, **kwargs):
            # The final rename moves the '.compresso.part' file into place; fail that one.
            if str(src).endswith(".compresso.part"):
                raise OSError("simulated disk failure during final rename")
            return real_move(src, dst, *args, **kwargs)

        with patch(f"{PP}.shutil.move", side_effect=flaky_move):
            self._run(pp)

        # The pre-existing destination must be restored from its backup.
        assert os.path.exists(dest), "pre-existing destination must be restored after rollback"
        with open(dest, "rb") as fh:
            assert fh.read() == b"EXISTING-DESTINATION", "destination content must be rolled back intact"
        # The source must not have been removed (movement was not successful).
        assert os.path.exists(source), "source must be preserved when the move fails"
        assert not os.path.exists(dest + ".compresso.bak"), "rollback should consume the backup"
