#!/usr/bin/env python3

"""Two-process localhost drill for Compresso's real HTTP transfer boundary."""

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def _checksum(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _request_json(url: str, method: str = "GET", payload: dict | None = None, headers: dict | None = None):
    body = None if payload is None else json.dumps(payload).encode()
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)  # noqa: S310
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - localhost URL is constructed internally
        return response.status, json.loads(response.read())


def _post_chunk(url: str, data: bytes, offset: int):
    request = urllib.request.Request(  # noqa: S310
        url,
        data=data,
        headers={
            "Content-Type": "application/octet-stream",
            "X-Transfer-Offset": str(offset),
            "X-Chunk-Checksum": _checksum(data),
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - localhost URL is constructed internally
        return response.status, json.loads(response.read())


class _CompressoProcess:
    def __init__(self, name: str, home: Path, port: int, repository_root: Path):
        self.name = name
        self.home = home
        self.port = port
        self.repository_root = repository_root
        self.process = None
        self.log_handle = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/compresso/api/v2"

    def start(self, bind_attempts: int = 3):
        last_error = None
        for attempt in range(bind_attempts):
            self.home.mkdir(parents=True, exist_ok=True)
            for directory in (self.home / "cache", self.home / "staging", self.home / "library"):
                directory.mkdir(parents=True, exist_ok=True)
            self.log_handle = (self.home / f"{self.name}.stdout.log").open("ab")
            environment = {
                **os.environ,
                "HOME_DIR": str(self.home),
                "PYTHONPATH": str(self.repository_root),
                "config_path": str(self.home / "config"),
                "cache_path": str(self.home / "cache"),
                "log_path": str(self.home / "logs"),
                "plugins_path": str(self.home / "plugins"),
                "staging_path": str(self.home / "staging"),
                "library_path": str(self.home / "library"),
                "userdata_path": str(self.home / "userdata"),
                # The drill's isolated 1-3 MiB fixture must not inherit the
                # host's production reserve. Real deployments keep the 5 GiB
                # default; this process can only write below its temporary home.
                "minimum_free_space_gb": "0",
            }
            self.process = subprocess.Popen(  # noqa: S603 - fixed interpreter/module invocation
                [sys.executable, "-m", "compresso", "--address", "127.0.0.1", "--port", str(self.port)],
                cwd=self.repository_root,
                env=environment,
                stdout=self.log_handle,
                stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    last_error = RuntimeError(f"{self.name} exited during startup on port {self.port}")
                    break
                try:
                    _status, readiness = _request_json(f"{self.base_url}/healthcheck/readiness")
                    if readiness.get("ready") is True:
                        return
                except (OSError, ValueError, urllib.error.URLError) as error:
                    last_error = error
                time.sleep(0.1)
            else:
                self.stop()
                raise TimeoutError(f"{self.name} was not ready after 60 seconds: {last_error}")

            self.stop()
            if attempt + 1 < bind_attempts:
                self.port = _free_port()
        raise RuntimeError(f"{self.name} failed to bind after {bind_attempts} attempts: {last_error}")

    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None

    def restart(self):
        self.stop()
        self.port = _free_port()
        self.start()


def _assert_single_remote_task(worker: _CompressoProcess, expected_task_id: int):
    _status, task_status = _request_json(
        f"{worker.base_url}/pending/status/get",
        method="POST",
        payload={"id_list": [expected_task_id]},
    )
    results = task_status.get("results", [])
    _status, tasks = _request_json(f"{worker.base_url}/pending/tasks", method="POST", payload={"start": 0, "length": 20})
    if tasks.get("recordsTotal") != 1 or len(results) != 1 or results[0].get("id") != expected_task_id:
        raise RuntimeError(f"remote task identity was not idempotent: status={task_status}, queue={tasks}")


def run_drill(size_mb: int = 3, chunk_mb: int = 1) -> dict[str, object]:
    """Start a master and worker, interrupt upload, resume, finalize once, and restart."""
    if size_mb < 1 or chunk_mb < 1 or chunk_mb > 8:
        raise ValueError("size_mb must be positive and chunk_mb must be between 1 and 8")

    repository_root = Path(__file__).resolve().parents[2]
    master_port = _free_port()
    worker_port = _free_port()
    while worker_port == master_port:
        worker_port = _free_port()

    source = bytes(index % 251 for index in range(size_mb * 1024 * 1024))
    source_checksum = _checksum(source)
    chunk_size = chunk_mb * 1024 * 1024
    job_id = "two-process-drill"

    with tempfile.TemporaryDirectory(prefix="compresso-two-process-") as temp_dir:
        root = Path(temp_dir)
        master = _CompressoProcess("master", root / "master", master_port, repository_root)
        worker = _CompressoProcess("worker", root / "worker", worker_port, repository_root)
        try:
            master.start()
            worker.start()

            _status, validation = _request_json(
                f"{master.base_url}/settings/link/validate",
                method="POST",
                payload={"address": f"127.0.0.1:{worker_port}"},
            )
            if not validation.get("installation", {}).get("session", {}).get("uuid"):
                raise RuntimeError(f"master could not validate the worker over HTTP: {validation}")

            _status, session = _request_json(
                f"{worker.base_url}/transfer/session",
                method="POST",
                payload={
                    "job_id": job_id,
                    "filename": "synthetic.mkv",
                    "total_size": len(source),
                    "expected_checksum": source_checksum,
                    "lease_token": "drill-lease",
                    "origin_installation_uuid": "drill-master",
                },
            )
            transfer_id = session["transfer_id"]
            transfer_url = f"{worker.base_url}/transfer/chunk/{transfer_id}"
            first_chunk = source[:chunk_size]
            _post_chunk(transfer_url, first_chunk, 0)

            worker.restart()
            _status, resumed = _request_json(f"{worker.base_url}/transfer/session/{transfer_id}")
            if resumed.get("offset") != len(first_chunk):
                raise RuntimeError(f"worker restart lost the durable transfer offset: {resumed}")

            transfer_url = f"{worker.base_url}/transfer/chunk/{transfer_id}"
            try:
                _post_chunk(transfer_url, first_chunk, 0)
            except urllib.error.HTTPError as error:
                if error.code != 400:
                    raise
            else:
                raise RuntimeError("worker accepted a duplicate chunk at a stale offset")

            offset = len(first_chunk)
            while offset < len(source):
                chunk = source[offset : offset + chunk_size]
                _post_chunk(transfer_url, chunk, offset)
                offset += len(chunk)

            finalize_url = f"{worker.base_url}/transfer/finalize/{transfer_id}"
            _status, finalized = _request_json(finalize_url, method="POST", payload={})
            _status, finalized_again = _request_json(finalize_url, method="POST", payload={})
            if finalized["id"] != finalized_again["id"] or finalized.get("checksum") != source_checksum:
                raise RuntimeError("repeated finalization changed task identity or checksum")
            _assert_single_remote_task(worker, finalized["id"])

            worker.restart()
            _assert_single_remote_task(worker, finalized["id"])

            _status, master_tasks = _request_json(
                f"{master.base_url}/pending/tasks",
                method="POST",
                payload={"start": 0, "length": 20},
            )
            if master_tasks.get("recordsTotal") != 0:
                raise RuntimeError("master and worker did not keep isolated task databases")

            return {
                "master_worker_link": "validated",
                "bytes_transferred": len(source),
                "chunks": (len(source) + chunk_size - 1) // chunk_size,
                "restart_during_upload": "resumed",
                "stale_offset": "rejected",
                "final_checksum": source_checksum,
                "task_id": finalized["id"],
                "duplicate_finalization": "idempotent",
                "restart_after_finalization": "preserved",
                "database_isolation": "preserved",
            }
        finally:
            worker.stop()
            master.stop()
