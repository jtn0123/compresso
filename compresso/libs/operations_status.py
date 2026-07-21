#!/usr/bin/env python3

"""Low-cost operational counters for large-library processing."""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from peewee import fn

from compresso.libs.resumable_transfer import ResumableTransferStore
from compresso.libs.unmodels.tasks import Tasks

if TYPE_CHECKING:
    from compresso.config import Config
    from compresso.libs.foreman import Foreman


class TaskCountRow(Protocol):
    status: str
    row_count: int


def _queue_depth(value: object) -> int:
    qsize = getattr(value, "qsize", None)
    if not callable(qsize):
        return 0
    depth: object = qsize()
    return depth if isinstance(depth, int) and not isinstance(depth, bool) else 0


class OperationsStatus:
    @staticmethod
    def task_summary() -> dict[str, int]:
        result: dict[str, int] = {}
        query = Tasks.select(Tasks.status, fn.COUNT(Tasks.id).alias("row_count")).group_by(Tasks.status)
        for model_row in query:
            row = cast("TaskCountRow", model_row)
            result[row.status] = int(row.row_count)
        result["total"] = sum(result.values())

        now = datetime.now()
        result["active_remote_leases"] = (
            Tasks.select().where(Tasks.lease_token.is_null(False) & (Tasks.lease_expires_at > now)).count()
        )
        result["expired_remote_leases"] = (
            Tasks.select().where(Tasks.lease_token.is_null(False) & (Tasks.lease_expires_at <= now)).count()
        )
        return result

    @staticmethod
    def _worker_summary(foreman: Foreman | None) -> dict[str, int]:
        statuses = foreman.get_all_worker_status() if foreman else []
        return {
            "total": len(statuses),
            "idle": sum(bool(worker.get("idle")) for worker in statuses),
            "busy": sum(not bool(worker.get("idle")) for worker in statuses),
            "paused": sum(bool(worker.get("paused")) for worker in statuses),
            "disk_pressure": sum(bool(worker.get("disk_pressure")) for worker in statuses),
        }

    def snapshot(
        self,
        settings: Config,
        foreman: Foreman | None = None,
        data_queues: Mapping[str, object] | None = None,
    ) -> dict[str, object]:
        cache_path = os.path.abspath(settings.get_cache_path())
        transfer_root = os.path.join(cache_path, "remote_transfers")
        transfers = ResumableTransferStore(transfer_root).summary()
        disk = shutil.disk_usage(cache_path)
        checkpoint_root = Path(settings.get_userdata_path()) / "scan-checkpoints"
        scheduled_queue = data_queues.get("scheduledtasks") if data_queues else None
        scheduled_queue_depth = _queue_depth(scheduled_queue)
        return {
            "tasks": self.task_summary(),
            "scheduled_queue_depth": scheduled_queue_depth,
            "workers": self._worker_summary(foreman),
            "transfers": transfers,
            "cache_disk": {
                "path": cache_path,
                "total_bytes": int(disk.total),
                "used_bytes": int(disk.used),
                "free_bytes": int(disk.free),
                "reserve_bytes": int(float(settings.get_minimum_free_space_gb()) * 1024**3),
            },
            "scan_checkpoints": len(list(checkpoint_root.glob("library-*.json"))) if checkpoint_root.exists() else 0,
        }
