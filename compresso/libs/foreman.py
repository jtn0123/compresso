#!/usr/bin/env python3

"""
compresso.foreman.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     02 Jan 2019, (7:21 AM)

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

from __future__ import annotations

import hashlib
import json
import queue
import threading
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, TypedDict, cast

import peewee

from compresso import config
from compresso.libs import installation_link, narrowing
from compresso.libs.frontend_push_messages import FrontendPushMessages
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler
from compresso.libs.safety_state import SafetyForeman, SafetyState, record_safety_event
from compresso.libs.task import Task
from compresso.libs.taskqueue import TaskQueue
from compresso.libs.worker_capabilities import WorkerCapabilities
from compresso.libs.worker_group import WorkerGroup
from compresso.libs.workers import Worker

if TYPE_CHECKING:
    from compresso.libs.remote_task_manager import RemoteTaskManager


type LibrarySettings = dict[str, object]
type LibrarySettingsById = dict[int | str, LibrarySettings]
type RemoteManagerInfo = dict[str, object]


class CurrentConfig(TypedDict):
    settings: LibrarySettingsById
    settings_hash: str


class Foreman(threading.Thread):
    # Guards compound mutations of worker_threads/paused_worker_threads, which
    # are touched by both the Foreman loop and Tornado API handlers. RLock
    # because the *_all_* helpers call the per-worker helpers. Class-level so
    # it exists even for instances constructed without __init__ (as some unit
    # tests do); the process only ever runs one Foreman.
    worker_registry_lock = threading.RLock()

    def __init__(
        self,
        data_queues: Mapping[str, object],
        settings: config.Config,
        task_queue: TaskQueue,
        event: threading.Event,
    ) -> None:
        super().__init__(name="Foreman")
        self.settings = settings
        self.event = event
        self.task_queue = task_queue
        self.data_queues = data_queues
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)
        try:
            self.safety_latched = bool(SafetyState(settings.get_userdata_path()).snapshot()["pause_required"])
        except (OSError, TypeError, ValueError) as exc:
            self.logger.error("Unable to load durable safety state; workers will remain paused: %s", exc)
            self.safety_latched = True
        self.workers_pending_task_queue: queue.Queue[Task] = queue.Queue(maxsize=1)
        self.remote_workers_pending_task_queue: queue.Queue[Task] = queue.Queue(maxsize=1)
        self.complete_queue: queue.Queue[Task] = queue.Queue()
        self.worker_threads: dict[str, Worker] = {}
        self.paused_worker_threads: list[str] = []
        self.remote_task_manager_threads: dict[str, RemoteTaskManager] = {}
        self.abort_flag = threading.Event()
        self.abort_flag.clear()

        # Set the current plugin config
        self.current_config: CurrentConfig = {"settings": {}, "settings_hash": ""}
        self.configuration_changed()

        # Set the current time for scheduler
        self.last_schedule_run = datetime.today().strftime("%H:%M")

        self.links = installation_link.Links()
        self.link_heartbeat_last_run = 0.0
        self.available_remote_managers: dict[str, RemoteManagerInfo] = {}

    def stop(self) -> None:
        self.abort_flag.set()
        # Stop all workers
        # To avoid having the dictionary change size during iteration,
        #   we need to first get the thread_keys, then iterate through that
        with self.worker_registry_lock:
            self.paused_worker_threads = []
            thread_keys = [t for t in self.worker_threads]
            for thread in thread_keys:
                self.mark_worker_thread_as_redundant(thread)
        # Stop all remote link manager threads
        thread_keys = [t for t in self.remote_task_manager_threads]
        for thread in thread_keys:
            self.mark_remote_task_manager_thread_as_redundant(thread)

    def get_total_worker_count(self) -> int:
        """Returns the worker count as an integer"""
        worker_count = 0
        for worker_group in WorkerGroup.get_all_worker_groups():
            worker_count += worker_group["number_of_workers"]
        return worker_count

    def save_current_config(
        self,
        settings: LibrarySettingsById | None = None,
        settings_hash: str | None = None,
    ) -> None:
        if settings is not None:
            self.current_config["settings"] = settings
        if settings_hash is not None:
            self.current_config["settings_hash"] = settings_hash
        self.logger.debug("Updated config. If this is modified, all workers will be paused")

    def get_current_library_configuration(self) -> LibrarySettingsById:
        # Fetch all libraries
        all_plugin_settings: LibrarySettingsById = {}
        for library in Library.get_all_libraries():
            try:
                library_config = Library(library["id"])
            except Exception as e:
                # Skip libraries whose config cannot be loaded rather than aborting the sweep.
                self.logger.exception("Unable to fetch library config for ID %s: %s", library["id"], e)
                continue
            # Get list of enabled plugins with their settings
            enabled_plugins: list[dict[str, object]] = []
            for enabled_plugin in library_config.get_enabled_plugins(include_settings=True):
                enabled_plugins.append(
                    {
                        "plugin_id": enabled_plugin.get("plugin_id"),
                        "settings": enabled_plugin.get("settings"),
                    }
                )

            # Get the plugin flow
            plugin_flow = library_config.get_plugin_flow()

            # Append this library's plugin config and flow the the dictionary
            all_plugin_settings[library["id"]] = {
                "enabled_plugins": enabled_plugins,
                "plugin_flow": plugin_flow,
            }
        return all_plugin_settings

    def configuration_changed(self) -> bool:
        current_settings = self.get_current_library_configuration()
        # Compare current settings with foreman recorded settings.
        json_encoded_settings = json.dumps(current_settings, sort_keys=True).encode()
        current_settings_hash = hashlib.md5(json_encoded_settings).hexdigest()  # noqa: S324 — used for config change detection, not security
        if current_settings_hash == self.current_config["settings_hash"]:
            return False
        # Record current settings
        self.save_current_config(settings=current_settings, settings_hash=current_settings_hash)
        # Settings have changed
        return True

    def validate_worker_config(self) -> bool:
        valid = True
        frontend_messages = FrontendPushMessages()

        # Ensure that the enabled plugins are compatible with the PluginHandler version
        plugin_handler = PluginsHandler()
        if plugin_handler.get_incompatible_enabled_plugins():
            valid = False
        if not self.links.within_enabled_link_limits():
            valid = False

        # Check if plugin configuration has been modified. If it has, stop the workers.
        # What we want to avoid here is someone partially modifying the plugin configuration
        #   and having the workers pickup a job mid configuration.
        if self.configuration_changed():
            # Generate a frontend message and falsify validation
            self.logger.warning("Plugin configuration changed — stopping all workers until config stabilises")
            frontend_messages.add(
                {
                    "id": "pluginSettingsChangeWorkersStopped",
                    "type": "warning",
                    "code": "pluginSettingsChangeWorkersStopped",
                    "message": "",
                    "timeout": 0,
                }
            )
            valid = False

        return valid

    def run_task(
        self,
        time_now: str,
        task: str,
        worker_count: int | None,
        worker_group: WorkerGroup,
    ) -> None:
        worker_group_id = worker_group.get_id()
        self.last_schedule_run = time_now
        if task == "pause":
            # Pause all workers now
            self.logger.debug("Running scheduled event - Pause all worker threads")
            self.pause_all_worker_threads(worker_group_id=worker_group_id)
        elif task == "resume":
            # Resume all workers now
            self.logger.debug("Running scheduled event - Resume all worker threads")
            self.resume_all_worker_threads(worker_group_id=worker_group_id)
        elif task == "count" and worker_count is not None:
            # Set the worker count value
            # Save the settings so this scheduled event will persist an application restart
            self.logger.debug("Running scheduled event - Setting worker count to %s", worker_count)
            worker_group.set_number_of_workers(worker_count)
            worker_group.save()

    def manage_event_schedules(self) -> None:
        """
        Manage all scheduled worker events
        This function limits itself to run only once every 60 seconds

        :return:
        """
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        day_of_week = datetime.today().weekday()
        time_now = datetime.today().strftime("%H:%M")

        # Only run once a minute
        if time_now == self.last_schedule_run:
            return

        for wg in WorkerGroup.get_all_worker_groups():
            try:
                worker_group = WorkerGroup(group_id=wg["id"])
                event_schedules = worker_group.get_worker_event_schedules()
            except (ValueError, AttributeError, TypeError, peewee.PeeweeException) as e:
                self.logger.debug("While iterating through the worker groups, the worker group disappeared: %s", str(e))
                continue
            self._run_due_schedules(event_schedules, worker_group, time_now, days[day_of_week])

    def _run_due_schedules(
        self,
        event_schedules: Sequence[Mapping[str, object]],
        worker_group: WorkerGroup,
        time_now: str,
        day: str,
    ) -> None:
        for event_schedule in event_schedules:
            if time_now != event_schedule.get("schedule_time"):
                continue
            repetition = event_schedule.get("repetition")
            if repetition and self._schedule_repeats_today(repetition, day):
                scheduled_task = narrowing.strict_str_or_none(event_schedule.get("schedule_task"))
                if scheduled_task is None:
                    continue
                self.run_task(
                    time_now,
                    scheduled_task,
                    narrowing.coerce_int_or_none(event_schedule.get("schedule_worker_count")),
                    worker_group,
                )

    @staticmethod
    def _schedule_repeats_today(repetition: object, day: str) -> bool:
        is_weekend = day in {"saturday", "sunday"}
        return (
            repetition == "daily"
            or (repetition == "weekday" and not is_weekend)
            or (repetition == "weekend" and is_weekend)
            or repetition == day
        )

    def init_worker_threads(self) -> None:
        with self.worker_registry_lock:
            self._remove_dead_worker_threads()

            # Check that we have enough workers running. Spawn new ones as required.
            worker_group_ids: list[int] = []
            worker_group_names: list[str] = []
            for worker_group in WorkerGroup.get_all_worker_groups():
                worker_group_id, worker_group_name, worker_count, names = self._init_worker_group(worker_group)
                worker_group_ids.append(worker_group_id)
                worker_group_names.extend(names)

                # Remove any workers that do not belong. The max number of supported workers is 12
                for i in range(worker_count, 12):
                    worker_id = f"{worker_group_name}-{i}"
                    # Only remove threads that are idle (never terminate a task just to reduce worker count)
                    if worker_id in self.worker_threads and self.worker_threads[worker_id].idle:
                        self.mark_worker_thread_as_redundant(worker_id)

            self._remove_obsolete_worker_threads(worker_group_ids, worker_group_names)

    def _remove_dead_worker_threads(self) -> None:
        for worker_id in list(self.worker_threads):
            if not self.worker_threads[worker_id].is_alive():
                del self.worker_threads[worker_id]

    def _remove_obsolete_worker_threads(self, worker_group_ids: list[int], worker_group_names: list[str]) -> None:
        for worker_id, worker in list(self.worker_threads.items()):
            group_removed = worker.worker_group_id not in worker_group_ids
            name_removed = worker.name not in worker_group_names
            if (group_removed or name_removed) and worker.idle:
                self.mark_worker_thread_as_redundant(worker_id)

    def _init_worker_group(self, worker_group: Mapping[str, object]) -> tuple[int, str, int, list[str]]:
        worker_group_id = narrowing.strict_int(worker_group["id"])
        worker_group_name = narrowing.strict_str(worker_group["name"])
        worker_count = narrowing.strict_int(worker_group["number_of_workers"])
        worker_names: list[str] = []
        for index in range(worker_count):
            worker_id = f"{worker_group_name}-{index}"
            worker_name = f"{worker_group_name}-Worker-{index + 1}"
            worker_names.append(worker_name)
            if worker_id not in self.worker_threads:
                self.start_worker_thread(worker_id, worker_name, worker_group_id)
        return worker_group_id, worker_group_name, worker_count, worker_names

    def fetch_available_remote_installation(
        self,
        library_name: str | None = None,
        preferred_installation_uuid: str | None = None,
        required_encoder: str | None = None,
    ) -> tuple[str | None, RemoteManagerInfo]:
        candidates: list[tuple[float, str, RemoteManagerInfo]] = []
        installation_ids = [t for t in self.available_remote_managers]
        for installation_id in installation_ids:
            if installation_id not in self.remote_task_manager_threads:
                manager_info = self.available_remote_managers[installation_id]
                # Check that a remote worker is on an installation with a matching library name
                installation_library_names = narrowing.string_list(manager_info.get("library_names"))
                if library_name is not None and library_name not in installation_library_names:
                    continue
                configured_uuid = manager_info.get("uuid") or manager_info.get("installation_uuid")
                if preferred_installation_uuid and configured_uuid != preferred_installation_uuid:
                    continue
                capabilities = narrowing.string_keyed_dict(manager_info.get("capabilities"))
                score = WorkerCapabilities.scheduling_score(capabilities, required_encoder)
                if score is None:
                    continue
                if score <= 0:
                    score = max(0.0, narrowing.coerce_float(manager_info.get("scheduling_score")))
                queue_depth = max(0, narrowing.coerce_int(manager_info.get("queue_depth")))
                effective_score = float(score) / (1 + queue_depth)
                candidates.append((effective_score, installation_id, manager_info))
        if not candidates:
            return None, {}
        _, installation_id, installation_info = min(candidates, key=lambda candidate: (-candidate[0], candidate[1]))
        return installation_id, installation_info

    def get_required_video_encoder(self, library_id: int | str) -> str | None:
        """Return the explicitly configured encoder for a library, if any."""
        settings = self.current_config["settings"]
        library_settings = settings.get(library_id)
        if library_settings is None:
            library_settings = settings.get(str(library_id), {})
        enabled_plugins = library_settings.get("enabled_plugins")
        if not isinstance(enabled_plugins, list):
            return None
        for plugin_value in enabled_plugins:
            plugin = narrowing.string_keyed_dict(plugin_value)
            if plugin.get("plugin_id") != "encoding_presets":
                continue
            plugin_settings = narrowing.string_keyed_dict(plugin.get("settings"))
            encoder = plugin_settings.get("video_encoder")
            if isinstance(encoder, str) and encoder:
                return encoder
            codec = plugin_settings.get("video_codec")
            if not isinstance(codec, str):
                return None
            return {
                "h264": "libx264",
                "hevc": "libx265",
                "av1": "libsvtav1",
                "vp9": "libvpx-vp9",
            }.get(codec)
        return None

    def init_remote_task_manager_thread(
        self,
        library_name: str | None = None,
        preferred_installation_uuid: str | None = None,
        required_encoder: str | None = None,
    ) -> bool:
        # Fetch the installation ID and info
        installation_id, installation_info = self.fetch_available_remote_installation(
            library_name=library_name,
            preferred_installation_uuid=preferred_installation_uuid,
            required_encoder=required_encoder,
        )

        # Ensure a worker was assigned
        if installation_id is None or not installation_info:
            return False

        del self.available_remote_managers[installation_id]

        # Startup a thread
        thread_factory = cast("type[RemoteTaskManager]", installation_link.RemoteTaskManager)
        thread = thread_factory(
            installation_id,
            f"RemoteTaskManager-{installation_id}",
            installation_info,
            self.remote_workers_pending_task_queue,
            self.complete_queue,
            self.event,
        )
        thread.safety_event_recorder = self._record_remote_safety_event
        thread.daemon = True
        thread.start()
        self.remote_task_manager_threads[installation_id] = thread
        return True

    def _record_remote_safety_event(self, code: str, message: str, **details: object) -> object:
        return record_safety_event(self.settings, self, code, message, **details)

    def remove_stale_available_remote_managers(self) -> None:
        """
        Loop over the current list of available remote managers and remove any that were marked available over X seconds ago
        This ensures that the data on these manager info lists are up-to-date if the remote installation config changes.

        :return:
        """
        installation_ids = [t for t in self.available_remote_managers]
        for installation_id in installation_ids:
            if installation_id not in self.remote_task_manager_threads:
                # Check that a remote worker is on an installation with a matching library name
                installation_info = self.available_remote_managers[installation_id]
                created = installation_info.get("created")
                if isinstance(created, datetime) and created < datetime.now() - timedelta(seconds=30):
                    del self.available_remote_managers[installation_id]

    def remove_stopped_remote_task_manager_threads(self) -> None:
        """
        Remove any redundant link managers from our list
        Remove any worker IDs from the remote_task_manager_threads list so they are freed up for another link manager thread

        :return:
        """
        # Remove any redundant link managers from our list
        thread_keys = [t for t in self.remote_task_manager_threads]
        for thread in thread_keys:
            if thread in self.remote_task_manager_threads and not self.remote_task_manager_threads[thread].is_alive():
                self.logger.debug("Removing thread %s", thread)
                del self.remote_task_manager_threads[thread]
                continue

    def terminate_unlinked_remote_task_manager_threads(self) -> None:
        """
        Mark a manager as redundant if the remote installation configuration has been removed

        :return:
        """
        # Get a list of configured UUIDS
        configured_uuids: dict[str, str | None] = {}
        for configured_remote_installation in self.settings.get_remote_installations():
            configured_uuid = configured_remote_installation.get("uuid")
            configured_address = configured_remote_installation.get("address")
            if isinstance(configured_uuid, str) and configured_uuid:
                configured_uuids[configured_uuid] = configured_address if isinstance(configured_address, str) else None
        # Find and remove any redundant link managers from our list
        term_log_msg = "Remote installation link with {} '{}' has been removed from settings. Marking tread for termination"
        for thread in self.remote_task_manager_threads:
            thread_info = self.remote_task_manager_threads[thread].get_info()
            installation_info = narrowing.string_keyed_dict(thread_info.get("installation_info"))
            thread_assigned_uuid = installation_info.get("uuid")
            thread_assigned_address = installation_info.get("address")
            # Ensure the UUID is still in our config
            if thread_assigned_uuid not in configured_uuids:
                self.mark_remote_task_manager_thread_as_redundant(thread)
                self.logger.info(term_log_msg.format("UUID", thread_assigned_uuid))
                continue
            # Ensure the configured address has not changed
            configured_address = configured_uuids.get(thread_assigned_uuid)
            if thread_assigned_address != configured_address:
                self.mark_remote_task_manager_thread_as_redundant(thread)
                self.logger.info(term_log_msg.format("address", thread_assigned_address))
                continue

    def update_remote_worker_availability_status(self) -> None:
        """
        Updates the list of available remote managers that can be started

        :return:
        """
        available_installations = self.links.check_remote_installation_for_available_workers()
        for installation_uuid in available_installations:
            remote_address = available_installations[installation_uuid].get("address", "")
            remote_auth = available_installations[installation_uuid].get("auth", "None")
            remote_username = available_installations[installation_uuid].get("username", "")
            remote_password = available_installations[installation_uuid].get("password", "")
            remote_api_token = available_installations[installation_uuid].get("api_token", "")
            remote_library_names = available_installations[installation_uuid].get("library_names", [])
            available_slots = max(0, narrowing.coerce_int(available_installations[installation_uuid].get("available_slots")))
            capabilities = narrowing.string_keyed_dict(available_installations[installation_uuid].get("capabilities"))
            scheduling_score = available_installations[installation_uuid].get("scheduling_score", 0)
            queue_depth = available_installations[installation_uuid].get("queue_depth", 0)
            for slot_number in range(available_slots):
                remote_manager_id = f"{installation_uuid}|M{slot_number}"
                if (
                    remote_manager_id in self.available_remote_managers
                    or remote_manager_id in self.remote_task_manager_threads
                ):
                    # This worker is already managed by a link manager thread or is already in the list of available workers
                    continue
                # Add this remote worker ID to the list of available remote managers
                self.available_remote_managers[remote_manager_id] = {
                    "uuid": installation_uuid,
                    "address": remote_address,
                    "auth": remote_auth,
                    "username": remote_username,
                    "password": remote_password,
                    "api_token": remote_api_token,
                    "library_names": remote_library_names,
                    "capabilities": capabilities,
                    "scheduling_score": scheduling_score,
                    "queue_depth": queue_depth,
                    "created": datetime.now(),
                }

    def start_worker_thread(self, worker_id: str, worker_name: str, worker_group: int | str) -> None:
        thread = Worker(worker_id, worker_name, worker_group, self.workers_pending_task_queue, self.complete_queue, self.event)
        thread._safety_event_recorder = self._record_worker_safety_event
        thread.daemon = True
        thread.start()
        self.worker_threads[worker_id] = thread

    def _record_worker_safety_event(
        self,
        settings: config.Config,
        foreman: SafetyForeman | None,
        code: str,
        message: str,
        **details: object,
    ) -> object:
        del foreman
        return record_safety_event(settings, self, code, message, **details)

    def fetch_available_worker_ids(self) -> list[str]:
        thread_ids: list[str] = []
        for thread in self.worker_threads:
            wt = self.worker_threads[thread]
            if wt.idle and wt.is_alive() and not wt.paused:
                thread_ids.append(str(wt.thread_id))
        return thread_ids

    def check_for_idle_workers(self) -> bool:
        for thread in self.worker_threads:
            wt = self.worker_threads[thread]
            if wt.idle and wt.is_alive() and not wt.paused:
                return True
        return False

    def check_for_idle_remote_workers(self) -> bool:
        return bool(self.available_remote_managers)

    def get_available_remote_library_names(self) -> list[str]:
        library_names: list[str] = []
        for installation_id in self.available_remote_managers:
            configured_names = self.available_remote_managers[installation_id].get("library_names")
            for library_name in narrowing.string_list(configured_names):
                if library_name not in library_names:
                    library_names.append(library_name)
        return library_names

    def get_tags_configured_for_worker(self, worker_id: str) -> list[str]:
        """Fetch the tags for a given worker ID"""
        with self.worker_registry_lock:
            worker_thread = self.worker_threads.get(worker_id)
            if worker_thread is None:
                raise ValueError(f"Worker ID '{worker_id}' is no longer registered")
            assigned_worker_group_id = worker_thread.worker_group_id
        # Workers created by this foreman always receive the integer DB group ID.
        worker_group = WorkerGroup(group_id=cast("int", assigned_worker_group_id))
        tags: object = worker_group.get_tags()
        return narrowing.string_list(tags)

    def postprocessor_queue_full(self) -> bool:
        """
        Check if Post-processor queue is greater than the number of workers enabled.
        If it is, return True. Else False.

        :return:
        """
        frontend_messages = FrontendPushMessages()
        # Use the configured worker count + 1 as the post-processor queue limit
        limit = int(self.get_total_worker_count()) + 1
        # Include a count of all available and busy remote workers for the postprocessor queue limit
        limit += len(self.available_remote_managers)
        limit += len(self.remote_task_manager_threads)
        current_count = len(self.task_queue.list_processed_tasks())
        if current_count > limit:
            msg = "There are currently {} items in the post-processor queue. Halting feeding workers until it drops below {}."
            self.logger.warning(msg.format(current_count, limit))
            frontend_messages.update(
                {
                    "id": "pendingTaskHaltedPostProcessorQueueFull",
                    "type": "status",
                    "code": "pendingTaskHaltedPostProcessorQueueFull",
                    "message": "",
                    "timeout": 0,
                }
            )
            return True

        # Remove the status notification
        frontend_messages.remove_item("pendingTaskHaltedPostProcessorQueueFull")
        return False

    def pause_worker_thread(self, worker_id: str, record_paused: bool = False) -> bool:
        """
        Pauses a single worker thread

        :param worker_id:
        :param record_paused:
        :return:
        """
        with self.worker_registry_lock:
            if worker_id not in self.worker_threads:
                self.logger.warning("Asked to pause Worker ID '%s', but this was not found.", worker_id)
                return False

            if not self.worker_threads[worker_id].paused_flag.is_set():
                self.logger.debug("Asked to pause Worker ID %s", worker_id)
                self.worker_threads[worker_id].paused_flag.set()
                if record_paused and worker_id not in self.paused_worker_threads:
                    self.paused_worker_threads.append(worker_id)
            return True

    def pause_all_worker_threads(
        self,
        worker_group_id: int | str | None = None,
        record_paused: bool = False,
    ) -> bool:
        """
        Pause all threads

        :param worker_group_id:
        :param record_paused:
        :return:
        """
        result = True
        with self.worker_registry_lock:
            for thread in list(self.worker_threads):
                # Limit by worker group if requested
                if worker_group_id and self.worker_threads[thread].worker_group_id != worker_group_id:
                    continue
                if not self.pause_worker_thread(thread, record_paused=record_paused):
                    result = False
        return result

    def resume_worker_thread(self, worker_id: str) -> bool:
        """
        Resume a single worker thread

        :param worker_id:
        :type worker_id:
        :return:
        :rtype:
        """
        self.logger.debug("Asked to resume Worker ID %s", worker_id)
        if getattr(self, "safety_latched", False):
            self.logger.warning("Refusing to resume Worker ID '%s' while the durable safety latch is active.", worker_id)
            return False
        with self.worker_registry_lock:
            if worker_id not in self.worker_threads:
                self.logger.warning("Asked to resume Worker ID '%s', but this was not found.", worker_id)
                return False

            self.worker_threads[worker_id].paused_flag.clear()
            if worker_id in self.paused_worker_threads:
                self.paused_worker_threads.remove(worker_id)
            return True

    def resume_all_worker_threads(
        self,
        worker_group_id: int | str | None = None,
        recorded_paused_only: bool = False,
    ) -> bool:
        """Resume all threads"""
        result = True
        with self.worker_registry_lock:
            for thread in list(self.worker_threads):
                # Limit by worker group if requested
                if worker_group_id and self.worker_threads[thread].worker_group_id != worker_group_id:
                    continue
                if recorded_paused_only and thread not in self.paused_worker_threads:
                    continue
                if not self.resume_worker_thread(thread):
                    result = False
        return result

    def terminate_worker_thread(self, worker_id: str) -> bool:
        """
        Terminate a single worker thread

        :param worker_id:
        :type worker_id:
        :return:
        :rtype:
        """
        self.logger.debug("Asked to terminate Worker ID %s", worker_id)
        with self.worker_registry_lock:
            if worker_id not in self.worker_threads:
                self.logger.warning("Asked to terminate Worker ID '%s', but this was not found.", worker_id)
                return False

            self.mark_worker_thread_as_redundant(worker_id)
            return True

    def terminate_all_worker_threads(self) -> bool:
        """Terminate all threads"""
        result = True
        with self.worker_registry_lock:
            for thread in list(self.worker_threads):
                if not self.terminate_worker_thread(thread):
                    result = False
        return result

    def mark_worker_thread_as_redundant(self, worker_id: str) -> None:
        with self.worker_registry_lock:
            worker_thread = self.worker_threads.get(worker_id)
        if worker_thread:
            worker_thread.redundant_flag.set()

    def mark_remote_task_manager_thread_as_redundant(self, link_manager_id: str) -> None:
        self.remote_task_manager_threads[link_manager_id].redundant_flag.set()

    def hand_task_to_workers(
        self,
        item: Task,
        local: bool = True,
        library_name: str | None = None,
        worker_id: str | None = None,
    ) -> bool:
        return self._hand_local_task(item, worker_id) if local else self._hand_remote_task(item, library_name)

    def _hand_local_task(self, item: Task, worker_id: str | None) -> bool:
        if worker_id not in self.worker_threads or not self.worker_threads[worker_id].is_alive():
            return False
        self.worker_threads[worker_id].set_task(item)
        if item.get_task_type() == "local":
            event_data = {
                "library_id": item.get_task_library_id(),
                "task_id": item.get_task_id(),
                "task_type": item.get_task_type(),
                "task_schedule_type": "local",
                "remote_installation_info": {},
                "source_data": item.get_source_data(),
            }
            PluginsHandler().run_event_plugins_for_plugin_type("events.task_scheduled", event_data)
        return True

    def _hand_remote_task(self, item: Task, library_name: str | None) -> bool:
        self.remote_workers_pending_task_queue.put(item)
        preferred = getattr(getattr(item, "task", None), "remote_installation_uuid", None)
        preferred_uuid = preferred if isinstance(preferred, str) and preferred else None
        manager_started = self.init_remote_task_manager_thread(
            library_name=library_name,
            preferred_installation_uuid=preferred_uuid,
            required_encoder=self.get_required_video_encoder(item.get_task_library_id()),
        )
        if manager_started:
            return True
        self.remote_workers_pending_task_queue.get_nowait()
        return False

    def link_manager_tread_heartbeat(self) -> None:
        """
        Run a list of tasks to test the status of our Link Management threads.
        Unlike worker threads, Link Management threads live and die for a single task.
        If a Link Management thread is alive for more than 10 seconds without picking up a task, it will die.
        This function will reap all dead or completed threads and clean up issues where a thread may have died
            before running a task that was added to the pending task queue (in which case a new thread should be started)

        :return:
        """
        # Only run heartbeat every 10 seconds
        time_now = time.time()
        if self.link_heartbeat_last_run > (time_now - 10):
            return
        # Terminate remote manager threads for unlinked installations
        self.terminate_unlinked_remote_task_manager_threads()
        # Clear out dead threads
        self.remove_stopped_remote_task_manager_threads()
        # Clear out old available workers (should last only a minute before being refreshed)
        self.remove_stale_available_remote_managers()
        # Check for updates to the worker availability status of linked remote installations
        self.update_remote_worker_availability_status()
        # Mark this as the last time run
        self.link_heartbeat_last_run = time_now

    def _drain_completed_tasks(self) -> None:
        """Move all finished tasks from the complete_queue to 'processed' status."""
        while not self.abort_flag.is_set() and not self.complete_queue.empty():
            self.event.wait(0.5)
            try:
                task_item = self.complete_queue.get_nowait()
                task_item.set_status("processed")
            except queue.Empty:
                continue
            except (AttributeError, KeyError, TypeError) as e:
                self.logger.exception("Exception when fetching completed task report from worker: %s", str(e))

    def _sync_and_validate_workers(self) -> bool:
        """Ensure correct worker count and valid config. Returns True if config is valid."""
        if not self.abort_flag.is_set():
            self.init_worker_threads()

        valid_config = self.validate_worker_config()
        if not valid_config:
            self.pause_all_worker_threads(record_paused=True)
            return False

        if getattr(self, "safety_latched", False):
            self.pause_all_worker_threads(record_paused=True)
            return False

        with self.worker_registry_lock:
            if self.paused_worker_threads:
                self.resume_all_worker_threads(recorded_paused_only=True)
                self.paused_worker_threads = []
        return True

    def _record_worker_metrics(self, last_metrics_time: float) -> float:
        """Emit worker metrics, adjusting the interval based on worker activity."""
        workers_info = self.get_all_worker_status()
        any_busy = any(not worker_info.get("idle") for worker_info in workers_info)
        metrics_interval = 2 if any_busy else 10
        now = time.time()
        if now - last_metrics_time < metrics_interval:
            return last_metrics_time
        for worker_info in workers_info:
            CompressoLogging.log_metric(
                "worker_info",
                worker_name=worker_info.get("name"),
                idle=worker_info.get("idle"),
                paused=worker_info.get("paused"),
                start_time=worker_info.get("start_time"),
                current_task=worker_info.get("current_task"),
                current_file=worker_info.get("current_file"),
                current_command=worker_info.get("current_command"),
                worker_log_tail=worker_info.get("worker_log_tail"),
                runners_info=worker_info.get("runners_info"),
                subprocess=worker_info.get("subprocess"),
            )
        return now

    def _check_queue_idle_transition(self, was_active: bool) -> bool:
        """Detect queue transition from active→idle and dispatch notification. Returns current active state."""
        queue_has_tasks = not self.task_queue.task_list_pending_is_empty()
        any_workers_busy = any(
            not self.worker_threads[t].idle for t in self.worker_threads if self.worker_threads[t].is_alive()
        )
        any_remote_workers_busy = any(self.remote_task_manager_threads[t].is_alive() for t in self.remote_task_manager_threads)
        queue_is_active = queue_has_tasks or any_workers_busy or any_remote_workers_busy
        if was_active and not queue_is_active:
            try:
                from compresso.libs.external_notifications import ExternalNotificationDispatcher

                ExternalNotificationDispatcher().dispatch("queue_empty", {})
            except Exception as e:
                self.logger.debug("Failed to dispatch queue_empty notification: %s", e)
        return queue_is_active

    def _find_and_assign_pending_task(self, allow_local_check: bool) -> bool:
        """Find an idle worker and assign the next pending task. Returns updated allow_local_check flag."""
        if self.abort_flag.is_set() or self.task_queue.task_list_pending_is_empty():
            return allow_local_check

        self.link_manager_tread_heartbeat()

        # Gate: don't assign if pending task queues haven't been consumed yet
        if self.workers_pending_task_queue.full() or self.remote_workers_pending_task_queue.full():
            return allow_local_check

        choice = self._pending_worker_choice(allow_local_check)
        if choice is None:
            self.event.wait(1)
            return True
        allow_local_check, process_local, get_local_pending_tasks_only, worker_ids = choice

        # Check if postprocessor task queue is full
        if self.postprocessor_queue_full():
            self.event.wait(5)
            return allow_local_check

        next_item_to_process, available_worker_id = self._claim_pending_task(
            process_local, get_local_pending_tasks_only, worker_ids
        )
        if process_local and available_worker_id is None:
            self.event.wait(1)
            return False

        if next_item_to_process:
            self._assign_claimed_task(next_item_to_process, process_local, available_worker_id)

        return allow_local_check

    def _assign_claimed_task(self, item: Task, process_local: bool, worker_id: str | None) -> None:
        try:
            source_abspath = item.get_source_abspath()
            library_name = item.get_task_library_name()
        except (AttributeError, KeyError, TypeError) as error:
            self.logger.exception("Exception in fetching task details: %s", error)
            self.event.wait(3)
            return
        self.logger.info("Processing item - %s", source_abspath)
        if self.hand_task_to_workers(item, local=process_local, library_name=library_name, worker_id=worker_id):
            return
        self.logger.warning("Re-queueing task; no capable worker for '%s'", source_abspath)
        try:
            item.set_status("pending")
        except (AttributeError, TypeError, peewee.PeeweeException) as error:
            self.logger.exception("Unable to return claimed task to pending: %s", error)
        self.task_queue.requeue_tasks_at_bottom(item.get_task_id())

    def _pending_worker_choice(self, allow_local_check: bool) -> tuple[bool, bool, bool, list[str]] | None:
        if allow_local_check and self.check_for_idle_workers():
            worker_ids = self.fetch_available_worker_ids()
            return (allow_local_check, True, False, worker_ids) if worker_ids else None
        if self.check_for_idle_remote_workers():
            return True, False, True, []
        return None

    def _claim_pending_task(
        self, process_local: bool, local_only: bool, worker_ids: list[str]
    ) -> tuple[Task | None, str | None]:
        if not process_local:
            candidate = self.task_queue.get_next_pending_tasks(
                local_only=local_only, library_names=self.get_available_remote_library_names()
            )
            return candidate if candidate else None, None
        for worker_id in worker_ids:
            try:
                library_tags = self.get_tags_configured_for_worker(worker_id)
            except (ValueError, AttributeError, TypeError, peewee.PeeweeException) as error:
                self.logger.debug("Error while fetching the tags for the configured worker: %s", error)
                break
            candidate = self.task_queue.get_next_pending_tasks(local_only=local_only, library_tags=library_tags)
            if candidate:
                return candidate, worker_id
        return None, None

    def run(self) -> None:
        self.logger.info("Starting Foreman Monitor loop")

        allow_local_idle_worker_check = True
        last_metrics_time = 0.0
        was_queue_active = False

        while not self.abort_flag.is_set():
            self.event.wait(2)

            try:
                self._drain_completed_tasks()

                if not self._sync_and_validate_workers():
                    continue

                last_metrics_time = self._record_worker_metrics(last_metrics_time)

                was_queue_active = self._check_queue_idle_transition(was_queue_active)

                self.manage_event_schedules()

                allow_local_idle_worker_check = self._find_and_assign_pending_task(allow_local_idle_worker_check)
            except Exception:
                self.logger.exception("Unhandled exception in Foreman main loop")
                self.event.wait(5)

        self.logger.info("Leaving Foreman Monitor loop...")

    def get_all_worker_status(self) -> list[dict[str, object]]:
        all_status: list[dict[str, object]] = []
        for thread in self.worker_threads:
            all_status.append(self.worker_threads[thread].get_status())
        return all_status

    def get_worker_status(self, worker_id: int | str) -> dict[str, object]:
        result: dict[str, object] = {}
        for thread in self.worker_threads:
            # Worker threads are keyed by their string thread_id (e.g. "GroupName-0"),
            # so compare as strings rather than coercing to int.
            if str(worker_id) == str(thread):
                result = self.worker_threads[thread].get_status()
        return result
