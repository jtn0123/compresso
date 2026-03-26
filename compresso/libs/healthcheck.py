#!/usr/bin/env python3

"""
    compresso.healthcheck.py

    Health check manager for validating media file integrity.

"""

import datetime
import os
import queue
import subprocess
import threading
import time

from compresso.libs.ffprobe_utils import probe_file
from compresso.libs.logs import CompressoLogging
from compresso.libs.unmodels.healthstatus import HealthStatus


class HealthCheckManager:
    """
    Manages health checking of media files.
    """

    _lock = threading.Lock()
    _scanning = False
    _cancel_event = threading.Event()
    _scan_progress = {
        'total': 0,
        'checked': 0,
        'library_id': None,
        'worker_count': 0,
        'max_workers': 1,
        'workers': {},
        'start_time': None,
        'files_per_second': 0.0,
        'eta_seconds': 0,
    }
    _worker_count_requested = 1

    _file_locks = {}
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

        streams = result.get('streams', [])
        if not streams:
            return False, "No streams found in file"

        fmt = result.get('format', {})
        duration = fmt.get('duration')
        if duration is not None:
            try:
                dur = float(duration)
                if dur <= 0:
                    return False, "File has zero or negative duration"
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
            'ffmpeg',
            '-v', 'error',
            '-i', filepath,
            '-f', 'null',
            '-',
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            stderr = result.stderr.strip() if result.stderr else ''

            if result.returncode != 0:
                error_lines = stderr.split('\n') if stderr else ['Unknown error']
                return False, '; '.join(error_lines[:5])

            if stderr:
                error_lines = [line for line in stderr.split('\n') if line.strip()]
                error_count = len(error_lines)
                if error_count > 10:
                    return False, "Decode produced {} errors: {}".format(error_count, '; '.join(error_lines[:3]))
                if error_count >= 1:
                    return 'warning', "Decode produced {} warning(s): {}".format(error_count, '; '.join(error_lines[:3]))

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

    def check_file(self, filepath, library_id=1, mode='quick'):
        """
        Check a single file and store the result.

        :param filepath: Absolute path
        :param library_id: Library ID
        :param mode: 'quick' or 'thorough'
        :return: dict with status info
        """
        file_lock = self._get_file_lock(filepath)
        with file_lock:
            # Mark as checking
            health, _ = HealthStatus.get_or_create(
                abspath=filepath,
                defaults={'library_id': library_id, 'status': 'checking', 'check_mode': mode}
            )
            health.status = 'checking'
            health.check_mode = mode
            health.library_id = library_id
            health.save()

            # Run check
            if mode == 'thorough':
                is_healthy, error_detail = self.thorough_check(filepath)
            else:
                is_healthy, error_detail = self.quick_check(filepath)

            # Update result — thorough_check may return 'warning' as is_healthy
            if is_healthy == 'warning':
                health.status = 'warning'
            elif is_healthy:
                health.status = 'healthy'
            else:
                health.status = 'corrupted'
            health.error_detail = error_detail
            health.last_checked = datetime.datetime.now()
            if health.status in ('corrupted', 'warning'):
                health.error_count = health.error_count + 1
            health.save()

            result = {
                'abspath': filepath,
                'status': health.status,
                'check_mode': mode,
                'error_detail': error_detail,
                'last_checked': str(health.last_checked),
                'error_count': health.error_count,
            }

        # Release the per-file lock to prevent unbounded growth
        with HealthCheckManager._file_locks_lock:
            HealthCheckManager._file_locks.pop(filepath, None)

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
            fn.COUNT(HealthStatus.id).alias('count'),
        )

        if library_id is not None:
            query = query.where(HealthStatus.library_id == library_id)

        query = query.group_by(HealthStatus.status)

        result = {
            'healthy': 0,
            'corrupted': 0,
            'warning': 0,
            'unchecked': 0,
            'checking': 0,
            'total': 0,
        }

        for row in query:
            status = row.status
            count = row.count
            if status in result:
                result[status] = count
            result['total'] += count

        return result

    def get_health_statuses_paginated(self, start=0, length=10, search_value=None,
                                       library_id=None, status_filter=None, order=None):
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

        ALLOWED_ORDER_COLUMNS = {'last_checked', 'abspath', 'status', 'check_mode', 'library_id', 'error_count'}

        if order:
            col = order.get('column', 'last_checked')
            direction = order.get('dir', 'desc')
            if col not in ALLOWED_ORDER_COLUMNS:
                col = 'last_checked'
            order_field = getattr(HealthStatus, col, HealthStatus.last_checked)
            if direction == 'asc':
                query = query.order_by(order_field.asc())
            else:
                query = query.order_by(order_field.desc())
        else:
            query = query.order_by(HealthStatus.last_checked.desc())

        if length:
            query = query.limit(length).offset(start)

        results = []
        for row in query:
            results.append({
                'id': row.id,
                'abspath': row.abspath,
                'library_id': row.library_id,
                'status': row.status,
                'check_mode': row.check_mode or '',
                'error_detail': row.error_detail or '',
                'last_checked': str(row.last_checked) if row.last_checked else '',
                'error_count': row.error_count,
            })

        return {
            'recordsTotal': records_total,
            'recordsFiltered': records_filtered,
            'results': results,
        }

    def schedule_library_scan(self, library_id, mode='quick'):
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

        thread = threading.Thread(
            target=self._run_library_scan,
            args=(library_id, mode),
            daemon=True,
        )
        thread.start()
        return True

    def _scan_worker(self, worker_id, file_queue, library_id, mode):
        """Worker thread that pulls files from the queue and checks them."""
        with HealthCheckManager._lock:
            HealthCheckManager._scan_progress['workers'][worker_id] = {
                'status': 'idle',
                'current_file': '',
            }

        while True:
            # Check for cancellation
            if HealthCheckManager._cancel_event.is_set():
                break

            try:
                filepath = file_queue.get(timeout=0.5)
            except queue.Empty:
                # Queue is empty, worker is done
                break

            with HealthCheckManager._lock:
                HealthCheckManager._scan_progress['workers'][worker_id] = {
                    'status': 'checking',
                    'current_file': filepath,
                }

            try:
                self.check_file(filepath, library_id=library_id, mode=mode)
            except Exception as e:
                self.logger.error("Health check failed for %s: %s", filepath, str(e))

            with HealthCheckManager._lock:
                HealthCheckManager._scan_progress['checked'] += 1
                checked = HealthCheckManager._scan_progress['checked']
                start_time = HealthCheckManager._scan_progress['start_time']
                total = HealthCheckManager._scan_progress['total']
                if start_time and checked > 0:
                    elapsed = time.time() - start_time
                    fps = checked / elapsed if elapsed > 0 else 0.0
                    HealthCheckManager._scan_progress['files_per_second'] = round(fps, 2)
                    remaining = total - checked
                    HealthCheckManager._scan_progress['eta_seconds'] = int(remaining / fps) if fps > 0 else 0

        with HealthCheckManager._lock:
            HealthCheckManager._scan_progress['workers'][worker_id] = {
                'status': 'idle',
                'current_file': '',
            }

    def _run_library_scan(self, library_id, mode):
        """Run library scan in background thread using a worker pool."""
        try:
            from compresso.libs.unmodels import Libraries
            try:
                library = Libraries.get_by_id(library_id)
                library_path = library.path
            except Exception:
                self.logger.error("Library %s not found", library_id)
                return

            # Collect media files
            media_extensions = {
                '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm',
                '.m4v', '.mpg', '.mpeg', '.ts', '.vob', '.3gp',
                '.m2ts', '.mts', '.ogv', '.mxf', '.rmvb',
            }

            files_to_check = []
            for root, _dirs, files in os.walk(library_path):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in media_extensions:
                        files_to_check.append(os.path.join(root, filename))

            with HealthCheckManager._lock:
                HealthCheckManager._scan_progress = {
                    'total': len(files_to_check),
                    'checked': 0,
                    'library_id': library_id,
                    'worker_count': 0,
                    'max_workers': HealthCheckManager._worker_count_requested,
                    'workers': {},
                    'start_time': time.time(),
                    'files_per_second': 0.0,
                    'eta_seconds': 0,
                }

            self.logger.info("Health scan: checking %d files in library %s", len(files_to_check), library_id)

            if not files_to_check:
                self.logger.info("Health scan complete for library %s (no files)", library_id)
                return

            # Put all files into a queue
            file_queue = queue.Queue()
            for filepath in files_to_check:
                file_queue.put(filepath)

            # Spawn initial workers
            workers = []
            initial_count = HealthCheckManager._worker_count_requested
            for i in range(initial_count):
                t = threading.Thread(
                    target=self._scan_worker,
                    args=(i, file_queue, library_id, mode),
                    daemon=True,
                )
                t.start()
                workers.append(t)

            with HealthCheckManager._lock:
                HealthCheckManager._scan_progress['worker_count'] = initial_count

            next_worker_id = initial_count

            # Monitor loop: check for worker count changes and track alive workers
            while any(t.is_alive() for t in workers) or not file_queue.empty():
                if HealthCheckManager._cancel_event.is_set():
                    # Drain the queue to stop workers
                    while not file_queue.empty():
                        try:
                            file_queue.get_nowait()
                        except queue.Empty:
                            break
                    self.logger.info("Health scan cancelled for library %s", library_id)
                    break

                time.sleep(0.5)

                with HealthCheckManager._lock:
                    requested = HealthCheckManager._worker_count_requested
                    current_alive = sum(1 for t in workers if t.is_alive())
                    HealthCheckManager._scan_progress['worker_count'] = current_alive
                    HealthCheckManager._scan_progress['max_workers'] = requested

                # Spawn more workers if requested count increased and queue has items
                if current_alive < requested and not file_queue.empty():
                    new_count = requested - current_alive
                    for _ in range(new_count):
                        if file_queue.empty():
                            break
                        t = threading.Thread(
                            target=self._scan_worker,
                            args=(next_worker_id, file_queue, library_id, mode),
                            daemon=True,
                        )
                        t.start()
                        workers.append(t)
                        next_worker_id += 1

                # Break if queue is empty and no workers alive
                if file_queue.empty() and not any(t.is_alive() for t in workers):
                    break

            # Join all threads
            for t in workers:
                t.join(timeout=5.0)

            self.logger.info("Health scan complete for library %s", library_id)

        except Exception as e:
            self.logger.error("Library scan failed: %s", str(e))
        finally:
            with self._lock:
                HealthCheckManager._scanning = False
                HealthCheckManager._cancel_event.clear()
            with HealthCheckManager._file_locks_lock:
                HealthCheckManager._file_locks.clear()

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
                return True
            return False

    @classmethod
    def get_worker_count(cls):
        with cls._lock:
            return cls._worker_count_requested
