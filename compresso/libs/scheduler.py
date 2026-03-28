#!/usr/bin/env python3

"""
compresso.scheduler.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     11 Sep 2021, (11:15 AM)

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
import random
import shutil
import threading
import time
from datetime import datetime, timedelta

import schedule

from compresso import config
from compresso.libs import task
from compresso.libs.installation_link import Links
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler
from compresso.libs.session import Session


class ScheduledTasksManager(threading.Thread):
    """
    Manage any tasks that Compresso needs to execute at regular intervals
    """

    def __init__(self, event):
        super().__init__(name="ScheduledTasksManager")
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)
        self.event = event
        self.abort_flag = threading.Event()
        self.abort_flag.clear()
        self.scheduler = schedule.Scheduler()
        self.force_local_worker_timer = 0

    def stop(self):
        self.abort_flag.set()

    def run(self):
        self.logger.info("Starting ScheduledTasks Monitor loop")

        # Create scheduled tasks
        # Check the session every 60 minutes
        self.scheduler.every(60).minutes.do(self.register_compresso)
        # Run the plugin repo update every 3 hours
        self.scheduler.every(3).hours.do(self.plugin_repo_update)
        # Run the remote installation link update every 10 seconds
        self.scheduler.every(10).seconds.do(self.update_remote_installation_links)
        # Run the remote installation distributed worker counter sync every minute
        self.scheduler.every(1).minutes.do(self.set_worker_count_based_on_remote_installation_links)
        # Run a completed task cleanup every 60 minutes and on startup
        self.scheduler.every(12).hours.do(self.manage_completed_tasks)
        self.manage_completed_tasks()
        # Run preview cleanup every hour
        self.scheduler.every(1).hours.do(self.cleanup_old_previews)
        # Run staging directory cleanup every 6 hours
        self.scheduler.every(6).hours.do(self.cleanup_expired_staging)

        # Loop every 2 seconds to check if a task is due to be run
        while not self.abort_flag.is_set():
            self.event.wait(2)
            # Check if scheduled task is due
            self.scheduler.run_pending()

        # Clear any tasks and exit
        self.scheduler.clear()
        self.logger.info("Leaving ScheduledTasks Monitor loop...")

    def register_compresso(self):
        self.logger.info("Updating session data")
        s = Session()
        s.register_compresso(force=True)

    def plugin_repo_update(self):
        self.logger.info("Checking for updates to plugin repos")
        plugin_handler = PluginsHandler()
        plugin_handler.update_plugin_repos()

    def update_remote_installation_links(self):
        # Don't log this as it will happen often
        links = Links()
        links.update_all_remote_installation_links()

    def set_worker_count_based_on_remote_installation_links(self):
        settings = config.Config()

        # Get local task count as int
        task_handler = task.Task()
        local_task_count = int(task_handler.get_total_task_list_count())

        # Get target count
        target_count = int(settings.get_distributed_worker_count_target())

        linked_configs = []
        for local_config in settings.get_remote_installations():
            if local_config.get("enable_distributed_worker_count"):
                linked_configs.append(local_config)

        # If no remote links are configured, then return here
        if not linked_configs:
            return

        # There is a link config with distributed worker counts enabled
        self.logger.info("Syncing distributed worker count for this installation")

        # Get total tasks count of pending tasks across all linked_configs
        total_tasks = local_task_count
        for linked_config in linked_configs:
            total_tasks += int(linked_config.get("task_count", 0))

        # From the counts fetched from all linked_configs, balance out the target count (including this installation)
        allocated_worker_count = 0
        for linked_config in linked_configs:
            if linked_config.get("task_count", 0) == 0:
                continue
            allocated_worker_count += round((int(linked_config.get("task_count", 0)) / total_tasks) * target_count)

        # Calculate worker count for local
        target_workers_for_this_installation = 0
        if local_task_count > 0:
            target_workers_for_this_installation = round((local_task_count / total_tasks) * target_count)

        # If the total allocated worker count is now above our target, set this installation back to 0
        if allocated_worker_count > target_count:
            target_workers_for_this_installation = 0

        # Every 10-12 minutes (make it random), give this installation at least 1 worker if it has pending tasks.
        #       This should cause the pending task queue to sit idle if there is only one task in the queue and it will provide
        #           rotation of workers when the pending task queue is close to the same.
        #       EG. If time now (seconds) > time last checked (seconds) + 10mins (600 seconds) + random seconds within 2mins
        time_now = time.time()
        # noqa justification: S311 — jitter for scheduling, not crypto
        time_to_next_force_local_worker = int(
            self.force_local_worker_timer + 600 + random.randrange(120)  # noqa: S311
        )
        if (
            time_now > time_to_next_force_local_worker
            and (local_task_count > 1)
            and (target_workers_for_this_installation < 1)
        ):
            target_workers_for_this_installation = 1
            self.force_local_worker_timer = time_now

        self.logger.info("Configuring worker count as %s for this installation", target_workers_for_this_installation)
        settings.set_config_item("number_of_workers", target_workers_for_this_installation, save_settings=True)

    def manage_completed_tasks(self):
        settings = config.Config()
        # Only run if configured to auto manage completed tasks
        if not settings.get_auto_manage_completed_tasks():
            return

        self.logger.info("Running completed task cleanup for this installation")
        max_age_in_days = settings.get_max_age_of_completed_tasks()
        compress_completed_tasks_logs = settings.get_compress_completed_tasks_logs()
        date_x_days_ago = datetime.now() - timedelta(days=int(max_age_in_days))
        before_time = date_x_days_ago.timestamp()

        task_success = True
        inc_status = "successfully"
        if not settings.get_always_keep_failed_tasks():
            inc_status = "successfully or failed"
            task_success = None

        # Fetch completed tasks
        from compresso.libs import history

        history_logging = history.History()
        count = history_logging.get_historic_task_list_filtered_and_sorted(
            task_success=task_success, before_time=before_time
        ).count()
        results = history_logging.get_historic_task_list_filtered_and_sorted(
            task_success=task_success, before_time=before_time
        )

        if count == 0:
            self.logger.info("Found no %s completed tasks older than %s days", inc_status, max_age_in_days)
            return

        if compress_completed_tasks_logs:
            self.logger.info(
                "Found %s %s completed tasks older than %s days that should be compressed", count, inc_status, max_age_in_days
            )
            task_ids = [historic_task.id for historic_task in results]
            if not history_logging.delete_historic_task_command_logs(task_ids):
                self.logger.error("Failed to compress %s %s completed tasks", count, inc_status)
                return
            self.logger.info("Compressed %s %s completed tasks", count, inc_status)
            return

        self.logger.info(
            "Found %s %s completed tasks older than %s days that should be removed", count, inc_status, max_age_in_days
        )
        if not history_logging.delete_historic_tasks_recursively(results):
            self.logger.error("Failed to delete %s %s completed tasks", count, inc_status)
            return

        self.logger.info("Deleted %s %s completed tasks", count, inc_status)

    def cleanup_old_previews(self):
        """Clean up preview jobs older than 24 hours."""
        try:
            from compresso.libs.preview import PreviewManager

            preview_manager = PreviewManager()
            preview_manager.cleanup_old_previews()
        except Exception as e:
            self.logger.error("Failed to cleanup old previews: %s", e)

    def cleanup_expired_staging(self):
        """Remove staging directories for tasks that have expired or no longer exist."""
        settings = config.Config()
        expiry_days = settings.get_staging_expiry_days()
        if not expiry_days or expiry_days <= 0:
            return

        staging_path = settings.get_staging_path()
        if not os.path.exists(staging_path):
            return

        cutoff = datetime.now() - timedelta(days=int(expiry_days))

        for entry in os.scandir(staging_path):
            if not entry.is_dir() or not entry.name.startswith("task_"):
                continue
            try:
                task_id = int(entry.name.split("_")[1])
            except (ValueError, IndexError):
                continue

            # Check if the associated task still exists and is still awaiting approval
            from compresso.libs.unmodels.tasks import Tasks

            try:
                task_obj = Tasks.get_by_id(task_id)
                if task_obj.status == "awaiting_approval":
                    # Check age by finish_time
                    if task_obj.finish_time and task_obj.finish_time < cutoff:
                        self.logger.info("Auto-rejecting expired staging task %s (finished %s)", task_id, task_obj.finish_time)
                        task_obj.delete_instance()
                        try:
                            shutil.rmtree(entry.path)
                        except OSError as e:
                            self.logger.warning("Failed to remove staging dir for task %s: %s", task_id, e)
                    # Still within expiry — leave it
                else:
                    # Task exists but isn't awaiting approval — staging is orphaned
                    self.logger.info("Cleaning orphaned staging dir for task %s (status=%s)", task_id, task_obj.status)
                    try:
                        shutil.rmtree(entry.path)
                    except OSError as e:
                        self.logger.warning("Failed to remove orphaned staging dir for task %s: %s", task_id, e)
            except Tasks.DoesNotExist:
                # Task was already deleted — clean up orphaned staging
                self.logger.info("Cleaning orphaned staging dir for deleted task %s", task_id)
                try:
                    shutil.rmtree(entry.path)
                except OSError as e:
                    self.logger.warning("Failed to remove orphaned staging dir for deleted task %s: %s", task_id, e)
