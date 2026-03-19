#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_rate_limiting.py

    Tests for the API rate limiter.

"""

import pytest
from unittest.mock import patch

from compresso.webserver.api_v2.rate_limiter import RateLimiter


@pytest.mark.unittest
class TestRateLimiter(object):
    """Tests for the RateLimiter class."""

    def _make_limiter(self):
        return RateLimiter()

    def test_under_limit_succeeds(self):
        limiter = self._make_limiter()
        allowed, remaining, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert allowed is True
        assert remaining == 59

    def test_over_limit_returns_false(self):
        limiter = self._make_limiter()
        for _ in range(60):
            limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        allowed, remaining, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert allowed is False
        assert remaining == 0

    def test_different_ips_independent(self):
        limiter = self._make_limiter()
        for _ in range(60):
            limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        # Different IP should still be allowed
        allowed, _, _ = limiter.check_rate_limit('5.6.7.8', '/healthcheck/summary')
        assert allowed is True

    def test_expensive_endpoint_lower_threshold(self):
        limiter = self._make_limiter()
        for _ in range(5):
            limiter.check_rate_limit('1.2.3.4', '/preview/create')
        allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/preview/create')
        assert allowed is False

    def test_expensive_endpoint_identified(self):
        limiter = self._make_limiter()
        assert limiter.is_expensive('/compresso/api/v2/preview/create') is True
        assert limiter.is_expensive('/compresso/api/v2/healthcheck/scan') is True
        assert limiter.is_expensive('/compresso/api/v2/healthcheck/scan-library') is True
        assert limiter.is_expensive('/compresso/api/v2/healthcheck/summary') is False

    def test_normal_endpoint_not_affected_by_expensive_limit(self):
        limiter = self._make_limiter()
        # Exhaust expensive limit
        for _ in range(5):
            limiter.check_rate_limit('1.2.3.4', '/preview/create')
        # Normal endpoint should still work
        allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert allowed is True

    @patch('compresso.webserver.api_v2.rate_limiter.time.time')
    def test_window_slides_old_requests_expire(self, mock_time):
        limiter = self._make_limiter()
        # First request at t=0
        mock_time.return_value = 1000.0
        for _ in range(60):
            limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        # Over limit
        allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert allowed is False

        # Advance time past window
        mock_time.return_value = 1061.0
        allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert allowed is True

    def test_reset_time_returned(self):
        limiter = self._make_limiter()
        _, _, reset_time = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert reset_time > 0

    @patch('compresso.webserver.api_v2.rate_limiter.time.time')
    def test_stale_ips_cleaned_up(self, mock_time):
        """IPs with no requests in the last 5 minutes should be removed."""
        limiter = self._make_limiter()
        # Add request at t=0
        mock_time.return_value = 1000.0
        limiter.check_rate_limit('stale.ip', '/healthcheck/summary')
        assert 'stale.ip' in limiter._requests

        # Advance 6 minutes
        mock_time.return_value = 1361.0
        limiter._cleanup_stale_ips()
        assert 'stale.ip' not in limiter._requests

    def test_exactly_at_limit_last_request_allowed(self):
        limiter = self._make_limiter()
        # Make 59 requests (0-58)
        for _ in range(59):
            allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
            assert allowed is True
        # 60th request should still be allowed (count was 59 before this)
        allowed, remaining, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert allowed is True
        assert remaining == 0
        # 61st should be rejected
        allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert allowed is False

    def test_expensive_at_exact_limit(self):
        limiter = self._make_limiter()
        # Make 4 requests
        for _ in range(4):
            allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/preview/create')
            assert allowed is True
        # 5th should be allowed
        allowed, remaining, _ = limiter.check_rate_limit('1.2.3.4', '/preview/create')
        assert allowed is True
        assert remaining == 0
        # 6th should be rejected
        allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/preview/create')
        assert allowed is False

    def test_remaining_count_decrements_correctly(self):
        limiter = self._make_limiter()
        for i in range(5):
            allowed, remaining, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
            assert allowed is True
            assert remaining == 59 - i

    def test_expensive_and_normal_counts_are_separate(self):
        limiter = self._make_limiter()
        # Exhaust expensive limit
        for _ in range(5):
            limiter.check_rate_limit('1.2.3.4', '/preview/create')
        allowed, _, _ = limiter.check_rate_limit('1.2.3.4', '/preview/create')
        assert allowed is False
        # Normal endpoint should still have capacity (but counts all 5 expensive requests too)
        allowed, remaining, _ = limiter.check_rate_limit('1.2.3.4', '/healthcheck/summary')
        assert allowed is True
        # 60 limit - 5 expensive requests already counted - 1 for this request = 54
        assert remaining == 54

    def test_get_rate_limiter_singleton_returns_same_instance(self):
        import compresso.webserver.api_v2.rate_limiter as rl_module
        original = rl_module._rate_limiter
        try:
            rl_module._rate_limiter = None
            from compresso.webserver.api_v2.rate_limiter import get_rate_limiter
            a = get_rate_limiter()
            b = get_rate_limiter()
            assert a is b
        finally:
            rl_module._rate_limiter = original

    @patch('compresso.webserver.api_v2.rate_limiter.time.time')
    def test_cleanup_counter_triggers(self, mock_time):
        """Cleanup should run every 100th request."""
        limiter = self._make_limiter()
        mock_time.return_value = 1000.0

        # Add a stale IP manually
        limiter._requests['old.ip'] = [(500.0, '/test')]

        # Make 99 requests (counter starts at 0)
        for i in range(99):
            mock_time.return_value = 1000.0 + i
            limiter.check_rate_limit('active.ip', '/healthcheck/summary')

        # old.ip should still exist (cleanup hasn't run yet)
        assert 'old.ip' in limiter._requests

        # 100th request triggers cleanup
        mock_time.return_value = 1100.0
        limiter.check_rate_limit('active.ip', '/healthcheck/summary')
        assert 'old.ip' not in limiter._requests
