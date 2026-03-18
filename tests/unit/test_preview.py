#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_preview.py

    Unit tests for the PreviewManager class.

    Tests input validation, job status lookups, cleanup behaviour,
    and the MAX_DURATION cap. Does NOT run ffmpeg (file-system side
    effects are avoided by testing with non-existent paths where appropriate).

"""

import os
import time
import pytest
import tempfile
from unittest.mock import patch, MagicMock


class TestPreviewManager(object):
    """
    TestPreviewManager

    Test the PreviewManager without launching ffmpeg processes.
    """

    def setup_class(self):
        """
        Setup the class state for pytest.

        Initialise a Config so that PreviewManager.__init__ can call
        config.Config().
        """
        config_path = tempfile.mkdtemp(prefix='unmanic_tests_')

        from unmanic import config
        self.settings = config.Config(config_path=config_path)

    def teardown_class(self):
        pass

    def _make_manager(self):
        """Create a fresh PreviewManager and reset its class-level state."""
        from unmanic.libs.preview import PreviewManager
        mgr = PreviewManager()
        # Reset shared state between tests
        mgr._jobs = {}
        mgr._current_job = None
        return mgr

    # ------------------------------------------------------------------
    # create_preview — input validation
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_create_preview_raises_for_nonexistent_source(self):
        """create_preview should raise ValueError when source file does not exist."""
        mgr = self._make_manager()
        with pytest.raises(ValueError, match="Source file does not exist"):
            mgr.create_preview(
                source_path='/nonexistent/path/video.mkv',
                start_time=0,
                duration=10,
                library_id=1,
            )

    @pytest.mark.unittest
    def test_create_preview_raises_for_zero_duration(self):
        """create_preview should raise ValueError when duration is zero."""
        mgr = self._make_manager()
        # Create a real temporary file so the source-path check passes
        with tempfile.NamedTemporaryFile(suffix='.mkv', delete=False) as f:
            tmp_path = f.name
        try:
            with pytest.raises(ValueError, match="Duration must be positive"):
                mgr.create_preview(
                    source_path=tmp_path,
                    start_time=0,
                    duration=0,
                    library_id=1,
                )
        finally:
            os.unlink(tmp_path)

    @pytest.mark.unittest
    def test_create_preview_raises_for_negative_duration(self):
        """create_preview should raise ValueError when duration is negative."""
        mgr = self._make_manager()
        with tempfile.NamedTemporaryFile(suffix='.mkv', delete=False) as f:
            tmp_path = f.name
        try:
            with pytest.raises(ValueError, match="Duration must be positive"):
                mgr.create_preview(
                    source_path=tmp_path,
                    start_time=0,
                    duration=-5,
                    library_id=1,
                )
        finally:
            os.unlink(tmp_path)

    # ------------------------------------------------------------------
    # MAX_DURATION cap
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_max_duration_cap(self):
        """Duration > MAX_DURATION should be capped to MAX_DURATION (30)."""
        mgr = self._make_manager()

        with tempfile.NamedTemporaryFile(suffix='.mkv', delete=False) as f:
            tmp_path = f.name

        try:
            # Patch threading.Thread so we don't actually spawn ffmpeg
            with patch('unmanic.libs.preview.threading.Thread') as mock_thread:
                mock_thread_instance = MagicMock()
                mock_thread.return_value = mock_thread_instance

                job_id = mgr.create_preview(
                    source_path=tmp_path,
                    start_time=0,
                    duration=60,  # exceeds MAX_DURATION of 30
                    library_id=1,
                )

                # Verify the job was created with capped duration
                job = mgr._jobs[job_id]
                assert job['duration'] == mgr.MAX_DURATION
                assert job['duration'] == 30
        finally:
            os.unlink(tmp_path)

    @pytest.mark.unittest
    def test_max_duration_constant_is_30(self):
        """PreviewManager.MAX_DURATION should be 30."""
        from unmanic.libs.preview import PreviewManager
        assert PreviewManager.MAX_DURATION == 30

    # ------------------------------------------------------------------
    # get_job_status
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_job_status_returns_none_for_unknown_job(self):
        """get_job_status should return None for a job_id that does not exist."""
        mgr = self._make_manager()
        result = mgr.get_job_status('nonexistent-id')
        assert result is None

    @pytest.mark.unittest
    def test_get_job_status_returns_dict_for_known_job(self):
        """get_job_status should return a dict when a job exists."""
        mgr = self._make_manager()

        # Manually insert a job into the internal state
        mgr._jobs['test-job'] = {
            'job_id': 'test-job',
            'status': 'running',
            'error': None,
            'source_size': 0,
            'encoded_size': 0,
            'source_codec': '',
            'encoded_codec': '',
        }

        result = mgr.get_job_status('test-job')
        assert result is not None
        assert result['job_id'] == 'test-job'
        assert result['status'] == 'running'

    @pytest.mark.unittest
    def test_get_job_status_ready_includes_urls(self):
        """When job status is 'ready', result should include source_url and encoded_url."""
        mgr = self._make_manager()

        mgr._jobs['ready-job'] = {
            'job_id': 'ready-job',
            'status': 'ready',
            'error': None,
            'source_size': 5000,
            'encoded_size': 3000,
            'source_codec': 'hevc',
            'encoded_codec': 'h264',
        }

        result = mgr.get_job_status('ready-job')
        assert 'source_url' in result
        assert 'encoded_url' in result
        assert 'ready-job' in result['source_url']
        assert 'ready-job' in result['encoded_url']

    # ------------------------------------------------------------------
    # cleanup_job
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_cleanup_job_handles_missing_job_gracefully(self):
        """cleanup_job should not raise when called with a non-existent job_id."""
        mgr = self._make_manager()
        # Should not raise any exception
        mgr.cleanup_job('does-not-exist')

    @pytest.mark.unittest
    def test_cleanup_job_removes_job_from_dict(self):
        """cleanup_job should remove the job from the internal _jobs dict."""
        mgr = self._make_manager()

        job_dir = tempfile.mkdtemp(prefix='preview_test_')
        mgr._jobs['cleanup-test'] = {
            'job_id': 'cleanup-test',
            'job_dir': job_dir,
            'status': 'ready',
        }

        mgr.cleanup_job('cleanup-test')
        assert 'cleanup-test' not in mgr._jobs

    @pytest.mark.unittest
    def test_cleanup_job_removes_directory(self):
        """cleanup_job should remove the job's cache directory."""
        mgr = self._make_manager()

        job_dir = tempfile.mkdtemp(prefix='preview_test_')
        mgr._jobs['dir-cleanup'] = {
            'job_id': 'dir-cleanup',
            'job_dir': job_dir,
            'status': 'ready',
        }

        assert os.path.exists(job_dir)
        mgr.cleanup_job('dir-cleanup')
        assert not os.path.exists(job_dir)


    # ------------------------------------------------------------------
    # cleanup_old_previews (B3)
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_cleanup_old_previews_removes_expired_jobs(self):
        """Jobs older than CLEANUP_AGE should be removed by cleanup_old_previews."""
        mgr = self._make_manager()

        job_dir = tempfile.mkdtemp(prefix='preview_expired_')
        mgr._jobs['expired-job'] = {
            'job_id': 'expired-job',
            'job_dir': job_dir,
            'status': 'ready',
            'created_at': time.time() - mgr.CLEANUP_AGE - 100,
        }

        mgr.cleanup_old_previews()
        assert 'expired-job' not in mgr._jobs

    @pytest.mark.unittest
    def test_cleanup_old_previews_keeps_recent_jobs(self):
        """Jobs newer than CLEANUP_AGE should be retained by cleanup_old_previews."""
        mgr = self._make_manager()

        job_dir = tempfile.mkdtemp(prefix='preview_recent_')
        mgr._jobs['recent-job'] = {
            'job_id': 'recent-job',
            'job_dir': job_dir,
            'status': 'ready',
            'created_at': time.time() - 60,  # 1 minute ago
        }

        mgr.cleanup_old_previews()
        assert 'recent-job' in mgr._jobs
        # Clean up
        if os.path.exists(job_dir):
            import shutil
            shutil.rmtree(job_dir)

    # ------------------------------------------------------------------
    # _get_video_codec (B4)
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_get_video_codec_success(self, mock_run):
        """_get_video_codec returns codec name on success."""
        mock_run.return_value = MagicMock(returncode=0, stdout='hevc\n')
        mgr = self._make_manager()
        result = mgr._get_video_codec('/test/file.mkv')
        assert result == 'hevc'

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_get_video_codec_failure(self, mock_run):
        """_get_video_codec returns empty string on failure."""
        mock_run.side_effect = OSError("ffprobe not found")
        mgr = self._make_manager()
        result = mgr._get_video_codec('/test/file.mkv')
        assert result == ''

    # ------------------------------------------------------------------
    # _run_plugin_pipeline
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    @patch('unmanic.libs.plugins.PluginsHandler')
    def test_run_plugin_pipeline_no_plugins_returns_false(self, mock_ph_class):
        """Empty plugin list returns False."""
        mock_ph = MagicMock()
        mock_ph.get_enabled_plugin_modules_by_type.return_value = []
        mock_ph_class.return_value = mock_ph
        mgr = self._make_manager()
        result = mgr._run_plugin_pipeline('/tmp/seg.mkv', '/tmp/enc.mp4', library_id=1)
        assert result is False

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    @patch('unmanic.libs.plugins.PluginsHandler')
    def test_run_plugin_pipeline_success(self, mock_ph_class, mock_run):
        """Plugin sets exec_command, subprocess runs, returns True."""
        import shutil as _shutil

        job_dir = tempfile.mkdtemp(prefix='preview_pipeline_')
        seg_path = os.path.join(job_dir, 'segment.mkv')
        enc_path = os.path.join(job_dir, 'encoded.mp4')
        with open(seg_path, 'w') as f:
            f.write('fake')

        mock_ph = MagicMock()
        plugin_module = {'plugin_id': 'test_plugin'}
        mock_ph.get_enabled_plugin_modules_by_type.return_value = [plugin_module]

        def set_exec_command(data, plugin_id, plugin_type):
            data['exec_command'] = ['echo', 'test']
            # Create the output file
            with open(data['file_out'], 'w') as f:
                f.write('encoded')
            return True

        mock_ph.exec_plugin_runner.side_effect = set_exec_command
        mock_ph_class.return_value = mock_ph

        # Mock subprocess: the remux command needs to create the output file
        def mock_subprocess_run(cmd, **kwargs):
            # If this is a remux/encode command that produces remuxed.mp4, create it
            for arg in cmd:
                if isinstance(arg, str) and arg.endswith('remuxed.mp4'):
                    with open(arg, 'w') as f:
                        f.write('remuxed')
                    break
            return MagicMock(returncode=0, stderr='')
        mock_run.side_effect = mock_subprocess_run

        mgr = self._make_manager()
        # Create the encoded output so shutil.copy2 works
        with open(enc_path, 'w') as f:
            f.write('placeholder')
        result = mgr._run_plugin_pipeline(seg_path, enc_path, library_id=1)
        assert result is True

        # Cleanup
        _shutil.rmtree(job_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # _generate_preview pipeline integration
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.PreviewManager.compute_quality_metrics')
    @patch('unmanic.libs.preview.PreviewManager._get_video_codec')
    @patch('unmanic.libs.preview.PreviewManager._run_plugin_pipeline')
    @patch('unmanic.libs.preview.subprocess.run')
    def test_generate_preview_falls_back_on_pipeline_failure(
        self, mock_run, mock_pipeline, mock_codec, mock_metrics
    ):
        """When _run_plugin_pipeline returns False, fallback CRF 23 encode is used."""
        mock_pipeline.return_value = False
        mock_codec.return_value = 'h264'
        mock_metrics.return_value = (None, None)
        mock_run.return_value = MagicMock(returncode=0, stderr='')

        mgr = self._make_manager()

        # Create a temp file for source
        with tempfile.NamedTemporaryFile(suffix='.mkv', delete=False) as f:
            tmp_path = f.name

        try:
            with patch('unmanic.libs.preview.threading.Thread') as mock_thread:
                mock_thread_instance = MagicMock()
                mock_thread.return_value = mock_thread_instance

                job_id = mgr.create_preview(
                    source_path=tmp_path,
                    start_time=0,
                    duration=5,
                    library_id=1,
                )

            # Run _generate_preview directly
            job = mgr._jobs[job_id]
            # Create job_dir files so os.path.exists checks pass
            os.makedirs(job['job_dir'], exist_ok=True)

            mgr._generate_preview(job_id)

            # Pipeline was called but returned False
            mock_pipeline.assert_called_once()

            # subprocess.run should have been called for:
            # 1. segment extraction, 2. source_web encode, 3. fallback CRF 23 encode
            assert mock_run.call_count == 3
            # The third call should contain CRF 23 args
            third_call_args = mock_run.call_args_list[2][0][0]
            assert '-crf' in third_call_args
            crf_idx = third_call_args.index('-crf')
            assert third_call_args[crf_idx + 1] == '23'

            # encoded_by_pipeline should be False
            assert job['encoded_by_pipeline'] is False
        finally:
            os.unlink(tmp_path)

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.PreviewManager.compute_quality_metrics')
    @patch('unmanic.libs.preview.PreviewManager._get_video_codec')
    @patch('unmanic.libs.preview.PreviewManager._run_plugin_pipeline')
    @patch('unmanic.libs.preview.subprocess.run')
    def test_generate_preview_uses_pipeline_when_available(
        self, mock_run, mock_pipeline, mock_codec, mock_metrics
    ):
        """When _run_plugin_pipeline returns True, pipeline is used and encoded_by_pipeline is True."""
        mock_pipeline.return_value = True
        mock_codec.return_value = 'h264'
        mock_metrics.return_value = (None, None)
        mock_run.return_value = MagicMock(returncode=0, stderr='')

        mgr = self._make_manager()

        with tempfile.NamedTemporaryFile(suffix='.mkv', delete=False) as f:
            tmp_path = f.name

        try:
            with patch('unmanic.libs.preview.threading.Thread') as mock_thread:
                mock_thread_instance = MagicMock()
                mock_thread.return_value = mock_thread_instance

                job_id = mgr.create_preview(
                    source_path=tmp_path,
                    start_time=0,
                    duration=5,
                    library_id=1,
                )

            job = mgr._jobs[job_id]
            os.makedirs(job['job_dir'], exist_ok=True)
            # Create the encoded_path so os.path.exists works for size check
            with open(job['encoded_path'], 'w') as f:
                f.write('fake encoded')
            with open(job['source_web_path'], 'w') as f:
                f.write('fake source web')

            mgr._generate_preview(job_id)

            mock_pipeline.assert_called_once()

            # subprocess.run should have been called only for:
            # 1. segment extraction, 2. source_web encode (NOT for CRF 23 fallback)
            assert mock_run.call_count == 2

            # encoded_by_pipeline should be True
            assert job['encoded_by_pipeline'] is True
        finally:
            os.unlink(tmp_path)


class TestPreviewQualityMetrics(object):
    """
    TestPreviewQualityMetrics

    Tests for compute_quality_metrics() and get_job_status() quality fields.
    """

    def setup_class(self):
        config_path = tempfile.mkdtemp(prefix='unmanic_tests_quality_')
        from unmanic import config
        self.settings = config.Config(config_path=config_path)

    def teardown_class(self):
        pass

    def _make_manager(self):
        from unmanic.libs.preview import PreviewManager
        mgr = PreviewManager()
        mgr._jobs = {}
        mgr._current_job = None
        return mgr

    # ------------------------------------------------------------------
    # compute_quality_metrics
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_ssim_only_vmaf_fails(self, mock_run):
        """SSIM succeeds, VMAF raises → ssim_score set, vmaf_score None."""
        ssim_result = MagicMock(returncode=0, stderr='[Parsed_ssim_0] SSIM All:0.9812 (17.26)')
        mock_run.side_effect = [ssim_result, OSError("libvmaf not available")]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert ssim == pytest.approx(0.9812)
        assert vmaf is None

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_vmaf_only_ssim_fails(self, mock_run):
        """SSIM raises, VMAF succeeds → vmaf_score set, ssim_score None."""
        vmaf_result = MagicMock(returncode=0, stderr='VMAF score: 95.32')
        mock_run.side_effect = [OSError("ssim failed"), vmaf_result]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert vmaf == pytest.approx(95.32)
        assert ssim is None

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_both_succeed(self, mock_run):
        """Both SSIM and VMAF succeed → both scores set."""
        ssim_result = MagicMock(returncode=0, stderr='All:0.9500 (13.01)')
        vmaf_result = MagicMock(returncode=0, stderr='VMAF score: 88.50')
        mock_run.side_effect = [ssim_result, vmaf_result]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert ssim == pytest.approx(0.95)
        assert vmaf == pytest.approx(88.50)

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_alternate_vmaf_pattern(self, mock_run):
        """Alternate vmaf_score pattern is parsed."""
        ssim_result = MagicMock(returncode=0, stderr='no ssim match here')
        vmaf_result = MagicMock(returncode=0, stderr='vmaf_score: 91.00')
        mock_run.side_effect = [ssim_result, vmaf_result]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert vmaf == pytest.approx(91.00)
        assert ssim is None

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_both_fail(self, mock_run):
        """Both raise OSError → (None, None)."""
        mock_run.side_effect = [OSError("ssim fail"), OSError("vmaf fail")]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert vmaf is None
        assert ssim is None

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_ssim_success_no_regex_match(self, mock_run):
        """SSIM returncode=0 but no regex match → ssim_score is None."""
        ssim_result = MagicMock(returncode=0, stderr='no useful output')
        vmaf_result = MagicMock(returncode=0, stderr='also nothing useful')
        mock_run.side_effect = [ssim_result, vmaf_result]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert ssim is None
        assert vmaf is None

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_vmaf_success_no_regex_match(self, mock_run):
        """VMAF returncode=0 but no regex match → vmaf_score is None."""
        ssim_result = MagicMock(returncode=0, stderr='All:0.9700')
        vmaf_result = MagicMock(returncode=0, stderr='completed but no score')
        mock_run.side_effect = [ssim_result, vmaf_result]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert ssim == pytest.approx(0.97)
        assert vmaf is None

    # ------------------------------------------------------------------
    # get_job_status with quality scores
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_job_with_quality_scores(self):
        """Job with vmaf/ssim scores includes them in status."""
        mgr = self._make_manager()
        mgr._jobs['quality-job'] = {
            'job_id': 'quality-job',
            'status': 'ready',
            'error': None,
            'source_size': 5000,
            'encoded_size': 3000,
            'source_codec': 'hevc',
            'encoded_codec': 'h264',
            'vmaf_score': 92.5,
            'ssim_score': 0.9812,
        }
        result = mgr.get_job_status('quality-job')
        assert result['vmaf_score'] == 92.5
        assert result['ssim_score'] == 0.9812

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_ssim_command_uses_stream_mapping(self, mock_run):
        """SSIM ffmpeg command includes [0:v][1:v]ssim filter."""
        ssim_result = MagicMock(returncode=0, stderr='All:0.9500')
        vmaf_result = MagicMock(returncode=0, stderr='VMAF score: 90.0')
        mock_run.side_effect = [ssim_result, vmaf_result]

        mgr = self._make_manager()
        mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')

        ssim_call_args = mock_run.call_args_list[0][0][0]
        lavfi_idx = ssim_call_args.index('-lavfi')
        assert '[0:v][1:v]ssim' in ssim_call_args[lavfi_idx + 1]

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_vmaf_command_uses_stream_mapping(self, mock_run):
        """VMAF ffmpeg command includes [0:v][1:v]libvmaf filter."""
        ssim_result = MagicMock(returncode=0, stderr='All:0.9500')
        vmaf_result = MagicMock(returncode=0, stderr='VMAF score: 90.0')
        mock_run.side_effect = [ssim_result, vmaf_result]

        mgr = self._make_manager()
        mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')

        vmaf_call_args = mock_run.call_args_list[1][0][0]
        lavfi_idx = vmaf_call_args.index('-lavfi')
        assert '[0:v][1:v]libvmaf' in vmaf_call_args[lavfi_idx + 1]

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_integer_ssim_score_parsed(self, mock_run):
        """Integer SSIM score 'All:1' → ssim_score=1.0."""
        ssim_result = MagicMock(returncode=0, stderr='All:1')
        vmaf_result = MagicMock(returncode=0, stderr='no match')
        mock_run.side_effect = [ssim_result, vmaf_result]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert ssim == pytest.approx(1.0)

    @pytest.mark.unittest
    @patch('unmanic.libs.preview.subprocess.run')
    def test_integer_vmaf_score_parsed(self, mock_run):
        """Integer VMAF score 'VMAF score: 100' → vmaf_score=100.0."""
        ssim_result = MagicMock(returncode=0, stderr='no match')
        vmaf_result = MagicMock(returncode=0, stderr='VMAF score: 100')
        mock_run.side_effect = [ssim_result, vmaf_result]

        mgr = self._make_manager()
        vmaf, ssim = mgr.compute_quality_metrics('/src.mp4', '/enc.mp4')
        assert vmaf == pytest.approx(100.0)

    @pytest.mark.unittest
    def test_job_without_quality_scores(self):
        """Job without quality scores → vmaf_score/ssim_score are None."""
        mgr = self._make_manager()
        mgr._jobs['no-quality'] = {
            'job_id': 'no-quality',
            'status': 'running',
            'error': None,
            'source_size': 0,
            'encoded_size': 0,
            'source_codec': '',
            'encoded_codec': '',
            'vmaf_score': None,
            'ssim_score': None,
        }
        result = mgr.get_job_status('no-quality')
        assert result['vmaf_score'] is None
        assert result['ssim_score'] is None

    @pytest.mark.unittest
    def test_job_status_includes_encoded_by_pipeline(self):
        """get_job_status includes encoded_by_pipeline field."""
        mgr = self._make_manager()
        mgr._jobs['pipeline-job'] = {
            'job_id': 'pipeline-job',
            'status': 'ready',
            'error': None,
            'source_size': 5000,
            'encoded_size': 3000,
            'source_codec': 'hevc',
            'encoded_codec': 'h264',
            'vmaf_score': 90.0,
            'ssim_score': 0.98,
            'encoded_by_pipeline': True,
        }
        result = mgr.get_job_status('pipeline-job')
        assert result['encoded_by_pipeline'] is True

    @pytest.mark.unittest
    def test_job_status_encoded_by_pipeline_defaults_false(self):
        """get_job_status defaults encoded_by_pipeline to False when not set."""
        mgr = self._make_manager()
        mgr._jobs['no-pipeline'] = {
            'job_id': 'no-pipeline',
            'status': 'running',
            'error': None,
            'source_size': 0,
            'encoded_size': 0,
            'source_codec': '',
            'encoded_codec': '',
        }
        result = mgr.get_job_status('no-pipeline')
        assert result['encoded_by_pipeline'] is False


class TestPreviewJobTimeout(object):
    """Tests for preview job timeout (Phase 3B)."""

    def setup_class(self):
        config_path = tempfile.mkdtemp(prefix='unmanic_tests_timeout_')
        from unmanic import config
        self.settings = config.Config(config_path=config_path)

    def _make_manager(self):
        from unmanic.libs.preview import PreviewManager
        mgr = PreviewManager()
        mgr._jobs = {}
        mgr._current_job = None
        return mgr

    @pytest.mark.unittest
    def test_max_job_timeout_constant(self):
        from unmanic.libs.preview import PreviewManager
        assert PreviewManager.MAX_JOB_TIMEOUT == 600

    @pytest.mark.unittest
    def test_check_timeout_raises_on_expired(self):
        mgr = self._make_manager()
        mgr._jobs['expired'] = {
            'job_id': 'expired',
            'created_at': time.time() - 700,
        }
        with pytest.raises(RuntimeError, match="timed out"):
            mgr._check_timeout('expired')

    @pytest.mark.unittest
    def test_check_timeout_does_not_raise_on_fresh(self):
        mgr = self._make_manager()
        mgr._jobs['fresh'] = {
            'job_id': 'fresh',
            'created_at': time.time(),
        }
        # Should not raise
        mgr._check_timeout('fresh')


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
