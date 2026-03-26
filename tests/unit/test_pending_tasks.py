#!/usr/bin/env python3

"""
    tests.unit.test_pending_tasks.py

    Unit tests for compresso.webserver.helpers.pending_tasks.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unittest
class TestPrepareFilteredPendingTasksForTable:

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_returns_correct_structure(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_task_instance.get_total_task_list_count.return_value = 0
        mock_query = MagicMock()
        mock_query.count.return_value = 0
        mock_query.__iter__ = MagicMock(return_value=iter([]))
        mock_task_instance.get_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.pending_tasks import prepare_filtered_pending_tasks_for_table
        result = prepare_filtered_pending_tasks_for_table({
            'draw': 1, 'start': 0, 'length': 10,
            'search': {'value': ''},
        })

        assert 'draw' in result
        assert 'recordsTotal' in result
        assert 'recordsFiltered' in result
        assert 'data' in result
        assert result['data'] == []

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_maps_task_fields_correctly(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_task_instance.get_total_task_list_count.return_value = 1

        task_row = {'id': 1, 'abspath': '/media/file.mkv', 'status': 'pending', 'priority': 100}
        mock_count_query = MagicMock()
        mock_count_query.count.return_value = 1
        mock_results_query = MagicMock()
        mock_results_query.__iter__ = MagicMock(return_value=iter([task_row]))

        mock_task_instance.get_task_list_filtered_and_sorted.side_effect = [mock_count_query, mock_results_query]

        from compresso.webserver.helpers.pending_tasks import prepare_filtered_pending_tasks_for_table
        result = prepare_filtered_pending_tasks_for_table({
            'draw': 1, 'start': 0, 'length': 10,
            'search': {'value': ''},
        })

        assert len(result['data']) == 1
        item = result['data'][0]
        assert item['id'] == 1
        assert item['abspath'] == '/media/file.mkv'
        assert item['status'] == 'pending'


@pytest.mark.unittest
class TestGetFilteredPendingTaskIds:

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_returns_list_of_ids(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_query = MagicMock()
        mock_query.__iter__ = MagicMock(return_value=iter([
            {'id': 1}, {'id': 2}, {'id': 3},
        ]))
        mock_task_instance.get_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.pending_tasks import get_filtered_pending_task_ids
        result = get_filtered_pending_task_ids({})
        assert result == [1, 2, 3]

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_excludes_specified_ids(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_query = MagicMock()
        mock_query.__iter__ = MagicMock(return_value=iter([
            {'id': 1}, {'id': 2}, {'id': 3},
        ]))
        mock_task_instance.get_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.pending_tasks import get_filtered_pending_task_ids
        result = get_filtered_pending_task_ids({}, exclude_ids=[2])
        assert result == [1, 3]

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_skips_records_with_none_id(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_query = MagicMock()
        mock_query.__iter__ = MagicMock(return_value=iter([
            {'id': 1}, {'id': None}, {'id': 3},
        ]))
        mock_task_instance.get_task_list_filtered_and_sorted.return_value = mock_query

        from compresso.webserver.helpers.pending_tasks import get_filtered_pending_task_ids
        result = get_filtered_pending_task_ids({})
        assert result == [1, 3]


@pytest.mark.unittest
class TestRemovePendingTasks:

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_delegates_to_task_handler(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance

        from compresso.webserver.helpers.pending_tasks import remove_pending_tasks
        remove_pending_tasks([1, 2, 3])
        mock_task_instance.delete_tasks_recursively.assert_called_once_with(id_list=[1, 2, 3])


@pytest.mark.unittest
class TestReorderPendingTasks:

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_delegates_to_task_handler_top(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance

        from compresso.webserver.helpers.pending_tasks import reorder_pending_tasks
        reorder_pending_tasks([1, 2], 'top')
        mock_task_instance.reorder_tasks.assert_called_once_with([1, 2], 'top')

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_delegates_to_task_handler_bottom(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance

        from compresso.webserver.helpers.pending_tasks import reorder_pending_tasks
        reorder_pending_tasks([1, 2], 'bottom')
        mock_task_instance.reorder_tasks.assert_called_once_with([1, 2], 'bottom')


@pytest.mark.unittest
class TestAddRemoteTasks:

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_returns_task_data_on_success(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_task_instance.create_task_by_absolute_path.return_value = True
        mock_task_instance.get_task_data.return_value = {'id': 1, 'abspath': '/upload/file.mkv'}

        from compresso.webserver.helpers.pending_tasks import add_remote_tasks
        result = add_remote_tasks('/upload/file.mkv')
        assert result == {'id': 1, 'abspath': '/upload/file.mkv'}

    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_returns_false_on_failure(self, mock_task_module):
        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_task_instance.create_task_by_absolute_path.return_value = False

        from compresso.webserver.helpers.pending_tasks import add_remote_tasks
        result = add_remote_tasks('/upload/bad.mkv')
        assert result is False


@pytest.mark.unittest
class TestCreateTask:

    @patch('compresso.webserver.helpers.pending_tasks.Library')
    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_creates_task_with_library_id(self, mock_task_module, mock_library_cls):
        mock_lib = MagicMock()
        mock_lib.get_id.return_value = 1
        mock_library_cls.return_value = mock_lib

        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_task_instance.create_task_by_absolute_path.return_value = True
        mock_task_instance.get_task_data.return_value = {
            'id': 10, 'abspath': '/media/file.mkv', 'priority': 0,
            'type': 'local', 'status': 'pending', 'library_id': 1,
        }

        from compresso.webserver.helpers.pending_tasks import create_task
        result = create_task('/media/file.mkv', library_id=1)
        assert result['id'] == 10
        assert result['library_id'] == 1

    @patch('compresso.webserver.helpers.pending_tasks.Library')
    @patch('compresso.webserver.helpers.pending_tasks.task')
    def test_returns_false_when_task_creation_fails(self, mock_task_module, mock_library_cls):
        mock_lib = MagicMock()
        mock_lib.get_id.return_value = 1
        mock_library_cls.return_value = mock_lib

        mock_task_instance = MagicMock()
        mock_task_module.Task.return_value = mock_task_instance
        mock_task_instance.create_task_by_absolute_path.return_value = False

        from compresso.webserver.helpers.pending_tasks import create_task
        result = create_task('/media/file.mkv', library_id=1)
        assert result is False
