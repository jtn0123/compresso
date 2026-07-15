#!/usr/bin/env python3

import errno
import hashlib
import json
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from compresso.libs.resumable_transfer import ResumableTransferStore, TransferStorageError


def _sha256(data):
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


@pytest.mark.unittest
def test_interrupted_transfer_resumes_from_persisted_offset(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"abcdefghij"
    status = store.begin("job-1", "movie.mkv", len(payload), _sha256(payload))
    store.append(status["transfer_id"], 0, payload[:4], _sha256(payload[:4]))

    restarted_store = ResumableTransferStore(tmp_path)
    resumed = restarted_store.begin("job-1", "movie.mkv", len(payload), _sha256(payload))

    assert resumed["transfer_id"] == status["transfer_id"]
    assert resumed["offset"] == 4
    assert resumed["complete"] is False


@pytest.mark.unittest
def test_begin_rejects_file_above_configured_maximum_before_creating_manifest(tmp_path):
    store = ResumableTransferStore(tmp_path, maximum_file_size_bytes=9)
    checksum = _sha256(b"x" * 10)

    with pytest.raises(ValueError, match="maximum"):
        store.begin("job-too-large", "movie.mkv", 10, checksum)

    assert list((tmp_path / "manifests").iterdir()) == []


@pytest.mark.unittest
def test_concurrent_sessions_reserve_all_remaining_bytes(tmp_path):
    disk = SimpleNamespace(total=100, used=0, free=100)
    store = ResumableTransferStore(
        tmp_path,
        minimum_free_bytes=10,
        disk_usage=lambda _path: disk,
    )
    store.begin("job-one", "one.mkv", 60, _sha256(b"x" * 60))

    store.begin("job-two", "two.mkv", 30, _sha256(b"y" * 30))
    checksum = _sha256(b"z")
    with pytest.raises(TransferStorageError, match="reserved"):
        store.begin("job-three", "three.mkv", 1, checksum)

    assert len(list((tmp_path / "manifests").glob("*.json"))) == 2


@pytest.mark.unittest
def test_simultaneous_session_creation_cannot_overcommit_shared_reservation(tmp_path):
    disk = SimpleNamespace(total=100, used=0, free=100)
    store = ResumableTransferStore(tmp_path, disk_usage=lambda _path: disk)
    barrier = threading.Barrier(2)

    def create_session(index):
        barrier.wait()
        try:
            store.begin(f"job-{index}", f"movie-{index}.mkv", 60, _sha256(bytes([index]) * 60))
            return "created"
        except TransferStorageError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create_session, (1, 2)))

    assert sorted(results) == ["created", "rejected"]
    assert len(list((tmp_path / "manifests").glob("*.json"))) == 1


@pytest.mark.unittest
def test_append_rechecks_free_space_and_retains_resumable_state(tmp_path):
    disk = SimpleNamespace(total=100, used=0, free=100)
    store = ResumableTransferStore(
        tmp_path,
        minimum_free_bytes=10,
        disk_usage=lambda _path: disk,
    )
    session = store.begin("job-one", "one.mkv", 20, _sha256(b"x" * 20))
    disk.free = 14
    chunk = b"12345"
    chunk_checksum = _sha256(chunk)

    with pytest.raises(TransferStorageError, match="reserve"):
        store.append(session["transfer_id"], 0, chunk, chunk_checksum)

    assert store.status(session["transfer_id"])["offset"] == 0
    assert store._manifest_path(session["transfer_id"]).exists()


@pytest.mark.unittest
def test_abandon_removes_owned_partial_manifest_and_completed_directory(tmp_path):
    store = ResumableTransferStore(tmp_path)
    session = store.begin("job-abandon", "movie.mkv", 10, _sha256(b"x" * 10))
    store.append(session["transfer_id"], 0, b"123", _sha256(b"123"))
    completed_dir = store.completed_dir / session["transfer_id"]
    completed_dir.mkdir()
    (completed_dir / "leftover").write_bytes(b"old")

    result = store.abandon(session["transfer_id"])

    assert result == {"transfer_id": session["transfer_id"], "abandoned": True}
    assert not store._manifest_path(session["transfer_id"]).exists()
    assert not store._partial_path(session["transfer_id"]).exists()
    assert not completed_dir.exists()


@pytest.mark.unittest
def test_append_rejects_wrong_offset_without_corrupting_partial_file(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"abcdefghij"
    status = store.begin("job-1", "movie.mkv", len(payload), _sha256(payload))
    store.append(status["transfer_id"], 0, payload[:4], _sha256(payload[:4]))

    with pytest.raises(ValueError, match="offset"):
        store.append(status["transfer_id"], 2, payload[4:], _sha256(payload[4:]))

    assert store.status(status["transfer_id"])["offset"] == 4


@pytest.mark.unittest
def test_append_rejects_corrupt_chunk(tmp_path):
    store = ResumableTransferStore(tmp_path)
    status = store.begin("job-1", "movie.mkv", 4, _sha256(b"good"))

    with pytest.raises(ValueError, match="checksum"):
        store.append(status["transfer_id"], 0, b"bad!", _sha256(b"good"))

    assert store.status(status["transfer_id"])["offset"] == 0


@pytest.mark.unittest
def test_finalize_verifies_full_checksum_and_atomically_publishes(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"complete-media-file"
    status = store.begin("job-1", "movie.mkv", len(payload), _sha256(payload))
    store.append(status["transfer_id"], 0, payload, _sha256(payload))

    completed = store.finalize(status["transfer_id"])

    assert completed.read_bytes() == payload
    final_status = store.status(status["transfer_id"])
    assert final_status["complete"] is True
    assert final_status["offset"] == len(payload)


@pytest.mark.unittest
def test_finalize_resets_partial_when_full_checksum_is_wrong(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"complete-media-file"
    status = store.begin("job-1", "movie.mkv", len(payload), _sha256(b"different"))
    store.append(status["transfer_id"], 0, payload, _sha256(payload))

    with pytest.raises(ValueError, match="checksum"):
        store.finalize(status["transfer_id"])

    assert store.status(status["transfer_id"])["offset"] == 0
    assert store.status(status["transfer_id"])["complete"] is False


@pytest.mark.unittest
def test_cleanup_removes_only_stale_incomplete_transfers(tmp_path):
    clock = [1000.0]
    store = ResumableTransferStore(tmp_path, now=lambda: clock[0])
    stale = store.begin("stale-job", "stale.mkv", 10, _sha256(b"x" * 10))
    clock[0] = 2000.0
    fresh = store.begin("fresh-job", "fresh.mkv", 10, _sha256(b"y" * 10))

    removed = store.cleanup_stale(max_age_seconds=500)

    assert stale["transfer_id"] in removed
    assert store.status(fresh["transfer_id"])["offset"] == 0


@pytest.mark.unittest
def test_summary_reports_active_complete_bytes_and_corrupt_manifests(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"complete"
    complete = store.begin("complete-job", "complete.mkv", len(payload), _sha256(payload))
    store.append(complete["transfer_id"], 0, payload, _sha256(payload))
    store.finalize(complete["transfer_id"])
    store.begin("active-job", "active.mkv", 100, f"sha256:{'0' * 64}")
    (tmp_path / "manifests" / "corrupt.json").write_text("bad json")

    assert store.summary() == {
        "active": 1,
        "complete": 1,
        "corrupt": 1,
        "bytes_received": len(payload),
        "bytes_total": 100 + len(payload),
    }


@pytest.mark.unittest
def test_store_instances_for_same_root_share_one_process_lock(tmp_path):
    first = ResumableTransferStore(tmp_path)
    second = ResumableTransferStore(tmp_path)

    assert first._lock is second._lock


@pytest.mark.unittest
def test_full_checksum_failure_resets_partial_for_clean_retry(tmp_path):
    store = ResumableTransferStore(tmp_path)
    expected = b"expected"
    corrupt = b"corrupt!"
    status = store.begin("job-1", "movie.mkv", len(expected), _sha256(expected))
    store.append(status["transfer_id"], 0, corrupt, _sha256(corrupt))

    with pytest.raises(ValueError, match="checksum"):
        store.finalize(status["transfer_id"])

    assert store.status(status["transfer_id"])["offset"] == 0


@pytest.mark.unittest
def test_begin_repairs_partial_larger_than_declared_transfer(tmp_path):
    store = ResumableTransferStore(tmp_path)
    expected = b"abcd"
    status = store.begin("job-1", "movie.mkv", len(expected), _sha256(expected))
    store._partial_path(status["transfer_id"]).write_bytes(b"oversized")

    resumed = ResumableTransferStore(tmp_path).begin("job-1", "movie.mkv", len(expected), _sha256(expected))

    assert resumed["offset"] == 0


@pytest.mark.unittest
def test_cleanup_removes_corrupt_manifest_and_continues_with_valid_stale_transfer(tmp_path):
    clock = [100.0]
    store = ResumableTransferStore(tmp_path, now=lambda: clock[0])
    stale = store.begin("stale", "stale.mkv", 4, _sha256(b"data"))
    (tmp_path / "manifests" / "corrupt.json").write_text("not json")
    clock[0] = 1000.0

    removed = store.cleanup_stale(100)

    assert removed == [stale["transfer_id"]]
    assert not (tmp_path / "manifests" / "corrupt.json").exists()


@pytest.mark.unittest
def test_complete_transfer_is_not_reported_when_artifact_is_missing(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"complete"
    status = store.begin("job", "movie.mkv", len(payload), _sha256(payload))
    store.append(status["transfer_id"], 0, payload, _sha256(payload))
    completed = store.finalize(status["transfer_id"])
    completed.unlink()

    with pytest.raises(ValueError, match="missing or has the wrong size"):
        store.status(status["transfer_id"])

    assert store.summary()["corrupt"] == 1
    assert store.cleanup_stale(1) == [status["transfer_id"]]
    assert not store._manifest_path(status["transfer_id"]).exists()


@pytest.mark.unittest
def test_finalizing_recovery_rehashes_artifact_before_marking_complete(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"complete"
    status = store.begin("job", "movie.mkv", len(payload), _sha256(payload))
    store.append(status["transfer_id"], 0, payload, _sha256(payload))
    completed = store.finalize(status["transfer_id"])
    completed.write_bytes(b"corrupt!")
    manifest_path = store._manifest_path(status["transfer_id"])
    manifest = json.loads(manifest_path.read_text())
    manifest["state"] = "finalizing"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="integrity validation"):
        ResumableTransferStore(tmp_path).status(status["transfer_id"])


@pytest.mark.unittest
def test_cleanup_removes_invalid_manifest_and_owned_artifacts(tmp_path):
    store = ResumableTransferStore(tmp_path)
    transfer_id = "a" * 32
    store._manifest_path(transfer_id).write_text(json.dumps({}))
    store._partial_path(transfer_id).write_bytes(b"partial")
    completed = store.completed_dir / transfer_id
    completed.mkdir()
    (completed / "movie.mkv").write_bytes(b"corrupt")

    removed = store.cleanup_stale(1)

    assert removed == [transfer_id]
    assert not store._manifest_path(transfer_id).exists()
    assert not store._partial_path(transfer_id).exists()
    assert not completed.exists()


@pytest.mark.unittest
def test_cleanup_removes_non_utf8_manifest_without_aborting(tmp_path):
    store = ResumableTransferStore(tmp_path)
    transfer_id = "b" * 32
    store._manifest_path(transfer_id).write_bytes(b"\xff\xfe")
    store._partial_path(transfer_id).write_bytes(b"partial")

    assert store.cleanup_stale(1) == [transfer_id]
    assert not store._manifest_path(transfer_id).exists()
    assert not store._partial_path(transfer_id).exists()


@pytest.mark.unittest
def test_deterministic_chunk_restart_fuzz_preserves_payload_and_offsets(tmp_path):
    for seed in range(40):
        rng = random.Random(seed)
        payload = rng.randbytes(rng.randint(0, 2048))
        root = tmp_path / f"seed-{seed}"
        store = ResumableTransferStore(root)
        status = store.begin(f"job-{seed}", "media.mkv", len(payload), _sha256(payload))
        offset = 0
        while offset < len(payload):
            chunk = payload[offset : offset + rng.randint(1, 97)]
            status = store.append(status["transfer_id"], offset, chunk, _sha256(chunk))
            offset += len(chunk)
            assert status["offset"] == offset
            if rng.choice((True, False)):
                store = ResumableTransferStore(root)
                assert store.status(status["transfer_id"])["offset"] == offset
        completed = store.finalize(status["transfer_id"])
        assert completed.read_bytes() == payload
        assert json.loads(store._manifest_path(status["transfer_id"]).read_text())["state"] == "complete"


@pytest.mark.unittest
def test_zero_byte_transfer_finalizes_with_empty_sha256(tmp_path):
    store = ResumableTransferStore(tmp_path)
    status = store.begin("empty-job", "empty.mkv", 0, _sha256(b""))

    completed = store.finalize(status["transfer_id"])

    assert completed.read_bytes() == b""
    assert store.status(status["transfer_id"])["complete"] is True


@pytest.mark.unittest
def test_summary_uses_actual_partial_size_after_interrupted_manifest_update(tmp_path):
    store = ResumableTransferStore(tmp_path)
    status = store.begin("job-1", "movie.mkv", 10, _sha256(b"x" * 10))
    store._partial_path(status["transfer_id"]).write_bytes(b"12345")

    summary = store.summary()

    assert summary["bytes_received"] == 5


@pytest.mark.unittest
def test_tampered_manifest_cannot_redirect_completed_file(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"safe"
    status = store.begin("job-1", "movie.mkv", len(payload), _sha256(payload))
    store.append(status["transfer_id"], 0, payload, _sha256(payload))
    manifest_path = store._manifest_path(status["transfer_id"])
    manifest = json.loads(manifest_path.read_text())
    outside = tmp_path / "outside.mkv"
    manifest["final_path"] = str(outside)
    manifest_path.write_text(json.dumps(manifest))

    completed = store.finalize(status["transfer_id"])

    assert completed.is_relative_to(tmp_path / "completed")
    assert completed.read_bytes() == payload
    assert not outside.exists()


@pytest.mark.unittest
def test_transfer_store_rejects_untrusted_transfer_id():
    store = ResumableTransferStore.__new__(ResumableTransferStore)

    with pytest.raises(ValueError, match="transfer ID"):
        store._validate_transfer_id("../escape")


@pytest.mark.unittest
@pytest.mark.parametrize(
    ("job_id", "checksum", "message"),
    [("", f"sha256:{'0' * 64}", "job identity"), ("job", "sha256:not-hex", "checksum")],
)
def test_begin_rejects_invalid_identity_and_checksum(tmp_path, job_id, checksum, message):
    store = ResumableTransferStore(tmp_path)

    with pytest.raises(ValueError, match=message):
        store.begin(job_id, "movie.mkv", 1, checksum)


@pytest.mark.unittest
@pytest.mark.parametrize("total_size", [True, 1.5, "1"])
def test_begin_rejects_noninteger_transfer_size(tmp_path, total_size):
    store = ResumableTransferStore(tmp_path)

    with pytest.raises(ValueError, match="must be an integer"):
        store.begin("job", "movie.mkv", total_size, _sha256(b"x"))


@pytest.mark.unittest
def test_manifest_rejects_noninteger_sizes(tmp_path):
    store = ResumableTransferStore(tmp_path)
    status = store.begin("job", "movie.mkv", 1, _sha256(b"x"))
    manifest_path = store._manifest_path(status["transfer_id"])
    manifest = json.loads(manifest_path.read_text())
    manifest["total_size"] = 1.5
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="sizes are invalid"):
        store.status(status["transfer_id"])


@pytest.mark.unittest
def test_manifest_rejects_non_object_metadata(tmp_path):
    store = ResumableTransferStore(tmp_path)
    status = store.begin("job", "movie.mkv", 1, _sha256(b"x"))
    manifest_path = store._manifest_path(status["transfer_id"])
    manifest = json.loads(manifest_path.read_text())
    manifest["metadata"] = "not-an-object"
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="metadata"):
        store.get_manifest(status["transfer_id"])


@pytest.mark.unittest
def test_complete_manifest_requires_terminal_offset(tmp_path):
    store = ResumableTransferStore(tmp_path)
    payload = b"done"
    status = store.begin("job", "movie.mkv", len(payload), _sha256(payload))
    store.append(status["transfer_id"], 0, payload, _sha256(payload))
    store.finalize(status["transfer_id"])
    manifest_path = store._manifest_path(status["transfer_id"])
    manifest = json.loads(manifest_path.read_text())
    manifest["offset"] = 0
    manifest_path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="terminal offset"):
        store.status(status["transfer_id"])


@pytest.mark.unittest
def test_nonfinite_manifest_timestamp_is_cleaned_as_corrupt(tmp_path):
    store = ResumableTransferStore(tmp_path, now=lambda: 1_000.0)
    status = store.begin("job", "movie.mkv", 1, _sha256(b"x"))
    manifest_path = store._manifest_path(status["transfer_id"])
    manifest = json.loads(manifest_path.read_text())
    manifest["updated_at"] = float("inf")
    manifest_path.write_text(json.dumps(manifest))

    assert store.cleanup_stale(1) == [status["transfer_id"]]


@pytest.mark.unittest
def test_status_rejects_partial_larger_than_declared_transfer(tmp_path):
    store = ResumableTransferStore(tmp_path)
    status = store.begin("job", "movie.mkv", 4, _sha256(b"data"))
    store._partial_path(status["transfer_id"]).write_bytes(b"oversized")

    with pytest.raises(ValueError, match="partial artifact exceeds"):
        store.status(status["transfer_id"])

    assert store.summary()["corrupt"] == 1


@pytest.mark.unittest
@pytest.mark.parametrize("error_number", [errno.ENOSPC, errno.EROFS])
def test_injected_filesystem_failure_preserves_resume_offset(tmp_path, error_number):
    failures = [error_number]

    def inject(operation, _path):
        if operation == "append" and failures:
            raise OSError(failures.pop(), "synthetic filesystem fault")

    payload = b"safe-media"
    store = ResumableTransferStore(tmp_path, fault_injector=inject)
    status = store.begin("fault-job", "movie.mkv", len(payload), _sha256(payload))

    with pytest.raises(OSError) as raised:
        store.append(status["transfer_id"], 0, payload, _sha256(payload))

    assert raised.value.errno == error_number
    assert store.status(status["transfer_id"])["offset"] == 0
    store.append(status["transfer_id"], 0, payload, _sha256(payload))
    assert store.finalize(status["transfer_id"]).read_bytes() == payload
