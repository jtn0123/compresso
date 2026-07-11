#!/usr/bin/env python3

"""Persistent leases for exactly-once remote task ownership."""

import datetime
import uuid

from compresso.libs.unmodels.tasks import Tasks


class RemoteTaskLease:
    DEFAULT_TTL_SECONDS = 3600

    @staticmethod
    def _now(now=None):
        return now or datetime.datetime.now()

    @classmethod
    def _ensure_job_id(cls, task):
        if task.job_id:
            return task.job_id
        job_id = str(uuid.uuid4())
        updated = Tasks.update(job_id=job_id).where((Tasks.id == task.id) & Tasks.job_id.is_null()).execute()
        if updated:
            task.job_id = job_id
            return job_id
        return Tasks.get_by_id(task.id).job_id

    @classmethod
    def acquire(cls, task, installation_uuid, ttl_seconds=None, now=None):
        """Acquire or resume an unexpired lease for one remote installation."""
        now = cls._now(now)
        ttl_seconds = max(1, int(cls.DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds))
        task = Tasks.get_by_id(task.id)
        cls._ensure_job_id(task)

        if task.remote_completed_at is not None:
            return None

        if task.lease_token and task.lease_expires_at and task.lease_expires_at > now:
            if task.remote_installation_uuid == installation_uuid:
                return task.lease_token if cls.heartbeat(task, task.lease_token, ttl_seconds=ttl_seconds, now=now) else None
            return None

        token = str(uuid.uuid4())
        expires_at = now + datetime.timedelta(seconds=ttl_seconds)
        available = Tasks.lease_token.is_null() | Tasks.lease_expires_at.is_null() | (Tasks.lease_expires_at <= now)
        updated = (
            Tasks.update(
                lease_token=token,
                remote_installation_uuid=installation_uuid,
                heartbeat_at=now,
                lease_expires_at=expires_at,
            )
            .where((Tasks.id == task.id) & available)
            .execute()
        )
        return token if updated else None

    @classmethod
    def heartbeat(cls, task, token, ttl_seconds=None, now=None):
        """Extend a live lease when the caller still owns its token."""
        now = cls._now(now)
        ttl_seconds = max(1, int(cls.DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds))
        expires_at = now + datetime.timedelta(seconds=ttl_seconds)
        updated = (
            Tasks.update(heartbeat_at=now, lease_expires_at=expires_at)
            .where((Tasks.id == task.id) & (Tasks.lease_token == token) & Tasks.remote_completed_at.is_null())
            .execute()
        )
        return bool(updated)

    @classmethod
    def complete(cls, task, token, result_checksum, now=None):
        """Persist one completion result; identical repeats are successful no-ops."""
        now = cls._now(now)
        current = Tasks.get_by_id(task.id)
        if current.remote_result_checksum is not None:
            return current.lease_token == token and current.remote_result_checksum == result_checksum
        updated = (
            Tasks.update(
                remote_result_checksum=result_checksum,
                remote_completed_at=now,
                heartbeat_at=now,
                lease_expires_at=None,
            )
            .where((Tasks.id == task.id) & (Tasks.lease_token == token) & Tasks.remote_result_checksum.is_null())
            .execute()
        )
        if updated:
            return True
        current = Tasks.get_by_id(task.id)
        return current.remote_result_checksum == result_checksum
