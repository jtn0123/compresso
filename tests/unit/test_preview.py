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


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
