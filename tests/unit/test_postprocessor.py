#!/usr/bin/env python3

"""
tests.unit.test_postprocessor.py

Unit tests for compresso.libs.postprocessor.PostProcessor.

"""

import os
import shutil
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest


def _make_postprocessor(abort_immediately=False):
    """Create a PostProcessor with mocked dependencies."""
    with (
        patch("compresso.libs.postprocessor.config.Config"),
        patch("compresso.libs.postprocessor.CompressoLogging") as mock_logging,
    ):
        mock_logger = MagicMock()
        mock_logging.get_logger.return_value = mock_logger

        from compresso.libs.postprocessor import PostProcessor

        data_queues = {}
        task_queue = MagicMock()
        event = threading.Event()
        pp = PostProcessor(data_queues, task_queue, event)
        if abort_immediately:
            pp.abort_flag.set()
        return pp


# ------------------------------------------------------------------
# TestSystemConfigurationIsValid
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestSystemConfigurationIsValid:
    """Tests for PostProcessor.system_configuration_is_valid()."""

    @patch("compresso.libs.postprocessor.PluginsHandler")
    def test_valid_when_no_incompatible_plugins(self, mock_ph_class):
        mock_ph = MagicMock()
        mock_ph.get_incompatible_enabled_plugins.return_value = []
        mock_ph_class.return_value = mock_ph

        pp = _make_postprocessor()
        assert pp.system_configuration_is_valid() is True

    @patch("compresso.libs.postprocessor.PluginsHandler")
    def test_invalid_when_incompatible_plugins(self, mock_ph_class):
        mock_ph = MagicMock()
        mock_ph.get_incompatible_enabled_plugins.return_value = ["bad_plugin"]
        mock_ph_class.return_value = mock_ph

        pp = _make_postprocessor()
        assert pp.system_configuration_is_valid() is False


# ------------------------------------------------------------------
# TestCopyFile
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestCopyFile:
    """Tests for PostProcessor.__copy_file() using real temp files."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="compresso_test_copy_")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_file(self, name, content=b"test content"):
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_copy_file_creates_destination(self):
        pp = _make_postprocessor()
        src = self._make_file("source.mkv", b"video data")
        dst = os.path.join(self.tmpdir, "dest.mkv")
        dest_files = []

        result = pp._PostProcessor__copy_file(src, dst, dest_files, "test_plugin", move=False)
        assert result is True
        assert os.path.exists(dst)
        assert os.path.exists(src)  # source still exists (copy, not move)
        assert dst in dest_files

    def test_move_file_removes_source(self):
        pp = _make_postprocessor()
        src = self._make_file("source.mkv", b"video data")
        dst = os.path.join(self.tmpdir, "dest.mkv")
        dest_files = []

        result = pp._PostProcessor__copy_file(src, dst, dest_files, "test_plugin", move=True)
        assert result is True
        assert os.path.exists(dst)
        assert not os.path.exists(src)  # source removed (move)
        assert dst in dest_files

    def test_same_file_returns_false(self):
        pp = _make_postprocessor()
        src = self._make_file("same.mkv", b"data")
        dest_files = []

        result = pp._PostProcessor__copy_file(src, src, dest_files, "test_plugin")
        assert result is False
        assert len(dest_files) == 0

    def test_missing_source_returns_false(self):
        pp = _make_postprocessor()
        src = os.path.join(self.tmpdir, "nonexistent.mkv")
        dst = os.path.join(self.tmpdir, "dest.mkv")
        dest_files = []

        # The method waits 1 second then tries to copy; will fail
        result = pp._PostProcessor__copy_file(src, dst, dest_files, "test_plugin")
        assert result is False


# ------------------------------------------------------------------
# TestFileOperationTracker
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestFileOperationTracker:
    """Tests for the FileOperationTracker rollback helper."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="compresso_test_tracker_")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_file(self, name, content=b"test content"):
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def _make_tracker(self):
        import logging

        from compresso.libs.postprocessor import FileOperationTracker

        logger = logging.getLogger("test_tracker")
        return FileOperationTracker(logger)

    def test_safe_remove_creates_backup_and_removes_file(self):
        tracker = self._make_tracker()
        path = self._make_file("original.mkv", b"important data")

        tracker.safe_remove(path)

        assert not os.path.exists(path)
        assert os.path.exists(path + ".compresso.bak")

    def test_commit_removes_backups(self):
        tracker = self._make_tracker()
        path = self._make_file("original.mkv", b"data")

        tracker.safe_remove(path)
        assert os.path.exists(path + ".compresso.bak")

        tracker.commit()
        assert not os.path.exists(path + ".compresso.bak")

    def test_rollback_restores_files(self):
        tracker = self._make_tracker()
        content = b"very important data"
        path = self._make_file("original.mkv", content)

        tracker.safe_remove(path)
        assert not os.path.exists(path)

        tracker.rollback()
        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert f.read() == content

    def test_rollback_clears_backup_list(self):
        tracker = self._make_tracker()
        path = self._make_file("file.mkv", b"data")

        tracker.safe_remove(path)
        tracker.rollback()

        # Rolling back again should be a no-op (list is cleared)
        tracker.rollback()
        assert os.path.exists(path)

    def test_commit_clears_backup_list(self):
        tracker = self._make_tracker()
        path = self._make_file("file.mkv", b"data")

        tracker.safe_remove(path)
        tracker.commit()

        # Committing again should be a no-op
        tracker.commit()

    def test_safe_remove_nonexistent_file_is_noop(self):
        tracker = self._make_tracker()
        path = os.path.join(self.tmpdir, "nonexistent.mkv")

        # Should not raise
        tracker.safe_remove(path)

    def test_multiple_files_rolled_back_in_reverse(self):
        tracker = self._make_tracker()
        a = self._make_file("a.mkv", b"aaa")
        b = self._make_file("b.mkv", b"bbb")

        tracker.safe_remove(a)
        tracker.safe_remove(b)

        assert not os.path.exists(a)
        assert not os.path.exists(b)

        tracker.rollback()

        assert os.path.exists(a)
        assert os.path.exists(b)
        with open(a, "rb") as f:
            assert f.read() == b"aaa"
        with open(b, "rb") as f:
            assert f.read() == b"bbb"

    def test_multiple_files_committed(self):
        tracker = self._make_tracker()
        a = self._make_file("a.mkv", b"aaa")
        b = self._make_file("b.mkv", b"bbb")

        tracker.safe_remove(a)
        tracker.safe_remove(b)
        tracker.commit()

        assert not os.path.exists(a)
        assert not os.path.exists(b)
        assert not os.path.exists(a + ".compresso.bak")
        assert not os.path.exists(b + ".compresso.bak")


# ------------------------------------------------------------------
# TestCopyFileWithTracker
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestCopyFileWithTracker:
    """Tests for PostProcessor.__copy_file() with tracker parameter."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="compresso_test_copy_tracker_")

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_file(self, name, content=b"test content"):
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def _make_tracker(self):
        import logging

        from compresso.libs.postprocessor import FileOperationTracker

        logger = logging.getLogger("test_tracker")
        return FileOperationTracker(logger)

    def test_copy_with_tracker_backs_up_destination(self):
        """When tracker is provided and destination exists, it should be backed up."""
        pp = _make_postprocessor()
        tracker = self._make_tracker()

        existing_content = b"original destination"
        src = self._make_file("new_source.mkv", b"new data")
        dst = self._make_file("dest.mkv", existing_content)
        dest_files = []

        result = pp._PostProcessor__copy_file(src, dst, dest_files, "test", move=True, tracker=tracker)
        assert result is True
        assert os.path.exists(dst)
        # Backup should exist until commit
        assert os.path.exists(dst + ".compresso.bak")
        with open(dst + ".compresso.bak", "rb") as f:
            assert f.read() == existing_content

        tracker.commit()
        assert not os.path.exists(dst + ".compresso.bak")

    def test_copy_without_tracker_no_backup(self):
        """When no tracker is provided, no backup should be created."""
        pp = _make_postprocessor()

        src = self._make_file("source.mkv", b"new data")
        dst = self._make_file("dest.mkv", b"old data")
        dest_files = []

        result = pp._PostProcessor__copy_file(src, dst, dest_files, "test", move=True)
        assert result is True
        assert not os.path.exists(dst + ".compresso.bak")


# ------------------------------------------------------------------
# TestCleanupCacheFiles
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestCleanupCacheFiles:
    """Tests for PostProcessor.__cleanup_cache_files()."""

    def test_removes_directory_with_compresso_file_conversion_in_path(self):
        tmpdir = tempfile.mkdtemp(prefix="compresso_file_conversion_test_")
        cache_file = os.path.join(tmpdir, "output.mkv")
        with open(cache_file, "w") as f:
            f.write("test")

        pp = _make_postprocessor()
        pp._PostProcessor__cleanup_cache_files(cache_file)
        assert not os.path.exists(tmpdir)

    def test_does_not_remove_directory_without_marker(self):
        tmpdir = tempfile.mkdtemp(prefix="safe_dir_")
        cache_file = os.path.join(tmpdir, "output.mkv")
        with open(cache_file, "w") as f:
            f.write("test")

        pp = _make_postprocessor()
        pp._PostProcessor__cleanup_cache_files(cache_file)
        assert os.path.exists(tmpdir)
        shutil.rmtree(tmpdir, ignore_errors=True)


# ------------------------------------------------------------------
# TestWriteHistoryLog
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestWriteHistoryLog:
    """Tests for PostProcessor.write_history_log()."""

    @patch("compresso.libs.postprocessor.PluginsHandler")
    @patch("compresso.libs.postprocessor.extract_media_metadata", return_value={})
    @patch("compresso.libs.postprocessor.os.path.exists", return_value=False)
    @patch("compresso.libs.postprocessor.os.path.getsize", return_value=0)
    @patch("compresso.libs.postprocessor.CompressoLogging")
    @patch("compresso.libs.postprocessor.history.History")
    def test_successful_task_saves_history(
        self, mock_history_class, mock_logging_class, mock_getsize, mock_exists, mock_extract, mock_ph
    ):
        pp = _make_postprocessor()

        mock_task = MagicMock()
        mock_task.task_dump.return_value = {
            "task_label": "test.mkv",
            "abspath": "/test/test.mkv",
            "task_success": True,
            "start_time": "2024-01-01 00:00:00",
            "finish_time": "2024-01-01 00:01:00",
            "processed_by_worker": "worker-0",
            "log": "",
            "source_size": 1000,
            "library_id": 1,
        }
        mock_task.task.success = True
        mock_task.get_destination_data.return_value = {"abspath": "/test/test.mkv", "basename": "test.mkv"}
        mock_task.get_source_data.return_value = {"abspath": "/test/test.mkv", "basename": "test.mkv"}
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = "task-1"
        mock_task.get_task_type.return_value = "local"
        pp.current_task = mock_task

        mock_history = MagicMock()
        mock_history_class.return_value = mock_history
        mock_logging_class.log_data = MagicMock()

        pp.write_history_log()

        mock_history.save_task_history.assert_called_once()
        call_args = mock_history.save_task_history.call_args[0][0]
        assert call_args["task_label"] == "test.mkv"
        assert call_args["task_success"] is True

    @patch("compresso.libs.postprocessor.PluginsHandler")
    @patch("compresso.libs.postprocessor.extract_media_metadata", return_value={})
    @patch("compresso.libs.postprocessor.os.path.exists", return_value=False)
    @patch("compresso.libs.postprocessor.CompressoLogging")
    @patch("compresso.libs.postprocessor.Notifications")
    @patch("compresso.libs.postprocessor.history.History")
    def test_failed_task_creates_notification(
        self, mock_history_class, mock_notif_class, mock_logging_class, mock_exists, mock_extract, mock_ph
    ):
        pp = _make_postprocessor()

        mock_task = MagicMock()
        mock_task.task_dump.return_value = {
            "task_label": "fail.mkv",
            "abspath": "/test/fail.mkv",
            "task_success": False,
            "start_time": "",
            "finish_time": "",
            "processed_by_worker": "",
            "log": "error occurred",
            "source_size": 0,
            "library_id": 1,
        }
        mock_task.task.success = False
        mock_task.get_destination_data.return_value = {"abspath": "/test/fail.mkv", "basename": "fail.mkv"}
        mock_task.get_source_data.return_value = {"abspath": "/test/fail.mkv", "basename": "fail.mkv"}
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = "task-2"
        mock_task.get_task_type.return_value = "local"
        pp.current_task = mock_task

        mock_history_class.return_value = MagicMock()
        mock_logging_class.log_data = MagicMock()
        mock_notif = MagicMock()
        mock_notif_class.return_value = mock_notif

        pp.write_history_log()

        mock_notif.add.assert_called_once()
        notif_data = mock_notif.add.call_args[0][0]
        assert notif_data["type"] == "error"


# ------------------------------------------------------------------
# TestCommitTaskMetadata
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestCommitTaskMetadata:
    """Tests for PostProcessor.commit_task_metadata()."""

    @patch("compresso.libs.postprocessor.CompressoFileMetadata")
    def test_commits_metadata(self, mock_meta_class):
        pp = _make_postprocessor()

        mock_task = MagicMock()
        mock_task.get_source_data.return_value = {"abspath": "/test/src.mkv"}
        mock_task.get_destination_data.return_value = {"abspath": "/test/dst.mkv"}
        mock_task.get_task_success.return_value = True
        mock_task.get_task_id.return_value = "task-1"
        pp.current_task = mock_task
        pp._last_destination_files = ["/test/dst.mkv"]

        mock_meta_class.commit_task.return_value = 1

        result = pp.commit_task_metadata()
        assert result == 1
        mock_meta_class.commit_task.assert_called_once_with(
            task_id="task-1",
            task_success=True,
            source_path="/test/src.mkv",
            destination_paths=["/test/dst.mkv"],
        )


# ------------------------------------------------------------------
# TestLogCompletedTaskData
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestLogCompletedTaskData:
    """Tests for PostProcessor._log_completed_task_data()."""

    @patch("compresso.libs.postprocessor.CompressoLogging")
    def test_logs_success_status(self, mock_logging_class):
        pp = _make_postprocessor()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_library_name.return_value = "Movies"
        mock_task.get_task_id.return_value = "task-1"
        mock_task.get_task_type.return_value = "local"
        pp.current_task = mock_task

        mock_logging_class.log_data = MagicMock()

        task_dump = {"task_success": True, "start_time": "t1", "finish_time": "t2", "log": ""}
        source_data = {"abspath": "/src.mkv", "basename": "src.mkv"}
        dest_data = {"abspath": "/dst.mkv", "basename": "dst.mkv"}

        pp._log_completed_task_data(task_dump, source_data, dest_data)

        mock_logging_class.log_data.assert_called_once()
        call_kwargs = mock_logging_class.log_data.call_args
        assert call_kwargs[1]["status"] == "success"

    @patch("compresso.libs.postprocessor.CompressoLogging")
    def test_logs_failed_status(self, mock_logging_class):
        pp = _make_postprocessor()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_library_name.return_value = "Movies"
        mock_task.get_task_id.return_value = "task-1"
        mock_task.get_task_type.return_value = "local"
        pp.current_task = mock_task

        mock_logging_class.log_data = MagicMock()

        task_dump = {"task_success": False, "start_time": "t1", "finish_time": "t2", "log": "error line\nanother"}
        source_data = {"abspath": "/src.mkv", "basename": "src.mkv"}
        dest_data = {"abspath": "/dst.mkv", "basename": "dst.mkv"}

        pp._log_completed_task_data(task_dump, source_data, dest_data)

        call_kwargs = mock_logging_class.log_data.call_args
        assert call_kwargs[1]["status"] == "failed"


# ------------------------------------------------------------------
# TestDumpHistoryLog
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestDumpHistoryLog:
    """Tests for PostProcessor.dump_history_log()."""

    @patch("compresso.libs.postprocessor.common.json_dump_to_file")
    @patch("compresso.libs.postprocessor.TaskDataStore.export_task_state", return_value={})
    def test_dumps_to_file(self, mock_export, mock_json_dump):
        pp = _make_postprocessor()

        mock_task = MagicMock()
        mock_task.task_dump.return_value = {
            "task_label": "remote.mkv",
            "abspath": "/remote/remote.mkv",
            "task_success": True,
            "start_time": "",
            "finish_time": "",
            "processed_by_worker": "",
            "log": "",
        }
        mock_task.get_destination_data.return_value = {"abspath": "/cache/output/remote.mkv"}
        mock_task.get_task_id.return_value = "task-r1"
        pp.current_task = mock_task

        mock_json_dump.return_value = {"success": True, "errors": []}

        pp.dump_history_log()

        mock_json_dump.assert_called_once()
        call_args = mock_json_dump.call_args[0]
        assert call_args[0]["task_label"] == "remote.mkv"
        assert "data.json" in call_args[1]

    @patch("compresso.libs.postprocessor.common.json_dump_to_file")
    @patch("compresso.libs.postprocessor.TaskDataStore.export_task_state", return_value={})
    def test_raises_on_failure(self, mock_export, mock_json_dump):
        pp = _make_postprocessor()

        mock_task = MagicMock()
        mock_task.task_dump.return_value = {
            "task_label": "remote.mkv",
            "abspath": "/remote/remote.mkv",
            "task_success": False,
            "start_time": "",
            "finish_time": "",
            "processed_by_worker": "",
            "log": "",
        }
        mock_task.get_destination_data.return_value = {"abspath": "/cache/output/remote.mkv"}
        mock_task.get_task_id.return_value = "task-r2"
        pp.current_task = mock_task

        mock_json_dump.return_value = {"success": False, "errors": ["write failed"]}

        with pytest.raises(Exception, match="Exception in dumping"):
            pp.dump_history_log()


# ------------------------------------------------------------------
# TestRunLoopAbort
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestRunLoopAbort:
    """Tests for PostProcessor.run() abort behavior."""

    def test_stop_causes_run_to_exit(self):
        pp = _make_postprocessor(abort_immediately=True)
        # run() should exit immediately since abort_flag is already set
        pp.run()
        # If we get here, the loop exited properly


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
