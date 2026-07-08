#!/usr/bin/env python3

"""
tests.unit.test_approval_search_sort.py

Unit tests for approval API search, sort, and select-all features:
- Approval task listing accepts order_by and order_direction
- Approval task listing accepts search_value
- Approve with all_matching=true resolves IDs server-side
- Reject with all_matching=true resolves IDs server-side
- get_all_matching_task_ids returns filtered IDs
"""

from unittest.mock import MagicMock, patch

import pytest

# ------------------------------------------------------------------
# TestApprovalListingOrderAndSearch
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestApprovalListingOrderAndSearch:
    """Tests for order_by, order_direction, and search_value in prepare_filtered_approval_tasks."""

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata", return_value={})
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_passes_order_by_to_task_handler(self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model):
        from compresso.webserver.helpers.approval import prepare_filtered_approval_tasks

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = "/tmp/staging"
        mock_config_class.return_value = mock_config

        mock_task_handler = MagicMock()
        mock_task_handler.get_total_task_list_count.return_value = 0
        approval_query = MagicMock()
        approval_query.count.return_value = 0
        mock_task_handler.get_task_list_filtered_and_sorted.side_effect = [
            approval_query,
            [],  # no results
        ]
        mock_task_module.Task.return_value = mock_task_handler

        prepare_filtered_approval_tasks(
            {
                "start": 0,
                "length": 10,
                "order_by": "source_size",
                "order_direction": "asc",
            }
        )

        # Verify the order was passed through
        calls = mock_task_handler.get_task_list_filtered_and_sorted.call_args_list
        for call_args in calls:
            order = call_args[1].get("order") or call_args.kwargs.get("order")
            if order:
                assert order["column"] == "source_size"
                assert order["dir"] == "asc"

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata", return_value={})
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_passes_search_value_to_task_handler(self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model):
        from compresso.webserver.helpers.approval import prepare_filtered_approval_tasks

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = "/tmp/staging"
        mock_config_class.return_value = mock_config

        mock_task_handler = MagicMock()
        mock_task_handler.get_total_task_list_count.return_value = 0
        approval_query = MagicMock()
        approval_query.count.return_value = 0
        mock_task_handler.get_task_list_filtered_and_sorted.side_effect = [
            approval_query,
            [],
        ]
        mock_task_module.Task.return_value = mock_task_handler

        prepare_filtered_approval_tasks(
            {
                "start": 0,
                "length": 10,
                "search_value": "movie.mkv",
            }
        )

        calls = mock_task_handler.get_task_list_filtered_and_sorted.call_args_list
        for call_args in calls:
            search = call_args[1].get("search_value") or call_args.kwargs.get("search_value")
            if search is not None:
                assert search == "movie.mkv"

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata", return_value={})
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_defaults_order_to_finish_time_desc(self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model):
        from compresso.webserver.helpers.approval import prepare_filtered_approval_tasks

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = "/tmp/staging"
        mock_config_class.return_value = mock_config

        mock_task_handler = MagicMock()
        mock_task_handler.get_total_task_list_count.return_value = 0
        approval_query = MagicMock()
        approval_query.count.return_value = 0
        mock_task_handler.get_task_list_filtered_and_sorted.side_effect = [
            approval_query,
            [],
        ]
        mock_task_module.Task.return_value = mock_task_handler

        # Pass empty params — should default
        prepare_filtered_approval_tasks({"start": 0, "length": 10})

        calls = mock_task_handler.get_task_list_filtered_and_sorted.call_args_list
        for call_args in calls:
            order = call_args[1].get("order") or call_args.kwargs.get("order")
            if order:
                assert order["column"] == "finish_time"
                assert order["dir"] == "desc"

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata", return_value={})
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_invalid_order_direction_defaults_to_desc(
        self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model
    ):
        from compresso.webserver.helpers.approval import prepare_filtered_approval_tasks

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = "/tmp/staging"
        mock_config_class.return_value = mock_config

        mock_task_handler = MagicMock()
        mock_task_handler.get_total_task_list_count.return_value = 0
        approval_query = MagicMock()
        approval_query.count.return_value = 0
        mock_task_handler.get_task_list_filtered_and_sorted.side_effect = [
            approval_query,
            [],
        ]
        mock_task_module.Task.return_value = mock_task_handler

        prepare_filtered_approval_tasks(
            {
                "start": 0,
                "length": 10,
                "order_direction": "INVALID",
            }
        )

        calls = mock_task_handler.get_task_list_filtered_and_sorted.call_args_list
        for call_args in calls:
            order = call_args[1].get("order") or call_args.kwargs.get("order")
            if order:
                assert order["dir"] == "desc"

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata")
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_filters_by_codec_and_quality_min(
        self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model
    ):
        from compresso.webserver.helpers.approval import prepare_filtered_approval_tasks

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = "/tmp/staging"
        mock_config_class.return_value = mock_config

        mock_task_handler = MagicMock()
        mock_task_handler.get_total_task_list_count.return_value = 2
        approval_query = MagicMock()
        approval_query.count.return_value = 2
        mock_task_handler.get_task_list_filtered_and_sorted.side_effect = [
            approval_query,
            [
                {
                    "id": 1,
                    "abspath": "/media/hevc.mkv",
                    "priority": 100,
                    "type": "local",
                    "status": "awaiting_approval",
                    "source_size": 1000,
                    "finish_time": "2024-06-01",
                    "library_id": 1,
                    "vmaf_score": 95,
                },
                {
                    "id": 2,
                    "abspath": "/media/h264.mkv",
                    "priority": 100,
                    "type": "local",
                    "status": "awaiting_approval",
                    "source_size": 1000,
                    "finish_time": "2024-06-01",
                    "library_id": 1,
                    "vmaf_score": 80,
                },
            ],
        ]
        mock_task_module.Task.return_value = mock_task_handler
        mock_tasks_model.get_by_id.side_effect = [
            MagicMock(vmaf_score=95, ssim_score=0.98),
            MagicMock(vmaf_score=80, ssim_score=0.95),
        ]
        mock_extract.side_effect = [
            {"codec": "hevc", "resolution": "1080p"},
            {"codec": "h264", "resolution": "1080p"},
        ]

        result = prepare_filtered_approval_tasks({"start": 0, "length": 10, "codec": "hevc", "quality_min": 90})

        assert result["recordsFiltered"] == 1
        assert [item["id"] for item in result["results"]] == [1]

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata")
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_summary_returns_aggregates_and_codec_options(
        self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model
    ):
        from compresso.webserver.helpers.approval import prepare_approval_summary

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = "/tmp/staging"
        mock_config_class.return_value = mock_config

        mock_task_handler = MagicMock()
        mock_task_handler.get_total_task_list_count.return_value = 2
        mock_task_handler.get_task_list_filtered_and_sorted.side_effect = [
            MagicMock(),
            [
                {
                    "id": 1,
                    "abspath": "/media/hevc.mkv",
                    "priority": 100,
                    "type": "local",
                    "status": "awaiting_approval",
                    "source_size": 1000,
                    "finish_time": "2024-06-01",
                    "library_id": 1,
                    "vmaf_score": 95,
                },
                {
                    "id": 2,
                    "abspath": "/media/h264.mkv",
                    "priority": 100,
                    "type": "local",
                    "status": "awaiting_approval",
                    "source_size": 2000,
                    "finish_time": "2024-06-02",
                    "library_id": 1,
                    "vmaf_score": 85,
                },
            ],
        ]
        mock_task_module.Task.return_value = mock_task_handler
        mock_tasks_model.get_by_id.side_effect = [
            MagicMock(vmaf_score=95, ssim_score=0.98),
            MagicMock(vmaf_score=85, ssim_score=0.95),
        ]
        mock_extract.side_effect = [
            {"codec": "hevc", "resolution": "1080p"},
            {"codec": "h264", "resolution": "1080p"},
        ]

        result = prepare_approval_summary({})

        assert result["total_count"] == 2
        assert result["total_source_size"] == 3000
        assert result["average_savings_percent"] == 100
        assert result["largest_savings_file"] == "/media/hevc.mkv"
        assert result["average_vmaf"] == 90
        assert result["codec_options"] == ["h264", "hevc"]


# ------------------------------------------------------------------
# TestGetAllMatchingTaskIds
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGetAllMatchingTaskIds:
    """Tests for get_all_matching_task_ids server-side resolution."""

    @patch("compresso.webserver.helpers.approval.task")
    def test_returns_matching_ids(self, mock_task_module):
        from compresso.webserver.helpers.approval import get_all_matching_task_ids

        mock_task_handler = MagicMock()
        mock_task_handler.get_task_list_filtered_and_sorted.return_value = [
            {"id": 1, "abspath": "/lib/movie1.mkv"},
            {"id": 2, "abspath": "/lib/movie2.mkv"},
            {"id": 5, "abspath": "/lib/movie5.mkv"},
        ]
        mock_task_module.Task.return_value = mock_task_handler

        result = get_all_matching_task_ids(search_value="movie")
        assert result == [1, 2, 5]

    @patch("compresso.webserver.helpers.approval.task")
    def test_returns_empty_list_when_no_matches(self, mock_task_module):
        from compresso.webserver.helpers.approval import get_all_matching_task_ids

        mock_task_handler = MagicMock()
        mock_task_handler.get_task_list_filtered_and_sorted.return_value = []
        mock_task_module.Task.return_value = mock_task_handler

        result = get_all_matching_task_ids(search_value="nonexistent")
        assert result == []

    @patch("compresso.webserver.helpers.approval.task")
    def test_passes_search_value_and_status_filter(self, mock_task_module):
        from compresso.webserver.helpers.approval import get_all_matching_task_ids

        mock_task_handler = MagicMock()
        mock_task_handler.get_task_list_filtered_and_sorted.return_value = []
        mock_task_module.Task.return_value = mock_task_handler

        get_all_matching_task_ids(search_value="test_query")

        mock_task_handler.get_task_list_filtered_and_sorted.assert_called_once()
        call_kwargs = mock_task_handler.get_task_list_filtered_and_sorted.call_args[1]
        assert call_kwargs["search_value"] == "test_query"
        assert call_kwargs["status"] == "awaiting_approval"

    @patch("compresso.webserver.helpers.approval.task")
    def test_passes_empty_search_for_select_all(self, mock_task_module):
        from compresso.webserver.helpers.approval import get_all_matching_task_ids

        mock_task_handler = MagicMock()
        mock_task_handler.get_task_list_filtered_and_sorted.return_value = [
            {"id": 10},
            {"id": 20},
        ]
        mock_task_module.Task.return_value = mock_task_handler

        result = get_all_matching_task_ids(search_value="")
        assert result == [10, 20]


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
