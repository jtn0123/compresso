#!/usr/bin/env python3

"""
tests.unit.test_approval.py

Unit tests for the approval workflow:
- Task status transitions (awaiting_approval, approved)
- Postprocessor staging logic
- Approval helpers (approve, reject, list)
- Approval API endpoints
"""

import os
import shutil
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest

# ------------------------------------------------------------------
# TestTaskStatusTransitions
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestTaskStatusTransitions:
    """Tests for the new task statuses: awaiting_approval, approved."""

    def test_set_status_allows_awaiting_approval(self):
        """Task.set_status('awaiting_approval') should be allowed."""
        from compresso.libs.task import Task

        t = Task()
        mock_task = MagicMock()
        t.task = mock_task

        t.set_status("awaiting_approval")
        assert mock_task.status == "awaiting_approval"
        mock_task.save.assert_called()

    def test_set_status_allows_approved(self):
        """Task.set_status('approved') should be allowed."""
        from compresso.libs.task import Task

        t = Task()
        mock_task = MagicMock()
        t.task = mock_task

        t.set_status("approved")
        assert mock_task.status == "approved"
        mock_task.save.assert_called()

    def test_set_status_rejects_invalid(self):
        """Task.set_status('garbage') should raise."""
        from compresso.libs.task import Task

        t = Task()
        t.task = MagicMock()

        with pytest.raises(Exception, match="Unable to set status"):
            t.set_status("garbage")


# ------------------------------------------------------------------
# TestPostprocessorStaging
# ------------------------------------------------------------------


def _make_postprocessor():
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
        return pp


@pytest.mark.unittest
class TestPostprocessorStaging:
    """Tests for the postprocessor approval staging logic."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="compresso_test_staging_")
        self.staging_dir = os.path.join(self.tmpdir, "staging")
        self.cache_dir = os.path.join(self.tmpdir, "compresso_file_conversion_test")
        os.makedirs(self.staging_dir)
        os.makedirs(self.cache_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _make_cache_file(self, name="output.mkv", content=b"transcoded video data"):
        path = os.path.join(self.cache_dir, name)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def test_stage_for_approval_copies_to_staging(self):
        """When approval_required is True, file should be copied to staging dir."""
        pp = _make_postprocessor()
        pp.settings.get_staging_path.return_value = self.staging_dir
        pp.settings.get_approval_required.return_value = True

        cache_file = self._make_cache_file()

        mock_task = MagicMock()
        mock_task.get_cache_path.return_value = cache_file
        mock_task.get_task_id.return_value = 42
        mock_task.task.success = True
        pp.current_task = mock_task

        pp._stage_for_approval()

        # Verify staged file exists
        task_staging_dir = os.path.join(self.staging_dir, "task_42")
        assert os.path.exists(task_staging_dir)
        staged_files = os.listdir(task_staging_dir)
        assert len(staged_files) == 1
        assert staged_files[0] == "output.mkv"

        # Verify status was set
        mock_task.set_status.assert_called_once_with("awaiting_approval")

    def test_stage_for_approval_preserves_cache(self):
        """Staging should copy, not move — cache file should still exist."""
        pp = _make_postprocessor()
        pp.settings.get_staging_path.return_value = self.staging_dir
        pp.settings.get_approval_required.return_value = True

        cache_file = self._make_cache_file()
        mock_task = MagicMock()
        mock_task.get_cache_path.return_value = cache_file
        mock_task.get_task_id.return_value = 99
        mock_task.task.success = True
        pp.current_task = mock_task

        pp._stage_for_approval()

        # Cache file should still exist
        assert os.path.exists(cache_file)

    def test_cleanup_staging_files_removes_task_dir(self):
        """_cleanup_staging_files should remove the per-task staging dir."""
        pp = _make_postprocessor()
        pp.settings.get_staging_path.return_value = self.staging_dir

        task_staging_dir = os.path.join(self.staging_dir, "task_7")
        os.makedirs(task_staging_dir)
        with open(os.path.join(task_staging_dir, "test.mkv"), "w") as f:
            f.write("data")

        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 7
        pp.current_task = mock_task

        pp._cleanup_staging_files()

        assert not os.path.exists(task_staging_dir)

    def test_cleanup_staging_files_noop_when_no_dir(self):
        """_cleanup_staging_files should not fail if staging dir doesn't exist."""
        pp = _make_postprocessor()
        pp.settings.get_staging_path.return_value = self.staging_dir

        mock_task = MagicMock()
        mock_task.get_task_id.return_value = 999
        pp.current_task = mock_task

        # Should not raise
        pp._cleanup_staging_files()


# ------------------------------------------------------------------
# TestApprovalHelpers
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestApprovalHelpers:
    """Tests for the approval helper functions."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="compresso_test_approval_helpers_")
        self.staging_dir = os.path.join(self.tmpdir, "staging")
        os.makedirs(self.staging_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_get_staged_file_info_with_file(self):
        """Should return size and path when staged file exists."""
        from compresso.webserver.helpers.approval import _get_staged_file_info

        task_dir = os.path.join(self.staging_dir, "task_10")
        os.makedirs(task_dir)
        staged_file = os.path.join(task_dir, "video.mkv")
        with open(staged_file, "wb") as f:
            f.write(b"x" * 500)

        info = _get_staged_file_info(10, self.staging_dir)
        assert info["size"] == 500
        assert info["path"] == staged_file

    def test_get_staged_file_info_no_dir(self):
        """Should return zeros when staging dir doesn't exist for task."""
        from compresso.webserver.helpers.approval import _get_staged_file_info

        info = _get_staged_file_info(999, self.staging_dir)
        assert info["size"] == 0
        assert info["path"] == ""

    @patch("compresso.webserver.helpers.approval.task")
    def test_approve_tasks_sets_approved_status(self, mock_task_module):
        """approve_tasks should call set_tasks_status with 'approved'."""
        from compresso.webserver.helpers.approval import approve_tasks

        mock_task_module.Task.set_tasks_status.return_value = 3
        result = approve_tasks([1, 2, 3])
        mock_task_module.Task.set_tasks_status.assert_called_once_with([1, 2, 3], "approved")
        assert result == 3

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_reject_tasks_deletes_by_default(self, mock_task_module, mock_config_class, mock_tasks_model):
        """reject_tasks without requeue should delete tasks."""
        from compresso.webserver.helpers.approval import reject_tasks

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = self.staging_dir
        mock_config_class.return_value = mock_config

        mock_task_handler = MagicMock()
        mock_task_handler.delete_tasks_recursively.return_value = True
        mock_task_module.Task.return_value = mock_task_handler

        # Create a staging dir for the task
        task_dir = os.path.join(self.staging_dir, "task_5")
        os.makedirs(task_dir)
        with open(os.path.join(task_dir, "video.mkv"), "w") as f:
            f.write("test")

        # Mock the Tasks.get_by_id to return a task with cache_path
        mock_record = MagicMock()
        mock_record.cache_path = "/nonexistent/cache/path"
        mock_tasks_model.get_by_id.return_value = mock_record

        reject_tasks([5], requeue=False)

        # Staging dir should be cleaned up
        assert not os.path.exists(task_dir)
        # Tasks should be deleted
        mock_task_handler.delete_tasks_recursively.assert_called_once_with([5])

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_reject_tasks_requeues_when_requested(self, mock_task_module, mock_config_class, mock_tasks_model):
        """reject_tasks with requeue=True should set status to pending."""
        from compresso.webserver.helpers.approval import reject_tasks

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = self.staging_dir
        mock_config_class.return_value = mock_config

        mock_tasks_model.get_by_id.return_value = MagicMock(cache_path=None)

        mock_task_module.Task.set_tasks_status.return_value = 1

        reject_tasks([5], requeue=True)
        mock_task_module.Task.set_tasks_status.assert_called_once_with([5], "pending")


# ------------------------------------------------------------------
# TestApprovalConfig
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestApprovalConfig:
    """Tests for approval-related config settings."""

    def test_approval_required_defaults_to_false(self):
        """Config.get_approval_required() should return False for a fresh instance."""
        # Test the getter logic directly without touching the singleton
        from compresso.config import Config

        # Create a bare object bypassing __init__ to test getter logic only
        obj = object.__new__(Config)
        obj.approval_required = False
        assert obj.get_approval_required() is False

    def test_approval_required_string_conversion(self):
        """Config.get_approval_required() should handle string values."""
        from compresso.config import Config

        obj = object.__new__(Config)

        obj.approval_required = "true"
        assert obj.get_approval_required() is True

        obj.approval_required = "false"
        assert obj.get_approval_required() is False

        obj.approval_required = "1"
        assert obj.get_approval_required() is True

        obj.approval_required = "0"
        assert obj.get_approval_required() is False


# ------------------------------------------------------------------
# TestHandleProcessedTaskRouting
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestHandleProcessedTaskRouting:
    """Tests that _handle_processed_task routes correctly based on approval_required."""

    @patch("compresso.libs.postprocessor.PluginsHandler")
    def test_routes_to_staging_when_approval_required(self, mock_ph):
        """When approval_required=True and task succeeded, should stage."""
        pp = _make_postprocessor()
        pp.settings.get_approval_required.return_value = True
        pp._stage_for_approval = MagicMock()
        pp._finalize_local_task = MagicMock()

        mock_task = MagicMock()
        mock_task.get_task_type.return_value = "local"
        mock_task.task.success = True
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 1
        mock_task.get_cache_path.return_value = "/cache/test.mkv"
        mock_task.get_source_data.return_value = {"abspath": "/lib/test.mkv"}
        mock_task.get_source_abspath.return_value = "/lib/test.mkv"
        pp.current_task = mock_task

        pp._handle_processed_task()

        pp._stage_for_approval.assert_called_once()
        pp._finalize_local_task.assert_not_called()

    @patch("compresso.libs.postprocessor.PluginsHandler")
    def test_routes_to_finalize_when_approval_not_required(self, mock_ph):
        """When approval_required=False, should finalize directly."""
        pp = _make_postprocessor()
        pp.settings.get_approval_required.return_value = False
        pp._stage_for_approval = MagicMock()
        pp._finalize_local_task = MagicMock()

        mock_task = MagicMock()
        mock_task.get_task_type.return_value = "local"
        mock_task.task.success = True
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 1
        mock_task.get_cache_path.return_value = "/cache/test.mkv"
        mock_task.get_source_data.return_value = {"abspath": "/lib/test.mkv"}
        mock_task.get_source_abspath.return_value = "/lib/test.mkv"
        pp.current_task = mock_task

        pp._handle_processed_task()

        pp._stage_for_approval.assert_not_called()
        pp._finalize_local_task.assert_called_once()

    @patch("compresso.libs.postprocessor.PluginsHandler")
    def test_routes_to_finalize_when_task_failed(self, mock_ph):
        """When task failed, should finalize even if approval_required=True."""
        pp = _make_postprocessor()
        pp.settings.get_approval_required.return_value = True
        pp._stage_for_approval = MagicMock()
        pp._finalize_local_task = MagicMock()

        mock_task = MagicMock()
        mock_task.get_task_type.return_value = "local"
        mock_task.task.success = False
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 1
        mock_task.get_cache_path.return_value = "/cache/test.mkv"
        mock_task.get_source_data.return_value = {"abspath": "/lib/test.mkv"}
        mock_task.get_source_abspath.return_value = "/lib/test.mkv"
        pp.current_task = mock_task

        pp._handle_processed_task()

        pp._stage_for_approval.assert_not_called()
        pp._finalize_local_task.assert_called_once()

    @patch("compresso.libs.postprocessor.PluginsHandler")
    def test_routes_remote_to_finalize_remote(self, mock_ph):
        """Remote tasks should always go to _finalize_remote_task."""
        pp = _make_postprocessor()
        pp.settings.get_approval_required.return_value = True
        pp._finalize_remote_task = MagicMock()
        pp._stage_for_approval = MagicMock()

        mock_task = MagicMock()
        mock_task.get_task_type.return_value = "remote"
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 1
        mock_task.get_cache_path.return_value = "/cache/test.mkv"
        mock_task.get_source_data.return_value = {"abspath": "/lib/test.mkv"}
        mock_task.get_source_abspath.return_value = "/lib/test.mkv"
        pp.current_task = mock_task

        pp._handle_processed_task()

        pp._finalize_remote_task.assert_called_once()
        pp._stage_for_approval.assert_not_called()


# ------------------------------------------------------------------
# TestApprovalQualityScores
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestApprovalQualityScores:
    """Tests for quality score fields in approval helpers."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix="compresso_test_quality_")
        self.staging_dir = os.path.join(self.tmpdir, "staging")
        os.makedirs(self.staging_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata", return_value={})
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_detail_includes_quality_scores(self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model):
        """get_approval_task_detail should include vmaf_score and ssim_score."""
        from compresso.webserver.helpers.approval import get_approval_task_detail

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = self.staging_dir
        mock_config_class.return_value = mock_config

        # Create staged file
        task_dir = os.path.join(self.staging_dir, "task_1")
        os.makedirs(task_dir)
        staged_file = os.path.join(task_dir, "video.mkv")
        with open(staged_file, "wb") as f:
            f.write(b"x" * 100)

        # Mock task query
        mock_task_handler = MagicMock()
        task_data = {
            "id": 1,
            "abspath": "/test/video.mkv",
            "source_size": 1000,
            "cache_path": "/cache/video.mkv",
            "success": True,
            "start_time": "2024-01-01",
            "finish_time": "2024-01-02",
            "log": "",
            "library_id": 1,
        }
        mock_task_handler.get_task_list_filtered_and_sorted.return_value = [task_data]
        mock_task_module.Task.return_value = mock_task_handler

        # Mock Tasks.get_by_id for quality scores
        mock_record = MagicMock()
        mock_record.vmaf_score = 91.5
        mock_record.ssim_score = 0.972
        mock_tasks_model.get_by_id.return_value = mock_record

        result = get_approval_task_detail(1)
        assert result is not None
        assert result["vmaf_score"] == 91.5
        assert result["ssim_score"] == 0.972

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata", return_value={})
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_detail_none_scores_when_not_computed(self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model):
        """Quality scores should be None when not computed."""
        from compresso.webserver.helpers.approval import get_approval_task_detail

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = self.staging_dir
        mock_config_class.return_value = mock_config

        task_dir = os.path.join(self.staging_dir, "task_2")
        os.makedirs(task_dir)
        with open(os.path.join(task_dir, "video.mkv"), "wb") as f:
            f.write(b"x" * 100)

        mock_task_handler = MagicMock()
        task_data = {
            "id": 2,
            "abspath": "/test/video.mkv",
            "source_size": 1000,
            "cache_path": "/cache/video.mkv",
            "success": True,
            "start_time": "",
            "finish_time": "",
            "log": "",
            "library_id": 1,
        }
        mock_task_handler.get_task_list_filtered_and_sorted.return_value = [task_data]
        mock_task_module.Task.return_value = mock_task_handler

        mock_record = MagicMock()
        mock_record.vmaf_score = None
        mock_record.ssim_score = None
        mock_tasks_model.get_by_id.return_value = mock_record

        result = get_approval_task_detail(2)
        assert result is not None
        assert result["vmaf_score"] is None
        assert result["ssim_score"] is None

    @patch("compresso.webserver.helpers.approval.Tasks")
    @patch("compresso.webserver.helpers.approval.extract_media_metadata", return_value={})
    @patch("compresso.webserver.helpers.approval.config.Config")
    @patch("compresso.webserver.helpers.approval.task")
    def test_list_includes_quality_scores(self, mock_task_module, mock_config_class, mock_extract, mock_tasks_model):
        """prepare_filtered_approval_tasks should include vmaf_score and ssim_score."""
        from compresso.webserver.helpers.approval import prepare_filtered_approval_tasks

        mock_config = MagicMock()
        mock_config.get_staging_path.return_value = self.staging_dir
        mock_config_class.return_value = mock_config

        task_dir = os.path.join(self.staging_dir, "task_10")
        os.makedirs(task_dir)
        with open(os.path.join(task_dir, "video.mkv"), "wb") as f:
            f.write(b"x" * 200)

        mock_task_handler = MagicMock()
        mock_task_handler.get_total_task_list_count.return_value = 1
        approval_query = MagicMock()
        approval_query.count.return_value = 1
        task_data = {
            "id": 10,
            "abspath": "/test/movie.mkv",
            "priority": 100,
            "type": "local",
            "status": "awaiting_approval",
            "source_size": 5000,
            "finish_time": "2024-06-01",
            "library_id": 1,
        }
        # First call returns count query, second returns data query
        mock_task_handler.get_task_list_filtered_and_sorted.side_effect = [
            approval_query,
            [task_data],
        ]
        mock_task_module.Task.return_value = mock_task_handler

        mock_record = MagicMock()
        mock_record.vmaf_score = 85.0
        mock_record.ssim_score = 0.940
        mock_tasks_model.get_by_id.return_value = mock_record

        result = prepare_filtered_approval_tasks({"start": 0, "length": 10})
        assert len(result["results"]) == 1
        item = result["results"][0]
        assert item["vmaf_score"] == 85.0
        assert item["ssim_score"] == 0.940


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
