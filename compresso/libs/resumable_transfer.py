#!/usr/bin/env python3

"""Crash-safe chunked file transfers with persistent resume offsets."""

import hashlib
import json
import math
import os
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any

from compresso.libs.json_state import atomic_json_write

MANIFEST_GLOB = "*.json"


class TransferStorageError(OSError):
    """Raised before a transfer would consume reserved cache capacity."""

    def __init__(self, message, *, free_bytes=None, required_bytes=None, reserved_bytes=None):
        super().__init__(message)
        self.free_bytes = free_bytes
        self.required_bytes = required_bytes
        self.reserved_bytes = reserved_bytes


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:  # NOSONAR - callers supply validated task or transfer-store paths
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


class ResumableTransferStore:
    _locks_guard = threading.Lock()
    _locks_by_root: dict[str, Any] = {}

    def __init__(
        self,
        root_dir,
        now=time.time,
        fault_injector=None,
        *,
        maximum_file_size_bytes=None,
        minimum_free_bytes=0,
        disk_usage=shutil.disk_usage,
    ):
        self.root_dir = Path(root_dir).resolve()
        self.partial_dir = self.root_dir / "partial"
        self.completed_dir = self.root_dir / "completed"
        self.manifest_dir = self.root_dir / "manifests"
        self._now = now
        self._fault_injector = fault_injector
        self.maximum_file_size_bytes = None if maximum_file_size_bytes is None else max(0, int(maximum_file_size_bytes))
        self.minimum_free_bytes = max(0, int(minimum_free_bytes))
        self._disk_usage = disk_usage
        with self._locks_guard:
            self._lock = self._locks_by_root.setdefault(str(self.root_dir), threading.RLock())
        for directory in (self.partial_dir, self.completed_dir, self.manifest_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def _inject_fault(self, operation, path):
        if self._fault_injector is not None:
            self._fault_injector(operation, path)

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

    def _validate_manifest(self, manifest, transfer_id):
        if not isinstance(manifest, dict):
            raise ValueError("Transfer manifest must be an object")
        if manifest.get("version") != 1 or manifest.get("transfer_id") != transfer_id:
            raise ValueError("Transfer manifest identity mismatch")
        state = manifest.get("state")
        if state not in {"active", "finalizing", "complete"}:
            raise ValueError("Transfer manifest state is invalid")
        try:
            total_size = manifest["total_size"]
            offset = manifest["offset"]
        except KeyError as error:
            raise ValueError("Transfer manifest sizes are invalid") from error
        if (
            not isinstance(total_size, int)
            or isinstance(total_size, bool)
            or not isinstance(offset, int)
            or isinstance(offset, bool)
            or total_size < 0
            or offset < 0
            or offset > total_size
        ):
            raise ValueError("Transfer manifest sizes are invalid")
        if state in {"finalizing", "complete"} and offset != total_size:
            raise ValueError("Transfer manifest terminal offset is invalid")
        checksum = manifest.get("expected_checksum")
        if not isinstance(checksum, str) or re.fullmatch(r"sha256:[a-f0-9]{64}", checksum) is None:
            raise ValueError("Transfer manifest checksum is invalid")
        if not isinstance(manifest.get("job_id"), str) or not manifest["job_id"]:
            raise ValueError("Transfer manifest job identity is invalid")
        if not isinstance(manifest.get("metadata"), dict):
            raise ValueError("Transfer manifest metadata is invalid")
        updated_at = manifest.get("updated_at")
        if (
            not isinstance(updated_at, (int, float))
            or isinstance(updated_at, bool)
            or not math.isfinite(updated_at)
            or updated_at < 0
        ):
            raise ValueError("Transfer manifest timestamp is invalid")
        self._final_path(manifest)
        return manifest

    def _active_partial_size(self, manifest):
        partial_path = self._partial_path(manifest["transfer_id"])
        size = partial_path.stat().st_size if partial_path.exists() else 0
        if size > manifest["total_size"]:
            raise ValueError("Transfer partial artifact exceeds its declared size")
        return size

    def _active_reserved_bytes(self, *, exclude_transfer_id=None):
        reserved = 0
        for manifest_path in self.manifest_dir.glob(MANIFEST_GLOB):
            transfer_id = manifest_path.stem
            if transfer_id == exclude_transfer_id:
                continue
            try:
                manifest = self._load(transfer_id)
                if manifest.get("state") != "active":
                    continue
                reserved += int(manifest["total_size"]) - self._active_partial_size(manifest)
            except (KeyError, OSError, TypeError, ValueError) as exc:
                raise TransferStorageError(
                    "Transfer capacity cannot be reserved while existing session state is invalid"
                ) from exc
        return reserved

    def _ensure_new_session_capacity(self, transfer_id, total_size):
        if self.maximum_file_size_bytes is not None and total_size > self.maximum_file_size_bytes:
            raise ValueError("Transfer exceeds the configured maximum file size")
        try:
            free_bytes = int(self._disk_usage(self.root_dir).free)
        except OSError as exc:
            raise TransferStorageError("Transfer cache free space could not be checked") from exc
        reserved_bytes = self._active_reserved_bytes(exclude_transfer_id=transfer_id)
        required_bytes = self.minimum_free_bytes + reserved_bytes + total_size
        if free_bytes < required_bytes:
            raise TransferStorageError(
                "Transfer cache capacity is already reserved by active sessions",
                free_bytes=free_bytes,
                required_bytes=required_bytes,
                reserved_bytes=reserved_bytes,
            )

    def _ensure_chunk_capacity(self, chunk_size):
        try:
            free_bytes = int(self._disk_usage(self.root_dir).free)
        except OSError as exc:
            raise TransferStorageError("Transfer cache free space could not be checked") from exc
        required_bytes = self.minimum_free_bytes + max(0, int(chunk_size))
        if free_bytes < required_bytes:
            raise TransferStorageError(
                "Transfer chunk would breach the cache disk reserve",
                free_bytes=free_bytes,
                required_bytes=required_bytes,
            )

    @staticmethod
    def _artifact_matches_manifest(path, manifest, *, checksum=False):
        try:
            if not path.is_file() or path.stat().st_size != int(manifest["total_size"]):
                return False
            return not checksum or file_sha256(path) == manifest["expected_checksum"]
        except OSError:
            return False

    def _write_manifest(self, manifest):
        atomic_json_write(self._manifest_path(manifest["transfer_id"]), manifest, mode=0o600)

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
        self._validate_manifest(manifest, transfer_id)
        final_path = self._final_path(manifest)
        manifest["final_path"] = str(final_path)
        if manifest.get("state") == "finalizing" and final_path.is_file():
            if not self._artifact_matches_manifest(final_path, manifest, checksum=True):
                raise ValueError("Finalizing transfer artifact failed integrity validation")
            manifest["state"] = "complete"
            manifest["offset"] = manifest["total_size"]
            manifest["updated_at"] = self._now()
            self._write_manifest(manifest)
        if manifest.get("state") == "complete" and not self._artifact_matches_manifest(final_path, manifest):
            raise ValueError("Completed transfer artifact is missing or has the wrong size")
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
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("Invalid transfer job identity")
        filename = os.path.basename(filename)
        if not filename or filename in {".", ".."}:
            raise ValueError("Invalid transfer filename")
        if not isinstance(total_size, int) or isinstance(total_size, bool):
            raise ValueError("Transfer size must be an integer")
        if total_size < 0:
            raise ValueError("Transfer size cannot be negative")
        if not isinstance(expected_checksum, str) or re.fullmatch(r"sha256:[a-f0-9]{64}", expected_checksum) is None:
            raise ValueError("Invalid transfer checksum")
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

            self._ensure_new_session_capacity(transfer_id, total_size)
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
                manifest["offset"] = self._active_partial_size(manifest)
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
            self._ensure_chunk_capacity(len(data))
            self._inject_fault("append", partial_path)
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
            self._inject_fault("final_replace", final_path)
            os.replace(partial_path, final_path)  # NOSONAR - both paths are derived within the transfer root
            manifest["state"] = "complete"
            manifest["offset"] = manifest["total_size"]
            manifest["updated_at"] = self._now()
            self._write_manifest(manifest)
            return final_path

    def _remove_artifacts(self, transfer_id):
        self._partial_path(transfer_id).unlink(missing_ok=True)
        shutil.rmtree(self.completed_dir / transfer_id, ignore_errors=True)
        self._manifest_path(transfer_id).unlink(missing_ok=True)

    def abandon(self, transfer_id):
        """Intentionally discard one incomplete transfer and all owned artifacts."""
        with self._lock:
            manifest = self._load(transfer_id)
            if manifest.get("state") == "complete":
                raise ValueError("Completed transfers cannot be abandoned")
            self._remove_artifacts(transfer_id)
            return {"transfer_id": transfer_id, "abandoned": True}

    def cleanup_stale(self, max_age_seconds):
        cutoff = self._now() - max(0, int(max_age_seconds))
        removed = []
        with self._lock:
            for manifest_path in self.manifest_dir.glob(MANIFEST_GLOB):
                try:
                    transfer_id = manifest_path.stem
                    self._validate_transfer_id(transfer_id)
                    with open(manifest_path) as source:
                        manifest = json.load(source)
                    self._validate_manifest(manifest, transfer_id)
                    updated_at = float(manifest.get("updated_at", 0))
                except (KeyError, OSError, TypeError, ValueError, OverflowError):
                    transfer_id = manifest_path.stem
                    if re.fullmatch(r"[a-f0-9]{32}", transfer_id):
                        self._partial_path(transfer_id).unlink(missing_ok=True)
                        shutil.rmtree(self.completed_dir / transfer_id, ignore_errors=True)
                        removed.append(transfer_id)
                    manifest_path.unlink(missing_ok=True)
                    continue
                if manifest.get("state") == "complete":
                    if self._artifact_matches_manifest(self._final_path(manifest), manifest):
                        continue
                elif updated_at >= cutoff:
                    continue
                self._remove_artifacts(transfer_id)
                removed.append(transfer_id)
        return removed

    def summary(self):
        """Return cheap transfer counters for the operations status API."""
        result = {"active": 0, "complete": 0, "corrupt": 0, "bytes_received": 0, "bytes_total": 0}
        with self._lock:
            for manifest_path in self.manifest_dir.glob(MANIFEST_GLOB):
                try:
                    with open(manifest_path) as source:
                        manifest = json.load(source)
                    transfer_id = manifest_path.stem
                    self._validate_transfer_id(transfer_id)
                    self._validate_manifest(manifest, transfer_id)
                    state = "complete" if manifest.get("state") == "complete" else "active"
                    if state == "complete" and not self._artifact_matches_manifest(self._final_path(manifest), manifest):
                        raise ValueError("completed artifact is unavailable")
                    result[state] += 1
                    offset = int(manifest.get("offset", 0))
                    if state == "active":
                        offset = self._active_partial_size(manifest)
                    result["bytes_received"] += offset
                    result["bytes_total"] += int(manifest.get("total_size", 0))
                except (KeyError, OSError, TypeError, ValueError, OverflowError):
                    result["corrupt"] += 1
        return result
