#!/usr/bin/env python3

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.postprocessor import PostProcessor


def _postprocessor():
    with patch("compresso.libs.postprocessor.config.Config") as config_class:
        settings = MagicMock()
        settings.get_staging_path.return_value = "/staging"
        settings.get_disk_space_retry_seconds.return_value = 60
        config_class.return_value = settings
        processor = PostProcessor({}, MagicMock(), MagicMock())
    processor.settings = settings
    processor.current_task = MagicMock()
    processor.current_task.task.success = True
    processor.current_task.task.status = "processed"
    processor.current_task.task.deferred_until = None
    processor.current_task.get_task_id.return_value = 42
    processor.current_task.get_cache_path.return_value = "/cache/encoded.mkv"
    processor.current_task.get_source_abspath.return_value = "/library/source.mkv"
    processor.current_task.get_destination_data.return_value = {"abspath": "/library/source.mkv"}
    processor._safety_event_recorder = MagicMock()
    return processor


def _low_space_check(phase):
    return SimpleNamespace(
        ok=False,
        phase=phase,
        path="/volume",
        free_bytes=100,
        required_bytes=200,
    )


@pytest.mark.unittest
def test_low_staging_space_defers_without_falling_back_to_replacement():
    processor = _postprocessor()
    guard = MagicMock()
    guard.check_staging_capacity.return_value = _low_space_check("approval_staging")
    processor._disk_space_guard = guard

    with (
        patch("compresso.libs.postprocessor.shutil.copy2") as copy_file,
        patch.object(processor, "_finalize_local_task") as finalize,
    ):
        processor._stage_for_approval()

    copy_file.assert_not_called()
    finalize.assert_not_called()
    assert processor.current_task.task.status == "processed"
    assert processor.current_task.task.deferred_until is not None
    processor.current_task.task.save.assert_called()
    processor._safety_event_recorder.assert_called_once()


@pytest.mark.unittest
def test_low_finalization_space_defers_without_deleting_task_or_output():
    processor = _postprocessor()
    guard = MagicMock()
    guard.check_finalization_capacity.return_value = _low_space_check("final_replacement")
    processor._disk_space_guard = guard

    with (
        patch.object(processor, "post_process_file") as post_process,
        patch.object(processor, "write_history_log") as write_history,
    ):
        processor._finalize_local_task()

    post_process.assert_not_called()
    write_history.assert_not_called()
    processor.current_task.delete.assert_not_called()
    assert processor.current_task.task.status == "processed"
    assert processor.current_task.task.deferred_until is not None
    processor._safety_event_recorder.assert_called_once()


@pytest.mark.unittest
def test_finalization_resumes_and_clears_defer_when_space_recovers():
    processor = _postprocessor()
    processor.current_task.task.deferred_until = "previous-defer"
    guard = MagicMock()
    guard.check_finalization_capacity.return_value = SimpleNamespace(ok=True)
    processor._disk_space_guard = guard

    with (
        patch.object(processor, "post_process_file"),
        patch.object(processor, "write_history_log"),
        patch.object(processor, "commit_task_metadata"),
        patch.object(processor, "_cleanup_staging_files"),
        patch.object(processor, "_finalize_file_operation_journal"),
        patch("compresso.libs.external_notifications.ExternalNotificationDispatcher"),
    ):
        processor._finalize_local_task()

    assert processor.current_task.task.deferred_until is None
