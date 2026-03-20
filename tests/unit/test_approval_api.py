#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_approval_api.py

    Tests for the approval API handler endpoints.
    Covers: get_approval_tasks, approve_tasks, reject_tasks,
    get_task_detail, get_approval_count.
"""

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType
from tests.unit.api_test_base import ApiTestBase
from compresso.webserver.api_v2.approval_api import ApiApprovalHandler

APPROVAL_HELPERS = 'compresso.webserver.helpers.approval'


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


# ------------------------------------------------------------------
# Get approval tasks
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiApprovalHandler, 'initialize', _mock_initialize)
class TestApprovalApiGetTasks(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + '.prepare_filtered_approval_tasks')
    def test_get_approval_tasks_success(self, mock_tasks):
        mock_tasks.return_value = {
            'recordsTotal': 2,
            'recordsFiltered': 1,
            'results': [
                {'id': 1, 'abspath': '/media/v.mp4', 'status': 'awaiting_approval'},
            ],
        }
        resp = self.post_json('/approval/tasks', {
            'start': 0, 'length': 10,
        })
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['recordsTotal'] == 2

    @patch(APPROVAL_HELPERS + '.prepare_filtered_approval_tasks')
    def test_get_approval_tasks_error(self, mock_tasks):
        mock_tasks.side_effect = Exception("DB error")
        resp = self.post_json('/approval/tasks', {'start': 0, 'length': 10})
        assert resp.code == 500

    def test_get_approval_tasks_invalid_json(self):
        resp = self.fetch(
            '/compresso/api/v2/approval/tasks',
            method='POST',
            body='not json',
            headers={'Content-Type': 'application/json'},
        )
        assert resp.code == 400


# ------------------------------------------------------------------
# Approve tasks
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiApprovalHandler, 'initialize', _mock_initialize)
class TestApprovalApiApprove(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + '.approve_tasks')
    def test_approve_tasks_success(self, mock_approve):
        resp = self.post_json('/approval/approve', {'id_list': [1, 2]})
        assert resp.code == 200
        mock_approve.assert_called_once_with([1, 2])

    @patch(APPROVAL_HELPERS + '.approve_tasks')
    def test_approve_tasks_error(self, mock_approve):
        mock_approve.side_effect = Exception("error")
        resp = self.post_json('/approval/approve', {'id_list': [1]})
        assert resp.code == 500


# ------------------------------------------------------------------
# Reject tasks
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiApprovalHandler, 'initialize', _mock_initialize)
class TestApprovalApiReject(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + '.reject_tasks')
    def test_reject_tasks_success(self, mock_reject):
        resp = self.post_json('/approval/reject', {'id_list': [1]})
        assert resp.code == 200
        mock_reject.assert_called_once_with(task_ids=[1], requeue=False)

    @patch(APPROVAL_HELPERS + '.reject_tasks')
    def test_reject_tasks_with_requeue(self, mock_reject):
        resp = self.post_json('/approval/reject', {'id_list': [1], 'requeue': True})
        assert resp.code == 200
        mock_reject.assert_called_once_with(task_ids=[1], requeue=True)

    @patch(APPROVAL_HELPERS + '.reject_tasks')
    def test_reject_tasks_error(self, mock_reject):
        mock_reject.side_effect = Exception("error")
        resp = self.post_json('/approval/reject', {'id_list': [1]})
        assert resp.code == 500


# ------------------------------------------------------------------
# Get task detail
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiApprovalHandler, 'initialize', _mock_initialize)
class TestApprovalApiDetail(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + '.get_approval_task_detail')
    def test_get_detail_success(self, mock_detail):
        mock_detail.return_value = {
            'id': 1,
            'abspath': '/media/v.mp4',
            'source_size': 1000,
            'staged_size': 500,
            'staged_path': '/cache/v.mp4',
            'size_delta': -500,
            'size_ratio': 0.5,
            'cache_path': '/cache',
            'start_time': '2024-01-01',
            'finish_time': '2024-01-01',
            'log': '',
            'library_id': 1,
        }
        resp = self.post_json('/approval/detail', {'id': 1})
        assert resp.code == 200

    @patch(APPROVAL_HELPERS + '.get_approval_task_detail', return_value=None)
    def test_get_detail_not_found(self, _mock_detail):
        resp = self.post_json('/approval/detail', {'id': 999})
        assert resp.code == 400

    @patch(APPROVAL_HELPERS + '.get_approval_task_detail')
    def test_get_detail_error(self, mock_detail):
        mock_detail.side_effect = Exception("error")
        resp = self.post_json('/approval/detail', {'id': 1})
        assert resp.code == 500


# ------------------------------------------------------------------
# Get approval count
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiApprovalHandler, 'initialize', _mock_initialize)
class TestApprovalApiCount(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + '.get_approval_count', return_value=5)
    def test_get_count_success(self, _mock_count):
        resp = self.get_json('/approval/count')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['count'] == 5

    @patch(APPROVAL_HELPERS + '.get_approval_count')
    def test_get_count_error(self, mock_count):
        mock_count.side_effect = Exception("error")
        resp = self.get_json('/approval/count')
        assert resp.code == 500
