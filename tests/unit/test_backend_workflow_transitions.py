#!/usr/bin/env python3

"""Transition-table contracts for the backend workflow simplification."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from compresso.libs.media_manifest import _manifest_entry_path_transition, _verify_manifest_entry
from compresso.libs.postprocessor import PostProcessor
from compresso.libs.taskhandler import StartupRecoveryAction, TaskHandler


@pytest.mark.unittest
@pytest.mark.parametrize(
    (
        "status",
        "clear_pending",
        "success",
        "cache_usable",
        "staged_usable",
        "has_cache_path",
        "expected_action",
        "protect_cache",
        "protect_staged",
    ),
    [
        ("pending", True, None, False, False, True, StartupRecoveryAction.DELETE, False, False),
        ("in_progress", False, None, False, False, True, StartupRecoveryAction.REQUEUE, False, False),
        ("processed", False, True, False, False, True, StartupRecoveryAction.REQUEUE, False, False),
        ("processed", False, False, False, False, True, StartupRecoveryAction.NONE, False, False),
        ("processed", False, True, True, False, True, StartupRecoveryAction.PROTECT, True, False),
        ("awaiting_approval", False, True, True, True, True, StartupRecoveryAction.PROTECT, True, True),
        ("awaiting_approval", False, True, True, False, True, StartupRecoveryAction.RESTAGE, True, False),
        ("awaiting_approval", False, True, False, False, True, StartupRecoveryAction.REQUEUE, False, False),
        ("approved", False, True, True, False, True, StartupRecoveryAction.PROTECT, True, False),
        ("approved", False, True, False, True, True, StartupRecoveryAction.RESTORE_CACHE, True, True),
        ("approved", False, True, False, True, False, StartupRecoveryAction.REQUEUE, False, False),
        ("complete", False, True, True, False, True, StartupRecoveryAction.PROTECT, True, False),
        ("unknown", False, None, False, False, True, StartupRecoveryAction.NONE, False, False),
    ],
)
def test_startup_recovery_transition_table(
    status,
    clear_pending,
    success,
    cache_usable,
    staged_usable,
    has_cache_path,
    expected_action,
    protect_cache,
    protect_staged,
):
    transition = TaskHandler._startup_recovery_transition(
        status=status,
        clear_pending=clear_pending,
        success=success,
        cache_usable=cache_usable,
        staged_usable=staged_usable,
        has_cache_path=has_cache_path,
    )

    assert transition.action is expected_action
    assert transition.protect_cache is protect_cache
    assert transition.protect_staged is protect_staged


@pytest.mark.unittest
@pytest.mark.parametrize(
    ("current_phase", "event", "expected_phase"),
    [
        ("file_committed", "history_persisted", "history_committed"),
        ("history_committed", "metadata_persisted", "metadata_committed"),
        ("metadata_committed", "task_removed", "task_deleted"),
        ("history_committed", "history_persisted", "history_committed"),
        ("metadata_committed", "history_persisted", "metadata_committed"),
        ("task_deleted", "metadata_persisted", "task_deleted"),
        (None, "history_persisted", "history_committed"),
    ],
)
def test_local_finalization_transition_table(current_phase, event, expected_phase):
    assert PostProcessor._next_finalization_phase(current_phase, event) == expected_phase


@pytest.mark.unittest
@pytest.mark.parametrize(
    ("task_success", "movement_success", "commit_journal", "rollback_journal", "cleanup_cache", "succeeded"),
    [
        (True, True, True, False, True, True),
        (True, False, False, True, False, False),
        (False, True, False, False, True, True),
        (False, False, False, False, True, False),
    ],
)
def test_postprocess_completion_transition_table(
    task_success,
    movement_success,
    commit_journal,
    rollback_journal,
    cleanup_cache,
    succeeded,
):
    transition = PostProcessor._postprocess_completion_transition(task_success, movement_success)

    assert transition.commit_journal is commit_journal
    assert transition.rollback_journal is rollback_journal
    assert transition.cleanup_cache is cleanup_cache
    assert transition.succeeded is succeeded


@pytest.mark.unittest
@pytest.mark.parametrize(
    ("relative_path", "seen", "expected_issue", "include_expected"),
    [
        (None, set(), "manifest relative_path is invalid", False),
        ("", set(), "manifest relative_path is invalid", False),
        ("/absolute.mkv", set(), "manifest relative_path is invalid", False),
        ("video.mkv", {"video.mkv"}, "manifest relative_path is duplicated", False),
        ("../escape.mkv", set(), "manifest path escapes verification root", True),
        ("video.mkv", set(), None, True),
    ],
)
def test_manifest_entry_path_transition_table(tmp_path, relative_path, seen, expected_issue, include_expected):
    transition = _manifest_entry_path_transition(str(tmp_path), relative_path, seen)

    assert transition.include_expected is include_expected
    if expected_issue is None:
        assert transition.issues == ()
        assert transition.path == str(Path(tmp_path, "video.mkv").resolve())
    else:
        assert expected_issue in transition.issues


@pytest.mark.unittest
def test_manifest_entry_paths_use_normalized_duplicate_keys(tmp_path):
    seen = set()

    first = _manifest_entry_path_transition(str(tmp_path), "./video.mkv", seen)
    second = _manifest_entry_path_transition(str(tmp_path), "video.mkv", seen)

    assert first.issues == ()
    assert second.issues == ("manifest relative_path is duplicated",)


@pytest.mark.unittest
def test_manifest_entry_cross_drive_path_is_reported_as_escape(tmp_path, monkeypatch):
    def cross_drive(_paths):
        raise ValueError("Paths do not have the same drive")

    monkeypatch.setattr("compresso.libs.media_manifest.os.path.commonpath", cross_drive)

    transition = _manifest_entry_path_transition(str(tmp_path), "video.mkv", set())

    assert transition.issues == ("manifest path escapes verification root",)


@pytest.mark.unittest
def test_manifest_entry_size_race_becomes_a_verification_issue(tmp_path, monkeypatch):
    media_path = tmp_path / "video.mkv"
    media_path.write_bytes(b"media")
    monkeypatch.setattr("compresso.libs.media_manifest.os.path.getsize", MagicMock(side_effect=OSError("vanished")))

    result, _before_size, current_size, _include_expected = _verify_manifest_entry(
        str(tmp_path),
        {"relative_path": "video.mkv", "size_bytes": 5, "media": {}},
        set(),
    )

    assert current_size == 0
    assert result["issues"] == ["output probe failed: vanished"]


@pytest.mark.unittest
@pytest.mark.parametrize(
    ("phase", "history_calls", "metadata_calls", "remove_calls"),
    [
        ("file_committed", 1, 1, 1),
        ("history_committed", 0, 1, 1),
        ("metadata_committed", 0, 0, 1),
    ],
)
def test_local_finalization_resumes_after_last_committed_phase(phase, history_calls, metadata_calls, remove_calls):
    processor = PostProcessor.__new__(PostProcessor)
    processor._file_operation_tracker = MagicMock(finalization_phase=phase)
    processor._postprocess_local_file_safely = MagicMock(return_value=True)
    processor._persist_local_history = MagicMock(return_value=True)
    processor._persist_local_metadata = MagicMock(return_value=True)
    processor._remove_finalized_local_task = MagicMock(return_value=True)
    processor._mark_finalization_transition = MagicMock()
    processor._finalize_file_operation_journal = MagicMock()
    processor._dispatch_completion_notification = MagicMock()

    processor._finalize_local_task_with_capacity()

    assert processor._persist_local_history.call_count == history_calls
    assert processor._persist_local_metadata.call_count == metadata_calls
    assert processor._remove_finalized_local_task.call_count == remove_calls


@pytest.mark.unittest
def test_failed_file_journal_commit_defers_finalization():
    processor = PostProcessor.__new__(PostProcessor)
    processor._log = MagicMock()
    tracker = MagicMock()
    tracker.commit.return_value = False

    transition = processor._transition_postprocess_journal(
        tracker,
        task_success=True,
        movement_success=True,
        cache_path="/cache/video.mkv",
    )

    assert transition.succeeded is False
    assert transition.cleanup_cache is False
    tracker.mark_finalization_phase.assert_not_called()
