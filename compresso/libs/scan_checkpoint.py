#!/usr/bin/env python3

"""Small durable journal for restartable library scans."""

import json
import os
import threading
import time
from contextlib import suppress
from pathlib import PurePosixPath, PureWindowsPath
from typing import TypedDict, cast

from compresso.libs.json_state import atomic_json_write

CHECKPOINT_MTIME_SLOP_NS = 2_000_000_000


class ScanCheckpoint(TypedDict):
    completed_root: str
    updated_at_ns: int


class ScanCheckpointStore:
    _locks_guard = threading.Lock()
    _locks_by_root: dict[str, threading.RLock] = {}

    def __init__(self, userdata_path: str | os.PathLike[str]) -> None:
        self.root = os.path.join(os.path.abspath(userdata_path), "scan-checkpoints")
        with self._locks_guard:
            self._lock = self._locks_by_root.setdefault(self.root, threading.RLock())

    def _path(self, library_id: int) -> str:
        return os.path.join(self.root, f"library-{int(library_id)}.json")

    def load(self, library_id: int, library_path: str | os.PathLike[str]) -> str | None:
        record = self.load_record(library_id, library_path)
        return record["completed_root"] if record else None

    def load_record(self, library_id: int, library_path: str | os.PathLike[str]) -> ScanCheckpoint | None:
        path = self._path(library_id)
        try:
            with self._lock, open(path, encoding="utf-8") as checkpoint_file:
                raw_data: object = json.load(checkpoint_file)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(raw_data, dict) or not all(isinstance(key, str) for key in raw_data):
            return None
        data = cast("dict[str, object]", raw_data)
        if data.get("library_path") != os.path.abspath(library_path):
            return None
        completed_root = data.get("completed_root")
        updated_at_ns = data.get("updated_at_ns")
        if not isinstance(completed_root, str) or not completed_root:
            return None
        posix_path = PurePosixPath(completed_root)
        windows_path = PureWindowsPath(completed_root)
        if posix_path.is_absolute() or windows_path.anchor or ".." in completed_root.replace("\\", "/").split("/"):
            return None
        if not isinstance(updated_at_ns, int) or isinstance(updated_at_ns, bool) or updated_at_ns <= 0:
            return None
        return {"completed_root": completed_root, "updated_at_ns": updated_at_ns}

    def save(self, library_id: int, library_path: str | os.PathLike[str], completed_root: str) -> None:
        os.makedirs(self.root, exist_ok=True)
        path = self._path(library_id)
        data: dict[str, object] = {
            "library_id": int(library_id),
            "library_path": os.path.abspath(library_path),
            "completed_root": completed_root,
            "updated_at": time.time(),
            "updated_at_ns": time.time_ns(),
        }
        with self._lock:
            atomic_json_write(path, data, mode=0o600)

    def clear(self, library_id: int) -> None:
        with self._lock, suppress(FileNotFoundError):
            os.unlink(self._path(library_id))
