#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_filetest.py

    Unit tests for compresso.libs.filetest.FileTest.
"""

import pytest
from unittest.mock import patch, MagicMock


def _make_filetest():
    """Create a FileTest instance with mocked dependencies."""
    with patch('compresso.libs.filetest.config.Config'), \
         patch('compresso.libs.filetest.CompressoLogging'), \
         patch('compresso.libs.filetest.PluginsHandler') as mock_ph:
        mock_ph.return_value.get_enabled_plugin_modules_by_type.return_value = []
        from compresso.libs.filetest import FileTest
        ft = FileTest(library_id=1)
        return ft


# ------------------------------------------------------------------
# TestFileInCompressoIgnoreLockfile
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFileInCompressoIgnoreLockfile:

    def test_exact_match_returns_true(self, tmp_path):
        ignore_file = tmp_path / '.compressoignore'
        ignore_file.write_text('video.mp4\n')
        path = str(tmp_path / 'video.mp4')

        ft = _make_filetest()
        assert ft.file_in_compresso_ignore_lockfile(path) is True

    def test_substring_no_false_positive(self, tmp_path):
        """Bug 1.4: clip.mp4 should NOT match long_clip.mp4."""
        ignore_file = tmp_path / '.compressoignore'
        ignore_file.write_text('long_clip.mp4\n')
        path = str(tmp_path / 'clip.mp4')

        ft = _make_filetest()
        assert ft.file_in_compresso_ignore_lockfile(path) is False

    def test_no_ignore_file_returns_false(self, tmp_path):
        path = str(tmp_path / 'video.mp4')
        ft = _make_filetest()
        assert ft.file_in_compresso_ignore_lockfile(path) is False

    def test_empty_ignore_file_returns_false(self, tmp_path):
        ignore_file = tmp_path / '.compressoignore'
        ignore_file.write_text('')
        path = str(tmp_path / 'video.mp4')

        ft = _make_filetest()
        assert ft.file_in_compresso_ignore_lockfile(path) is False

    def test_comment_lines_ignored(self, tmp_path):
        ignore_file = tmp_path / '.compressoignore'
        ignore_file.write_text('# video.mp4\n')
        path = str(tmp_path / 'video.mp4')

        ft = _make_filetest()
        assert ft.file_in_compresso_ignore_lockfile(path) is False

    def test_blank_lines_ignored(self, tmp_path):
        ignore_file = tmp_path / '.compressoignore'
        ignore_file.write_text('\n\nvideo.mp4\n\n')
        path = str(tmp_path / 'video.mp4')

        ft = _make_filetest()
        assert ft.file_in_compresso_ignore_lockfile(path) is True


# ------------------------------------------------------------------
# TestFileFailedInHistory
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFileFailedInHistory:

    @patch('compresso.libs.filetest.history.History')
    def test_returns_true_for_failed_path(self, mock_history_cls):
        mock_history_cls.return_value.get_historic_tasks_list_with_source_probe.return_value = [
            {'abspath': '/media/video.mp4'}
        ]
        ft = _make_filetest()
        assert ft.file_failed_in_history('/media/video.mp4') is True

    @patch('compresso.libs.filetest.history.History')
    def test_returns_false_for_unknown_path(self, mock_history_cls):
        mock_history_cls.return_value.get_historic_tasks_list_with_source_probe.return_value = [
            {'abspath': '/media/other.mp4'}
        ]
        ft = _make_filetest()
        assert ft.file_failed_in_history('/media/video.mp4') is False

    @patch('compresso.libs.filetest.history.History')
    def test_caches_failed_paths(self, mock_history_cls):
        mock_hist = mock_history_cls.return_value
        mock_hist.get_historic_tasks_list_with_source_probe.return_value = [
            {'abspath': '/media/video.mp4'}
        ]
        ft = _make_filetest()
        ft.file_failed_in_history('/media/video.mp4')
        ft.file_failed_in_history('/media/video.mp4')
        # History should only be queried once (cached after first call)
        mock_hist.get_historic_tasks_list_with_source_probe.assert_called_once()


# ------------------------------------------------------------------
# TestShouldFileBeAddedToTaskList
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestShouldFileBeAddedToTaskList:

    def test_returns_false_if_in_ignore_file(self):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=True)
        ft.file_failed_in_history = MagicMock(return_value=False)

        result, issues, _, _ = ft.should_file_be_added_to_task_list('/media/video.mp4')
        assert result is False
        assert any(i['id'] == 'compressoignore' for i in issues)

    def test_returns_false_if_failed_in_history(self):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=True)

        result, issues, _, _ = ft.should_file_be_added_to_task_list('/media/video.mp4')
        assert result is False
        assert any(i['id'] == 'blacklisted' for i in issues)

    def test_runs_plugins_when_no_early_exit(self):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)

        mock_module = {'plugin_id': 'test_plugin', 'name': 'Test Plugin'}
        ft.plugin_modules = [mock_module]
        ft.plugin_handler.exec_plugin_runner = MagicMock(return_value=True)

        # Plugin sets add_file_to_pending_tasks
        def exec_side_effect(data, plugin_id, runner_type):
            data['add_file_to_pending_tasks'] = True
            return True

        ft.plugin_handler.exec_plugin_runner.side_effect = exec_side_effect

        result, _, _, decision_plugin = ft.should_file_be_added_to_task_list('/media/video.mp4')
        assert result is True
        assert decision_plugin['plugin_id'] == 'test_plugin'

    def test_returns_none_when_no_plugins_decide(self):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)
        ft.plugin_modules = []

        result, _, _, decision_plugin = ft.should_file_be_added_to_task_list('/media/video.mp4')
        assert result is None
        assert decision_plugin is None
