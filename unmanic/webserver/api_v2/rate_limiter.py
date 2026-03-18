#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.rate_limiter.py

    In-memory sliding window rate limiter for API endpoints.

"""

import threading
import time


class RateLimiter:
    """
    Sliding window rate limiter keyed by IP address.

    Default: 60 requests/minute for normal endpoints.
    Strict: 5 requests/minute for expensive endpoints.
    """

    DEFAULT_LIMIT = 60
    DEFAULT_WINDOW = 60  # seconds
    STRICT_LIMIT = 5
    STRICT_WINDOW = 60

    EXPENSIVE_PATHS = {
        '/preview/create',
        '/healthcheck/scan',
        '/healthcheck/scan-library',
    }

    def __init__(self):
        self._requests = {}  # {ip: [(timestamp, path), ...]}
        self._lock = threading.Lock()
        self._request_counter = 0

    def _cleanup_old(self, ip, window):
        """Remove requests outside the current window."""
        cutoff = time.time() - window
        if ip in self._requests:
            self._requests[ip] = [
                (ts, path) for ts, path in self._requests[ip] if ts > cutoff
            ]

    def is_expensive(self, path):
        """Check if a path matches an expensive endpoint."""
        for expensive in self.EXPENSIVE_PATHS:
            if path.endswith(expensive):
                return True
        return False

    def _cleanup_stale_ips(self):
        """Remove IPs that have no requests in the last 5 minutes."""
        cutoff = time.time() - 300
        stale = [ip for ip, reqs in self._requests.items()
                 if not reqs or max(ts for ts, _ in reqs) < cutoff]
        for ip in stale:
            del self._requests[ip]

    def check_rate_limit(self, ip, path):
        """
        Check if a request is within rate limits.

        Returns (allowed, remaining, reset_time) tuple.
        - allowed: True if request is within limits
        - remaining: number of requests remaining in window
        - reset_time: seconds until window resets
        """
        now = time.time()
        is_expensive = self.is_expensive(path)
        limit = self.STRICT_LIMIT if is_expensive else self.DEFAULT_LIMIT
        window = self.STRICT_WINDOW if is_expensive else self.DEFAULT_WINDOW

        with self._lock:
            self._request_counter += 1
            if self._request_counter % 100 == 0:
                self._cleanup_stale_ips()
            self._cleanup_old(ip, window)

            if ip not in self._requests:
                self._requests[ip] = []

            # Count requests in current window
            cutoff = now - window
            if is_expensive:
                recent = [
                    (ts, p) for ts, p in self._requests[ip]
                    if ts > cutoff and self.is_expensive(p)
                ]
            else:
                recent = [
                    (ts, p) for ts, p in self._requests[ip]
                    if ts > cutoff
                ]

            count = len(recent)

            if count >= limit:
                # Find when the oldest request in window expires
                oldest = min(ts for ts, _ in recent) if recent else now
                reset_time = int(oldest + window - now) + 1
                return False, 0, reset_time

            # Record this request
            self._requests[ip].append((now, path))
            remaining = limit - count - 1
            reset_time = int(window)

            return True, remaining, reset_time


# Singleton instance
_rate_limiter = None
_rate_limiter_lock = threading.Lock()


def get_rate_limiter():
    """Get the singleton RateLimiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        with _rate_limiter_lock:
            if _rate_limiter is None:
                _rate_limiter = RateLimiter()
    return _rate_limiter
