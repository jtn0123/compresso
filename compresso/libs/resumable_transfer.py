#!/usr/bin/env python3

"""Crash-safe chunked file transfers with persistent resume offsets."""

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:  # NOSONAR - callers supply validated task or transfer-store paths
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


class ResumableTransferStore:
    _locks_guard = threading.Lock()
    _locks_by_root: dict[str, Any] = {}

    def __init__(self, root_dir, now=time.time):
        self.root_dir = Path(root_dir).resolve()
        self.partial_dir = self.root_dir / "partial"
        self.completed_dir = self.root_dir / "completed"
        self.manifest_dir = self.root_dir / "manifests"
        self._now = now
        with self._locks_guard:
            self._lock = self._locks_by_root.setdefault(str(self.root_dir), threading.RLock())
        for directory in (self.partial_dir, self.completed_dir, self.manifest_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _checksum(data):
        return f"sha256:{hashlib.sha256(data).hexdigest()}"

    @staticmethod
    def _file_checksum(path):
        return file_sha256(path)

    @staticmethod
    def _transfer_id(job_id, filename, total_size):
        identity = f"{job_id}\0{filename}\0{int(total_size)}".encode()
        return hashlib.sha256(identity).hexdigest()[:32]

    def _manifest_path(self, transfer_id):
        self._validate_transfer_id(transfer_id)
        return self.manifest_dir / f"{transfer_id}.json"

    def _partial_path(self, transfer_id):
        self._validate_transfer_id(transfer_id)
        return self.partial_dir / f"{transfer_id}.part"

    @staticmethod
    def _validate_transfer_id(transfer_id):
        if not isinstance(transfer_id, str) or re.fullmatch(r"[a-f0-9]{32}", transfer_id) is None:
            raise ValueError("Invalid transfer ID")

    def _final_path(self, manifest):
        transfer_id = manifest.get("transfer_id")
        self._validate_transfer_id(transfer_id)
        filename = manifest.get("filename")
        if not isinstance(filename, str) or filename != os.path.basename(filename) or filename in {"", ".", ".."}:
            raise ValueError("Invalid transfer filename")
        final_path = (self.completed_dir / transfer_id / filename).resolve()  # NOSONAR - validated immediately below
        if not final_path.is_relative_to(self.completed_dir):
            raise ValueError("Transfer path escapes completed directory")
        return final_path

    def _write_manifest(self, manifest):
        fd, temporary_path = tempfile.mkstemp(prefix=".transfer-", suffix=".tmp", dir=self.manifest_dir)
        try:
            with os.fdopen(fd, "w") as output:
                json.dump(manifest, output, sort_keys=True)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary_path, self._manifest_path(manifest["transfer_id"]))
        except Exception:
            if os.path.exists(temporary_path):
                os.remove(temporary_path)
            raise

    def _reset_partial(self, manifest):
        partial_path = self._partial_path(manifest["transfer_id"])
        if partial_path.exists():
            partial_path.unlink()
        manifest["offset"] = 0
        manifest["state"] = "active"
        manifest["updated_at"] = self._now()
        self._write_manifest(manifest)

    def _load(self, transfer_id):
        manifest_path = self._manifest_path(transfer_id)
        if not manifest_path.exists():
            raise KeyError(f"Unknown transfer ID: {transfer_id}")
        with open(manifest_path) as source:
            manifest = json.load(source)
        if manifest.get("transfer_id") != transfer_id:
            raise ValueError("Transfer manifest identity mismatch")
        final_path = self._final_path(manifest)
        manifest["final_path"] = str(final_path)
        if manifest.get("state") == "finalizing" and final_path.is_file():
            manifest["state"] = "complete"
            manifest["offset"] = manifest["total_size"]
            manifest["updated_at"] = self._now()
            self._write_manifest(manifest)
        return manifest

    @staticmethod
    def _public_status(manifest):
        return {
            "transfer_id": manifest["transfer_id"],
            "job_id": manifest["job_id"],
            "filename": manifest["filename"],
            "offset": int(manifest["offset"]),
            "total_size": int(manifest["total_size"]),
            "complete": manifest.get("state") == "complete",
            "final_path": manifest["final_path"] if manifest.get("state") == "complete" else None,
        }

    def begin(self, job_id, filename, total_size, expected_checksum, metadata=None):
        filename = os.path.basename(filename)
        if not filename or filename in {".", ".."}:
            raise ValueError("Invalid transfer filename")
        total_size = int(total_size)
        if total_size < 0:
            raise ValueError("Transfer size cannot be negative")
        transfer_id = self._transfer_id(job_id, filename, total_size)
        with self._lock:
            manifest_path = self._manifest_path(transfer_id)
            if manifest_path.exists():
                manifest = self._load(transfer_id)
                if manifest["expected_checksum"] != expected_checksum:
                    raise ValueError("Transfer checksum does not match existing session")
                partial_path = self._partial_path(transfer_id)
                if manifest.get("state") == "active":
                    actual_size = partial_path.stat().st_size if partial_path.exists() else 0
                    if actual_size > int(manifest["total_size"]):
                        self._reset_partial(manifest)
                    else:
                        manifest["offset"] = actual_size
                        self._write_manifest(manifest)
                return self._public_status(manifest)

            final_path = self.completed_dir / transfer_id / filename
            manifest = {
                "version": 1,
                "transfer_id": transfer_id,
                "job_id": job_id,
                "filename": filename,
                "total_size": total_size,
                "expected_checksum": expected_checksum,
                "metadata": dict(metadata or {}),
                "offset": 0,
                "state": "active",
                "final_path": str(final_path),
                "updated_at": self._now(),
            }
            self._write_manifest(manifest)
            return self._public_status(manifest)

    def get_manifest(self, transfer_id):
        with self._lock:
            return dict(self._load(transfer_id))

    def status(self, transfer_id):
        with self._lock:
            manifest = self._load(transfer_id)
            if manifest.get("state") == "active":
                partial_path = self._partial_path(transfer_id)
                manifest["offset"] = partial_path.stat().st_size if partial_path.exists() else 0
            return self._public_status(manifest)

    def append(self, transfer_id, offset, data, chunk_checksum):
        with self._lock:
            manifest = self._load(transfer_id)
            if manifest.get("state") != "active":
                raise ValueError("Transfer is already complete")
            partial_path = self._partial_path(transfer_id)
            current_offset = partial_path.stat().st_size if partial_path.exists() else 0
            if int(offset) != current_offset:
                raise ValueError(f"Transfer offset mismatch: expected {current_offset}, got {offset}")
            if self._checksum(data) != chunk_checksum:
                raise ValueError("Transfer chunk checksum mismatch")
            if current_offset + len(data) > int(manifest["total_size"]):
                raise ValueError("Transfer chunk exceeds declared size")
            with open(partial_path, "ab") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            manifest["offset"] = current_offset + len(data)
            manifest["updated_at"] = self._now()
            self._write_manifest(manifest)
            return self._public_status(manifest)

    def finalize(self, transfer_id):
        with self._lock:
            manifest = self._load(transfer_id)
            if manifest.get("state") == "complete":
                return Path(manifest["final_path"])
            partial_path = self._partial_path(transfer_id)
            actual_size = partial_path.stat().st_size if partial_path.exists() else 0
            if actual_size != int(manifest["total_size"]):
                raise ValueError(f"Transfer size mismatch: expected {manifest['total_size']}, got {actual_size}")
            if actual_size == 0:
                partial_path.touch(exist_ok=True)
            if self._file_checksum(partial_path) != manifest["expected_checksum"]:
                self._reset_partial(manifest)
                raise ValueError("Transfer checksum mismatch")

            final_path = self._final_path(manifest)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            manifest["state"] = "finalizing"
            manifest["updated_at"] = self._now()
            self._write_manifest(manifest)
            os.replace(partial_path, final_path)  # NOSONAR - both paths are derived within the transfer root
            manifest["state"] = "complete"
            manifest["offset"] = manifest["total_size"]
            manifest["updated_at"] = self._now()
            self._write_manifest(manifest)
            return final_path

    def cleanup_stale(self, max_age_seconds):
        cutoff = self._now() - max(0, int(max_age_seconds))
        removed = []
        with self._lock:
            for manifest_path in self.manifest_dir.glob("*.json"):
                try:
                    with open(manifest_path) as source:
                        manifest = json.load(source)
                except (OSError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                if manifest.get("state") == "complete" or float(manifest.get("updated_at", 0)) >= cutoff:
                    continue
                transfer_id = manifest["transfer_id"]
                partial_path = self._partial_path(transfer_id)
                if partial_path.exists():
                    partial_path.unlink()
                shutil.rmtree(self.completed_dir / transfer_id, ignore_errors=True)
                manifest_path.unlink()
                removed.append(transfer_id)
        return removed

    def summary(self):
        """Return cheap transfer counters for the operations status API."""
        result = {"active": 0, "complete": 0, "corrupt": 0, "bytes_received": 0, "bytes_total": 0}
        with self._lock:
            for manifest_path in self.manifest_dir.glob("*.json"):
                try:
                    with open(manifest_path) as source:
                        manifest = json.load(source)
                    state = "complete" if manifest.get("state") == "complete" else "active"
                    result[state] += 1
                    offset = int(manifest.get("offset", 0))
                    if state == "active":
                        partial_path = self._partial_path(manifest["transfer_id"])
                        offset = partial_path.stat().st_size if partial_path.exists() else 0
                    result["bytes_received"] += offset
                    result["bytes_total"] += int(manifest.get("total_size", 0))
                except (OSError, TypeError, ValueError, json.JSONDecodeError):
                    result["corrupt"] += 1
        return result
