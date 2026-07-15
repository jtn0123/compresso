#!/usr/bin/env python3

"""
compresso.healthcheck.py

Health check manager for validating media file integrity.

"""

import datetime
import math
import os
import queue
import subprocess
import threading
import time
from contextlib import contextmanager

from compresso.config import Config
from compresso.libs.ffprobe_utils import probe_file
from compresso.libs.logs import CompressoLogging
from compresso.libs.unmodels.healthstatus import HealthStatus
from compresso.webserver.helpers.library_analysis import iter_media_files


def _initial_scan_progress(library_id=None, max_workers=1):
    return {
        "phase": "idle" if library_id is None else "discovering",
        "total": 0,
        "discovered": 0,
        "discovery_complete": False,
        "checked": 0,
        "cancelled": False,
        "error": None,
        "library_id": library_id,
        "worker_count": 0,
        "max_workers": max_workers,
        "workers": {},
        "start_time": None if library_id is None else time.time(),
        "files_per_second": 0.0,
        "eta_seconds": 0,
    }


class HealthCheckManager:
    """
    Manages health checking of media files.
    """

    _lock = threading.Lock()
    _scanning = False
    _cancel_event = threading.Event()
    _scan_progress: dict = _initial_scan_progress()
    _worker_count_requested = 1
    _retire_worker_ids: set[int] = set()

    _file_locks: dict = {}
    _file_lock_users: dict = {}
    _file_locks_lock = threading.Lock()

    def __init__(self):
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)

    def quick_check(self, filepath):
        """
        Quick check: validate file with ffprobe.
        Returns (is_healthy, error_detail).

        :param filepath: Absolute path to the media file
        :return: tuple (bool, str)
        """
        if not os.path.exists(filepath):
            return False, "File not found"

        result = probe_file(filepath, timeout=60)
        if result is None:
            return False, "ffprobe failed to parse file"

        streams = result.get("streams", [])
        if not streams:
            return False, "No streams found in file"

        fmt = result.get("format", {})
        duration = fmt.get("duration")
        if duration is not None:
            try:
                dur = float(duration)
                if not math.isfinite(dur) or dur <= 0:
                    return False, "File has zero or negative or invalid duration"
            except (ValueError, TypeError):
                pass

        return True, ""

    def thorough_check(self, filepath):
        """
        Thorough check: decode entire file with ffmpeg and count error lines.
        Returns (is_healthy, error_detail).

        :param filepath: Absolute path to the media file
        :return: tuple (bool, str)
        """
        if not os.path.exists(filepath):
            return False, "File not found"

        cmd = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            filepath,
            "-f",
            "null",
            "-",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)  # noqa: S603 - trusted ffmpeg command built internally
            stderr = result.stderr.strip() if result.stderr else ""

            if result.returncode != 0:
                error_lines = stderr.split("\n") if stderr else ["Unknown error"]
                return False, "; ".join(error_lines[:5])

            if stderr:
                error_lines = [line for line in stderr.split("\n") if line.strip()]
                error_count = len(error_lines)
                if error_count > 10:
                    return False, f"Decode produced {error_count} errors: {'; '.join(error_lines[:3])}"
                if error_count >= 1:
                    return "warning", f"Decode produced {error_count} warning(s): {'; '.join(error_lines[:3])}"

            return True, ""

        except subprocess.TimeoutExpired:
            return False, "Thorough check timed out (>600s)"
        except Exception as e:
            return False, f"Check failed: {str(e)}"

    def _get_file_lock(self, filepath):
        """Get or create a lock for a specific file path."""
        with HealthCheckManager._file_locks_lock:
            if filepath not in HealthCheckManager._file_locks:
                HealthCheckManager._file_locks[filepath] = threading.Lock()
            return HealthCheckManager._file_locks[filepath]

    @contextmanager
    def _hold_file_lock(self, filepath):
        with HealthCheckManager._file_locks_lock:
            file_lock = HealthCheckManager._file_locks.setdefault(filepath, threading.Lock())
            HealthCheckManager._file_lock_users[filepath] = HealthCheckManager._file_lock_users.get(filepath, 0) + 1
        try:
            with file_lock:
                yield
        finally:
            with HealthCheckManager._file_locks_lock:
                remaining = HealthCheckManager._file_lock_users.get(filepath, 1) - 1
                if remaining <= 0:
                    HealthCheckManager._file_lock_users.pop(filepath, None)
                    if HealthCheckManager._file_locks.get(filepath) is file_lock:
                        HealthCheckManager._file_locks.pop(filepath, None)
                else:
                    HealthCheckManager._file_lock_users[filepath] = remaining

    def check_file(self, filepath, library_id=1, mode="quick"):
        """
        Check a single file and store the result.

        :param filepath: Absolute path
        :param library_id: Library ID
        :param mode: 'quick' or 'thorough'
        :return: dict with status info
        """
        with self._hold_file_lock(filepath):
            # Mark as checking
            health, _ = HealthStatus.get_or_create(
                abspath=filepath, defaults={"library_id": library_id, "status": "checking", "check_mode": mode}
            )
            health.status = "checking"
            health.check_mode = mode
            health.library_id = library_id
            health.save()

            # Run check
            if mode == "thorough":
                is_healthy, error_detail = self.thorough_check(filepath)
            else:
                is_healthy, error_detail = self.quick_check(filepath)

            # Update result — thorough_check may return 'warning' as is_healthy
            if is_healthy == "warning":
                health.status = "warning"
            elif is_healthy:
                health.status = "healthy"
            else:
                health.status = "corrupted"
            health.error_detail = error_detail
            health.last_checked = datetime.datetime.now()
            if health.status in ("corrupted", "warning"):
                health.error_count = health.error_count + 1
            health.save()

            result = {
                "abspath": filepath,
                "status": health.status,
                "check_mode": mode,
                "error_detail": error_detail,
                "last_checked": str(health.last_checked),
                "error_count": health.error_count,
            }

        return result

    def get_health_summary(self, library_id=None):
        """
        Get aggregate health status counts.

        :param library_id: Optional library ID filter
        :return: dict with counts per status
        """
        from peewee import fn

        query = HealthStatus.select(
            HealthStatus.status,
            fn.COUNT(HealthStatus.id).alias("count"),
        )

        if library_id is not None:
            query = query.where(HealthStatus.library_id == library_id)

        query = query.group_by(HealthStatus.status)

        result = {
            "healthy": 0,
            "corrupted": 0,
            "warning": 0,
            "unchecked": 0,
            "checking": 0,
            "total": 0,
        }

        for row in query:
            status = row.status
            count = row.count
            if status in result:
                result[status] = count
            result["total"] += count

        return result

    def get_health_statuses_paginated(
        self, start=0, length=10, search_value=None, library_id=None, status_filter=None, order=None
    ):
        """
        Get paginated health status records.

        :return: dict with recordsTotal, recordsFiltered, results
        """
        query = HealthStatus.select()

        if library_id is not None:
            query = query.where(HealthStatus.library_id == library_id)

        if status_filter:
            query = query.where(HealthStatus.status == status_filter)

        if search_value:
            query = query.where(HealthStatus.abspath.contains(search_value))

        records_total_query = HealthStatus.select()
        if library_id is not None:
            records_total_query = records_total_query.where(HealthStatus.library_id == library_id)
        records_total = records_total_query.count()
        records_filtered = query.count()

        ALLOWED_ORDER_COLUMNS = {"last_checked", "abspath", "status", "check_mode", "library_id", "error_count"}

        if order:
            col = order.get("column", "last_checked")
            direction = order.get("dir", "desc")
            if col not in ALLOWED_ORDER_COLUMNS:
                col = "last_checked"
            order_field = getattr(HealthStatus, col, HealthStatus.last_checked)
            query = query.order_by(order_field.asc()) if direction == "asc" else query.order_by(order_field.desc())
        else:
            query = query.order_by(HealthStatus.last_checked.desc())

        if length:
            query = query.limit(length).offset(start)

        results = []
        for row in query:
            results.append(
                {
                    "id": row.id,
                    "abspath": row.abspath,
                    "library_id": row.library_id,
                    "status": row.status,
                    "check_mode": row.check_mode or "",
                    "error_detail": row.error_detail or "",
                    "last_checked": str(row.last_checked) if row.last_checked else "",
                    "error_count": row.error_count,
                }
            )

        return {
            "recordsTotal": records_total,
            "recordsFiltered": records_filtered,
            "results": results,
        }

    def schedule_library_scan(self, library_id, mode="quick"):
        """
        Start a background scan of all files in a library.

        :param library_id: Library ID to scan
        :param mode: 'quick' or 'thorough'
        :return: True if scan started, False if already scanning
        """
        with self._lock:
            if self._scanning:
                return False
            HealthCheckManager._scanning = True
            HealthCheckManager._cancel_event.clear()
            HealthCheckManager._retire_worker_ids.clear()
            HealthCheckManager._scan_progress = _initial_scan_progress(
                library_id=library_id,
                max_workers=HealthCheckManager._worker_count_requested,
            )

        thread = threading.Thread(
            target=self._run_library_scan,
            args=(library_id, mode),
            daemon=True,
        )
        thread.start()
        return True

    def _scan_worker(self, worker_id, file_queue, library_id, mode, discovery_done=None):
        """Worker thread that pulls files from the queue and checks them."""
        if discovery_done is None:
            discovery_done = threading.Event()
            discovery_done.set()
        with HealthCheckManager._lock:
            HealthCheckManager._scan_progress["workers"][worker_id] = {
                "status": "idle",
                "current_file": "",
            }

        while True:
            with HealthCheckManager._lock:
                retire_requested = worker_id in HealthCheckManager._retire_worker_ids
            if HealthCheckManager._cancel_event.is_set() or retire_requested:
                break

            try:
                filepath = file_queue.get(timeout=0.1)
            except queue.Empty:
                if discovery_done.is_set():
                    break
                continue

            with HealthCheckManager._lock:
                HealthCheckManager._scan_progress["workers"][worker_id] = {
                    "status": "checking",
                    "current_file": filepath,
                }

            try:
                self.check_file(filepath, library_id=library_id, mode=mode)
            except Exception as e:
                self.logger.error("Health check failed for %s: %s", filepath, str(e))
            finally:
                file_queue.task_done()
                self._record_checked_file()

        with HealthCheckManager._lock:
            HealthCheckManager._scan_progress["workers"].pop(worker_id, None)
            HealthCheckManager._retire_worker_ids.discard(worker_id)

    @staticmethod
    def _record_checked_file():
        with HealthCheckManager._lock:
            progress = HealthCheckManager._scan_progress
            progress["checked"] += 1
            checked = progress["checked"]
            start_time = progress["start_time"]
            if not start_time or checked <= 0:
                return
            elapsed = time.time() - start_time
            fps = checked / elapsed if elapsed > 0 else 0.0
            progress["files_per_second"] = round(fps, 2)
            if not progress["discovery_complete"]:
                progress["eta_seconds"] = 0
                return
            remaining = max(0, progress["total"] - checked)
            progress["eta_seconds"] = int(remaining / fps) if fps > 0 else 0

    @staticmethod
    def _drain_scan_queue(file_queue):
        while True:
            try:
                file_queue.get_nowait()
            except queue.Empty:
                return
            else:
                file_queue.task_done()

    def _discover_media(self, library_path, file_queue, discovery_done, discovery_errors):
        completed = False
        try:
            for filepath in iter_media_files(library_path, cancel_event=HealthCheckManager._cancel_event):
                if HealthCheckManager._cancel_event.is_set():
                    break
                with HealthCheckManager._lock:
                    progress = HealthCheckManager._scan_progress
                    progress["discovered"] += 1
                    progress["total"] = progress["discovered"]
                while not HealthCheckManager._cancel_event.is_set():
                    try:
                        file_queue.put(str(filepath), timeout=0.1)
                    except queue.Full:
                        continue
                    break
            completed = not HealthCheckManager._cancel_event.is_set()
        except Exception as error:
            discovery_errors.append(error)
            self.logger.error("Health scan discovery failed: %s", str(error))
        finally:
            with HealthCheckManager._lock:
                progress = HealthCheckManager._scan_progress
                progress["discovery_complete"] = completed and not discovery_errors
                if progress["discovery_complete"]:
                    progress["phase"] = "checking"
            discovery_done.set()

    def _start_scan_worker(self, worker_id, workers, file_queue, library_id, mode, discovery_done):
        worker = threading.Thread(
            target=self._scan_worker,
            args=(worker_id, file_queue, library_id, mode, discovery_done),
            daemon=True,
            name=f"HealthCheck-{library_id}-{worker_id}",
        )
        workers[worker_id] = worker
        worker.start()

    def _sync_worker_pool(self, workers, next_worker_id, file_queue, library_id, mode, discovery_done):
        live_ids = [worker_id for worker_id, worker in workers.items() if worker.is_alive()]
        with HealthCheckManager._lock:
            requested = HealthCheckManager._worker_count_requested
            active_ids = [worker_id for worker_id in live_ids if worker_id not in HealthCheckManager._retire_worker_ids]
            if len(active_ids) > requested:
                retiring = sorted(active_ids, reverse=True)[: len(active_ids) - requested]
                HealthCheckManager._retire_worker_ids.update(retiring)
                for worker_id in retiring:
                    worker_progress = HealthCheckManager._scan_progress["workers"].get(worker_id)
                    if worker_progress is not None:
                        worker_progress["retiring"] = True
                active_ids = [worker_id for worker_id in active_ids if worker_id not in retiring]
            HealthCheckManager._scan_progress["worker_count"] = len(live_ids)
            HealthCheckManager._scan_progress["max_workers"] = requested

        may_have_work = not discovery_done.is_set() or not file_queue.empty()
        for _ in range(max(0, requested - len(active_ids)) if may_have_work else 0):
            self._start_scan_worker(next_worker_id, workers, file_queue, library_id, mode, discovery_done)
            next_worker_id += 1
        return next_worker_id

    @staticmethod
    def _finish_scan(phase, error=None):
        with HealthCheckManager._lock:
            progress = HealthCheckManager._scan_progress
            progress["phase"] = phase
            progress["cancelled"] = phase == "cancelled"
            progress["error"] = error
            progress["worker_count"] = 0
            progress["eta_seconds"] = 0
            if phase == "complete":
                progress["discovery_complete"] = True

    def _run_library_scan(self, library_id, mode):
        """Stream library discovery through a bounded, live-scalable worker pool."""
        with HealthCheckManager._lock:
            HealthCheckManager._scan_progress = _initial_scan_progress(
                library_id=library_id,
                max_workers=HealthCheckManager._worker_count_requested,
            )
            HealthCheckManager._retire_worker_ids.clear()
        try:
            from compresso.libs.unmodels import Libraries

            try:
                library = Libraries.get_by_id(library_id)
                library_path = library.path
            except Exception as error:
                self.logger.error("Library %s not found", library_id)
                self._finish_scan("failed", f"Library {library_id} not found: {error}")
                return

            file_queue = queue.Queue(maxsize=Config().get_library_scan_queue_limit())
            discovery_done = threading.Event()
            discovery_errors = []
            workers = {}
            producer = threading.Thread(
                target=self._discover_media,
                args=(library_path, file_queue, discovery_done, discovery_errors),
                daemon=True,
                name=f"HealthDiscovery-{library_id}",
            )
            producer.start()
            next_worker_id = 0

            while True:
                next_worker_id = self._sync_worker_pool(workers, next_worker_id, file_queue, library_id, mode, discovery_done)
                if HealthCheckManager._cancel_event.is_set():
                    self._drain_scan_queue(file_queue)
                live_workers = any(worker.is_alive() for worker in workers.values())
                if discovery_done.is_set() and file_queue.empty() and not live_workers:
                    break
                time.sleep(0.05)

            producer.join(timeout=5.0)
            for worker in workers.values():
                worker.join(timeout=5.0)

            if discovery_errors:
                self._finish_scan("failed", str(discovery_errors[0]))
            elif HealthCheckManager._cancel_event.is_set():
                self.logger.info("Health scan cancelled for library %s", library_id)
                self._finish_scan("cancelled")
            else:
                self.logger.info("Health scan complete for library %s", library_id)
                self._finish_scan("complete")

        except Exception as e:
            self.logger.error("Library scan failed: %s", str(e))
            self._finish_scan("failed", str(e))
        finally:
            with self._lock:
                HealthCheckManager._scanning = False
                HealthCheckManager._cancel_event.clear()
                HealthCheckManager._retire_worker_ids.clear()
            with HealthCheckManager._file_locks_lock:
                HealthCheckManager._file_locks.clear()
                HealthCheckManager._file_lock_users.clear()

    @classmethod
    def is_scanning(cls):
        return cls._scanning

    @classmethod
    def get_scan_progress(cls):
        import copy

        with cls._lock:
            return copy.deepcopy(cls._scan_progress)

    @classmethod
    def set_worker_count(cls, count):
        """Set target worker count (1-16)."""
        with cls._lock:
            cls._worker_count_requested = max(1, min(16, count))

    @classmethod
    def cancel_scan(cls):
        """Request cancellation of the current library scan."""
        with cls._lock:
            if cls._scanning:
                cls._cancel_event.set()
                cls._scan_progress["phase"] = "cancelling"
                return True
            return False

    @classmethod
    def get_worker_count(cls):
        with cls._lock:
            return cls._worker_count_requested
