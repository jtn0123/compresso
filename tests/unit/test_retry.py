#!/usr/bin/env python3

"""
tests.unit.test_retry.py

Unit tests for the task retry system:
- PostProcessor._attempt_retry() exponential backoff logic
- PostProcessor._is_guardrail_rejection() detection
- TaskQueue deferred_until filtering in build_tasks_query()
- TaskQueue deferred_until filtering in build_tasks_query_full_task_list()
"""

import datetime
import os
import threading
import time
from unittest.mock import MagicMock, PropertyMock, patch

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


def _wait_for(predicate, timeout=2.0, interval=0.02):
    """Poll until predicate() returns True or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


@pytest.fixture
def task_db(tmp_path):
    """Create a SQLite database with Tasks and Libraries tables."""
    db_file = os.path.join(str(tmp_path), "test_retry.db")
    database_settings = {
        "TYPE": "SQLITE",
        "FILE": db_file,
        "MIGRATIONS_DIR": os.path.join(str(tmp_path), "migrations"),
    }
    db_connection = Database.select_database(database_settings)
    db_connection.create_tables([Tasks, Libraries, LibraryTags, Tags])
    # Create a default library
    Libraries.create(id=1, name="TestLib", path="/tmp/test")
    yield db_connection
    db_connection.close()


# ------------------------------------------------------------------
# Helper: create a PostProcessor with mocked dependencies
# ------------------------------------------------------------------


def _make_postprocessor():
    """Create a PostProcessor instance with minimal mocked dependencies."""
    with (
        patch("compresso.libs.postprocessor.CompressoLogging") as mock_log,
        patch("compresso.libs.postprocessor.config.Config") as mock_config,
    ):
        mock_log.get_logger.return_value = MagicMock()
        mock_settings = MagicMock()
        mock_settings.get_default_max_retries.return_value = 3
        mock_config.return_value = mock_settings
        from compresso.libs.postprocessor import PostProcessor

        data_queues = {}
        task_queue = MagicMock()
        event = threading.Event()
        pp = PostProcessor(data_queues, task_queue, event)
    return pp


# ------------------------------------------------------------------
# TestIsGuardrailRejection
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestIsGuardrailRejection:
    def test_returns_true_when_log_contains_rejection(self):
        pp = _make_postprocessor()
        mock_task_obj = MagicMock()
        mock_task_obj.log = "Some output\nSize guardrail REJECTED: 150.0% (allowed 10-95%)\n"
        mock_current_task = MagicMock()
        mock_current_task.task = mock_task_obj
        pp.current_task = mock_current_task
        assert pp._is_guardrail_rejection() is True

    def test_returns_false_when_log_is_empty(self):
        pp = _make_postprocessor()
        mock_task_obj = MagicMock()
        mock_task_obj.log = ""
        mock_current_task = MagicMock()
        mock_current_task.task = mock_task_obj
        pp.current_task = mock_current_task
        assert pp._is_guardrail_rejection() is False

    def test_returns_false_when_log_has_normal_failure(self):
        pp = _make_postprocessor()
        mock_task_obj = MagicMock()
        mock_task_obj.log = "RUNNER:\nCOMMAND:\nffmpeg exited with code 1\nLOG:\nOut of memory"
        mock_current_task = MagicMock()
        mock_current_task.task = mock_task_obj
        pp.current_task = mock_current_task
        assert pp._is_guardrail_rejection() is False

    def test_returns_false_when_log_is_none(self):
        pp = _make_postprocessor()
        mock_task_obj = MagicMock()
        mock_task_obj.log = None
        mock_current_task = MagicMock()
        mock_current_task.task = mock_task_obj
        pp.current_task = mock_current_task
        assert pp._is_guardrail_rejection() is False

    def test_returns_false_on_exception(self):
        pp = _make_postprocessor()
        mock_current_task = MagicMock()
        type(mock_current_task).task = PropertyMock(side_effect=Exception("no task"))
        pp.current_task = mock_current_task
        assert pp._is_guardrail_rejection() is False


# ------------------------------------------------------------------
# TestAttemptRetry — use mock task objects to avoid SqliteQueueDatabase
# async write timing issues. Verify in-memory state modifications.
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestAttemptRetry:
    def _make_mock_task(self, **kwargs):
        """Create a mock task object that behaves like a peewee model for _attempt_retry()."""
        task_obj = MagicMock()
        task_obj.retry_count = kwargs.get("retry_count", 0)
        task_obj.max_retries = kwargs.get("max_retries", 3)
        task_obj.log = kwargs.get("log", "")
        task_obj.success = kwargs.get("success", False)
        task_obj.status = kwargs.get("status", "processed")
        # Mock the _meta.database.atomic() context manager
        mock_db = MagicMock()
        mock_atomic = MagicMock()
        mock_atomic.__enter__ = MagicMock(return_value=None)
        mock_atomic.__exit__ = MagicMock(return_value=False)
        mock_db.atomic.return_value = mock_atomic
        task_obj._meta = MagicMock()
        task_obj._meta.database = mock_db
        return task_obj

    def test_retry_increments_count_and_sets_pending(self):
        """A failed task with retries remaining should go back to pending."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=0, max_retries=3, log="ffmpeg error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        with patch("compresso.libs.postprocessor.FrontendPushMessages"):
            result = pp._attempt_retry()

        assert result is True
        assert task_obj.status == "pending"
        assert task_obj.retry_count == 1
        assert task_obj.success is None
        assert task_obj.log == ""
        assert task_obj.deferred_until is not None
        task_obj.save.assert_called_once()

    def test_retry_sets_deferred_until_in_future(self):
        """The deferred_until timestamp should be in the future."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=0, max_retries=3, log="error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        before = datetime.datetime.now()
        with patch("compresso.libs.postprocessor.FrontendPushMessages"):
            pp._attempt_retry()

        assert task_obj.deferred_until > before
        # First retry: 30 * (4^0) = 30 seconds
        expected_min = before + datetime.timedelta(seconds=25)  # tolerance
        assert task_obj.deferred_until >= expected_min

    def test_retry_uses_exponential_backoff(self):
        """Second retry should use longer delay than first."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=1, max_retries=3, log="disk full")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        before = datetime.datetime.now()
        with patch("compresso.libs.postprocessor.FrontendPushMessages"):
            result = pp._attempt_retry()

        assert result is True
        assert task_obj.retry_count == 2
        # Second retry: 30 * (4^1) = 120 seconds = 2 minutes
        expected_min = before + datetime.timedelta(seconds=115)
        assert task_obj.deferred_until >= expected_min

    def test_third_retry_backoff_is_8_minutes(self):
        """Third retry should defer for ~8 minutes."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=2, max_retries=3, log="error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        before = datetime.datetime.now()
        with patch("compresso.libs.postprocessor.FrontendPushMessages"):
            result = pp._attempt_retry()

        assert result is True
        assert task_obj.retry_count == 3
        # Third retry: 30 * (4^2) = 480 seconds = 8 minutes
        expected_min = before + datetime.timedelta(seconds=475)
        assert task_obj.deferred_until >= expected_min

    def test_no_retry_when_max_reached(self):
        """A task at max retries should not be retried."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=3, max_retries=3, log="error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        result = pp._attempt_retry()

        assert result is False
        assert task_obj.status == "processed"  # unchanged
        assert task_obj.retry_count == 3  # unchanged
        task_obj.save.assert_not_called()

    def test_no_retry_for_guardrail_rejection(self):
        """Guardrail rejections should not be retried."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=0, max_retries=3, log="Size guardrail REJECTED: 150.0% (allowed 10-95%)")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        result = pp._attempt_retry()

        assert result is False
        task_obj.save.assert_not_called()

    def test_retry_cleans_up_cache(self):
        """Cache files should be cleaned up on retry."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=0, max_retries=3, log="error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = "/tmp/cache/compresso_file_conversion_abc/video.mkv"
        pp.current_task = mock_current_task

        with (
            patch.object(pp, "_PostProcessor__cleanup_cache_files") as mock_cleanup,
            patch("compresso.libs.postprocessor.FrontendPushMessages"),
        ):
            result = pp._attempt_retry()

        assert result is True
        mock_cleanup.assert_called_once_with("/tmp/cache/compresso_file_conversion_abc/video.mkv")

    def test_retry_does_not_clean_when_no_cache(self):
        """No cache cleanup when cache_path is None."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=0, max_retries=3, log="error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        with (
            patch.object(pp, "_PostProcessor__cleanup_cache_files") as mock_cleanup,
            patch("compresso.libs.postprocessor.FrontendPushMessages"),
        ):
            pp._attempt_retry()

        mock_cleanup.assert_not_called()

    def test_retry_pushes_frontend_notification(self):
        """Retry should push a warning notification to FrontendPushMessages."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=0, max_retries=3, log="error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video6.mkv"
        mock_current_task.get_task_id.return_value = 42
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        with patch("compresso.libs.postprocessor.FrontendPushMessages") as MockFPM:
            mock_fpm = MagicMock()
            MockFPM.return_value = mock_fpm
            pp._attempt_retry()

        mock_fpm.update.assert_called_once()
        call_args = mock_fpm.update.call_args[0][0]
        assert call_args["type"] == "warning"
        assert call_args["code"] == "taskRetrying"
        assert call_args["id"] == "taskRetry_42"
        assert "video6.mkv" in call_args["message"]
        assert "attempt 1/3" in call_args["message"]
        assert call_args["timeout"] == 15000

    def test_retry_uses_config_max_when_task_has_none(self):
        """When task.max_retries is None, fall back to config default."""
        pp = _make_postprocessor()
        pp.settings.get_default_max_retries.return_value = 5
        task_obj = self._make_mock_task(retry_count=0, max_retries=None, log="error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        with patch("compresso.libs.postprocessor.FrontendPushMessages"):
            result = pp._attempt_retry()

        assert result is True
        assert task_obj.retry_count == 1
        task_obj.save.assert_called_once()

    def test_retry_uses_config_max_when_task_has_zero(self):
        """When task.max_retries is 0 (falsy), fall back to config default."""
        pp = _make_postprocessor()
        pp.settings.get_default_max_retries.return_value = 3
        task_obj = self._make_mock_task(retry_count=0, max_retries=0, log="error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_task_id.return_value = 1
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        with patch("compresso.libs.postprocessor.FrontendPushMessages"):
            result = pp._attempt_retry()

        assert result is True

    def test_exception_in_retry_returns_false(self):
        """If retry logic throws, it should catch the exception and return False."""
        pp = _make_postprocessor()
        task_obj = self._make_mock_task(retry_count=0, max_retries=3, log="error")
        # Make _meta.database.atomic() raise
        task_obj._meta.database.atomic.side_effect = Exception("DB error")

        mock_current_task = MagicMock()
        mock_current_task.task = task_obj
        mock_current_task.get_source_abspath.return_value = "/tmp/test/video.mkv"
        mock_current_task.get_cache_path.return_value = None
        pp.current_task = mock_current_task

        result = pp._attempt_retry()
        assert result is False


# ------------------------------------------------------------------
# TestDeferredFiltering — uses real DB for query tests
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestDeferredFiltering:
    def test_build_tasks_query_excludes_deferred_tasks(self, task_db):
        """Tasks with deferred_until in the future should be excluded from the query."""
        from compresso.libs.taskqueue import build_tasks_query

        future = datetime.datetime.now() + datetime.timedelta(hours=1)
        Tasks.create(
            abspath="/tmp/test/deferred.mkv",
            status="pending",
            retry_count=1,
            deferred_until=future,
            library_id=1,
        )
        Tasks.create(
            abspath="/tmp/test/ready.mkv",
            status="pending",
            retry_count=0,
            deferred_until=None,
            library_id=1,
        )
        # Wait for SqliteQueueDatabase to process writes
        assert _wait_for(lambda: build_tasks_query("pending", sort_by=Tasks.id) is not None)

        result = build_tasks_query("pending", sort_by=Tasks.id)
        assert result.abspath == "/tmp/test/ready.mkv"

    def test_build_tasks_query_includes_expired_deferred_tasks(self, task_db):
        """Tasks with deferred_until in the past should be included."""
        from compresso.libs.taskqueue import build_tasks_query

        past = datetime.datetime.now() - datetime.timedelta(minutes=5)
        Tasks.create(
            abspath="/tmp/test/expired_deferred.mkv",
            status="pending",
            retry_count=1,
            deferred_until=past,
            library_id=1,
        )
        assert _wait_for(lambda: build_tasks_query("pending", sort_by=Tasks.id) is not None)

        result = build_tasks_query("pending", sort_by=Tasks.id)
        assert result.abspath == "/tmp/test/expired_deferred.mkv"

    def test_build_tasks_query_includes_null_deferred(self, task_db):
        """Tasks with deferred_until=None should always be included."""
        from compresso.libs.taskqueue import build_tasks_query

        Tasks.create(
            abspath="/tmp/test/normal.mkv",
            status="pending",
            deferred_until=None,
            library_id=1,
        )
        assert _wait_for(lambda: build_tasks_query("pending", sort_by=Tasks.id) is not None)

        result = build_tasks_query("pending", sort_by=Tasks.id)
        assert result.abspath == "/tmp/test/normal.mkv"

    def test_build_tasks_query_full_list_excludes_deferred(self, task_db):
        """build_tasks_query_full_task_list should also exclude deferred tasks."""
        from compresso.libs.taskqueue import build_tasks_query_full_task_list

        future = datetime.datetime.now() + datetime.timedelta(hours=1)
        Tasks.create(
            abspath="/tmp/test/deferred_list.mkv",
            status="pending",
            retry_count=1,
            deferred_until=future,
            library_id=1,
        )
        Tasks.create(
            abspath="/tmp/test/ready_list.mkv",
            status="pending",
            retry_count=0,
            deferred_until=None,
            library_id=1,
        )
        # Wait until the non-deferred task is visible in the full list
        assert _wait_for(
            lambda: any(
                r["abspath"] == "/tmp/test/ready_list.mkv"
                for r in build_tasks_query_full_task_list("pending", sort_by=Tasks.id)
            )
        )

        results = list(build_tasks_query_full_task_list("pending", sort_by=Tasks.id))
        abspaths = [r["abspath"] for r in results]
        assert "/tmp/test/ready_list.mkv" in abspaths
        assert "/tmp/test/deferred_list.mkv" not in abspaths

    def test_build_tasks_query_returns_none_when_all_deferred(self, task_db):
        """When all pending tasks are deferred, the query should return None."""
        from compresso.libs.taskqueue import build_tasks_query

        future = datetime.datetime.now() + datetime.timedelta(hours=1)
        Tasks.create(
            abspath="/tmp/test/all_deferred.mkv",
            status="pending",
            retry_count=1,
            deferred_until=future,
            library_id=1,
        )
        # Wait until the task record exists in DB (even though deferred, verify write completed)
        assert _wait_for(lambda: Tasks.select().where(Tasks.abspath == "/tmp/test/all_deferred.mkv").count() > 0)

        result = build_tasks_query("pending", sort_by=Tasks.id)
        assert result is None
