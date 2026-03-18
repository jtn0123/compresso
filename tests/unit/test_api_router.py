#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json

import pytest
import tornado.routing
import tornado.testing
import tornado.web
from unittest.mock import MagicMock, patch

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

    @patch('unmanic.webserver.api_v2.history_api.completed_tasks.prepare_filtered_completed_tasks')
    @patch('unmanic.webserver.api_v2.history_api.session.Session')
    @patch('unmanic.webserver.api_v2.history_api.config.Config')
    @patch('unmanic.webserver.api_v2.history_api.UnmanicDataQueues')
    def test_history_route_resolves_through_router(
            self,
            mock_data_queues,
            mock_config,
            _mock_session,
            mock_prepare,
    ):
        mock_data_queues.return_value.get_unmanic_data_queues.return_value = {}
        mock_config.return_value = MagicMock()
        mock_prepare.return_value = {
            'recordsTotal': 1,
            'recordsFiltered': 1,
            'successCount': 1,
            'failedCount': 0,
            'results': [
                {'id': 1, 'task_label': 'movie.mkv', 'task_success': True, 'finish_time': 1704067200, 'has_metadata': False},
            ],
        }

        response = self.fetch(
            '/unmanic/api/v2/history/tasks',
            method='POST',
            body=json.dumps({'start': 0, 'length': 10}),
            headers={'Content-Type': 'application/json'},
        )

        assert response.code == 200
        data = self.parse_response(response)
        assert data['recordsTotal'] == 1
        assert len(data['results']) == 1

    def test_unknown_route_returns_404(self):
        response = self.fetch('/unmanic/api/v2/does-not-exist/foo', method='GET')
        assert response.code == 404
