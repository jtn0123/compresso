#!/usr/bin/env python3

"""Deterministic malformed-state fuzzing for 20 TB restart boundaries."""

import hashlib
import json
import random
from unittest.mock import MagicMock

import pytest

from compresso.libs.file_operation_tracker import FileOperationTracker
from compresso.libs.resumable_transfer import ResumableTransferStore
from compresso.libs.safety_state import SafetyState
from compresso.libs.scan_checkpoint import ScanCheckpointStore


def _sha256(data):
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


@pytest.mark.unittest
def test_checkpoint_and_safety_json_fuzz_fail_closed(tmp_path):
    malformed_values = [None, True, 17, "text", [], ["event"], {}, {"schema_version": 1}, {"events": {}}]
    rng = random.Random(20260713)

    for seed in range(200):
        payload = rng.choice(malformed_values)
        checkpoint_root = tmp_path / f"checkpoint-{seed}"
        checkpoint_dir = checkpoint_root / "scan-checkpoints"
        checkpoint_dir.mkdir(parents=True)
        (checkpoint_dir / "library-7.json").write_text(json.dumps(payload))
        assert ScanCheckpointStore(checkpoint_root).load(7, "/media") is None

        safety_root = tmp_path / f"safety-{seed}"
        safety_dir = safety_root / "safety"
        safety_dir.mkdir(parents=True)
        (safety_dir / "state.json").write_text(json.dumps(payload))
        snapshot = SafetyState(safety_root).snapshot()
        assert snapshot["pause_required"] is True
        assert snapshot["events"][0]["code"] == "safety-state-corrupt"


@pytest.mark.unittest
def test_file_operation_journal_schema_fuzz_never_mutates_media(tmp_path):
    mutations = [
        ("version", 2),
        ("operation_id", "task-other"),
        ("task_id", True),
        ("state", "commited"),
        ("finalization_phase", "unknown"),
        ("backups", [["/unowned.bak", "/media/movie.mkv"]]),
        ("created_paths", "not-a-list"),
    ]
    rng = random.Random(4040)

    for seed in range(200):
        root = tmp_path / f"journal-{seed}"
        journal_dir = root / "journals"
        journal_dir.mkdir(parents=True)
        sentinel = root / "media.mkv"
        sentinel.write_bytes(b"preserve")
        payload = {
            "version": 1,
            "operation_id": "task-42",
            "task_id": 42,
            "state": "active",
            "finalization_phase": None,
            "backups": [],
            "created_paths": [str(sentinel)],
        }
        key, value = rng.choice(mutations)
        payload[key] = value
        (journal_dir / "task-42.json").write_text(json.dumps(payload))

        with pytest.raises(RuntimeError, match="file-operation journal"):
            FileOperationTracker.recover_all(str(journal_dir), MagicMock())

        assert sentinel.read_bytes() == b"preserve"


@pytest.mark.unittest
def test_resumable_manifest_schema_fuzz_rejects_every_mutation(tmp_path):
    mutations = [
        ("metadata", "not-an-object"),
        ("state", "done"),
        ("offset", 2),
        ("expected_checksum", "sha256:not-hex"),
        ("updated_at", float("inf")),
        ("updated_at", True),
        ("job_id", ""),
        ("filename", "../escape.mkv"),
    ]
    rng = random.Random(8080)

    for seed in range(200):
        store = ResumableTransferStore(tmp_path / f"transfer-{seed}")
        status = store.begin(f"job-{seed}", "movie.mkv", 1, _sha256(b"x"))
        manifest_path = store._manifest_path(status["transfer_id"])
        manifest = json.loads(manifest_path.read_text())
        key, value = rng.choice(mutations)
        manifest[key] = value
        manifest_path.write_text(json.dumps(manifest))

        with pytest.raises(ValueError):
            store.status(status["transfer_id"])
