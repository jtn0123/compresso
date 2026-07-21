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

from collections.abc import Mapping

from tornado.log import app_log
from tornado.routing import PathMatches

from compresso.webserver.api_v2.base_api_handler import (
    ApiRoute,
)
from compresso.webserver.api_v2.base_api_handler import (
    BaseApiHandler as V2BaseApiHandler,
)


class BaseApiHandler(V2BaseApiHandler):
    """Deprecated v1 router with the same cross-cutting guards as API v2."""

    api_version = 1
    routes: list[ApiRoute] = []
    MUTATING_GET_PATHS = frozenset({"/pending/rescan", "/plugins/repos/fetch"})

    def set_default_headers(self) -> None:
        super().set_default_headers()
        self.set_header("Deprecation", "true")
        self.set_header("Warning", '299 Compresso "API v1 is deprecated and will be removed in the next major release"')

    def _requires_mutation_protection(self) -> bool:
        if self.request.method == "GET" and self._request_api_path() in self.MUTATING_GET_PATHS:
            return True
        return super()._requires_mutation_protection()

    def handle_404(self) -> None:
        self.set_status(404)
        self.write("404 Not Found")

    def action_route(self) -> None:
        request_api_endpoint = (self.request.uri or "").split("?", 1)[0]
        if request_api_endpoint.startswith("/compresso"):
            request_api_endpoint = request_api_endpoint[len("/compresso") :]
        for route in self.routes:
            # Check if the rout supports the supported http methods
            supported_methods = route.get("supported_methods")
            if supported_methods and self.request.method not in supported_methods:
                # The request's method is not supported by this route.
                continue

            # If the route does not have any params an it matches the current request URI, then route to that method.
            if list(filter(None, request_api_endpoint.split("/"))) == list(filter(None, route.get("path_pattern").split("/"))):
                app_log.debug(f"Routing API to {self.__class__.__name__}.{route.get('call_method')}()", exc_info=True)
                self._route_method(self, route)()
                return

            # Fetch the path match from this route's path pattern
            path_match = PathMatches(route["path_pattern"])

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
                self._route_method(self, route)(*path_args, **path_kwargs)
                return

        # If we got this far, then the URI does not match any of our configured routes.
        app_log.warning(f"No match found for API route: {self.request.uri}", exc_info=True)
        self.handle_404()
