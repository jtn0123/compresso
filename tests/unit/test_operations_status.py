#!/usr/bin/env python3

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.operations_status import OperationsStatus


@pytest.mark.unittest
def test_snapshot_combines_queue_transfer_worker_disk_and_scan_state(tmp_path):
    settings = MagicMock()
    settings.get_cache_path.return_value = str(tmp_path / "cache")
    settings.get_userdata_path.return_value = str(tmp_path / "userdata")
    settings.get_minimum_free_space_gb.return_value = 5
    foreman = MagicMock()
    foreman.get_all_worker_status.return_value = [
        {"idle": True, "paused": False, "disk_pressure": None},
        {"idle": False, "paused": True, "disk_pressure": {"free_bytes": 10}},
    ]
    queues = {"scheduledtasks": MagicMock(qsize=MagicMock(return_value=17))}

    with patch.object(OperationsStatus, "task_summary", return_value={"pending": 12, "complete": 3, "total": 15}):
        status = OperationsStatus().snapshot(settings, foreman=foreman, data_queues=queues)

    assert status["tasks"]["pending"] == 12
    assert status["scheduled_queue_depth"] == 17
    assert status["workers"] == {"total": 2, "idle": 1, "busy": 1, "paused": 1, "disk_pressure": 1}
    assert status["transfers"]["active"] == 0
    assert status["scan_checkpoints"] == 0
    assert status["cache_disk"]["free_bytes"] > 0
