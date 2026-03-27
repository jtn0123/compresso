#!/usr/bin/env python3

"""
tests.unit.test_filetest_extended.py

Extended tests for compresso.libs.filetest covering uncovered code paths.
Covers: codec pre-filter logic, FileTesterThread lifecycle.
"""

import queue
import threading
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType

FILETEST_MOD = "compresso.libs.filetest"


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_filetest():
    """Create a FileTest instance with mocked dependencies."""
    with (
        patch(f"{FILETEST_MOD}.config.Config"),
        patch(f"{FILETEST_MOD}.CompressoLogging"),
        patch(f"{FILETEST_MOD}.PluginsHandler") as mock_ph,
    ):
        mock_ph.return_value.get_enabled_plugin_modules_by_type.return_value = []
        from compresso.libs.filetest import FileTest

        ft = FileTest(library_id=1)
        return ft


# ------------------------------------------------------------------
# Codec pre-filter tests
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestFileTestCodecPreFilter:
    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_skip_codec_match_returns_false(self, mock_lib_cls, mock_meta):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)

        mock_library = MagicMock()
        mock_library.get_target_codecs.return_value = []
        mock_library.get_skip_codecs.return_value = ["hevc"]
        mock_lib_cls.return_value = mock_library

        mock_meta.return_value = {"codec": "hevc"}
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/media/video.mp4")
        assert result is False
        assert any(i["id"] == "codec_skip" for i in issues)

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_target_codec_not_in_list_returns_false(self, mock_lib_cls, mock_meta):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)

        mock_library = MagicMock()
        mock_library.get_target_codecs.return_value = ["h264"]
        mock_library.get_skip_codecs.return_value = []
        mock_lib_cls.return_value = mock_library

        mock_meta.return_value = {"codec": "hevc"}
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/media/video.mp4")
        assert result is False
        assert any(i["id"] == "codec_target" for i in issues)

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_target_codec_in_list_continues(self, mock_lib_cls, mock_meta):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)

        mock_library = MagicMock()
        mock_library.get_target_codecs.return_value = ["hevc"]
        mock_library.get_skip_codecs.return_value = []
        mock_lib_cls.return_value = mock_library

        mock_meta.return_value = {"codec": "hevc"}
        # No plugins, so result should be None (no decision)
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/media/video.mp4")
        assert result is None

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_codec_with_estimated_suffix(self, mock_lib_cls, mock_meta):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)

        mock_library = MagicMock()
        mock_library.get_target_codecs.return_value = []
        mock_library.get_skip_codecs.return_value = ["hevc"]
        mock_lib_cls.return_value = mock_library

        mock_meta.return_value = {"codec": "hevc (estimated)"}
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/media/video.mp4")
        assert result is False

    @patch("compresso.libs.ffprobe_utils.extract_media_metadata")
    @patch("compresso.libs.library.Library")
    def test_codec_probe_failure_continues(self, mock_lib_cls, mock_meta):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)

        mock_library = MagicMock()
        mock_library.get_target_codecs.return_value = ["hevc"]
        mock_library.get_skip_codecs.return_value = []
        mock_lib_cls.return_value = mock_library

        mock_meta.side_effect = Exception("probe failed")
        # Should continue without error
        result, issues, _, _ = ft.should_file_be_added_to_task_list("/media/video.mp4")
        assert result is None

    @patch("compresso.libs.library.Library")
    def test_no_codecs_configured_skips_filter(self, mock_lib_cls):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)

        mock_library = MagicMock()
        mock_library.get_target_codecs.return_value = []
        mock_library.get_skip_codecs.return_value = []
        mock_lib_cls.return_value = mock_library

        result, issues, _, _ = ft.should_file_be_added_to_task_list("/media/video.mp4")
        assert result is None


# ------------------------------------------------------------------
# Plugin exec_plugin_runner returning False
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestFileTestPluginExecFailure:
    @patch("compresso.libs.library.Library")
    def test_plugin_exec_returns_false_continues(self, mock_lib_cls):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=False)
        ft.file_failed_in_history = MagicMock(return_value=False)

        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = []
        mock_lib.get_skip_codecs.return_value = []
        mock_lib_cls.return_value = mock_lib

        mock_module = {"plugin_id": "test_plugin", "name": "Test Plugin"}
        ft.plugin_modules = [mock_module]
        ft.plugin_handler.exec_plugin_runner = MagicMock(return_value=False)

        result, _, _, decision_plugin = ft.should_file_be_added_to_task_list("/media/video.mp4")
        # Plugin returned False so it should continue (no decision)
        assert result is None
        assert decision_plugin is None


# ------------------------------------------------------------------
# Both ignore file and history
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestFileTestBothFlags:
    @patch("compresso.libs.library.Library")
    def test_both_ignore_and_history_returns_false(self, mock_lib_cls):
        ft = _make_filetest()
        ft.file_in_compresso_ignore_lockfile = MagicMock(return_value=True)
        ft.file_failed_in_history = MagicMock(return_value=True)

        mock_lib = MagicMock()
        mock_lib.get_target_codecs.return_value = []
        mock_lib.get_skip_codecs.return_value = []
        mock_lib_cls.return_value = mock_lib

        result, issues, _, _ = ft.should_file_be_added_to_task_list("/media/video.mp4")
        assert result is False
        assert len(issues) == 2


# ------------------------------------------------------------------
# FileTesterThread
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestFileTesterThread:
    @patch("compresso.libs.filetest.config.Config")
    @patch("compresso.libs.filetest.CompressoLogging")
    def test_thread_stop_and_is_testing(self, _log, _cfg):
        from compresso.libs.filetest import FileTesterThread

        files_to_test = queue.Queue()
        files_to_process = queue.Queue()
        status_updates = queue.Queue()
        event = threading.Event()

        ftt = FileTesterThread(
            name="test-thread",
            files_to_test=files_to_test,
            files_to_process=files_to_process,
            status_updates=status_updates,
            library_id=1,
            event=event,
        )

        assert ftt.is_testing_file() is False
        ftt._set_testing_state(True)
        assert ftt.is_testing_file() is True
        ftt._set_testing_state(False)
        assert ftt.is_testing_file() is False

        ftt.stop()
        assert ftt.abort_flag.is_set()

    @patch("compresso.libs.filetest.config.Config")
    @patch("compresso.libs.filetest.CompressoLogging")
    def test_add_path_to_queue(self, _log, _cfg):
        from compresso.libs.filetest import FileTesterThread

        files_to_test = queue.Queue()
        files_to_process = queue.Queue()
        status_updates = queue.Queue()
        event = threading.Event()

        ftt = FileTesterThread(
            name="test-thread",
            files_to_test=files_to_test,
            files_to_process=files_to_process,
            status_updates=status_updates,
            library_id=1,
            event=event,
        )

        ftt.add_path_to_queue({"path": "/test.mp4", "priority_score": 10})
        assert not files_to_process.empty()
        item = files_to_process.get_nowait()
        assert item["path"] == "/test.mp4"
