#!/usr/bin/env python3

import queue
from unittest.mock import MagicMock, patch

import pytest
from peewee import OperationalError


@pytest.fixture
def task_handler():
    from compresso.libs.taskhandler import TaskHandler

    data_queues = {
        'inotifytasks': queue.Queue(),
        'scheduledtasks': queue.Queue(),
    }
    event = MagicMock()
    event.wait.return_value = None

    with patch('compresso.libs.taskhandler.config.Config') as mock_config, \
         patch('compresso.libs.taskhandler.CompressoLogging.get_logger', return_value=MagicMock()), \
         patch.object(TaskHandler, 'clear_tasks_on_startup'):
        mock_config.return_value.get_clear_pending_tasks_on_restart.return_value = True
        handler = TaskHandler(data_queues, MagicMock(), event)

    return handler


@pytest.mark.unittest
def test_stop_sets_abort_flag(task_handler):
    task_handler.stop()

    assert task_handler.abort_flag.is_set()


@pytest.mark.unittest
def test_run_processes_queues_then_exits(task_handler):
    task_handler.process_inotifytasks_queue = MagicMock()

    def stop_after_scheduled():
        task_handler.abort_flag.set()

    task_handler.process_scheduledtasks_queue = MagicMock(side_effect=stop_after_scheduled)

    task_handler.run()

    task_handler.event.wait.assert_called_once_with(2)
    task_handler.process_scheduledtasks_queue.assert_called_once_with()
    task_handler.process_inotifytasks_queue.assert_called_once_with()


@pytest.mark.unittest
def test_process_scheduledtasks_queue_logs_add_and_skip(task_handler):
    task_handler.scheduledtasks.put({'pathname': '/one.mkv', 'library_id': 1, 'priority_score': 10})
    task_handler.scheduledtasks.put({'pathname': '/two.mkv', 'library_id': 2})
    task_handler.add_path_to_task_queue = MagicMock(side_effect=[True, False])
    task_handler._log = MagicMock()

    task_handler.process_scheduledtasks_queue()

    task_handler.add_path_to_task_queue.assert_any_call('/one.mkv', 1, priority_score=10)
    task_handler.add_path_to_task_queue.assert_any_call('/two.mkv', 2, priority_score=0)
    assert task_handler._log.call_count == 2


@pytest.mark.unittest
def test_process_scheduledtasks_queue_logs_exception(task_handler):
    task_handler.scheduledtasks.put({'pathname': '/one.mkv', 'library_id': 1})
    task_handler.add_path_to_task_queue = MagicMock(side_effect=Exception('boom'))
    task_handler._log = MagicMock()

    task_handler.process_scheduledtasks_queue()

    task_handler._log.assert_called_with('Exception in processing scheduledtasks', 'boom', level='exception')


@pytest.mark.unittest
def test_process_inotifytasks_queue_logs_add_and_skip(task_handler):
    task_handler.inotifytasks.put({'pathname': '/one.mkv', 'library_id': 1})
    task_handler.inotifytasks.put({'pathname': '/two.mkv', 'library_id': 2, 'priority_score': 20})
    task_handler.add_path_to_task_queue = MagicMock(side_effect=[True, False])
    task_handler._log = MagicMock()

    task_handler.process_inotifytasks_queue()

    task_handler.add_path_to_task_queue.assert_any_call('/one.mkv', 1, priority_score=0)
    task_handler.add_path_to_task_queue.assert_any_call('/two.mkv', 2, priority_score=20)
    assert task_handler._log.call_count == 2


@pytest.mark.unittest
def test_process_inotifytasks_queue_logs_exception(task_handler):
    task_handler.inotifytasks.put({'pathname': '/one.mkv', 'library_id': 1})
    task_handler.add_path_to_task_queue = MagicMock(side_effect=Exception('boom'))
    task_handler._log = MagicMock()

    task_handler.process_inotifytasks_queue()

    task_handler._log.assert_called_with('Exception in processing inotifytasks', 'boom', level='exception')


@pytest.mark.unittest
def test_clear_tasks_on_startup_clears_matching_tasks(task_handler):
    select_query = MagicMock()
    select_query.where.return_value = select_query
    select_query.tuples.return_value = [(1,), (2,)]

    delete_query = MagicMock()
    delete_query.where.return_value = delete_query
    delete_query.execute.return_value = 2

    task_handler.settings.get_clear_pending_tasks_on_restart.return_value = False
    task_handler._log = MagicMock()

    with patch('compresso.libs.taskhandler.Tasks.select', return_value=select_query), \
         patch('compresso.libs.taskhandler.Tasks.delete', return_value=delete_query), \
         patch('compresso.libs.taskhandler.task.TaskDataStore.clear_task') as mock_clear:
        task_handler.clear_tasks_on_startup()

    assert mock_clear.call_count == 2
    select_query.where.assert_called_once()
    delete_query.where.assert_called_once()
    delete_query.execute.assert_called_once_with()


@pytest.mark.unittest
def test_clear_tasks_on_startup_handles_missing_table(task_handler):
    task_handler._log = MagicMock()

    with patch('compresso.libs.taskhandler.Tasks.select', side_effect=OperationalError('missing')):
        task_handler.clear_tasks_on_startup()

    task_handler._log.assert_called_with(
        'Skipping task cleanup at startup; tasks table missing',
        'missing',
        level='debug',
    )


@pytest.mark.unittest
def test_check_if_task_exists_matching_path_true_and_false():
    from compresso.libs.taskhandler import TaskHandler

    existing_query = MagicMock()
    existing_query.where.return_value = existing_query
    existing_query.limit.return_value = existing_query
    existing_query.count.return_value = 1

    with patch('compresso.libs.taskhandler.Tasks.select', return_value=existing_query):
        assert TaskHandler.check_if_task_exists_matching_path('/tmp/video.mkv') is True

    existing_query.count.return_value = 0
    with patch('compresso.libs.taskhandler.Tasks.select', return_value=existing_query):
        assert TaskHandler.check_if_task_exists_matching_path('/tmp/video.mkv') is False


@pytest.mark.unittest
def test_add_path_to_task_queue_returns_false_when_task_exists(task_handler):
    task_handler.check_if_task_exists_matching_path = MagicMock(return_value=True)

    assert task_handler.add_path_to_task_queue('/tmp/video.mkv', 1) is False


@pytest.mark.unittest
def test_add_path_to_task_queue_runs_event_plugins(task_handler):
    created_task = MagicMock()
    created_task.get_task_id.return_value = 42
    created_task.get_task_type.return_value = 'local'
    created_task.get_source_data.return_value = {'file': '/tmp/video.mkv'}

    task_handler.check_if_task_exists_matching_path = MagicMock(return_value=False)
    task_handler.create_task_from_path = MagicMock(return_value=created_task)

    with patch('compresso.libs.taskhandler.PluginsHandler') as mock_plugins:
        assert task_handler.add_path_to_task_queue('/tmp/video.mkv', 9, priority_score=50) is True

    mock_plugins.return_value.run_event_plugins_for_plugin_type.assert_called_once()


@pytest.mark.unittest
def test_create_task_from_path_returns_false_when_task_creation_fails(task_handler):
    with patch('compresso.libs.taskhandler.task.Task') as mock_task_cls:
        mock_task = MagicMock()
        mock_task.create_task_by_absolute_path.return_value = False
        mock_task_cls.return_value = mock_task

        assert task_handler.create_task_from_path('/tmp/video.mkv', 3) is False


@pytest.mark.unittest
def test_create_task_from_path_returns_new_task_on_success(task_handler):
    with patch('compresso.libs.taskhandler.task.Task') as mock_task_cls:
        mock_task = MagicMock()
        mock_task.create_task_by_absolute_path.return_value = True
        mock_task_cls.return_value = mock_task

        assert task_handler.create_task_from_path('/tmp/video.mkv', 3, priority_score=77) is mock_task
        mock_task.create_task_by_absolute_path.assert_called_once()
