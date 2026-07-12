#!/usr/bin/env python3

"""
tests.unit.test_base_api_handler.py

Unit tests for the shared BaseApiHandler helpers.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from marshmallow import Schema, fields

from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler

BASE_API = "compresso.webserver.api_v2.base_api_handler"


def _make_bare_handler():
    """Build a BaseApiHandler without running Tornado's RequestHandler.__init__."""
    handler = BaseApiHandler.__new__(BaseApiHandler)
    handler._status_code = 200
    handler._reason = "OK"

    def set_status(status_code, reason=None):
        handler._status_code = status_code
        handler._reason = reason or ""

    handler.set_status = MagicMock(side_effect=set_status)
    handler.get_status = MagicMock(side_effect=lambda: handler._status_code)
    handler.finish = MagicMock()
    handler.error_messages = {}
    handler.route = {}
    handler._finished = False
    handler.application = MagicMock(settings={})
    return handler


@pytest.mark.unittest
class TestHandleUnhandledError:
    def test_logs_private_detail_and_returns_correlated_public_error(self):
        handler = _make_bare_handler()
        handler.route = {"call_method": "do_thing"}

        with (
            patch(f"{BASE_API}.secrets.token_hex", return_value="error123"),
            patch(f"{BASE_API}.tornado.log.app_log.exception") as mock_log,
        ):
            handler.handle_unhandled_error(ValueError("boom"))

        mock_log.assert_called_once()
        handler.set_status.assert_called_once_with(BaseApiHandler.STATUS_ERROR_INTERNAL, reason="Internal server error")
        response = handler.finish.call_args.args[0]
        assert response == {
            "error": "500: Internal server error",
            "messages": {},
            "error_id": "error123",
        }
        assert "boom" not in str(response)

    def test_handles_missing_route(self):
        # When routing never set self.route, the helper must still respond
        # rather than raising AttributeError.
        handler = _make_bare_handler()

        with (
            patch(f"{BASE_API}.secrets.token_hex", return_value="error456"),
            patch(f"{BASE_API}.tornado.log.app_log.exception") as mock_log,
        ):
            handler.handle_unhandled_error(RuntimeError("kaboom"))

        # call_method falls back to None
        assert mock_log.call_args.args[-1] is None
        assert handler.finish.call_args.args[0]["error_id"] == "error456"


@pytest.mark.unittest
class TestStructuredApiErrors:
    def test_expected_error_separates_public_and_private_details(self):
        handler = _make_bare_handler()
        handler.route = {"call_method": "create_task"}
        error = BaseApiError(
            "Invalid task request",
            messages={"path": ["Not found"]},
            private_detail="private mount path /secret/nas/file.mkv",
        )

        with (
            patch(f"{BASE_API}.secrets.token_hex", return_value="request123"),
            patch(f"{BASE_API}.tornado.log.app_log.warning") as mock_log,
        ):
            handler.handle_base_api_error(error)

        response = handler.finish.call_args.args[0]
        assert response["error"] == "400: Invalid task request"
        assert response["messages"] == {"path": ["Not found"]}
        assert response["error_id"] == "request123"
        assert "/secret/nas" not in str(response)
        assert "/secret/nas" in mock_log.call_args.args[-1]

    def test_invalid_json_raises_without_writing_or_echoing_body(self):
        handler = _make_bare_handler()
        handler.request = MagicMock(body=b'{"api_token":"super-secret"')

        with pytest.raises(BaseApiError) as exc_info:
            handler.read_json_request(Schema())

        assert exc_info.value.public_message == "Expected request body to be valid JSON"
        assert exc_info.value.messages == {"body": ["Invalid JSON payload"]}
        assert "super-secret" not in str(exc_info.value)
        handler.set_status.assert_not_called()
        handler.finish.assert_not_called()

    def test_schema_validation_is_carried_by_the_exception(self):
        class RequestSchema(Schema):
            name = fields.String(required=True)

        handler = _make_bare_handler()
        handler.request = MagicMock(body=b"{}")

        with pytest.raises(BaseApiError) as exc_info:
            handler.read_json_request(RequestSchema())

        assert exc_info.value.public_message == "Failed request schema validation"
        assert "name" in exc_info.value.messages
        handler.finish.assert_not_called()

    def test_route_invocation_owns_escaped_expected_errors(self):
        handler = _make_bare_handler()
        handler.operation = AsyncMock(side_effect=BaseApiError("Invalid operation"))

        asyncio.run(handler._invoke_route({"call_method": "operation"}))

        assert handler.finish.call_args.args[0]["error"] == "400: Invalid operation"

    def test_legacy_500_writer_never_exposes_reason(self):
        handler = _make_bare_handler()
        handler.get_status = MagicMock(return_value=500)
        handler._reason = "database password leaked"

        with patch(f"{BASE_API}.secrets.token_hex", return_value="legacy500"):
            handler.write_error()

        response = handler.finish.call_args.args[0]
        assert response["error"] == "500: Internal server error"
        assert response["error_id"] == "legacy500"
        assert "password" not in str(response)
