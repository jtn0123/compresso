#!/usr/bin/env python3

import hashlib
import json
import random

import pytest

from compresso.libs.resumable_transfer import ResumableTransferStore


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
def test_cleanup_skips_corrupt_manifest_and_continues_with_valid_stale_transfer(tmp_path):
    clock = [100.0]
    store = ResumableTransferStore(tmp_path, now=lambda: clock[0])
    stale = store.begin("stale", "stale.mkv", 4, _sha256(b"data"))
    (tmp_path / "manifests" / "corrupt.json").write_text("not json")
    clock[0] = 1000.0

    removed = store.cleanup_stale(100)

    assert removed == [stale["transfer_id"]]
    assert (tmp_path / "manifests" / "corrupt.json").exists()


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
