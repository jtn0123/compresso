#!/usr/bin/env python3

"""
tests.unit.test_completed_tasks.py

Unit tests for compresso.webserver.helpers.completed_tasks.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unittest
class TestParseDatetimeToTimestamp:
    def _call(self, value):
        from compresso.webserver.helpers.completed_tasks import _parse_datetime_to_timestamp

        return _parse_datetime_to_timestamp(value)

    def test_none_returns_none(self):
        assert self._call(None) is None

    def test_datetime_object_returns_timestamp(self):
        dt = datetime(2023, 1, 15, 10, 30, 0)
        result = self._call(dt)
        assert result == dt.timestamp()

    def test_string_iso_format_parses(self):
        result = self._call("2023-01-15T10:30:00")
        expected = datetime(2023, 1, 15, 10, 30, 0).timestamp()
        assert result == expected

    def test_string_short_format_parses(self):
        result = self._call("2023-01-15 10:30")
        expected = datetime(2023, 1, 15, 10, 30).timestamp()
        assert result == expected

    def test_invalid_string_returns_none(self):
        assert self._call("not-a-date") is None

    def test_empty_string_returns_none(self):
        assert self._call("") is None

    def test_integer_returns_none(self):
        assert self._call(12345) is None


@pytest.mark.unittest
class TestPrepareFilteredCompletedTasks:
    @patch("compresso.webserver.helpers.completed_tasks.FileMetadataPaths")
    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_returns_correct_structure(self, mock_history_module, mock_fmp):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_hist.get_total_historic_task_list_count.return_value = 0

        mock_query = MagicMock()
        mock_query.count.return_value = 0
        mock_query.__iter__ = MagicMock(return_value=iter([]))
        mock_hist.get_historic_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.completed_tasks import prepare_filtered_completed_tasks

        result = prepare_filtered_completed_tasks({})

        assert "recordsTotal" in result
        assert "recordsFiltered" in result
        assert "successCount" in result
        assert "failedCount" in result
        assert "results" in result

    @patch("compresso.webserver.helpers.completed_tasks.FileMetadataPaths")
    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_status_success_passes_true(self, mock_history_module, mock_fmp):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_hist.get_total_historic_task_list_count.return_value = 0

        mock_query = MagicMock()
        mock_query.count.return_value = 0
        mock_query.__iter__ = MagicMock(return_value=iter([]))
        mock_hist.get_historic_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.completed_tasks import prepare_filtered_completed_tasks

        prepare_filtered_completed_tasks({"status": "success"})

        # Verify task_success=True was passed in at least one call
        calls = mock_hist.get_historic_task_list_filtered_and_sorted.call_args_list
        assert any(c.kwargs.get("task_success") is True for c in calls)

    @patch("compresso.webserver.helpers.completed_tasks.FileMetadataPaths")
    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_status_failed_passes_false(self, mock_history_module, mock_fmp):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_hist.get_total_historic_task_list_count.return_value = 0

        mock_query = MagicMock()
        mock_query.count.return_value = 0
        mock_query.__iter__ = MagicMock(return_value=iter([]))
        mock_hist.get_historic_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.completed_tasks import prepare_filtered_completed_tasks

        prepare_filtered_completed_tasks({"status": "failed"})

        calls = mock_hist.get_historic_task_list_filtered_and_sorted.call_args_list
        assert any(c.kwargs.get("task_success") is False for c in calls)


@pytest.mark.unittest
class TestGetFilteredCompletedTaskIds:
    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_returns_list_of_ids(self, mock_history_module):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_query = MagicMock()
        mock_query.__iter__ = MagicMock(
            return_value=iter(
                [
                    {"id": 10},
                    {"id": 20},
                    {"id": 30},
                ]
            )
        )
        mock_hist.get_historic_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.completed_tasks import get_filtered_completed_task_ids

        result = get_filtered_completed_task_ids({})
        assert result == [10, 20, 30]

    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_excludes_specified_ids(self, mock_history_module):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_query = MagicMock()
        mock_query.__iter__ = MagicMock(
            return_value=iter(
                [
                    {"id": 10},
                    {"id": 20},
                    {"id": 30},
                ]
            )
        )
        mock_hist.get_historic_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.completed_tasks import get_filtered_completed_task_ids

        result = get_filtered_completed_task_ids({}, exclude_ids=[20])
        assert result == [10, 30]

    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_skips_records_with_none_id(self, mock_history_module):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_query = MagicMock()
        mock_query.__iter__ = MagicMock(
            return_value=iter(
                [
                    {"id": 10},
                    {"id": None},
                    {"id": 30},
                ]
            )
        )
        mock_hist.get_historic_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.completed_tasks import get_filtered_completed_task_ids

        result = get_filtered_completed_task_ids({})
        assert result == [10, 30]


@pytest.mark.unittest
class TestRemoveCompletedTasks:
    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_delegates_to_history_handler(self, mock_history_module):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist

        from compresso.webserver.helpers.completed_tasks import remove_completed_tasks

        remove_completed_tasks([1, 2, 3])
        mock_hist.delete_historic_tasks_recursively.assert_called_once_with(id_list=[1, 2, 3])


@pytest.mark.unittest
class TestAddHistoricTasksToPendingList:
    @patch("compresso.webserver.helpers.completed_tasks.task")
    @patch("compresso.webserver.helpers.completed_tasks.os.path.exists", return_value=True)
    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_returns_empty_errors_on_success(self, mock_history_module, mock_exists, mock_task_module):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_hist.get_current_path_of_historic_tasks_by_id.return_value = [
            {"id": 1, "abspath": "/media/file.mkv"},
        ]

        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_task_instance.create_task_by_absolute_path.return_value = True

        from compresso.webserver.helpers.completed_tasks import add_historic_tasks_to_pending_tasks_list

        errors = add_historic_tasks_to_pending_tasks_list([1])
        assert errors == {}

    @patch("compresso.webserver.helpers.completed_tasks.os.path.exists", return_value=False)
    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_returns_error_when_path_not_exists(self, mock_history_module, mock_exists):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_hist.get_current_path_of_historic_tasks_by_id.return_value = [
            {"id": 1, "abspath": "/media/missing.mkv"},
        ]

        from compresso.webserver.helpers.completed_tasks import add_historic_tasks_to_pending_tasks_list

        errors = add_historic_tasks_to_pending_tasks_list([1])
        assert 1 in errors
        assert "does not exist" in errors[1]

    @patch("compresso.webserver.helpers.completed_tasks.task")
    @patch("compresso.webserver.helpers.completed_tasks.os.path.exists", return_value=True)
    @patch("compresso.webserver.helpers.completed_tasks.history")
    def test_returns_error_when_task_already_queued(self, mock_history_module, mock_exists, mock_task_module):
        mock_hist = MagicMock()
        mock_history_module.History.return_value = mock_hist
        mock_hist.get_current_path_of_historic_tasks_by_id.return_value = [
            {"id": 1, "abspath": "/media/file.mkv"},
        ]

        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_task_instance.create_task_by_absolute_path.return_value = False

        from compresso.webserver.helpers.completed_tasks import add_historic_tasks_to_pending_tasks_list

        errors = add_historic_tasks_to_pending_tasks_list([1])
        assert 1 in errors
        assert "already in task queue" in errors[1]


@pytest.mark.unittest
class TestFormatFfmpegLogText:
    def _call(self, lines):
        from compresso.webserver.helpers.completed_tasks import format_ffmpeg_log_text

        return format_ffmpeg_log_text(lines)

    def test_empty_list_returns_empty(self):
        assert self._call([]) == []

    def test_runner_header_prepends_hr(self):
        result = self._call(["RUNNER:"])
        assert "<hr>" in result
        assert "<b>RUNNER:</b>" in result

    def test_command_header_bolded(self):
        result = self._call(["COMMAND:"])
        assert "<b>COMMAND:</b>" in result

    def test_terminated_header_has_terminated_class(self):
        result = self._call(["WORKER TERMINATED!"])
        assert 'class="terminated"' in result[0]

    def test_leading_whitespace_converted_to_nbsp(self):
        result = self._call(["   some text"])
        assert "&nbsp;&nbsp;&nbsp;" in result[0]

    def test_lines_after_command_get_pre_tags(self):
        result = self._call(["COMMAND:", "ffmpeg -i input.mkv output.mp4"])
        # The second line should have <pre> wrapping
        assert "<pre>" in result[1]
