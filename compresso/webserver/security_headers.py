#!/usr/bin/env python3

"""
compresso.security_headers.py

Mixin that adds standard security headers to all HTTP responses.
Applied to API handlers, the main UI handler, and plugin handlers.
"""

from typing import Protocol, cast
from urllib.parse import urlparse

from tornado.httputil import HTTPServerRequest
from tornado.web import RequestHandler


class _HeaderOwner(Protocol):
    request: HTTPServerRequest

    def set_header(self, name: str, value: str) -> None: ...


class SecurityHeadersMixin:
    """Mixin that sets standard security response headers.

    Apply to any Tornado RequestHandler via multiple inheritance.
    Call ``set_security_headers()`` from ``set_default_headers()``
    or at the top of individual handler methods.
    """

    def _header_owner(self) -> _HeaderOwner:
        return cast(_HeaderOwner, self)

    def set_security_headers(self) -> None:
        owner = self._header_owner()
        # Prevent MIME-type sniffing
        owner.set_header("X-Content-Type-Options", "nosniff")

        # Prevent clickjacking
        owner.set_header("X-Frame-Options", "DENY")

        # Disable legacy XSS filter (modern browsers don't need it;
        # setting to "0" avoids XSS-auditor-based attacks)
        owner.set_header("X-XSS-Protection", "0")

        # Control referrer information leakage
        owner.set_header("Referrer-Policy", "strict-origin-when-cross-origin")

        # Restrict browser features the app doesn't need
        owner.set_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

        # HSTS only when the request arrived over HTTPS
        request: object = getattr(self, "request", None)
        if getattr(request, "protocol", None) == "https":
            owner.set_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    def set_html_security_headers(self) -> None:
        """Additional headers appropriate for HTML responses (not JSON APIs)."""
        self.set_security_headers()

        # Content Security Policy for the production SPA frontend. The Vite
        # build emits external module scripts and does not require eval or
        # inline JavaScript. Quasar still applies dynamic style attributes, so
        # that narrowly-scoped exception remains in style-src-attr.
        self._header_owner().set_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; "
            "object-src 'none'; "
            "script-src 'self'; "
            "style-src-elem 'self'; "
            "style-src-attr 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self'; "
            "form-action 'self'; "
            "frame-ancestors 'none'",
        )


def check_websocket_origin(handler: RequestHandler, origin: str) -> bool:
    """Validate that a WebSocket origin matches the server host.

    Returns True if the origin is acceptable, False otherwise.
    Intended for use in ``WebSocketHandler.check_origin()``.
    """
    if not origin:
        return False
    parsed = urlparse(origin)
    origin_host = parsed.hostname
    # Compare against the Host header (which includes port for non-default)
    request_host = handler.request.headers.get("Host", "")
    if not isinstance(request_host, str):
        return False
    # Strip port from both for comparison
    request_hostname = request_host.split(":")[0]
    return origin_host == request_hostname
