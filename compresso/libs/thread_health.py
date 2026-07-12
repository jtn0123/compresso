"""Small, thread-safe health telemetry for long-running service loops."""

import threading
import time


class ThreadHealthMixin:
    def _init_thread_health(self):
        self._health_lock = threading.Lock()
        self._last_heartbeat_at = time.time()
        self._last_success_at = None
        self._last_error_at = None
        self._last_error = None
        self._consecutive_failures = 0

    def _mark_thread_heartbeat(self):
        with self._health_lock:
            self._last_heartbeat_at = time.time()

    def _mark_thread_success(self):
        now = time.time()
        with self._health_lock:
            self._last_heartbeat_at = now
            self._last_success_at = now
            self._consecutive_failures = 0

    def _mark_thread_error(self, error):
        now = time.time()
        with self._health_lock:
            self._last_heartbeat_at = now
            self._last_error_at = now
            self._last_error = str(error)
            self._consecutive_failures += 1

    def get_health_snapshot(self):
        with self._health_lock:
            return {
                "last_heartbeat_at": self._last_heartbeat_at,
                "last_success_at": self._last_success_at,
                "last_error_at": self._last_error_at,
                "last_error": self._last_error,
                "consecutive_failures": self._consecutive_failures,
            }
