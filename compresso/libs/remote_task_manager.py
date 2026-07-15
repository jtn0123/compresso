#!/usr/bin/env python3

"""
compresso.remote_task_manager.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     28 Oct 2021, (7:24 PM)

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
import os.path
import queue
import re
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from compresso.libs import common
from compresso.libs.installation_link import Links
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler
from compresso.libs.remote_task_lease import RemoteTaskLease
from compresso.libs.resumable_transfer import file_sha256
from compresso.libs.task import TaskDataStore


@dataclass
class RemoteTaskContext:
    original_abspath: str
    address: str | None
    library_name: str
    library_path: str
    remote_task_id: int | str | None = None
    remote_task_status: str | None = None


@dataclass(frozen=True)
class LeasePhaseResult:
    succeeded: bool
    deferred: bool = False


@dataclass(frozen=True)
class UploadPhaseResult:
    succeeded: bool
    remote_task_id: int | str | None = None
    remote_task_status: str | None = None
    cleanup_remote: bool = False


@dataclass(frozen=True)
class MonitoringPhaseResult:
    succeeded: bool
    worker_id: object | None = None
    cleanup_remote: bool = False


@dataclass(frozen=True)
class DownloadPhaseResult:
    succeeded: bool
    cache_path: str | None = None
    checksum: str | None = None
    cleanup_remote: bool = False


@dataclass(frozen=True)
class FinalizationPhaseResult:
    succeeded: bool
    cleanup_remote: bool = False


@dataclass(frozen=True)
class CleanupPhaseResult:
    succeeded: bool
    remote_removed: bool


class RemoteTaskManager(threading.Thread):
    paused = False

    current_task = None
    worker_log = None
    start_time = None
    finish_time = None

    worker_subprocess_percent = "0"
    worker_subprocess_elapsed = "0"

    worker_runners_info: dict = {}

    def __init__(self, thread_id, name, installation_info, pending_queue, complete_queue, event):
        super().__init__(name=name)
        self.thread_id = thread_id
        self.name = name
        self.event = event
        self.installation_info = installation_info
        self.pending_queue = pending_queue
        self.complete_queue = complete_queue

        self.links = Links()
        self.lease_token = None
        self.origin_installation_uuid = None
        self.safety_event_recorder = None

        # Create 'redundancy' flag. When this is set, the worker should die
        self.redundant_flag = threading.Event()
        self.redundant_flag.clear()

        # Create 'paused' flag. When this is set, the worker should be paused
        self.paused_flag = threading.Event()
        self.paused_flag.clear()

        # Create logger for this worker
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)

    def _log(self, message, message2="", level="info"):
        message = common.format_message(message, message2)
        getattr(self.logger, level)(message)

    @staticmethod
    def _existing_library_result(candidate_path, library_path):
        """Return an existing result only after confining it to the local library."""
        library_root = os.path.realpath(library_path)
        candidate = os.path.realpath(candidate_path)
        try:
            confined = candidate != library_root and os.path.commonpath((library_root, candidate)) == library_root
        except ValueError:
            confined = False
        if not confined or not os.path.isfile(candidate):
            return None
        return candidate

    def get_info(self):
        return {
            "name": self.name,
            "installation_info": self.installation_info,
        }

    def run(self):
        # A manager should only run for a single task and connection to a single worker.
        # If either of these become unavailable, then the manager should exit
        self._log(f"Starting remote task manager {self.thread_id} - {self.installation_info.get('address')}")
        # Pull task
        next_task = None
        try:
            # Pending task queue has an item available. Fetch it.
            next_task = self.pending_queue.get_nowait()

            # Configure worker for this task
            self.__set_current_task(next_task)

            # Process the set task
            self.__process_task_queue_item()

        except queue.Empty:
            self._log("Remote task manager started by the pending queue was empty", level="warning")
        except Exception as e:
            self._log(f"Exception in processing job with {self.name}:", message2=str(e), level="exception")
            if self.current_task is not None:
                # Task was being processed -- mark it as failed and send to complete queue
                self.current_task.set_success(False)
                self.__write_failure_to_worker_log()
                self.complete_queue.put(self.current_task)
                self.__unset_current_task()
            elif next_task is not None:
                # Task was dequeued but never started -- requeue it
                try:
                    self.pending_queue.put(next_task)
                except Exception:
                    self._log("Failed to requeue task after exception", level="error")

        self._log(f"Stopping remote task manager {self.thread_id} - {self.installation_info.get('address')}")

    def __set_current_task(self, current_task):
        """Sets the given task to the worker class"""
        self.current_task = current_task
        self.worker_log = []

        # Execute event plugin runners
        event_data = {
            "library_id": self.current_task.get_task_library_id(),
            "task_id": self.current_task.get_task_id(),
            "task_type": self.current_task.get_task_type(),
            "task_schedule_type": "remote",
            "remote_installation_info": {
                "uuid": self.installation_info.get("installation_uuid"),
                "address": self.installation_info.get("remote_address"),
            },
            "source_data": self.current_task.get_source_data(),
        }
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type("events.task_scheduled", event_data)

    def __unset_current_task(self):
        self.current_task = None
        self.worker_runners_info = {}
        self.worker_log = []

    def __process_task_queue_item(self):
        """
        Processes the set task.

        :return:
        """
        # Set the progress to an empty string
        self.worker_subprocess_percent = "0"
        self.worker_subprocess_elapsed = "0"

        lease_result = self._lease_phase()
        if not lease_result.succeeded:
            self.current_task.task.deferred_until = datetime.now() + timedelta(seconds=10)
            self.current_task.task.save()
            self.current_task.set_status("pending")
            self.__unset_current_task()
            return

        # Log the start of the job
        self._log(f"Picked up job - {self.current_task.get_source_abspath()}")

        # Mark as being "in progress"
        self.current_task.set_status("in_progress")

        # Start current task stats
        self.__set_start_task_stats()

        # Process the file. Will return true if success, otherwise false
        success = self.__send_task_to_remote_worker_and_monitor()
        # Mark the task as either success or not
        self.current_task.set_success(success)

        # Mark task completion statistics
        self.__set_finish_task_stats()

        # Log completion of job
        self._log(f"Finished job - {self.current_task.get_source_abspath()}")

        # Place the task into the completed queue
        self.complete_queue.put(self.current_task)

        # Reset the current file info for the next task
        self.__unset_current_task()

    def _lease_phase(self) -> LeasePhaseResult:
        acquired = self._acquire_remote_lease()
        return LeasePhaseResult(succeeded=acquired, deferred=not acquired)

    def _acquire_remote_lease(self):
        installation_uuid = self.installation_info.get("installation_uuid") or self.installation_info.get("uuid")
        self.lease_token = RemoteTaskLease.acquire(self.current_task.task, installation_uuid)
        if not self.lease_token:
            if self.safety_event_recorder is not None:
                self.safety_event_recorder(
                    "duplicate-lease",
                    "A remote task already has a different active owner",
                    installation_uuid=installation_uuid,
                    task_id=self.current_task.get_task_id(),
                )
            self._log(
                f"Unable to acquire remote task lease for installation '{installation_uuid}'",
                level="warning",
            )
            return False
        self.origin_installation_uuid = self.links.session.get_installation_uuid()
        return True

    def _remote_identity(self):
        identity = {"job_id": self.current_task.task.job_id}
        if self.lease_token:
            identity.update(
                {
                    "lease_token": self.lease_token,
                    "origin_installation_uuid": self.origin_installation_uuid,
                }
            )
        return identity

    def _heartbeat_remote_lease(self):
        if not self.lease_token:
            return False
        return RemoteTaskLease.heartbeat(self.current_task.task, self.lease_token)

    def __set_start_task_stats(self):
        """Sets the initial stats for the start of a task"""
        # Set the start time to now
        self.start_time = time.time()

        # Clear the finish time
        self.finish_time = None

        # Format our starting statistics data
        self.current_task.task.processed_by_worker = self.name
        self.current_task.task.start_time = self.start_time
        self.current_task.task.finish_time = self.finish_time

    def __set_finish_task_stats(self):
        """Sets the final stats for the end of a task"""
        # Set the finish time to now
        self.finish_time = time.time()

        # Set the finish time in the statistics data
        self.current_task.task.finish_time = self.finish_time

    def __write_failure_to_worker_log(self):
        """Persist the standard remote-task failure explanation."""
        self.worker_log.append("\n\nREMOTE TASK FAILED!")
        self.worker_log.append("\nAn error occurred during one of these stages:")
        self.worker_log.append("\n    - while sending task to remote installation")
        self.worker_log.append("\n    - during the remote task processing")
        self.worker_log.append("\n    - while attempting to retrieve the completed task from the remote installation")
        self.worker_log.append("\nCheck Compresso logs for more information.")
        self.worker_log.append(f"\nRelevant logs will be prefixed with 'ERROR:Compresso.{self.name}'")
        self.current_task.save_command_log(self.worker_log)

    def __send_task_to_remote_worker_and_monitor(self):
        """Run the remote task lifecycle through explicit typed phases."""
        context = self._prepare_remote_task_context()
        if context is None:
            return False

        upload = self._upload_phase(context)
        context.remote_task_id = upload.remote_task_id
        context.remote_task_status = upload.remote_task_status
        if not upload.succeeded:
            return self._finish_failed_phase(context, upload.cleanup_remote)

        monitoring = self._monitoring_phase(context)
        if not monitoring.succeeded:
            return self._finish_failed_phase(context, monitoring.cleanup_remote)

        download = self._download_phase(context)
        if not download.succeeded:
            return self._finish_failed_phase(context, download.cleanup_remote)

        finalization = self._finalization_phase(context, download)
        if not finalization.succeeded:
            return self._finish_failed_phase(context, finalization.cleanup_remote)

        return self._cleanup_phase(context).succeeded

    def _finish_failed_phase(self, context, cleanup_remote):
        if cleanup_remote:
            self._cleanup_phase(context)
        return False

    def _prepare_remote_task_context(self):
        original_abspath = self.current_task.get_source_abspath()
        if not os.path.exists(original_abspath):
            self._log(f"File no longer exists '{original_abspath}'. Was it removed?", level="warning")
            self.__write_failure_to_worker_log()
            return None

        library_id = self.current_task.get_task_library_id()
        try:
            library = Library(library_id)
        except Exception:
            self._log(f"Unable to fetch library config for ID {library_id}", level="exception")
            self.__write_failure_to_worker_log()
            return None
        return RemoteTaskContext(
            original_abspath=original_abspath,
            address=self.installation_info.get("address"),
            library_name=library.get_name(),
            library_path=library.get_path(),
        )

    def _upload_phase(self, context: RemoteTaskContext) -> UploadPhaseResult:
        library_config = self.links.get_the_remote_library_config_by_name(
            self.installation_info,
            context.library_name,
        )
        if not isinstance(library_config, dict):
            library_config = {}

        send_file = bool(library_config.get("enable_remote_only"))
        if not send_file and (not library_config.get("id") or not library_config.get("path")):
            self._log(
                f"Remote library mapping for '{context.library_name}' is unavailable. Falling back to a checksummed upload.",
                level="warning",
            )
            send_file = True

        result: UploadPhaseResult | None = None
        if not send_file:
            result = self._create_remote_task_from_library_path(context, library_config)
            if result is not None and not result.succeeded:
                return result
        if result is None:
            result = self._upload_remote_task_source(context)
        if not result.succeeded:
            return result
        if result.remote_task_id is None:
            self._log("Failed to create remote task. Var remote_task_id is still None", level="error")
            self.__write_failure_to_worker_log()
            return UploadPhaseResult(False)

        current_task = self.current_task
        if current_task is None:
            raise RuntimeError("remote task disappeared during upload")
        current_task.task.remote_task_id = int(result.remote_task_id)
        current_task.task.save()
        if not self._set_remote_task_library(context, result):
            return UploadPhaseResult(
                False,
                result.remote_task_id,
                result.remote_task_status,
                cleanup_remote=True,
            )
        if not self._start_remote_task(context, result):
            return UploadPhaseResult(
                False,
                result.remote_task_id,
                result.remote_task_status,
                cleanup_remote=True,
            )
        return result

    def _create_remote_task_from_library_path(
        self,
        context: RemoteTaskContext,
        library_config: dict,
    ) -> UploadPhaseResult | None:
        remote_library_path = library_config.get("path")
        if not isinstance(remote_library_path, str) or not remote_library_path:
            return None
        original_relpath = os.path.relpath(context.original_abspath, context.library_path)
        remote_original_abspath = os.path.join(remote_library_path, original_relpath)
        info = self.links.new_pending_task_create_on_remote_installation(
            self.installation_info,
            remote_original_abspath,
            library_config.get("id"),
            **self._remote_identity(),
        )
        if not info:
            self._log(
                f"Unable to create remote pending task for path '{remote_original_abspath}'. Fallback to sending file.",
                level="debug",
            )
            return None
        error = info.get("error", "").lower()
        if "path does not exist" in error:
            self._log(
                f"Unable to find file in remote library's path '{remote_original_abspath}'. Fallback to sending file.",
                level="debug",
            )
            return None
        if "task already exists" in error:
            self._log(
                f"A remote task already exists with the path '{remote_original_abspath}'. Fallback to sending file.",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return UploadPhaseResult(False)
        return UploadPhaseResult(
            True,
            remote_task_id=info.get("id"),
            remote_task_status=info.get("status"),
        )

    def _upload_remote_task_source(self, context: RemoteTaskContext) -> UploadPhaseResult:
        initial_checksum = file_sha256(context.original_abspath)
        initial_file_size = os.path.getsize(context.original_abspath)
        upload_deadline = time.monotonic() + 1800
        info = {}
        while not self.redundant_flag.is_set():
            if time.monotonic() > upload_deadline:
                self._log(f"Upload retry deadline exceeded for '{context.original_abspath}'", level="error")
                self.__write_failure_to_worker_log()
                return UploadPhaseResult(False)

            lock_key = None
            if initial_file_size > 100000000:
                lock_key = self.links.acquire_network_transfer_lock(
                    context.address,
                    transfer_limit=1,
                    lock_type="send",
                )
                if not lock_key:
                    self.event.wait(1)
                    continue

            self._log(
                f"Uploading file to remote installation '{context.original_abspath}'",
                level="debug",
            )
            upload_identity = self._remote_identity()

            def upload_progress(active_lock=lock_key):
                lock_active = not active_lock or self.links.refresh_network_transfer_lock(active_lock)
                lease_active = self._heartbeat_remote_lease() if self.lease_token else True
                return bool(lock_active and lease_active)

            if self.lease_token or lock_key:
                upload_identity["progress_callback"] = upload_progress
            try:
                info = self.links.send_file_to_remote_installation(
                    self.installation_info,
                    context.original_abspath,
                    **upload_identity,
                )
            finally:
                self.links.release_network_transfer_lock(lock_key)
            if info:
                break
            self._log(
                f"Upload interrupted; retaining resume state for '{context.original_abspath}'",
                level="warning",
            )
            if not self.lease_token:
                self.__write_failure_to_worker_log()
                return UploadPhaseResult(False)
            if not self._heartbeat_remote_lease():
                self._log(
                    f"Remote task lease was lost during upload for '{context.original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return UploadPhaseResult(False)
            self.event.wait(2)

        remote_task_id = info.get("id")
        remote_task_status = info.get("status")
        if info.get("checksum") != initial_checksum:
            self._record_transfer_corruption("upload", "A remote upload checksum did not match its source")
            self._log(
                f"The uploaded file did not return a correct checksum '{context.original_abspath}'",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return UploadPhaseResult(
                False,
                remote_task_id,
                remote_task_status,
                cleanup_remote=True,
            )
        return UploadPhaseResult(True, remote_task_id, remote_task_status)

    def _record_transfer_corruption(self, phase, message):
        if self.safety_event_recorder is not None:
            self.safety_event_recorder(
                "manifest-corruption",
                message,
                task_id=self.current_task.get_task_id(),
                phase=phase,
            )

    def _set_remote_task_library(self, context, upload):
        deadline = time.monotonic() + 1800
        while not self.redundant_flag.is_set():
            if upload.remote_task_status in {"in_progress", "processed", "complete"}:
                break
            if time.monotonic() > deadline:
                self._log(
                    f"Set-remote-library retry deadline exceeded for '{context.original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return False
            result = self.links.set_the_remote_task_library(
                self.installation_info,
                upload.remote_task_id,
                context.library_name,
            )
            if result is None:
                self.event.wait(2)
                continue
            if not result.get("success"):
                self._log(
                    f"Failed to match a remote library named '{context.library_name}'."
                    " Remote installation will use the default library",
                    level="warning",
                )
            break
        return True

    def _start_remote_task(self, context, upload):
        deadline = time.monotonic() + 1800
        while not self.redundant_flag.is_set():
            if upload.remote_task_status in {"in_progress", "processed", "complete"}:
                break
            if time.monotonic() > deadline:
                self._log(
                    f"Start-task retry deadline exceeded for '{context.original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return False
            result = self.links.start_the_remote_task_by_id(
                self.installation_info,
                upload.remote_task_id,
            )
            if not result:
                self.event.wait(2)
                continue
            if not result.get("success"):
                self._log(
                    f"Failed to set initial remote pending task to status '{context.original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return False
            break
        return True

    def _monitoring_phase(self, context: RemoteTaskContext) -> MonitoringPhaseResult:
        worker_id = None
        task_status = ""
        last_status_fetch = 0.0
        polling_delay = 5
        consecutive_poll_failures = 0
        first_failure_time: float | None = None
        while task_status != "complete":
            self.event.wait(1)
            if self.redundant_flag.is_set():
                if worker_id:
                    self.links.terminate_remote_worker(self.installation_info, worker_id)
                break

            time_now = time.time()
            if last_status_fetch > (time_now - polling_delay):
                continue
            if first_failure_time and (time_now - first_failure_time) > 1800:
                self._log(
                    f"Remote link unreachable for over 1800 seconds, giving up on task '{context.original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return MonitoringPhaseResult(False, worker_id)

            all_task_states = self.links.get_remote_pending_task_state(
                self.installation_info,
                context.remote_task_id,
            )
            task_status = ""
            polling_delay = 5
            if all_task_states:
                if self.lease_token and not self._heartbeat_remote_lease():
                    self._log(
                        f"Remote task lease was lost while polling '{context.original_abspath}'",
                        level="error",
                    )
                    self.__write_failure_to_worker_log()
                    return MonitoringPhaseResult(False, worker_id)
                consecutive_poll_failures = 0
                first_failure_time = None
                task_status = self._parse_remote_task_status(
                    all_task_states,
                    context.remote_task_id,
                    context.original_abspath,
                )
                if task_status is None:
                    return MonitoringPhaseResult(False, worker_id)

            if task_status == "complete":
                break
            if not all_task_states:
                consecutive_poll_failures += 1
                polling_delay, first_failure_time = self._remote_poll_failure(
                    context,
                    consecutive_poll_failures,
                    time_now,
                    first_failure_time,
                )
                last_status_fetch = time_now
                continue
            if task_status == "removed":
                self._log(
                    f"Task has been removed by remote installation '{context.original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return MonitoringPhaseResult(False, worker_id)
            if task_status != "in_progress":
                last_status_fetch = time_now
                polling_delay = 10
                continue

            worker_id, progress_updated = self._update_remote_worker_progress(
                context.remote_task_id,
                worker_id,
            )
            if not progress_updated:
                last_status_fetch = time_now
                continue
            last_status_fetch = time_now

        if self.redundant_flag.is_set():
            worker_log = self.worker_log
            current_task = self.current_task
            if worker_log is None or current_task is None:
                raise RuntimeError("remote task state disappeared during monitoring")
            worker_log += ["\n\nREMOTE LINK MANAGER TERMINATED!"]
            current_task.save_command_log(worker_log)
            return MonitoringPhaseResult(False, worker_id)

        self._log(f"Remote task completed '{context.original_abspath}'", level="info")
        return MonitoringPhaseResult(True, worker_id)

    def _parse_remote_task_status(self, all_task_states, remote_task_id, original_abspath):
        remote_results = all_task_states.get("results") if isinstance(all_task_states, dict) else None
        if not isinstance(remote_results, list) or not all(isinstance(item, dict) for item in remote_results):
            self._log(
                f"Remote task status response was malformed for '{original_abspath}'",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return None
        for task_state in remote_results:
            if str(task_state.get("id")) == str(remote_task_id):
                return task_state.get("status")
        return "removed"

    def _remote_poll_failure(self, context, failure_count, time_now, first_failure_time):
        if failure_count == 3 and self.lease_token and self.safety_event_recorder is not None:
            self.safety_event_recorder(
                "remote-poll-loss",
                "Three consecutive remote status polls failed while this node held the task lease",
                task_id=self.current_task.get_task_id(),
                installation_uuid=self.installation_info.get("installation_uuid") or self.installation_info.get("uuid"),
            )
        if first_failure_time is None:
            first_failure_time = time_now
        polling_delay = min(60, 5 * (2 ** min(failure_count, 4)))
        self._log(
            f"Lost contact with remote installation (attempt {failure_count}),"
            f" next poll in {polling_delay}s for '{context.original_abspath}'",
            level="warning",
        )
        return polling_delay, first_failure_time

    def _update_remote_worker_progress(self, remote_task_id, worker_id):
        if not worker_id:
            workers_status = self.links.get_all_worker_status(self.installation_info)
            if not workers_status:
                return worker_id, False
            for worker in workers_status:
                if str(worker.get("current_task")) == str(remote_task_id):
                    worker_id = worker.get("id")

        worker_status = self.links.get_single_worker_status(self.installation_info, worker_id)
        if not worker_status:
            return worker_id, False
        self.paused = worker_status.get("paused")
        self.worker_log = worker_status.get("worker_log_tail")
        self.worker_runners_info = worker_status.get("runners_info")
        self.worker_subprocess_percent = worker_status.get("subprocess", {}).get("percent")
        self.worker_subprocess_elapsed = worker_status.get("subprocess", {}).get("elapsed")
        return worker_id, True

    def _download_phase(self, context: RemoteTaskContext) -> DownloadPhaseResult:
        data, cache_directory = self._fetch_remote_result_data(context)
        if data is None:
            return DownloadPhaseResult(False)
        if not data.get("task_success"):
            self.__write_failure_to_worker_log()
            return DownloadPhaseResult(False)

        task_label = data.get("task_label")
        self._log(
            f"Remote task #{context.remote_task_id} was successful, proceeding to download the completed file '{task_label}'",
            level="debug",
        )
        self._log("Remote task result path will be transferred", level="debug")
        remote_result_path = data.get("abspath")
        if not isinstance(remote_result_path, str) or not remote_result_path:
            self._log(
                f"Remote task result path was malformed for '{context.original_abspath}'",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return DownloadPhaseResult(False)

        local_result_path = self._existing_library_result(remote_result_path, context.library_path)
        if local_result_path:
            task_cache_path = self._copy_shared_remote_result(
                context,
                local_result_path,
                cache_directory,
            )
            if task_cache_path is None:
                return DownloadPhaseResult(False, cleanup_remote=True)
        else:
            task_cache_path = self._set_download_cache_path(remote_result_path, cache_directory)
            downloaded, cleanup_remote = self._download_remote_result(
                context,
                task_label,
                task_cache_path,
            )
            if not downloaded:
                return DownloadPhaseResult(False, cleanup_remote=cleanup_remote)

        if self.redundant_flag.is_set():
            worker_log = self.worker_log
            current_task = self.current_task
            if worker_log is None or current_task is None:
                raise RuntimeError("remote task state disappeared during download")
            worker_log += ["\n\nREMOTE LINK MANAGER TERMINATED!"]
            current_task.save_command_log(worker_log)
            return DownloadPhaseResult(False)

        expected_checksum = data.get("checksum")
        downloaded_checksum = file_sha256(task_cache_path)
        if not expected_checksum or expected_checksum == "UNKNOWN" or downloaded_checksum != expected_checksum:
            self._record_transfer_corruption(
                "download",
                "A downloaded remote result did not match its manifest checksum",
            )
            self._log(
                f"The downloaded file did not produce a correct checksum '{task_cache_path}'",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return DownloadPhaseResult(False, cleanup_remote=True)
        return DownloadPhaseResult(
            True,
            cache_path=task_cache_path,
            checksum=downloaded_checksum,
        )

    def _fetch_remote_result_data(self, context):
        task_cache_path = self.current_task.get_cache_path()
        cache_directory = os.path.dirname(os.path.abspath(task_cache_path))
        if not os.path.exists(cache_directory):
            os.makedirs(cache_directory)
        data = self.links.fetch_remote_task_data(
            self.installation_info,
            context.remote_task_id,
            os.path.join(cache_directory, "remote_data.json"),
        )
        if not isinstance(data, dict) or not data:
            self._log(
                f"Failed to retrieve remote task data for '{context.original_abspath}'."
                " NOTE: The cached files have not been removed from the remote host.",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return None, cache_directory

        self.worker_log = [data.get("log")]
        self.current_task.save_command_log(self.worker_log)
        task_state = data.get("task_state")
        self.logger.warn("Importing task_state into TaskDataStore: %s", task_state)
        if task_state:
            if not isinstance(task_state, dict):
                self._log(
                    f"Remote task state was malformed for '{context.original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return None, cache_directory
            TaskDataStore.import_task_state(self.current_task.get_task_id(), task_state)
        return data, cache_directory

    def _copy_shared_remote_result(self, context, task_cache_path, cache_directory):
        self.current_task.cache_path = task_cache_path
        self._log(f"abspath exists - task cache path: '{task_cache_path}'", level="debug")
        tcp_base = os.path.basename(task_cache_path)
        local_match = re.search(r"-\w{5}-\d{10}", cache_directory)
        if not local_match:
            self._log(
                f"Unable to detect random_string pattern in main instance cache directory named '{cache_directory}'",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return None
        remote_match = re.search(r"-\w{5}-\d{10}", tcp_base)
        if not remote_match:
            self._log(
                f"Unable to detect random_string pattern in remote library located directory named '{task_cache_path}'",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return None

        incorrect_random_string = remote_match.group()
        new_tcp_base, suffix = tcp_base.split(incorrect_random_string)
        output_path = os.path.join(
            cache_directory,
            new_tcp_base + local_match.group() + suffix,
        )
        self._log(f"...copying {task_cache_path} to {output_path}", level="debug")
        try:
            output = shutil.copy(task_cache_path, output_path)
        except (FileNotFoundError, PermissionError, shutil.SameFileError):
            self._log(
                f"Failed to copy file from '{task_cache_path}' to '{output_path}'",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return None
        if not os.path.exists(output) or os.path.getsize(output) <= 0:
            self._log(f"Copied file is missing or empty at '{output_path}'", level="error")
            self.__write_failure_to_worker_log()
            return None
        self._log(
            f"File successfully copied from remote library located cache to main instance cache at '{output}'",
            level="info",
        )
        self.current_task.cache_path = output
        return output

    def _set_download_cache_path(self, remote_result_path, cache_directory):
        file_extension = os.path.splitext(remote_result_path)[1].lstrip(".")
        self.current_task.set_cache_path(cache_directory, file_extension)
        task_cache_path = self.current_task.get_cache_path()
        self._log(f"task cache path: '{task_cache_path}'", level="debug")
        return task_cache_path

    def _download_remote_result(self, context, task_label, task_cache_path):
        download_deadline = time.monotonic() + 1800
        while not self.redundant_flag.is_set():
            if time.monotonic() > download_deadline:
                self._log(f"Download retry deadline exceeded for '{task_label}'", level="error")
                self.__write_failure_to_worker_log()
                return False, False
            lock_key = self.links.acquire_network_transfer_lock(
                context.address,
                transfer_limit=2,
                lock_type="receive",
            )
            if not lock_key:
                self.event.wait(1)
                continue
            self._log(
                f"Downloading file from remote installation '{task_label}'",
                level="debug",
            )
            success = self._fetch_remote_result_file(
                context,
                task_cache_path,
                lock_key,
            )
            if success:
                return True, False
            self._log(
                "Download interrupted; retaining resumable transfer state",
                level="warning",
            )
            if not self.lease_token:
                self.__write_failure_to_worker_log()
                return False, True
            if not self._heartbeat_remote_lease():
                self._log(
                    f"Remote task lease was lost during download for '{context.original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return False, False
            self.event.wait(2)
        return False, False

    def _fetch_remote_result_file(self, context, task_cache_path, lock_key):
        try:
            if not self.lease_token:
                return self.links.fetch_remote_task_completed_file(
                    self.installation_info,
                    context.remote_task_id,
                    task_cache_path,
                )

            def download_progress(active_lock=lock_key):
                lock_active = self.links.refresh_network_transfer_lock(active_lock)
                lease_active = self._heartbeat_remote_lease()
                return bool(lock_active and lease_active)

            return self.links.fetch_remote_task_completed_file_resumable(
                self.installation_info,
                context.remote_task_id,
                task_cache_path,
                progress_callback=download_progress,
            )
        finally:
            self.links.release_network_transfer_lock(lock_key)

    def _finalization_phase(
        self,
        context: RemoteTaskContext,
        download: DownloadPhaseResult,
    ) -> FinalizationPhaseResult:
        current_task = self.current_task
        if current_task is None:
            raise RuntimeError("remote task disappeared during finalization")
        if self.lease_token and not RemoteTaskLease.complete(
            current_task.task,
            self.lease_token,
            download.checksum,
        ):
            if self.safety_event_recorder is not None:
                self.safety_event_recorder(
                    "duplicate-lease",
                    "A conflicting remote completion attempted to close this task lease",
                    task_id=current_task.get_task_id(),
                )
            self._log(
                f"Conflicting remote completion received for '{context.original_abspath}'",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return FinalizationPhaseResult(False)
        return FinalizationPhaseResult(True)

    def _cleanup_phase(self, context) -> CleanupPhaseResult:
        response = self.links.remove_task_from_remote_installation(
            self.installation_info,
            context.remote_task_id,
        )
        remote_removed = bool(response.get("success")) if isinstance(response, dict) else bool(response)
        return CleanupPhaseResult(succeeded=remote_removed, remote_removed=remote_removed)
