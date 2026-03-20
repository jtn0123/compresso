#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_pending_api.py

    Tests for the pending API handler endpoints.

"""

import json
import queue

import pytest
from unittest.mock import patch, MagicMock

from tests.unit.api_test_base import ApiTestBase
from compresso.webserver.api_v2.pending_api import ApiPendingHandler

PENDING_HELPERS = 'compresso.webserver.helpers.pending_tasks'


def _mock_initialize(self, **kwargs):
    """Stub out ApiPendingHandler.initialize to avoid loading real session/queues."""
    self.session = MagicMock()
    self.params = kwargs.get("params")
    # Use a real queue so .full() behaves correctly
    q = queue.Queue(maxsize=1)
    self.compresso_data_queues = {
        'library_scanner_triggers': q,
    }


@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiGetTasks(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.prepare_filtered_pending_tasks')
    def test_get_pending_tasks_success(self, mock_tasks):
        mock_tasks.return_value = {
            'recordsTotal': 5,
            'recordsFiltered': 3,
            'results': [],
        }
        resp = self.post_json('/pending/tasks', {'start': 0, 'length': 10})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['recordsTotal'] == 5

    def test_get_pending_tasks_invalid_json(self):
        resp = self.fetch(
            '/compresso/api/v2/pending/tasks',
            method='POST',
            body='not json',
            headers={'Content-Type': 'application/json'},
        )
        assert resp.code == 400

    @patch(PENDING_HELPERS + '.prepare_filtered_pending_tasks')
    def test_get_pending_tasks_internal_error(self, mock_tasks):
        mock_tasks.side_effect = Exception("DB error")
        resp = self.post_json('/pending/tasks', {'start': 0, 'length': 10})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiDeleteTasks(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.remove_pending_tasks', return_value=True)
    def test_delete_pending_tasks_success(self, _mock_remove):
        resp = self.fetch(
            '/compresso/api/v2/pending/tasks',
            method='DELETE',
            body=json.dumps({'id_list': [1, 2, 3]}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 200

    @patch(PENDING_HELPERS + '.remove_pending_tasks', return_value=False)
    def test_delete_pending_tasks_failure(self, _mock_remove):
        resp = self.fetch(
            '/compresso/api/v2/pending/tasks',
            method='DELETE',
            body=json.dumps({'id_list': [1]}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500

    def test_delete_pending_tasks_empty_list(self):
        resp = self.fetch(
            '/compresso/api/v2/pending/tasks',
            method='DELETE',
            body=json.dumps({'id_list': []}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 400


@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiRescan(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    def test_trigger_rescan_success(self):
        resp = self.post_json('/pending/rescan', {})
        assert resp.code == 200

    def test_trigger_rescan_queue_full(self):
        def _mock_init_full(self, **kwargs):
            self.session = MagicMock()
            self.params = kwargs.get("params")
            q = queue.Queue(maxsize=1)
            q.put('dummy')  # Fill the queue
            self.compresso_data_queues = {
                'library_scanner_triggers': q,
            }

        with patch.object(ApiPendingHandler, 'initialize', _mock_init_full):
            resp = self.post_json('/pending/rescan', {})
            assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiReorder(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.reorder_pending_tasks', return_value=True)
    def test_reorder_tasks_success(self, _mock_reorder):
        resp = self.post_json('/pending/reorder', {
            'id_list': [3, 1, 2],
            'position': 'top',
        })
        assert resp.code == 200

    @patch(PENDING_HELPERS + '.reorder_pending_tasks', return_value=False)
    def test_reorder_tasks_failure(self, _mock_reorder):
        resp = self.post_json('/pending/reorder', {
            'id_list': [1],
            'position': 'top',
        })
        assert resp.code == 500

    def test_reorder_tasks_empty_list(self):
        resp = self.post_json('/pending/reorder', {
            'id_list': [],
            'position': 'top',
        })
        assert resp.code == 400


@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiStatusGet(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.fetch_tasks_status')
    def test_get_status_success(self, mock_status):
        mock_status.return_value = [
            {
                'id': 1,
                'abspath': '/a.mkv',
                'status': 'pending',
                'priority': 100,
                'type': 'local',
            },
        ]
        resp = self.post_json('/pending/status/get', {'id_list': [1]})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert len(data['results']) == 1

    @patch(PENDING_HELPERS + '.fetch_tasks_status', return_value=None)
    def test_get_status_failure(self, _mock_status):
        resp = self.post_json('/pending/status/get', {'id_list': [1]})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiStatusSetReady(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.update_pending_tasks_status', return_value=True)
    def test_set_ready_success(self, _mock_update):
        resp = self.post_json('/pending/status/set/ready', {'id_list': [1, 2]})
        assert resp.code == 200

    @patch(PENDING_HELPERS + '.update_pending_tasks_status', return_value=False)
    def test_set_ready_failure(self, _mock_update):
        resp = self.post_json('/pending/status/set/ready', {'id_list': [1]})
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiLibraryUpdate(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.update_pending_tasks_library', return_value=True)
    def test_set_library_success(self, _mock_update):
        resp = self.post_json('/pending/library/update', {
            'id_list': [1, 2],
            'library_name': 'Movies',
        })
        assert resp.code == 200

    @patch(PENDING_HELPERS + '.update_pending_tasks_library', return_value=False)
    def test_set_library_failure(self, _mock_update):
        resp = self.post_json('/pending/library/update', {
            'id_list': [1],
            'library_name': 'Movies',
        })
        assert resp.code == 500
