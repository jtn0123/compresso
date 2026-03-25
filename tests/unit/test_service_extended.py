#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_service_extended.py

    Extended unit tests for compresso/service.py.
    Covers init_db, argument parsing, RootService thread orchestration,
    signal handlers, stop_threads, start_threads order, and startup readiness.
"""

import signal
from unittest.mock import patch, MagicMock

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.mark.unittest
class TestInitDb:

    @patch('compresso.service.Migrations')
    @patch('compresso.libs.unmodels.lib.Database.select_database')
    @patch('compresso.service.os.path.exists', return_value=True)
    def test_init_db_returns_connection(self, mock_exists, mock_select_db, mock_migrations):
        from compresso.service import init_db
        mock_conn = MagicMock()
        mock_select_db.return_value = mock_conn
        result = init_db('/tmp/config')
        assert result is mock_conn
        mock_select_db.assert_called_once()
        mock_migrations.return_value.update_schema.assert_called_once()

    @patch('compresso.service.Migrations')
    @patch('compresso.libs.unmodels.lib.Database.select_database')
    @patch('compresso.service.os.path.exists', return_value=False)
    @patch('compresso.service.os.makedirs')
    def test_init_db_creates_config_path(self, mock_makedirs, mock_exists,
                                          mock_select_db, mock_migrations):
        from compresso.service import init_db
        mock_select_db.return_value = MagicMock()
        init_db('/tmp/new_config')
        mock_makedirs.assert_called_once_with('/tmp/new_config')

    @patch('compresso.service.Migrations')
    @patch('compresso.libs.unmodels.lib.Database.select_database')
    @patch('compresso.service.os.path.exists', return_value=True)
    def test_init_db_database_settings(self, mock_exists, mock_select_db, mock_migrations):
        from compresso.service import init_db
        mock_select_db.return_value = MagicMock()
        init_db('/config/path')
        call_args = mock_select_db.call_args[0][0]
        assert call_args['TYPE'] == 'SQLITE'
        assert 'compresso.db' in call_args['FILE']
        assert 'migrations_v1' in call_args['MIGRATIONS_DIR']


@pytest.mark.unittest
class TestRootServiceInit:

    @patch('compresso.service.CompressoLogging')
    @patch('compresso.service.startup.StartupState')
    def test_init_attributes(self, mock_startup, mock_log):
        mock_log.get_logger.return_value = MagicMock()
        mock_log.metric = MagicMock()
        from compresso.service import RootService
        service = RootService()
        assert service.threads == []
        assert service.run_threads is True
        assert service.db_connection is None
        assert service.developer is None
        assert service.dev_api is None


@pytest.mark.unittest
class TestRootServiceStop:

    @patch('compresso.service.CompressoLogging')
    @patch('compresso.service.startup.StartupState')
    def test_stop_sets_flag(self, mock_startup, mock_log):
        mock_log.get_logger.return_value = MagicMock()
        mock_log.metric = MagicMock()
        from compresso.service import RootService
        service = RootService()
        service.stop()
        assert service.run_threads is False


@pytest.mark.unittest
class TestRootServiceSigHandle:

    @patch('compresso.service.CompressoLogging')
    @patch('compresso.service.startup.StartupState')
    def test_sig_handle_calls_stop(self, mock_startup, mock_log):
        mock_log.get_logger.return_value = MagicMock()
        mock_log.metric = MagicMock()
        from compresso.service import RootService
        service = RootService()
        service.sig_handle(signal.SIGTERM, None)
        assert service.run_threads is False


@pytest.mark.unittest
class TestVerifyThreadStarted:

    @patch('compresso.service.CompressoLogging')
    @patch('compresso.service.startup.StartupState')
    def test_alive_thread_passes(self, mock_startup, mock_log):
        mock_log.get_logger.return_value = MagicMock()
        mock_log.metric = MagicMock()
        from compresso.service import RootService
        service = RootService()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        service._verify_thread_started('TestThread', mock_thread, timeout=1)

    @patch('compresso.service.CompressoLogging')
    @patch('compresso.service.startup.StartupState')
    def test_dead_thread_raises(self, mock_startup, mock_log):
        mock_log.get_logger.return_value = MagicMock()
        mock_log.metric = MagicMock()
        from compresso.service import RootService
        service = RootService()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        with pytest.raises(RuntimeError, match="did not remain alive"):
            service._verify_thread_started('DeadThread', mock_thread, timeout=0.2)


@pytest.mark.unittest
class TestStopThreads:

    @patch('compresso.service.CompressoLogging')
    @patch('compresso.service.startup.StartupState')
    def test_stop_threads_calls_stop_and_join(self, mock_startup, mock_log):
        mock_log.get_logger.return_value = MagicMock()
        mock_log.metric = MagicMock()
        from compresso.service import RootService
        service = RootService()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = False
        service.threads = [{'name': 'Test', 'thread': mock_thread}]
        service.stop_threads()
        mock_thread.stop.assert_called_once()
        mock_thread.join.assert_called_once_with(10)
        assert service.threads == []
        assert service.event.is_set()

    @patch('compresso.service.CompressoLogging')
    @patch('compresso.service.startup.StartupState')
    def test_stop_threads_timeout_logged(self, mock_startup, mock_log):
        mock_log.get_logger.return_value = MagicMock()
        mock_log.metric = MagicMock()
        from compresso.service import RootService
        service = RootService()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True  # Thread doesn't die
        service.threads = [{'name': 'Stubborn', 'thread': mock_thread}]
        service.stop_threads()
        # Should log error about thread not stopping
        service.logger.error.assert_called()


@pytest.mark.unittest
class TestStartThreadMethods:

    def _make_service(self):
        with patch('compresso.service.CompressoLogging') as mock_log, \
             patch('compresso.service.startup.StartupState'):
            mock_log.get_logger.return_value = MagicMock()
            mock_log.metric = MagicMock()
            from compresso.service import RootService
            service = RootService()
        return service

    @patch('compresso.service.TaskHandler')
    def test_start_handler(self, mock_handler_cls):
        service = self._make_service()
        mock_handler = MagicMock()
        mock_handler.is_alive.return_value = True
        mock_handler_cls.return_value = mock_handler
        data_queues = {}
        task_queue = MagicMock()
        service.start_handler(data_queues, task_queue)
        mock_handler.start.assert_called_once()
        assert len(service.threads) == 1
        assert service.threads[0]['name'] == 'TaskHandler'

    @patch('compresso.service.PostProcessor')
    def test_start_post_processor(self, mock_pp_cls):
        service = self._make_service()
        mock_pp = MagicMock()
        mock_pp.is_alive.return_value = True
        mock_pp_cls.return_value = mock_pp
        service.start_post_processor({}, MagicMock())
        mock_pp.start.assert_called_once()
        assert service.threads[0]['name'] == 'PostProcessor'

    @patch('compresso.service.Foreman')
    def test_start_foreman(self, mock_foreman_cls):
        service = self._make_service()
        mock_foreman = MagicMock()
        mock_foreman.is_alive.return_value = True
        mock_foreman_cls.return_value = mock_foreman
        service.start_foreman({}, MagicMock(), MagicMock())
        mock_foreman.start.assert_called_once()
        assert service.threads[0]['name'] == 'Foreman'

    @patch('compresso.service.libraryscanner.LibraryScannerManager')
    def test_start_library_scanner(self, mock_scanner_cls):
        service = self._make_service()
        mock_scanner = MagicMock()
        mock_scanner.is_alive.return_value = True
        mock_scanner_cls.return_value = mock_scanner
        service.start_library_scanner_manager({})
        mock_scanner.start.assert_called_once()
        assert service.threads[0]['name'] == 'LibraryScannerManager'

    @patch('compresso.service.ScheduledTasksManager')
    def test_start_scheduled_tasks_manager(self, mock_stm_cls):
        service = self._make_service()
        mock_stm = MagicMock()
        mock_stm.is_alive.return_value = True
        mock_stm_cls.return_value = mock_stm
        service.start_scheduled_tasks_manager()
        mock_stm.start.assert_called_once()
        assert service.threads[0]['name'] == 'ScheduledTasksManager'

    @patch('compresso.service.UIServer')
    def test_start_ui_server(self, mock_ui_cls):
        service = self._make_service()
        mock_ui = MagicMock()
        mock_ui_cls.return_value = mock_ui
        service.start_ui_server({}, MagicMock())
        mock_ui.start.assert_called_once()
        assert service.threads[0]['name'] == 'UIServer'


@pytest.mark.unittest
class TestStartInotifyWatchManager:

    def _make_service(self):
        with patch('compresso.service.CompressoLogging') as mock_log, \
             patch('compresso.service.startup.StartupState'):
            mock_log.get_logger.return_value = MagicMock()
            mock_log.metric = MagicMock()
            from compresso.service import RootService
            service = RootService()
        return service

    @patch('compresso.service.eventmonitor.event_monitor_module', 'watchdog')
    @patch('compresso.service.eventmonitor.EventMonitorManager')
    def test_with_watchdog_available(self, mock_emm_cls):
        service = self._make_service()
        mock_emm = MagicMock()
        mock_emm.is_alive.return_value = True
        mock_emm_cls.return_value = mock_emm
        service.start_inotify_watch_manager({}, MagicMock())
        mock_emm.start.assert_called_once()
        assert service.threads[0]['name'] == 'EventMonitorManager'

    @patch('compresso.service.eventmonitor.event_monitor_module', None)
    def test_without_watchdog(self):
        service = self._make_service()
        result = service.start_inotify_watch_manager({}, MagicMock())
        assert result is None
        assert len(service.threads) == 0


@pytest.mark.unittest
class TestLogStartupSummary:

    def _make_service(self):
        with patch('compresso.service.CompressoLogging') as mock_log, \
             patch('compresso.service.startup.StartupState'):
            mock_log.get_logger.return_value = MagicMock()
            mock_log.metric = MagicMock()
            from compresso.service import RootService
            service = RootService()
        return service

    @patch('compresso.service.startup.build_startup_summary')
    def test_log_startup_summary(self, mock_build):
        service = self._make_service()
        mock_build.return_value = {
            'library_path': '/media',
            'cache_path': '/cache',
            'config_path': '/config',
            'enable_library_scanner': True,
            'run_full_scan_on_start': False,
            'concurrent_file_testers': 2,
            'worker_count': 3,
            'event_monitor_active': True,
            'safe_defaults': False,
        }
        mock_settings = MagicMock()
        service.log_startup_summary(mock_settings)
        assert service.logger.info.call_count >= 3


@pytest.mark.unittest
class TestWaitForStartupReadiness:

    def _make_service(self):
        with patch('compresso.service.CompressoLogging') as mock_log, \
             patch('compresso.service.startup.StartupState'):
            mock_log.get_logger.return_value = MagicMock()
            mock_log.metric = MagicMock()
            from compresso.service import RootService
            service = RootService()
        return service

    def test_ready_returns_snapshot(self):
        service = self._make_service()
        service.startup_state.snapshot.return_value = {'ready': True, 'stages': {}}
        mock_settings = MagicMock()
        mock_settings.get_startup_readiness_timeout_seconds.return_value = 1
        result = service.wait_for_startup_readiness(mock_settings)
        assert result['ready'] is True

    def test_errors_raise(self):
        service = self._make_service()
        service.startup_state.snapshot.return_value = {
            'ready': False,
            'errors': ['config_loaded'],
            'stages': {},
        }
        mock_settings = MagicMock()
        mock_settings.get_startup_readiness_timeout_seconds.return_value = 0.1
        with pytest.raises(RuntimeError, match="Startup readiness check failed"):
            service.wait_for_startup_readiness(mock_settings)

    def test_timeout_raises(self):
        service = self._make_service()
        service.startup_state.snapshot.return_value = {
            'ready': False,
            'errors': [],
            'stages': {},
            'details': {},
        }
        mock_settings = MagicMock()
        mock_settings.get_startup_readiness_timeout_seconds.return_value = 0.1
        with pytest.raises(RuntimeError, match="Startup readiness check failed"):
            service.wait_for_startup_readiness(mock_settings)


@pytest.mark.unittest
class TestStartThreadsOrchestration:

    def _make_service(self):
        with patch('compresso.service.CompressoLogging') as mock_log, \
             patch('compresso.service.startup.StartupState'):
            mock_log.get_logger.return_value = MagicMock()
            mock_log.metric = MagicMock()
            from compresso.service import RootService
            service = RootService()
        return service

    @patch('compresso.service.common.clean_files_in_cache_dir')
    @patch('compresso.service.TaskQueue')
    def test_start_threads_calls_all(self, mock_tq_cls, mock_clean):
        service = self._make_service()
        mock_settings = MagicMock()
        mock_settings.get_cache_path.return_value = '/tmp/cache'
        with patch.object(service, 'initial_register_compresso'), \
             patch.object(service, 'start_post_processor', return_value=MagicMock()), \
             patch.object(service, 'start_foreman', return_value=MagicMock()), \
             patch.object(service, 'start_handler', return_value=MagicMock()), \
             patch.object(service, 'start_library_scanner_manager', return_value=MagicMock()), \
             patch.object(service, 'start_inotify_watch_manager', return_value=MagicMock()), \
             patch.object(service, 'start_ui_server', return_value=MagicMock()), \
             patch.object(service, 'start_scheduled_tasks_manager', return_value=MagicMock()), \
             patch.object(service, 'start_resource_logger'):
            service.start_threads(mock_settings)
            mock_clean.assert_called_once()
            mock_tq_cls.assert_called_once()

    @patch('compresso.service.common.clean_files_in_cache_dir', side_effect=Exception("fail"))
    def test_start_threads_cache_cleanup_failure_raises(self, mock_clean):
        service = self._make_service()
        mock_settings = MagicMock()
        mock_settings.get_cache_path.return_value = '/tmp/cache'
        with pytest.raises(Exception, match="fail"):
            service.start_threads(mock_settings)


@pytest.mark.unittest
class TestRootServiceRun:

    def _make_service(self):
        with patch('compresso.service.CompressoLogging') as mock_log, \
             patch('compresso.service.startup.StartupState') as mock_startup_cls:
            mock_log.get_logger.return_value = MagicMock()
            mock_log.metric = MagicMock()
            mock_startup_cls.return_value = MagicMock()
            from compresso.service import RootService
            service = RootService()
        return service

    def test_run_happy_path_initializes_manager_and_stops_cleanly(self):
        service = self._make_service()
        mock_manager = MagicMock()
        mock_manager.dict.side_effect = [MagicMock(), MagicMock()]
        mock_db = MagicMock()
        mock_db.is_stopped.side_effect = [False, True]
        mock_settings = MagicMock()
        mock_settings.get_config_path.return_value = '/tmp/config'
        mock_settings.get_plugins_path.return_value = '/tmp/fake_plugins'

        with patch('multiprocessing.Manager', return_value=mock_manager), \
             patch('atexit.register') as mock_register, \
             patch('tornado.autoreload.add_reload_hook') as mock_reload_hook, \
             patch('compresso.service.config.Config', return_value=mock_settings), \
             patch('compresso.service.startup.validate_startup_environment') as mock_validate, \
             patch('compresso.service.init_db', return_value=mock_db), \
             patch('compresso.libs.unplugins.child_process.set_shared_manager') as mock_set_manager, \
             patch.object(service, 'start_threads') as mock_start_threads, \
             patch.object(service, 'wait_for_startup_readiness') as mock_wait_ready, \
             patch.object(service, 'log_startup_summary') as mock_log_summary, \
             patch.object(service, 'stop_threads') as mock_stop_threads, \
             patch('compresso.service.signal.signal') as mock_signal, \
             patch('compresso.service.signal.pause', side_effect=lambda: service.stop()), \
             patch('compresso.service.time.sleep') as mock_sleep, \
             patch('compresso.service.os.name', 'posix'):
            service.run()

        assert mock_register.call_count == 2
        assert mock_reload_hook.call_count == 2
        mock_set_manager.assert_called_once_with(mock_manager)
        mock_validate.assert_called_once_with(mock_settings)
        mock_start_threads.assert_called_once_with(mock_settings)
        mock_wait_ready.assert_called_once_with(mock_settings)
        mock_log_summary.assert_called_once_with(mock_settings)
        mock_stop_threads.assert_called_once_with()
        mock_db.stop.assert_called_once_with()
        assert mock_signal.call_count == 2
        mock_sleep.assert_any_call(.5)
        service.startup_state.reset.assert_called_once_with()

    def test_run_marks_config_failure_and_raises(self):
        service = self._make_service()
        mock_manager = MagicMock()
        mock_manager.dict.side_effect = [MagicMock(), MagicMock()]

        with patch('multiprocessing.Manager', return_value=mock_manager), \
             patch('atexit.register'), \
             patch('tornado.autoreload.add_reload_hook'), \
             patch('compresso.service.config.Config', side_effect=Exception('bad config')), \
             patch('compresso.libs.unplugins.child_process.set_shared_manager'):
            with pytest.raises(Exception, match='bad config'):
                service.run()

        service.startup_state.mark_error.assert_called_once()

    def test_run_marks_startup_validation_failure(self):
        service = self._make_service()
        mock_manager = MagicMock()
        mock_manager.dict.side_effect = [MagicMock(), MagicMock()]
        mock_settings = MagicMock()
        mock_settings.get_config_path.return_value = '/tmp/config'

        with patch('multiprocessing.Manager', return_value=mock_manager), \
             patch('atexit.register'), \
             patch('tornado.autoreload.add_reload_hook'), \
             patch('compresso.service.config.Config', return_value=mock_settings), \
             patch('compresso.service.startup.validate_startup_environment', side_effect=Exception('bad env')), \
             patch('compresso.libs.unplugins.child_process.set_shared_manager'):
            with pytest.raises(Exception, match='bad env'):
                service.run()

        service.startup_state.mark_error.assert_called_once()

    def test_run_marks_threading_failure(self):
        service = self._make_service()
        service.startup_state.snapshot.return_value = {'errors': []}
        mock_manager = MagicMock()
        mock_manager.dict.side_effect = [MagicMock(), MagicMock()]
        mock_settings = MagicMock()
        mock_settings.get_config_path.return_value = '/tmp/config'
        mock_settings.get_plugins_path.return_value = '/tmp/fake_plugins'
        mock_db = MagicMock()

        with patch('multiprocessing.Manager', return_value=mock_manager), \
             patch('atexit.register'), \
             patch('tornado.autoreload.add_reload_hook'), \
             patch('compresso.service.config.Config', return_value=mock_settings), \
             patch('compresso.service.startup.validate_startup_environment'), \
             patch('compresso.service.init_db', return_value=mock_db), \
             patch('compresso.libs.unplugins.child_process.set_shared_manager'), \
             patch.object(service, 'start_threads', side_effect=Exception('thread failure')):
            with pytest.raises(Exception, match='thread failure'):
                service.run()

        service.startup_state.mark_error.assert_called_once()


@pytest.mark.unittest
class TestMainArgParser:

    @patch('compresso.service.config.Config')
    @patch('compresso.service.init_db')
    @patch('compresso.service.RootService')
    def test_main_starts_service(self, mock_service_cls, mock_init_db, mock_config):
        mock_settings = MagicMock()
        mock_config.return_value = mock_settings
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service
        with patch('sys.argv', ['compresso']):
            from compresso.service import main
            main()
        mock_service.run.assert_called_once()

    @patch('compresso.service.config.Config')
    @patch('compresso.service.init_db')
    def test_main_manage_plugins(self, mock_init_db, mock_config):
        mock_settings = MagicMock()
        mock_settings.get_config_path.return_value = '/tmp/config'
        mock_config.return_value = mock_settings
        mock_db = MagicMock()
        mock_db.is_stopped.return_value = True
        mock_init_db.return_value = mock_db
        mock_cli = MagicMock()
        mock_cli_mod = MagicMock()
        mock_cli_mod.PluginsCLI.return_value = mock_cli
        with patch('sys.argv', ['compresso', '--manage-plugins']), \
             patch.dict('sys.modules', {'compresso.libs.unplugins.pluginscli': mock_cli_mod}):
            from compresso.service import main
            main()
            mock_cli.run.assert_called_once()

    @patch('compresso.service.time.sleep')
    @patch('compresso.service.config.Config')
    @patch('compresso.service.init_db')
    def test_main_manage_plugins_runs_from_args_and_waits_for_db_stop(self, mock_init_db, mock_config, mock_sleep):
        mock_settings = MagicMock()
        mock_settings.get_config_path.return_value = '/tmp/config'
        mock_config.return_value = mock_settings
        mock_db = MagicMock()
        mock_db.is_stopped.side_effect = [False, True]
        mock_init_db.return_value = mock_db
        mock_cli = MagicMock()
        mock_cli_mod = MagicMock()
        mock_cli_mod.PluginsCLI.return_value = mock_cli
        with patch('sys.argv', ['compresso', '--manage-plugins', '--test-plugins']), \
             patch.dict('sys.modules', {'compresso.libs.unplugins.pluginscli': mock_cli_mod}):
            from compresso.service import main
            main()

        mock_cli.run_from_args.assert_called_once()
        mock_sleep.assert_called_once_with(.2)


@pytest.mark.unittest
class TestInitialRegisterCompresso:

    def _make_service(self):
        with patch('compresso.service.CompressoLogging') as mock_log, \
             patch('compresso.service.startup.StartupState'):
            mock_log.get_logger.return_value = MagicMock()
            mock_log.metric = MagicMock()
            from compresso.service import RootService
            service = RootService()
        return service

    @patch('compresso.libs.session.Session')
    def test_register(self, mock_session_cls):
        service = self._make_service()
        mock_session = MagicMock()
        mock_session.get_installation_uuid.return_value = 'uuid-123'
        mock_session_cls.return_value = mock_session
        service.initial_register_compresso()
        mock_session.register_compresso.assert_called_once_with('uuid-123')


@pytest.mark.unittest
class TestStartResourceLogger:

    def _make_service(self):
        with patch('compresso.service.CompressoLogging') as mock_log, \
             patch('compresso.service.startup.StartupState'):
            mock_log.get_logger.return_value = MagicMock()
            mock_log.metric = MagicMock()
            from compresso.service import RootService
            service = RootService()
        return service

    @patch('compresso.service.psutil')
    def test_start_resource_logger(self, mock_psutil):
        service = self._make_service()
        mock_proc = MagicMock()
        mock_proc.cpu_percent.return_value = 5.0
        mock_proc.memory_info.return_value = MagicMock(rss=1024, vms=2048)
        mock_psutil.Process.return_value = mock_proc
        mock_psutil.cpu_count.return_value = 4
        mock_psutil.virtual_memory.return_value = MagicMock(total=8192)

        # Don't set event yet so the thread stays alive long enough
        with patch.object(service, '_verify_thread_started'):
            service.start_resource_logger()
        assert len(service.threads) == 1
        assert service.threads[0]['name'] == 'RootServiceResourceLogger'
        # Now stop the thread
        service.event.set()
        service.threads[0]['thread'].stop()
        service.threads[0]['thread'].join(2)
