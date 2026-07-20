#!/usr/bin/env python3

"""Synthetic, metadata-only large-library scanner and SQLite benchmark."""

import math
import os
import platform
import sqlite3
import tempfile
import threading
import time
import tracemalloc
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from compresso.libs.json_state import atomic_json_write
from compresso.libs.libraryscanner import iter_sorted_library_directories


def synthetic_walk(entry_count: int, files_per_directory: int = 1_000) -> Iterator[tuple[str, list[str], list[str]]]:
    """Generate bounded directory metadata without creating media files on disk."""
    for directory_index, start in enumerate(range(0, entry_count, files_per_directory)):
        batch_size = min(files_per_directory, entry_count - start)
        files = [f"media_{index:09d}.mkv" for index in range(start, start + batch_size)]
        yield f"/synthetic/library/dir_{directory_index:06d}", [], files


class _RssSampler:
    def __init__(self):
        self.process = psutil.Process()
        self.baseline = self.process.memory_info().rss
        self.peak = self.baseline
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, name="LibraryScaleRssSampler", daemon=True)

    def _sample(self):
        while not self._stop.wait(0.01):
            self.peak = max(self.peak, self.process.memory_info().rss)

    def start(self):
        self._thread.start()

    def stop(self):
        self.peak = max(self.peak, self.process.memory_info().rss)
        self._stop.set()
        self._thread.join(timeout=1)


def _percentile(values: list[float], percentile: float = 0.95) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _create_database(connection: sqlite3.Connection):
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA busy_timeout=5000;
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            abspath TEXT NOT NULL UNIQUE,
            library_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            priority INTEGER NOT NULL
        );
        CREATE INDEX tasks_status_priority ON tasks(status, priority);
        CREATE INDEX tasks_library_id ON tasks(library_id);
        """
    )


def _measure_query_latency(connection: sqlite3.Connection, entry_count: int) -> tuple[float, float]:
    lookup_latencies = []
    page_latencies = []
    sample_count = min(100, max(20, entry_count))
    for sample in range(sample_count):
        task_id = 1 + ((sample * 7_919) % entry_count)
        started = time.perf_counter()
        connection.execute("SELECT abspath, status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        lookup_latencies.append((time.perf_counter() - started) * 1_000)

        started = time.perf_counter()
        page_offset = min((sample * entry_count) // sample_count, max(0, entry_count - 100))
        connection.execute(
            "SELECT id, abspath, priority FROM tasks WHERE status = ? ORDER BY priority LIMIT 100 OFFSET ?",
            ("pending", page_offset),
        ).fetchall()
        page_latencies.append((time.perf_counter() - started) * 1_000)
    return _percentile(lookup_latencies), _percentile(page_latencies)


def run_benchmark(entry_count: int, batch_size: int = 1_000) -> dict[str, object]:
    """Enumerate synthetic scan metadata and schedule it into an indexed SQLite queue."""
    if entry_count < 1:
        raise ValueError("entry_count must be positive")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    rss = _RssSampler()
    tracemalloc.start()
    rss.start()
    started = time.perf_counter()
    inserted = 0

    try:
        with tempfile.TemporaryDirectory(prefix="compresso-library-scale-") as temp_dir:
            database_path = Path(temp_dir) / "tasks.db"
            connection = sqlite3.connect(database_path)
            try:
                _create_database(connection)
                pending_rows = []
                with connection:
                    walk = synthetic_walk(entry_count, files_per_directory=batch_size)
                    for root, files in iter_sorted_library_directories(walk):
                        for filename in files:
                            pending_rows.append((os.path.join(root, filename), 1, "pending", inserted))
                            inserted += 1
                        connection.executemany(
                            "INSERT INTO tasks(abspath, library_id, status, priority) VALUES (?, ?, ?, ?)",
                            pending_rows,
                        )
                        pending_rows.clear()

                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                lookup_p95_ms, page_p95_ms = _measure_query_latency(connection, entry_count)
                database_bytes = database_path.stat().st_size
                stored_count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            finally:
                connection.close()
    finally:
        duration_seconds = time.perf_counter() - started
        _current, peak_python_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss.stop()

    if inserted != entry_count or stored_count != entry_count:
        raise RuntimeError(f"scheduled {inserted} entries but SQLite contains {stored_count}")

    bytes_per_entry = database_bytes / entry_count
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "machine": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "logical_cpus": psutil.cpu_count(),
        },
        "entry_count": entry_count,
        "batch_size": batch_size,
        "duration_seconds": round(duration_seconds, 4),
        "entries_per_second": round(entry_count / duration_seconds, 2),
        "peak_python_mb": round(peak_python_bytes / (1024 * 1024), 2),
        "baseline_rss_mb": round(rss.baseline / (1024 * 1024), 2),
        "peak_rss_mb": round(rss.peak / (1024 * 1024), 2),
        "peak_rss_delta_mb": round((rss.peak - rss.baseline) / (1024 * 1024), 2),
        "database_mb": round(database_bytes / (1024 * 1024), 2),
        "database_bytes_per_entry": round(bytes_per_entry, 2),
        "sqlite_lookup_p95_ms": round(lookup_p95_ms, 4),
        "sqlite_page_p95_ms": round(page_p95_ms, 4),
    }


def run_real_pipeline_benchmark(entry_count: int, batch_size: int = 1_000) -> dict[str, object]:
    """
    Schedule entries through the real peewee task pipeline.

    Unlike run_benchmark (a synthetic floor for raw SQLite scheduling), this
    tier exercises the code a production scan actually runs per queued file:
    the Tasks model insert through SqliteQueueDatabase's writer queue (with
    duplicates rejected by the UNIQUE abspath constraint, as in production),
    cache-path assignment, the library priority lookup, and the pending-status
    transition. ffprobe and plugin execution are intentionally excluded so the
    benchmark stays hermetic (no subprocesses or network).
    """
    if entry_count < 1:
        raise ValueError("entry_count must be positive")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    # Imports are local so the synthetic benchmark stays importable without
    # dragging in the full application stack.
    from compresso import config
    from compresso.libs import task as task_lib
    from compresso.libs.unmodels import Libraries, Tasks
    from compresso.libs.unmodels.lib import Database

    rss = _RssSampler()
    tracemalloc.start()
    rss.start()
    started = time.perf_counter()
    queued = 0

    try:
        with tempfile.TemporaryDirectory(prefix="compresso-library-scale-real-") as temp_dir:
            temp = Path(temp_dir)
            library_dir = temp / "library"
            cache_dir = temp / "cache"
            library_dir.mkdir()
            cache_dir.mkdir()

            settings = config.Config(config_path=str(temp / "config"))
            settings.set_cache_path(str(cache_dir))

            database_path = temp / "tasks.db"
            db_connection = Database.select_database(
                {
                    "TYPE": "SQLITE",
                    "FILE": str(database_path),
                    "MIGRATIONS_DIR": str(temp / "migrations"),
                }
            )
            try:
                db_connection.create_tables([Tasks, Libraries])
                Libraries.create(id=1, name="ScaleBenchmark", path=str(library_dir))

                for root, _dirs, files in synthetic_walk(entry_count, files_per_directory=batch_size):
                    directory = library_dir / Path(root).name
                    directory.mkdir()
                    for filename in files:
                        file_path = directory / filename
                        file_path.touch()
                        abspath = str(file_path)
                        if task_lib.Task().create_task_by_absolute_path(abspath, library_id=1):
                            queued += 1
            finally:
                # Flush the queued writer before measuring read latency
                db_connection.obj.stop()
                db_connection.obj.close()

            read_connection = sqlite3.connect(database_path)
            try:
                lookup_p95_ms, page_p95_ms = _measure_query_latency(read_connection, entry_count)
                stored_count = read_connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            finally:
                read_connection.close()
            database_bytes = database_path.stat().st_size
    finally:
        duration_seconds = time.perf_counter() - started
        _current, peak_python_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss.stop()

    if queued != entry_count or stored_count != entry_count:
        raise RuntimeError(f"queued {queued} entries but SQLite contains {stored_count} (expected {entry_count})")

    return {
        "schema_version": 1,
        "mode": "real_pipeline",
        "recorded_at": datetime.now(UTC).isoformat(),
        "machine": {
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "logical_cpus": psutil.cpu_count(),
        },
        "entry_count": entry_count,
        "batch_size": batch_size,
        "duration_seconds": round(duration_seconds, 4),
        "entries_per_second": round(entry_count / duration_seconds, 2),
        "peak_python_mb": round(peak_python_bytes / (1024 * 1024), 2),
        "baseline_rss_mb": round(rss.baseline / (1024 * 1024), 2),
        "peak_rss_mb": round(rss.peak / (1024 * 1024), 2),
        "peak_rss_delta_mb": round((rss.peak - rss.baseline) / (1024 * 1024), 2),
        "database_mb": round(database_bytes / (1024 * 1024), 2),
        "database_bytes_per_entry": round(database_bytes / entry_count, 2),
        "sqlite_lookup_p95_ms": round(lookup_p95_ms, 4),
        "sqlite_page_p95_ms": round(page_p95_ms, 4),
    }


def matching_threshold(entry_count: int, threshold_config: dict[str, Any]) -> dict[str, float]:
    tiers = threshold_config.get("tiers", {})
    if not isinstance(tiers, dict):
        raise ValueError("threshold configuration has no tiers object")
    if not tiers:
        raise ValueError("threshold configuration has no tier entries")
    eligible = sorted(int(count) for count in tiers if int(count) >= entry_count)
    tier_key = str(eligible[0] if eligible else max(int(count) for count in tiers))
    selected = tiers[tier_key]
    if not isinstance(selected, dict):
        raise ValueError(f"threshold tier {tier_key} is not an object")
    return {str(name): float(value) for name, value in selected.items()}


def threshold_failures(result: dict[str, object], thresholds: dict[str, float]) -> list[str]:
    checks = {
        "duration_seconds": "max_duration_seconds",
        "peak_rss_delta_mb": "max_peak_rss_delta_mb",
        "sqlite_lookup_p95_ms": "max_sqlite_lookup_p95_ms",
        "sqlite_page_p95_ms": "max_sqlite_page_p95_ms",
    }
    failures = []
    for result_name, threshold_name in checks.items():
        result_value = result[result_name]
        if not isinstance(result_value, int | float):
            raise ValueError(f"benchmark result {result_name} is not numeric")
        actual = float(result_value)
        allowed = float(thresholds[threshold_name])
        if actual > allowed:
            failures.append(f"{result_name}={actual} exceeded {threshold_name}={allowed}")

    # Optional throughput floor: guards against per-entry regressions that a
    # generous wall-clock ceiling would let through.
    if "min_entries_per_second" in thresholds:
        eps_value = result["entries_per_second"]
        if not isinstance(eps_value, int | float):
            raise ValueError("benchmark result entries_per_second is not numeric")
        eps = float(eps_value)
        floor = float(thresholds["min_entries_per_second"])
        if eps < floor:
            failures.append(f"entries_per_second={eps} fell below min_entries_per_second={floor}")
    return failures


def write_result(result: dict[str, object], output_path: Path):
    atomic_json_write(output_path, result, mode=0o600)
