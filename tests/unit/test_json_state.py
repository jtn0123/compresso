#!/usr/bin/env python3

"""Failure-injection coverage for the shared atomic JSON writer."""

import json
import os
from unittest.mock import patch

import pytest


def _existing_document(tmp_path):
    path = tmp_path / "state.json"
    original = {"generation": 1, "status": "safe"}
    path.write_text(json.dumps(original), encoding="utf-8")
    return path, original


@pytest.mark.unittest
def test_atomic_json_write_replaces_document_and_syncs_file_and_directory(tmp_path):
    from compresso.libs import json_state

    path, _original = _existing_document(tmp_path)
    real_fsync = os.fsync
    calls = []

    def recording_fsync(descriptor):
        calls.append(descriptor)
        return real_fsync(descriptor)

    with patch.object(json_state.os, "fsync", side_effect=recording_fsync):
        json_state.atomic_json_write(path, {"generation": 2}, mode=0o600)

    assert json.loads(path.read_text(encoding="utf-8")) == {"generation": 2}
    assert len(calls) == (1 if os.name == "nt" else 2)
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
    assert list(tmp_path.glob(".state.json-*.tmp")) == []


@pytest.mark.unittest
@pytest.mark.parametrize("failure_point", ["before-write", "serialize", "file-fsync", "before-replace"])
def test_atomic_json_write_failure_keeps_prior_document_valid(tmp_path, failure_point):
    from compresso.libs import json_state

    path, original = _existing_document(tmp_path)
    if failure_point == "before-write":
        target = patch.object(json_state.tempfile, "mkstemp", side_effect=OSError("injected before write"))
    elif failure_point == "serialize":
        target = patch.object(json_state.json, "dump", side_effect=TypeError("injected serialization failure"))
    elif failure_point == "file-fsync":
        target = patch.object(json_state.os, "fsync", side_effect=OSError("injected fsync failure"))
    else:
        target = patch.object(json_state.os, "replace", side_effect=OSError("injected pre-replacement failure"))

    with target, pytest.raises((OSError, TypeError), match="injected"):
        json_state.atomic_json_write(path, {"generation": 2})

    assert json.loads(path.read_text(encoding="utf-8")) == original
    assert list(tmp_path.glob(".state.json-*.tmp")) == []


@pytest.mark.unittest
@pytest.mark.skipif(os.name == "nt", reason="symlink behavior requires Unix permissions")
def test_atomic_json_write_replaces_symlink_without_touching_its_target(tmp_path):
    from compresso.libs.json_state import atomic_json_write

    outside = tmp_path / "outside.json"
    outside.write_text('{"preserve": true}', encoding="utf-8")
    destination = tmp_path / "state.json"
    destination.symlink_to(outside)

    atomic_json_write(destination, {"safe": True})

    assert not destination.is_symlink()
    assert json.loads(destination.read_text(encoding="utf-8")) == {"safe": True}
    assert json.loads(outside.read_text(encoding="utf-8")) == {"preserve": True}
