#!/usr/bin/env python3

"""
tests.unit.test_approval_api.py

Tests for the approval API handler endpoints.
Covers: get_approval_tasks, approve_tasks, reject_tasks,
get_task_detail, get_approval_count.
"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v2.approval_api import ApiApprovalHandler
from tests.unit.api_test_base import ApiTestBase

APPROVAL_HELPERS = "compresso.webserver.helpers.approval"


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
@patch.object(ApiApprovalHandler, "initialize", _mock_initialize)
class TestApprovalApiGetTasks(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + ".prepare_filtered_approval_tasks")
    def test_get_approval_tasks_success(self, mock_tasks):
        mock_tasks.return_value = {
            "recordsTotal": 2,
            "recordsFiltered": 1,
            "results": [
                {"id": 1, "abspath": "/media/v.mp4", "status": "awaiting_approval"},
            ],
        }
        resp = self.post_json(
            "/approval/tasks",
            {
                "start": 0,
                "length": 10,
            },
        )
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["recordsTotal"] == 2
        mock_tasks.assert_called_once()
        params = mock_tasks.call_args.kwargs["params"]
        assert params["codec"] == ""
        assert params["quality_min"] == 0

    @patch(APPROVAL_HELPERS + ".prepare_filtered_approval_tasks")
    def test_get_approval_tasks_error(self, mock_tasks):
        mock_tasks.side_effect = Exception("DB error")
        resp = self.post_json("/approval/tasks", {"start": 0, "length": 10})
        assert resp.code == 500

    def test_get_approval_tasks_invalid_json(self):
        resp = self.fetch(
            "/compresso/api/v2/approval/tasks",
            method="POST",
            body="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.code == 400

    def test_get_approval_tasks_invalid_order_by(self):
        resp = self.post_json("/approval/tasks", {"start": 0, "length": 10, "order_by": "not_a_column"})
        assert resp.code == 400

    @patch(APPROVAL_HELPERS + ".prepare_filtered_approval_tasks")
    def test_get_approval_tasks_passes_filters(self, mock_tasks):
        mock_tasks.return_value = {"recordsTotal": 2, "recordsFiltered": 1, "results": []}
        resp = self.post_json(
            "/approval/tasks",
            {
                "start": 0,
                "length": 10,
                "codec": "hevc",
                "quality_min": 90,
            },
        )
        assert resp.code == 200
        params = mock_tasks.call_args.kwargs["params"]
        assert params["codec"] == "hevc"
        assert params["quality_min"] == 90


# ------------------------------------------------------------------
# Get approval summary
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiApprovalHandler, "initialize", _mock_initialize)
class TestApprovalApiSummary(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + ".prepare_approval_summary")
    def test_get_summary_success(self, mock_summary):
        mock_summary.return_value = {
            "total_count": 2,
            "total_source_size": 3000,
            "total_staged_size": 1800,
            "total_space_saved": 1200,
            "average_savings_percent": 40,
            "largest_savings_file": "/media/v.mp4",
            "largest_savings_bytes": 1200,
            "average_vmaf": 92.5,
            "codec_options": ["h264", "hevc"],
        }
        resp = self.post_json("/approval/summary", {"codec": "hevc", "quality_min": 80})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["total_count"] == 2
        assert data["codec_options"] == ["h264", "hevc"]
        params = mock_summary.call_args.kwargs["params"]
        assert params["codec"] == "hevc"
        assert params["quality_min"] == 80

    @patch(APPROVAL_HELPERS + ".prepare_approval_summary")
    def test_get_summary_error(self, mock_summary):
        mock_summary.side_effect = Exception("DB error")
        resp = self.post_json("/approval/summary", {})
        assert resp.code == 500

    def test_get_summary_invalid_quality_min(self):
        resp = self.post_json("/approval/summary", {"quality_min": 101})
        assert resp.code == 400


# ------------------------------------------------------------------
# Approve tasks
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiApprovalHandler, "initialize", _mock_initialize)
class TestApprovalApiApprove(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + ".approve_tasks")
    def test_approve_tasks_success(self, mock_approve):
        resp = self.post_json("/approval/approve", {"id_list": [1, 2]})
        assert resp.code == 200
        mock_approve.assert_called_once_with([1, 2])

    @patch(APPROVAL_HELPERS + ".approve_tasks")
    def test_approve_tasks_error(self, mock_approve):
        mock_approve.side_effect = Exception("error")
        resp = self.post_json("/approval/approve", {"id_list": [1]})
        assert resp.code == 500

    @patch(APPROVAL_HELPERS + ".approve_tasks")
    @patch(APPROVAL_HELPERS + ".get_all_matching_task_ids", return_value=[1, 3])
    def test_approve_all_matching_passes_filters(self, mock_matching, _mock_approve):
        resp = self.post_json(
            "/approval/approve",
            {
                "all_matching": True,
                "search_value": "movie",
                "library_ids": [2],
                "codec": "hevc",
                "quality_min": 90,
            },
        )
        assert resp.code == 200
        mock_matching.assert_called_once_with(
            search_value="movie",
            library_ids=[2],
            codec="hevc",
            quality_min=90,
        )


# ------------------------------------------------------------------
# Reject tasks
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiApprovalHandler, "initialize", _mock_initialize)
class TestApprovalApiReject(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + ".reject_tasks")
    def test_reject_tasks_success(self, mock_reject):
        resp = self.post_json("/approval/reject", {"id_list": [1]})
        assert resp.code == 200
        mock_reject.assert_called_once_with(task_ids=[1], requeue=False)

    @patch(APPROVAL_HELPERS + ".reject_tasks")
    def test_reject_tasks_with_requeue(self, mock_reject):
        resp = self.post_json("/approval/reject", {"id_list": [1], "requeue": True})
        assert resp.code == 200
        mock_reject.assert_called_once_with(task_ids=[1], requeue=True)

    @patch(APPROVAL_HELPERS + ".reject_tasks")
    def test_reject_tasks_error(self, mock_reject):
        mock_reject.side_effect = Exception("error")
        resp = self.post_json("/approval/reject", {"id_list": [1]})
        assert resp.code == 500

    @patch(APPROVAL_HELPERS + ".reject_tasks")
    @patch(APPROVAL_HELPERS + ".get_all_matching_task_ids", return_value=[2])
    def test_reject_all_matching_passes_filters(self, mock_matching, _mock_reject):
        resp = self.post_json(
            "/approval/reject",
            {
                "all_matching": True,
                "search_value": "movie",
                "library_ids": [2],
                "codec": "h264",
                "quality_min": 75,
            },
        )
        assert resp.code == 200
        mock_matching.assert_called_once_with(
            search_value="movie",
            library_ids=[2],
            codec="h264",
            quality_min=75,
        )


# ------------------------------------------------------------------
# Get task detail
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiApprovalHandler, "initialize", _mock_initialize)
class TestApprovalApiDetail(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + ".get_approval_task_detail")
    def test_get_detail_success(self, mock_detail):
        mock_detail.return_value = {
            "id": 1,
            "abspath": "/media/v.mp4",
            "source_size": 1000,
            "staged_size": 500,
            "staged_path": "/cache/v.mp4",
            "size_delta": -500,
            "size_ratio": 0.5,
            "cache_path": "/cache",
            "start_time": "2024-01-01",
            "finish_time": "2024-01-01",
            "log": "",
            "library_id": 1,
        }
        resp = self.post_json("/approval/detail", {"id": 1})
        assert resp.code == 200

    @patch(APPROVAL_HELPERS + ".get_approval_task_detail", return_value=None)
    def test_get_detail_not_found(self, _mock_detail):
        resp = self.post_json("/approval/detail", {"id": 999})
        assert resp.code == 400

    @patch(APPROVAL_HELPERS + ".get_approval_task_detail")
    def test_get_detail_error(self, mock_detail):
        mock_detail.side_effect = Exception("error")
        resp = self.post_json("/approval/detail", {"id": 1})
        assert resp.code == 500


# ------------------------------------------------------------------
# Get approval count
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiApprovalHandler, "initialize", _mock_initialize)
class TestApprovalApiCount(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch(APPROVAL_HELPERS + ".get_approval_count", return_value=5)
    def test_get_count_success(self, _mock_count):
        resp = self.get_json("/approval/count")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["count"] == 5

    @patch(APPROVAL_HELPERS + ".get_approval_count")
    def test_get_count_error(self, mock_count):
        mock_count.side_effect = Exception("error")
        resp = self.get_json("/approval/count")
        assert resp.code == 500
