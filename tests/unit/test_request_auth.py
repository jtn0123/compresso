from unittest.mock import MagicMock

import pytest

from compresso.webserver.request_auth import (
    WEBSOCKET_AUTH_PROTOCOL_PREFIX,
    encode_websocket_token,
    request_has_valid_api_token,
)


@pytest.mark.unittest
class TestRequestAuth:
    def test_accepts_bearer_header(self):
        request = MagicMock()
        request.headers = {"Authorization": "Bearer secret"}

        assert request_has_valid_api_token(request, "secret") is True

    def test_accepts_compresso_header(self):
        request = MagicMock()
        request.headers = {"X-Compresso-Api-Token": "secret"}

        assert request_has_valid_api_token(request, "secret") is True

    def test_rejects_missing_configured_token(self):
        request = MagicMock()
        request.headers = {"X-Compresso-Api-Token": "secret"}

        assert request_has_valid_api_token(request, "") is False

    def test_accepts_encoded_websocket_subprotocol(self):
        encoded = encode_websocket_token("token with punctuation: !")
        request = MagicMock()
        request.headers = {"Sec-WebSocket-Protocol": f"compresso, {WEBSOCKET_AUTH_PROTOCOL_PREFIX}{encoded}"}

        assert request_has_valid_api_token(request, "token with punctuation: !", allow_websocket_protocol=True) is True

    def test_rejects_invalid_websocket_subprotocol(self):
        request = MagicMock()
        request.headers = {
            "Sec-WebSocket-Protocol": f"compresso, {WEBSOCKET_AUTH_PROTOCOL_PREFIX}{encode_websocket_token('wrong')}"
        }

        assert request_has_valid_api_token(request, "secret", allow_websocket_protocol=True) is False
