#!/usr/bin/env python3

import os
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.file_operation_tracker import FileOperationTracker


def _tracker(tmp_path, task_id=42):
    return FileOperationTracker(
        MagicMock(),
        journal_dir=str(tmp_path / "journals"),
        operation_id=f"task-{task_id}",
        task_id=task_id,
    )


@pytest.mark.unittest
def test_recovery_restores_original_after_crash_during_in_place_replace(tmp_path):
    original = tmp_path / "movie.mkv"
    original.write_bytes(b"original")
    tracker = _tracker(tmp_path)

    tracker.safe_remove(str(original))
    tracker.record_created(str(original))
    original.write_bytes(b"encoded")

    result = FileOperationTracker.recover_all(str(tmp_path / "journals"), MagicMock())

    assert original.read_bytes() == b"original"
    assert result == {"rolled_back_task_ids": [42], "committed_task_ids": [], "finalization_task_ids": []}
    assert not list((tmp_path / "journals").glob("*.json"))


@pytest.mark.unittest
def test_recovery_removes_new_destination_and_restores_removed_source(tmp_path):
    source = tmp_path / "movie.mkv"
    destination = tmp_path / "movie.mp4"
    source.write_bytes(b"original")
    destination.write_bytes(b"encoded")
    tracker = _tracker(tmp_path)

    tracker.record_created(str(destination))
    tracker.safe_remove(str(source))

    FileOperationTracker.recover_all(str(tmp_path / "journals"), MagicMock())

    assert source.read_bytes() == b"original"
    assert not destination.exists()


@pytest.mark.unittest
def test_committing_journal_keeps_destination_and_reports_resumable_finalization(tmp_path):
    original = tmp_path / "movie.mkv"
    original.write_bytes(b"original")
    tracker = _tracker(tmp_path)

    tracker.safe_remove(str(original))
    tracker.record_created(str(original))
    original.write_bytes(b"encoded")
    tracker.commit()

    result = FileOperationTracker.recover_all(str(tmp_path / "journals"), MagicMock())

    assert original.read_bytes() == b"encoded"
    assert result == {"rolled_back_task_ids": [], "committed_task_ids": [], "finalization_task_ids": [42]}
    assert list((tmp_path / "journals").glob("*.json"))

    FileOperationTracker.finalize_committed(str(tmp_path / "journals"))

    assert list((tmp_path / "journals").glob("*.json"))


@pytest.mark.unittest
def test_task_deleted_phase_allows_journal_cleanup(tmp_path):
    tracker = _tracker(tmp_path)
    tracker.commit()
    tracker.mark_finalization_phase("task_deleted")

    result = FileOperationTracker.recover_all(str(tmp_path / "journals"), MagicMock())

    assert result["committed_task_ids"] == [42]
    FileOperationTracker.finalize_committed(str(tmp_path / "journals"))
    assert not list((tmp_path / "journals").glob("*.json"))


@pytest.mark.unittest
def test_resume_committed_restores_finalization_phase(tmp_path):
    tracker = _tracker(tmp_path)
    tracker.commit()
    tracker.mark_finalization_phase("history_committed")

    resumed = FileOperationTracker.resume_committed(str(tmp_path / "journals"), task_id=42, logger=MagicMock())

    assert resumed is not None
    assert resumed.finalization_phase == "history_committed"


@pytest.mark.unittest
def test_finalize_removes_committed_journal(tmp_path):
    destination = tmp_path / "movie.mp4"
    destination.write_bytes(b"encoded")
    tracker = _tracker(tmp_path)
    tracker.record_created(str(destination))
    tracker.commit()

    assert list((tmp_path / "journals").glob("*.json"))

    tracker.finalize()

    assert not list((tmp_path / "journals").glob("*.json"))


@pytest.mark.unittest
def test_recovery_keeps_destination_if_required_backup_was_lost(tmp_path):
    original = tmp_path / "movie.mkv"
    original.write_bytes(b"original")
    tracker = _tracker(tmp_path)
    tracker.safe_remove(str(original))
    tracker.record_created(str(original))
    original.write_bytes(b"encoded")

    (tmp_path / "movie.mkv.compresso.bak").unlink()
    with pytest.raises(RuntimeError, match="file-operation journal"):
        FileOperationTracker.recover_all(str(tmp_path / "journals"), MagicMock())

    assert original.read_bytes() == b"encoded"
    assert list((tmp_path / "journals").glob("*.json"))


@pytest.mark.unittest
def test_safe_remove_refuses_to_overwrite_preexisting_backup(tmp_path):
    original = tmp_path / "movie.mkv"
    backup = tmp_path / "movie.mkv.compresso.bak"
    original.write_bytes(b"original")
    backup.write_bytes(b"user-backup")
    tracker = _tracker(tmp_path)

    with pytest.raises(FileExistsError):
        tracker.safe_remove(str(original))

    assert original.read_bytes() == b"original"
    assert backup.read_bytes() == b"user-backup"


@pytest.mark.unittest
def test_failed_rollback_keeps_durable_journal_for_startup_recovery(tmp_path):
    original = tmp_path / "movie.mkv"
    original.write_bytes(b"original")
    tracker = _tracker(tmp_path)
    tracker.safe_remove(str(original))

    with patch("compresso.libs.file_operation_tracker.shutil.move", side_effect=OSError("busy")):
        assert tracker.rollback() is False

    assert tracker._backups
    assert list((tmp_path / "journals").glob("*.json"))


@pytest.mark.unittest
def test_existing_operation_journal_cannot_be_silently_overwritten(tmp_path):
    first = _tracker(tmp_path)
    destination = tmp_path / "movie.mkv"
    first.record_created(str(destination))

    with pytest.raises(FileExistsError):
        _tracker(tmp_path)


@pytest.mark.unittest
def test_commit_cleanup_failure_remains_recoverable(tmp_path):
    original = tmp_path / "movie.mkv"
    original.write_bytes(b"original")
    tracker = _tracker(tmp_path)
    tracker.safe_remove(str(original))
    backup = tmp_path / "movie.mkv.compresso.bak"

    real_remove = os.remove

    def fail_backup_only(path):
        if path == str(backup):
            raise OSError("busy")
        return real_remove(path)

    with patch("compresso.libs.file_operation_tracker.os.remove", side_effect=fail_backup_only):
        assert tracker.commit() is False

    assert backup.exists()
    assert tracker._state == "commit_cleanup_pending"
    assert list((tmp_path / "journals").glob("*.json"))

    result = FileOperationTracker.recover_all(str(tmp_path / "journals"), MagicMock())
    assert result["finalization_task_ids"] == [42]
    assert not backup.exists()
