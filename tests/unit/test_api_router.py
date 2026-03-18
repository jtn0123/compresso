#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

import pytest
import tornado.routing
import tornado.testing
import tornado.web
from unittest.mock import patch

from unmanic.webserver.api_request_router import APIRequestRouter


class ApiRouterTestBase(tornado.testing.AsyncHTTPTestCase):
    __test__ = False

    def runTest(self):
        pass

    def get_app(self):
        app = tornado.web.Application([])
        app.add_handlers(r'.*', [
            (
                tornado.routing.PathMatches(r"/unmanic/api/.*"),
                APIRequestRouter(app),
            ),
        ])
        return app

    def parse_response(self, response):
        return json.loads(response.body.decode('utf-8'))


@pytest.mark.unittest
class TestApiRouter(ApiRouterTestBase):
    __test__ = True

    @patch('unmanic.libs.session.Session')
    def test_version_route_resolves_through_router(self, _mock_session):
        response = self.fetch('/unmanic/api/v2/version/read', method='GET')
        assert response.code == 200
        data = self.parse_response(response)
        assert 'version' in data

    @patch('unmanic.webserver.helpers.healthcheck.get_startup_readiness')
    def test_readiness_route_resolves_through_router(self, mock_readiness):
        mock_readiness.return_value = {
            'ready': True,
            'stages': {
                'config_loaded': True,
                'startup_validation': True,
                'db_ready': True,
                'threads_ready': True,
                'ui_server_ready': True,
            },
            'details': {'ui_server_ready': '0.0.0.0:8888'},
            'errors': [],
        }

        response = self.fetch('/unmanic/api/v2/healthcheck/readiness', method='GET')
        assert response.code == 200
        data = self.parse_response(response)
        assert data['ready'] is True

    def test_unknown_route_returns_404(self):
        response = self.fetch('/unmanic/api/v2/does-not-exist/foo', method='GET')
        assert response.code == 404
