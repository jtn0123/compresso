#!/usr/bin/env python3

"""
tests.unit.test_security_headers.py

Tests for security headers applied across all handler types.
"""

from unittest.mock import MagicMock, patch

import pytest
import tornado.testing
import tornado.web

from compresso.webserver.api_v2.base_api_handler import BaseApiHandler as V2BaseApiHandler
from compresso.webserver.security_headers import SecurityHeadersMixin, check_websocket_origin

# --- Unit tests for the mixin itself ---


@pytest.mark.unittest
class TestSecurityHeadersMixin:
    def _make_handler(self):
        """Create a minimal handler-like object with the mixin."""

        class FakeHandler(SecurityHeadersMixin):
            def __init__(self):
                self.headers = {}
                self.request = MagicMock()
                self.request.protocol = "http"

            def set_header(self, name, value):
                self.headers[name] = value

        return FakeHandler()

    def test_set_security_headers_adds_all_required(self):
        handler = self._make_handler()
        handler.set_security_headers()

        assert handler.headers["X-Content-Type-Options"] == "nosniff"
        assert handler.headers["X-Frame-Options"] == "DENY"
        assert handler.headers["X-XSS-Protection"] == "0"
        assert handler.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "camera=()" in handler.headers["Permissions-Policy"]

    def test_no_hsts_over_http(self):
        handler = self._make_handler()
        handler.request.protocol = "http"
        handler.set_security_headers()

        assert "Strict-Transport-Security" not in handler.headers

    def test_hsts_over_https(self):
        handler = self._make_handler()
        handler.request.protocol = "https"
        handler.set_security_headers()

        assert "Strict-Transport-Security" in handler.headers
        assert "max-age=" in handler.headers["Strict-Transport-Security"]

    def test_html_security_headers_includes_csp(self):
        handler = self._make_handler()
        handler.set_html_security_headers()

        assert "Content-Security-Policy" in handler.headers
        assert "default-src 'self'" in handler.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in handler.headers["Content-Security-Policy"]
        # Should also include the base security headers
        assert handler.headers["X-Content-Type-Options"] == "nosniff"


# --- Unit tests for WebSocket origin check ---


@pytest.mark.unittest
class TestCheckWebsocketOrigin:
    def _make_handler(self, host="localhost:8888"):
        handler = MagicMock()
        handler.request.headers = {"Host": host}
        return handler

    def test_same_origin_accepted(self):
        handler = self._make_handler("localhost:8888")
        assert check_websocket_origin(handler, "http://localhost:8888") is True

    def test_different_origin_rejected(self):
        handler = self._make_handler("localhost:8888")
        assert check_websocket_origin(handler, "http://evil.com:8888") is False

    def test_empty_origin_rejected(self):
        handler = self._make_handler()
        assert check_websocket_origin(handler, "") is False

    def test_none_origin_rejected(self):
        handler = self._make_handler()
        assert check_websocket_origin(handler, None) is False

    def test_same_host_different_port_accepted(self):
        """Origin hostname matches host header hostname — ports don't affect the check."""
        handler = self._make_handler("myserver:8888")
        assert check_websocket_origin(handler, "http://myserver:9999") is True


# --- Integration test: v2 API handler returns security headers ---


def _mock_initialize(self, **kwargs):
    self.params = kwargs.get("params", [])


@pytest.mark.unittest
@patch.object(V2BaseApiHandler, "initialize", _mock_initialize)
class TestV2ApiSecurityHeaders(tornado.testing.AsyncHTTPTestCase):
    def runTest(self):
        pass

    def get_app(self):
        return tornado.web.Application(
            [(r"/compresso/api/v2/(.*)", V2BaseApiHandler)],
        )

    def test_api_response_has_security_headers(self):
        resp = self.fetch("/compresso/api/v2/nonexistent")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("X-XSS-Protection") == "0"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert "camera=()" in resp.headers.get("Permissions-Policy", "")
        # API responses should NOT have CSP (that's for HTML only)
        assert resp.headers.get("Content-Security-Policy") is None
