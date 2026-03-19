#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_taskqueue.py

    Unit tests for compresso/libs/taskqueue.py:
    - build_tasks_count_query
    - build_tasks_query_full_task_list
    - TaskQueue list/mark/empty methods

"""

import os
import shutil
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels import Libraries, Tags
from compresso.libs.unmodels.tasks import Tasks

LibraryTags = Libraries.tags.get_through_model()


class TestTaskQueue:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_taskqueue_')
        self.db_file = os.path.join(self.config_path, 'test_taskqueue.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([Tasks, Libraries, LibraryTags, Tags])
        self.db_connection.execute_sql('SELECT 1')
        self.default_library = Libraries.create(
            name='default',
            path='/media/library',
            locked=False,
            enable_remote_only=False,
            enable_scanner=False,
            enable_inotify=False,
            priority_score=0,
        )

    def teardown_class(self):
        if self.db_connection:
            self.db_connection.close()
        if os.path.exists(self.config_path):
            shutil.rmtree(self.config_path, ignore_errors=True)

    def setup_method(self):
        Tasks.delete().execute()

    def _create_task(self, abspath, status='pending', library_id=None):
        if library_id is None:
            library_id = self.default_library.id
        return Tasks.create(
            abspath=abspath,
            status=status,
            library_id=library_id,
            priority=100,
            type='local',
        )

    @pytest.mark.unittest
    def test_list_pending_tasks_empty(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            tq = TaskQueue(data_queues={})
            result = tq.list_pending_tasks()
            assert result == []

    @pytest.mark.unittest
    def test_list_pending_tasks_returns_pending_only(self):
        self._create_task('/media/file1.mkv', status='pending')
        self._create_task('/media/file2.mkv', status='in_progress')
        self._create_task('/media/file3.mkv', status='processed')
        self._create_task('/media/file4.mkv', status='pending')

        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            tq = TaskQueue(data_queues={})
            result = tq.list_pending_tasks()
            assert len(result) == 2
            for item in result:
                assert item['status'] == 'pending'

    @pytest.mark.unittest
    def test_task_list_pending_is_empty(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            assert TaskQueue.task_list_pending_is_empty() is True
            self._create_task('/media/notempty.mkv', status='pending')
            assert TaskQueue.task_list_pending_is_empty() is False

    @pytest.mark.unittest
    def test_mark_item_in_progress(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            mock_task = MagicMock()
            TaskQueue.mark_item_in_progress(mock_task)
            mock_task.set_status.assert_called_once_with('in_progress')

    @pytest.mark.unittest
    def test_mark_item_as_processed(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            mock_task = MagicMock()
            TaskQueue.mark_item_as_processed(mock_task)
            mock_task.set_status.assert_called_once_with('processed')

    @pytest.mark.unittest
    def test_build_tasks_query_sort_order(self):
        self._create_task('/media/aaa.mkv', status='pending')
        self._create_task('/media/zzz.mkv', status='pending')

        from compresso.libs.taskqueue import build_tasks_query_full_task_list
        asc_results = list(build_tasks_query_full_task_list('pending', sort_by=Tasks.id, sort_order='asc'))
        desc_results = list(build_tasks_query_full_task_list('pending', sort_by=Tasks.id, sort_order='desc'))
        assert asc_results[0]['id'] < asc_results[-1]['id']
        assert desc_results[0]['id'] > desc_results[-1]['id']

    @pytest.mark.unittest
    def test_list_in_progress_tasks_empty(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            tq = TaskQueue(data_queues={})
            result = tq.list_in_progress_tasks()
            assert result == []

    @pytest.mark.unittest
    def test_list_in_progress_tasks_returns_in_progress_only(self):
        self._create_task('/media/ip1.mkv', status='in_progress')
        self._create_task('/media/ip2.mkv', status='pending')
        self._create_task('/media/ip3.mkv', status='in_progress')

        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            tq = TaskQueue(data_queues={})
            result = tq.list_in_progress_tasks()
            assert len(result) == 2
            for item in result:
                assert item['status'] == 'in_progress'

    @pytest.mark.unittest
    def test_list_processed_tasks_empty(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            tq = TaskQueue(data_queues={})
            result = tq.list_processed_tasks()
            assert result == []

    @pytest.mark.unittest
    def test_list_processed_tasks_returns_processed_only(self):
        self._create_task('/media/proc1.mkv', status='processed')
        self._create_task('/media/proc2.mkv', status='pending')

        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            tq = TaskQueue(data_queues={})
            result = tq.list_processed_tasks()
            assert len(result) == 1
            assert result[0]['status'] == 'processed'

    @pytest.mark.unittest
    def test_list_awaiting_approval_tasks_empty(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            tq = TaskQueue(data_queues={})
            result = tq.list_awaiting_approval_tasks()
            assert result == []

    @pytest.mark.unittest
    def test_list_awaiting_approval_tasks_returns_correct_status(self):
        self._create_task('/media/aa1.mkv', status='awaiting_approval')
        self._create_task('/media/aa2.mkv', status='pending')

        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            tq = TaskQueue(data_queues={})
            result = tq.list_awaiting_approval_tasks()
            assert len(result) == 1
            assert result[0]['status'] == 'awaiting_approval'

    @pytest.mark.unittest
    def test_task_list_in_progress_is_empty(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            assert TaskQueue.task_list_in_progress_is_empty() is True
            self._create_task('/media/ip.mkv', status='in_progress')
            assert TaskQueue.task_list_in_progress_is_empty() is False

    @pytest.mark.unittest
    def test_task_list_processed_is_empty(self):
        with patch('compresso.libs.taskqueue.CompressoLogging.get_logger'):
            from compresso.libs.taskqueue import TaskQueue
            assert TaskQueue.task_list_processed_is_empty() is True
            self._create_task('/media/proc.mkv', status='processed')
            assert TaskQueue.task_list_processed_is_empty() is False

    @pytest.mark.unittest
    def test_build_tasks_count_query_returns_zero_for_no_tasks(self):
        from compresso.libs.taskqueue import build_tasks_count_query
        count = build_tasks_count_query('pending')
        assert count == 0

    @pytest.mark.unittest
    def test_build_tasks_count_query_returns_one_for_existing(self):
        self._create_task('/media/count.mkv', status='pending')
        from compresso.libs.taskqueue import build_tasks_count_query
        count = build_tasks_count_query('pending')
        assert count >= 1

    @pytest.mark.unittest
    def test_fetch_next_task_filtered_returns_false_when_empty(self):
        from compresso.libs.taskqueue import fetch_next_task_filtered
        result = fetch_next_task_filtered('pending', sort_by=Tasks.id, sort_order='asc')
        assert result is False

    @pytest.mark.unittest
    def test_build_tasks_query_library_filter(self):
        second_library = Libraries.create(
            name='second_lib',
            path='/media/second',
            locked=False,
            enable_remote_only=False,
            enable_scanner=False,
            enable_inotify=False,
            priority_score=0,
        )
        self._create_task('/media/lib1_file.mkv', status='pending', library_id=self.default_library.id)
        self._create_task('/media/lib2_file.mkv', status='pending', library_id=second_library.id)

        from compresso.libs.taskqueue import build_tasks_query
        result = build_tasks_query(
            'pending',
            sort_by=Tasks.id,
            sort_order='asc',
            library_names=['second_lib'],
        )
        assert result is not None
        assert result.library_id == second_library.id


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
