#!/usr/bin/env python3

import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.resumable_transfer import ResumableTransferStore
from compresso.webserver.api_v2.transfer_api import ApiTransferHandler


def _checksum(data):
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _handler(store, body=b"", headers=None):
    handler = ApiTransferHandler.__new__(ApiTransferHandler)
    handler.request = SimpleNamespace(body=body, headers=headers or {})
    handler._store = MagicMock(return_value=store)
    handler.write_success = MagicMock()
    handler.write_error = MagicMock()
    handler.set_status = MagicMock()
    handler.error_messages = {}
    handler.route = {}
    return handler


@pytest.mark.unittest
def test_begin_and_append_chunk_return_persisted_offsets(tmp_path):
    payload = b"chunked-media"
    store = ResumableTransferStore(tmp_path)
    request = {
        "job_id": "job-1",
        "filename": "movie.mkv",
        "total_size": len(payload),
        "expected_checksum": _checksum(payload),
    }
    handler = _handler(store, json.dumps(request).encode())

    asyncio.run(handler.begin_transfer())
    session = handler.write_success.call_args.args[0]

    chunk_handler = _handler(
        store,
        payload[:5],
        {
            "X-Transfer-Offset": "0",
            "X-Chunk-Checksum": _checksum(payload[:5]),
        },
    )
    asyncio.run(chunk_handler.append_transfer_chunk(session["transfer_id"]))

    assert chunk_handler.write_success.call_args.args[0]["offset"] == 5


@pytest.mark.unittest
def test_transfer_route_accepts_tornado_byte_path_parameter(tmp_path):
    payload = b"route-boundary"
    store = ResumableTransferStore(tmp_path)
    session = store.begin("job-route", "movie.mkv", len(payload), _checksum(payload))
    handler = _handler(
        store,
        payload,
        {
            "X-Transfer-Offset": "0",
            "X-Chunk-Checksum": _checksum(payload),
        },
    )

    asyncio.run(handler.append_transfer_chunk(session["transfer_id"].encode("ascii")))

    assert handler.write_success.call_args.args[0]["offset"] == len(payload)


@pytest.mark.unittest
def test_transfer_status_accepts_tornado_byte_path_parameter(tmp_path):
    store = ResumableTransferStore(tmp_path)
    session = store.begin("job-status", "movie.mkv", 0, _checksum(b""))
    handler = _handler(store)

    asyncio.run(handler.get_transfer_status(session["transfer_id"].encode("ascii")))

    assert handler.write_success.call_args.args[0]["transfer_id"] == session["transfer_id"]


@pytest.mark.unittest
def test_source_chunk_reads_file_off_event_loop(tmp_path):
    source = tmp_path / "movie.mkv"
    source.write_bytes(b"abcdefgh")
    handler = _handler(MagicMock())
    handler.get_query_argument = MagicMock(side_effect=lambda name, default: {"offset": "2", "limit": "3"}[name])
    handler.set_header = MagicMock()
    handler.finish = MagicMock()
    task = SimpleNamespace(abspath=str(source))

    with patch.object(ApiTransferHandler, "_completed_source", return_value=task) as completed_source:
        asyncio.run(handler.get_source_chunk(b"7"))

    completed_source.assert_called_once_with("7")
    handler.finish.assert_called_once_with(b"cde")


@pytest.mark.unittest
def test_source_manifest_decodes_tornado_byte_path_parameter(tmp_path):
    source = tmp_path / "movie.mkv"
    source.write_bytes(b"manifest")
    handler = _handler(MagicMock())
    task = SimpleNamespace(id=7, job_id="job-7", abspath=str(source))

    with patch.object(ApiTransferHandler, "_completed_source", return_value=task) as completed_source:
        asyncio.run(handler.get_source_manifest(b"7"))

    completed_source.assert_called_once_with("7")
    assert handler.write_success.call_args.args[0]["task_id"] == 7


@pytest.mark.unittest
def test_finalize_creates_one_remote_task_from_verified_file(tmp_path):
    payload = b"complete-media"
    store = ResumableTransferStore(tmp_path)
    session = store.begin(
        "job-1",
        "movie.mkv",
        len(payload),
        _checksum(payload),
        metadata={"lease_token": "lease-1", "origin_installation_uuid": "master-1"},  # noqa: S106
    )
    store.append(session["transfer_id"], 0, payload, _checksum(payload))
    handler = _handler(store)

    with (
        patch("compresso.webserver.api_v2.transfer_api.pending_tasks.add_remote_tasks") as add_task,
        patch("compresso.webserver.api_v2.transfer_api.pending_tasks.bind_remote_task_identity") as bind_identity,
    ):
        add_task.return_value = {"id": 7, "status": "creating"}
        asyncio.run(handler.finalize_transfer(session["transfer_id"].encode("ascii")))

    completed_path = add_task.call_args.args[0]
    assert completed_path.endswith("movie.mkv")
    add_task.assert_called_once_with(completed_path, job_id="job-1")
    bind_identity.assert_called_once_with(
        7,
        lease_token="lease-1",  # noqa: S106 - synthetic lease fixture
        origin_installation_uuid="master-1",
    )
    assert handler.write_success.call_args.args[0]["checksum"] == _checksum(payload)


@pytest.mark.unittest
def test_finalize_rejects_conflicting_identity_rebind(tmp_path):
    payload = b"complete-media"
    store = ResumableTransferStore(tmp_path)
    session = store.begin(
        "job-1",
        "movie.mkv",
        len(payload),
        _checksum(payload),
        metadata={"lease_token": "wrong-lease", "origin_installation_uuid": "master-1"},  # noqa: S106
    )
    store.append(session["transfer_id"], 0, payload, _checksum(payload))
    handler = _handler(store)

    with (
        patch(
            "compresso.webserver.api_v2.transfer_api.pending_tasks.add_remote_tasks",
            return_value={"id": 7, "status": "creating"},
        ),
        patch("compresso.webserver.api_v2.transfer_api.pending_tasks.bind_remote_task_identity", return_value=False),
    ):
        asyncio.run(handler.finalize_transfer(session["transfer_id"]))

    handler.write_success.assert_not_called()
    handler.write_error.assert_called_once()


@pytest.mark.unittest
@pytest.mark.parametrize(
    "request_update",
    [
        {"job_id": ""},
        {"filename": ""},
        {"total_size": -1},
        {"expected_checksum": "UNKNOWN"},
        {"expected_checksum": "sha256:not-hex"},
    ],
)
def test_begin_rejects_invalid_transfer_identity_and_checksum(tmp_path, request_update):
    request = {
        "job_id": "job-1",
        "filename": "movie.mkv",
        "total_size": 4,
        "expected_checksum": _checksum(b"data"),
    }
    request.update(request_update)
    handler = _handler(ResumableTransferStore(tmp_path), json.dumps(request).encode())

    asyncio.run(handler.begin_transfer())

    handler.write_success.assert_not_called()
    handler.write_error.assert_called()
