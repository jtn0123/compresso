#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_history_api.py

    Tests for the history API handler endpoints.

"""

import json
import pytest
from unittest.mock import patch, MagicMock

from tests.unit.api_test_base import ApiTestBase
from compresso.webserver.api_v2.history_api import ApiHistoryHandler

COMPLETED_TASKS = 'compresso.webserver.helpers.completed_tasks'


def _mock_initialize(self, **kwargs):
    """Stub out ApiHistoryHandler.initialize to avoid loading real config/session."""
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}
    self.config = MagicMock()


@pytest.mark.unittest
@patch.object(ApiHistoryHandler, 'initialize', _mock_initialize)
class TestHistoryApiGetTasks(ApiTestBase):
    __test__ = True
    handler_class = ApiHistoryHandler

    @patch(COMPLETED_TASKS + '.prepare_filtered_completed_tasks')
    def test_get_completed_tasks_success(self, mock_prepare):
        mock_prepare.return_value = {
            'recordsTotal': 2,
            'recordsFiltered': 2,
            'successCount': 1,
            'failedCount': 1,
            'results': [
                {'id': 1, 'task_label': 'a.mkv', 'task_success': True, 'finish_time': 1704067200, 'has_metadata': False},
                {'id': 2, 'task_label': 'b.mkv', 'task_success': False, 'finish_time': 1704153600, 'has_metadata': False},
            ],
        }
        resp = self.post_json('/history/tasks', {
            'start': 0,
            'length': 10,
        })
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['recordsTotal'] == 2
        assert len(data['results']) == 2

    @patch(COMPLETED_TASKS + '.prepare_filtered_completed_tasks')
    def test_get_completed_tasks_with_filters(self, mock_prepare):
        """Verify filter params are passed through to helper."""
        mock_prepare.return_value = {
            'recordsTotal': 1,
            'recordsFiltered': 1,
            'successCount': 1,
            'failedCount': 0,
            'results': [
                {'id': 1, 'task_label': 'a.mkv', 'task_success': True, 'finish_time': 1704067200, 'has_metadata': False},
            ],
        }
        resp = self.post_json('/history/tasks', {
            'start': 5,
            'length': 25,
            'search_value': 'movie',
            'status': 'success',
            'order_by': 'task_label',
            'order_direction': 'asc',
        })
        assert resp.code == 200
        call_args = mock_prepare.call_args[0][0]
        assert call_args['start'] == 5
        assert call_args['length'] == 25
        assert call_args['search_value'] == 'movie'
        assert call_args['status'] == 'success'
        assert call_args['order']['column'] == 'task_label'
        assert call_args['order']['dir'] == 'asc'

    @patch(COMPLETED_TASKS + '.prepare_filtered_completed_tasks')
    def test_get_completed_tasks_empty_results(self, mock_prepare):
        mock_prepare.return_value = {
            'recordsTotal': 0,
            'recordsFiltered': 0,
            'successCount': 0,
            'failedCount': 0,
            'results': [],
        }
        resp = self.post_json('/history/tasks', {'start': 0, 'length': 10})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['recordsTotal'] == 0
        assert data['results'] == []

    @patch(COMPLETED_TASKS + '.prepare_filtered_completed_tasks')
    def test_get_completed_tasks_response_has_all_fields(self, mock_prepare):
        mock_prepare.return_value = {
            'recordsTotal': 1,
            'recordsFiltered': 1,
            'successCount': 1,
            'failedCount': 0,
            'results': [
                {'id': 1, 'task_label': 'x.mkv', 'task_success': True, 'finish_time': 1704067200, 'has_metadata': True},
            ],
        }
        resp = self.post_json('/history/tasks', {'start': 0, 'length': 10})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'recordsTotal' in data
        assert 'recordsFiltered' in data
        assert 'successCount' in data
        assert 'failedCount' in data
        assert 'results' in data
        row = data['results'][0]
        assert row['task_label'] == 'x.mkv'
        assert row['task_success'] is True

    @patch(COMPLETED_TASKS + '.prepare_filtered_completed_tasks')
    def test_get_completed_tasks_internal_error(self, mock_prepare):
        mock_prepare.side_effect = Exception("DB error")
        resp = self.post_json('/history/tasks', {
            'start': 0,
            'length': 10,
        })
        assert resp.code == 500


@pytest.mark.unittest
@patch.object(ApiHistoryHandler, 'initialize', _mock_initialize)
class TestHistoryApiDeleteTasks(ApiTestBase):
    __test__ = True
    handler_class = ApiHistoryHandler

    @patch(COMPLETED_TASKS + '.remove_completed_tasks', return_value=True)
    def test_delete_tasks_success(self, mock_remove):
        resp = self.fetch(
            '/compresso/api/v2/history/tasks',
            method='DELETE',
            body=json.dumps({'id_list': [1, 2]}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 200
        mock_remove.assert_called_once_with([1, 2])

    @patch(COMPLETED_TASKS + '.remove_completed_tasks', return_value=False)
    def test_delete_tasks_failure(self, mock_remove):
        resp = self.fetch(
            '/compresso/api/v2/history/tasks',
            method='DELETE',
            body=json.dumps({'id_list': [1]}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 500

    def test_delete_tasks_empty_list(self):
        resp = self.fetch(
            '/compresso/api/v2/history/tasks',
            method='DELETE',
            body=json.dumps({'id_list': []}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 400


@pytest.mark.unittest
@patch.object(ApiHistoryHandler, 'initialize', _mock_initialize)
class TestHistoryApiReprocess(ApiTestBase):
    __test__ = True
    handler_class = ApiHistoryHandler

    @patch(COMPLETED_TASKS + '.add_historic_tasks_to_pending_tasks_list', return_value={})
    def test_reprocess_success(self, mock_add):
        resp = self.post_json('/history/reprocess', {
            'id_list': [1, 2],
        })
        assert resp.code == 200

    @patch(COMPLETED_TASKS + '.add_historic_tasks_to_pending_tasks_list')
    def test_reprocess_with_errors(self, mock_add):
        mock_add.return_value = {1: "Path does not exist"}
        resp = self.post_json('/history/reprocess', {
            'id_list': [1],
        })
        assert resp.code == 500

    def test_reprocess_empty_list(self):
        resp = self.post_json('/history/reprocess', {
            'id_list': [],
        })
        assert resp.code == 400


@pytest.mark.unittest
@patch.object(ApiHistoryHandler, 'initialize', _mock_initialize)
class TestHistoryApiTaskLog(ApiTestBase):
    __test__ = True
    handler_class = ApiHistoryHandler

    @patch(COMPLETED_TASKS + '.read_command_log_for_task')
    def test_get_task_log_success(self, mock_read):
        mock_read.return_value = {
            'command_log': 'RUNNER: test\nCOMMAND: ffmpeg ...',
            'command_log_lines': ['<b>RUNNER: test</b>', '<pre>ffmpeg ...</pre>'],
        }
        resp = self.post_json('/history/task/log', {'task_id': 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert 'command_log' in data

    @patch(COMPLETED_TASKS + '.read_command_log_for_task')
    def test_get_task_log_internal_error(self, mock_read):
        mock_read.side_effect = Exception("DB error")
        resp = self.post_json('/history/task/log', {'task_id': 1})
        assert resp.code == 500
