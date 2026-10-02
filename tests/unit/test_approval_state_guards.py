#!/usr/bin/env python3

"""Database-backed tests for approval task-state guards."""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.unmodels.tasks import Tasks


def _create_task(path, status):
    return Tasks.create(
        abspath=path,
        cache_path=None,
        priority=1,
        type="local",
        library_id=1,
        status=status,
    )


@pytest.mark.unittest
def test_approve_rejects_task_that_is_not_awaiting_approval(in_memory_db):
    from compresso.webserver.helpers.approval import approve_tasks

    pending = _create_task("/library/pending.mkv", "pending")

    with pytest.raises(ValueError, match="awaiting approval"):
        approve_tasks([pending.id])

    assert Tasks.get_by_id(pending.id).status == "pending"


@pytest.mark.unittest
def test_approve_mixed_batch_is_all_or_nothing(in_memory_db):
    from compresso.webserver.helpers.approval import approve_tasks

    awaiting = _create_task("/library/awaiting.mkv", "awaiting_approval")
    pending = _create_task("/library/other.mkv", "pending")

    with pytest.raises(ValueError, match="awaiting approval"):
        approve_tasks([awaiting.id, pending.id])

    assert Tasks.get_by_id(awaiting.id).status == "awaiting_approval"
    assert Tasks.get_by_id(pending.id).status == "pending"


@pytest.mark.unittest
def test_approve_updates_only_valid_awaiting_tasks(in_memory_db):
    from compresso.webserver.helpers.approval import approve_tasks

    first = _create_task("/library/first.mkv", "awaiting_approval")
    second = _create_task("/library/second.mkv", "awaiting_approval")

    assert approve_tasks([first.id, second.id]) == 2
    assert Tasks.get_by_id(first.id).status == "approved"
    assert Tasks.get_by_id(second.id).status == "approved"


@pytest.mark.unittest
def test_approve_deduplicates_task_ids(in_memory_db):
    from compresso.webserver.helpers.approval import approve_tasks

    awaiting = _create_task("/library/duplicate.mkv", "awaiting_approval")

    assert approve_tasks([awaiting.id, awaiting.id]) == 1
    assert Tasks.get_by_id(awaiting.id).status == "approved"


@pytest.mark.unittest
def test_approve_rejects_missing_task(in_memory_db):
    from compresso.webserver.helpers.approval import approve_tasks

    existing = _create_task("/library/existing.mkv", "awaiting_approval")

    with pytest.raises(ValueError, match="awaiting approval"):
        approve_tasks([existing.id + 999_999])


@pytest.mark.unittest
def test_reject_validates_state_before_filesystem_cleanup(in_memory_db, tmp_path):
    from compresso.webserver.helpers.approval import reject_tasks

    pending = _create_task("/library/pending-reject.mkv", "pending")
    staging_path = tmp_path / "staging"
    task_staging_path = staging_path / f"task_{pending.id}"
    task_staging_path.mkdir(parents=True)
    staged_file = task_staging_path / "output.mkv"
    staged_file.write_bytes(b"staged")

    settings = MagicMock()
    settings.get_staging_path.return_value = str(staging_path)

    with (
        patch("compresso.webserver.helpers.approval.config.Config", return_value=settings),
        pytest.raises(ValueError, match="awaiting approval"),
    ):
        reject_tasks([pending.id], requeue=False)

    assert staged_file.exists()
    assert Tasks.get_by_id(pending.id).status == "pending"
