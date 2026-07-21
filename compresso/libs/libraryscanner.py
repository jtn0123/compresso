#!/usr/bin/env python3

"""
compresso.libraryscanner.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     20 Aug 2021, (5:37 PM)

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

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

import gc
import json
import os
import queue
import threading
import time
from collections.abc import Iterable, Iterator, Mapping
from typing import cast

import schedule

from compresso import config
from compresso.libs import narrowing
from compresso.libs.filetest import FileTesterThread
from compresso.libs.frontend_push_messages import FrontendPushMessages
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler
from compresso.libs.scan_checkpoint import CHECKPOINT_MTIME_SLOP_NS, ScanCheckpointStore
from compresso.libs.taskhandler import QueuedPath


def _queue(value: object) -> queue.Queue[object]:
    if not isinstance(value, queue.Queue):
        raise TypeError("library scanner data queue is missing")
    return cast("queue.Queue[object]", value)


def iter_sorted_library_directories(
    walk_entries: Iterable[tuple[str, list[str], list[str]]],
) -> Iterator[tuple[str, list[str]]]:
    """Yield deterministic, directory-sized scan batches from an os.walk iterable."""
    for root, subfolders, files in walk_entries:
        subfolders.sort()
        files.sort()
        yield root, files


class LibraryScannerManager(threading.Thread):
    def __init__(self, data_queues: Mapping[str, object], event: threading.Event) -> None:
        super().__init__(name="LibraryScannerManager")
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)
        self.interval = 0
        self.firstrun = True
        self.data_queues = data_queues
        self.settings = config.Config()
        self.event = event
        self.scheduledtasks = cast("queue.Queue[QueuedPath]", _queue(data_queues["scheduledtasks"]))
        self.library_scanner_triggers = cast("queue.Queue[str]", _queue(data_queues["library_scanner_triggers"]))
        self.abort_flag = threading.Event()
        self.abort_flag.clear()
        self.scheduler = schedule.Scheduler()

        self.file_test_managers: dict[int, FileTesterThread] = {}
        self.files_to_test: queue.Queue[str] = queue.Queue()
        self.files_to_process: queue.Queue[dict[str, object]] = queue.Queue()

    def stop(self) -> None:
        self.abort_flag.set()
        # Stop all child threads
        self.stop_all_file_test_managers()

    def abort_is_set(self) -> bool:
        # Check if the abort flag is set
        if self.abort_flag.is_set():
            # Return True straight away if it is
            return True
        # Sleep for a fraction of a second to prevent CPU pinning
        self.event.wait(0.1)
        # Return False
        return False

    def run(self) -> None:
        self.logger.info("Starting LibraryScanner Monitor loop")
        while not self.abort_is_set():
            self.event.wait(1)

            # Main loop to configure the scheduler
            if int(self.settings.get_schedule_full_scan_minutes()) != self.interval:
                self.interval = int(self.settings.get_schedule_full_scan_minutes())
            if self.interval and self.interval != 0:
                self.logger.info("Setting LibraryScanner schedule to scan every %s mins...", self.interval)
                # Configure schedule
                self.scheduler.every(self.interval).minutes.do(self.scheduled_job)
                # Register application
                self.register_compresso()

                # First run the task
                if self.settings.get_run_full_scan_on_start() and self.firstrun:
                    self.logger.info("Running LibraryScanner on start")
                    self.scheduled_job()
                self.firstrun = False

                self._run_scheduled_scan_loop()
                self.scheduler.clear()

        self.logger.info("Leaving LibraryScanner Monitor loop...")

    def _run_scheduled_scan_loop(self) -> None:
        while not self.abort_is_set():
            self.event.wait(1)
            try:
                trigger = self.library_scanner_triggers.get_nowait()
            except queue.Empty:
                trigger = None
            except Exception as error:
                self.logger.exception("Exception retrieving library scanner trigger %s: %s", self.name, error)
                trigger = None
            if trigger == "library_scan":
                self.scheduled_job()
                return
            if not self.settings.get_enable_library_scanner():
                self.event.wait(20)
                continue
            self.scheduler.run_pending()
            if int(self.settings.get_schedule_full_scan_minutes()) != self.interval:
                self.logger.info("Resetting LibraryScanner schedule")
                return

    def scheduled_job(self) -> None:
        """
        Function called by the scheduled task

        :return:
        """
        if not self.system_configuration_is_valid():
            self.logger.warning("Skipping library scanner due invalid system configuration.")
            return

        # For each configured library, check if a library scan is required
        no_libraries_configured = True
        for lib_info in Library.get_all_libraries():
            no_libraries_configured = False
            try:
                library = Library(lib_info["id"])
            except Exception:
                self.logger.exception("Unable to fetch library config for ID %s", lib_info["id"])
                continue
            # Check if the library is configured for remote files only
            if library.get_enable_remote_only():
                # This library is configured to receive remote files only... Never run a library scan on it
                continue
            # Check if library scanner is enabled on any library
            if library.get_enable_scanner():
                # Run library scan
                library_name = library.get_name()
                self.logger.info("Running full library scan on library '%s'", library_name)
                self.scan_library_path(library_name, library.get_path(), library.get_id())
        if no_libraries_configured:
            self.logger.info("No libraries are configured to run a library scan")

    def system_configuration_is_valid(self) -> bool:
        """
        Check and ensure the system configuration is correct for running

        :return:
        """
        plugin_handler = PluginsHandler()
        return not plugin_handler.get_incompatible_enabled_plugins()

    def add_path_to_queue(self, pathname: str, library_id: int, priority_score: int) -> None:
        self.scheduledtasks.put(
            {
                "pathname": pathname,
                "library_id": library_id,
                "priority_score": priority_score,
            }
        )

    def start_results_manager_thread(
        self,
        manager_id: int,
        status_updates: queue.Queue[str],
        library_id: int,
    ) -> None:
        manager = FileTesterThread(
            f"FileTesterThread-{manager_id}", self.files_to_test, self.files_to_process, status_updates, library_id, self.event
        )
        manager.daemon = True
        manager.start()
        self.file_test_managers[manager_id] = manager

    def stop_all_file_test_managers(self) -> None:
        for manager_id in self.file_test_managers:
            self.file_test_managers[manager_id].abort_flag.set()

    @staticmethod
    def update_scan_progress(frontend_messages: FrontendPushMessages, message: str) -> None:
        frontend_messages.update(
            {"id": "libraryScanProgress", "type": "status", "code": "libraryScanProgress", "message": message, "timeout": 0}
        )

    def file_tests_in_progress(self) -> bool:
        """
        Check if any file tester threads are still processing a file.

        :return: bool
        """
        for manager in self.file_test_managers.values():
            testing_check = getattr(manager, "is_testing_file", None)
            if callable(testing_check) and bool(testing_check()):
                return True
        return False

    def scan_work_is_pending(self) -> bool:
        """Include dequeued work that a tester has not acknowledged yet."""
        return bool(self.files_to_test.unfinished_tasks) or self.file_tests_in_progress()

    def get_scan_queue_limit(self) -> int:
        try:
            return max(1, int(self.settings.get_library_scan_queue_limit()))
        except (AttributeError, TypeError, ValueError):
            return 500

    def get_scan_checkpoint_store(self) -> ScanCheckpointStore | None:
        try:
            userdata_path = self.settings.get_userdata_path()
        except (AttributeError, TypeError):
            return None
        if not isinstance(userdata_path, str) or not userdata_path:
            return None
        return ScanCheckpointStore(userdata_path)

    @staticmethod
    def root_was_completed(root: str, library_path: str, completed_root: str | None) -> bool:
        if not completed_root:
            return False
        relative_root = os.path.relpath(root, library_path)
        return relative_root == completed_root

    def drain_scan_outputs(
        self,
        status_updates: queue.Queue[str],
        frontend_messages: FrontendPushMessages,
        current_file: str,
        library_id: int,
    ) -> str:
        while True:
            try:
                current_file = status_updates.get_nowait()
            except queue.Empty:
                break
        while True:
            try:
                item = self.files_to_process.get_nowait()
            except queue.Empty:
                break
            path = item.get("path")
            if not isinstance(path, str):
                self.logger.warning("Ignoring malformed library scan output without a path")
                continue
            self.add_path_to_queue(path, library_id, narrowing.coerce_int(item.get("priority_score")))
        if current_file:
            self.update_scan_progress(frontend_messages, f"Testing: {current_file}")
        return current_file

    def scan_library_path(
        self,
        library_name: str,
        library_path: str,
        library_id: int,
    ) -> None:
        """
        Run a scan of the given library path

        :param library_name:
        :param library_path:
        :param library_id:
        :return:
        """
        if not os.path.exists(library_path):
            self.logger.warning("Path does not exist - '%s'", library_path)
            return
        if self.settings.get_debugging():
            self.logger.debug("Scanning directory - '%s'", library_path)

        # Push status notification to frontend
        frontend_messages = FrontendPushMessages()

        # Start X number of FileTesterThread threads
        concurrent_file_testers = self.settings.get_concurrent_file_testers()
        status_updates: queue.Queue[str] = queue.Queue()
        self.file_test_managers = {}
        for results_manager_id in range(int(concurrent_file_testers)):
            self.start_results_manager_thread(results_manager_id, status_updates, library_id)

        scan_start_time = time.time()

        frontend_messages.update(
            {
                "id": "libraryScanProgress",
                "type": "status",
                "code": "libraryScanProgress",
                "message": f"Scanning directory - '{library_path}'",
                "timeout": 0,
            }
        )

        queue_limit = self.get_scan_queue_limit()
        checkpoint_store = self.get_scan_checkpoint_store()
        checkpoint = checkpoint_store.load_record(library_id, library_path) if checkpoint_store else None
        completed_root = checkpoint["completed_root"] if checkpoint else None
        checkpoint_updated_at_ns = checkpoint["updated_at_ns"] if checkpoint else None
        if completed_root and not os.path.isdir(os.path.join(library_path, completed_root)):
            if checkpoint_store:
                checkpoint_store.clear(library_id)
            completed_root = None
        total_file_count, current_file = self._scan_directories(
            library_path,
            library_id,
            queue_limit,
            status_updates,
            frontend_messages,
            checkpoint_store,
            completed_root,
            checkpoint_updated_at_ns,
        )
        self._wait_for_scan_completion(status_updates, frontend_messages, current_file, library_id, total_file_count)

        # Wait for threads to finish
        for manager_id in self.file_test_managers:
            self.file_test_managers[manager_id].abort_flag.set()
            self.file_test_managers[manager_id].join(2)
            if self.file_test_managers[manager_id].is_alive():
                self.logger.error(
                    "Completing Library scan, but thread %s is still alive. Files tested by this thread will be ignored.",
                    manager_id,
                )

        scan_end_time = time.time()
        scan_duration = str(scan_end_time - scan_start_time)
        self.logger.warning("Library scan completed in %s seconds", scan_duration)
        CompressoLogging.log_metric(
            "library_scan_completed",
            library_name=library_name,
            library_path=library_path,
            library_id=library_id,
            scan_start_time=scan_start_time,
            scan_end_time=scan_end_time,
            scan_duration=scan_duration,
        )
        CompressoLogging.log_data(
            "last_library_scan",
            data_search_key=str(library_id),  # Key this metric by the library_id
            library_name=library_name,
            library_path=library_path,
            library_id=library_id,
            scan_start_time=scan_start_time,
            scan_end_time=scan_end_time,
            scan_duration=scan_duration,
            files_scanned_count=total_file_count,
        )

        # Execute event plugin runners
        data = {
            "library_id": library_id,
            "library_name": library_name,
            "library_path": library_path,
            "scan_start_time": scan_start_time,
            "scan_end_time": scan_end_time,
            "scan_duration": scan_duration,
            "files_scanned_count": total_file_count,
        }
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type("events.scan_complete", data)

        if checkpoint_store and not self.abort_flag.is_set():
            checkpoint_store.clear(library_id)

        # Run a manual garbage collection
        gc.collect()

        # Remove frontend status message
        frontend_messages.remove_item("libraryScanProgress")

    def _scan_directories(
        self,
        library_path: str,
        library_id: int,
        queue_limit: int,
        status_updates: queue.Queue[str],
        messages: FrontendPushMessages,
        checkpoint_store: ScanCheckpointStore | None,
        completed_root: str | None,
        checkpoint_updated_at_ns: int | None,
    ) -> tuple[int, str]:
        resume_reached = completed_root is None
        total, current_file = 0, ""
        walk_entries = os.walk(library_path, followlinks=self.settings.get_follow_symlinks())
        for root, files in iter_sorted_library_directories(walk_entries):
            if self.abort_flag.is_set():
                break
            skip, resume_reached = self._should_skip_checkpoint_root(
                root, library_path, library_id, checkpoint_store, completed_root, checkpoint_updated_at_ns, resume_reached
            )
            if skip:
                continue
            added, current_file = self._queue_scan_directory(
                root, files, library_id, queue_limit, status_updates, messages, current_file
            )
            total += added
            current_file = self._checkpoint_scanned_directory(
                root, library_path, library_id, checkpoint_store, status_updates, messages, current_file
            )
        return total, current_file

    def _should_skip_checkpoint_root(
        self,
        root: str,
        library_path: str,
        library_id: int,
        store: ScanCheckpointStore | None,
        completed_root: str | None,
        updated_at_ns: int | None,
        resume_reached: bool,
    ) -> tuple[bool, bool]:
        if resume_reached or updated_at_ns is None:
            return False, resume_reached
        try:
            changed = os.stat(root).st_mtime_ns >= updated_at_ns - CHECKPOINT_MTIME_SLOP_NS
        except OSError:
            changed = True
        if changed:
            if store:
                store.clear(library_id)
            return False, True
        reached = self.root_was_completed(root, library_path, completed_root)
        return True, reached

    def _queue_scan_directory(
        self,
        root: str,
        files: list[str],
        library_id: int,
        queue_limit: int,
        status_updates: queue.Queue[str],
        messages: FrontendPushMessages,
        current_file: str,
    ) -> tuple[int, str]:
        if self.settings.get_debugging():
            self.logger.debug(json.dumps(files, indent=2))
        added = 0
        for file_path in files:
            while self.files_to_test.qsize() >= queue_limit and not self.abort_flag.is_set():
                current_file = self.drain_scan_outputs(status_updates, messages, current_file, library_id)
                self.event.wait(0.1)
            if self.abort_flag.is_set():
                break
            self.files_to_test.put(os.path.join(root, file_path))
            added += 1
            if not status_updates.empty():
                current_file = status_updates.get()
                self.update_scan_progress(messages, f"Testing: {current_file}")
        return added, current_file

    def _checkpoint_scanned_directory(
        self,
        root: str,
        library_path: str,
        library_id: int,
        store: ScanCheckpointStore | None,
        status_updates: queue.Queue[str],
        messages: FrontendPushMessages,
        current_file: str,
    ) -> str:
        if not self.file_test_managers or self.abort_flag.is_set():
            return current_file
        while not self.abort_flag.is_set() and self.scan_work_is_pending():
            current_file = self.drain_scan_outputs(status_updates, messages, current_file, library_id)
            self.event.wait(0.1)
        current_file = self.drain_scan_outputs(status_updates, messages, current_file, library_id)
        if store and not self.abort_flag.is_set():
            store.save(library_id, library_path, os.path.relpath(root, library_path))
        return current_file

    def _wait_for_scan_completion(
        self, status_updates: queue.Queue[str], messages: FrontendPushMessages, current_file: str, library_id: int, total: int
    ) -> None:
        idle_checks = 0
        while not self.abort_flag.is_set():
            if self.files_to_test.empty() and self.files_to_process.empty() and status_updates.empty():
                if self.file_tests_in_progress():
                    idle_checks = 0
                else:
                    idle_checks += 1
                    if idle_checks > 5:
                        self.stop_all_file_test_managers()
                        return
                self.event.wait(0.5)
                continue
            current_file = self.drain_scan_outputs(status_updates, messages, current_file, library_id)
            remaining = self.files_to_test.qsize()
            percent = int(100 - (remaining / total * 100)) if total and remaining else 100
            self.update_scan_progress(messages, f"{percent}% - Testing: {current_file}")
            self.event.wait(0.1)

    def register_compresso(self) -> None:
        from compresso.libs import session

        s = session.Session()
        s.register_compresso()
