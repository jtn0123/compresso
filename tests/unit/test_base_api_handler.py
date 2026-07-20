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


@pytest.mark.unittest
class TestRouteBodyOffload:
    """Tests for the _invoke_route offload / deferred-finish mechanism."""

    def _make_offload_handler(self):
        handler = BaseApiHandler.__new__(BaseApiHandler)
        handler.error_messages = {}
        handler.route = {}
        handler._finished = False
        handler.application = MagicMock(settings={})
        handler.calls = []
        return handler

    def test_sync_route_body_is_offloaded_and_finish_deferred(self):
        handler = self._make_offload_handler()
        finished_chunks = []

        def fake_super_finish(chunk=None):
            finished_chunks.append(chunk)
            handler._finished = True

        def sync_body():
            # finish() during the offloaded body must only be recorded
            handler.calls.append("body")
            handler.finish({"success": True})
            assert handler._finish_deferred is True
            assert handler._finished is False

        handler.sync_body = sync_body
        with patch.object(BaseApiHandler.__bases__[1], "finish", side_effect=fake_super_finish, autospec=False):
            asyncio.run(handler._invoke_route({"call_method": "sync_body"}))

        assert handler.calls == ["body"]
        # The real finish happened exactly once, back on the caller, with the chunk
        assert finished_chunks == [{"success": True}]
        assert handler._finish_deferred is False

    def test_run_on_ioloop_route_is_not_offloaded(self):
        handler = self._make_offload_handler()

        async def loop_body():
            handler.calls.append("loop-body")
            # Not deferred: finish() should go straight through
            assert getattr(handler, "_defer_finish", False) is False

        handler.loop_body = loop_body
        asyncio.run(handler._invoke_route({"call_method": "loop_body", "run_on_ioloop": True}))
        assert handler.calls == ["loop-body"]

    def test_offload_disabled_per_handler_runs_on_loop(self):
        handler = self._make_offload_handler()
        handler.offload_route_bodies = False

        async def loop_body():
            handler.calls.append("no-offload")
            assert getattr(handler, "_defer_finish", False) is False

        handler.loop_body = loop_body
        asyncio.run(handler._invoke_route({"call_method": "loop_body"}))
        assert handler.calls == ["no-offload"]

    def test_error_after_deferred_finish_does_not_double_respond(self):
        handler = self._make_offload_handler()
        finished_chunks = []

        def fake_super_finish(chunk=None):
            finished_chunks.append(chunk)
            handler._finished = True

        def sync_body():
            handler.finish({"success": True})
            raise RuntimeError("late failure after response was produced")

        handler.sync_body = sync_body
        with (
            patch.object(BaseApiHandler.__bases__[1], "finish", side_effect=fake_super_finish, autospec=False),
            patch(f"{BASE_API}.tornado.log.app_log.exception"),
        ):
            asyncio.run(handler._invoke_route({"call_method": "sync_body"}))

        # The deferred success response is delivered once; the late error is logged only
        assert finished_chunks == [{"success": True}]
