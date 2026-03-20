#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_helpers_approval.py

    Tests for the approval helper functions.

"""

import pytest
from unittest.mock import patch, MagicMock

APPROVAL_MODULE = 'compresso.webserver.helpers.approval'


@pytest.mark.unittest
class TestApproveTasksHelper:

    @patch(APPROVAL_MODULE + '.task')
    def test_approve_tasks_calls_set_status(self, mock_task_module):
        from compresso.webserver.helpers.approval import approve_tasks
        mock_task_module.Task.set_tasks_status.return_value = 2
        result = approve_tasks([1, 2])
        mock_task_module.Task.set_tasks_status.assert_called_once_with([1, 2], 'approved')
        assert result == 2


@pytest.mark.unittest
class TestRejectTasksHelper:

    @patch(APPROVAL_MODULE + '.shutil')
    @patch(APPROVAL_MODULE + '.os')
    @patch(APPROVAL_MODULE + '.Tasks')
    @patch(APPROVAL_MODULE + '.config')
    @patch(APPROVAL_MODULE + '.task')
    def test_reject_tasks_with_requeue(self, mock_task_module, mock_config, mock_tasks_model,
                                       mock_os, mock_shutil):
        from compresso.webserver.helpers.approval import reject_tasks
        mock_settings = MagicMock()
        mock_settings.get_staging_path.return_value = '/tmp/staging'
        mock_config.Config.return_value = mock_settings
        mock_os.path.exists.return_value = False

        mock_task_record = MagicMock()
        mock_task_record.cache_path = ''
        mock_tasks_model.get_by_id.return_value = mock_task_record

        mock_task_module.Task.set_tasks_status.return_value = True
        result = reject_tasks([1], requeue=True)
        mock_task_module.Task.set_tasks_status.assert_called_once_with([1], 'pending')
        assert result is True

    @patch(APPROVAL_MODULE + '.shutil')
    @patch(APPROVAL_MODULE + '.os')
    @patch(APPROVAL_MODULE + '.Tasks')
    @patch(APPROVAL_MODULE + '.config')
    @patch(APPROVAL_MODULE + '.task')
    def test_reject_tasks_without_requeue_deletes(self, mock_task_module, mock_config,
                                                   mock_tasks_model, mock_os, mock_shutil):
        from compresso.webserver.helpers.approval import reject_tasks
        mock_settings = MagicMock()
        mock_settings.get_staging_path.return_value = '/tmp/staging'
        mock_config.Config.return_value = mock_settings
        mock_os.path.exists.return_value = False

        mock_task_record = MagicMock()
        mock_task_record.cache_path = ''
        mock_tasks_model.get_by_id.return_value = mock_task_record

        mock_task_handler = MagicMock()
        mock_task_handler.delete_tasks_recursively.return_value = True
        mock_task_module.Task.return_value = mock_task_handler

        result = reject_tasks([1], requeue=False)
        mock_task_handler.delete_tasks_recursively.assert_called_once_with([1])
        assert result is True

    @patch(APPROVAL_MODULE + '.shutil')
    @patch(APPROVAL_MODULE + '.os')
    @patch(APPROVAL_MODULE + '.Tasks')
    @patch(APPROVAL_MODULE + '.config')
    @patch(APPROVAL_MODULE + '.task')
    def test_reject_tasks_cleans_staging_dir(self, mock_task_module, mock_config,
                                             mock_tasks_model, mock_os, mock_shutil):
        from compresso.webserver.helpers.approval import reject_tasks
        mock_settings = MagicMock()
        mock_settings.get_staging_path.return_value = '/tmp/staging'
        mock_config.Config.return_value = mock_settings

        # os.path.exists returns True for staging dir, False for cache dir check
        mock_os.path.exists.side_effect = lambda p: 'task_5' in p
        mock_os.path.join = lambda *args: '/'.join(args)
        mock_os.path.dirname = lambda p: '/'.join(p.split('/')[:-1])

        mock_task_record = MagicMock()
        mock_task_record.cache_path = ''
        mock_tasks_model.get_by_id.return_value = mock_task_record

        mock_task_handler = MagicMock()
        mock_task_handler.delete_tasks_recursively.return_value = True
        mock_task_module.Task.return_value = mock_task_handler

        reject_tasks([5], requeue=False)
        mock_shutil.rmtree.assert_called_once_with('/tmp/staging/task_5')


@pytest.mark.unittest
class TestGetApprovalCountHelper:

    @patch(APPROVAL_MODULE + '.Tasks')
    def test_get_approval_count(self, mock_tasks_model):
        from compresso.webserver.helpers.approval import get_approval_count
        mock_query = MagicMock()
        mock_query.count.return_value = 7
        mock_tasks_model.select.return_value.where.return_value.limit.return_value = mock_query
        result = get_approval_count()
        assert result == 7


@pytest.mark.unittest
class TestPrepareFilteredApprovalTasks:

    @patch(APPROVAL_MODULE + '.extract_media_metadata', return_value={})
    @patch(APPROVAL_MODULE + '.config')
    @patch(APPROVAL_MODULE + '.task')
    def test_returns_empty_results(self, mock_task_module, mock_config, _mock_meta):
        from compresso.webserver.helpers.approval import prepare_filtered_approval_tasks
        mock_settings = MagicMock()
        mock_settings.get_staging_path.return_value = '/tmp/staging'
        mock_config.Config.return_value = mock_settings

        mock_handler = MagicMock()
        mock_handler.get_total_task_list_count.return_value = 0
        mock_filtered = MagicMock()
        mock_filtered.count.return_value = 0
        mock_filtered.__iter__ = MagicMock(return_value=iter([]))
        mock_handler.get_task_list_filtered_and_sorted.return_value = mock_filtered
        mock_task_module.Task.return_value = mock_handler

        result = prepare_filtered_approval_tasks({'start': 0, 'length': 10})
        assert result['recordsTotal'] == 0
        assert result['recordsFiltered'] == 0
        assert result['results'] == []
