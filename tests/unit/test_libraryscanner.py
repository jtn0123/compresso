#!/usr/bin/env python3

"""
tests.unit.test_libraryscanner.py

Unit tests for compresso/libs/libraryscanner.LibraryScannerManager.
Tests library scanning logic, file traversal, schedule configuration,
and thread management.
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


def _make_scanner():
    """Create a LibraryScannerManager with mocked dependencies."""
    with (
        patch("compresso.libs.libraryscanner.CompressoLogging") as mock_log,
        patch("compresso.libs.libraryscanner.config.Config") as mock_config,
    ):
        mock_log.get_logger.return_value = MagicMock()
        mock_config.return_value = MagicMock()
        from compresso.libs.libraryscanner import LibraryScannerManager

        data_queues = {
            "scheduledtasks": queue.Queue(),
            "library_scanner_triggers": queue.Queue(),
        }
        event = threading.Event()
        mgr = LibraryScannerManager(data_queues, event)
    return mgr


@pytest.mark.unittest
class TestLibraryScannerInit:
    def test_init_attributes(self):
        mgr = _make_scanner()
        assert mgr.name == "LibraryScannerManager"
        assert mgr.interval == 0
        assert mgr.firstrun is True
        assert not mgr.abort_flag.is_set()

    def test_stop_sets_abort_flag(self):
        mgr = _make_scanner()
        mgr.stop()
        assert mgr.abort_flag.is_set()


@pytest.mark.unittest
class TestAbortIsSet:
    def test_abort_not_set_returns_false(self):
        mgr = _make_scanner()
        mgr.event.set()  # Don't block on wait
        assert mgr.abort_is_set() is False

    def test_abort_set_returns_true(self):
        mgr = _make_scanner()
        mgr.abort_flag.set()
        assert mgr.abort_is_set() is True


@pytest.mark.unittest
class TestSystemConfigurationIsValid:
    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_valid_config(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = []
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = True
        assert mgr.system_configuration_is_valid() is True

    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_incompatible_plugins(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = ["bad_plugin"]
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = True
        assert mgr.system_configuration_is_valid() is False

    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_library_count_exceeded(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = []
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = False
        assert mgr.system_configuration_is_valid() is False


@pytest.mark.unittest
class TestAddPathToQueue:
    def test_add_path_puts_to_queue(self):
        mgr = _make_scanner()
        mgr.add_path_to_queue("/media/video.mp4", 1, 100)
        item = mgr.scheduledtasks.get_nowait()
        assert item["pathname"] == "/media/video.mp4"
        assert item["library_id"] == 1
        assert item["priority_score"] == 100


@pytest.mark.unittest
class TestFileTestsInProgress:
    def test_no_managers_returns_false(self):
        mgr = _make_scanner()
        mgr.file_test_managers = {}
        assert mgr.file_tests_in_progress() is False

    def test_with_busy_manager_returns_true(self):
        mgr = _make_scanner()
        mock_manager = MagicMock()
        mock_manager.is_testing_file.return_value = True
        mgr.file_test_managers = {"m1": mock_manager}
        assert mgr.file_tests_in_progress() is True

    def test_with_idle_manager_returns_false(self):
        mgr = _make_scanner()
        mock_manager = MagicMock()
        mock_manager.is_testing_file.return_value = False
        mgr.file_test_managers = {"m1": mock_manager}
        assert mgr.file_tests_in_progress() is False

    def test_with_manager_without_is_testing_file(self):
        mgr = _make_scanner()
        mock_manager = MagicMock(spec=[])
        mgr.file_test_managers = {"m1": mock_manager}
        assert mgr.file_tests_in_progress() is False


@pytest.mark.unittest
class TestStopAllFileTestManagers:
    def test_stop_all(self):
        mgr = _make_scanner()
        m1 = MagicMock()
        m2 = MagicMock()
        m1.abort_flag = MagicMock()
        m2.abort_flag = MagicMock()
        mgr.file_test_managers = {"m1": m1, "m2": m2}
        mgr.stop_all_file_test_managers()
        m1.abort_flag.set.assert_called_once()
        m2.abort_flag.set.assert_called_once()


@pytest.mark.unittest
class TestStartResultsManagerThread:
    @patch("compresso.libs.libraryscanner.FileTesterThread")
    def test_starts_thread(self, mock_tester_cls):
        mgr = _make_scanner()
        mock_thread = MagicMock()
        mock_tester_cls.return_value = mock_thread
        status_updates = queue.Queue()
        mgr.start_results_manager_thread("t1", status_updates, 1)
        mock_thread.start.assert_called_once()
        assert "t1" in mgr.file_test_managers


@pytest.mark.unittest
class TestUpdateScanProgress:
    def test_update_scan_progress(self):
        from compresso.libs.libraryscanner import LibraryScannerManager

        mock_frontend = MagicMock()
        LibraryScannerManager.update_scan_progress(mock_frontend, "Testing: file.mp4")
        mock_frontend.update.assert_called_once()
        call_arg = mock_frontend.update.call_args[0][0]
        assert call_arg["id"] == "libraryScanProgress"
        assert call_arg["message"] == "Testing: file.mp4"


@pytest.mark.unittest
class TestScheduledJob:
    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_invalid_config_skips(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = ["bad"]
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = True
        mgr.scheduled_job()
        mock_library_cls.get_all_libraries.assert_not_called()

    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_no_libraries_configured(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = []
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = True
        mock_library_cls.get_all_libraries.return_value = []
        mgr.scheduled_job()

    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_remote_only_library_skipped(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = []
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = True
        mock_library_cls.get_all_libraries.return_value = [{"id": 1}]
        mock_lib = MagicMock()
        mock_lib.get_enable_remote_only.return_value = True
        mock_library_cls.return_value = mock_lib
        with patch.object(mgr, "scan_library_path") as mock_scan:
            mgr.scheduled_job()
            mock_scan.assert_not_called()

    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_scanner_disabled_library_skipped(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = []
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = True
        mock_library_cls.get_all_libraries.return_value = [{"id": 1}]
        mock_lib = MagicMock()
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_scanner.return_value = False
        mock_library_cls.return_value = mock_lib
        with patch.object(mgr, "scan_library_path") as mock_scan:
            mgr.scheduled_job()
            mock_scan.assert_not_called()

    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_scanner_enabled_library_scanned(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = []
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = True
        mock_library_cls.get_all_libraries.return_value = [{"id": 1}]
        mock_lib = MagicMock()
        mock_lib.get_enable_remote_only.return_value = False
        mock_lib.get_enable_scanner.return_value = True
        mock_lib.get_name.return_value = "TestLib"
        mock_lib.get_path.return_value = "/media/lib"
        mock_lib.get_id.return_value = 1
        mock_library_cls.return_value = mock_lib
        with patch.object(mgr, "scan_library_path") as mock_scan:
            mgr.scheduled_job()
            mock_scan.assert_called_once_with("TestLib", "/media/lib", 1)

    @patch("compresso.libs.libraryscanner.Library")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    def test_library_init_exception_handled(self, mock_handler_cls, mock_library_cls):
        mgr = _make_scanner()
        mock_handler = MagicMock()
        mock_handler.get_incompatible_enabled_plugins.return_value = []
        mock_handler_cls.return_value = mock_handler
        mock_library_cls.within_library_count_limits.return_value = True
        mock_library_cls.get_all_libraries.return_value = [{"id": 1}]
        mock_library_cls.side_effect = Exception("DB error")
        # Should not raise
        mgr.scheduled_job()


@pytest.mark.unittest
class TestScanLibraryPath:
    @patch("compresso.libs.libraryscanner.os.path.exists", return_value=False)
    def test_path_not_exists(self, mock_exists):
        mgr = _make_scanner()
        mgr.scan_library_path("TestLib", "/nonexistent", 1)
        # Should return early without error

    @patch("compresso.libs.libraryscanner.gc")
    @patch("compresso.libs.libraryscanner.PluginsHandler")
    @patch("compresso.libs.libraryscanner.CompressoLogging")
    @patch("compresso.libs.libraryscanner.FrontendPushMessages")
    @patch("compresso.libs.libraryscanner.os.walk")
    @patch("compresso.libs.libraryscanner.os.path.exists", return_value=True)
    def test_scan_empty_directory(self, mock_exists, mock_walk, mock_frontend_cls, mock_logging, mock_plugins, mock_gc):
        mgr = _make_scanner()
        mgr.settings.get_debugging.return_value = False
        mgr.settings.get_concurrent_file_testers.return_value = 1
        mgr.settings.get_follow_symlinks.return_value = False
        mock_frontend = MagicMock()
        mock_frontend_cls.return_value = mock_frontend
        mock_walk.return_value = []
        mock_logging.log_metric = MagicMock()
        mock_logging.log_data = MagicMock()
        mock_handler = MagicMock()
        mock_plugins.return_value = mock_handler

        with patch.object(mgr, "start_results_manager_thread"), patch.object(mgr, "stop_all_file_test_managers"):
            # Set abort to break out of the wait loop
            mgr.abort_flag.set()
            mgr.scan_library_path("TestLib", "/media/lib", 1)

        mock_frontend.remove_item.assert_called_with("libraryScanProgress")


@pytest.mark.unittest
class TestRegisterCompresso:
    @patch("compresso.libs.session.Session")
    def test_register(self, mock_session_cls):
        mgr = _make_scanner()
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session
        mgr.register_compresso()
        mock_session.register_compresso.assert_called_once()
