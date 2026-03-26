#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.workers.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     11 Aug 2021, (12:06 PM)

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
import shlex
import shutil
import subprocess
import threading
import time

import psutil

from compresso.libs import common
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler
from compresso.libs.worker_subprocess_monitor import WorkerSubprocessMonitor


class Worker(threading.Thread):
    idle = True
    paused = False

    current_task = None
    worker_log = None
    start_time = None
    finish_time = None

    worker_runners_info = {}

    def __init__(self, thread_id, name, worker_group_id, pending_queue, complete_queue, event):
        super(Worker, self).__init__(name=name)
        self.thread_id = thread_id
        self.name = name
        self.worker_group_id = worker_group_id
        self.event = event

        self.current_task = None
        self.current_command_ref = None
        self.pending_queue = pending_queue
        self.complete_queue = complete_queue
        self.worker_subprocess_monitor = None

        # Create 'redundancy' flag. When this is set, the worker should die
        self.redundant_flag = threading.Event()
        self.redundant_flag.clear()

        # Create 'paused' flag. When this is set, the worker should be paused
        self.paused_flag = threading.Event()
        self.paused_flag.clear()

        # Create logger for this worker
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)

    def run(self):
        self.logger.info("Starting worker")

        # Create proc monitor
        self.worker_subprocess_monitor = WorkerSubprocessMonitor(self)
        self.worker_subprocess_monitor.start()

        while not self.redundant_flag.is_set():
            self.event.wait(1)  # Add delay for preventing loop maxing compute resources

            # If the Foreman has paused this worker, then don't do anything
            if self.paused_flag.is_set():
                self.paused = True
                # If the worker is paused, wait for 5 seconds before continuing the loop
                self.event.wait(5)
                continue
            self.paused = False

            # Set the worker as Idle - This will announce to the Foreman that it's ready for a task
            self.idle = True

            # Wait for task
            while not self.redundant_flag.is_set() and self.current_task:
                self.event.wait(.5)  # Add delay for preventing loop maxing compute resources

                try:
                    # Process the set task
                    self.__process_task_queue_item()
                except queue.Empty:
                    continue
                except Exception as e:
                    self.logger.error("WORKER_TASK_PROCESSING_FAILED worker=%s", self.name)
                    self.logger.exception("Exception in processing job with %s: %s", self.name, e)

        self.logger.info("Stopping worker")
        self.worker_subprocess_monitor.stop()
        self.worker_subprocess_monitor.join()
        self.worker_subprocess_monitor = None

    def set_task(self, new_task):
        """Sets the given task to the worker class"""
        # Ensure only one task can be set for a worker
        if self.current_task:
            return
        # Set the task
        self.current_task = new_task
        self.worker_log = []
        self.idle = False

    def get_status(self):
        """
        Fetch the status of this worker.

        :return:
        """
        subprocess_stats = None
        if self.worker_subprocess_monitor:
            subprocess_stats = self.worker_subprocess_monitor.get_subprocess_stats()
        current_command = ""
        try:
            if self.current_command_ref:
                shared_command = self.current_command_ref[-1]
                if shared_command:
                    current_command = shared_command
        except (AttributeError, TypeError, IndexError) as e:
            self.logger.exception("Exception in fetching current command of worker %s: %s", self.name, e)
        status = {
            'id':              str(self.thread_id),
            'name':            self.name,
            'idle':            self.idle,
            'paused':          self.paused_flag.is_set(),
            'start_time':      None if not self.start_time else str(self.start_time),
            'current_task':    None,
            'current_file':    "",
            'current_command': current_command,
            'worker_log_tail': [],
            'runners_info':    {},
            'subprocess':      subprocess_stats,
        }
        if self.current_task:
            # Fetch the current file
            try:
                status['current_task'] = self.current_task.get_task_id()
            except (AttributeError, KeyError, TypeError) as e:
                self.logger.exception("Exception in fetching the current task ID for worker %s: %s", self.name, e)
            except Exception as e:
                self.logger.exception("Unexpected error fetching task ID for worker %s: %s", self.name, e)

            # Fetch the current file
            try:
                status['current_file'] = self.current_task.get_source_basename()
            except (AttributeError, KeyError, TypeError) as e:
                self.logger.exception("Exception in fetching the current file of worker %s: %s", self.name, e)
            except Exception as e:
                self.logger.exception("Unexpected error fetching current file for worker %s: %s", self.name, e)

            # Append the worker log tail
            try:
                if self.worker_log and len(self.worker_log) > 40:
                    status['worker_log_tail'] = self.worker_log[-39:]
                else:
                    status['worker_log_tail'] = self.worker_log
            except (AttributeError, TypeError, IndexError) as e:
                self.logger.exception("Exception in fetching log tail of worker: %s", e)

            # Append the runners info
            try:
                status['runners_info'] = self.worker_runners_info
            except (AttributeError, KeyError, TypeError) as e:
                self.logger.exception("Exception in runners info of worker %s: %s", self.name, e)
        return status

    def __unset_current_task(self):
        self.current_task = None
        self.worker_runners_info = {}
        self.worker_log = []

    def __process_task_queue_item(self):
        """
        Processes the set task.

        :return:
        """
        # Mark worker as not idle now that it is processing a task
        self.idle = False

        # Log the start of the job
        self.logger.info("Picked up job - %s", self.current_task.get_source_abspath())

        # Start current task stats
        self.__set_start_task_stats()

        # Mark as being "in progress"
        self.current_task.set_status('in_progress')

        # Process the file. Will return true if success, otherwise false
        success = self.__exec_worker_runners_on_set_task()
        # Mark the task as either success or not
        self.current_task.set_success(success)

        # Store encoding speed stats on the task for postprocessor
        if self.worker_subprocess_monitor is not None:
            speed_stats = self.worker_subprocess_monitor.get_encoding_speed_stats()
            elapsed = self.worker_subprocess_monitor.get_subprocess_elapsed()
            self.current_task.statistics['encoding_speed'] = {
                'avg_encoding_fps': speed_stats.get('avg_encoding_fps', 0),
                'encoding_speed_ratio': speed_stats.get('encoding_speed_ratio', 0),
                'encoding_duration_seconds': elapsed,
            }
            self.worker_subprocess_monitor.reset_encoding_speed_stats()
        else:
            self.current_task.statistics['encoding_speed'] = {
                'avg_encoding_fps': 0,
                'encoding_speed_ratio': 0,
                'encoding_duration_seconds': 0,
            }

        # Mark task completion statistics
        self.__set_finish_task_stats()

        # Log completion of job
        self.logger.info("Finished job - %s", self.current_task.get_source_abspath())

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
        self.current_task.task.processed_by_worker = str(self.name)
        self.current_task.task.start_time = self.start_time
        self.current_task.task.finish_time = self.finish_time

    def __set_finish_task_stats(self):
        """Sets the final stats for the end of a task"""
        # Set the finish time to now
        self.finish_time = time.time()

        # Set the finish time in the statistics data
        self.current_task.task.finish_time = self.finish_time

    def __exec_worker_runners_on_set_task(self):
        """
        Executes the configured plugin runners against the set task.

        :return:
        """
        # Init plugins
        library_id = self.current_task.get_task_library_id()
        plugin_handler = PluginsHandler()
        plugin_modules = plugin_handler.get_enabled_plugin_modules_by_type('worker.process', library_id=library_id)

        # Create dictionary of runners info for the frontend
        self.worker_runners_info = {}
        for plugin_module in plugin_modules:
            self.worker_runners_info[plugin_module.get('plugin_id')] = {
                'plugin_id':   plugin_module.get('plugin_id'),
                'status':      'pending',
                "name":        plugin_module.get('name'),
                "author":      plugin_module.get('author'),
                "version":     plugin_module.get('version'),
                "icon":        plugin_module.get('icon'),
                "description": plugin_module.get('description'),
            }

        # Set the absolute path to the original file
        original_abspath = self.current_task.get_source_abspath()

        # Process item in loop.
        # First process the item for each plugin that configures it, then run the default Compresso configuration
        task_cache_path = self.current_task.get_cache_path()
        cache_directory = os.path.dirname(os.path.abspath(task_cache_path))
        # Set the current input file to the original file path
        file_in = original_abspath
        # Mark the overall success of all runners. This will be set to False if any of the runners fails.
        overall_success = True
        # Set the current file out to nothing.
        # This will be configured by each runner.
        # If no runners are configured, then nothing needs to be done.
        current_file_out = original_abspath
        # The number of runners that have been run
        runner_count = 0
        # Flag if a task has run a command
        no_exec_command_run = True

        # Execute event plugin runners
        plugin_handler.run_event_plugins_for_plugin_type('events.worker_process_started', {
            "library_id":          library_id,
            "task_id":             self.current_task.get_task_id(),
            "task_type":           self.current_task.get_task_type(),
            "original_file_path":  original_abspath,
            "cache_directory":     cache_directory,
            "worker_runners_info": self.worker_runners_info,
        })

        # Generate default data object for the runner functions
        task_id = self.current_task.get_task_id()
        data = {
            "worker_log":              self.worker_log,
            "library_id":              library_id,
            "exec_command":            [],
            "current_command":         [],
            "command_progress_parser": None,
            "file_in":                 file_in,
            "file_out":                None,
            "original_file_path":      original_abspath,
            "repeat":                  False,
        }

        for plugin_module in plugin_modules:
            # Increment the runners count (first runner will be set as #1)
            runner_count += 1
            runner_id = plugin_module.get('plugin_id')

            if not overall_success:
                # If one of the Plugins fails, don't continue.
                # The Plugins could be co-dependant and the final file will not go anywhere if 'overall_success' is False
                break

            # Mark the status of the worker for the frontend
            self.worker_runners_info[runner_id]['status'] = 'in_progress'
            self.worker_runners_info[runner_id]['success'] = False

            # Loop over runner. This way we can repeat the function with the same data if requested by the repeat flag
            runner_pass_count = 0
            while not self.redundant_flag.is_set():
                runner_pass_count += 1

                # Fetch file out details
                # This creates a temp file labeled "WORKING" that will be moved to the cache_path on completion
                split_file_out = os.path.splitext(task_cache_path)
                split_file_in = os.path.splitext(file_in)
                file_out = "{}-{}-{}-{}{}".format(split_file_out[0], "WORKING", runner_count, runner_pass_count,
                                                  split_file_in[1])

                # Reset data object for this runner functions
                data['library_id'] = library_id
                data['exec_command'] = []
                data['current_command'] = []
                data['command_progress_parser'] = self.worker_subprocess_monitor.default_progress_parser
                data['file_in'] = file_in
                data['file_out'] = file_out
                data['original_file_path'] = original_abspath
                data['repeat'] = False
                data['task_id'] = task_id
                self.current_command_ref = data['current_command']

                self.event.wait(.2)  # Add delay for preventing loop maxing compute resources
                self.worker_log.append(f"\n\nRUNNER: \n{plugin_module.get('name')} [Pass #{runner_pass_count}]\n\n")
                self.worker_log.append("\nExecuting plugin runner... Please wait\n")

                # Run plugin (in its own thread) to update data
                result = {"success": None}

                def _run_plugin():
                    result["success"] = plugin_handler.exec_plugin_runner(
                        data, runner_id, 'worker.process'
                    )

                runner_thread = threading.Thread(target=_run_plugin, daemon=True)
                runner_thread.start()

                # monitor the thread, bail if redundancy requested
                while runner_thread.is_alive():
                    if self.redundant_flag.is_set():
                        self.logger.warning("Worker stop flag set, aborting plugin runner '%s'", runner_id)
                        break
                    self.event.wait(0.2)

                # if we were told to shut down, mark failure and exit loop
                if self.redundant_flag.is_set():
                    self.worker_runners_info[runner_id]['status'] = 'complete'
                    self.worker_runners_info[runner_id]['success'] = False
                    overall_success = False
                    self.worker_log.append("\n\nWORKER TERMINATED!")
                    break

                # now check the plugin result
                if not result["success"]:
                    # Skip this plugin module's loop
                    self.worker_runners_info[runner_id]['status'] = 'complete'
                    self.worker_runners_info[runner_id]['success'] = False
                    # Set overall success status to failed
                    overall_success = False
                    # Append long entry to say the worker was terminated
                    self.worker_log.append("\n\nPLUGIN FAILED!")
                    self.worker_log.append("\nFailed to execute Plugin '{}'".format(plugin_module.get('name')))
                    self.worker_log.append("\nCheck Compresso logs for more information")
                    self.current_command_ref = None
                    data['current_command'] = []
                    break

                # Log the in and out files returned by the plugin runner for debugging
                self.logger.debug("Worker process '%s' (in) %s", runner_id, data.get("file_in"))
                self.logger.debug("Worker process '%s' (out) %s", runner_id, data.get("file_out"))

                # Only run the conversion process if "exec_command" is not empty
                if data.get("exec_command"):
                    self.worker_log.append("\nPlugin runner requested for a command to be executed by Compresso")

                    # Exec command as subprocess
                    self.current_command_ref = data['current_command']
                    success = self.__exec_command_subprocess(data)
                    no_exec_command_run = False

                    if self.redundant_flag.is_set():
                        # This worker has been marked as redundant. It is being terminated.
                        self.logger.warning("Worker has been terminated before a command was completed")
                        # Mark runner as failed
                        self.worker_runners_info[runner_id]['success'] = False
                        # Set overall success status to failed
                        overall_success = False
                        # Append long entry to say the worker was terminated
                        self.worker_log.append("\n\nWORKER TERMINATED!")
                        self.current_command_ref = None
                        data['current_command'] = []
                        # Don't continue
                        break

                    # Check if command exited successfully.
                    if success:
                        # If file conversion was successful
                        self.logger.info("Successfully ran worker process '%s' on file '%s'",
                                         runner_id,
                                         data.get("file_in"))
                        # Check if 'file_out' was nulled by the plugin. If it is, then we will assume that the plugin modified the file_in in-place
                        if not data.get('file_out'):
                            # The 'file_out' is None. Ensure the new 'file_in' is set to whatever the plugin returned for 'file_in' for the next loop
                            file_in = data.get("file_in")
                        # Ensure the 'file_out' that was specified by the plugin to be created was actually created.
                        elif os.path.exists(data.get('file_out')):
                            # The outfile exists...
                            # In order to clean up as we go and avoid unnecessary RAM/disk use in the cache directory,
                            #   we want to remove the 'file_in' file.
                            # We want to ensure that we do not accidentally remove any original files here.
                            # We also want to ensure that the 'file_out' is not removed if the plugin set it to the same path as the 'file_in'.
                            # To avoid this, run x3 tests.
                            # First, check current 'file_in' is not the original file.
                            if os.path.abspath(data.get("file_in")) != os.path.abspath(original_abspath):
                                # Second, check that the 'file_in' is actually in cache directory. If it is not, we did not create it.
                                if "compresso_file_conversion" in os.path.abspath(data.get("file_in")):
                                    # Finally, check that the file_out is not the same file as the file_in
                                    if os.path.abspath(data.get("file_out")) != os.path.abspath(data.get("file_in")):
                                        # Remove the old file_in file
                                        os.remove(os.path.abspath(data.get("file_in")))

                            # Set the new 'file_in' as the previous runner's 'file_out' for the next loop
                            file_in = data.get("file_out")
                    else:
                        # If file conversion was not successful
                        self.logger.error("WORKER_RUNNER_FAILED runner=%s file=%s",
                                          runner_id,
                                          original_abspath)
                        self.logger.error("Error while running worker process '%s' on file '%s'",
                                          runner_id,
                                          original_abspath)
                        self.worker_runners_info[runner_id]['success'] = False
                        overall_success = False
                else:
                    # Ensure the new 'file_in' is set to the previous runner's 'file_in' for the next loop
                    file_in = data.get("file_in")
                    # Log that this plugin did not request to execute anything
                    self.worker_log.append("\nRunner did not request for Compresso to execute a command")
                    self.logger.debug("Worker process '%s' did not request to execute a command.", runner_id)

                if data.get('file_out') and os.path.exists(data.get('file_out')):
                    # Set the current file out to the most recently completed cache file
                    # If the file out does not exist, it is likely never used by the plugin.
                    current_file_out = data.get('file_out')
                else:
                    # Ensure the current_file_out is set the currently set 'file_in'
                    current_file_out = data.get('file_in')

                # Exec command was handled, clear shared command reference for the UI.
                self.current_command_ref = None
                data['current_command'] = []

                if data.get("repeat"):
                    # The returned data contained the 'repeat' flag.
                    # Run another pass against this same plugin
                    continue
                break

            self.worker_runners_info[runner_id]['success'] = True
            self.worker_runners_info[runner_id]['status'] = 'complete'

        # Log if no command was run by any Plugins
        if no_exec_command_run:
            # If no jobs were carried out on this task
            self.logger.warning("No Plugin requested for Compresso to run commands for this file '%s'", original_abspath)
            self.worker_log.append(
                "\n\nNo Plugin requested for Compresso to run commands for this file '{}'".format(original_abspath))

        # Save the completed command log
        self.current_task.save_command_log(self.worker_log)

        # If all plugins that were executed completed successfully, then this was overall a successful task.
        # At this point we need to move the final out file to the original task cache path so the postprocessor can collect it.
        if overall_success:
            # If jobs carried out on this task were all successful, we will get here
            self.logger.info("Successfully completed Worker processing on file '%s'", original_abspath)

            # Attempt to move the final output file to the final cache file path for the postprocessor
            try:
                # Set the new file out as the extension may have changed
                split_file_name = os.path.splitext(current_file_out)
                file_extension = split_file_name[1].lstrip('.')
                self.current_task.set_cache_path(cache_directory, file_extension)
                # Read the updated cache path
                task_cache_path = self.current_task.get_cache_path()

                # Move file to original cache path
                self.logger.info("Moving final cache file from '%s' to '%s'", current_file_out, task_cache_path)
                current_file_out = os.path.abspath(current_file_out)

                # There is a really odd intermittent bug with the shutil module that is causing it to
                #   sometimes report that the file does not exist.
                # This section adds a small pause and logs the error if that is the case.
                # I have not yet figured out a solution as this is difficult to reproduce.
                if not os.path.exists(current_file_out):
                    self.logger.error("WORKER_FINAL_OUTPUT_MISSING file=%s", file_in)
                    self.logger.error("Error - current_file_out path does not exist! '%s'", file_in)
                    self.event.wait(1)

                # Ensure the cache directory exists
                if not os.path.exists(cache_directory):
                    os.makedirs(cache_directory)

                # Check that the current file out is not the original source file
                if os.path.abspath(current_file_out) == os.path.abspath(original_abspath):
                    # The current file out is not a cache file, the file must have never been modified.
                    # This can happen if all Plugins failed to run, or a Plugin specifically reset the out
                    #   file to the original source in order to preserve it.
                    # In this circumstance, we want to create a cache copy and let the process continue.
                    self.logger.debug("Final cache file is the same path as the original source. Creating cache copy.")
                    shutil.copyfile(current_file_out, task_cache_path)
                else:
                    # Use shutil module to move the file to the final task cache location
                    shutil.move(current_file_out, task_cache_path)
            except (OSError, PermissionError, shutil.Error) as e:
                self.logger.error("WORKER_FINAL_MOVE_FAILED source=%s dest=%s", current_file_out, task_cache_path)
                self.logger.exception("Exception in final move operation of file %s to %s: %s",
                                      current_file_out,
                                      task_cache_path,
                                      e)
                overall_success = False

        # Execute event plugin runners (only when added to queue)
        plugin_handler.run_event_plugins_for_plugin_type('events.worker_process_complete', {
            "library_id":          library_id,
            "task_id":             self.current_task.get_task_id(),
            "task_type":           self.current_task.get_task_type(),
            "original_file_path":  original_abspath,
            "final_cache_path":    task_cache_path,
            "overall_success":     overall_success,
            "worker_runners_info": self.worker_runners_info,
            "worker_log":          self.worker_log,
        })

        # If the overall result of the jobs carried out on this task were not successful, log the failure and return False
        if not overall_success:
            self.logger.warning("WORKER_TASK_FAILED file=%s", original_abspath)
            self.logger.warning("Failed to process task for file '%s'", original_abspath)
        return overall_success

    def __exec_command_subprocess(self, data):
        """
        Executes a command as a shell subprocess.
        Uses the given parser to record progress data from the shell STDOUT.

        :param data:
        :return:
        """
        # Fetch command to execute.
        exec_command = data.get("exec_command", [])

        # Fetch the command progress parser function
        command_progress_parser = data.get("command_progress_parser",
                                           self.worker_subprocess_monitor.default_progress_parser)

        # Log the command for debugging
        command_string = exec_command
        if isinstance(exec_command, list):
            command_string = shlex.join(exec_command)
        self.logger.debug("Executing: %s", command_string)
        current_command_ref = data.get("current_command")
        if isinstance(current_command_ref, list):
            current_command_ref.clear()
            current_command_ref.append(command_string)

        # Append start of command to worker subprocess stdout
        self.worker_log += [
            '\n\n',
            'COMMAND:\n',
            command_string,
            '\n\n',
            'LOG:\n',
        ]

        # Create output path if file_out is present and the path does not exists
        if data.get("file_out"):
            common.ensure_dir(data.get("file_out"))

        # Convert file
        try:
            # Execute command
            if isinstance(exec_command, list):
                sub_proc = subprocess.Popen(exec_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            universal_newlines=True, errors='replace')
            elif isinstance(exec_command, str):
                sub_proc = subprocess.Popen(exec_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            universal_newlines=True, errors='replace', shell=True)
            else:
                raise TypeError(
                    "Plugin's returned 'exec_command' object must be either a list or a string. Received type {}.".format(
                        type(exec_command)))

            # Fetch process using psutil for control (sending SIGSTOP on windows will not work)
            proc = psutil.Process(pid=sub_proc.pid)

            # Create proc monitor
            self.worker_subprocess_monitor.set_proc(sub_proc.pid)

            # Set process priority (cross-platform via psutil)
            try:
                if os.name == "nt":
                    proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
                else:
                    parent_proc = psutil.Process(os.getpid())
                    proc.nice(parent_proc.nice() + 1)
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError) as e:
                self.logger.warning("Unable to lower priority of subprocess. Subprocess should continue to run at normal priority: %s",
                                    e)

            # Poll process for new output until finished
            while not self.redundant_flag.is_set():

                # Stop parsing the sub process if the worker is paused
                # Then resume it when the worker is resumed
                if self.paused_flag.is_set():
                    self.logger.debug("Pausing worker exec command subprocess loop")
                    while not self.redundant_flag.is_set():
                        self.event.wait(1)
                        if not self.paused_flag.is_set():
                            self.logger.debug("Resuming worker exec command subprocess loop")
                            break
                        continue

                # Fetch command stdout and append it to the current task object (to be saved during post process)
                line_text = sub_proc.stdout.readline()
                self.worker_log.append(line_text)

                # Check if the command has completed. If it has, exit the loop
                if line_text == '' and sub_proc.poll() is not None:
                    self.logger.debug("Subprocess task completed!")
                    break

                # Parse encoding speed from FFmpeg output
                self.worker_subprocess_monitor.parse_ffmpeg_speed(line_text)

                # Parse the progress
                try:
                    progress_dict = command_progress_parser(line_text)
                    progress_percent = progress_dict.get('percent', 0)
                    self.worker_subprocess_monitor.set_subprocess_percent(progress_percent)
                except (ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
                    # Only need to show any sort of exception if we have debugging enabled.
                    # So we should log it as a debug rather than an exception.
                    self.logger.debug("Exception while parsing command progress: %s", e)

            # Get the final output and the exit status
            if not self.redundant_flag.is_set():
                sub_proc.communicate()

            # If the process is still running, kill it
            self.worker_subprocess_monitor.terminate_proc()

            # Stop proc monitor
            self.worker_subprocess_monitor.unset_proc()
            if isinstance(current_command_ref, list):
                current_command_ref.clear()

            if sub_proc.returncode == 0:
                return True
            else:
                self.logger.error("WORKER_COMMAND_FAILED file=%s command=%s", data.get("file_in"), exec_command)
                self.logger.error("Command run against '%s' exited with non-zero status. "
                                  "Download command dump from history for more information. %s",
                                  data.get("file_in"),
                                  exec_command)
                return False

        except (subprocess.SubprocessError, OSError, FileNotFoundError, TypeError) as e:
            self.logger.error("WORKER_COMMAND_EXCEPTION file=%s", data.get("file_in"))
            self.logger.error("Error while executing the command against file %s. %s",
                              data.get("file_in"),
                              e)

        return False


# Backward-compatible imports
from compresso.libs.worker_subprocess_monitor import WorkerSubprocessMonitor as WorkerSubprocessMonitor, WorkerCommandError  # noqa: E402, F811, F401
