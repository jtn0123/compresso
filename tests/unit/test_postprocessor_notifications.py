#!/usr/bin/env python3

"""
    tests.unit.test_postprocessor_notifications.py

    Unit tests for notification dispatch integration in PostProcessor:
    - _finalize_local_task dispatches 'task_completed' on success
    - _finalize_local_task dispatches 'task_failed' on failure
    - _stage_for_approval dispatches 'approval_needed'
    - Notification failure does not crash the postprocessor
"""

import os
import shutil
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest


def _make_postprocessor():
    """Create a PostProcessor with mocked dependencies."""
    with patch('compresso.libs.postprocessor.config.Config'), \
         patch('compresso.libs.postprocessor.CompressoLogging') as mock_logging:
        mock_logger = MagicMock()
        mock_logging.get_logger.return_value = mock_logger

        from compresso.libs.postprocessor import PostProcessor

        data_queues = {}
        task_queue = MagicMock()
        event = threading.Event()
        pp = PostProcessor(data_queues, task_queue, event)
        return pp


def _make_mock_task(success=True, source_abspath='/lib/movie.mkv', cache_path='/cache/movie.mkv'):
    """Build a mock task with the standard interface."""
    mock_task = MagicMock()
    mock_task.task.success = success
    mock_task.task.source_size = 5000000
    mock_task.task.vmaf_score = 92.5
    mock_task.task.ssim_score = 0.97
    mock_task.get_source_data.return_value = {'abspath': source_abspath, 'size': 5000000}
    mock_task.get_destination_data.return_value = {'abspath': source_abspath, 'size': 3000000}
    mock_task.get_source_abspath.return_value = source_abspath
    mock_task.get_cache_path.return_value = cache_path
    mock_task.get_task_id.return_value = 42
    mock_task.get_task_library_id.return_value = 1
    mock_task.get_task_type.return_value = 'local'
    return mock_task


# ------------------------------------------------------------------
# TestFinalizeLocalTaskNotifications
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFinalizeLocalTaskNotifications:
    """Tests that _finalize_local_task dispatches the correct external notifications."""

    @patch('compresso.libs.external_notifications.ExternalNotificationDispatcher')
    def test_dispatches_task_completed_on_success(self, mock_dispatcher_cls):
        pp = _make_postprocessor()
        mock_task = _make_mock_task(success=True)
        pp.current_task = mock_task

        mock_dispatcher = MagicMock()
        mock_dispatcher_cls.return_value = mock_dispatcher

        pp.post_process_file = MagicMock()
        pp.write_history_log = MagicMock()
        pp.commit_task_metadata = MagicMock()
        pp._cleanup_staging_files = MagicMock()

        pp._finalize_local_task()

        mock_dispatcher.dispatch.assert_called_once()
        event_name = mock_dispatcher.dispatch.call_args[0][0]
        assert event_name == 'task_completed'

    @patch('compresso.libs.external_notifications.ExternalNotificationDispatcher')
    def test_dispatches_task_failed_on_failure(self, mock_dispatcher_cls):
        pp = _make_postprocessor()
        mock_task = _make_mock_task(success=False)
        pp.current_task = mock_task

        mock_dispatcher = MagicMock()
        mock_dispatcher_cls.return_value = mock_dispatcher

        pp.post_process_file = MagicMock()
        pp.write_history_log = MagicMock()
        pp.commit_task_metadata = MagicMock()
        pp._cleanup_staging_files = MagicMock()

        pp._finalize_local_task()

        mock_dispatcher.dispatch.assert_called_once()
        event_name = mock_dispatcher.dispatch.call_args[0][0]
        assert event_name == 'task_failed'

    @patch('compresso.libs.external_notifications.ExternalNotificationDispatcher')
    def test_notification_context_contains_file_name(self, mock_dispatcher_cls):
        pp = _make_postprocessor()
        mock_task = _make_mock_task(success=True, source_abspath='/lib/my_movie.mkv')
        pp.current_task = mock_task

        mock_dispatcher = MagicMock()
        mock_dispatcher_cls.return_value = mock_dispatcher

        pp.post_process_file = MagicMock()
        pp.write_history_log = MagicMock()
        pp.commit_task_metadata = MagicMock()
        pp._cleanup_staging_files = MagicMock()

        pp._finalize_local_task()

        context = mock_dispatcher.dispatch.call_args[0][1]
        assert context['file_name'] == 'my_movie.mkv'

    @patch('compresso.libs.external_notifications.ExternalNotificationDispatcher')
    def test_notification_failure_does_not_crash_finalize(self, mock_dispatcher_cls):
        """If ExternalNotificationDispatcher raises, _finalize_local_task should still complete."""
        pp = _make_postprocessor()
        mock_task = _make_mock_task(success=True)
        pp.current_task = mock_task

        mock_dispatcher_cls.side_effect = ImportError("notifications not available")

        pp.post_process_file = MagicMock()
        pp.write_history_log = MagicMock()
        pp.commit_task_metadata = MagicMock()
        pp._cleanup_staging_files = MagicMock()

        # Should not raise
        pp._finalize_local_task()

        # Core operations should still have been called
        pp.post_process_file.assert_called_once()
        pp.write_history_log.assert_called_once()


# ------------------------------------------------------------------
# TestStageForApprovalNotifications
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestStageForApprovalNotifications:
    """Tests that _stage_for_approval dispatches 'approval_needed' notification."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix='compresso_test_staging_notif_')
        self.staging_dir = os.path.join(self.tmpdir, 'staging')
        self.cache_dir = os.path.join(self.tmpdir, 'compresso_file_conversion_test')
        os.makedirs(self.staging_dir)
        os.makedirs(self.cache_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_cache_file(self, name='output.mkv', content=b'transcoded video data'):
        path = os.path.join(self.cache_dir, name)
        with open(path, 'wb') as f:
            f.write(content)
        return path

    @patch('compresso.libs.external_notifications.ExternalNotificationDispatcher')
    @patch('compresso.libs.ffprobe_utils.compute_quality_scores', return_value=None)
    def test_dispatches_approval_needed_notification(self, mock_quality_scores,
                                                      mock_dispatcher_cls):
        pp = _make_postprocessor()
        pp.settings.get_staging_path.return_value = self.staging_dir

        cache_file = self._make_cache_file()

        mock_task = MagicMock()
        mock_task.get_cache_path.return_value = cache_file
        mock_task.get_task_id.return_value = 42
        mock_task.get_source_abspath.return_value = '/lib/movie.mkv'
        mock_task.get_source_data.return_value = {'abspath': '/lib/movie.mkv'}
        mock_task.task.success = True
        mock_task.task.vmaf_score = None
        mock_task.task.ssim_score = None
        pp.current_task = mock_task

        mock_dispatcher = MagicMock()
        mock_dispatcher_cls.return_value = mock_dispatcher

        pp._stage_for_approval()

        mock_dispatcher.dispatch.assert_called_once()
        event_name = mock_dispatcher.dispatch.call_args[0][0]
        context = mock_dispatcher.dispatch.call_args[0][1]
        assert event_name == 'approval_needed'
        assert context['file_name'] == 'movie.mkv'
        assert context['task_id'] == 42
        assert 'staged_path' in context

    @patch('compresso.libs.external_notifications.ExternalNotificationDispatcher')
    @patch('compresso.libs.ffprobe_utils.compute_quality_scores', return_value=None)
    def test_approval_notification_failure_does_not_crash(self, mock_quality_scores,
                                                           mock_dispatcher_cls):
        """Notification failure during staging should not prevent staging completion."""
        pp = _make_postprocessor()
        pp.settings.get_staging_path.return_value = self.staging_dir

        cache_file = self._make_cache_file()

        mock_task = MagicMock()
        mock_task.get_cache_path.return_value = cache_file
        mock_task.get_task_id.return_value = 43
        mock_task.get_source_abspath.return_value = '/lib/test.mkv'
        mock_task.get_source_data.return_value = {'abspath': '/lib/test.mkv'}
        mock_task.task.success = True
        mock_task.task.vmaf_score = None
        mock_task.task.ssim_score = None
        pp.current_task = mock_task

        mock_dispatcher_cls.side_effect = ImportError("notifications not available")

        # Should not raise
        pp._stage_for_approval()

        # Status should still be set despite notification failure
        mock_task.set_status.assert_called_once_with('awaiting_approval')


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
