#!/usr/bin/env python3

"""
tests.unit.test_base_api_handler.py

Unit tests for the shared BaseApiHandler helpers.
"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.webserver.api_v2.base_api_handler import BaseApiHandler

BASE_API = "compresso.webserver.api_v2.base_api_handler"


def _make_bare_handler():
    """Build a BaseApiHandler without running Tornado's RequestHandler.__init__."""
    handler = BaseApiHandler.__new__(BaseApiHandler)
    handler.set_status = MagicMock()
    handler.write_error = MagicMock()
    return handler


@pytest.mark.unittest
class TestHandleUnhandledError:
    def test_logs_sets_status_and_writes_error(self):
        handler = _make_bare_handler()
        handler.route = {"call_method": "do_thing"}

        with patch(f"{BASE_API}.tornado.log.app_log.exception") as mock_log:
            handler.handle_unhandled_error(ValueError("boom"))

        mock_log.assert_called_once()
        handler.set_status.assert_called_once_with(BaseApiHandler.STATUS_ERROR_INTERNAL, reason="boom")
        handler.write_error.assert_called_once_with()

    def test_handles_missing_route(self):
        # When routing never set self.route, the helper must still respond
        # rather than raising AttributeError.
        handler = _make_bare_handler()

        with patch(f"{BASE_API}.tornado.log.app_log.exception") as mock_log:
            handler.handle_unhandled_error(RuntimeError("kaboom"))

        # call_method falls back to None
        assert mock_log.call_args.args[-1] is None
        handler.set_status.assert_called_once_with(BaseApiHandler.STATUS_ERROR_INTERNAL, reason="kaboom")
        handler.write_error.assert_called_once_with()
