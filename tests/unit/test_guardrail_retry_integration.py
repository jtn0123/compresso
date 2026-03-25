#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_guardrail_retry_integration.py

    Integration-style unit tests verifying that the guardrail rejection
    flow correctly prevents retries. This tests the end-to-end path:
    1. Size guardrail writes rejection message into task.log
    2. _is_guardrail_rejection() detects it in task.log
    3. _attempt_retry() skips the task

    Also tests the WebSocket pending tasks helper includes retry fields.
"""

import threading

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_postprocessor():
    """Create a PostProcessor instance with minimal mocked dependencies."""
    with patch('compresso.libs.postprocessor.CompressoLogging') as mock_log, \
         patch('compresso.libs.postprocessor.config.Config') as mock_config:
        mock_log.get_logger.return_value = MagicMock()
        mock_settings = MagicMock()
        mock_settings.get_default_max_retries.return_value = 3
        mock_config.return_value = mock_settings
        from compresso.libs.postprocessor import PostProcessor
        pp = PostProcessor({}, MagicMock(), threading.Event())
    return pp


# ------------------------------------------------------------------
# TestGuardrailWritesToTaskLog
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGuardrailWritesToTaskLog:
    """Verify the guardrail rejection message is written into task.log so
    _is_guardrail_rejection() can detect it."""

    def test_guardrail_rejection_populates_task_log(self):
        """When size guardrail rejects, the rejection message must appear in task.log."""
        pp = _make_postprocessor()

        # Create a mock task with a DB-like atomic context
        mock_task_obj = MagicMock()
        mock_task_obj.success = True  # Start as successful
        mock_task_obj.log = ''
        mock_task_obj.source_size = 1000
        mock_task_obj.retry_count = 0
        mock_task_obj.max_retries = 3

        mock_db = MagicMock()
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_db.atomic.return_value = mock_atomic
        mock_task_obj._meta = MagicMock()
        mock_task_obj._meta.database = mock_db

        mock_current_task = MagicMock()
        mock_current_task.task = mock_task_obj
        mock_current_task.get_task_type.return_value = 'local'
        mock_current_task.get_task_library_id.return_value = 1
        mock_current_task.get_source_abspath.return_value = '/test/video.mkv'
        mock_current_task.get_cache_path.return_value = '/tmp/cache/video.mkv'
        mock_current_task.get_task_id.return_value = 1
        pp.current_task = mock_current_task

        # Set up library with guardrails that will reject
        mock_library = MagicMock()
        mock_library.get_size_guardrail_enabled.return_value = True
        mock_library.get_size_guardrail_min_pct.return_value = 10
        mock_library.get_size_guardrail_max_pct.return_value = 95
        mock_library.get_replacement_policy.return_value = 'replace'

        # Simulate output file that is 150% of source (will be rejected)
        with patch('compresso.libs.postprocessor.Library', return_value=mock_library), \
             patch('compresso.libs.postprocessor.os.path.exists', return_value=True), \
             patch('compresso.libs.postprocessor.os.path.getsize', return_value=1500), \
             patch('compresso.libs.postprocessor.PluginsHandler'), \
             patch('compresso.libs.postprocessor.FrontendPushMessages'):

            pp._handle_processed_task()

        # The task.log should now contain the guardrail rejection message
        assert 'Size guardrail REJECTED' in mock_task_obj.log
        # The task should have been marked as failed
        assert mock_task_obj.success is False

    def test_guardrail_rejection_prevents_retry(self):
        """Full flow: guardrail rejection → log populated → retry skipped."""
        pp = _make_postprocessor()

        # Mock task with guardrail rejection already in log
        mock_task_obj = MagicMock()
        mock_task_obj.success = False
        mock_task_obj.log = 'Size guardrail REJECTED: 150.0% (allowed 10-95%)'
        mock_task_obj.retry_count = 0
        mock_task_obj.max_retries = 3

        mock_current_task = MagicMock()
        mock_current_task.task = mock_task_obj
        pp.current_task = mock_current_task

        # _attempt_retry should detect the guardrail rejection and return False
        result = pp._attempt_retry()
        assert result is False
        mock_task_obj.save.assert_not_called()

    def test_non_guardrail_failure_is_retried(self):
        """A normal failure (not guardrail) should be retried."""
        pp = _make_postprocessor()

        mock_task_obj = MagicMock()
        mock_task_obj.success = False
        mock_task_obj.log = 'ffmpeg exited with code 137'
        mock_task_obj.retry_count = 0
        mock_task_obj.max_retries = 3

        mock_db = MagicMock()
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_db.atomic.return_value = mock_atomic
        mock_task_obj._meta = MagicMock()
        mock_task_obj._meta.database = mock_db

        mock_current_task = MagicMock()
        mock_current_task.task = mock_task_obj
        mock_current_task.get_source_abspath.return_value = '/test/video.mkv'
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        with patch('compresso.libs.postprocessor.FrontendPushMessages'):
            result = pp._attempt_retry()

        assert result is True
        assert mock_task_obj.status == 'pending'
        assert mock_task_obj.retry_count == 1
        mock_task_obj.save.assert_called_once()

    def test_guardrail_log_appends_to_existing_log(self):
        """If task already has log content, guardrail message is appended."""
        pp = _make_postprocessor()

        mock_task_obj = MagicMock()
        mock_task_obj.success = True
        mock_task_obj.log = 'RUNNER:\nCOMMAND:\nffmpeg ...\nLOG:\nProcessing complete'
        mock_task_obj.source_size = 1000

        mock_db = MagicMock()
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_db.atomic.return_value = mock_atomic
        mock_task_obj._meta = MagicMock()
        mock_task_obj._meta.database = mock_db

        mock_current_task = MagicMock()
        mock_current_task.task = mock_task_obj
        mock_current_task.get_task_type.return_value = 'local'
        mock_current_task.get_task_library_id.return_value = 1
        mock_current_task.get_source_abspath.return_value = '/test/video.mkv'
        mock_current_task.get_cache_path.return_value = '/tmp/cache/video.mkv'
        mock_current_task.get_task_id.return_value = 1
        pp.current_task = mock_current_task

        mock_library = MagicMock()
        mock_library.get_size_guardrail_enabled.return_value = True
        mock_library.get_size_guardrail_min_pct.return_value = 10
        mock_library.get_size_guardrail_max_pct.return_value = 95
        mock_library.get_replacement_policy.return_value = 'replace'

        with patch('compresso.libs.postprocessor.Library', return_value=mock_library), \
             patch('compresso.libs.postprocessor.os.path.exists', return_value=True), \
             patch('compresso.libs.postprocessor.os.path.getsize', return_value=1500), \
             patch('compresso.libs.postprocessor.PluginsHandler'), \
             patch('compresso.libs.postprocessor.FrontendPushMessages'):

            pp._handle_processed_task()

        # Both the original log and the rejection should be present
        assert 'RUNNER:' in mock_task_obj.log
        assert 'Size guardrail REJECTED' in mock_task_obj.log


# ------------------------------------------------------------------
# TestPendingTasksRetryFields
# ------------------------------------------------------------------

def _call_helper_with_mock_tasks(task_records):
    """Call prepare_filtered_pending_tasks with mocked task handler returning given records."""
    mock_task_handler = MagicMock()
    mock_task_handler.get_total_task_list_count.return_value = len(task_records)

    # First call is for .count() (filtered count), second call returns iterable results
    mock_count_result = MagicMock()
    mock_count_result.count.return_value = len(task_records)
    mock_task_handler.get_task_list_filtered_and_sorted.side_effect = [
        mock_count_result,
        task_records,
    ]

    with patch('compresso.webserver.helpers.pending_tasks.task') as mock_task_module:
        mock_task_module.Task.return_value = mock_task_handler
        from compresso.webserver.helpers.pending_tasks import prepare_filtered_pending_tasks
        return prepare_filtered_pending_tasks({})


@pytest.mark.unittest
class TestPendingTasksRetryFields:
    """Verify that pending_tasks helper includes retry_count and deferred_until
    when they are present on a task."""

    def test_includes_retry_count_when_nonzero(self):
        """Pending task result should include retry_count when > 0."""
        result = _call_helper_with_mock_tasks([{
            'id': 1,
            'abspath': '/test/video.mkv',
            'priority': 100,
            'type': 'local',
            'status': 'pending',
            'retry_count': 2,
            'deferred_until': '2025-03-24 15:30:00',
            'library_id': 1,
        }])
        item = result['results'][0]
        assert 'retry_count' in item
        assert item['retry_count'] == 2
        assert 'deferred_until' in item

    def test_omits_retry_count_when_zero(self):
        """Pending task result should NOT include retry_count when 0."""
        result = _call_helper_with_mock_tasks([{
            'id': 1,
            'abspath': '/test/video.mkv',
            'priority': 100,
            'type': 'local',
            'status': 'pending',
            'retry_count': 0,
            'deferred_until': None,
            'library_id': 1,
        }])
        item = result['results'][0]
        assert 'retry_count' not in item
        assert 'deferred_until' not in item

    def test_omits_retry_count_when_none(self):
        """Pending task result should NOT include retry_count when None."""
        result = _call_helper_with_mock_tasks([{
            'id': 1,
            'abspath': '/test/video.mkv',
            'priority': 100,
            'type': 'local',
            'status': 'pending',
            'retry_count': None,
            'deferred_until': None,
            'library_id': 1,
        }])
        item = result['results'][0]
        assert 'retry_count' not in item
        assert 'deferred_until' not in item
