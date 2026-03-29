#!/usr/bin/env python3

"""
tests.unit.test_eventmonitor.py

Unit tests for compresso/libs/eventmonitor.
Tests EventHandler, EventMonitorManager, system config validation,
start/stop event processor, and event queue management.
"""

import queue
import threading
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_event_monitor():
    """Create an EventMonitorManager with mocked dependencies."""
    with (
        patch("compresso.libs.eventmonitor.CompressoLogging") as mock_log,
        patch("compresso.libs.eventmonitor.config.Config") as mock_config,
    ):
        mock_log.get_logger.return_value = MagicMock()
        mock_config.return_value = MagicMock()
        from compresso.libs.eventmonitor import EventMonitorManager

        data_queues = {
            "inotifytasks": queue.Queue(),
        }
        event = threading.Event()
        mgr = EventMonitorManager(data_queues, event)
    return mgr


@pytest.mark.unittest
class TestEventHandlerInit:
    def test_event_handler_init(self):
        from compresso.libs.eventmonitor import EventHandler

        files_to_test = queue.Queue()
        with patch("compresso.libs.eventmonitor.CompressoLogging") as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            handler = EventHandler(files_to_test, library_id=42)
        assert handler.library_id == 42
        assert not handler.abort_flag.is_set()


@pytest.mark.unittest
class TestEventHandlerOnAnyEvent:
    def test_created_event_adds_to_queue(self):
        from compresso.libs.eventmonitor import EventHandler

        files_to_test = queue.Queue()
        with patch("compresso.libs.eventmonitor.CompressoLogging") as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            handler = EventHandler(files_to_test, library_id=1)

        event = MagicMock()
        event.event_type = "created"
        event.is_directory = False
        event.src_path = "/media/new_file.mp4"
        handler.on_any_event(event)
        item = files_to_test.get_nowait()
        assert item["src_path"] == "/media/new_file.mp4"
        assert item["library_id"] == 1

    def test_closed_event_adds_to_queue(self):
        from compresso.libs.eventmonitor import EventHandler

        files_to_test = queue.Queue()
        with patch("compresso.libs.eventmonitor.CompressoLogging") as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            handler = EventHandler(files_to_test, library_id=2)

        event = MagicMock()
        event.event_type = "closed"
        event.is_directory = False
        event.src_path = "/media/file.mp4"
        handler.on_any_event(event)
        assert not files_to_test.empty()

    def test_directory_event_ignored(self):
        from compresso.libs.eventmonitor import EventHandler

        files_to_test = queue.Queue()
        with patch("compresso.libs.eventmonitor.CompressoLogging") as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            handler = EventHandler(files_to_test, library_id=1)

        event = MagicMock()
        event.event_type = "created"
        event.is_directory = True
        handler.on_any_event(event)
        assert files_to_test.empty()

    def test_modified_event_ignored(self):
        from compresso.libs.eventmonitor import EventHandler

        files_to_test = queue.Queue()
        with patch("compresso.libs.eventmonitor.CompressoLogging") as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            handler = EventHandler(files_to_test, library_id=1)

        event = MagicMock()
        event.event_type = "modified"
        event.is_directory = False
        handler.on_any_event(event)
        assert files_to_test.empty()

    def test_deleted_event_ignored(self):
        from compresso.libs.eventmonitor import EventHandler

        files_to_test = queue.Queue()
        with patch("compresso.libs.eventmonitor.CompressoLogging") as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            handler = EventHandler(files_to_test, library_id=1)

        event = MagicMock()
        event.event_type = "deleted"
        event.is_directory = False
        handler.on_any_event(event)
        assert files_to_test.empty()


@pytest.mark.unittest
class TestEventMonitorManagerInit:
    def test_init_attributes(self):
        mgr = _make_event_monitor()
        assert mgr.name == "EventMonitorManager"
        assert not mgr.abort_flag.is_set()
        assert mgr.event_observer_thread is None
        assert mgr.event_observer_threads == []

    def test_stop_sets_abort_flag(self):
        mgr = _make_event_monitor()
        mgr.stop()
        assert mgr.abort_flag.is_set()


@pytest.mark.unittest
class TestEventMonitorSystemConfig:
    @patch("compresso.libs.eventmonitor.PluginsHandler")
    def test_valid_config(self, mock_handler_cls):
        mgr = _make_event_monitor()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = []
        mock_handler_cls.return_value = mock_handler
        assert mgr.system_configuration_is_valid() is True

    @patch("compresso.libs.eventmonitor.PluginsHandler")
    def test_invalid_plugins(self, mock_handler_cls):
        mgr = _make_event_monitor()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = ["bad"]
        mock_handler_cls.return_value = mock_handler
        assert mgr.system_configuration_is_valid() is False


@pytest.mark.unittest
class TestStopEventProcessor:
    def test_stop_when_running(self):
        mgr = _make_event_monitor()
        mock_observer = MagicMock()
        mgr.event_observer_thread = mock_observer
        mgr.stop_event_processor()
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once()
        assert mgr.event_observer_thread is None

    def test_stop_when_not_running(self):
        mgr = _make_event_monitor()
        mgr.event_observer_thread = None
        mgr.stop_event_processor()  # Should not raise
        assert mgr.event_observer_thread is None


@pytest.mark.unittest
class TestStartEventProcessor:
    @patch("compresso.libs.eventmonitor.os.path.exists", return_value=True)
    @patch("compresso.libs.eventmonitor.Observer")
    @patch("compresso.libs.eventmonitor.Library")
    def test_start_with_inotify_enabled(self, mock_library_cls, mock_observer_cls, mock_exists):
        mgr = _make_event_monitor()
        mock_observer = MagicMock()
        mock_observer_cls.return_value = mock_observer
        mock_lib = MagicMock()
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_inotify.return_value = True
        mock_lib.get_path.return_value = "/media/lib"
        mock_lib.get_id.return_value = 1
        mock_library_cls.return_value = mock_lib
        mock_library_cls.get_all_libraries.return_value = [{"id": 1}]
        mgr.start_event_processor()
        mock_observer.schedule.assert_called_once()
        mock_observer.start.assert_called_once()
        assert mgr.event_observer_thread is mock_observer

    @patch("compresso.libs.eventmonitor.Library")
    @patch("compresso.libs.eventmonitor.Observer")
    def test_start_no_libraries_with_inotify(self, mock_observer_cls, mock_library_cls):
        mgr = _make_event_monitor()
        mock_observer = MagicMock()
        mock_observer_cls.return_value = mock_observer
        mock_lib = MagicMock()
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_inotify.return_value = False
        mock_library_cls.return_value = mock_lib
        mock_library_cls.get_all_libraries.return_value = [{"id": 1}]
        mgr.start_event_processor()
        mock_observer.start.assert_not_called()

    def test_start_when_already_running(self):
        mgr = _make_event_monitor()
        mgr.event_observer_thread = MagicMock()
        mgr.start_event_processor()  # Should log and skip

    @patch("compresso.libs.eventmonitor.Library")
    @patch("compresso.libs.eventmonitor.Observer")
    def test_start_remote_only_library_skipped(self, mock_observer_cls, mock_library_cls):
        mgr = _make_event_monitor()
        mock_observer = MagicMock()
        mock_observer_cls.return_value = mock_observer
        mock_lib = MagicMock()
        mock_lib.get_enable_remote_only.return_value = True
        mock_library_cls.return_value = mock_lib
        mock_library_cls.get_all_libraries.return_value = [{"id": 1}]
        mgr.start_event_processor()
        mock_observer.schedule.assert_not_called()
        mock_observer.start.assert_not_called()

    @patch("compresso.libs.eventmonitor.os.path.exists", return_value=False)
    @patch("compresso.libs.eventmonitor.Library")
    @patch("compresso.libs.eventmonitor.Observer")
    def test_start_path_not_exists(self, mock_observer_cls, mock_library_cls, mock_exists):
        mgr = _make_event_monitor()
        mock_observer = MagicMock()
        mock_observer_cls.return_value = mock_observer
        mock_lib = MagicMock()
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_inotify.return_value = True
        mock_lib.get_path.return_value = "/nonexistent"
        mock_library_cls.return_value = mock_lib
        mock_library_cls.get_all_libraries.return_value = [{"id": 1}]
        mgr.start_event_processor()
        mock_observer.schedule.assert_not_called()


@pytest.mark.unittest
class TestManageEventQueue:
    @patch("compresso.libs.eventmonitor.FileTest")
    def test_file_should_be_added(self, mock_filetest_cls):
        mgr = _make_event_monitor()
        mock_ft = MagicMock()
        mock_ft.should_file_be_added_to_task_list.return_value = (True, [], 100, None)
        mock_filetest_cls.return_value = mock_ft
        mgr.manage_event_queue("/media/file.mp4", 1)
        item = mgr.data_queues["inotifytasks"].get_nowait()
        assert item["pathname"] == "/media/file.mp4"
        assert item["priority_score"] == 100

    @patch("compresso.libs.eventmonitor.FileTest")
    def test_file_should_not_be_added(self, mock_filetest_cls):
        mgr = _make_event_monitor()
        mock_ft = MagicMock()
        mock_ft.should_file_be_added_to_task_list.return_value = (False, [{"message": "skip"}], 0, None)
        mock_filetest_cls.return_value = mock_ft
        mgr.manage_event_queue("/media/file.mp4", 1)
        assert mgr.data_queues["inotifytasks"].empty()

    @patch("compresso.libs.eventmonitor.FileTest")
    def test_unicode_error_handled(self, mock_filetest_cls):
        mgr = _make_event_monitor()
        mock_filetest_cls.side_effect = UnicodeEncodeError("utf-8", "", 0, 1, "error")
        mgr.manage_event_queue("/media/bad\udcfffile.mp4", 1)
        # Should not raise

    @patch("compresso.libs.eventmonitor.FileTest")
    def test_generic_exception_handled(self, mock_filetest_cls):
        mgr = _make_event_monitor()
        mock_filetest_cls.side_effect = Exception("unexpected")
        mgr.manage_event_queue("/media/file.mp4", 1)
        # Should not raise

    @patch("compresso.libs.eventmonitor.FileTest")
    def test_issues_logged_as_strings(self, mock_filetest_cls):
        mgr = _make_event_monitor()
        mock_ft = MagicMock()
        mock_ft.should_file_be_added_to_task_list.return_value = (False, ["simple string issue"], 0, None)
        mock_filetest_cls.return_value = mock_ft
        mgr.manage_event_queue("/media/file.mp4", 1)
        # Should log the string issue without error


@pytest.mark.unittest
class TestAddPathToQueue:
    def test_add_path_to_inotify_queue(self):
        mgr = _make_event_monitor()
        mgr._EventMonitorManager__add_path_to_queue("/media/file.mp4", 1, 50)
        item = mgr.data_queues["inotifytasks"].get_nowait()
        assert item["pathname"] == "/media/file.mp4"
        assert item["library_id"] == 1
        assert item["priority_score"] == 50
