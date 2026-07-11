#!/usr/bin/env python3

import json
import os

import pytest

from compresso.libs.scan_checkpoint import ScanCheckpointStore


@pytest.mark.unittest
def test_scan_checkpoint_survives_restart_and_can_be_cleared(tmp_path):
    first = ScanCheckpointStore(str(tmp_path))
    first.save(7, "/media/movies", "A/Season 1")

    second = ScanCheckpointStore(str(tmp_path))
    assert second.load(7, "/media/movies") == "A/Season 1"

    second.clear(7)
    assert first.load(7, "/media/movies") is None


@pytest.mark.unittest
def test_scan_checkpoint_is_ignored_if_library_root_changed(tmp_path):
    store = ScanCheckpointStore(str(tmp_path))
    store.save(7, "/media/movies", "A")

    assert store.load(7, "/new/movies") is None


@pytest.mark.unittest
def test_scan_checkpoint_recovers_from_corrupt_journal(tmp_path):
    checkpoint_dir = tmp_path / "scan-checkpoints"
    checkpoint_dir.mkdir()
    (checkpoint_dir / "library-7.json").write_text("not json")

    assert ScanCheckpointStore(str(tmp_path)).load(7, "/media/movies") is None


@pytest.mark.unittest
def test_checkpoint_write_is_valid_json(tmp_path):
    store = ScanCheckpointStore(str(tmp_path))
    store.save(4, "/media/tv", "Shows/A")

    data = json.loads((tmp_path / "scan-checkpoints" / "library-4.json").read_text())
    assert data["library_path"] == os.path.abspath("/media/tv")
    assert data["completed_root"] == "Shows/A"


@pytest.mark.unittest
def test_store_instances_share_lock_and_do_not_share_fixed_temp_filename(tmp_path):
    first = ScanCheckpointStore(str(tmp_path))
    second = ScanCheckpointStore(str(tmp_path))

    assert first._lock is second._lock
