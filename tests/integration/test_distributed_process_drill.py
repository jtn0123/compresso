#!/usr/bin/env python3

"""Process-level distributed boundary acceptance test."""

import pytest

from compresso.libs.distributed_process_drill import run_drill


@pytest.mark.integrationtest
def test_two_process_transfer_survives_restart_and_is_idempotent():
    result = run_drill(size_mb=1, chunk_mb=1)

    assert result["master_worker_link"] == "validated"
    assert result["restart_during_upload"] == "resumed"
    assert result["stale_offset"] == "rejected"
    assert result["duplicate_finalization"] == "idempotent"
    assert result["restart_after_finalization"] == "preserved"
    assert result["database_isolation"] == "preserved"
