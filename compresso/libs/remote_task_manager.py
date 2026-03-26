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

from compresso.libs import common
from compresso.libs.installation_link import Links
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler
from compresso.libs.task import TaskDataStore


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

    def get_info(self):
        return {
            "name": self.name,
            "installation_info": self.installation_info,
        }

    def run(self):
        # A manager should only run for a single task and connection to a single worker.
        # If either of these become unavailable, then the manager should exit
        self._log("Starting remote task manager {} - {}".format(self.thread_id, self.installation_info.get("address")))
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

        self._log("Stopping remote task manager {} - {}".format(self.thread_id, self.installation_info.get("address")))

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
        # Append long entry to say the worker was terminated
        self.worker_log.append("\n\nREMOTE TASK FAILED!")
        self.worker_log.append("\nAn error occurred during one of these stages:")
        self.worker_log.append("\n    - while sending task to remote installation")
        self.worker_log.append("\n    - during the remote task processing")
        self.worker_log.append("\n    - while attempting to retrieve the completed task from the remote installation")
        self.worker_log.append("\nCheck Compresso logs for more information.")
        self.worker_log.append(f"\nRelevant logs will be prefixed with 'ERROR:Compresso.{self.name}'")
        self.current_task.save_command_log(self.worker_log)

    def __send_task_to_remote_worker_and_monitor(self):  # noqa: C901
        """
        Sends the task file to the remote installation to process.
        Monitors progress and then fetches the results.

        Network disconnections are handled with exponential backoff.
        The manager will retry for up to 30 minutes before giving up
        and returning the task to the local queue.

        :return:
        """
        # Set the absolute path to the original file
        original_abspath = self.current_task.get_source_abspath()

        # Ensure file exists
        if not os.path.exists(original_abspath):
            self._log(f"File no longer exists '{original_abspath}'. Was it removed?", level="warning")
            self.__write_failure_to_worker_log()
            return False

        # Set the remote worker address
        address = self.installation_info.get("address")

        lock_key = None

        # Fetch the library name and path this task is for
        library_id = self.current_task.get_task_library_id()
        try:
            library = Library(library_id)
        except Exception:
            self._log(f"Unable to fetch library config for ID {library_id}", level="exception")
            self.__write_failure_to_worker_log()
            return False
        library_name = library.get_name()
        library_path = library.get_path()

        # Check if we can create the remote task with just a relative path
        #   only create checksum and send file if the remote library path cannot accept relative paths, or
        #   it is configured for only receiving remote files
        send_file = False
        library_config = self.links.get_the_remote_library_config_by_name(self.installation_info, library_name)

        # Check if remote library is configured only for receiving remote files
        if library_config.get("enable_remote_only"):
            send_file = True

        # First attempt to create a task with an abspath on the remote installation
        remote_task_id = None
        if not send_file:
            remote_library_id = library_config.get("id")

            # Remove library path from file abspath to create a relative path
            original_relpath = os.path.relpath(original_abspath, library_path)
            # Join remote library path to the relative path to form a remote library abspath to the file
            remote_original_abspath = os.path.join(library_config.get("path"), original_relpath)
            # Post the task creation. This will error if the file does not exist
            info = self.links.new_pending_task_create_on_remote_installation(
                self.installation_info, remote_original_abspath, remote_library_id
            )
            if not info:
                self._log(
                    f"Unable to create remote pending task for path '{remote_original_abspath}'. Fallback to sending file.",
                    level="debug",
                )
                send_file = True
            elif "path does not exist" in info.get("error", "").lower():
                self._log(
                    f"Unable to find file in remote library's path '{remote_original_abspath}'. Fallback to sending file.",
                    level="debug",
                )
                send_file = True
            elif "task already exists" in info.get("error", "").lower():
                self._log(
                    f"A remote task already exists with the path '{remote_original_abspath}'. Fallback to sending file.",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return False

            # Set the remote task ID
            remote_task_id = info.get("id")

        if send_file:
            initial_checksum = None
            if self.installation_info.get("enable_checksum_validation", False):
                # Get source file checksum
                initial_checksum = common.get_file_checksum(original_abspath)
            initial_file_size = os.path.getsize(original_abspath)

            # Loop until we are able to upload the file to the remote installation
            info = {}
            upload_deadline = time.monotonic() + 1800  # 30 min max
            while not self.redundant_flag.is_set():
                if time.monotonic() > upload_deadline:
                    self._log(f"Upload retry deadline exceeded for '{original_abspath}'", level="error")
                    self.__write_failure_to_worker_log()
                    return False
                # For files smaller than 100MB, just transfer them in parallel
                # Smaller files add a lot of time overhead with the waiting in line and it slows the whole process down
                # Larger files benefit from being transferred one at a time.
                if initial_file_size > 100000000:
                    # Check for network transfer lock
                    lock_key = self.links.acquire_network_transfer_lock(address, transfer_limit=1, lock_type="send")
                    if not lock_key:
                        self.event.wait(1)
                        continue

                # Send a file to a remote installation.
                self._log(f"Uploading file to remote installation '{original_abspath}'", level="debug")
                info = self.links.send_file_to_remote_installation(self.installation_info, original_abspath)
                self.links.release_network_transfer_lock(lock_key)
                if not info:
                    self._log(f"Failed to upload the file '{original_abspath}'", level="error")
                    self.__write_failure_to_worker_log()
                    return False
                break

            # Set the remote task ID
            remote_task_id = info.get("id")

            # Compare uploaded file md5checksum
            if initial_checksum and info.get("checksum") != initial_checksum:
                self._log(f"The uploaded file did not return a correct checksum '{original_abspath}'", level="error")
                # Send request to terminate the remote worker then return
                self.links.remove_task_from_remote_installation(self.installation_info, remote_task_id)
                self.__write_failure_to_worker_log()
                return False

        # Ensure at this point we have set the remote_task_id
        if remote_task_id is None:
            self._log("Failed to create remote task. Var remote_task_id is still None", level="error")
            self.__write_failure_to_worker_log()
            return False

        # Set the library of the remote task using the library's name
        set_lib_deadline = time.monotonic() + 1800  # 30 min max
        while not self.redundant_flag.is_set():
            if time.monotonic() > set_lib_deadline:
                self._log(f"Set-remote-library retry deadline exceeded for '{original_abspath}'", level="error")
                self.__write_failure_to_worker_log()
                return False
            result = self.links.set_the_remote_task_library(self.installation_info, remote_task_id, library_name)
            if result is None:
                # Unable to reach remote installation
                self.event.wait(2)
                continue
            if not result.get("success"):
                self._log(
                    f"Failed to match a remote library named '{library_name}'."
                    " Remote installation will use the default library",
                    level="warning",
                )
                # Just log the warning for this. If no matching library name is found it will remain set as the default library
                break
            if result.get("success"):
                break

        # Start the remote task
        start_task_deadline = time.monotonic() + 1800  # 30 min max
        while not self.redundant_flag.is_set():
            if time.monotonic() > start_task_deadline:
                self._log(f"Start-task retry deadline exceeded for '{original_abspath}'", level="error")
                self.__write_failure_to_worker_log()
                return False
            result = self.links.start_the_remote_task_by_id(self.installation_info, remote_task_id)
            if not result:
                # Unable to reach remote installation
                self.event.wait(2)
                continue
            if not result.get("success"):
                self._log(f"Failed to set initial remote pending task to status '{original_abspath}'", level="error")
                # Send request to terminate the remote worker then return
                self.links.remove_task_from_remote_installation(self.installation_info, remote_task_id)
                self.__write_failure_to_worker_log()
                return False
            if result.get("success"):
                break

        # Loop while redundant_flag not set (while true because of below)
        worker_id = None
        task_status = ""
        last_status_fetch = 0
        polling_delay = 5
        consecutive_poll_failures = 0
        max_retry_seconds = 1800  # 30 minutes total retry window
        first_failure_time = None
        while task_status != "complete":
            self.event.wait(1)
            if self.redundant_flag.is_set():
                # Send request to terminate the remote worker then exit
                if worker_id:
                    self.links.terminate_remote_worker(self.installation_info, worker_id)
                break

            # Only fetch the status every polling_delay seconds
            time_now = time.time()
            if last_status_fetch > (time_now - polling_delay):
                continue

            # Check if we have exceeded the maximum retry window
            if first_failure_time and (time_now - first_failure_time) > max_retry_seconds:
                self._log(
                    f"Remote link unreachable for over {max_retry_seconds} seconds, giving up on task '{original_abspath}'",
                    level="error",
                )
                self.__write_failure_to_worker_log()
                return False

            # Fetch task status
            all_task_states = self.links.get_remote_pending_task_state(self.installation_info, remote_task_id)
            task_status = ""
            polling_delay = 5
            if all_task_states:
                # Successful contact -- reset backoff state
                consecutive_poll_failures = 0
                first_failure_time = None
                for ts in all_task_states.get("results", []):
                    if str(ts.get("id")) == str(remote_task_id):
                        # Task is complete. Exit loop but do not set redundant flag on link manager
                        task_status = ts.get("status")
                        break
                if not all_task_states.get("results", []):
                    # Remote task list is empty
                    task_status = "removed"
                elif all_task_states.get("results") and task_status == "":
                    # Remote task list did not contain this task
                    task_status = "removed"

            # If the task status is 'complete', break the loop here and move onto the result retrieval
            # If all_task_states returned no results (we are unable to connect to the remote installation)
            # If all_task_states did return results but our task_status was found, the remote installation has removed our task
            # If the task status is not 'in_progress', loop here and wait for task to be picked up by a worker
            if task_status == "complete":
                break
            elif not all_task_states:
                # Connection failed -- apply exponential backoff
                consecutive_poll_failures += 1
                if first_failure_time is None:
                    first_failure_time = time_now
                polling_delay = min(60, 5 * (2 ** min(consecutive_poll_failures, 4)))
                self._log(
                    f"Lost contact with remote installation (attempt {consecutive_poll_failures}),"
                    f" next poll in {polling_delay}s for '{original_abspath}'",
                    level="warning",
                )
                last_status_fetch = time_now
                continue
            elif task_status == "removed":
                self._log(f"Task has been removed by remote installation '{original_abspath}'", level="error")
                self.__write_failure_to_worker_log()
                return False
            elif task_status != "in_progress":
                # Mark this as the last time run
                last_status_fetch = time_now
                polling_delay = 10
                continue

            # Check if we know the task's worker ID already
            if not worker_id:
                # The task has been picked up by a worker, find out which one...
                workers_status = self.links.get_all_worker_status(self.installation_info)
                if not workers_status:
                    # The request failed for some reason... Perhaps we lost contact with the remote installation
                    # Mark this as the last time run
                    last_status_fetch = time_now
                    continue
                for worker in workers_status:
                    if str(worker.get("current_task")) == str(remote_task_id):
                        worker_id = worker.get("id")

            # Fetch worker progress
            worker_status = self.links.get_single_worker_status(self.installation_info, worker_id)
            if not worker_status:
                # Mark this as the last time run
                last_status_fetch = time_now
                continue

            # Update status
            self.paused = worker_status.get("paused")
            self.worker_log = worker_status.get("worker_log_tail")
            self.worker_runners_info = worker_status.get("runners_info")
            self.worker_subprocess_percent = worker_status.get("subprocess", {}).get("percent")
            self.worker_subprocess_elapsed = worker_status.get("subprocess", {}).get("elapsed")

            # Mark this as the last time run
            last_status_fetch = time_now

        # If the previous loop was broken because this tread needs to terminate, return False here (did not complete)
        if self.redundant_flag.is_set():
            self.worker_log += ["\n\nREMOTE LINK MANAGER TERMINATED!"]
            self.current_task.save_command_log(self.worker_log)
            return False

        self._log(f"Remote task completed '{original_abspath}'", level="info")

        # Create local cache path to download results
        task_cache_path = self.current_task.get_cache_path()
        # Ensure the cache directory exists
        cache_directory = os.path.dirname(os.path.abspath(task_cache_path))
        if not os.path.exists(cache_directory):
            os.makedirs(cache_directory)

        # Fetch remote task result data
        data = self.links.fetch_remote_task_data(
            self.installation_info, remote_task_id, os.path.join(cache_directory, "remote_data.json")
        )

        if not data:
            self._log(
                f"Failed to retrieve remote task data for '{original_abspath}'."
                " NOTE: The cached files have not been removed from the remote host.",
                level="error",
            )
            self.__write_failure_to_worker_log()
            return False
        self.worker_log = [data.get("log")]

        # Save the completed command log
        self.current_task.save_command_log(self.worker_log)

        # Update task state
        task_state = data.get("task_state")
        self.logger.warn("Importing task_state into TaskDataStore: %s", task_state)
        if task_state:
            TaskDataStore.import_task_state(self.current_task.get_task_id(), task_state)

        # Fetch remote task file
        if data.get("task_success"):
            task_label = data.get("task_label")
            self._log(
                f"Remote task #{remote_task_id} was successful, proceeding to download the completed file '{task_label}'",
                level="debug",
            )
            self._log("Remote task abspath {} to be transferred".format(data.get("abspath")), level="debug")
            if os.path.exists(data.get("abspath")):
                # /library/tvshows/show_name/season/compresso_remote_pending_library/file.mkv
                task_cache_path = data.get("abspath")
                self.current_task.cache_path = task_cache_path
                self._log(f"abspath exists - task cache path: '{task_cache_path}'", level="debug")
                # need to get the file into the local instance /tmp/compresso/compresso_file_conversion... location
                # the task_cache_path file is currently sitting in the library's compresso_remote_pending_library directory
                # with a different random string - reformulate the basename of the file with the correct random string
                # and copy it to the local instance /tmp/compresso/compresso_file_conversion location
                tcp_base = os.path.basename(task_cache_path)
                match1 = re.search(r"-\w{5}-\d{10}", cache_directory)
                if match1:
                    correct_random_string = match1.group()
                else:
                    self._log(
                        f"Unable to detect random_string pattern in main instance cache directory named '{cache_directory}'",
                        level="error",
                    )
                    self.links.remove_task_from_remote_installation(self.installation_info, remote_task_id)
                    self.__write_failure_to_worker_log()
                    return False
                match2 = re.search(r"-\w{5}-\d{10}", tcp_base)
                if match2:
                    incorrect_random_string = match2.group()
                else:
                    self._log(
                        f"Unable to detect random_string pattern in remote library"
                        f" located directory named '{task_cache_path}'",
                        level="error",
                    )
                    self.links.remove_task_from_remote_installation(self.installation_info, remote_task_id)
                    self.__write_failure_to_worker_log()
                    return False
                new_tcp_base = tcp_base.split(incorrect_random_string)[0]
                sfx = tcp_base.split(incorrect_random_string)[1]
                correct_cache_file_path = os.path.join(cache_directory, new_tcp_base + correct_random_string + sfx)
                self._log(f"...copying {task_cache_path} to {correct_cache_file_path}", level="debug")
                try:
                    output = shutil.copy(task_cache_path, correct_cache_file_path)
                    if os.path.exists(output) and os.path.getsize(output) > 0:
                        self._log(
                            f"File successfully copied from remote library located cache to main instance cache at '{output}'",
                            level="info",
                        )
                        # Update task pointers to the new local cache path
                        task_cache_path = output
                        self.current_task.cache_path = output
                    else:
                        self._log(f"Copied file is missing or empty at '{correct_cache_file_path}'", level="error")
                        self.__write_failure_to_worker_log()
                        return False
                except (FileNotFoundError, PermissionError, shutil.SameFileError):
                    self._log(f"Failed to copy file from '{task_cache_path}' to '{correct_cache_file_path}'", level="error")
                    self.__write_failure_to_worker_log()
                    return False
            else:
                # Set the new file out as the extension may have changed
                split_file_name = os.path.splitext(data.get("abspath"))
                file_extension = split_file_name[1].lstrip(".")
                self.current_task.set_cache_path(cache_directory, file_extension)
                # Read the updated cache path
                task_cache_path = self.current_task.get_cache_path()
                self._log(f"task cache path: '{task_cache_path}'", level="debug")

                # Loop until we are able to download the file from the remote installation
                download_deadline = time.monotonic() + 1800  # 30 min max
                while not self.redundant_flag.is_set():
                    if time.monotonic() > download_deadline:
                        self._log(f"Download retry deadline exceeded for '{task_label}'", level="error")
                        self.__write_failure_to_worker_log()
                        return False
                    # Check for network transfer lock
                    lock_key = self.links.acquire_network_transfer_lock(address, transfer_limit=2, lock_type="receive")
                    if not lock_key:
                        self.event.wait(1)
                        continue
                    # Download the file
                    self._log(f"Downloading file from remote installation '{task_label}'", level="debug")
                    success = self.links.fetch_remote_task_completed_file(
                        self.installation_info,
                        remote_task_id,
                        task_cache_path,
                    )
                    self.links.release_network_transfer_lock(lock_key)
                    if not success:
                        self._log("Failed to download file '{}'".format(os.path.basename(data.get("abspath"))), level="error")
                        # Send request to terminate the remote worker then return
                        self.links.remove_task_from_remote_installation(self.installation_info, remote_task_id)
                        self.__write_failure_to_worker_log()
                        return False
                    break

            # If the previous loop was broken because this tread needs to terminate, return False here (did not complete)
            if self.redundant_flag.is_set():
                self.worker_log += ["\n\nREMOTE LINK MANAGER TERMINATED!"]
                self.current_task.save_command_log(self.worker_log)
                return False

            # Match checksum from task result data with downloaded file
            if self.installation_info.get("enable_checksum_validation", False):
                downloaded_checksum = common.get_file_checksum(task_cache_path)
                if downloaded_checksum != data.get("checksum"):
                    self._log(f"The downloaded file did not produce a correct checksum '{task_cache_path}'", level="error")
                    # Send request to terminate the remote worker then return
                    self.links.remove_task_from_remote_installation(self.installation_info, remote_task_id)
                    self.__write_failure_to_worker_log()
                    return False

            # Send request to terminate the remote worker then return
            self.links.remove_task_from_remote_installation(self.installation_info, remote_task_id)

            return True

        self.__write_failure_to_worker_log()
        return False
