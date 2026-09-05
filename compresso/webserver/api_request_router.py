#!/usr/bin/env python3

"""
compresso.api_request_router.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     25 Oct 2020, (8:26 PM)

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

import importlib

import tornado.routing
import tornado.web
from tornado.httputil import HTTPMessageDelegate, HTTPServerRequest
from tornado.log import app_log
from tornado.web import Application, RequestHandler

from compresso import config


def endpoint_handler_name(api_version: str, endpoint: str, path: str) -> str:
    """Select the one split upload handler while preserving legacy routing."""
    if endpoint == "upload" and path == f"/compresso/api/{api_version}/upload/plugin/file":
        return "ApiPluginUploadHandler"
    return f"Api{endpoint.title()}Handler"


class Handle404(tornado.web.RequestHandler):
    def initialize(self, **kwargs: object) -> None:
        """No-op — 404 handler requires no initialization."""

    def get(self, *args: str, **kwargs: str) -> None:
        self.set_status(404)
        self.write("404 Not Found")


class APIRequestRouter(tornado.routing.Router):
    app: Application
    config: config.Config

    def __init__(self, app: Application, **kwargs: object) -> None:
        self.app = app
        self.config = config.Config()

    def find_handler(self, request: HTTPServerRequest, **kwargs: object) -> HTTPMessageDelegate | None:
        # Check for proxy header
        target_id = request.headers.get("X-Compresso-Target-Installation")
        if target_id and target_id.lower() != "local":
            # Return proxy handler
            from compresso.webserver.proxy import ProxyHandler

            return self.app.get_handler_delegate(request, ProxyHandler)

        path_parts = request.path.split("/")
        if len(path_parts) < 5:
            return self.app.get_handler_delegate(request, Handle404)
        api_version = path_parts[3]  # Set API version
        endpoint = path_parts[4]  # Set the endpoint
        params = list(filter(None, path_parts[4:]))  # Set the request params

        endpoint_handler = endpoint_handler_name(api_version, endpoint, request.path)

        # Check if the handler exists - Otherwise set it to 404
        try:
            # Fetch handler class from api module matching api version
            candidate = getattr(importlib.import_module(f"compresso.webserver.api_{api_version}"), endpoint_handler)
            if not isinstance(candidate, type) or not issubclass(candidate, RequestHandler):
                raise AttributeError(endpoint_handler)
            handler: type[RequestHandler] = candidate
        except (AttributeError, KeyError, ModuleNotFoundError):
            app_log.warning(f"Unable to find handler for path: {endpoint_handler}", exc_info=True)
            handler = Handle404

        # Return handler
        return self.app.get_handler_delegate(
            request,
            handler,
            target_kwargs=dict(
                params=params,
            ),
            path_args=[request.path.encode("utf-8")],
        )
