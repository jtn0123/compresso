#!/usr/bin/env python3

"""Transition-table contracts for the backend workflow simplification."""

from pathlib import Path

import pytest

from compresso.libs.media_manifest import _manifest_entry_path_transition
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
