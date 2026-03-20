#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_child_process.py

    Unit tests for compresso.libs.unplugins.child_process.
"""

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture(autouse=True)
def reset_child_process_globals():
    """Reset module-level globals between tests."""
    import compresso.libs.unplugins.child_process as cp
    cp._active_plugin_pids = set()
    cp._shared_manager = None
    yield
    cp._active_plugin_pids = set()
    cp._shared_manager = None


@pytest.mark.unittest
class TestRegisterPid:

    def test_adds_pid_to_active_set(self):
        from compresso.libs.unplugins.child_process import _register_pid, _active_plugin_pids
        _register_pid(1234)
        assert 1234 in _active_plugin_pids

    def test_adding_same_pid_twice(self):
        from compresso.libs.unplugins.child_process import _register_pid, _active_plugin_pids
        _register_pid(1234)
        _register_pid(1234)
        assert len(_active_plugin_pids) == 1


@pytest.mark.unittest
class TestUnregisterPid:

    def test_removes_pid_from_active_set(self):
        from compresso.libs.unplugins.child_process import _register_pid, _unregister_pid, _active_plugin_pids
        _register_pid(5678)
        _unregister_pid(5678)
        assert 5678 not in _active_plugin_pids

    def test_unregister_nonexistent_pid_does_not_raise(self):
        from compresso.libs.unplugins.child_process import _unregister_pid
        # Should not raise
        _unregister_pid(9999)


@pytest.mark.unittest
class TestKillAllPluginProcesses:

    def test_kills_registered_processes(self):
        from compresso.libs.unplugins.child_process import _register_pid, kill_all_plugin_processes, _active_plugin_pids

        _register_pid(100)
        _register_pid(200)

        mock_proc = MagicMock()
        mock_proc.children.return_value = []

        with patch('compresso.libs.unplugins.child_process.psutil.Process', return_value=mock_proc), \
             patch('compresso.libs.unplugins.child_process.psutil.wait_procs', return_value=([], [])):
            kill_all_plugin_processes()

        assert len(_active_plugin_pids) == 0
        mock_proc.terminate.assert_called()

    def test_handles_no_such_process(self):
        import psutil
        from compresso.libs.unplugins.child_process import _register_pid, kill_all_plugin_processes

        _register_pid(300)

        with patch('compresso.libs.unplugins.child_process.psutil.Process',
                   side_effect=psutil.NoSuchProcess(300)):
            # Should not raise
            kill_all_plugin_processes()

    def test_clears_pids_set(self):
        from compresso.libs.unplugins.child_process import _register_pid, kill_all_plugin_processes, _active_plugin_pids

        _register_pid(400)

        mock_proc = MagicMock()
        mock_proc.children.return_value = []

        with patch('compresso.libs.unplugins.child_process.psutil.Process', return_value=mock_proc), \
             patch('compresso.libs.unplugins.child_process.psutil.wait_procs', return_value=([], [])):
            kill_all_plugin_processes()

        assert len(_active_plugin_pids) == 0

    def test_force_kills_alive_processes(self):
        from compresso.libs.unplugins.child_process import _register_pid, kill_all_plugin_processes

        _register_pid(500)

        mock_proc = MagicMock()
        mock_proc.children.return_value = []
        alive_proc = MagicMock()

        with patch('compresso.libs.unplugins.child_process.psutil.Process', return_value=mock_proc), \
             patch('compresso.libs.unplugins.child_process.psutil.wait_procs',
                   side_effect=[([], [alive_proc]), ([], [])]):
            kill_all_plugin_processes()

        alive_proc.kill.assert_called_once()


@pytest.mark.unittest
class TestSetSharedManager:

    def test_sets_global_manager(self):
        import compresso.libs.unplugins.child_process as cp
        mock_mgr = MagicMock()
        cp.set_shared_manager(mock_mgr)
        assert cp._shared_manager is mock_mgr


@pytest.mark.unittest
class TestPluginChildProcessInit:

    def test_requires_shared_manager(self):
        import compresso.libs.unplugins.child_process as cp
        cp._shared_manager = None

        with patch('compresso.libs.unplugins.child_process.CompressoLogging') as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            with pytest.raises(RuntimeError, match="shared Manager"):
                cp.PluginChildProcess('test_plugin', {})

    def test_init_with_shared_manager(self):
        import compresso.libs.unplugins.child_process as cp
        mock_mgr = MagicMock()
        mock_mgr.Queue.return_value = MagicMock()
        cp._shared_manager = mock_mgr

        with patch('compresso.libs.unplugins.child_process.CompressoLogging') as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            pcp = cp.PluginChildProcess('test_plugin', {'worker_log': [], 'current_command': []})
            assert pcp.manager is mock_mgr
            assert pcp.data == {'worker_log': [], 'current_command': []}


@pytest.mark.unittest
class TestPluginChildProcessSetCurrentCommand:

    def test_sets_command(self):
        import compresso.libs.unplugins.child_process as cp
        mock_mgr = MagicMock()
        mock_mgr.Queue.return_value = MagicMock()
        cp._shared_manager = mock_mgr

        with patch('compresso.libs.unplugins.child_process.CompressoLogging') as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            current_cmd = []
            pcp = cp.PluginChildProcess('test_plugin', {
                'worker_log': [],
                'current_command': current_cmd,
            })
            pcp._set_current_command('ffmpeg -i test.mkv')
            assert current_cmd == ['ffmpeg -i test.mkv']

    def test_set_command_with_non_list_is_noop(self):
        import compresso.libs.unplugins.child_process as cp
        mock_mgr = MagicMock()
        mock_mgr.Queue.return_value = MagicMock()
        cp._shared_manager = mock_mgr

        with patch('compresso.libs.unplugins.child_process.CompressoLogging') as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            pcp = cp.PluginChildProcess('test_plugin', {
                'worker_log': [],
                'current_command': 'not_a_list',
            })
            # Should not raise
            pcp._set_current_command('test')


@pytest.mark.unittest
class TestPluginChildProcessClearCurrentCommand:

    def test_clears_command(self):
        import compresso.libs.unplugins.child_process as cp
        mock_mgr = MagicMock()
        mock_mgr.Queue.return_value = MagicMock()
        cp._shared_manager = mock_mgr

        with patch('compresso.libs.unplugins.child_process.CompressoLogging') as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            current_cmd = ['some command']
            pcp = cp.PluginChildProcess('test_plugin', {
                'worker_log': [],
                'current_command': current_cmd,
            })
            pcp._clear_current_command()
            assert current_cmd == []

    def test_clear_with_non_list_is_noop(self):
        import compresso.libs.unplugins.child_process as cp
        mock_mgr = MagicMock()
        mock_mgr.Queue.return_value = MagicMock()
        cp._shared_manager = mock_mgr

        with patch('compresso.libs.unplugins.child_process.CompressoLogging') as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            pcp = cp.PluginChildProcess('test_plugin', {
                'worker_log': [],
                'current_command': None,
            })
            # Should not raise
            pcp._clear_current_command()


@pytest.mark.unittest
class TestPluginChildProcessRun:

    def test_run_launches_process_and_returns(self):
        import compresso.libs.unplugins.child_process as cp
        mock_mgr = MagicMock()
        mock_mgr.Queue.return_value = MagicMock()
        cp._shared_manager = mock_mgr

        with patch('compresso.libs.unplugins.child_process.CompressoLogging') as mock_log:
            mock_log.get_logger.return_value = MagicMock()
            pcp = cp.PluginChildProcess('test_plugin', {
                'worker_log': [],
                'current_command': [],
                'command_progress_parser': MagicMock(),
            })

            mock_proc = MagicMock()
            mock_proc.pid = 12345
            mock_proc.is_alive.return_value = False
            mock_proc.exitcode = 0

            with patch('multiprocessing.Process', return_value=mock_proc), \
                 patch.object(pcp, '_monitor', return_value=True):
                target_fn = MagicMock()
                result = pcp.run(target_fn)
                assert result is True
                mock_proc.start.assert_called_once()
