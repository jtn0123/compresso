#!/usr/bin/env python3

"""
    tests.unit.test_foreman.py

    Unit tests for bug fixes in compresso.libs.foreman.Foreman.
"""

from unittest.mock import MagicMock, patch

import pytest


def _make_foreman():
    """Create a Foreman instance with mocked dependencies."""
    with patch('compresso.libs.foreman.WorkerGroup'), \
         patch('compresso.libs.foreman.installation_link'), \
         patch('compresso.libs.foreman.PluginsHandler'), \
         patch('compresso.libs.foreman.CompressoLogging'), \
         patch('compresso.libs.foreman.Foreman.configuration_changed', return_value=False):
        from compresso.libs.foreman import Foreman
        settings = MagicMock()
        settings.get_remote_installations.return_value = []
        data_queues = {}
        task_queue = MagicMock()
        event = MagicMock()
        foreman = Foreman(data_queues, settings, task_queue, event)
        return foreman


# ------------------------------------------------------------------
# TestFetchAvailableRemoteInstallation
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFetchAvailableRemoteInstallation:

    def test_returns_none_when_no_remotes_available(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {}
        installation_id, installation_info = foreman.fetch_available_remote_installation()
        assert installation_id is None
        assert installation_info == {}

    def test_returns_matching_installation(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1': {'address': '192.168.1.1', 'library_names': ['Movies']},
        }
        foreman.remote_task_manager_threads = {}
        installation_id, installation_info = foreman.fetch_available_remote_installation()
        assert installation_id == 'uuid-1'
        assert installation_info['address'] == '192.168.1.1'

    def test_filters_by_library_name(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1': {'address': '192.168.1.1', 'library_names': ['Movies']},
            'uuid-2': {'address': '192.168.1.2', 'library_names': ['TV']},
        }
        foreman.remote_task_manager_threads = {}
        installation_id, _ = foreman.fetch_available_remote_installation(library_name='TV')
        assert installation_id == 'uuid-2'

    def test_skips_already_running_threads(self):
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1': {'address': '192.168.1.1', 'library_names': ['Movies']},
        }
        foreman.remote_task_manager_threads = {'uuid-1': MagicMock()}
        installation_id, installation_info = foreman.fetch_available_remote_installation()
        assert installation_id is None
        assert installation_info == {}


# ------------------------------------------------------------------
# TestInitRemoteTaskManagerThread
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestInitRemoteTaskManagerThread:

    @patch('compresso.libs.foreman.installation_link')
    def test_returns_false_when_no_remote_available(self, mock_link):
        """Bug 1.1: should not KeyError when no remote is available."""
        foreman = _make_foreman()
        foreman.available_remote_managers = {}
        result = foreman.init_remote_task_manager_thread()
        assert result is False

    @patch('compresso.libs.foreman.installation_link')
    def test_removes_installation_from_available_after_init(self, mock_link):
        mock_thread = MagicMock()
        mock_link.RemoteTaskManager.return_value = mock_thread
        foreman = _make_foreman()
        foreman.available_remote_managers = {
            'uuid-1': {'address': '192.168.1.1', 'library_names': ['Movies']},
        }
        foreman.remote_task_manager_threads = {}
        result = foreman.init_remote_task_manager_thread()
        assert result is True
        assert 'uuid-1' not in foreman.available_remote_managers


# ------------------------------------------------------------------
# TestTerminateUnlinkedRemoteTaskManagerThreads
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestTerminateUnlinkedRemoteTaskManagerThreads:

    def _setup_foreman_with_thread(self, thread_uuid, thread_address, configured_installations):
        foreman = _make_foreman()
        foreman.settings.get_remote_installations.return_value = configured_installations

        mock_thread = MagicMock()
        mock_thread.get_info.return_value = {
            'installation_info': {'uuid': thread_uuid, 'address': thread_address}
        }
        foreman.remote_task_manager_threads = {'thread-1': mock_thread}
        foreman.mark_remote_task_manager_thread_as_redundant = MagicMock()
        return foreman

    def test_marks_thread_redundant_when_uuid_removed(self):
        foreman = self._setup_foreman_with_thread(
            'uuid-1', '192.168.1.1',
            configured_installations=[]  # UUID gone from config
        )
        foreman.terminate_unlinked_remote_task_manager_threads()
        foreman.mark_remote_task_manager_thread_as_redundant.assert_called_once_with('thread-1')

    def test_marks_thread_redundant_when_address_changed(self):
        """Bug 1.2: equality check, not substring."""
        foreman = self._setup_foreman_with_thread(
            'uuid-1', '192.168.1.1',
            configured_installations=[{'uuid': 'uuid-1', 'address': '192.168.1.10'}]
        )
        foreman.terminate_unlinked_remote_task_manager_threads()
        foreman.mark_remote_task_manager_thread_as_redundant.assert_called_once_with('thread-1')

    def test_keeps_thread_when_config_matches(self):
        foreman = self._setup_foreman_with_thread(
            'uuid-1', '192.168.1.1',
            configured_installations=[{'uuid': 'uuid-1', 'address': '192.168.1.1'}]
        )
        foreman.terminate_unlinked_remote_task_manager_threads()
        foreman.mark_remote_task_manager_thread_as_redundant.assert_not_called()


# ------------------------------------------------------------------
# TestManageEventSchedules
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestManageEventSchedules:

    @patch('compresso.libs.foreman.WorkerGroup')
    @patch('compresso.libs.foreman.datetime')
    def test_no_double_today_call(self, mock_datetime, mock_wg):
        """Bug 1.3: datetime.today() should be called once, not chained."""
        mock_today = MagicMock()
        mock_today.weekday.return_value = 0
        mock_today.strftime.return_value = '00:00'
        mock_datetime.today.return_value = mock_today

        mock_wg.get_all_worker_groups.return_value = []

        foreman = _make_foreman()
        foreman.last_schedule_run = None  # Force it to run
        foreman.manage_event_schedules()

        # datetime.today() should be called, but .today() should NOT be called on the result
        mock_datetime.today.assert_called()
        mock_today.today.assert_not_called()
