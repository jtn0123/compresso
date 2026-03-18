#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.healthcheck.py

    Health check manager for validating media file integrity.

"""

import datetime
import os
import subprocess
import threading

from unmanic.libs.ffprobe_utils import probe_file
from unmanic.libs.logs import UnmanicLogging
from unmanic.libs.unmodels.healthstatus import HealthStatus


class HealthCheckManager:
    """
    Manages health checking of media files.
    """

    _lock = threading.Lock()
    _scanning = False
    _scan_progress = {'total': 0, 'checked': 0, 'library_id': None}

    def __init__(self):
        self.logger = UnmanicLogging.get_logger(name=__class__.__name__)

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
                error_lines = [l for l in stderr.split('\n') if l.strip()]
                error_count = len(error_lines)
                if error_count > 10:
                    return False, "Decode produced {} errors: {}".format(error_count, '; '.join(error_lines[:3]))

            return True, ""

        except subprocess.TimeoutExpired:
            return False, "Thorough check timed out (>600s)"
        except Exception as e:
            return False, "Check failed: {}".format(str(e))

    def check_file(self, filepath, library_id=1, mode='quick'):
        """
        Check a single file and store the result.

        :param filepath: Absolute path
        :param library_id: Library ID
        :param mode: 'quick' or 'thorough'
        :return: dict with status info
        """
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

        # Update result
        health.status = 'healthy' if is_healthy else 'corrupted'
        health.error_detail = error_detail
        health.last_checked = datetime.datetime.now()
        if not is_healthy:
            health.error_count = health.error_count + 1
        health.save()

        return {
            'abspath': filepath,
            'status': health.status,
            'check_mode': mode,
            'error_detail': error_detail,
            'last_checked': str(health.last_checked),
            'error_count': health.error_count,
        }

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

        records_total = HealthStatus.select().count()
        records_filtered = query.count()

        if order:
            col = order.get('column', 'last_checked')
            direction = order.get('dir', 'desc')
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

        thread = threading.Thread(
            target=self._run_library_scan,
            args=(library_id, mode),
            daemon=True,
        )
        thread.start()
        return True

    def _run_library_scan(self, library_id, mode):
        """Run library scan in background thread."""
        try:
            from unmanic.libs.unmodels import Libraries
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
            }

            files_to_check = []
            for root, _dirs, files in os.walk(library_path):
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in media_extensions:
                        files_to_check.append(os.path.join(root, filename))

            HealthCheckManager._scan_progress = {
                'total': len(files_to_check),
                'checked': 0,
                'library_id': library_id,
            }

            self.logger.info("Health scan: checking %d files in library %s", len(files_to_check), library_id)

            for filepath in files_to_check:
                try:
                    self.check_file(filepath, library_id=library_id, mode=mode)
                except Exception as e:
                    self.logger.error("Health check failed for %s: %s", filepath, str(e))

                HealthCheckManager._scan_progress['checked'] += 1

            self.logger.info("Health scan complete for library %s", library_id)

        except Exception as e:
            self.logger.error("Library scan failed: %s", str(e))
        finally:
            with self._lock:
                HealthCheckManager._scanning = False

    @classmethod
    def is_scanning(cls):
        return cls._scanning

    @classmethod
    def get_scan_progress(cls):
        return dict(cls._scan_progress)
