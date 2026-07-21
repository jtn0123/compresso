"""Shared authentication helpers for HTTP and WebSocket request handlers."""

import base64
import hmac

from tornado.httputil import HTTPServerRequest
from tornado.web import RequestHandler

from compresso import config
from compresso.libs.constants import API_AUTH_HEADER_NAME, WEBSOCKET_AUTH_PROTOCOL_PREFIX

__all__ = [
    "API_AUTH_HEADER_NAME",
    "WEBSOCKET_AUTH_PROTOCOL_PREFIX",
    "authorize_request",
    "encode_websocket_token",
    "request_has_valid_api_token",
]


def _explicit_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes", "on")
    if isinstance(value, int):
        return bool(value)
    return False


def encode_websocket_token(token: object) -> str:
    """Encode a token using characters allowed in a WebSocket subprotocol."""
    return base64.urlsafe_b64encode(str(token).encode("utf-8")).decode("ascii").rstrip("=")


def _decode_websocket_token(encoded_token: str) -> str:
    try:
        padding = "=" * (-len(encoded_token) % 4)
        return base64.urlsafe_b64decode(encoded_token + padding).decode("utf-8")
    except ValueError:
        return ""


def _websocket_token(request: HTTPServerRequest) -> str:
    offered = request.headers.get("Sec-WebSocket-Protocol", "")
    for protocol in (item.strip() for item in offered.split(",")):
        if protocol.startswith(WEBSOCKET_AUTH_PROTOCOL_PREFIX):
            return _decode_websocket_token(protocol[len(WEBSOCKET_AUTH_PROTOCOL_PREFIX) :])
    return ""


def request_has_valid_api_token(
    request: HTTPServerRequest,
    expected_token: str | None,
    *,
    allow_websocket_protocol: bool = False,
) -> bool:
    """Return whether a request carries the configured API token."""
    if not expected_token:
        return False

    bearer_prefix = "Bearer "
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith(bearer_prefix) and hmac.compare_digest(auth_header[len(bearer_prefix) :], expected_token):
        return True

    token_header = request.headers.get(API_AUTH_HEADER_NAME, "")
    if token_header and hmac.compare_digest(token_header, expected_token):
        return True

    if allow_websocket_protocol:
        websocket_token = _websocket_token(request)
        return bool(websocket_token and hmac.compare_digest(websocket_token, expected_token))
    return False


def authorize_request(
    handler: RequestHandler,
    *,
    allow_websocket_protocol: bool = False,
    allow_options: bool = True,
) -> bool:
    """Enforce optional API auth on any Tornado request handler."""
    settings = config.Config()
    if not _explicit_bool(settings.get_api_auth_enforced()):
        return True
    if allow_options and handler.request.method == "OPTIONS":
        return True
    if request_has_valid_api_token(
        handler.request,
        settings.get_api_auth_token(),
        allow_websocket_protocol=allow_websocket_protocol,
    ):
        return True

    handler.set_status(401, reason="Unauthorized")
    handler.finish({"error": "401: Unauthorized", "messages": {}})
    return False
