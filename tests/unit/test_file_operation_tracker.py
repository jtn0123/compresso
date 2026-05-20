#!/usr/bin/env python3

"""
tests.unit.test_file_operation_tracker.py

Unit tests for compresso.libs.file_operation_tracker.FileOperationTracker:
- safe_remove: backs up then deletes the original
- commit: clears backups after successful processing
- rollback: restores files from backups in reverse order
- rollback handles per-file failures and continues with remaining entries
"""

import logging
import os
from unittest.mock import MagicMock

import pytest

from compresso.libs.file_operation_tracker import FileOperationTracker


@pytest.fixture
def logger():
    return logging.getLogger("compresso_test_file_op_tracker")


@pytest.fixture
def tracker(logger):
    return FileOperationTracker(logger)


@pytest.mark.unittest
class TestSafeRemove:
    def test_safe_remove_creates_backup_and_removes_original(self, tracker, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("hello world")

        tracker.safe_remove(str(f))

        # The original file should be gone
        assert not f.exists()
        # A backup with the .compresso.bak suffix should exist with the original contents
        backup = tmp_path / "data.txt.compresso.bak"
        assert backup.exists()
        assert backup.read_text() == "hello world"
        # And the tracker should remember the operation
        assert tracker._backups == [(str(backup), str(f))]

    def test_safe_remove_missing_file_is_noop(self, tracker, tmp_path):
        ghost = tmp_path / "does_not_exist.txt"
        # Should not raise, should not register anything
        tracker.safe_remove(str(ghost))
        assert tracker._backups == []

    def test_safe_remove_logs_and_reraises_on_copy_failure(self, tmp_path, logger):
        f = tmp_path / "locked.txt"
        f.write_text("payload")

        warn = MagicMock()
        log = MagicMock(warning=warn, error=MagicMock(), info=MagicMock())

        tracker = FileOperationTracker(log)

        # Force shutil.copy2 to fail
        from compresso.libs import file_operation_tracker as mod

        original_copy = mod.shutil.copy2
        mod.shutil.copy2 = MagicMock(side_effect=OSError("disk full"))
        try:
            with pytest.raises(OSError):
                tracker.safe_remove(str(f))
        finally:
            mod.shutil.copy2 = original_copy

        # Original must still be intact; nothing was tracked.
        assert f.exists()
        assert tracker._backups == []
        warn.assert_called_once()


@pytest.mark.unittest
class TestCommit:
    def test_commit_removes_backups_and_clears_state(self, tracker, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("A")
        f2.write_text("B")

        tracker.safe_remove(str(f1))
        tracker.safe_remove(str(f2))

        # Pre-commit: both originals removed, both backups exist
        assert not f1.exists() and not f2.exists()
        assert (tmp_path / "a.txt.compresso.bak").exists()
        assert (tmp_path / "b.txt.compresso.bak").exists()

        tracker.commit()

        # Post-commit: backups gone, originals stay deleted, state cleared.
        assert not (tmp_path / "a.txt.compresso.bak").exists()
        assert not (tmp_path / "b.txt.compresso.bak").exists()
        assert not f1.exists()
        assert not f2.exists()
        assert tracker._backups == []

    def test_commit_with_no_operations_is_noop(self, tracker):
        # Should not raise on empty state.
        tracker.commit()
        assert tracker._backups == []


@pytest.mark.unittest
class TestRollback:
    def test_rollback_restores_original_contents(self, tracker, tmp_path):
        f = tmp_path / "movie.mkv"
        original_bytes = b"\x00\x01\x02original payload"
        f.write_bytes(original_bytes)

        tracker.safe_remove(str(f))
        assert not f.exists()  # safe_remove deleted the original

        tracker.rollback()

        assert f.exists()
        assert f.read_bytes() == original_bytes
        # Backup must have been consumed (moved back into place).
        assert not (tmp_path / "movie.mkv.compresso.bak").exists()
        # State must be cleared post-rollback.
        assert tracker._backups == []

    def test_rollback_restores_multiple_files(self, tracker, tmp_path):
        f1 = tmp_path / "one.txt"
        f2 = tmp_path / "two.txt"
        f1.write_text("one")
        f2.write_text("two")

        tracker.safe_remove(str(f1))
        tracker.safe_remove(str(f2))

        tracker.rollback()

        assert f1.read_text() == "one"
        assert f2.read_text() == "two"
        assert tracker._backups == []

    def test_rollback_partial_failure_continues_with_remaining(self, tmp_path, logger):
        """If restoring one file fails, the rollback must still attempt the others.

        The current implementation iterates with reversed() and catches per-file
        errors, so a failed restore should NOT prevent the next entry's restore.
        """
        f1 = tmp_path / "alpha.txt"
        f2 = tmp_path / "beta.txt"
        f1.write_text("alpha-original")
        f2.write_text("beta-original")

        error_log = MagicMock()
        log = MagicMock(error=error_log, warning=MagicMock(), info=MagicMock())
        tracker = FileOperationTracker(log)

        tracker.safe_remove(str(f1))
        tracker.safe_remove(str(f2))

        # Pre-rollback: both originals gone, both backups present.
        assert not f1.exists() and not f2.exists()
        backup_alpha = tmp_path / "alpha.txt.compresso.bak"
        backup_beta = tmp_path / "beta.txt.compresso.bak"
        assert backup_alpha.exists() and backup_beta.exists()

        # Sabotage the *beta* backup by deleting it. rollback() iterates in
        # reverse insertion order, so beta is attempted first. The existing
        # `if os.path.exists(backup_path)` guard will simply skip beta and then
        # proceed to alpha. (Earlier implementations risked aborting on first
        # failure -- this test pins down the "continue past failures" guarantee.)
        backup_beta.unlink()

        tracker.rollback()

        # Alpha (the second-attempted entry) must have been restored successfully.
        assert f1.exists()
        assert f1.read_text() == "alpha-original"
        # Beta was sabotaged so it cannot be restored, but rollback should have
        # tolerated that and continued -- and it must have cleared state.
        assert not f2.exists()
        assert tracker._backups == []

    def test_rollback_partial_failure_on_move_error(self, tmp_path):
        """If shutil.move raises mid-rollback, the OTHER entry must still restore.

        This directly exercises the try/except inside the rollback loop.
        """
        f1 = tmp_path / "first.txt"
        f2 = tmp_path / "second.txt"
        f1.write_text("first")
        f2.write_text("second")

        log = MagicMock()
        tracker = FileOperationTracker(log)
        tracker.safe_remove(str(f1))
        tracker.safe_remove(str(f2))

        from compresso.libs import file_operation_tracker as mod

        real_move = mod.shutil.move
        call_state = {"count": 0}

        def flaky_move(src, dst):
            call_state["count"] += 1
            # rollback iterates reversed -> first call is for f2.
            if call_state["count"] == 1:
                raise OSError("simulated mid-rollback failure")
            return real_move(src, dst)

        mod.shutil.move = flaky_move
        try:
            tracker.rollback()  # MUST NOT raise
        finally:
            mod.shutil.move = real_move

        # f1 (second entry, attempted after the failure) must still be restored.
        assert f1.exists()
        assert f1.read_text() == "first"
        # f2 stayed broken because we made its move raise.
        assert not f2.exists()
        # And the error path must have logged.
        log.error.assert_called()
        # State cleared regardless of partial failure.
        assert tracker._backups == []


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
