#!/usr/bin/env python3

"""
    tests.unit.test_task_extended.py

    Extended unit tests for compresso.libs.task.Task and TaskDataStore.
    Covers error paths, delete_tasks_recursively, reorder_tasks,
    set_tasks_status, set_tasks_library_id, and edge cases.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.mark.unittest
class TestTaskSetCachePath:

    def test_set_cache_path_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.set_cache_path()

    def test_set_cache_path_default(self):
        from compresso.libs.task import Task
        t = Task()
        mock_task = MagicMock()
        mock_task.cache_path = None
        t.task = mock_task
        with patch('compresso.libs.task.os.path.splitext', return_value=('video', '.mkv')):
            with patch.object(t, 'get_source_basename', return_value='video.mkv'):
                with patch('compresso.libs.task.common.random_string', return_value='abc'):
                    with patch('compresso.libs.task.time.time', return_value=1000):
                        t.set_cache_path()
        assert t.task.cache_path is not None

    def test_set_cache_path_custom_directory(self):
        from compresso.libs.task import Task
        t = Task()
        mock_task = MagicMock()
        mock_task.cache_path = None
        t.task = mock_task
        with patch.object(t, 'get_source_basename', return_value='file.mp4'):
            with patch('compresso.libs.task.common.random_string', return_value='xyz'):
                with patch('compresso.libs.task.time.time', return_value=2000):
                    t.set_cache_path(cache_directory='/custom/cache')
        assert os.path.normpath('/custom/cache') in os.path.normpath(t.task.cache_path)

    def test_set_cache_path_custom_extension(self):
        from compresso.libs.task import Task
        t = Task()
        mock_task = MagicMock()
        mock_task.cache_path = None
        t.task = mock_task
        with patch.object(t, 'get_source_basename', return_value='file.mkv'):
            with patch('compresso.libs.task.common.random_string', return_value='test'):
                with patch('compresso.libs.task.time.time', return_value=3000):
                    t.set_cache_path(file_extension='avi')
        assert t.task.cache_path.endswith('.avi')


@pytest.mark.unittest
class TestTaskGetCachePath:

    def test_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.get_cache_path()

    def test_no_cache_path_raises(self):
        from compresso.libs.task import Task
        t = Task()
        t.task = MagicMock()
        t.task.cache_path = None
        with pytest.raises(Exception, match="cache path has not been set"):
            t.get_cache_path()


@pytest.mark.unittest
class TestTaskGetTaskData:

    def test_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.get_task_data()

    def test_returns_dict(self):
        from compresso.libs.task import Task
        t = Task()
        t.task = MagicMock()
        with patch('compresso.libs.task.model_to_dict', return_value={'id': 1, 'abspath': '/test'}):
            data = t.get_task_data()
        assert isinstance(data, dict)


@pytest.mark.unittest
class TestTaskGetLibraryName:

    def test_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.get_task_library_name()


@pytest.mark.unittest
class TestTaskGetLibraryPriorityScore:

    def test_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.get_task_library_priority_score()


@pytest.mark.unittest
class TestTaskSaveErrors:

    def test_save_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.save()

    def test_delete_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.delete()

    def test_modify_path_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.modify_path('/new/path')

    def test_save_command_log_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.save_command_log(['line'])

    def test_set_success_no_task_raises(self):
        from compresso.libs.task import Task
        t = Task()
        with pytest.raises(Exception, match="Task has not been set"):
            t.set_success(True)

    def test_get_source_data_no_abspath_raises(self):
        from compresso.libs.task import Task
        t = Task()
        t.task = MagicMock()
        t.task.abspath = None
        with pytest.raises(Exception, match="absolute path has not been set"):
            t.get_source_data()


@pytest.mark.unittest
class TestDeleteTasksRecursively:

    def test_empty_list_returns_false(self):
        from compresso.libs.task import Task
        t = Task()
        result = t.delete_tasks_recursively([])
        assert result is False

    def test_none_list_returns_false(self):
        from compresso.libs.task import Task
        t = Task()
        result = t.delete_tasks_recursively(None)
        assert result is False


@pytest.mark.unittest
class TestReorderTasks:

    def test_reorder_calls_update(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        Tasks.delete().execute()
        t1 = Tasks.create(abspath='/a.mkv', status='pending', library_id=1, priority=1)
        Tasks.create(abspath='/b.mkv', status='pending', library_id=1, priority=2)
        t = Task()
        result = t.reorder_tasks([t1.id], "top")
        assert result >= 0

    def test_reorder_bottom_sets_zero(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        Tasks.delete().execute()
        t1 = Tasks.create(abspath='/bottom.mkv', status='pending', library_id=1, priority=100)
        t = Task()
        t.reorder_tasks([t1.id], "bottom")
        refreshed = Tasks.get_by_id(t1.id)
        assert refreshed.priority == 0


@pytest.mark.unittest
class TestSetTasksStatus:

    def test_updates_status(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        Tasks.delete().execute()
        row = Tasks.create(abspath='/status.mkv', status='pending', library_id=1)
        Task.set_tasks_status([row.id], 'complete')
        refreshed = Tasks.get_by_id(row.id)
        assert refreshed.status == 'complete'


@pytest.mark.unittest
class TestSetTasksLibraryId:

    def test_updates_library_id(self, in_memory_db):
        from compresso.libs.task import Task
        from compresso.libs.unmodels.tasks import Tasks
        Tasks.delete().execute()
        row = Tasks.create(abspath='/lib.mkv', status='pending', library_id=1)
        Task.set_tasks_library_id([row.id], 5)
        refreshed = Tasks.get_by_id(row.id)
        assert refreshed.library_id == 5


@pytest.mark.unittest
class TestTaskDataStoreExtended:

    def test_export_import_json(self):
        from compresso.libs.task import TaskDataStore
        TaskDataStore.clear_task(999)
        TaskDataStore.set_task_state('key1', 'value1', task_id=999)
        exported = TaskDataStore.export_task_state_json(999)
        parsed = json.loads(exported)
        assert parsed['key1'] == 'value1'

        TaskDataStore.clear_task(998)
        TaskDataStore.import_task_state_json(998, exported)
        assert TaskDataStore.get_task_state('key1', task_id=998) == 'value1'

        # Cleanup
        TaskDataStore.clear_task(999)
        TaskDataStore.clear_task(998)

    def test_import_non_dict_raises(self):
        from compresso.libs.task import TaskDataStore
        with pytest.raises(ValueError, match="must be an object"):
            TaskDataStore.import_task_state_json(999, '"not a dict"')

    def test_delete_task_state(self):
        from compresso.libs.task import TaskDataStore
        TaskDataStore.clear_task(997)
        TaskDataStore.set_task_state('to_delete', 'val', task_id=997)
        TaskDataStore.delete_task_state('to_delete', task_id=997)
        assert TaskDataStore.get_task_state('to_delete', task_id=997) is None
        TaskDataStore.clear_task(997)

    def test_delete_task_state_no_context_raises(self):
        from compresso.libs.task import TaskDataStore
        TaskDataStore.clear_context()
        with pytest.raises(RuntimeError, match="Task ID not provided"):
            TaskDataStore.delete_task_state('key')

    def test_export_empty_task(self):
        from compresso.libs.task import TaskDataStore
        TaskDataStore.clear_task(996)
        assert TaskDataStore.export_task_state(996) == {}

    def test_import_task_state_merges(self):
        from compresso.libs.task import TaskDataStore
        TaskDataStore.clear_task(995)
        TaskDataStore.set_task_state('existing', 'old', task_id=995)
        TaskDataStore.import_task_state(995, {'new_key': 'new_val'})
        assert TaskDataStore.get_task_state('existing', task_id=995) == 'old'
        assert TaskDataStore.get_task_state('new_key', task_id=995) == 'new_val'
        TaskDataStore.clear_task(995)

    def test_runner_value_immutable(self):
        from compresso.libs.task import TaskDataStore
        TaskDataStore.clear_task(994)
        TaskDataStore.bind_runner_context(994, 'plugin_a', 'runner_x')
        assert TaskDataStore.set_runner_value('key', 'val1') is True
        # Second set should return False (immutable)
        assert TaskDataStore.set_runner_value('key', 'val2') is False
        assert TaskDataStore.get_runner_value('key') == 'val1'
        TaskDataStore.clear_context()
        TaskDataStore.clear_task(994)

    def test_runner_value_no_context_raises(self):
        from compresso.libs.task import TaskDataStore
        TaskDataStore.clear_context()
        with pytest.raises(RuntimeError, match="Runner context not bound"):
            TaskDataStore.set_runner_value('key', 'val')

    def test_get_runner_value_cross_plugin(self):
        from compresso.libs.task import TaskDataStore
        TaskDataStore.clear_task(993)
        TaskDataStore.bind_runner_context(993, 'plugin_a', 'runner_x')
        TaskDataStore.set_runner_value('data', 42)
        # Access from different plugin context using overrides
        TaskDataStore.bind_runner_context(993, 'plugin_b', 'runner_y')
        val = TaskDataStore.get_runner_value('data', plugin_id='plugin_a', runner='runner_x')
        assert val == 42
        TaskDataStore.clear_context()
        TaskDataStore.clear_task(993)
