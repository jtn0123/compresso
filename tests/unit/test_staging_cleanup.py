#!/usr/bin/env python3

"""
    tests.unit.test_staging_cleanup.py

    Unit tests for ScheduledTasksManager.cleanup_expired_staging().
    Verifies correct behavior for:
    - Expired awaiting_approval tasks (auto-rejected and cleaned)
    - Orphaned staging directories (task deleted or in wrong status)
    - Tasks still within the expiry window (preserved)
    - Disabled cleanup (staging_expiry_days <= 0)
    - Non-existent staging path
"""

import os
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.libs.unmodels import Libraries, Tags
from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels.tasks import Tasks

LibraryTags = Libraries.tags.get_through_model()


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture
def staging_db(tmp_path):
    """Create an SQLite database with Tasks and Libraries tables."""
    db_file = os.path.join(str(tmp_path), 'test_staging.db')
    database_settings = {
        "TYPE": "SQLITE",
        "FILE": db_file,
        "MIGRATIONS_DIR": os.path.join(str(tmp_path), 'migrations'),
    }
    db_connection = Database.select_database(database_settings)
    db_connection.create_tables([Tasks, Libraries, LibraryTags, Tags])
    Libraries.create(id=1, name='TestLib', path='/tmp/test')
    yield db_connection
    db_connection.close()


def _make_scheduler_manager():
    """Create a ScheduledTasksManager with mocked dependencies."""
    with patch('compresso.libs.scheduler.CompressoLogging') as mock_log:
        mock_log.get_logger.return_value = MagicMock()
        from compresso.libs.scheduler import ScheduledTasksManager
        event = threading.Event()
        mgr = ScheduledTasksManager(event)
    return mgr


# ------------------------------------------------------------------
# TestCleanupExpiredStaging
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCleanupExpiredStaging:

    def test_disabled_when_expiry_zero(self):
        """Cleanup should be skipped when staging_expiry_days is 0."""
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = 0

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            mgr.cleanup_expired_staging()

        # Should return early without checking the staging path
        mock_settings.get_staging_path.assert_not_called()

    def test_disabled_when_expiry_negative(self):
        """Cleanup should be skipped when staging_expiry_days is negative."""
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = -1

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            mgr.cleanup_expired_staging()

        mock_settings.get_staging_path.assert_not_called()

    def test_skips_nonexistent_staging_path(self):
        """Cleanup should be skipped when staging path doesn't exist."""
        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = 7
        mock_settings.get_staging_path.return_value = '/nonexistent/path'

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            # Should not raise
            mgr.cleanup_expired_staging()

    def test_removes_expired_awaiting_approval_task(self, staging_db, tmp_path):
        """An awaiting_approval task past expiry should be deleted and staging dir removed."""
        # Create a task that finished 10 days ago
        expired_time = datetime.now() - timedelta(days=10)
        task_obj = Tasks.create(
            abspath='/tmp/test/old_video.mkv',
            status='awaiting_approval',
            finish_time=expired_time,
            library_id=1,
        )

        # Create the staging directory
        staging_dir = os.path.join(str(tmp_path), 'staging')
        task_staging = os.path.join(staging_dir, f'task_{task_obj.id}')
        os.makedirs(task_staging)
        # Create a dummy file inside
        with open(os.path.join(task_staging, 'video.mkv'), 'w') as f:
            f.write('dummy')

        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = 7
        mock_settings.get_staging_path.return_value = staging_dir

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            mgr.cleanup_expired_staging()

        # Task should be deleted from DB
        assert Tasks.get_or_none(Tasks.id == task_obj.id) is None
        # Staging directory should be removed
        assert not os.path.exists(task_staging)

    def test_preserves_fresh_awaiting_approval_task(self, staging_db, tmp_path):
        """An awaiting_approval task within the expiry window should be preserved."""
        recent_time = datetime.now() - timedelta(days=2)
        task_obj = Tasks.create(
            abspath='/tmp/test/recent_video.mkv',
            status='awaiting_approval',
            finish_time=recent_time,
            library_id=1,
        )

        staging_dir = os.path.join(str(tmp_path), 'staging')
        task_staging = os.path.join(staging_dir, f'task_{task_obj.id}')
        os.makedirs(task_staging)
        with open(os.path.join(task_staging, 'video.mkv'), 'w') as f:
            f.write('dummy')

        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = 7
        mock_settings.get_staging_path.return_value = staging_dir

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            mgr.cleanup_expired_staging()

        # Task and directory should still exist
        assert Tasks.get_or_none(Tasks.id == task_obj.id) is not None
        assert os.path.exists(task_staging)

    def test_removes_orphaned_staging_for_completed_task(self, staging_db, tmp_path):
        """A staging dir for a task that's no longer awaiting_approval should be cleaned."""
        task_obj = Tasks.create(
            abspath='/tmp/test/completed_video.mkv',
            status='pending',  # not awaiting_approval
            finish_time=datetime.now(),
            library_id=1,
        )

        staging_dir = os.path.join(str(tmp_path), 'staging')
        task_staging = os.path.join(staging_dir, f'task_{task_obj.id}')
        os.makedirs(task_staging)
        with open(os.path.join(task_staging, 'video.mkv'), 'w') as f:
            f.write('dummy')

        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = 7
        mock_settings.get_staging_path.return_value = staging_dir

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            mgr.cleanup_expired_staging()

        # Staging directory should be removed (orphaned)
        assert not os.path.exists(task_staging)
        # Task itself should NOT be deleted (only staging dir)
        assert Tasks.get_or_none(Tasks.id == task_obj.id) is not None

    def test_removes_staging_for_deleted_task(self, staging_db, tmp_path):
        """A staging dir whose task no longer exists should be cleaned."""
        staging_dir = os.path.join(str(tmp_path), 'staging')
        # Create staging dir for a task ID that doesn't exist in DB
        task_staging = os.path.join(staging_dir, 'task_99999')
        os.makedirs(task_staging)
        with open(os.path.join(task_staging, 'video.mkv'), 'w') as f:
            f.write('dummy')

        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = 7
        mock_settings.get_staging_path.return_value = staging_dir

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            mgr.cleanup_expired_staging()

        assert not os.path.exists(task_staging)

    def test_ignores_non_task_directories(self, staging_db, tmp_path):
        """Directories not matching the task_N pattern should be left alone."""
        staging_dir = os.path.join(str(tmp_path), 'staging')
        non_task_dir = os.path.join(staging_dir, 'random_folder')
        os.makedirs(non_task_dir)
        with open(os.path.join(non_task_dir, 'file.txt'), 'w') as f:
            f.write('keep me')

        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = 7
        mock_settings.get_staging_path.return_value = staging_dir

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            mgr.cleanup_expired_staging()

        # Non-task directory should be preserved
        assert os.path.exists(non_task_dir)

    def test_ignores_invalid_task_directory_names(self, staging_db, tmp_path):
        """Directories matching task_ but with invalid IDs should be skipped."""
        staging_dir = os.path.join(str(tmp_path), 'staging')
        bad_dir = os.path.join(staging_dir, 'task_notanumber')
        os.makedirs(bad_dir)

        mgr = _make_scheduler_manager()
        mock_settings = MagicMock()
        mock_settings.get_staging_expiry_days.return_value = 7
        mock_settings.get_staging_path.return_value = staging_dir

        with patch('compresso.libs.scheduler.config.Config', return_value=mock_settings):
            mgr.cleanup_expired_staging()

        # Bad directory should be preserved (skipped)
        assert os.path.exists(bad_dir)
