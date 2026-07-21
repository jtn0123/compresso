#!/usr/bin/env python3

"""
compresso.request_handler.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     28 Oct 2021, (7:24 PM)

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
from typing import Protocol, TypedDict, Unpack, cast

import requests
from requests.auth import HTTPBasicAuth
from requests.models import Response

from compresso.libs.constants import API_AUTH_HEADER_NAME

DEFAULT_TIMEOUT = 30
type Timeout = float | tuple[float | None, float | None] | None


class RequestOptions(TypedDict, total=False):
    headers: Mapping[str, str | bytes] | None
    timeout: Timeout
    data: object
    json: object
    params: object
    stream: bool | None
    allow_redirects: bool
    verify: bool | str | None
    cert: str | tuple[str, str] | None
    auth: HTTPBasicAuth | None


class _RequestCallable(Protocol):
    def __call__(self, url: str | bytes, **kwargs: Unpack[RequestOptions]) -> Response: ...


class RequestHandler:
    def __init__(
        self,
        *args: object,
        auth: str = "",
        timeout: Timeout = DEFAULT_TIMEOUT,
        username: str | None = None,
        password: str | None = None,
        api_token: str | None = None,
    ) -> None:
        self.auth = auth
        self.timeout = timeout
        self.username = username or ""
        self.password = password or ""
        self.api_token = api_token or ""

    def __get_request_auth(self) -> HTTPBasicAuth | None:
        request_auth: HTTPBasicAuth | None = None
        if self.auth and self.auth.lower() == "basic":
            request_auth = HTTPBasicAuth(self.username, self.password)
        return request_auth

    def __prepare_kwargs(self, kwargs: RequestOptions) -> RequestOptions:
        kwargs.setdefault("timeout", self.timeout)
        if self.api_token:
            headers = dict(kwargs.get("headers") or {})
            headers[API_AUTH_HEADER_NAME] = self.api_token
            kwargs["headers"] = headers
        return kwargs

    def __request(self, request: _RequestCallable, url: str | bytes, kwargs: RequestOptions) -> Response:
        kwargs = self.__prepare_kwargs(kwargs)
        kwargs["auth"] = self.__get_request_auth()
        return request(url, **kwargs)  # noqa: S113 — timeout set via kwargs.setdefault above

    def get(self, url: str | bytes, **kwargs: Unpack[RequestOptions]) -> Response:
        return self.__request(cast("_RequestCallable", requests.get), url, kwargs)

    def post(self, url: str | bytes, **kwargs: Unpack[RequestOptions]) -> Response:
        return self.__request(cast("_RequestCallable", requests.post), url, kwargs)

    def put(self, url: str | bytes, **kwargs: Unpack[RequestOptions]) -> Response:
        return self.__request(cast("_RequestCallable", requests.put), url, kwargs)

    def patch(self, url: str | bytes, **kwargs: Unpack[RequestOptions]) -> Response:
        return self.__request(cast("_RequestCallable", requests.patch), url, kwargs)

    def delete(self, url: str | bytes, **kwargs: Unpack[RequestOptions]) -> Response:
        return self.__request(cast("_RequestCallable", requests.delete), url, kwargs)
