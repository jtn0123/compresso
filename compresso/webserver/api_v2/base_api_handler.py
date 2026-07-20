#!/usr/bin/env python3

"""
compresso.base_api_handler.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     26 Oct 2020, (12:15 PM)

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

import asyncio
import json
import secrets
import sys
import traceback
from json import JSONDecodeError
from typing import Any

import tornado.log
import tornado.routing
import tornado.web
from marshmallow import Schema, exceptions
from tornado.web import RequestHandler

from compresso.webserver.request_auth import authorize_request, request_has_valid_api_token
from compresso.webserver.security_headers import SecurityHeadersMixin

LOG_UNHANDLED_ERROR = "Unhandled error id=%s in %s.%s"
LOG_BASE_API_ERROR = "Expected API error id=%s in %s: %s"
CSRF_COOKIE_NAME = "compresso_csrf_token"
CSRF_HEADER_NAME = "X-Compresso-CSRF-Token"
READ_ONLY_POST_PATHS = (
    "/approval/tasks",
    "/approval/summary",
    "/approval/detail",
    "/compression/stats",
    "/compression/library-analysis/status",
    "/filebrowser/list",
    "/fileinfo/probe",
    "/fileinfo/task",
    "/healthcheck/status",
    "/metadata/search",
    "/metadata/by-task",
    "/metadata/by-fingerprint",
    "/plugins/installed",
    "/plugins/info",
    "/plugins/flow",
    "/settings/worker_group/read",
    "/settings/link/read",
    "/settings/library/read",
    "/preview/status",
)


class BaseApiError(Exception):
    """Expected API failure with an intentionally public response."""

    def __init__(self, public_message, *, messages=None, status_code=400, private_detail=None):
        super().__init__(public_message)
        self.public_message = public_message
        self.messages = messages or {}
        self.status_code = status_code
        self.private_detail = private_detail or public_message


class BaseApiHandler(SecurityHeadersMixin, RequestHandler):
    api_version = 2
    routes: list[dict[str, Any]] = []
    route: dict[str, Any] = {}
    error_messages: dict[str, Any] = {}
    # Route handler bodies are synchronous DB/file work; run them in a worker
    # thread by default so they cannot stall the IOLoop. Individual routes can
    # opt out with {"run_on_ioloop": True}; subclasses can disable per-handler.
    offload_route_bodies = True

    """
    Valid API return status codes:
    """
    STATUS_SUCCESS = 200
    STATUS_ERROR_UNAUTHORIZED = 401
    STATUS_ERROR_FORBIDDEN = 403
    STATUS_ERROR_EXTERNAL = 400
    STATUS_ERROR_ENDPOINT_NOT_FOUND = 404
    STATUS_ERROR_METHOD_NOT_ALLOWED = 405
    STATUS_ERROR_RATE_LIMITED = 429
    STATUS_ERROR_INTERNAL = 500

    def initialize(self, **kwargs):
        self.params = kwargs.get("params", [])
        self.error_messages = {}

    def prepare(self):
        """Check cross-cutting API guards before routing to handler methods."""
        from compresso.webserver.api_v2.rate_limiter import get_rate_limiter

        if not self._authorize_request():
            return

        limiter = get_rate_limiter()
        ip = self.request.remote_ip
        path = self.request.path

        allowed, remaining, reset_time = limiter.check_rate_limit(ip, path)
        self.set_header("X-RateLimit-Remaining", str(remaining))
        self.set_header("X-RateLimit-Reset", str(reset_time))

        if not allowed:
            self.set_status(self.STATUS_ERROR_RATE_LIMITED, reason="Too Many Requests")
            self.finish(
                {
                    "error": "429: Too Many Requests",
                    "messages": {"rate_limit": f"Rate limit exceeded. Try again in {reset_time} seconds."},
                }
            )

    def _request_api_path(self):
        path = self.request.path
        marker = f"/api/v{self.api_version}"
        if marker in path:
            return path.split(marker, 1)[1] or "/"
        return path

    def _is_read_only_post_path(self):
        api_path = self._request_api_path()
        return any(api_path == path or api_path.startswith(path + "/") for path in READ_ONLY_POST_PATHS)

    def _requires_mutation_protection(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return False
        return not (self.request.method == "POST" and self._is_read_only_post_path())

    def _finish_auth_error(self, status, reason):
        self.set_status(status, reason=reason)
        self.write_error()
        return False

    def _ensure_csrf_cookie(self):
        csrf_token = self.get_cookie(CSRF_COOKIE_NAME)
        if not csrf_token:
            csrf_token = secrets.token_urlsafe(32)
            self.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=False, samesite="Strict")
        return csrf_token

    @staticmethod
    def _explicit_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        if isinstance(value, int):
            return bool(value)
        return False

    def _authorize_request(self):
        from compresso import config

        settings = config.Config()
        csrf_enabled = self._explicit_bool(settings.get_csrf_protection_enforced())
        csrf_cookie = self._ensure_csrf_cookie() if csrf_enabled else ""
        api_auth_enabled = self._explicit_bool(settings.get_api_auth_enforced())
        service_authenticated = api_auth_enabled and request_has_valid_api_token(
            self.request,
            settings.get_api_auth_token(),
        )

        if self._request_api_path() != "/healthcheck/readiness" and not authorize_request(self):
            return False

        if (
            self._requires_mutation_protection()
            and csrf_enabled
            and not service_authenticated
            and self.request.headers.get(CSRF_HEADER_NAME, "") != csrf_cookie
        ):
            return self._finish_auth_error(self.STATUS_ERROR_FORBIDDEN, "Invalid CSRF token")

        return True

    def set_default_headers(self):
        """
        Set the default response header to be JSON.
        This overwrites the RequestHandler method.

        :return:
        """
        self.set_header("Content-Type", 'application/json; charset="utf-8"')
        self.set_security_headers()

    def read_json_request(self, schema: Schema):
        """

        :param schema:
        :type schema: Schema descendant
        :return:
        """
        # Ensure body can be JSON decoded
        try:
            json_data = json.loads(self.request.body)
        except (JSONDecodeError, UnicodeDecodeError) as exc:
            messages = {"body": ["Invalid JSON payload"]}
            self.error_messages = messages
            raise BaseApiError(
                "Expected request body to be valid JSON",
                messages=messages,
                private_detail=f"{type(exc).__name__}: {exc}",
            ) from exc

        request_validation_errors = schema.validate(json_data)
        if request_validation_errors:
            self.error_messages = request_validation_errors
            raise BaseApiError(
                "Failed request schema validation",
                messages=request_validation_errors,
                private_detail=f"Schema validation failed: {request_validation_errors}",
            )

        return schema.dump(schema.load(json_data))

    def load_request(self, schema: Schema):
        """Load and validate a JSON request body."""
        return self.read_json_request(schema)

    def build_response(self, schema: Schema, response):
        """
        Validate the given response against a given Schema.
        Return the response data as a serialized object according to the given Schema's fields.

        :param schema:
        :param response:
        :return:
        """
        # Validate that schema.
        # This is not normally done with responses, but I want to be strict about ensuring the schema is up-to-date
        validation_errors = schema.validate(response)

        if validation_errors:
            # Throw an exception here with all the errors.
            # This will be caught and handled by the 500 internal error
            raise exceptions.ValidationError(validation_errors)

        # Build schema object from response
        data = schema.dump(response)
        return data

    def respond_with_schema(self, schema: Schema, response):
        """Validate, serialize, and send a successful schema response."""
        self.write_success(self.build_response(schema, response))

    def handle_base_api_error(self, exc: BaseApiError) -> None:
        """Standard handler for expected API errors."""
        error_id = secrets.token_hex(8)
        call_method = self.route.get("call_method") if getattr(self, "route", None) else None
        tornado.log.app_log.warning(LOG_BASE_API_ERROR, error_id, call_method, exc.private_detail)
        if self._response_already_committed():
            return
        self.error_messages = exc.messages
        self._api_error_id = error_id
        self.set_status(exc.status_code, reason=exc.public_message)
        self.write_error()

    def write_success(self, response=None):
        """
        Write data out as HTTP code 200
        Finishes this response, ending the HTTP request.

        :param response:
        :return:
        """
        if response is None:
            response = {"success": True}
        self.set_status(self.STATUS_SUCCESS)
        self.finish(response)

    def handle_unhandled_error(self, exc: Exception) -> None:
        """
        Standard handling for an unexpected exception raised inside a handler.
        Private exception details remain in the correlated server log; clients
        receive a stable public message and opaque error identifier.

        Centralising this keeps the per-handler ``except Exception`` arms to a
        single call rather than repeating the log/set_status/write_error trio.

        :param exc: The caught exception.
        :return:
        """
        call_method = self.route.get("call_method") if getattr(self, "route", None) else None
        error_id = secrets.token_hex(8)
        tornado.log.app_log.exception(LOG_UNHANDLED_ERROR, error_id, self.__class__.__name__, call_method)
        if self._response_already_committed():
            return
        self.error_messages = {}
        self._api_error_id = error_id
        self.set_status(self.STATUS_ERROR_INTERNAL, reason="Internal server error")
        self.write_error()

    def write_api_error(self, status_code, public_reason, *, messages=None, error_id=None, exc_info=None) -> None:
        """Own the complete structured error response for v2 API handlers."""
        if self._response_already_committed():
            return

        self.error_messages = messages or {}
        if self.get_status() != status_code or self._reason != public_reason:
            self.set_status(status_code, reason=public_reason)
        response = {
            "error": f"{status_code:d}: {public_reason}",
            "messages": self.error_messages,
        }
        if error_id:
            response["error_id"] = error_id

        application = getattr(self, "application", None)
        settings = application.settings if application is not None else {}
        if settings.get("serve_traceback"):
            effective_exc_info = exc_info or sys.exc_info()
            if effective_exc_info and effective_exc_info[0]:
                response["traceback"] = traceback.format_exception(*effective_exc_info)
        self.finish(response)

    def write_error(self, status_code=None, **kwargs: Any) -> None:
        """
        Set the default error message.
        This overwrites the RequestHandler method.

        ``write_error`` may call `write`, `render`, `set_header`, etc
        to produce output as usual.

        If this error was caused by an uncaught exception (including
        HTTPError), an ``exc_info`` triple will be available as
        ``kwargs["exc_info"]``.  Note that this exception may not be
        the "current" exception for purposes of methods like
        ``sys.exc_info()`` or ``traceback.format_exc``.

        :param status_code:
        :param kwargs:
        :return:
        """
        if status_code is None:
            status_code = self.get_status()
        public_reason = self._reason
        error_id = getattr(self, "_api_error_id", None)
        if hasattr(self, "_api_error_id"):
            del self._api_error_id
        if status_code >= self.STATUS_ERROR_INTERNAL:
            public_reason = "Internal server error"
            if not error_id:
                error_id = secrets.token_hex(8)
                tornado.log.app_log.error(
                    "API error reached structured writer id=%s status=%s",
                    error_id,
                    status_code,
                    exc_info=kwargs.get("exc_info"),
                )
        self.write_api_error(
            status_code,
            public_reason,
            messages=self.error_messages,
            error_id=error_id,
            exc_info=kwargs.get("exc_info"),
        )

    async def _invoke_route(self, route, *args, **kwargs):
        """Invoke one routed method and own any exception it lets escape."""
        self.route = route
        method = getattr(self, route.get("call_method"))
        try:
            if route.get("run_on_ioloop") or not self.offload_route_bodies:
                await method(*args, **kwargs)
            else:
                await self._invoke_route_offloaded(method, *args, **kwargs)
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as exc:
            self.handle_unhandled_error(exc)
        finally:
            self._apply_deferred_finish()

    async def _invoke_route_offloaded(self, method, *args, **kwargs):
        """
        Run a handler body in a worker thread so its synchronous DB and file
        I/O cannot block the single Tornado IOLoop for every other client.

        Tornado handlers are not thread-safe, so ``finish()`` is deferred while
        the body runs off-loop: response status, headers, and body chunks are
        only buffered on the handler (safe — the awaiting coroutine is
        suspended until the worker completes), and the actual connection write
        happens back on the IOLoop in ``_apply_deferred_finish``.
        """
        self._finish_deferred = False
        self._defer_finish = True
        try:
            if asyncio.iscoroutinefunction(method):
                # Coroutine bodies get their own short-lived event loop in the
                # worker thread; awaits like asyncio.to_thread and
                # run_in_executor behave identically there.
                await asyncio.to_thread(asyncio.run, method(*args, **kwargs))
            else:
                await asyncio.to_thread(method, *args, **kwargs)
        finally:
            self._defer_finish = False

    def _response_already_committed(self):
        """True when a response has been finished or is pending deferred finish."""
        return getattr(self, "_finished", False) or getattr(self, "_finish_deferred", False)

    def _apply_deferred_finish(self):
        """Complete a finish() that was deferred while the body ran off-loop."""
        if getattr(self, "_finish_deferred", False):
            self._finish_deferred = False
            chunk = getattr(self, "_deferred_finish_chunk", None)
            self._deferred_finish_chunk = None
            if not self._finished:
                super().finish(chunk)

    def finish(self, chunk=None):
        if getattr(self, "_defer_finish", False):
            # Record the final chunk; it is handed to the real finish() on the
            # IOLoop thread once the offloaded body returns.
            self._deferred_finish_chunk = chunk
            self._finish_deferred = True
            return None
        return super().finish(chunk)

    def handle_endpoint_not_found(self):
        """
        Return a JSON 404 error message.
        Finishes this response, ending the HTTP request.

        :return:
        """
        response = {"error": f"{self.STATUS_ERROR_ENDPOINT_NOT_FOUND:d}: Endpoint not found"}
        self.set_status(self.STATUS_ERROR_ENDPOINT_NOT_FOUND)
        self.finish(response)

    def handle_method_not_allowed(self):
        """
        Return a JSON 405 error message.
        Finishes this response, ending the HTTP request.

        :return:
        """
        response = {"error": f"{self.STATUS_ERROR_METHOD_NOT_ALLOWED:d}: Method '{self.request.method}' not allowed"}
        self.set_status(self.STATUS_ERROR_METHOD_NOT_ALLOWED)
        self.finish(response)

    async def action_route(self):
        """
        Determine the handler method for the route.
        Execute that handler method.
        If not method if found to handle this route,
        return 404 by exec 'handle_missing_endpoint()' method.

        :return:
        """
        api_marker = f"api/v{self.api_version}"
        request_api_base = self.request.path.split(api_marker)[0] + api_marker
        # request_api_endpoint = re.sub('^/(compresso/)*api/v\d', '', self.request.uri)
        matched_route_with_unsupported_method = False
        for route in self.routes:
            # Get supported methods
            supported_methods = route.get("supported_methods", [])

            # Fetch the path match from this route's path pattern
            path_pattern = request_api_base + route.get("path_pattern")
            path_match = tornado.routing.PathMatches(path_pattern)
            if path_match.regex.match(self.request.path):
                # Check if this endpoint supports the request HTTP method
                if self.request.method not in supported_methods:
                    # The request's method is not supported by this route.
                    # Mark as having found a matching route, but with an un-supported HTTP method
                    matched_route_with_unsupported_method = True
                    continue

                # Check if the path matches, and get any params from a match
                params = path_match.match(self.request)

                # If we have a match and were returned some params, load that method
                if params:
                    tornado.log.app_log.debug(
                        "Routing API to {}.{}(*args={}, **kwargs={})".format(
                            self.__class__.__name__, route.get("call_method"), params["path_args"], params["path_kwargs"]
                        ),
                        exc_info=True,
                    )

                    await self._invoke_route(route, *params["path_args"], **params["path_kwargs"])
                    return

                # This route matches the current request URI and does not have any params.
                # Set this route and call the configured method.
                tornado.log.app_log.debug(
                    f"Routing API to {self.__class__.__name__}.{route.get('call_method')}()", exc_info=True
                )
                await self._invoke_route(route)
                return

        if matched_route_with_unsupported_method:
            tornado.log.app_log.warning(f"Method not allowed for API route: {self.request.uri}", exc_info=True)
            self.handle_method_not_allowed()
        else:
            tornado.log.app_log.warning(f"No match found for API route: {self.request.uri}", exc_info=True)
            self.handle_endpoint_not_found()

    async def delete(self, path):
        """
        Route all DELETE requests to the 'action_route()' method

        :param path:
        :return:
        """
        await self.action_route()

    async def get(self, path):
        """
        Route all GET requests to the 'action_route()' method

        :param path:
        :return:
        """
        await self.action_route()

    async def post(self, path):
        """
        Route all POST requests to the 'action_route()' method

        :param path:
        :return:
        """
        await self.action_route()

    async def put(self, path):
        """
        Route all PUT requests to the 'action_route()' method

        :param path:
        :return:
        """
        await self.action_route()
