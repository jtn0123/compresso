#!/usr/bin/env python3

"""Low-cost operational counters for large-library processing."""

import os
import shutil
from datetime import datetime
from pathlib import Path

from peewee import fn

from compresso.libs.resumable_transfer import ResumableTransferStore
from compresso.libs.unmodels.tasks import Tasks


class OperationsStatus:
    @staticmethod
    def task_summary():
        result = {}
        query = Tasks.select(Tasks.status, fn.COUNT(Tasks.id).alias("row_count")).group_by(Tasks.status)
        for row in query:
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
    def _worker_summary(foreman):
        statuses = foreman.get_all_worker_status() if foreman else []
        return {
            "total": len(statuses),
            "idle": sum(bool(worker.get("idle")) for worker in statuses),
            "busy": sum(not bool(worker.get("idle")) for worker in statuses),
            "paused": sum(bool(worker.get("paused")) for worker in statuses),
            "disk_pressure": sum(bool(worker.get("disk_pressure")) for worker in statuses),
        }

    def snapshot(self, settings, foreman=None, data_queues=None):
        cache_path = os.path.abspath(settings.get_cache_path())
        transfer_root = os.path.join(cache_path, "remote_transfers")
        transfers = ResumableTransferStore(transfer_root).summary()
        disk = shutil.disk_usage(cache_path)
        checkpoint_root = Path(settings.get_userdata_path()) / "scan-checkpoints"
        scheduled_queue = (data_queues or {}).get("scheduledtasks")
        return {
            "tasks": self.task_summary(),
            "scheduled_queue_depth": scheduled_queue.qsize() if scheduled_queue else 0,
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
