#!/usr/bin/env python3

"""
compresso.service.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     06 Dec 2018, (7:21 AM)

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

import argparse
import os
import queue
import signal
import threading
import time
from collections.abc import Callable, Mapping
from multiprocessing.managers import SyncManager
from types import FrameType
from typing import Protocol, TypedDict, cast

import psutil

from compresso import config, metadata
from compresso.libs import common, eventmonitor, libraryscanner, startup
from compresso.libs.db_migrate import Migrations
from compresso.libs.file_operation_tracker import FileOperationTracker
from compresso.libs.foreman import Foreman
from compresso.libs.logs import CompressoLogging
from compresso.libs.postprocessor import PostProcessor
from compresso.libs.safety_state import record_safety_event
from compresso.libs.scheduler import ScheduledTasksManager
from compresso.libs.taskhandler import QueuedPath, TaskHandler
from compresso.libs.taskqueue import TaskQueue
from compresso.libs.uiserver import DataQueues, UIServer
from compresso.libs.unmodels.lib.basemodel import DatabaseConfig


class DatabaseConnection(Protocol):
    def stop(self) -> None: ...

    def is_stopped(self) -> bool: ...


class ManagedThread(Protocol):
    def stop(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...

    def is_alive(self) -> bool: ...


class ThreadEntry(TypedDict):
    name: str
    thread: ManagedThread


class ResourceLoggerThread(threading.Thread):
    def __init__(self, target: Callable[[], None]) -> None:
        super().__init__(target=target, name="RootServiceResourceLogger", daemon=True)
        self.abort_flag = threading.Event()

    def stop(self) -> None:
        self.abort_flag.set()


def init_db(config_path: str) -> DatabaseConnection:
    # Set paths
    app_dir = os.path.dirname(os.path.abspath(__file__))

    # Set database connection settings
    database_config = DatabaseConfig(
        TYPE="SQLITE",
        FILE=os.path.join(config_path, "compresso.db"),
    )
    migration_settings: dict[str, object] = {
        "TYPE": "SQLITE",
        "FILE": os.path.join(config_path, "compresso.db"),
        "MIGRATIONS_DIR": os.path.join(app_dir, "migrations_v1"),
        "MIGRATIONS_HISTORY_VERSION": "v1",
    }

    # Ensure the config path exists
    if not os.path.exists(config_path):
        os.makedirs(config_path)

    # Create database connection
    from compresso.libs.unmodels.lib import Database

    db_connection = cast("DatabaseConnection", Database.select_database(database_config))

    # Run database migrations
    migrations = Migrations(migration_settings)
    migrations.update_schema()

    # Return the database connection
    return db_connection


class RootService:
    CRITICAL_THREAD_NAMES = frozenset({"PostProcessor", "ScheduledTasksManager", "TaskHandler", "Foreman"})

    def __init__(self) -> None:
        self.threads: list[ThreadEntry] = []
        self.run_threads = True
        self.db_connection: DatabaseConnection | None = None

        self.developer = False
        self.dev_api: str | None = None

        self.logger = CompressoLogging.get_logger(name=type(self).__name__)
        CompressoLogging.log_metric("root_service_started")

        self.event = threading.Event()
        self.startup_state = startup.StartupState()

        self._mgr: SyncManager | None = None

    def _verify_thread_started(self, name: str, thread: threading.Thread, timeout: float = 5) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if thread.is_alive():
                self.logger.info("WORKER_THREAD_STARTED name=%s", name)
                return
            time.sleep(0.1)
        message = f"WORKER_THREAD_STARTUP_FAILED name={name} did not remain alive"
        self.logger.error(message)
        self.startup_state.mark_error("threads_ready", message)
        raise RuntimeError(message)

    def start_handler(self, data_queues: DataQueues, task_queue: TaskQueue) -> TaskHandler:
        self.logger.info("Starting TaskHandler")
        queued_paths = cast("Mapping[str, queue.Queue[QueuedPath]]", data_queues)
        handler = TaskHandler(queued_paths, task_queue, self.event)
        handler.daemon = True
        handler.start()
        self._verify_thread_started("TaskHandler", handler)
        self.threads.append({"name": "TaskHandler", "thread": handler})
        return handler

    def start_post_processor(self, data_queues: DataQueues, task_queue: TaskQueue) -> PostProcessor:
        self.logger.info("Starting PostProcessor")
        postprocessor = PostProcessor(data_queues, task_queue, self.event)
        postprocessor.daemon = True
        postprocessor.start()
        self._verify_thread_started("PostProcessor", postprocessor)
        self.threads.append({"name": "PostProcessor", "thread": postprocessor})
        return postprocessor

    def start_foreman(self, data_queues: DataQueues, settings: config.Config, task_queue: TaskQueue) -> Foreman:
        self.logger.info("Starting Foreman")
        foreman = Foreman(data_queues, settings, task_queue, self.event)
        foreman.daemon = True
        foreman.start()
        self._verify_thread_started("Foreman", foreman)
        self.threads.append({"name": "Foreman", "thread": foreman})
        return foreman

    def start_library_scanner_manager(self, data_queues: DataQueues) -> libraryscanner.LibraryScannerManager:
        self.logger.info("Starting LibraryScannerManager")
        library_scanner_manager = libraryscanner.LibraryScannerManager(data_queues, self.event)
        library_scanner_manager.daemon = True
        library_scanner_manager.start()
        self._verify_thread_started("LibraryScannerManager", library_scanner_manager)
        self.threads.append({"name": "LibraryScannerManager", "thread": library_scanner_manager})
        return library_scanner_manager

    def start_inotify_watch_manager(
        self, data_queues: DataQueues, settings: config.Config
    ) -> eventmonitor.EventMonitorManager | None:
        if eventmonitor.event_monitor_module:
            self.logger.info("Starting EventMonitorManager")
            event_monitor_manager = eventmonitor.EventMonitorManager(data_queues, self.event)
            event_monitor_manager.daemon = True
            event_monitor_manager.start()
            self._verify_thread_started("EventMonitorManager", event_monitor_manager)
            self.threads.append({"name": "EventMonitorManager", "thread": event_monitor_manager})
            return event_monitor_manager
        else:
            self.logger.error("EVENT_MONITOR_UNAVAILABLE no event monitor module was found")
            return None

    def start_ui_server(self, data_queues: DataQueues, foreman: Foreman) -> UIServer:
        self.logger.info("Starting UIServer")
        uiserver = UIServer(data_queues, foreman, self.developer)
        uiserver.daemon = True
        uiserver.start()
        self.threads.append({"name": "UIServer", "thread": uiserver})
        return uiserver

    def start_scheduled_tasks_manager(self) -> ScheduledTasksManager:
        self.logger.info("Starting ScheduledTasksManager")
        scheduled_tasks_manager = ScheduledTasksManager(self.event)
        scheduled_tasks_manager.daemon = True
        scheduled_tasks_manager.start()
        self._verify_thread_started("ScheduledTasksManager", scheduled_tasks_manager)
        self.threads.append({"name": "ScheduledTasksManager", "thread": scheduled_tasks_manager})
        return scheduled_tasks_manager

    def start_resource_logger(self) -> ResourceLoggerThread:
        thread: ResourceLoggerThread

        def log_resources() -> None:
            pid = os.getpid()
            proc = psutil.Process(pid)
            cpu_count = psutil.cpu_count(logical=True) or 1
            start_time = time.time()

            while not self.event.is_set() and not thread.abort_flag.is_set():
                try:
                    # Fetch CPU info
                    cpu_percent = proc.cpu_percent(interval=None)
                    normalised_cpu_percent = cpu_percent / cpu_count

                    # Fetch Memory info
                    mem_info = proc.memory_info()
                    rss_bytes = mem_info.rss
                    vms_bytes = mem_info.vms

                    # Calculate percentage of memory used relative to total system RAM
                    total_system_ram = psutil.virtual_memory().total
                    mem_percent = (rss_bytes / total_system_ram) * 100

                    # Calculate uptime in seconds
                    uptime = int(time.time() - start_time)

                    CompressoLogging.log_metric(
                        "root_service_resources",
                        pid=pid,
                        uptime=uptime,
                        cpu_percent=normalised_cpu_percent,
                        mem_percent=mem_percent,
                        rss_bytes=rss_bytes,
                        vms_bytes=vms_bytes,
                    )
                except Exception as e:
                    self.logger.warning("Resource logging failed: %s", e)
                    time.sleep(5)
                    continue

                time.sleep(5)  # Polling interval

        thread = ResourceLoggerThread(target=log_resources)
        thread.start()
        self._verify_thread_started("RootServiceResourceLogger", thread)
        self.threads.append({"name": "RootServiceResourceLogger", "thread": thread})
        return thread

    def initial_register_compresso(self) -> None:
        from compresso.libs import session

        s = session.Session(dev_api=self.dev_api)
        s.register_compresso()

    def start_threads(self, settings: config.Config) -> None:
        # Create our data queues
        data_queues: DataQueues = {
            "library_scanner_triggers": queue.Queue(maxsize=1),
            "scheduledtasks": queue.Queue(),
            "inotifytasks": queue.Queue(),
            "progress_reports": queue.Queue(),
        }

        # Reconcile persisted task state before any worker or postprocessor can
        # claim work, then remove only cache directories that are not referenced
        # by recoverable tasks.
        self.logger.info("Recovering persisted tasks and clearing abandoned cache")
        try:
            journal_dir = os.path.join(settings.get_config_path(), "recovery", "file_operations")
            operation_recovery = FileOperationTracker.recover_all(journal_dir, self.logger)
            protected_paths = TaskHandler.recover_tasks_on_startup(
                settings,
                committed_task_ids=operation_recovery["committed_task_ids"],
                finalization_task_ids=operation_recovery.get("finalization_task_ids", []),
            )
            FileOperationTracker.finalize_committed(journal_dir)
            common.clean_files_in_cache_dir(settings.get_cache_path(), protected_paths=protected_paths)
        except Exception as e:
            try:
                record_safety_event(
                    settings,
                    None,
                    "rollback-failure",
                    "Startup file-operation recovery did not complete",
                    error_type=type(e).__name__,
                )
            except (OSError, TypeError, ValueError) as safety_error:
                self.logger.error("Unable to persist startup recovery safety event: %s", safety_error)
            message = f"STARTUP_CACHE_CLEANUP_FAILED cache_path={settings.get_cache_path()} error={str(e)}"
            self.logger.error(message)
            self.startup_state.mark_error("startup_validation", message)
            raise

        self.logger.info("Starting all threads")

        # Register installation
        self.initial_register_compresso()

        # Setup job queue
        task_queue = TaskQueue(data_queues)

        # Setup post-processor thread
        self.start_post_processor(data_queues, task_queue)

        # Start the foreman thread
        foreman = self.start_foreman(data_queues, settings, task_queue)

        # Start new thread to handle messages from service
        self.start_handler(data_queues, task_queue)

        # Start scheduled thread
        self.start_library_scanner_manager(data_queues)

        # Start inotify watch manager
        self.start_inotify_watch_manager(data_queues, settings)

        # Start new thread to run the web UI
        self.start_ui_server(data_queues, foreman)

        # Start new thread to run the scheduled tasks manager
        self.start_scheduled_tasks_manager()

        # Start main thread resource logger
        self.start_resource_logger()
        thread_names = [thread["name"] for thread in self.threads if thread["name"] != "UIServer"]
        self.startup_state.mark_ready("threads_ready", detail=", ".join(thread_names))

    def log_startup_summary(self, settings: config.Config) -> None:
        summary = startup.build_startup_summary(settings, eventmonitor.event_monitor_module)
        self.logger.info("STARTUP_SUMMARY library_path=%s", summary["library_path"])
        self.logger.info("STARTUP_SUMMARY cache_path=%s", summary["cache_path"])
        self.logger.info("STARTUP_SUMMARY config_path=%s", summary["config_path"])
        self.logger.info(
            "STARTUP_SUMMARY scan_enabled=%s full_scan_on_start=%s concurrent_file_testers=%s",
            summary["enable_library_scanner"],
            summary["run_full_scan_on_start"],
            summary["concurrent_file_testers"],
        )
        self.logger.info(
            "STARTUP_SUMMARY worker_count=%s event_monitor_active=%s safe_defaults=%s",
            summary["worker_count"],
            summary["event_monitor_active"],
            summary["safe_defaults"],
        )
        self.logger.info("STARTUP_SUMMARY ffmpeg_version=%s", summary.get("ffmpeg_version", "not found"))

    def wait_for_startup_readiness(self, settings: config.Config) -> dict[str, object]:
        deadline = time.time() + settings.get_startup_readiness_timeout_seconds()
        while time.time() < deadline:
            snapshot = self.startup_state.snapshot()
            if snapshot.get("ready"):
                return snapshot
            if snapshot.get("errors"):
                break
            time.sleep(0.2)

        snapshot = self.startup_state.snapshot()
        if snapshot.get("errors"):
            self.logger.error(
                "STARTUP_READINESS_PARTIAL_FAILURE stages=%s errors=%s", snapshot.get("stages"), snapshot.get("errors")
            )
        else:
            self.logger.error(
                "STARTUP_READINESS_TIMEOUT stages=%s details=%s", snapshot.get("stages"), snapshot.get("details")
            )
        raise RuntimeError("Startup readiness check failed")

    def stop_threads(self) -> None:
        self.logger.info("Stopping all threads")
        self.event.set()
        for thread in self.threads:
            self.logger.info("Sending thread %s abort signal", thread["name"])
            thread["thread"].stop()
        for thread in self.threads:
            self.logger.info("Waiting for thread %s to stop", thread["name"])
            thread["thread"].join(10)
            if thread["thread"].is_alive():
                self.logger.error("WORKER_THREAD_STOP_TIMEOUT name=%s", thread["name"])
            else:
                self.logger.info("WORKER_THREAD_STOPPED name=%s", thread["name"])
        self.threads = []
        # Shut down the notification executor
        try:
            from compresso.libs.external_notifications import ExternalNotificationDispatcher

            ExternalNotificationDispatcher().shutdown()
        except Exception:  # noqa: S110 — best-effort cleanup on shutdown
            pass

    def sig_handle(self, signum: int, frame: FrameType | None) -> None:
        self.logger.info("Received %s", signum)
        self.stop()

    def stop(self) -> None:
        self.run_threads = False
        self.event.set()

    def monitor_critical_threads(self) -> bool:
        """Publish runtime health and fail visibly if a critical service exits."""
        health: dict[str, object] = {}
        for entry in self.threads:
            name = entry["name"]
            if name not in self.CRITICAL_THREAD_NAMES:
                continue
            thread = entry["thread"]
            if not thread.is_alive():
                message = f"CRITICAL_THREAD_EXITED name={name}"
                self.logger.error(message)
                self.startup_state.mark_error("threads_ready", message)
                self.run_threads = False
                self.event.set()
                return False
            snapshot = getattr(thread, "get_health_snapshot", None)
            health[name] = cast("Callable[[], object]", snapshot)() if callable(snapshot) else {"alive": True}
        self.startup_state.mark_ready("threads_ready", detail=health)
        return True

    def run(self) -> None:
        # Init the TaskDataStore and PluginChildProcess
        import atexit
        from multiprocessing import Manager

        import tornado.autoreload

        from compresso.libs.task import TaskDataStore
        from compresso.libs.unplugins.child_process import kill_all_plugin_processes, set_shared_manager

        # Init a shared manager
        manager = Manager()
        self._mgr = manager
        # Ensure Manager shuts down on process exit or tornado autoreload (dev mode)
        atexit.register(manager.shutdown)
        tornado.autoreload.add_reload_hook(manager.shutdown)
        # Ensure any PluginChildProcess shuts down on process exit or tornado autoreload (dev mode)
        atexit.register(kill_all_plugin_processes)
        tornado.autoreload.add_reload_hook(kill_all_plugin_processes)
        # Replace the in-process dicts with manager proxies
        TaskDataStore._runner_state = manager.dict()
        TaskDataStore._task_state = manager.dict()
        # Set the shared manager for PluginChildProcess
        set_shared_manager(manager)

        self.startup_state.reset()

        # Init the configuration
        try:
            settings = config.Config()
            self.startup_state.mark_ready("config_loaded", detail=settings.get_config_path())
        except Exception as e:
            message = f"STARTUP_CONFIG_LOAD_FAILED error={str(e)}"
            self.logger.error(message)
            self.startup_state.mark_error("config_loaded", message)
            raise

        # Validate deployment paths before worker startup.
        try:
            startup.validate_startup_environment(settings)
            self.startup_state.mark_ready("startup_validation", detail="validated")
        except Exception as e:
            message = f"STARTUP_VALIDATION_FAILED error={str(e)}"
            self.logger.error(message)
            self.startup_state.mark_error("startup_validation", message)
            raise

        # Init the database
        try:
            self.db_connection = init_db(settings.get_config_path())
            self.startup_state.mark_ready("db_ready", detail=settings.get_config_path())
        except Exception as e:
            message = f"STARTUP_DB_INIT_FAILED error={str(e)}"
            self.logger.error(message)
            self.startup_state.mark_error("db_ready", message)
            raise

        # Install bundled plugins
        try:
            from compresso.bundled_plugins import install_bundled_plugins

            install_bundled_plugins(settings.get_plugins_path())
        except Exception as e:
            self.logger.warning("STARTUP_BUNDLED_PLUGINS_FAILED error=%s", str(e))

        # Start all threads
        try:
            self.start_threads(settings)
            self.wait_for_startup_readiness(settings)
            self.log_startup_summary(settings)
        except Exception as e:
            message = f"STARTUP_THREADING_FAILED error={str(e)}"
            self.logger.error(message)
            if not self.startup_state.snapshot().get("errors"):
                self.startup_state.mark_error("threads_ready", message)
            raise RuntimeError(message) from e

        # Watch for the term signal
        if os.name == "nt":
            while self.run_threads:
                try:
                    time.sleep(1)
                    if self.run_threads:
                        self.monitor_critical_threads()
                except (KeyboardInterrupt, SystemExit):
                    break
        else:
            signal.signal(signal.SIGINT, self.sig_handle)
            signal.signal(signal.SIGTERM, self.sig_handle)
            while self.run_threads:
                time.sleep(1)
                if self.run_threads:
                    self.monitor_critical_threads()

        # Received term signal. Stop everything
        self.stop_threads()
        db_connection = self.db_connection
        if db_connection is None:
            raise RuntimeError("database connection was not initialized")
        db_connection.stop()
        while not db_connection.is_stopped():
            time.sleep(0.5)
            continue
        self.logger.info("Exit Compresso")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compresso")
    parser.add_argument("--version", action="version", version=f"%(prog)s {metadata.read_version_string('long')}")
    parser.add_argument(
        "--manage-plugins", "--manage_plugins", action="store_true", dest="manage_plugins", help="manage installed plugins"
    )
    parser.add_argument("--create-plugin", action="store_true", help="Create a new plugin (use with --manage-plugins)")
    parser.add_argument("--plugin-id", nargs="?", help="Plugin id for plugin CLI actions")
    parser.add_argument("--plugin-name", nargs="?", help="Plugin name for --create-plugin")
    parser.add_argument(
        "--plugin-runners", nargs="+", help="Plugin runner types for --create-plugin (names or runner functions)"
    )
    parser.add_argument("--test-plugin", nargs="?", help="Test a specific plugin by id (use with --manage-plugins)")
    parser.add_argument("--test-plugins", action="store_true", help="Test all plugins (use with --manage-plugins)")
    parser.add_argument("--test-file-in", nargs="?", help="Override test_file_in for plugin tests (use with --manage-plugins)")
    parser.add_argument(
        "--test-file-out", nargs="?", help="Override test_file_out for plugin tests (use with --manage-plugins)"
    )
    parser.add_argument(
        "--remove-plugin", action="store_true", help="Remove a plugin by id (use with --manage-plugins and --plugin-id)"
    )
    parser.add_argument(
        "--reload-plugins", action="store_true", help="Reload all plugins from disk (use with --manage-plugins)"
    )
    parser.add_argument("--install-test-data", action="store_true", help="Install test data (use with --manage-plugins)")
    parser.add_argument("--dev", action="store_true", help="Enable developer mode")
    parser.add_argument("--dev-api", nargs="?", help="Enable development against another compresso support api")
    parser.add_argument("--port", nargs="?", help="Specify the port to run the webserver on")
    parser.add_argument(
        "--address", nargs="?", help="Specify the address to listen on, to limit connections to a specific interface"
    )
    # parser.add_argument('--compresso_path', nargs='?',
    #                    help='Specify the compresso configuration path instead of ~/.compresso')
    args = parser.parse_args()

    # Configure application from args
    settings = config.Config(port=args.port, address=args.address, compresso_path=None)

    if args.manage_plugins:
        # Init the DB connection
        db_connection = init_db(settings.get_config_path())

        # Run the plugin manager CLI
        from compresso.libs.unplugins.pluginscli import PluginsCLI

        plugin_cli = PluginsCLI()
        if (
            args.create_plugin
            or args.remove_plugin
            or args.reload_plugins
            or args.test_plugin
            or args.test_plugins
            or args.install_test_data
        ):
            plugin_cli.run_from_args(args)
        else:
            plugin_cli.run()

        # Stop the DB connection
        db_connection.stop()
        while not db_connection.is_stopped():
            time.sleep(0.2)
            continue
    else:
        # Run the main Compresso service
        service = RootService()
        service.developer = args.dev
        service.dev_api = args.dev_api
        service.run()


if __name__ == "__main__":
    main()
