#!/usr/bin/env python3

"""
compresso.security_headers.py

Mixin that adds standard security headers to all HTTP responses.
Applied to API handlers, the main UI handler, and plugin handlers.
"""

from urllib.parse import urlparse


class SecurityHeadersMixin:
    """Mixin that sets standard security response headers.

    Apply to any Tornado RequestHandler via multiple inheritance.
    Call ``set_security_headers()`` from ``set_default_headers()``
    or at the top of individual handler methods.
    """

    def set_security_headers(self):
        # Prevent MIME-type sniffing
        self.set_header("X-Content-Type-Options", "nosniff")

        # Prevent clickjacking
        self.set_header("X-Frame-Options", "DENY")

        # Disable legacy XSS filter (modern browsers don't need it;
        # setting to "0" avoids XSS-auditor-based attacks)
        self.set_header("X-XSS-Protection", "0")

        # Control referrer information leakage
        self.set_header("Referrer-Policy", "strict-origin-when-cross-origin")

        # Restrict browser features the app doesn't need
        self.set_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

        # HSTS only when the request arrived over HTTPS
        if getattr(self, "request", None) and self.request.protocol == "https":
            self.set_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    def set_html_security_headers(self):
        """Additional headers appropriate for HTML responses (not JSON APIs)."""
        self.set_security_headers()

        # Content Security Policy for the SPA frontend.
        # - 'unsafe-inline' / 'unsafe-eval' required by Vue.js runtime
        # - blob: needed for video preview playback
        # - ws:/wss: needed for WebSocket connections
        self.set_header(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "connect-src 'self' ws: wss:; "
            "font-src 'self'; "
            "frame-ancestors 'none'",
        )


def check_websocket_origin(handler, origin):
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
    # Strip port from both for comparison
    request_hostname = request_host.split(":")[0]
    return origin_host == request_hostname
