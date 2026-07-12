#!/usr/bin/env python3

import os
from unittest.mock import MagicMock

import pytest

from compresso.libs.singleton import SingletonType
from compresso.libs.taskhandler import TaskHandler
from compresso.libs.unmodels import Libraries, Tags
from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels.tasks import Tasks

LibraryTags = Libraries.tags.get_through_model()


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture
def recovery_db(tmp_path):
    database_settings = {
        "TYPE": "SQLITE",
        "FILE": str(tmp_path / "restart-recovery.db"),
        "MIGRATIONS_DIR": str(tmp_path / "migrations"),
    }
    db_connection = Database.select_database(database_settings)
    db_connection.create_tables([Tasks, Libraries, LibraryTags, Tags])
    Libraries.create(id=1, name="Movies", path=str(tmp_path / "library"))
    yield db_connection
    db_connection.close()


def _settings(tmp_path, *, clear_pending=False):
    settings = MagicMock()
    settings.get_clear_pending_tasks_on_restart.return_value = clear_pending
    settings.get_staging_path.return_value = str(tmp_path / "staging")
    return settings


def _task(tmp_path, status, *, cache_exists=False, task_type="local", success=True):
    source = tmp_path / "library" / f"{status}-{Tasks.select().count()}.mkv"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"source")
    cache = tmp_path / "cache" / f"compresso_file_conversion-{status}" / source.name
    if cache_exists:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"encoded")
    return Tasks.create(
        abspath=str(source),
        cache_path=str(cache),
        library_id=1,
        status=status,
        type=task_type,
        success=success,
    )


@pytest.mark.unittest
def test_interrupted_task_is_requeued_without_protecting_partial_cache(recovery_db, tmp_path):
    task = _task(tmp_path, "in_progress", cache_exists=True)

    protected = TaskHandler.recover_tasks_on_startup(_settings(tmp_path))

    task = Tasks.get_by_id(task.id)
    assert task.status == "pending"
    assert task.success is None
    assert task.processed_by_worker is None
    assert str(task.cache_path) not in protected


@pytest.mark.unittest
def test_completed_encode_with_cache_stays_processed(recovery_db, tmp_path):
    task = _task(tmp_path, "processed", cache_exists=True)

    protected = TaskHandler.recover_tasks_on_startup(_settings(tmp_path))

    assert Tasks.get_by_id(task.id).status == "processed"
    assert str(task.cache_path) in protected


@pytest.mark.unittest
def test_completed_encode_without_cache_is_requeued(recovery_db, tmp_path):
    task = _task(tmp_path, "processed", cache_exists=False)

    protected = TaskHandler.recover_tasks_on_startup(_settings(tmp_path))

    task = Tasks.get_by_id(task.id)
    assert task.status == "pending"
    assert task.success is None
    assert str(task.cache_path) not in protected


@pytest.mark.unittest
def test_awaiting_approval_with_staged_output_survives(recovery_db, tmp_path):
    task = _task(tmp_path, "awaiting_approval", cache_exists=True)
    staged = tmp_path / "staging" / f"task_{task.id}" / "encoded.mkv"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"staged")

    protected = TaskHandler.recover_tasks_on_startup(_settings(tmp_path))

    assert Tasks.get_by_id(task.id).status == "awaiting_approval"
    assert str(task.cache_path) in protected
    assert str(staged) in protected


@pytest.mark.unittest
def test_missing_staging_rebuilds_approval_from_valid_cache(recovery_db, tmp_path):
    task = _task(tmp_path, "awaiting_approval", cache_exists=True)

    TaskHandler.recover_tasks_on_startup(_settings(tmp_path))

    assert Tasks.get_by_id(task.id).status == "processed"


@pytest.mark.unittest
def test_approved_task_restores_missing_cache_from_staging(recovery_db, tmp_path):
    task = _task(tmp_path, "approved", cache_exists=False)
    staged = tmp_path / "staging" / f"task_{task.id}" / "encoded.mkv"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"staged-output")

    protected = TaskHandler.recover_tasks_on_startup(_settings(tmp_path))

    task = Tasks.get_by_id(task.id)
    assert task.status == "approved"
    assert os.path.exists(task.cache_path)
    with open(task.cache_path, "rb") as restored_cache:
        assert restored_cache.read() == b"staged-output"
    assert str(task.cache_path) in protected


@pytest.mark.unittest
def test_clear_pending_setting_only_removes_pending_tasks(recovery_db, tmp_path):
    pending = _task(tmp_path, "pending")
    approval = _task(tmp_path, "awaiting_approval", cache_exists=True)
    staged = tmp_path / "staging" / f"task_{approval.id}" / "encoded.mkv"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(b"staged")

    TaskHandler.recover_tasks_on_startup(_settings(tmp_path, clear_pending=True))

    assert Tasks.get_or_none(Tasks.id == pending.id) is None
    assert Tasks.get_by_id(approval.id).status == "awaiting_approval"


@pytest.mark.unittest
def test_remote_completed_task_and_result_are_preserved(recovery_db, tmp_path):
    task = _task(tmp_path, "complete", cache_exists=True, task_type="remote")

    protected = TaskHandler.recover_tasks_on_startup(_settings(tmp_path))

    assert Tasks.get_by_id(task.id).status == "complete"
    assert str(task.abspath) in protected
    assert str(task.cache_path) in protected


@pytest.mark.unittest
def test_committed_file_operation_task_is_not_requeued(recovery_db, tmp_path):
    task = _task(tmp_path, "processed", cache_exists=False)

    TaskHandler.recover_tasks_on_startup(_settings(tmp_path), committed_task_ids=[task.id])

    assert Tasks.get_or_none(Tasks.id == task.id) is None


@pytest.mark.unittest
def test_incomplete_finalization_task_is_preserved_for_replay(recovery_db, tmp_path):
    task = _task(tmp_path, "processed", cache_exists=False)

    TaskHandler.recover_tasks_on_startup(_settings(tmp_path), finalization_task_ids=[task.id])

    assert Tasks.get_by_id(task.id).status == "processed"


@pytest.mark.unittest
def test_interrupted_remote_lease_requeues_with_stable_binding(recovery_db, tmp_path):
    task = _task(tmp_path, "in_progress", cache_exists=False)
    task.job_id = "stable-job"
    task.remote_task_id = 77
    task.remote_installation_uuid = "worker-a"
    task.lease_token = "lease-token"  # noqa: S105 - synthetic lease fixture
    task.save()

    TaskHandler.recover_tasks_on_startup(_settings(tmp_path))

    task = Tasks.get_by_id(task.id)
    assert task.status == "pending"
    assert task.job_id == "stable-job"
    assert task.remote_task_id == 77
    assert task.remote_installation_uuid == "worker-a"
    assert task.lease_token == "lease-token"  # noqa: S105 - synthetic lease fixture
