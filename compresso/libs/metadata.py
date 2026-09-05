#!/usr/bin/env python3

"""
compresso.metadata.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     03 Feb 2026

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

import json
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from datetime import datetime
from typing import TypedDict, cast

from peewee import DoesNotExist, fn

from compresso.libs import common
from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_write
from compresso.libs.unmodels import FileMetadata, FileMetadataPaths, TaskMetadata, Tasks

ObjectDict = dict[str, object]


class ScopedMetadata(TypedDict):
    source: dict[str, object]
    destination: dict[str, object]
    __meta__: dict[str, object]


class TaskCacheEntry(TypedDict):
    staged: object
    staged_loaded: bool
    file: dict[str, object]
    file_loaded: bool
    source_path: str | None
    fingerprint: str | None
    fingerprint_algo: str | None
    source_plugins: set[str]
    source_fingerprint: str | None
    source_fingerprint_algo: str | None
    source_path_at_set: str | None


class PathCacheEntry(TypedDict):
    fingerprint: str
    fingerprint_algo: str
    metadata: dict[str, object]
    created_at: float
    last_accessed: float


class FingerprintGroup(TypedDict):
    algo: str
    paths: list[str]
    scope: str


class _MetadataContext(threading.local):
    plugin_id: str | None = None
    task_id: int | None = None
    path: str | None = None


class CompressoFileMetadata:
    """
    Thread-safe metadata access for plugins.
    """

    MAX_PLUGIN_JSON_BYTES = 32 * 1024
    CACHE_MAX_ENTRIES = 2000
    CACHE_TTL_SECONDS = 300
    CACHE_PRUNE_INTERVAL_SECONDS = 60

    _lock = threading.RLock()
    _ctx = _MetadataContext()
    _logger = CompressoLogging.get_logger(name="CompressoFileMetadata")
    _main_pid = os.getpid()

    _task_cache: dict[int, TaskCacheEntry] = {}
    _task_cache_timestamps: dict[int, float] = {}
    _path_cache: OrderedDict[str, PathCacheEntry] = OrderedDict()
    _last_prune: float = 0

    @classmethod
    def _ensure_main_process(cls) -> None:
        if os.getpid() != cls._main_pid:
            raise RuntimeError("CompressoFileMetadata is only available in the main process")

    @classmethod
    def bind_runner_context(cls, plugin_id: str, task_id: int | None = None, path: str | None = None) -> None:
        cls._ensure_main_process()
        cls._ctx.plugin_id = plugin_id
        cls._ctx.task_id = task_id
        cls._ctx.path = path

    @classmethod
    def clear_context(cls) -> None:
        cls._ctx.plugin_id = None
        cls._ctx.task_id = None
        cls._ctx.path = None

    @classmethod
    def _get_context(cls) -> tuple[str, int | None, str | None]:
        plugin_value: object = getattr(cls._ctx, "plugin_id", None)
        if not isinstance(plugin_value, str) or not plugin_value:
            raise RuntimeError("Metadata context not bound to a plugin_id")
        task_value: object = getattr(cls._ctx, "task_id", None)
        path_value: object = getattr(cls._ctx, "path", None)
        task_id = task_value if isinstance(task_value, int) else None
        path = path_value if isinstance(path_value, str) else None
        return plugin_value, task_id, path

    @classmethod
    def _load_json_dict(cls, raw_json: str | None) -> dict[str, object]:
        if not raw_json:
            return {}
        try:
            data = json.loads(raw_json)
        except (json.JSONDecodeError, TypeError) as e:
            cls._logger.debug("Failed to parse metadata JSON: %s", e)
            return {}
        if not isinstance(data, dict):
            return {}
        if not all(isinstance(key, str) for key in data):
            return {}
        return cast(ObjectDict, data)

    @classmethod
    def _dump_json_dict(cls, data: object) -> str:
        if not isinstance(data, Mapping):
            raise ValueError("Metadata JSON must be a dict")
        return json.dumps(data)

    @classmethod
    def _enforce_plugin_size_limit(cls, plugin_data: Mapping[str, object]) -> None:
        encoded = json.dumps(plugin_data).encode("utf-8")
        if len(encoded) > cls.MAX_PLUGIN_JSON_BYTES:
            raise ValueError(f"Plugin metadata exceeds size limit ({cls.MAX_PLUGIN_JSON_BYTES} bytes)")

    @classmethod
    def _prune_task_cache(cls) -> None:
        """Evict stale entries from _task_cache when it exceeds CACHE_MAX_ENTRIES."""
        if len(cls._task_cache) <= cls.CACHE_MAX_ENTRIES:
            return
        now = time.time()
        stale_ids = [tid for tid, ts in cls._task_cache_timestamps.items() if (now - ts) > cls.CACHE_TTL_SECONDS]
        for tid in stale_ids:
            cls._task_cache.pop(tid, None)
            cls._task_cache_timestamps.pop(tid, None)
        # If still over max, evict oldest entries
        if len(cls._task_cache) > cls.CACHE_MAX_ENTRIES:
            sorted_entries = sorted(cls._task_cache_timestamps.items(), key=lambda x: x[1])
            to_evict = len(cls._task_cache) - cls.CACHE_MAX_ENTRIES
            for tid, _ in sorted_entries[:to_evict]:
                cls._task_cache.pop(tid, None)
                cls._task_cache_timestamps.pop(tid, None)

    @classmethod
    def _ensure_task_cache_entry(cls, task_id: int) -> TaskCacheEntry:
        entry = cls._task_cache.get(task_id)
        if entry is None:
            cls._prune_task_cache()
            entry = TaskCacheEntry(
                staged={},
                staged_loaded=False,
                file={},
                file_loaded=False,
                source_path=None,
                fingerprint=None,
                fingerprint_algo=None,
                source_plugins=set(),
                source_fingerprint=None,
                source_fingerprint_algo=None,
                source_path_at_set=None,
            )
            cls._task_cache[task_id] = entry
        cls._task_cache_timestamps[task_id] = time.time()
        return entry

    @classmethod
    def _load_task_metadata(cls, task_id: int) -> dict[str, object]:
        entry = cls._ensure_task_cache_entry(task_id)
        if entry["staged_loaded"]:
            staged = entry["staged"]
            return staged if isinstance(staged, dict) else {}

        try:
            row = TaskMetadata.get(TaskMetadata.task == task_id)
            entry["staged"] = cls._load_json_dict(row.json_blob)
        except DoesNotExist:
            entry["staged"] = {}
        entry["staged_loaded"] = True
        staged = entry["staged"]
        return staged if isinstance(staged, dict) else {}

    @classmethod
    def _normalize_scoped_staged(cls, staged: object) -> ScopedMetadata:
        if not isinstance(staged, dict):
            return ScopedMetadata(source={}, destination={}, __meta__={})
        if "source" in staged or "destination" in staged or "__meta__" in staged:
            source = staged.get("source") or {}
            destination = staged.get("destination") or {}
            meta = staged.get("__meta__") or {}
            if not isinstance(source, dict):
                source = {}
            if not isinstance(destination, dict):
                destination = {}
            if not isinstance(meta, dict):
                meta = {}
            return ScopedMetadata(
                source=cast(ObjectDict, source),
                destination=cast(ObjectDict, destination),
                __meta__=cast(ObjectDict, meta),
            )

        # Legacy format: plugin_id -> dict. Treat as source scope.
        return ScopedMetadata(source=cast(ObjectDict, staged), destination={}, __meta__={})

    @classmethod
    def _load_task_source_path(cls, task_id: int) -> str | None:
        entry = cls._ensure_task_cache_entry(task_id)
        if entry["source_path"]:
            return entry["source_path"]
        try:
            task = Tasks.get_by_id(task_id)
            entry["source_path"] = task.abspath
        except DoesNotExist:
            cls._logger.debug("Task %s not found while loading source path", task_id)
            entry["source_path"] = None
        return entry["source_path"]

    @classmethod
    def _load_file_metadata_for_task(cls, task_id: int) -> dict[str, object]:
        entry = cls._ensure_task_cache_entry(task_id)
        if entry["file_loaded"]:
            return entry["file"]

        source_path = cls._load_task_source_path(task_id)
        if not source_path or not os.path.exists(source_path):
            entry["file"] = {}
            entry["file_loaded"] = True
            return entry["file"]

        fingerprint, algo = common.get_file_fingerprint(source_path)
        entry["fingerprint"] = fingerprint
        entry["fingerprint_algo"] = algo

        try:
            row = FileMetadata.get(FileMetadata.fingerprint == fingerprint)
            entry["file"] = cls._load_json_dict(row.metadata_json)
        except DoesNotExist:
            entry["file"] = {}
        entry["file_loaded"] = True
        return entry["file"]

    @classmethod
    def _prune_path_cache(cls, now: float) -> None:
        if now - cls._last_prune < cls.CACHE_PRUNE_INTERVAL_SECONDS:
            return
        cls._last_prune = now

        expired = []
        for key, entry in cls._path_cache.items():
            if now - entry.get("last_accessed", now) > cls.CACHE_TTL_SECONDS:
                expired.append(key)
        for key in expired:
            cls._path_cache.pop(key, None)

        while len(cls._path_cache) > cls.CACHE_MAX_ENTRIES:
            cls._path_cache.popitem(last=False)

    @classmethod
    def _get_cached_path_entry(cls, path: str) -> PathCacheEntry | None:
        now = time.time()
        with cls._lock:
            cls._prune_path_cache(now)
            entry = cls._path_cache.get(path)
            if not entry:
                return None
            entry["last_accessed"] = now
            cls._path_cache.move_to_end(path)
            return entry

    @classmethod
    def _set_cached_path_entry(cls, path: str, entry: PathCacheEntry) -> None:
        now = time.time()
        entry["created_at"] = now
        entry["last_accessed"] = now
        with cls._lock:
            cls._path_cache[path] = entry
            cls._path_cache.move_to_end(path)
            cls._prune_path_cache(now)

    @staticmethod
    def _plugin_metadata(value: object) -> dict[str, object]:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            return {}
        return cast(ObjectDict, value)

    @classmethod
    def get(cls, plugin_id_override: str | None = None) -> dict[str, object]:
        cls._ensure_main_process()
        plugin_id, task_id, path = cls._get_context()
        if plugin_id_override:
            plugin_id = plugin_id_override

        if task_id is not None:
            staged = cls._load_task_metadata(task_id)
            staged_scoped = cls._normalize_scoped_staged(staged)
            file_data = cls._load_file_metadata_for_task(task_id)
            merged = dict(file_data)
            merged.update(staged_scoped.get("source", {}))
            merged.update(staged_scoped.get("destination", {}))
            return deepcopy(cls._plugin_metadata(merged.get(plugin_id, {})))

        if not path:
            raise RuntimeError("Metadata context requires a task_id or path")

        cached = cls._get_cached_path_entry(path)
        if cached:
            return deepcopy(cls._plugin_metadata(cached["metadata"].get(plugin_id, {})))

        if not os.path.exists(path):
            return {}

        fingerprint, algo = common.get_file_fingerprint(path)
        try:
            row = FileMetadata.get(FileMetadata.fingerprint == fingerprint)
            metadata = cls._load_json_dict(row.metadata_json)
        except DoesNotExist:
            metadata = {}

        entry = PathCacheEntry(
            fingerprint=fingerprint,
            fingerprint_algo=algo,
            metadata=metadata,
            created_at=0,
            last_accessed=0,
        )
        cls._set_cached_path_entry(path, entry)
        return deepcopy(cls._plugin_metadata(metadata.get(plugin_id, {})))

    @classmethod
    def set(cls, data: object, use_source_scope: bool = False) -> None:
        cls._ensure_main_process()
        plugin_id, task_id, _ = cls._get_context()
        if task_id is None:
            raise RuntimeError("Metadata set() requires a task_id context")
        if not isinstance(data, dict):
            raise ValueError("Metadata set() requires a dict")
        if not all(isinstance(key, str) for key in data):
            raise ValueError("Metadata keys must be strings")
        updates = cast(ObjectDict, data)

        with cls._lock:
            cls._set_locked(task_id, plugin_id, updates, use_source_scope)

    @classmethod
    def _set_locked(cls, task_id: int, plugin_id: str, updates: ObjectDict, use_source_scope: bool) -> None:
        entry = cls._ensure_task_cache_entry(task_id)
        staged_scoped = cls._normalize_scoped_staged(cls._load_task_metadata(task_id))
        scope_blob = staged_scoped["source"] if use_source_scope else staged_scoped["destination"]
        plugin_data = scope_blob.get(plugin_id, {})
        if not isinstance(plugin_data, dict):
            plugin_data = {}
        for key, value in updates.items():
            if value is None:
                plugin_data.pop(key, None)
            else:
                plugin_data[key] = deepcopy(value)
        cls._enforce_plugin_size_limit(plugin_data)
        scope_blob[plugin_id] = plugin_data
        if use_source_scope:
            cls._record_source_fingerprint(task_id, staged_scoped)
        entry["staged"] = staged_scoped
        entry["staged_loaded"] = True
        cls._persist_staged_metadata(task_id, staged_scoped)

    @classmethod
    def _record_source_fingerprint(cls, task_id: int, staged_scoped: ScopedMetadata) -> None:
        meta = staged_scoped.get("__meta__", {})
        if meta.get("source_fingerprint"):
            return
        source_path = cls._load_task_source_path(task_id)
        meta["source_path_at_set"] = source_path
        if source_path and os.path.exists(source_path):
            fingerprint, algo = common.get_file_fingerprint(source_path)
            meta["source_fingerprint"] = fingerprint
            meta["source_fingerprint_algo"] = algo
        else:
            cls._logger.info("Unable to fingerprint source path for metadata set: %s", source_path)
        staged_scoped["__meta__"] = meta

    @classmethod
    def _persist_staged_metadata(cls, task_id: int, staged_scoped: ScopedMetadata) -> None:
        get_or_create = cast("Callable[..., tuple[TaskMetadata, bool]]", TaskMetadata.get_or_create)
        row, created = get_or_create(
            task=task_id,
            defaults={"json_blob": cls._dump_json_dict(staged_scoped), "updated_at": datetime.now()},
        )
        if not created:
            row.json_blob = cls._dump_json_dict(staged_scoped)
            row.updated_at = datetime.now()
            row.save()

    @classmethod
    def _upsert_path(cls, file_metadata_id: int, path: str | None, path_type: str) -> None:
        if not path:
            return
        now = datetime.now()
        execute_write(
            FileMetadataPaths.update(
                path_type=path_type,
                updated_at=now,
            ).where((FileMetadataPaths.file_metadata == file_metadata_id) & (FileMetadataPaths.path == path))
        )

        row = FileMetadataPaths.get_or_none(
            (FileMetadataPaths.file_metadata == file_metadata_id) & (FileMetadataPaths.path == path)
        )
        if not row:
            FileMetadataPaths.create(
                file_metadata=file_metadata_id,
                path=path,
                path_type=path_type,
                created_at=now,
                updated_at=now,
            )

    @classmethod
    def commit_task(
        cls,
        task_id: int,
        task_success: bool,
        source_path: str,
        destination_paths: Sequence[str] | None = None,
    ) -> int:
        cls._ensure_main_process()
        with cls._lock:
            staged = cls._load_task_metadata(task_id)
            if not staged:
                try:
                    execute_write(TaskMetadata.delete().where(TaskMetadata.task == task_id))
                except Exception as e:
                    cls._logger.debug("Could not clean up task metadata for task %s: %s", task_id, e)
                cls._task_cache.pop(task_id, None)
                cls._task_cache_timestamps.pop(task_id, None)
                return 0

            cls._ensure_task_cache_entry(task_id)
            staged_scoped = cls._normalize_scoped_staged(staged)
            source_staged = staged_scoped.get("source", {})
            destination_staged = staged_scoped.get("destination", {})
            meta = staged_scoped.get("__meta__", {})

        destination_paths = destination_paths or []
        destination_paths = [p for p in destination_paths if p]

        fingerprint_groups = cls._metadata_fingerprint_groups(
            task_id, task_success, destination_paths, destination_staged, source_staged, source_path, meta
        )

        # NOTE: SqliteQueueDatabase does not support atomic() transactions.
        # Write serialization is provided by the queue database's single writer thread.
        # The cls._lock protects in-memory cache consistency across app threads.
        with cls._lock:
            for fingerprint, data in fingerprint_groups.items():
                staged_payload = source_staged if data.get("scope") == "source" else destination_staged
                cls._persist_metadata_group(fingerprint, data, staged_payload, task_id, source_path, meta)

            execute_write(TaskMetadata.delete().where(TaskMetadata.task == task_id))
            cls._task_cache.pop(task_id, None)
            cls._task_cache_timestamps.pop(task_id, None)
        return len(fingerprint_groups)

    @classmethod
    def _persist_metadata_group(
        cls,
        fingerprint: str,
        data: FingerprintGroup,
        staged_payload: ObjectDict,
        task_id: int,
        source_path: str,
        meta: ObjectDict,
    ) -> None:
        if not staged_payload:
            return
        try:
            row = FileMetadata.get(FileMetadata.fingerprint == fingerprint)
            existing = cls._load_json_dict(row.metadata_json)
            existing.update(deepcopy(staged_payload))
            row.metadata_json = cls._dump_json_dict(existing)
            row.fingerprint_algo = data["algo"]
            row.updated_at = datetime.now()
            row.last_task_id = task_id
            row.save()
        except DoesNotExist:
            row = FileMetadata.create(
                fingerprint=fingerprint,
                fingerprint_algo=data["algo"],
                metadata_json=cls._dump_json_dict(staged_payload),
                created_at=datetime.now(),
                updated_at=datetime.now(),
                last_task_id=task_id,
            )
        paths = data["paths"]
        if data.get("scope") == "source":
            configured_path = meta.get("source_path_at_set")
            cls._upsert_path(row.id, configured_path if isinstance(configured_path, str) else source_path, "source")
            return
        for path in paths:
            cls._upsert_path(row.id, path, "destination")
        if paths:
            cls._upsert_path(row.id, paths[-1], "last_seen")

    @classmethod
    def _metadata_fingerprint_groups(
        cls,
        task_id: int,
        task_success: bool,
        destination_paths: Sequence[str],
        destination_staged: ObjectDict,
        source_staged: ObjectDict,
        source_path: str,
        meta: ObjectDict,
    ) -> dict[str, FingerprintGroup]:
        groups = cls._destination_fingerprint_groups(task_success, destination_paths, destination_staged)
        if not source_staged:
            return groups
        configured_path = meta.get("source_path_at_set")
        source_path_at_set = configured_path if isinstance(configured_path, str) else source_path
        if not source_path_at_set or not os.path.exists(source_path_at_set):
            cls._logger.info("Source file missing at metadata commit for task %s", task_id)
            return groups
        fingerprint = meta.get("source_fingerprint")
        algorithm = meta.get("source_fingerprint_algo")
        if not isinstance(fingerprint, str):
            fingerprint, algorithm = common.get_file_fingerprint(source_path_at_set)
        algorithm = algorithm if isinstance(algorithm, str) else "sampled_xxhash_v1"
        group = groups.setdefault(fingerprint, {"algo": algorithm, "paths": [], "scope": "source"})
        if source_path_at_set not in group["paths"]:
            group["paths"].append(source_path_at_set)
        return groups

    @staticmethod
    def _destination_fingerprint_groups(
        task_success: bool, destination_paths: Sequence[str], destination_staged: ObjectDict
    ) -> dict[str, FingerprintGroup]:
        groups: dict[str, FingerprintGroup] = {}
        if not task_success or not destination_staged:
            return groups
        for path in destination_paths:
            if not os.path.exists(path):
                continue
            fingerprint, algorithm = common.get_file_fingerprint(path)
            group = groups.setdefault(fingerprint, {"algo": algorithm, "paths": [], "scope": "destination"})
            if path not in group["paths"]:
                group["paths"].append(path)
        return groups

    @classmethod
    def find_by_path(cls, path: str | None) -> list[dict[str, object]]:
        cls._ensure_main_process()
        if not path:
            return []
        search_value = path.strip()
        if not search_value:
            return []
        path_rows = FileMetadataPaths.select(FileMetadataPaths.file_metadata).where(
            fn.LOWER(FileMetadataPaths.path).contains(search_value.lower())
        )
        metadata_ids = list({row.file_metadata.id for row in path_rows})
        if not metadata_ids:
            return []

        path_map: dict[int, list[dict[str, str]]] = {}
        for path_row in FileMetadataPaths.select().where(FileMetadataPaths.file_metadata.in_(metadata_ids)):
            path_map.setdefault(path_row.file_metadata.id, []).append(
                {
                    "path": path_row.path,
                    "path_type": path_row.path_type,
                }
            )

        results: list[dict[str, object]] = []
        for metadata_row in FileMetadata.select().where(FileMetadata.id.in_(metadata_ids)):
            results.append(
                {
                    "fingerprint": metadata_row.fingerprint,
                    "fingerprint_algo": metadata_row.fingerprint_algo,
                    "metadata_json": cls._load_json_dict(metadata_row.metadata_json),
                    "last_task_id": metadata_row.last_task_id,
                    "paths": path_map.get(metadata_row.id, []),
                }
            )
        return results

    @classmethod
    def find_all(cls) -> list[dict[str, object]]:
        cls._ensure_main_process()
        path_map: dict[int, list[dict[str, str]]] = {}
        for path_row in FileMetadataPaths.select():
            path_map.setdefault(path_row.file_metadata.id, []).append(
                {
                    "path": path_row.path,
                    "path_type": path_row.path_type,
                }
            )

        results: list[dict[str, object]] = []
        for metadata_row in FileMetadata.select():
            results.append(
                {
                    "fingerprint": metadata_row.fingerprint,
                    "fingerprint_algo": metadata_row.fingerprint_algo,
                    "metadata_json": cls._load_json_dict(metadata_row.metadata_json),
                    "last_task_id": metadata_row.last_task_id,
                    "paths": path_map.get(metadata_row.id, []),
                }
            )
        return results

    @classmethod
    def delete_for_plugin(cls, fingerprint: str | None, plugin_id: str | None = None) -> bool:
        cls._ensure_main_process()
        if not fingerprint:
            return False
        try:
            row = FileMetadata.get(FileMetadata.fingerprint == fingerprint)
        except DoesNotExist:
            return False

        if not plugin_id:
            row.delete_instance()
            return True

        data = cls._load_json_dict(row.metadata_json)
        data.pop(plugin_id, None)
        row.metadata_json = cls._dump_json_dict(data)
        row.updated_at = datetime.now()
        row.save()
        return True
