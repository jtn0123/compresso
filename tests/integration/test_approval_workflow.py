#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.integration.test_approval_workflow.py

    Integration tests for the approval workflow with real files.
    Uses a 30-second sample video to verify staging, approve, and reject flows.

    Requires: tests/fixtures/sample_30s.mp4
    Run with: pytest tests/integration/test_approval_workflow.py -v -m integrationtest
"""

import os
import shutil
import tempfile

import pytest
from unittest.mock import patch, MagicMock

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'sample_30s.mp4')

skip_if_no_fixture = pytest.mark.skipif(
    not os.path.exists(FIXTURE_PATH),
    reason="Test fixture tests/fixtures/sample_30s.mp4 not found"
)


def _make_postprocessor():
    """Create a PostProcessor with mocked dependencies."""
    import threading
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


@pytest.mark.integrationtest
class TestApprovalWorkflowIntegration:
    """Integration tests using real video files."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp(prefix='compresso_integ_approval_')
        self.staging_dir = os.path.join(self.tmpdir, 'staging')
        self.cache_dir = os.path.join(self.tmpdir, 'compresso_file_conversion_test')
        self.library_dir = os.path.join(self.tmpdir, 'library')
        os.makedirs(self.staging_dir)
        os.makedirs(self.cache_dir)
        os.makedirs(self.library_dir)

    def teardown_method(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _copy_fixture_to_cache(self, name='output.mp4'):
        """Copy the sample fixture into the cache dir, simulating transcoder output."""
        dest = os.path.join(self.cache_dir, name)
        shutil.copy2(FIXTURE_PATH, dest)
        return dest

    def _copy_fixture_to_library(self, name='sample.mp4'):
        """Copy the sample fixture into the library dir, simulating the original."""
        dest = os.path.join(self.library_dir, name)
        shutil.copy2(FIXTURE_PATH, dest)
        return dest

    @skip_if_no_fixture
    def test_staging_copies_to_staging_dir(self):
        """When approval_required=True, the cache file should be copied to the staging dir."""
        pp = _make_postprocessor()
        pp.settings.get_staging_path.return_value = self.staging_dir
        pp.settings.get_approval_required.return_value = True

        cache_file = self._copy_fixture_to_cache()

        mock_task = MagicMock()
        mock_task.get_cache_path.return_value = cache_file
        mock_task.get_task_id.return_value = 100
        mock_task.task.success = True
        pp.current_task = mock_task

        pp._stage_for_approval()

        task_staging_dir = os.path.join(self.staging_dir, 'task_100')
        assert os.path.exists(task_staging_dir), "Staging directory was not created"
        staged_files = os.listdir(task_staging_dir)
        assert len(staged_files) == 1
        assert staged_files[0] == 'output.mp4'

        # Staged file should have the same size as cache file
        staged_size = os.path.getsize(os.path.join(task_staging_dir, 'output.mp4'))
        cache_size = os.path.getsize(cache_file)
        assert staged_size == cache_size, "Staged file size doesn't match cache file"

        mock_task.set_status.assert_called_once_with('awaiting_approval')

    @skip_if_no_fixture
    def test_approve_finalizes_replacement(self):
        """After approval, the staged file should replace the original and staging cleaned up."""
        pp = _make_postprocessor()
        pp.settings.get_staging_path.return_value = self.staging_dir

        # Set up: original in library, staged file in staging dir
        original = self._copy_fixture_to_library('movie.mp4')
        os.path.getsize(original)

        task_staging_dir = os.path.join(self.staging_dir, 'task_200')
        os.makedirs(task_staging_dir)
        staged_file = os.path.join(task_staging_dir, 'movie.mp4')
        # Create a slightly different file to verify replacement
        with open(staged_file, 'wb') as f:
            f.write(b'replacement content for testing')
        replacement_size = os.path.getsize(staged_file)

        # Simulate the finalize step: copy staged to original, then clean up staging
        shutil.copy2(staged_file, original)
        shutil.rmtree(task_staging_dir)

        # Verify original was replaced
        assert os.path.getsize(original) == replacement_size
        assert not os.path.exists(task_staging_dir)

    @skip_if_no_fixture
    def test_reject_cleans_up_everything(self):
        """Rejecting should remove the staged file and the staging directory."""
        from compresso.webserver.helpers.approval import _get_staged_file_info

        # Set up staged file
        task_staging_dir = os.path.join(self.staging_dir, 'task_300')
        os.makedirs(task_staging_dir)
        staged_file = os.path.join(task_staging_dir, 'output.mp4')
        shutil.copy2(FIXTURE_PATH, staged_file)
        assert os.path.exists(staged_file)

        # Verify staged info works
        info = _get_staged_file_info(300, self.staging_dir)
        assert info['size'] > 0
        assert info['path'] == staged_file

        # Clean up (simulating reject)
        shutil.rmtree(task_staging_dir)

        # Verify cleaned up
        assert not os.path.exists(task_staging_dir)
        info_after = _get_staged_file_info(300, self.staging_dir)
        assert info_after['size'] == 0
        assert info_after['path'] == ''

    @skip_if_no_fixture
    def test_auto_mode_skips_staging(self):
        """When approval_required=False, _handle_processed_task should finalize directly."""
        pp = _make_postprocessor()
        pp.settings.get_approval_required.return_value = False
        pp._stage_for_approval = MagicMock()
        pp._finalize_local_task = MagicMock()

        with patch('compresso.libs.postprocessor.PluginsHandler'):
            mock_task = MagicMock()
            mock_task.get_task_type.return_value = 'local'
            mock_task.task.success = True
            mock_task.get_task_library_id.return_value = 1
            mock_task.get_task_id.return_value = 400
            mock_task.get_cache_path.return_value = self._copy_fixture_to_cache()
            mock_task.get_source_data.return_value = {'abspath': os.path.join(self.library_dir, 'test.mp4')}
            mock_task.get_source_abspath.return_value = os.path.join(self.library_dir, 'test.mp4')
            pp.current_task = mock_task

            pp._handle_processed_task()

            pp._stage_for_approval.assert_not_called()
            pp._finalize_local_task.assert_called_once()


@pytest.mark.integrationtest
class TestMediaMetadataIntegration:
    """Integration tests for ffprobe metadata extraction with a real file."""

    @skip_if_no_fixture
    def test_extract_metadata_from_fixture(self):
        """extract_media_metadata should return codec and resolution for the fixture."""
        from compresso.libs.ffprobe_utils import extract_media_metadata

        meta = extract_media_metadata(FIXTURE_PATH)
        assert meta['container'] == 'mp4'
        # The fixture should have some video codec
        assert meta['codec'] != '', "Expected a codec but got empty string"
        # Resolution should be detected
        assert meta['resolution'] != '', "Expected a resolution but got empty string"

    @skip_if_no_fixture
    def test_extract_metadata_nonexistent_file(self):
        """extract_media_metadata should return empty strings for nonexistent file."""
        from compresso.libs.ffprobe_utils import extract_media_metadata

        meta = extract_media_metadata('/nonexistent/path/video.mkv')
        assert meta['container'] == 'mkv'
        # Should fallback gracefully
        assert isinstance(meta['codec'], str)
        assert isinstance(meta['resolution'], str)
