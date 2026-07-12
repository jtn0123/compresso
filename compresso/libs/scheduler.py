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

import math
import os
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
from compresso.libs.resumable_transfer import ResumableTransferStore
from compresso.libs.session import Session
from compresso.libs.thread_health import ThreadHealthMixin
from compresso.libs.unmodels.tasks import Tasks
from compresso.libs.worker_capabilities import WorkerCapabilities
from compresso.libs.worker_group import WorkerGroup


class ScheduledTasksManager(ThreadHealthMixin, threading.Thread):
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
        self._init_thread_health()

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
        try:
            self.manage_completed_tasks()
            self._mark_thread_success()
        except Exception as e:
            self._mark_thread_error(e)
            self.logger.exception("Startup completed-task cleanup failed; continuing scheduler loop")
        # Run preview cleanup every hour
        self.scheduler.every(1).hours.do(self.cleanup_old_previews)
        self.scheduler.every(1).hours.do(self.cleanup_stale_transfers)
        self.scheduler.every(6).hours.do(self.cleanup_orphaned_remote_tasks)
        # Run staging directory cleanup every 6 hours
        self.scheduler.every(6).hours.do(self.cleanup_expired_staging)

        # Loop every 2 seconds to check if a task is due to be run
        while not self.abort_flag.is_set():
            self.event.wait(2)
            self._mark_thread_heartbeat()
            # Check if scheduled task is due
            try:
                self.scheduler.run_pending()
                self._mark_thread_success()
            except Exception as e:
                self._mark_thread_error(e)
                self.logger.exception("Scheduled task failed; continuing scheduler loop")

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

    @staticmethod
    def _worker_group_allocations(worker_groups, target_total):
        """Allocate an installation-level target across its worker groups."""
        if not worker_groups:
            return []

        target_total = max(0, int(target_total))
        current_counts = [max(0, int(group.get("number_of_workers", 0))) for group in worker_groups]
        current_total = sum(current_counts)
        if current_total == 0:
            return [target_total, *([0] * (len(worker_groups) - 1))]

        quotas = [(count / current_total) * target_total for count in current_counts]
        allocations = [int(quota) for quota in quotas]
        remaining = target_total - sum(allocations)
        largest_remainders = sorted(
            range(len(worker_groups)),
            key=lambda index: quotas[index] - allocations[index],
            reverse=True,
        )
        for index in largest_remainders[:remaining]:
            allocations[index] += 1
        return allocations

    def _set_local_worker_group_total(self, target_total):
        """Persist a distributed worker target to the worker-group model used by Foreman."""
        worker_groups = WorkerGroup.get_all_worker_groups()
        allocations = self._worker_group_allocations(worker_groups, target_total)
        for group_config, worker_count in zip(worker_groups, allocations, strict=True):
            worker_group = WorkerGroup(group_config["id"])
            worker_group.set_number_of_workers(worker_count)
            worker_group.save()

    @staticmethod
    def _installation_worker_allocations(candidates, target_total, runnable_demand):
        """Allocate a bounded global worker target by deterministic capacity score."""
        target_total = min(max(0, int(target_total)), max(0, int(runnable_demand)))
        if target_total == 0 or not candidates:
            return {candidate["id"]: 0 for candidate in candidates}

        weighted = []
        for candidate in candidates:
            try:
                score = float(candidate.get("score", 0))
            except (TypeError, ValueError):
                score = 0
            weighted.append((str(candidate["id"]), score if math.isfinite(score) and score > 0 else 1.0))

        total_weight = sum(score for _, score in weighted)
        quotas = {candidate_id: (score / total_weight) * target_total for candidate_id, score in weighted}
        allocations = {candidate_id: int(quota) for candidate_id, quota in quotas.items()}
        remaining = target_total - sum(allocations.values())
        ranked_remainders = sorted(
            allocations,
            key=lambda candidate_id: (-(quotas[candidate_id] - allocations[candidate_id]), candidate_id),
        )
        for candidate_id in ranked_remainders[:remaining]:
            allocations[candidate_id] += 1
        return allocations

    def set_worker_count_based_on_remote_installation_links(self):
        settings = config.Config()

        # Count only work a worker could claim now. Approval, completed, and
        # retry-deferred rows must not attract capacity.
        task_handler = task.Task()
        local_task_count = int(task_handler.get_runnable_task_count())

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

        # Get runnable demand across all linked installations.
        total_tasks = local_task_count
        for linked_config in linked_configs:
            total_tasks += int(linked_config.get("runnable_task_count", linked_config.get("task_count", 0)))

        try:
            local_capabilities = WorkerCapabilities().snapshot(settings)
        except Exception:
            local_capabilities = {}
        candidates = [
            {
                "id": "__local__",
                "score": WorkerCapabilities.scheduling_score(local_capabilities),
            }
        ]
        for index, linked_config in enumerate(linked_configs):
            if "available" in linked_config and not linked_config.get("available"):
                continue
            candidates.append(
                {
                    "id": str(linked_config.get("uuid") or linked_config.get("address") or f"remote-{index}"),
                    "score": WorkerCapabilities.scheduling_score(linked_config.get("capabilities", {})),
                }
            )
        allocations = self._installation_worker_allocations(candidates, target_count, total_tasks)
        target_workers_for_this_installation = allocations.get("__local__", 0)

        self.logger.info("Configuring worker count as %s for this installation", target_workers_for_this_installation)
        self._set_local_worker_group_total(target_workers_for_this_installation)

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

    def cleanup_stale_transfers(self):
        """Remove abandoned partial chunks after the configured resume window."""
        settings = config.Config()
        transfer_root = os.path.join(settings.get_cache_path(), "remote_transfers")
        max_age_seconds = settings.get_transfer_partial_retention_hours() * 60 * 60
        removed = ResumableTransferStore(transfer_root).cleanup_stale(max_age_seconds=max_age_seconds)
        if removed:
            self.logger.info("Removed %s stale resumable transfer(s)", len(removed))

    @staticmethod
    def _task_artifact_timestamp(task_model):
        try:
            if task_model.abspath and os.path.exists(task_model.abspath):
                return os.path.getmtime(task_model.abspath)
        except OSError:
            pass
        finish_time = task_model.finish_time
        if isinstance(finish_time, datetime):
            return finish_time.timestamp()
        try:
            return float(finish_time)
        except (TypeError, ValueError):
            return None

    def cleanup_orphaned_remote_tasks(self):
        """Expire remote results that were never acknowledged by their master."""
        settings = config.Config()
        cutoff = time.time() - (settings.get_remote_artifact_retention_hours() * 60 * 60)
        expired_ids = []
        transfer_completed_root = os.path.realpath(os.path.join(settings.get_cache_path(), "remote_transfers", "completed"))
        remote_tasks = Tasks.select().where((Tasks.type == "remote") & (Tasks.status == "complete"))
        for remote_task in remote_tasks:
            artifact_timestamp = self._task_artifact_timestamp(remote_task)
            if artifact_timestamp is None or artifact_timestamp >= cutoff:
                continue
            expired_ids.append(remote_task.id)
            artifact_path = os.path.realpath(remote_task.abspath)
            try:
                if os.path.commonpath([transfer_completed_root, artifact_path]) == transfer_completed_root:
                    shutil.rmtree(os.path.dirname(artifact_path), ignore_errors=True)
            except ValueError:
                continue
        if expired_ids:
            task.Task().delete_tasks_recursively(expired_ids)
            self.logger.info("Removed %s expired remote task artifact(s)", len(expired_ids))

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
