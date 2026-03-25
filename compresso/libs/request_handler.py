#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
import requests
from requests.auth import HTTPBasicAuth


class RequestHandler:

    def __init__(self, *args, **kwargs):
        self.auth = kwargs.get('auth', '')
        # Set username (could be passed in as None)
        self.username = ''
        if kwargs.get('username'):
            self.username = kwargs.get('username')
        # Set password (could be passed in as None)
        self.password = ''
        if kwargs.get('password'):
            self.password = kwargs.get('password')

    def __get_request_auth(self):
        request_auth = None
        if self.auth and self.auth.lower() == 'basic':
            request_auth = HTTPBasicAuth(self.username, self.password)
        return request_auth

    def get(self, url, **kwargs):
        return requests.get(url, auth=self.__get_request_auth(), **kwargs)

    def post(self, url, **kwargs):
        return requests.post(url, auth=self.__get_request_auth(), **kwargs)

    def delete(self, url, **kwargs):
        return requests.delete(url, auth=self.__get_request_auth(), **kwargs)
