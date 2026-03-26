#!/usr/bin/env python3

"""
    tests.unit.test_postprocessor_extended.py

    Extended unit tests for compresso.libs.postprocessor.PostProcessor,
    covering file operations, plugin handler integration, staging, and pipeline stages.
"""

import os
import shutil
import tempfile
import threading
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


PP_MOD = 'compresso.libs.postprocessor'


def _make_postprocessor():
    """Create a PostProcessor with mocked dependencies."""
    with patch(f'{PP_MOD}.config.Config'), \
         patch(f'{PP_MOD}.CompressoLogging') as mock_logging:
        mock_logger = MagicMock()
        mock_logging.get_logger.return_value = mock_logger

        from compresso.libs.postprocessor import PostProcessor

        data_queues = {}
        task_queue = MagicMock()
        event = threading.Event()
        pp = PostProcessor(data_queues, task_queue, event)
        return pp


def _make_current_task(success=True, task_type='local', library_id=1,
                       source_abspath='/src/test.mkv', dest_abspath='/dst/test.mkv',
                       cache_path='/cache/compresso_file_conversion_xyz/output.mkv'):
    mock_task = MagicMock()
    mock_task.task.success = success
    mock_task.task.source_size = 1000000
    mock_task.get_task_type.return_value = task_type
    mock_task.get_task_library_id.return_value = library_id
    mock_task.get_task_library_name.return_value = 'TestLib'
    mock_task.get_task_id.return_value = 42
    mock_task.get_cache_path.return_value = cache_path
    mock_task.get_source_abspath.return_value = source_abspath
    mock_task.get_source_data.return_value = {'abspath': source_abspath, 'basename': os.path.basename(source_abspath)}
    mock_task.get_destination_data.return_value = {'abspath': dest_abspath, 'basename': os.path.basename(dest_abspath)}
    mock_task.get_task_success.return_value = success
    mock_task.get_start_time.return_value = '2024-01-01 00:00:00'
    mock_task.get_finish_time.return_value = '2024-01-01 00:05:00'
    mock_task.task_dump.return_value = {
        'task_label': os.path.basename(source_abspath),
        'abspath': source_abspath,
        'task_success': success,
        'start_time': '2024-01-01 00:00:00',
        'finish_time': '2024-01-01 00:05:00',
        'processed_by_worker': 'worker-0',
        'log': '',
        'source_size': 1000000,
        'library_id': library_id,
    }
    return mock_task


# ------------------------------------------------------------------
# TestPostProcessError
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestPostProcessError:
    """Tests for PostProcessError exception."""

    def test_exception_message(self):
        from compresso.libs.postprocessor import PostProcessError
        err = PostProcessError('expected', 'actual')
        assert 'expected' in str(err)
        assert 'actual' in str(err)
        assert err.expected_var == 'expected'
        assert err.result_var == 'actual'


# ------------------------------------------------------------------
# TestStageForApproval
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestStageForApproval:
    """Tests for PostProcessor._stage_for_approval()."""

    @patch('compresso.libs.ffprobe_utils.compute_quality_scores', return_value={'vmaf_score': None, 'ssim_score': None})
    @patch(f'{PP_MOD}.shutil.copy2')
    @patch(f'{PP_MOD}.os.makedirs')
    def test_stages_file_successfully(self, mock_makedirs, mock_copy2, mock_quality):
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.settings.get_staging_path.return_value = '/staging'
        pp.current_task = _make_current_task()

        pp._stage_for_approval()

        mock_makedirs.assert_called_once_with(os.path.join('/staging', 'task_42'), exist_ok=True)
        mock_copy2.assert_called_once()
        pp.current_task.set_status.assert_called_once_with('awaiting_approval')

    @patch('compresso.libs.ffprobe_utils.compute_quality_scores', return_value={'vmaf_score': None, 'ssim_score': None})
    @patch(f'{PP_MOD}.shutil.copy2', side_effect=OSError("disk full"))
    @patch(f'{PP_MOD}.os.makedirs')
    def test_falls_back_on_staging_failure(self, mock_makedirs, mock_copy2, mock_quality):
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.settings.get_staging_path.return_value = '/staging'
        pp.current_task = _make_current_task()
        pp._finalize_local_task = MagicMock()

        pp._stage_for_approval()

        pp._finalize_local_task.assert_called_once()


# ------------------------------------------------------------------
# TestFinalizeLocalTask
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFinalizeLocalTask:
    """Tests for PostProcessor._finalize_local_task()."""

    @patch(f'{PP_MOD}.PostProcessor._cleanup_staging_files')
    @patch(f'{PP_MOD}.PostProcessor.commit_task_metadata')
    @patch(f'{PP_MOD}.PostProcessor.write_history_log')
    @patch(f'{PP_MOD}.PostProcessor.post_process_file')
    def test_runs_all_steps(self, mock_ppf, mock_whl, mock_ctm, mock_csf):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task()

        pp._finalize_local_task()

        mock_ppf.assert_called_once()
        mock_whl.assert_called_once()
        mock_ctm.assert_called_once()
        mock_csf.assert_called_once()
        pp.current_task.delete.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._cleanup_staging_files')
    @patch(f'{PP_MOD}.PostProcessor.commit_task_metadata')
    @patch(f'{PP_MOD}.PostProcessor.write_history_log')
    @patch(f'{PP_MOD}.PostProcessor.post_process_file', side_effect=Exception("boom"))
    def test_continues_on_post_process_error(self, mock_ppf, mock_whl, mock_ctm, mock_csf):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task()

        pp._finalize_local_task()

        # Should still attempt subsequent steps
        mock_whl.assert_called_once()
        mock_ctm.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._cleanup_staging_files')
    @patch(f'{PP_MOD}.PostProcessor.commit_task_metadata', side_effect=Exception("meta error"))
    @patch(f'{PP_MOD}.PostProcessor.write_history_log')
    @patch(f'{PP_MOD}.PostProcessor.post_process_file')
    def test_continues_on_metadata_error(self, mock_ppf, mock_whl, mock_ctm, mock_csf):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task()

        pp._finalize_local_task()

        # Cleanup and delete still called
        mock_csf.assert_called_once()
        pp.current_task.delete.assert_called_once()


# ------------------------------------------------------------------
# TestFinalizeLocalTaskKeepBoth
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFinalizeLocalTaskKeepBoth:
    """Tests for PostProcessor._finalize_local_task_keep_both()."""

    @patch(f'{PP_MOD}.extract_media_metadata', return_value={'codec': 'hevc'})
    @patch(f'{PP_MOD}.os.path.exists', return_value=False)
    @patch(f'{PP_MOD}.PostProcessor._finalize_local_task')
    def test_renames_with_codec_suffix(self, mock_finalize, mock_exists, mock_extract):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task(
            source_abspath='/media/test.mkv',
            dest_abspath='/media/test.mkv',
            cache_path='/cache/compresso_file_conversion_xyz/output.mkv'
        )

        pp._finalize_local_task_keep_both()

        pp.current_task.set_destination_path.assert_called_once_with('/media/test.hevc.mkv')
        mock_finalize.assert_called_once()

    @patch(f'{PP_MOD}.extract_media_metadata', side_effect=Exception("ffprobe failed"))
    @patch(f'{PP_MOD}.os.path.exists', return_value=False)
    @patch(f'{PP_MOD}.PostProcessor._finalize_local_task')
    def test_falls_back_to_transcoded_on_error(self, mock_finalize, mock_exists, mock_extract):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task(
            source_abspath='/media/test.mkv',
            dest_abspath='/media/test.mkv',
            cache_path='/cache/compresso_file_conversion_xyz/output.mkv'
        )

        pp._finalize_local_task_keep_both()

        pp.current_task.set_destination_path.assert_called_once_with('/media/test.transcoded.mkv')
        mock_finalize.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._finalize_local_task')
    def test_different_paths_no_rename(self, mock_finalize):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task(
            source_abspath='/media/src.mkv',
            dest_abspath='/media/dst.mkv',
        )

        pp._finalize_local_task_keep_both()

        pp.current_task.set_destination_path.assert_not_called()
        mock_finalize.assert_called_once()


# ------------------------------------------------------------------
# TestFinalizeRemoteTask
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFinalizeRemoteTask:
    """Tests for PostProcessor._finalize_remote_task()."""

    @patch(f'{PP_MOD}.PostProcessor.dump_history_log')
    @patch(f'{PP_MOD}.PostProcessor.post_process_remote_file')
    def test_runs_remote_steps(self, mock_pprf, mock_dhl):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task(task_type='remote')

        pp._finalize_remote_task()

        mock_pprf.assert_called_once()
        mock_dhl.assert_called_once()
        pp.current_task.set_status.assert_called_once_with('complete')

    @patch(f'{PP_MOD}.PostProcessor.dump_history_log')
    @patch(f'{PP_MOD}.PostProcessor.post_process_remote_file', side_effect=Exception("remote error"))
    def test_continues_on_remote_error(self, mock_pprf, mock_dhl):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task(task_type='remote')

        pp._finalize_remote_task()

        mock_dhl.assert_called_once()
        pp.current_task.set_status.assert_called_once_with('complete')


# ------------------------------------------------------------------
# TestCleanupStagingFiles
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCleanupStagingFiles:
    """Tests for PostProcessor._cleanup_staging_files()."""

    def test_removes_existing_staging_directory(self):
        tmpdir = tempfile.mkdtemp(prefix='compresso_staging_test_')
        task_dir = os.path.join(tmpdir, 'task_42')
        os.makedirs(task_dir)
        with open(os.path.join(task_dir, 'output.mkv'), 'w') as f:
            f.write('test')

        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.settings.get_staging_path.return_value = tmpdir
        pp.current_task = _make_current_task()

        pp._cleanup_staging_files()

        assert not os.path.exists(task_dir)
        shutil.rmtree(tmpdir, ignore_errors=True)

    @patch(f'{PP_MOD}.os.path.exists', return_value=False)
    def test_does_nothing_when_no_staging_dir(self, mock_exists):
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.settings.get_staging_path.return_value = '/staging'
        pp.current_task = _make_current_task()

        # Should not raise
        pp._cleanup_staging_files()


# ------------------------------------------------------------------
# TestHandleProcessedTask
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHandleProcessedTask:
    """Tests for PostProcessor._handle_processed_task()."""

    @patch(f'{PP_MOD}.PostProcessor._finalize_local_task')
    @patch(f'{PP_MOD}.Library')
    @patch(f'{PP_MOD}.PluginsHandler')
    def test_successful_local_task_replace_policy(self, mock_ph_cls, mock_lib_cls, mock_finalize):
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.settings.get_approval_required.return_value = False
        pp.current_task = _make_current_task(success=True)

        mock_lib = MagicMock()
        mock_lib.get_replacement_policy.return_value = 'replace'
        mock_lib.get_size_guardrail_enabled.return_value = False
        mock_lib_cls.return_value = mock_lib

        pp._handle_processed_task()

        mock_finalize.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._stage_for_approval')
    @patch(f'{PP_MOD}.Library')
    @patch(f'{PP_MOD}.PluginsHandler')
    def test_successful_local_task_approval_policy(self, mock_ph_cls, mock_lib_cls, mock_stage):
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.current_task = _make_current_task(success=True)

        mock_lib = MagicMock()
        mock_lib.get_replacement_policy.return_value = 'approval_required'
        mock_lib.get_size_guardrail_enabled.return_value = False
        mock_lib_cls.return_value = mock_lib

        pp._handle_processed_task()

        mock_stage.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._finalize_local_task_keep_both')
    @patch(f'{PP_MOD}.Library')
    @patch(f'{PP_MOD}.PluginsHandler')
    def test_successful_local_task_keep_both_policy(self, mock_ph_cls, mock_lib_cls, mock_keep_both):
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.current_task = _make_current_task(success=True)

        mock_lib = MagicMock()
        mock_lib.get_replacement_policy.return_value = 'keep_both'
        mock_lib.get_size_guardrail_enabled.return_value = False
        mock_lib_cls.return_value = mock_lib

        pp._handle_processed_task()

        mock_keep_both.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._finalize_local_task')
    @patch(f'{PP_MOD}.Library')
    @patch(f'{PP_MOD}.PluginsHandler')
    def test_failed_local_task_always_finalizes(self, mock_ph_cls, mock_lib_cls, mock_finalize):
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.current_task = _make_current_task(success=False)

        mock_lib = MagicMock()
        mock_lib.get_replacement_policy.return_value = 'replace'
        mock_lib.get_size_guardrail_enabled.return_value = False
        mock_lib_cls.return_value = mock_lib

        pp._handle_processed_task()

        mock_finalize.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._finalize_remote_task')
    @patch(f'{PP_MOD}.PluginsHandler')
    def test_remote_task_uses_remote_finalize(self, mock_ph_cls, mock_finalize):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task(task_type='remote')

        pp._handle_processed_task()

        mock_finalize.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._finalize_local_task')
    @patch(f'{PP_MOD}.Library')
    @patch(f'{PP_MOD}.PluginsHandler')
    @patch(f'{PP_MOD}.os.path.exists', return_value=True)
    @patch(f'{PP_MOD}.os.path.getsize', return_value=50000)
    def test_size_guardrail_rejects_output(self, mock_getsize, mock_exists, mock_ph_cls, mock_lib_cls, mock_finalize):
        """Size guardrail rejects when output ratio is outside bounds."""
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.settings.get_approval_required.return_value = False
        pp.current_task = _make_current_task(success=True)
        pp.current_task.task.source_size = 1000000  # 1MB source

        mock_lib = MagicMock()
        mock_lib.get_size_guardrail_enabled.return_value = True
        mock_lib.get_size_guardrail_min_pct.return_value = 10
        mock_lib.get_size_guardrail_max_pct.return_value = 90
        mock_lib.get_replacement_policy.return_value = 'replace'
        mock_lib_cls.return_value = mock_lib

        # 50000/1000000 = 5% which is below 10% min
        pp._handle_processed_task()

        # Task should be marked as failed
        assert pp.current_task.task.success is False


# ------------------------------------------------------------------
# TestHandleApprovedTask
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHandleApprovedTask:
    """Tests for PostProcessor._handle_approved_task()."""

    @patch(f'{PP_MOD}.PostProcessor._finalize_local_task')
    def test_calls_finalize(self, mock_finalize):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task()

        pp._handle_approved_task()

        mock_finalize.assert_called_once()


# ------------------------------------------------------------------
# TestPostProcessFile
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestPostProcessFile:
    """Tests for PostProcessor.post_process_file()."""

    @patch(f'{PP_MOD}.PostProcessor._PostProcessor__cleanup_cache_files')
    @patch(f'{PP_MOD}.PluginsHandler')
    def test_skips_file_movement_on_failed_task(self, mock_ph_cls, mock_cleanup):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task(success=False)

        mock_ph = MagicMock()
        mock_ph.get_enabled_plugin_modules_by_type.return_value = []
        mock_ph_cls.return_value = mock_ph

        pp.post_process_file()

        mock_cleanup.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._PostProcessor__cleanup_cache_files')
    @patch(f'{PP_MOD}.PostProcessor._PostProcessor__copy_file', return_value=True)
    @patch(f'{PP_MOD}.os.path.exists', return_value=False)
    @patch(f'{PP_MOD}.os.remove')
    @patch(f'{PP_MOD}.PluginsHandler')
    def test_successful_task_with_no_plugins(self, mock_ph_cls, mock_remove, mock_exists, mock_copy, mock_cleanup):
        pp = _make_postprocessor()
        pp.current_task = _make_current_task(
            success=True,
            source_abspath='/src/test.mkv',
            dest_abspath='/dst/test.mkv',
        )

        mock_ph = MagicMock()
        mock_ph.get_enabled_plugin_modules_by_type.return_value = []
        mock_ph.exec_plugin_runner.return_value = True
        mock_ph_cls.return_value = mock_ph

        pp.post_process_file()

        # Default file copy should happen since source != dest
        mock_copy.assert_called()
        mock_cleanup.assert_called_once()


# ------------------------------------------------------------------
# TestPostProcessRemoteFile
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestPostProcessRemoteFile:
    """Tests for PostProcessor.post_process_remote_file()."""

    @patch(f'{PP_MOD}.PostProcessor._PostProcessor__cleanup_cache_files')
    @patch(f'{PP_MOD}.PostProcessor._PostProcessor__copy_file', return_value=True)
    @patch(f'{PP_MOD}.os.path.exists', return_value=True)
    @patch(f'{PP_MOD}.os.remove')
    @patch(f'{PP_MOD}.common.random_string', return_value='abc')
    @patch(f'{PP_MOD}.time.time', return_value=1000)
    def test_remote_file_in_cache(self, mock_time, mock_random, mock_remove, mock_exists, mock_copy, mock_cleanup):
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.settings.get_cache_path.return_value = '/cache'

        pp.current_task = _make_current_task(
            task_type='remote',
            source_abspath='/cache/downloaded.mkv',
            dest_abspath='/cache/output.mkv',
            cache_path='/cache/compresso_file_conversion_xyz/output.mkv'
        )

        pp.post_process_remote_file()

        mock_remove.assert_called()
        mock_cleanup.assert_called_once()

    @patch(f'{PP_MOD}.PostProcessor._PostProcessor__cleanup_cache_files')
    @patch(f'{PP_MOD}.PostProcessor._PostProcessor__copy_file', return_value=True)
    @patch(f'{PP_MOD}.os.path.exists')
    @patch(f'{PP_MOD}.os.remove')
    @patch(f'{PP_MOD}.os.mkdir')
    @patch(f'{PP_MOD}.common.random_string', return_value='abc')
    @patch(f'{PP_MOD}.time.time', return_value=1000)
    def test_remote_source_not_in_cache(
        self, mock_time, mock_random, mock_mkdir, mock_remove, mock_exists, mock_copy, mock_cleanup,
    ):
        """Remote source outside cache: keep source, copy cache to library dir."""
        pp = _make_postprocessor()
        pp.settings = MagicMock()
        pp.settings.get_cache_path.return_value = '/cache'

        pp.current_task = _make_current_task(
            task_type='remote',
            source_abspath='/library/source.mkv',
            dest_abspath='/library/output.mkv',
            cache_path='/cache/compresso_file_conversion_xyz/output.mkv'
        )

        # source exists, cache exists
        mock_exists.return_value = True

        pp.post_process_remote_file()

        mock_cleanup.assert_called_once()


# ------------------------------------------------------------------
# TestLogAndStop
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestLogAndStop:
    """Tests for PostProcessor._log() and stop()."""

    def test_log_calls_logger(self):
        pp = _make_postprocessor()
        pp._log("test message")
        pp.logger.info.assert_called()

    def test_log_with_level(self):
        pp = _make_postprocessor()
        pp._log("warning message", level="warning")
        pp.logger.warning.assert_called()

    def test_stop_sets_abort_flag(self):
        pp = _make_postprocessor()
        assert not pp.abort_flag.is_set()
        pp.stop()
        assert pp.abort_flag.is_set()


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
