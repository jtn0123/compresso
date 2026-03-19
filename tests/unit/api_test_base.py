#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.api_test_base.py

    Base class for testing Tornado API handlers using tornado.testing.

"""

import json

import tornado.testing
import tornado.web


class ApiTestBase(tornado.testing.AsyncHTTPTestCase):
    """
    Base class for API handler tests.

    Subclasses must set `handler_class` to the handler class under test.
    """
    # Tell pytest not to collect this base class directly
    __test__ = False

    handler_class = None

    def setUp(self):
        if self.handler_class is None:
            return
        # Reset the rate limiter singleton between tests
        import compresso.webserver.api_v2.rate_limiter as rl_module
        rl_module._rate_limiter = None
        super().setUp()

    def tearDown(self):
        if self.handler_class is None:
            return
        super().tearDown()

    def runTest(self):
        pass

    def get_app(self):
        if self.handler_class is None:
            raise NotImplementedError("Subclass must set handler_class")
        return tornado.web.Application([
            (r"/compresso/api/v2/(.*)", self.handler_class),
        ])

    def post_json(self, path, body=None):
        """POST JSON to the API and return the response."""
        if body is None:
            body = {}
        response = self.fetch(
            '/compresso/api/v2' + path,
            method='POST',
            body=json.dumps(body),
            headers={'Content-Type': 'application/json'},
        )
        return response

    def get_json(self, path):
        """GET from the API and return the response."""
        response = self.fetch('/compresso/api/v2' + path, method='GET')
        return response

    def parse_response(self, response):
        """Parse a response body as JSON."""
        return json.loads(response.body.decode('utf-8'))
