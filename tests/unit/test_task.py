#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_task.py

    Unit tests for prepare_file_destination_data() and Task class methods.
"""

import os
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unittest
class TestPrepareFileDestinationData:

    def test_returns_expected_keys(self):
        from compresso.libs.task import prepare_file_destination_data
        result = prepare_file_destination_data('/media/video.mkv', 'mp4')
        assert 'basename' in result
        assert 'abspath' in result

    def test_uses_given_extension(self):
        from compresso.libs.task import prepare_file_destination_data
        result = prepare_file_destination_data('/media/video.mkv', 'mp4')
        assert result['basename'] == 'video.mp4'

    def test_abspath_combines_dirname_and_basename(self):
        from compresso.libs.task import prepare_file_destination_data
        result = prepare_file_destination_data('/media/movies/video.mkv', 'mp4')
        assert result['abspath'].endswith('/video.mp4')
        assert '/media/movies/' in result['abspath']

    def test_handles_dotted_filename(self):
        from compresso.libs.task import prepare_file_destination_data
        result = prepare_file_destination_data('/media/my.movie.2024.mkv', 'mp4')
        assert result['basename'] == 'my.movie.2024.mp4'


@pytest.mark.unittest
class TestTaskGetters:
    """Test Task getter methods with a mocked task model object."""

    def _make_task(self):
        from compresso.libs.task import Task
        t = Task()
        mock_task = MagicMock()
        mock_task.id = 42
        mock_task.type = 'local'
        mock_task.abspath = '/media/test_file.mkv'
        mock_task.cache_path = '/tmp/cache/test_file-abc12.mkv'
        mock_task.success = True
        mock_task.start_time = 1000.0
        mock_task.finish_time = 2000.0
        mock_task.library_id = 1
        mock_task.log = 'some log'
        mock_task.processed_by_worker = 'worker-0'
        mock_task.status = 'pending'
        mock_task.source_size = 5000
        t.task = mock_task
        return t

    def test_get_task_id(self):
        t = self._make_task()
        assert t.get_task_id() == 42

    def test_get_task_type(self):
        t = self._make_task()
        assert t.get_task_type() == 'local'

    def test_get_source_basename(self):
        t = self._make_task()
        assert t.get_source_basename() == 'test_file.mkv'

    def test_get_source_abspath(self):
        t = self._make_task()
        assert t.get_source_abspath() == '/media/test_file.mkv'

    def test_get_start_time(self):
        t = self._make_task()
        assert t.get_start_time() == 1000.0

    def test_get_finish_time(self):
        t = self._make_task()
        assert t.get_finish_time() == 2000.0

    def test_get_cache_path(self):
        t = self._make_task()
        assert t.get_cache_path() == '/tmp/cache/test_file-abc12.mkv'

    def test_get_task_success(self):
        t = self._make_task()
        assert t.get_task_success() is True

    def test_get_task_library_id(self):
        t = self._make_task()
        assert t.get_task_library_id() == 1

    def test_getters_raise_when_task_not_set(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.get_task_id()
        with pytest.raises(Exception, match="Task has not been set"):
            t.get_task_type()
        with pytest.raises(Exception, match="Task has not been set"):
            t.get_cache_path()

    def test_get_source_data_returns_dict(self):
        t = self._make_task()
        data = t.get_source_data()
        assert data['abspath'] == '/media/test_file.mkv'
        assert data['basename'] == 'test_file.mkv'

    def test_task_dump_returns_expected_keys(self):
        t = self._make_task()
        dump = t.task_dump()
        assert dump['task_label'] == 'test_file.mkv'
        assert dump['abspath'] == '/media/test_file.mkv'
        assert dump['task_success'] is True
        assert dump['source_size'] == 5000
        assert dump['library_id'] == 1

    def test_get_destination_data(self):
        t = self._make_task()
        data = t.get_destination_data()
        assert data['basename'] == 'test_file.mkv'


@pytest.mark.unittest
class TestTaskSetStatus:
    """Test set_status validation without requiring DB."""

    def test_set_status_invalid_raises(self):
        from compresso.libs.task import Task
        t = Task()
        t.task = MagicMock()
        with pytest.raises(Exception, match="Unable to set status"):
            t.set_status('invalid_status')

    def test_set_status_raises_when_no_task(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.set_status('pending')

    def test_set_success_true(self):
        from compresso.libs.task import Task
        t = Task()
        t.task = MagicMock()
        t.set_success(True)
        assert t.task.success is True

    def test_set_success_false(self):
        from compresso.libs.task import Task
        t = Task()
        t.task = MagicMock()
        t.set_success(False)
        assert t.task.success is False

    def test_modify_path(self):
        from compresso.libs.task import Task
        t = Task()
        t.task = MagicMock()
        t.modify_path('/new/path.mkv')
        assert t.task.abspath == '/new/path.mkv'

    def test_save_command_log(self):
        from compresso.libs.task import Task
        t = Task()
        t.task = MagicMock()
        t.task.log = ''
        t.save_command_log(['line1\n', 'line2\n'])
        assert t.task.log == 'line1\nline2\n'


@pytest.mark.unittest
class TestTaskDatabaseOps:
    """Test Task database operations with an in-memory DB."""

    def _create_library(self):
        from compresso.libs.unmodels import Libraries
        Libraries.create(
            name='Test Library',
            path='/media/test',
            locked=False,
            enable_scanner=True,
            enable_inotify=False,
            priority_score=0,
        )

    def test_create_task_by_absolute_path_returns_true(self, in_memory_db):
        from compresso.libs.task import Task
        self._create_library()
        with patch('compresso.libs.task.os.path.getsize', return_value=1000):
            t = Task()
            result = t.create_task_by_absolute_path('/media/newfile.mkv', library_id=1)
            assert result is True
            assert t.task is not None
            assert t.task.abspath == '/media/newfile.mkv'

    def test_create_task_duplicate_returns_false(self, in_memory_db):
        from compresso.libs.task import Task
        self._create_library()
        with patch('compresso.libs.task.os.path.getsize', return_value=1000):
            t1 = Task()
            t1.create_task_by_absolute_path('/media/duplicate.mkv', library_id=1)
            t2 = Task()
            result = t2.create_task_by_absolute_path('/media/duplicate.mkv', library_id=1)
            assert result is False

    def test_read_and_set_task_by_absolute_path(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        Tasks.create(abspath='/media/existing.mkv', status='pending', library_id=1)
        t = Task()
        t.read_and_set_task_by_absolute_path('/media/existing.mkv')
        assert t.task is not None
        assert t.task.abspath == '/media/existing.mkv'

    def test_set_status_updates_db(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        row = Tasks.create(abspath='/media/status_test.mkv', status='creating', library_id=1)
        t = Task()
        t.task = row
        t.set_status('pending')
        refreshed = Tasks.get_by_id(row.id)
        assert refreshed.status == 'pending'

    def test_delete_removes_row(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        row = Tasks.create(abspath='/media/to_delete.mkv', status='pending', library_id=1)
        row_id = row.id
        t = Task()
        t.task = row
        t.delete()
        assert Tasks.select().where(Tasks.id == row_id).count() == 0

    def test_get_total_task_list_count(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        Tasks.delete().execute()
        Tasks.create(abspath='/media/count1.mkv', status='pending', library_id=1)
        Tasks.create(abspath='/media/count2.mkv', status='pending', library_id=1)
        t = Task()
        assert t.get_total_task_list_count() == 2

    def test_get_task_list_filtered_and_sorted_with_search(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        Tasks.delete().execute()
        Tasks.create(abspath='/media/alpha.mkv', status='pending', library_id=1)
        Tasks.create(abspath='/media/beta.mkv', status='pending', library_id=1)
        t = Task()
        result = list(t.get_task_list_filtered_and_sorted(search_value='alpha'))
        assert len(result) >= 1
        assert any('alpha' in str(r.get('abspath', '')) for r in result)

    def test_save_persists_changes(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        row = Tasks.create(abspath='/media/save_test.mkv', status='creating', library_id=1)
        t = Task()
        t.task = row
        t.task.status = 'pending'
        t.save()
        refreshed = Tasks.get_by_id(row.id)
        assert refreshed.status == 'pending'
