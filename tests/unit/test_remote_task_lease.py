#!/usr/bin/env python3

import datetime

import pytest

from compresso.libs.remote_task_lease import RemoteTaskLease
from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels.tasks import Tasks


@pytest.fixture
def lease_db(tmp_path):
    database = Database.select_database(
        {
            "TYPE": "SQLITE",
            "FILE": str(tmp_path / "lease.db"),
            "MIGRATIONS_DIR": str(tmp_path / "migrations"),
        }
    )
    database.create_tables([Tasks])
    yield database
    database.close()


def _task():
    return Tasks.create(
        abspath="/library/movie.mkv",
        cache_path="/cache/movie.mkv",
        status="pending",
        type="local",
        library_id=1,
    )


@pytest.mark.unittest
def test_acquire_creates_stable_job_id_and_persisted_lease(lease_db):
    task = _task()
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)

    token = RemoteTaskLease.acquire(task, "worker-a", ttl_seconds=120, now=now)

    task = Tasks.get_by_id(task.id)
    assert token
    assert task.job_id
    assert task.remote_installation_uuid == "worker-a"
    assert task.lease_token == token
    assert task.heartbeat_at == now
    assert task.lease_expires_at == now + datetime.timedelta(seconds=120)


@pytest.mark.unittest
def test_active_lease_cannot_be_stolen_by_another_worker(lease_db):
    task = _task()
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    token = RemoteTaskLease.acquire(task, "worker-a", now=now)

    second = RemoteTaskLease.acquire(task, "worker-b", now=now + datetime.timedelta(seconds=5))

    assert second is None
    assert Tasks.get_by_id(task.id).lease_token == token


@pytest.mark.unittest
def test_expired_lease_can_be_reassigned(lease_db):
    task = _task()
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    first = RemoteTaskLease.acquire(task, "worker-a", ttl_seconds=10, now=now)

    second = RemoteTaskLease.acquire(task, "worker-b", now=now + datetime.timedelta(seconds=11))

    assert second
    assert second != first
    assert Tasks.get_by_id(task.id).remote_installation_uuid == "worker-b"


@pytest.mark.unittest
def test_heartbeat_extends_only_matching_lease(lease_db):
    task = _task()
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    token = RemoteTaskLease.acquire(task, "worker-a", ttl_seconds=30, now=now)

    assert RemoteTaskLease.heartbeat(task, "wrong-token", now=now + datetime.timedelta(seconds=5)) is False
    assert RemoteTaskLease.heartbeat(task, token, ttl_seconds=60, now=now + datetime.timedelta(seconds=5)) is True

    task = Tasks.get_by_id(task.id)
    assert task.heartbeat_at == now + datetime.timedelta(seconds=5)
    assert task.lease_expires_at == now + datetime.timedelta(seconds=65)


@pytest.mark.unittest
def test_completion_is_idempotent_but_rejects_conflicting_result(lease_db):
    task = _task()
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    token = RemoteTaskLease.acquire(task, "worker-a", now=now)

    assert RemoteTaskLease.complete(task, token, "sha256:abc", now=now) is True
    assert RemoteTaskLease.complete(task, token, "sha256:abc", now=now) is True
    assert RemoteTaskLease.complete(task, token, "sha256:different", now=now) is False

    task = Tasks.get_by_id(task.id)
    assert task.remote_result_checksum == "sha256:abc"
    assert task.remote_completed_at == now
    assert task.lease_expires_at is None


@pytest.mark.unittest
def test_reacquire_by_same_worker_renews_nearly_expired_lease(lease_db):
    task = _task()
    now = datetime.datetime(2026, 1, 1, 12, 0, 0)
    token = RemoteTaskLease.acquire(task, "worker-a", ttl_seconds=10, now=now)

    resumed = RemoteTaskLease.acquire(
        task,
        "worker-a",
        ttl_seconds=60,
        now=now + datetime.timedelta(seconds=9),
    )

    assert resumed == token
    assert Tasks.get_by_id(task.id).lease_expires_at == now + datetime.timedelta(seconds=69)


@pytest.mark.unittest
def test_idempotent_completion_still_requires_owning_token(lease_db):
    task = _task()
    token = RemoteTaskLease.acquire(task, "worker-a")
    assert RemoteTaskLease.complete(task, token, "sha256:abc") is True

    assert RemoteTaskLease.complete(task, "wrong-token", "sha256:abc") is False
