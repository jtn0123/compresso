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
import inspect
import json
import secrets
import sys
import traceback
from collections.abc import Awaitable, Callable, Mapping
from json import JSONDecodeError
from types import TracebackType
from typing import NotRequired, TypedDict, cast

import tornado
import tornado.log
from marshmallow import Schema, exceptions
from tornado.log import app_log
from tornado.routing import PathMatches
from tornado.web import RequestHandler

from compresso.webserver.request_auth import authorize_request, request_has_valid_api_token
from compresso.webserver.security_headers import SecurityHeadersMixin

# Some external tests and integrations patch ``tornado.log`` through this
# module's historical namespace. Keep the package exposed while using the
# explicitly typed imports internally.
_TORNADO_NAMESPACE = tornado

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

type ErrorMessages = dict[str, object]
type ExcInfo = tuple[type[BaseException], BaseException, TracebackType]
type ResponseData = dict[str, object]
type ResponseChunk = str | bytes | Mapping[str, object] | None


class ApiRoute(TypedDict):
    """Runtime routing contract shared by every v1 and v2 endpoint."""

    path_pattern: str
    supported_methods: list[str]
    call_method: str
    run_on_ioloop: NotRequired[bool]


def string_value(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def integer_value(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def optional_integer_value(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def float_value(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def boolean_value(value: object, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def integer_list_value(value: object) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int) and not isinstance(item, bool)]


class BaseApiError(Exception):
    """Expected API failure with an intentionally public response."""

    def __init__(
        self,
        public_message: str,
        *,
        messages: ErrorMessages | None = None,
        status_code: int = 400,
        private_detail: str | None = None,
    ) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.messages = dict(messages or {})
        self.status_code = status_code
        self.private_detail = private_detail or public_message


class BaseApiHandler(SecurityHeadersMixin, RequestHandler):
    api_version = 2
    routes: list[ApiRoute] = []
    route: ApiRoute | None = None
    error_messages: ErrorMessages = {}
    _defer_finish = False
    _finish_deferred = False
    _deferred_finish_chunk: ResponseChunk = None
    _deferred_finish_future: asyncio.Future[None]
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

    def initialize(self, **kwargs: object) -> None:
        self.params = kwargs.get("params", [])
        self.error_messages = {}

    def prepare(self) -> None:
        """Check cross-cutting API guards before routing to handler methods."""
        from compresso.webserver.api_v2.rate_limiter import get_rate_limiter

        if not self._authorize_request():
            return

        limiter = get_rate_limiter()
        remote_ip: object = self.request.remote_ip
        ip = remote_ip if isinstance(remote_ip, str) else ""
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

    def _request_api_path(self) -> str:
        path = self.request.path
        marker = f"/api/v{self.api_version}"
        if marker in path:
            return path.split(marker, 1)[1] or "/"
        return path

    def _is_read_only_post_path(self) -> bool:
        api_path = self._request_api_path()
        return any(api_path == path or api_path.startswith(path + "/") for path in READ_ONLY_POST_PATHS)

    def _requires_mutation_protection(self) -> bool:
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return False
        return not (self.request.method == "POST" and self._is_read_only_post_path())

    def _finish_auth_error(self, status: int, reason: str) -> bool:
        self.set_status(status, reason=reason)
        self.write_error()
        return False

    def _ensure_csrf_cookie(self) -> str:
        csrf_token = self.get_cookie(CSRF_COOKIE_NAME)
        if not csrf_token:
            csrf_token = secrets.token_urlsafe(32)
            self.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=False, samesite="Strict")
        return csrf_token

    @staticmethod
    def _explicit_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        if isinstance(value, int):
            return bool(value)
        return False

    def _authorize_request(self) -> bool:
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

    def set_default_headers(self) -> None:
        """
        Set the default response header to be JSON.
        This overwrites the RequestHandler method.

        :return:
        """
        self.set_header("Content-Type", 'application/json; charset="utf-8"')
        self.set_security_headers()

    @staticmethod
    def _require_response_mapping(value: object, *, source: str) -> ResponseData:
        """Narrow schema output before it crosses the HTTP response boundary."""
        if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
            raise exceptions.ValidationError(f"{source} must produce a JSON object")
        return {str(key): item for key, item in value.items()}

    def read_json_request(self, schema: Schema) -> ResponseData:
        """

        :param schema:
        :type schema: Schema descendant
        :return:
        """
        # Ensure body can be JSON decoded
        try:
            decoded: object = json.loads(self.request.body)
        except (JSONDecodeError, UnicodeDecodeError) as exc:
            invalid_json_messages: ErrorMessages = {"body": ["Invalid JSON payload"]}
            self.error_messages = invalid_json_messages
            raise BaseApiError(
                "Expected request body to be valid JSON",
                messages=invalid_json_messages,
                private_detail=f"{type(exc).__name__}: {exc}",
            ) from exc

        if not isinstance(decoded, Mapping) or not all(isinstance(key, str) for key in decoded):
            object_messages: ErrorMessages = {"body": ["Expected a JSON object"]}
            self.error_messages = object_messages
            raise BaseApiError("Expected request body to be a JSON object", messages=object_messages)
        json_data = {str(key): value for key, value in decoded.items()}

        raw_validation_errors = schema.validate(json_data)
        request_validation_errors: ErrorMessages = {str(key): value for key, value in raw_validation_errors.items()}
        if request_validation_errors:
            self.error_messages = request_validation_errors
            raise BaseApiError(
                "Failed request schema validation",
                messages=request_validation_errors,
                private_detail=f"Schema validation failed: {request_validation_errors}",
            )

        loaded: object = schema.load(json_data)
        dumped: object = schema.dump(loaded)
        return self._require_response_mapping(dumped, source="Request schema")

    def load_request(self, schema: Schema) -> ResponseData:
        """Load and validate a JSON request body."""
        return self.read_json_request(schema)

    def build_response(self, schema: Schema, response: Mapping[str, object]) -> ResponseData:
        """
        Validate the given response against a given Schema.
        Return the response data as a serialized object according to the given Schema's fields.

        :param schema:
        :param response:
        :return:
        """
        # Validate that schema.
        # This is not normally done with responses, but I want to be strict about ensuring the schema is up-to-date
        raw_validation_errors = schema.validate(response)
        validation_errors: ErrorMessages = {str(key): value for key, value in raw_validation_errors.items()}

        if validation_errors:
            # Throw an exception here with all the errors.
            # This will be caught and handled by the 500 internal error
            raise exceptions.ValidationError(validation_errors)

        # Build schema object from response
        data: object = schema.dump(response)
        return self._require_response_mapping(data, source="Response schema")

    def respond_with_schema(self, schema: Schema, response: Mapping[str, object]) -> None:
        """Validate, serialize, and send a successful schema response."""
        self.write_success(self.build_response(schema, response))

    def handle_base_api_error(self, exc: BaseApiError) -> None:
        """Standard handler for expected API errors."""
        error_id = secrets.token_hex(8)
        call_method = self.route.get("call_method") if self.route else None
        app_log.warning(LOG_BASE_API_ERROR, error_id, call_method, exc.private_detail)
        if self._response_already_committed():
            return
        self.error_messages = exc.messages
        self._api_error_id = error_id
        self.set_status(exc.status_code, reason=exc.public_message)
        self.write_error()

    def write_success(self, response: Mapping[str, object] | None = None) -> None:
        """
        Write data out as HTTP code 200
        Finishes this response, ending the HTTP request.

        :param response:
        :return:
        """
        if response is None:
            response = {"success": True}
        self.set_status(self.STATUS_SUCCESS)
        self.finish(dict(response))

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
        call_method = self.route.get("call_method") if self.route else None
        error_id = secrets.token_hex(8)
        app_log.exception(LOG_UNHANDLED_ERROR, error_id, self.__class__.__name__, call_method)
        if self._response_already_committed():
            return
        self.error_messages = {}
        self._api_error_id = error_id
        self.set_status(self.STATUS_ERROR_INTERNAL, reason="Internal server error")
        self.write_error()

    def write_api_error(
        self,
        status_code: int,
        public_reason: str,
        *,
        messages: ErrorMessages | None = None,
        error_id: str | None = None,
        exc_info: ExcInfo | None = None,
    ) -> None:
        """Own the complete structured error response for v2 API handlers."""
        if self._response_already_committed():
            return

        self.error_messages = messages or {}
        if self.get_status() != status_code or self._reason != public_reason:
            self.set_status(status_code, reason=public_reason)
        response: ResponseData = {
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

    def write_error(self, status_code: int | None = None, **kwargs: object) -> None:
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
        raw_exc_info = kwargs.get("exc_info")
        exc_info = cast(ExcInfo, raw_exc_info) if isinstance(raw_exc_info, tuple) and len(raw_exc_info) == 3 else None
        if status_code >= self.STATUS_ERROR_INTERNAL:
            public_reason = "Internal server error"
            if not error_id:
                error_id = secrets.token_hex(8)
                app_log.error(
                    "API error reached structured writer id=%s status=%s",
                    error_id,
                    status_code,
                    exc_info=exc_info,
                )
        self.write_api_error(
            status_code,
            public_reason,
            messages=self.error_messages,
            error_id=error_id,
            exc_info=exc_info,
        )

    @staticmethod
    def _route_method(handler: "BaseApiHandler", route: ApiRoute) -> Callable[..., object]:
        method = getattr(handler, route["call_method"], None)
        if not callable(method):
            raise BaseApiError(
                "Endpoint handler is unavailable",
                status_code=500,
                private_detail=f"Configured route method {route['call_method']!r} is not callable",
            )
        return cast(Callable[..., object], method)

    @staticmethod
    async def _await_route_result(result: Awaitable[object]) -> object:
        return await result

    async def _invoke_route(self, route: ApiRoute, *args: object, **kwargs: object) -> None:
        """Invoke one routed method and own any exception it lets escape."""
        self.route = route
        method = self._route_method(self, route)
        try:
            if route.get("run_on_ioloop") or not self.offload_route_bodies:
                result = method(*args, **kwargs)
                if inspect.isawaitable(result):
                    await cast(Awaitable[object], result)
            else:
                await self._invoke_route_offloaded(method, *args, **kwargs)
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as exc:
            self.handle_unhandled_error(exc)
        finally:
            self._apply_deferred_finish()

    async def _invoke_route_offloaded(
        self,
        method: Callable[..., object],
        *args: object,
        **kwargs: object,
    ) -> None:
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
        self._deferred_finish_future = asyncio.get_running_loop().create_future()

        def invoke() -> object:
            result = method(*args, **kwargs)
            if inspect.isawaitable(result):
                return asyncio.run(self._await_route_result(cast(Awaitable[object], result)))
            return result

        try:
            await asyncio.to_thread(invoke)
        finally:
            self._defer_finish = False

    def _response_already_committed(self) -> bool:
        """True when a response has been finished or is pending deferred finish."""
        return getattr(self, "_finished", False) or getattr(self, "_finish_deferred", False)

    def _apply_deferred_finish(self) -> None:
        """Complete a finish() that was deferred while the body ran off-loop."""
        if getattr(self, "_finish_deferred", False):
            self._finish_deferred = False
            chunk = self._deferred_finish_chunk
            self._deferred_finish_chunk = None
            if not self._finished:
                concrete_chunk = dict(chunk) if isinstance(chunk, Mapping) else chunk
                finish_future = super().finish(concrete_chunk)
                deferred_future = self._deferred_finish_future

                def complete_deferred(completed: asyncio.Future[None]) -> None:
                    if completed.cancelled():
                        deferred_future.cancel()
                    elif (exc := completed.exception()) is not None:
                        deferred_future.set_exception(exc)
                    else:
                        deferred_future.set_result(None)

                if isinstance(finish_future, asyncio.Future):
                    finish_future.add_done_callback(complete_deferred)
                else:
                    # Preserve compatibility with simple RequestHandler test
                    # doubles that complete synchronously and return None.
                    deferred_future.set_result(None)

    def finish(self, chunk: ResponseChunk = None) -> asyncio.Future[None]:
        if getattr(self, "_defer_finish", False):
            # Record the final chunk; it is handed to the real finish() on the
            # IOLoop thread once the offloaded body returns.
            self._deferred_finish_chunk = chunk
            self._finish_deferred = True
            return self._deferred_finish_future
        concrete_chunk = dict(chunk) if isinstance(chunk, Mapping) else chunk
        return super().finish(concrete_chunk)

    def handle_endpoint_not_found(self) -> None:
        """
        Return a JSON 404 error message.
        Finishes this response, ending the HTTP request.

        :return:
        """
        response = {"error": f"{self.STATUS_ERROR_ENDPOINT_NOT_FOUND:d}: Endpoint not found"}
        self.set_status(self.STATUS_ERROR_ENDPOINT_NOT_FOUND)
        self.finish(response)

    def handle_method_not_allowed(self) -> None:
        """
        Return a JSON 405 error message.
        Finishes this response, ending the HTTP request.

        :return:
        """
        response = {"error": f"{self.STATUS_ERROR_METHOD_NOT_ALLOWED:d}: Method '{self.request.method}' not allowed"}
        self.set_status(self.STATUS_ERROR_METHOD_NOT_ALLOWED)
        self.finish(response)

    async def _action_route_async(self) -> None:
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
            supported_methods = route["supported_methods"]

            # Fetch the path match from this route's path pattern
            path_pattern = request_api_base + route["path_pattern"]
            path_match = PathMatches(path_pattern)
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
                    app_log.debug(
                        "Routing API to {}.{}(*args={}, **kwargs={})".format(
                            self.__class__.__name__, route.get("call_method"), params["path_args"], params["path_kwargs"]
                        ),
                        exc_info=True,
                    )

                    raw_path_args: object = params["path_args"]
                    raw_path_kwargs: object = params["path_kwargs"]
                    path_args = tuple(raw_path_args) if isinstance(raw_path_args, (list, tuple)) else ()
                    path_kwargs = (
                        {str(key): value for key, value in raw_path_kwargs.items() if isinstance(key, str)}
                        if isinstance(raw_path_kwargs, Mapping)
                        else {}
                    )
                    await self._invoke_route(route, *path_args, **path_kwargs)
                    return

                # This route matches the current request URI and does not have any params.
                # Set this route and call the configured method.
                app_log.debug(f"Routing API to {self.__class__.__name__}.{route.get('call_method')}()", exc_info=True)
                await self._invoke_route(route)
                return

        if matched_route_with_unsupported_method:
            app_log.warning(f"Method not allowed for API route: {self.request.uri}", exc_info=True)
            self.handle_method_not_allowed()
        else:
            app_log.warning(f"No match found for API route: {self.request.uri}", exc_info=True)
            self.handle_endpoint_not_found()

    def action_route(self) -> Awaitable[None] | None:
        """Return v2 routing work; v1 overrides this with its legacy sync router."""
        return self._action_route_async()

    async def _dispatch_action_route(self) -> None:
        """Support both the asynchronous v2 router and the legacy sync v1 router."""
        result: object = self.action_route()
        if inspect.isawaitable(result):
            await cast(Awaitable[object], result)

    async def delete(self, path: str) -> None:
        """
        Route all DELETE requests to the 'action_route()' method

        :param path:
        :return:
        """
        await self._dispatch_action_route()

    async def get(self, path: str) -> None:
        """
        Route all GET requests to the 'action_route()' method

        :param path:
        :return:
        """
        await self._dispatch_action_route()

    async def post(self, path: str) -> None:
        """
        Route all POST requests to the 'action_route()' method

        :param path:
        :return:
        """
        await self._dispatch_action_route()

    async def put(self, path: str) -> None:
        """
        Route all PUT requests to the 'action_route()' method

        :param path:
        :return:
        """
        await self._dispatch_action_route()
