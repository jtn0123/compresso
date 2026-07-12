#!/usr/bin/env python3

"""
compresso.taskhandler.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     08 May 2020, (12:22 PM)

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

import os
import queue
import shutil
import threading

from peewee import OperationalError

from compresso import config
from compresso.libs import common, task
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler
from compresso.libs.unmodels.tasks import Tasks


class TaskHandler(threading.Thread):
    """
    TaskHandler

    The TaskHandler reads all items in the queues and passes them to the appropriate locations in the application.
    """

    def __init__(self, data_queues, task_queue, event):
        super().__init__(name="TaskHandler")
        self.settings = config.Config()
        self.event = event
        self.data_queues = data_queues
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)
        self.task_queue = task_queue
        self.inotifytasks = data_queues["inotifytasks"]
        self.scheduledtasks = data_queues["scheduledtasks"]
        self.abort_flag = threading.Event()
        self.abort_flag.clear()

    def _log(self, message, message2="", level="info"):
        message = common.format_message(message, message2)
        getattr(self.logger, level)(message)

    def stop(self):
        self.abort_flag.set()

    def run(self):
        self._log("Starting TaskHandler Monitor loop")
        while not self.abort_flag.is_set():
            self.event.wait(2)
            self.process_scheduledtasks_queue()
            self.process_inotifytasks_queue()

        self._log("Leaving TaskHandler Monitor loop...")

    def process_scheduledtasks_queue(self):
        while not self.abort_flag.is_set() and not self.scheduledtasks.empty():
            # Do not sleep at all here. Process this loop as quick as possible
            try:
                item = self.scheduledtasks.get_nowait()
                pathname = item["pathname"]
                library_id = item["library_id"]
                priority_score = item.get("priority_score", 0)
                if self.add_path_to_task_queue(pathname, library_id, priority_score=priority_score):
                    self._log("Adding file to task queue", pathname, level="info")
                else:
                    self._log("Skipping file as it is already in the queue", pathname, level="info")
            except queue.Empty:
                continue
            except Exception as e:
                self._log("Exception in processing scheduledtasks", str(e), level="exception")

    def process_inotifytasks_queue(self):
        while not self.abort_flag.is_set() and not self.inotifytasks.empty():
            # Do not sleep at all here. Process this loop as quick as possible
            try:
                item = self.inotifytasks.get_nowait()
                pathname = item["pathname"]
                library_id = item["library_id"]
                priority_score = item.get("priority_score", 0)
                if self.add_path_to_task_queue(pathname, library_id, priority_score=priority_score):
                    self._log("Adding inotify job to queue", pathname, level="info")
                else:
                    self._log("Skipping inotify job already in the queue", pathname, level="info")
            except queue.Empty:
                continue
            except Exception as e:
                self._log("Exception in processing inotifytasks", str(e), level="exception")

    @staticmethod
    def _file_is_usable(path):
        try:
            return bool(path) and os.path.isfile(path) and os.path.getsize(path) > 0
        except OSError:
            return False

    @classmethod
    def _find_staged_output(cls, staging_path, task_id):
        task_staging_dir = os.path.join(staging_path, f"task_{task_id}")
        if not os.path.isdir(task_staging_dir):
            return None
        try:
            for entry in os.scandir(task_staging_dir):
                if entry.is_file() and cls._file_is_usable(entry.path):
                    return entry.path
        except OSError:
            return None
        return None

    @staticmethod
    def _reset_interrupted_task(task_obj):
        task_obj.status = "pending"
        task_obj.success = None
        task_obj.processed_by_worker = None
        task_obj.start_time = None
        task_obj.finish_time = None
        task_obj.deferred_until = None
        task_obj.save()

    @staticmethod
    def _reconcile_finalization_override(task_obj, committed_task_ids, finalization_task_ids, logger):
        if task_obj.id in committed_task_ids:
            logger.warning("STARTUP_COMMITTED_TASK_FINALIZED id=%s", task_obj.id)
            task.TaskDataStore.clear_task(task_obj.id)
            Tasks.delete().where(Tasks.id == task_obj.id).execute()
            return True
        if task_obj.id in finalization_task_ids:
            logger.warning("STARTUP_TASK_FINALIZATION_RESUMED id=%s status=%s", task_obj.id, task_obj.status)
            return True
        return False

    @classmethod
    def recover_tasks_on_startup(cls, settings, committed_task_ids=None, finalization_task_ids=None):
        """Reconcile persisted tasks before worker and postprocessor startup.

        Returns file paths that startup cache cleanup must preserve. Interrupted
        work is requeued without consuming a normal retry. Completed outputs and
        approval artifacts are retained when they are still usable.
        """
        logger = CompressoLogging.get_logger(name=cls.__name__)
        protected_paths = set()
        staging_path = settings.get_staging_path()
        clear_pending = settings.get_clear_pending_tasks_on_restart()
        committed_task_ids = set(committed_task_ids or [])
        finalization_task_ids = set(finalization_task_ids or [])

        try:
            last_task_id = 0
            while True:
                task_batch = list(Tasks.select().where(Tasks.id > last_task_id).order_by(Tasks.id).limit(500))
                if not task_batch:
                    break

                for task_obj in task_batch:
                    last_task_id = task_obj.id
                    if cls._reconcile_finalization_override(task_obj, committed_task_ids, finalization_task_ids, logger):
                        continue
                    status = task_obj.status
                    source_path = task_obj.abspath
                    cache_path = task_obj.cache_path
                    staged_path = cls._find_staged_output(staging_path, task_obj.id)

                    if clear_pending and status == "pending":
                        task.TaskDataStore.clear_task(task_obj.id)
                        Tasks.delete().where(Tasks.id == task_obj.id).execute()
                        continue

                    if status == "in_progress":
                        cls._reset_interrupted_task(task_obj)
                        logger.warning("STARTUP_TASK_REQUEUED id=%s previous_status=in_progress", task_obj.id)
                    elif status == "processed":
                        if task_obj.success is not False and not cls._file_is_usable(cache_path):
                            cls._reset_interrupted_task(task_obj)
                            logger.warning("STARTUP_TASK_REQUEUED id=%s reason=missing_processed_cache", task_obj.id)
                        elif cls._file_is_usable(cache_path):
                            protected_paths.add(os.path.realpath(cache_path))
                    elif status == "awaiting_approval":
                        if staged_path:
                            protected_paths.add(os.path.realpath(staged_path))
                            if cls._file_is_usable(cache_path):
                                protected_paths.add(os.path.realpath(cache_path))
                        elif cls._file_is_usable(cache_path):
                            task_obj.status = "processed"
                            task_obj.save()
                            protected_paths.add(os.path.realpath(cache_path))
                            logger.warning("STARTUP_APPROVAL_RESTAGE id=%s", task_obj.id)
                        else:
                            cls._reset_interrupted_task(task_obj)
                            logger.warning("STARTUP_TASK_REQUEUED id=%s reason=missing_approval_output", task_obj.id)
                    elif status == "approved":
                        if cls._file_is_usable(cache_path):
                            protected_paths.add(os.path.realpath(cache_path))
                        elif staged_path and cache_path:
                            os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
                            shutil.copy2(staged_path, cache_path)
                            protected_paths.add(os.path.realpath(cache_path))
                            protected_paths.add(os.path.realpath(staged_path))
                            logger.warning("STARTUP_APPROVED_CACHE_RESTORED id=%s", task_obj.id)
                        else:
                            cls._reset_interrupted_task(task_obj)
                            logger.warning("STARTUP_TASK_REQUEUED id=%s reason=missing_approved_output", task_obj.id)
                    elif status == "complete" and cls._file_is_usable(cache_path):
                        protected_paths.add(os.path.realpath(cache_path))

                    # Uploaded remote sources live under the cache root and must
                    # remain available while the originating installation recovers.
                    if task_obj.type == "remote" and cls._file_is_usable(source_path):
                        protected_paths.add(os.path.realpath(source_path))
        except OperationalError as error:
            logger.debug("Skipping task recovery at startup; tasks table missing - %s", error)

        return sorted(protected_paths)

    def clear_tasks_on_startup(self):
        """Compatibility wrapper for callers that still invoke the old hook."""
        return self.recover_tasks_on_startup(self.settings)

    @staticmethod
    def check_if_task_exists_matching_path(abspath):
        """
        Check if a task already exists matching the given path

        :param abspath:
        :return:
        """
        existing_task_query = Tasks.select().where(Tasks.abspath == abspath).limit(1)
        return existing_task_query.count() > 0

    def add_path_to_task_queue(self, pathname, library_id, priority_score=0):
        """
        Add the path to the task queue ensuring that the path is only added once

        :param pathname:
        :param library_id:
        :param priority_score:
        :return:
        """
        # Check if file exists in task queue based on it's absolute path
        abspath = os.path.abspath(pathname)
        if self.check_if_task_exists_matching_path(abspath):
            return False
        # Create the new task from the provide path
        new_task = self.create_task_from_path(pathname, library_id, priority_score=priority_score)
        if not new_task:
            return False
        # Execute event plugin runners
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type(
            "events.task_queued",
            {
                "library_id": library_id,
                "task_id": new_task.get_task_id(),
                "task_type": new_task.get_task_type(),
                "source_data": new_task.get_source_data(),
            },
        )

        return True

    def create_task_from_path(self, pathname, library_id, priority_score=0):
        """
        Generate a Task object from a pathname

        :param pathname:
        :param library_id:
        :param priority_score:
        :return:
        """
        abspath = os.path.abspath(pathname)
        # Create a new task
        new_task = task.Task()

        if not new_task.create_task_by_absolute_path(abspath, library_id=library_id, priority_score=priority_score):
            # If file exists in task queue already this will return false.
            # Do not carry on.
            return False

        return new_task
