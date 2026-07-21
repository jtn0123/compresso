#!/usr/bin/env python3

"""
compresso.swagger.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     01 Aug 2021, (10:35 AM)

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

from collections.abc import Iterator, Mapping
from typing import Protocol, cast

from apispec import yaml_utils
from apispec.exceptions import APISpecError
from apispec_webframeworks.tornado import TornadoPlugin
from tornado.routing import PathMatches, URLSpec
from tornado.web import RequestHandler

from compresso.webserver.api_v2.base_api_handler import ApiRoute


class _DocumentedHandler(Protocol):
    routes: list[ApiRoute]


class CompressoSpecPlugin(TornadoPlugin):
    """APISpec plugin for Compresso"""

    @staticmethod
    def _operations_from_urlspec(urlspec: URLSpec) -> Iterator[dict[str, object]]:
        """Generator of operations described in the handler's routes list

        :param urlspec:
        :type urlspec: URLSpec descendant
        """
        handler_class = cast("type[_DocumentedHandler]", urlspec.handler_class)
        for r in handler_class.routes:
            matcher = PathMatches(r.get("path_pattern"))
            if matcher.regex == urlspec.regex:
                for http_method in r.get("supported_methods", []):
                    method = getattr(handler_class, r["call_method"])
                    operation_data = yaml_utils.load_yaml_from_docstring(method.__doc__)
                    if isinstance(operation_data, Mapping):
                        operation: dict[str, object] = {http_method.lower(): dict(operation_data)}
                        yield operation

    def path_helper(
        self,
        path: str | None = None,
        operations: dict[object, object] | None = None,
        parameters: list[dict[object, object]] | None = None,
        *,
        urlspec: URLSpec | tuple[object, ...] | None = None,
        **kwargs: object,
    ) -> str | None:
        """Path helper that allows passing a Tornado URLSpec or tuple."""
        del path, parameters, kwargs
        if urlspec is None:
            raise APISpecError("A Tornado URLSpec is required")
        if not isinstance(urlspec, URLSpec):
            if len(urlspec) < 2 or len(urlspec) > 4:
                raise APISpecError("Invalid Tornado URLSpec tuple")
            pattern, handler = urlspec[:2]
            if not isinstance(pattern, str) or not isinstance(handler, type) or not issubclass(handler, RequestHandler):
                raise APISpecError("Invalid Tornado URLSpec tuple")
            handler_kwargs_value = urlspec[2] if len(urlspec) >= 3 else None
            name_value = urlspec[3] if len(urlspec) >= 4 else None
            if handler_kwargs_value is not None and not isinstance(handler_kwargs_value, dict):
                raise APISpecError("Invalid Tornado handler arguments")
            if name_value is not None and not isinstance(name_value, str):
                raise APISpecError("Invalid Tornado route name")
            handler_kwargs = (
                {str(key): value for key, value in handler_kwargs_value.items()} if handler_kwargs_value is not None else None
            )
            urlspec = URLSpec(pattern, handler, handler_kwargs, name_value)
        if operations is None:
            operations = {}
        for operation in self._operations_from_urlspec(urlspec):
            operations.update(operation)
        if not operations:
            raise APISpecError(f"Could not find endpoint for urlspec {urlspec}")
        method_name = next(iter(operations))
        if not isinstance(method_name, str):
            raise APISpecError(f"Invalid operation method for urlspec {urlspec}")
        params_method = getattr(urlspec.handler_class, method_name)
        operations.update(self._extensions_from_handler(urlspec.handler_class))
        return self.tornadopath2openapi(urlspec, params_method)
