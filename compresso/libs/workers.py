#!/usr/bin/env python3

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
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol, cast

import psutil

from compresso import config
from compresso.libs import common
from compresso.libs.disk_space_guard import DiskSpaceCheck, DiskSpaceGuard
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler
from compresso.libs.safety_state import SafetyForeman, record_safety_event
from compresso.libs.task import Task
from compresso.libs.unmodels.tasks import Tasks
from compresso.libs.worker_subprocess_monitor import WorkerSubprocessMonitor

type WorkerLog = deque[str] | list[str]
type RunnerInfo = dict[str, dict[str, object]]


@dataclass(frozen=True)
class RunnerOutcome:
    file_in: str
    current_file_out: str
    success: bool
    command_run: bool


class SafetyEventRecorder(Protocol):
    def __call__(
        self,
        settings: config.Config,
        foreman: SafetyForeman | None,
        code: str,
        message: str,
        **details: object,
    ) -> object: ...


def _set_task_timestamp(
    task_model: Tasks,
    field: Literal["start_time", "finish_time"],
    value: float | None,
) -> None:
    """Bridge Peewee's write-time timestamp coercion and hydrated field type."""
    setattr(task_model, field, value)


def _run_worker_plugin(
    plugin_handler: PluginsHandler,
    data: dict[str, object],
    runner_id: str,
    outcome: "queue.Queue[bool]",
) -> None:
    outcome.put(plugin_handler.exec_plugin_runner(data, runner_id, "worker.process"))


class Worker(threading.Thread):
    # Instance state is initialised in __init__; annotations here avoid the
    # shared-mutable-default footgun of class-level `{}` / mutable attributes.
    idle: bool
    paused: bool
    worker_log: WorkerLog | None
    start_time: float | None
    finish_time: float | None
    worker_runners_info: RunnerInfo

    def __init__(
        self,
        thread_id: int | str,
        name: str,
        worker_group_id: int | str,
        pending_queue: queue.Queue[Task],
        complete_queue: queue.Queue[Task],
        event: threading.Event,
    ) -> None:
        super().__init__(name=name)
        self.thread_id = thread_id
        self.name = name
        self.worker_group_id = worker_group_id
        self.event = event

        self.idle = True
        self.paused = False
        self.worker_log = None
        self.start_time = None
        self.finish_time = None
        self.worker_runners_info = {}

        self.current_task: Task | None = None
        self.current_command_ref: list[str] | None = None
        self.pending_queue = pending_queue
        self.complete_queue = complete_queue
        self.worker_subprocess_monitor: WorkerSubprocessMonitor | None = None
        self._disk_space_guard: DiskSpaceGuard | None = None
        self.disk_pressure_paused = False
        self.disk_pressure: dict[str, bool | str | int] | None = None
        self._safety_event_recorder: SafetyEventRecorder = record_safety_event

        # Create 'redundancy' flag. When this is set, the worker should die
        self.redundant_flag = threading.Event()
        self.redundant_flag.clear()

        # Create 'paused' flag. When this is set, the worker should be paused
        self.paused_flag = threading.Event()
        self.paused_flag.clear()

        # Create logger for this worker
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)

    def _require_current_task(self) -> Task:
        current_task = self.current_task
        if current_task is None:
            raise RuntimeError("worker has no current task")
        return current_task

    @property
    def task(self) -> Task:
        return self._require_current_task()

    @property
    def model(self) -> Tasks:
        task_model = self.task.task
        if task_model is None:
            raise RuntimeError("worker current task is not loaded")
        return task_model

    @property
    def log(self) -> WorkerLog:
        worker_log = self.worker_log
        if worker_log is None:
            raise RuntimeError("worker log is not initialized")
        return worker_log

    @property
    def monitor(self) -> WorkerSubprocessMonitor:
        monitor = self.worker_subprocess_monitor
        if monitor is None:
            raise RuntimeError("worker subprocess monitor is not running")
        return monitor

    def run(self) -> None:
        self.logger.info("Starting worker")

        # Create proc monitor
        self.worker_subprocess_monitor = WorkerSubprocessMonitor(self)
        self.monitor.start()

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
                self.event.wait(0.5)  # Add delay for preventing loop maxing compute resources

                try:
                    # Process the set task
                    self.__process_task_queue_item()
                except queue.Empty:
                    continue
                except Exception as e:
                    self.logger.error("WORKER_TASK_PROCESSING_FAILED worker=%s", self.name)
                    self.logger.exception("Exception in processing job with %s: %s", self.name, e)
                    self._fail_current_task_after_unexpected_error(e)

        self.logger.info("Stopping worker")
        self.monitor.stop()
        self.monitor.join()
        self.worker_subprocess_monitor = None

    def set_task(self, new_task: Task) -> None:
        """Sets the given task to the worker class"""
        # Ensure only one task can be set for a worker
        if self.current_task:
            return
        # Set the task
        self.current_task = new_task
        self.worker_log = deque(maxlen=500)
        self.idle = False

    def get_status(self) -> dict[str, object]:
        """
        Fetch the status of this worker.

        :return:
        """
        subprocess_stats = None
        if self.worker_subprocess_monitor:
            subprocess_stats = self.monitor.get_subprocess_stats()
        current_command = ""
        try:
            if self.current_command_ref:
                shared_command = self.current_command_ref[-1]
                if shared_command:
                    current_command = shared_command
        except (AttributeError, TypeError, IndexError) as e:
            self.logger.exception("Exception in fetching current command of worker %s: %s", self.name, e)
        status: dict[str, object] = {
            "id": str(self.thread_id),
            "name": self.name,
            "idle": self.idle,
            "paused": self.paused_flag.is_set() or self.disk_pressure_paused,
            "pause_reason": "disk_pressure" if self.disk_pressure_paused else None,
            "disk_pressure": self.disk_pressure,
            "start_time": None if not self.start_time else str(self.start_time),
            "current_task": None,
            "current_file": "",
            "current_command": current_command,
            "worker_log_tail": [],
            "runners_info": {},
            "subprocess": subprocess_stats,
        }
        if self.current_task:
            self._add_current_task_status(status)
        return status

    def _add_current_task_status(self, status: dict[str, object]) -> None:
        status["current_task"] = self._safe_task_status_value("ID", self.task.get_task_id)
        status["current_file"] = self._safe_task_status_value("file", self.task.get_source_basename, "")
        try:
            log_tail = list(self.worker_log or [])
            status["worker_log_tail"] = log_tail[-39:] if len(log_tail) > 40 else log_tail
        except (AttributeError, TypeError, IndexError) as error:
            self.logger.exception("Exception in fetching log tail of worker: %s", error)
        try:
            status["runners_info"] = self.worker_runners_info
        except (AttributeError, KeyError, TypeError) as error:
            self.logger.exception("Exception in runners info of worker %s: %s", self.name, error)

    def _safe_task_status_value(self, label: str, getter: Callable[[], object], default: object = None) -> object:
        try:
            return getter()
        except Exception as error:
            self.logger.exception("Exception in fetching current task %s for worker %s: %s", label, self.name, error)
            return default

    def __unset_current_task(self) -> None:
        self.current_task = None
        self.worker_runners_info = {}
        self.worker_log = deque(maxlen=500)

    def _fail_current_task_after_unexpected_error(self, error: Exception) -> None:
        """Release a poisoned task so one exception cannot wedge a worker forever."""
        failed_task = self.current_task
        if failed_task is None:
            return

        if self.worker_subprocess_monitor is not None:
            self.monitor.terminate_proc()

        try:
            failed_task.set_success(False)
        except Exception:
            self.logger.exception("Unable to persist failure for task after worker error: %s", error)

        try:
            self.complete_queue.put(failed_task)
        except Exception:
            self.logger.exception("Unable to queue failed task after worker error: %s", error)
        finally:
            self.__unset_current_task()

    def __process_task_queue_item(self) -> None:
        """
        Processes the set task.

        :return:
        """
        # Mark worker as not idle now that it is processing a task
        self.idle = False

        # Log the start of the job
        self.logger.info("Picked up job - %s", self.task.get_source_abspath())

        disk_check = self._check_task_disk_space()
        if not disk_check.ok:
            if not self.disk_pressure_paused:
                self.logger.warning(
                    "WORKER_DISK_PRESSURE_PAUSED worker=%s path=%s free_bytes=%s required_bytes=%s",
                    self.name,
                    disk_check.path,
                    disk_check.free_bytes,
                    disk_check.required_bytes,
                )
                self._safety_event_recorder(
                    config.Config(),
                    None,
                    "disk-reserve",
                    "Cache disk free space is below the safe encoding reserve",
                    phase=disk_check.phase,
                    path=disk_check.path,
                    free_bytes=disk_check.free_bytes,
                    required_bytes=disk_check.required_bytes,
                )
            self.disk_pressure_paused = True
            self.disk_pressure = disk_check.to_dict() if hasattr(disk_check, "to_dict") else vars(disk_check)
            return
        if self.disk_pressure_paused:
            self.logger.info("WORKER_DISK_PRESSURE_RECOVERED worker=%s path=%s", self.name, disk_check.path)
        self.disk_pressure_paused = False
        self.disk_pressure = None

        # Start current task stats
        self.__set_start_task_stats()

        # Mark as being "in progress"
        self.task.set_status("in_progress")

        # Process the file. Will return true if success, otherwise false
        success = self.__exec_worker_runners_on_set_task()
        # Mark the task as either success or not
        self.task.set_success(success)

        # Store encoding speed stats on the task for postprocessor
        if self.worker_subprocess_monitor is not None:
            speed_stats = self.monitor.get_encoding_speed_stats()
            elapsed = self.monitor.get_subprocess_elapsed()
            self.task.statistics["encoding_speed"] = {
                "avg_encoding_fps": speed_stats.get("avg_encoding_fps", 0),
                "encoding_speed_ratio": speed_stats.get("encoding_speed_ratio", 0),
                "encoding_duration_seconds": elapsed,
            }
            self.monitor.reset_encoding_speed_stats()
        else:
            self.task.statistics["encoding_speed"] = {
                "avg_encoding_fps": 0,
                "encoding_speed_ratio": 0,
                "encoding_duration_seconds": 0,
            }

        # Mark task completion statistics
        self.__set_finish_task_stats()

        # Log completion of job
        self.logger.info("Finished job - %s", self.task.get_source_abspath())

        # Place the task into the completed queue
        self.complete_queue.put(self.task)

        # Reset the current file info for the next task
        self.__unset_current_task()

    def _check_task_disk_space(self) -> DiskSpaceCheck:
        if self._disk_space_guard is None:
            self._disk_space_guard = DiskSpaceGuard(config.Config())
        return self._disk_space_guard.check_cache_capacity(
            self.task.get_source_abspath(),
            self.task.get_cache_path(),
        )

    def __set_start_task_stats(self) -> None:
        """Sets the initial stats for the start of a task"""
        # Set the start time to now
        self.start_time = time.time()

        # Clear the finish time
        self.finish_time = None

        # Format our starting statistics data
        self.model.processed_by_worker = str(self.name)
        _set_task_timestamp(self.model, "start_time", self.start_time)
        _set_task_timestamp(self.model, "finish_time", self.finish_time)

    def __set_finish_task_stats(self) -> None:
        """Sets the final stats for the end of a task"""
        # Set the finish time to now
        self.finish_time = time.time()

        # Set the finish time in the statistics data
        _set_task_timestamp(self.model, "finish_time", self.finish_time)

    def __exec_worker_runners_on_set_task(self) -> bool:
        """
        Executes the configured plugin runners against the set task.

        :return:
        """
        library_id = self.task.get_task_library_id()
        plugin_handler = PluginsHandler()
        plugin_modules = plugin_handler.get_enabled_plugin_modules_by_type("worker.process", library_id=library_id)
        self.worker_runners_info = self.__build_worker_runners_info(plugin_modules)
        original_abspath = self.task.get_source_abspath()
        task_cache_path = self.task.get_cache_path()
        cache_directory = os.path.dirname(os.path.abspath(task_cache_path))
        file_in = original_abspath
        overall_success = True
        current_file_out = original_abspath
        no_exec_command_run = True
        self.__emit_worker_process_started(plugin_handler, library_id, original_abspath, cache_directory)
        data = self.__new_worker_runner_data(library_id, original_abspath)

        for runner_count, plugin_module in enumerate(plugin_modules, start=1):
            runner_id = plugin_module.get("plugin_id")
            if not isinstance(runner_id, str):
                self.logger.warning("Skipping worker plugin without a valid plugin ID")
                continue
            if not overall_success:
                break
            outcome = self.__run_worker_plugin_module(
                plugin_handler,
                plugin_module,
                runner_id,
                runner_count,
                data,
                library_id,
                original_abspath,
                task_cache_path,
                file_in,
            )
            file_in = outcome.file_in
            current_file_out = outcome.current_file_out
            overall_success = outcome.success
            no_exec_command_run = no_exec_command_run and not outcome.command_run

        # Log if no command was run by any Plugins
        if no_exec_command_run:
            # If no jobs were carried out on this task
            self.logger.warning("No Plugin requested for Compresso to run commands for this file '%s'", original_abspath)
            self.log.append(f"\n\nNo Plugin requested for Compresso to run commands for this file '{original_abspath}'")

        self.task.save_command_log(self.log)
        if overall_success:
            self.logger.info("Successfully completed Worker processing on file '%s'", original_abspath)
            move_ok, task_cache_path = self.__move_final_output_to_cache(
                current_file_out, cache_directory, original_abspath, task_cache_path
            )
            if not move_ok:
                overall_success = False
        self.__emit_worker_process_complete(plugin_handler, library_id, original_abspath, task_cache_path, overall_success)
        if not overall_success:
            self.logger.warning("WORKER_TASK_FAILED file=%s", original_abspath)
            self.logger.warning("Failed to process task for file '%s'", original_abspath)
        return overall_success

    def __emit_worker_process_started(
        self, plugin_handler: PluginsHandler, library_id: int, original_path: str, cache_directory: str
    ) -> None:
        plugin_handler.run_event_plugins_for_plugin_type(
            "events.worker_process_started",
            {
                "library_id": library_id,
                "task_id": self.task.get_task_id(),
                "task_type": self.task.get_task_type(),
                "original_file_path": original_path,
                "cache_directory": cache_directory,
                "worker_runners_info": self.worker_runners_info,
            },
        )

    def __emit_worker_process_complete(
        self,
        plugin_handler: PluginsHandler,
        library_id: int,
        original_path: str,
        cache_path: str,
        overall_success: bool,
    ) -> None:
        plugin_handler.run_event_plugins_for_plugin_type(
            "events.worker_process_complete",
            {
                "library_id": library_id,
                "task_id": self.task.get_task_id(),
                "task_type": self.task.get_task_type(),
                "original_file_path": original_path,
                "final_cache_path": cache_path,
                "overall_success": overall_success,
                "worker_runners_info": self.worker_runners_info,
                "worker_log": self.worker_log,
            },
        )

    def __new_worker_runner_data(self, library_id: int, original_path: str) -> dict[str, object]:
        return {
            "worker_log": self.worker_log,
            "library_id": library_id,
            "exec_command": [],
            "current_command": [],
            "command_progress_parser": None,
            "file_in": original_path,
            "file_out": None,
            "original_file_path": original_path,
            "repeat": False,
        }

    def __run_worker_plugin_module(
        self,
        plugin_handler: PluginsHandler,
        plugin_module: Mapping[str, object],
        runner_id: str,
        runner_count: int,
        data: dict[str, object],
        library_id: int,
        original_path: str,
        cache_path: str,
        file_in: str,
    ) -> RunnerOutcome:
        self.worker_runners_info[runner_id].update({"status": "in_progress", "success": False})
        current_file_out = file_in
        command_run = False
        runner_failed = False
        pass_count = 0
        while not self.redundant_flag.is_set():
            pass_count += 1
            self.__prepare_worker_runner_pass(data, library_id, original_path, cache_path, file_in, runner_count, pass_count)
            self.__log_worker_runner_start(plugin_module, pass_count)
            if not self.__invoke_worker_plugin(plugin_handler, data, runner_id, plugin_module.get("name")):
                runner_failed = True
                break
            plugin_paths = self.__validated_worker_plugin_paths(data, runner_id)
            if plugin_paths is None:
                runner_failed = True
                break
            pass_outcome = self.__process_worker_runner_pass(data, runner_id, original_path, *plugin_paths)
            file_in = pass_outcome.file_in
            current_file_out = pass_outcome.current_file_out
            command_run = command_run or pass_outcome.command_run
            if not pass_outcome.success:
                runner_failed = True
                break
            if not data.get("repeat"):
                break
        self.worker_runners_info[runner_id]["success"] = not runner_failed
        self.worker_runners_info[runner_id]["status"] = "complete"
        return RunnerOutcome(file_in, current_file_out, not runner_failed, command_run)

    def __prepare_worker_runner_pass(
        self,
        data: dict[str, object],
        library_id: int,
        original_path: str,
        cache_path: str,
        file_in: str,
        runner_count: int,
        pass_count: int,
    ) -> None:
        output_root = os.path.splitext(cache_path)[0]
        input_extension = os.path.splitext(file_in)[1]
        current_command: list[str] = []
        data.update(
            {
                "library_id": library_id,
                "exec_command": [],
                "current_command": current_command,
                "command_progress_parser": self.monitor.default_progress_parser,
                "file_in": file_in,
                "file_out": f"{output_root}-WORKING-{runner_count}-{pass_count}{input_extension}",
                "original_file_path": original_path,
                "repeat": False,
                "task_id": self.task.get_task_id(),
            }
        )
        self.current_command_ref = current_command

    def __log_worker_runner_start(self, plugin_module: Mapping[str, object], pass_count: int) -> None:
        self.event.wait(0.2)
        self.log.append(f"\n\nRUNNER: \n{plugin_module.get('name')} [Pass #{pass_count}]\n\n")
        self.log.append("\nExecuting plugin runner... Please wait\n")

    def __invoke_worker_plugin(
        self,
        plugin_handler: PluginsHandler,
        data: dict[str, object],
        runner_id: str,
        plugin_name: object,
    ) -> bool:
        outcome: queue.Queue[bool] = queue.Queue(maxsize=1)
        runner_thread = threading.Thread(
            target=_run_worker_plugin,
            args=(plugin_handler, data, runner_id, outcome),
            daemon=True,
        )
        runner_thread.start()
        self.__wait_for_worker_plugin(runner_thread, runner_id)
        if self.redundant_flag.is_set():
            self.__record_terminated_worker_plugin(runner_thread, runner_id, data)
            return False
        try:
            success = outcome.get_nowait()
        except queue.Empty:
            success = False
        if success:
            return True
        self.log.append("\n\nPLUGIN FAILED!")
        self.log.append(f"\nFailed to execute Plugin '{plugin_name}'")
        self.log.append("\nCheck Compresso logs for more information")
        self.__clear_current_command(data)
        return False

    def __wait_for_worker_plugin(self, runner_thread: threading.Thread, runner_id: str) -> None:
        while runner_thread.is_alive():
            if self.redundant_flag.is_set():
                self.logger.warning("Worker stop flag set, aborting plugin runner '%s'", runner_id)
                return
            self.event.wait(0.2)

    def __record_terminated_worker_plugin(
        self, runner_thread: threading.Thread, runner_id: str, data: dict[str, object]
    ) -> None:
        runner_thread.join(timeout=10)
        if runner_thread.is_alive():
            self.logger.warning("Plugin runner '%s' did not stop within timeout after worker shutdown", runner_id)
        self.log.append("\n\nWORKER TERMINATED!")
        self.__clear_current_command(data)

    def __validated_worker_plugin_paths(self, data: Mapping[str, object], runner_id: str) -> tuple[str, str | None] | None:
        self.logger.debug("Worker process '%s' (in) %s", runner_id, data.get("file_in"))
        self.logger.debug("Worker process '%s' (out) %s", runner_id, data.get("file_out"))
        plugin_file_in = data.get("file_in")
        plugin_file_out = data.get("file_out")
        if not isinstance(plugin_file_in, str) or (plugin_file_out is not None and not isinstance(plugin_file_out, str)):
            self.logger.error("Worker plugin '%s' returned invalid file paths", runner_id)
            return None
        return plugin_file_in, plugin_file_out

    def __process_worker_runner_pass(
        self,
        data: dict[str, object],
        runner_id: str,
        original_path: str,
        plugin_file_in: str,
        plugin_file_out: str | None,
    ) -> RunnerOutcome:
        if not data.get("exec_command"):
            self.log.append("\nRunner did not request for Compresso to execute a command")
            self.logger.debug("Worker process '%s' did not request to execute a command.", runner_id)
            self.__clear_current_command(data)
            return RunnerOutcome(plugin_file_in, self.__latest_runner_output(plugin_file_in, plugin_file_out), True, False)
        self.log.append("\nPlugin runner requested for a command to be executed by Compresso")
        self.current_command_ref = self.__string_list_or_none(data.get("current_command"))
        success = self.__exec_command_subprocess(data)
        if self.redundant_flag.is_set():
            self.logger.warning("Worker has been terminated before a command was completed")
            self.log.append("\n\nWORKER TERMINATED!")
            self.__clear_current_command(data)
            return RunnerOutcome(plugin_file_in, plugin_file_in, False, True)
        if not success:
            self.logger.error("WORKER_RUNNER_FAILED runner=%s file=%s", runner_id, original_path)
            self.logger.error("Error while running worker process '%s' on file '%s'", runner_id, original_path)
            self.__clear_current_command(data)
            return RunnerOutcome(plugin_file_in, plugin_file_in, False, True)
        file_in = self.__successful_runner_input(plugin_file_in, plugin_file_out, original_path, runner_id)
        current_file_out = self.__latest_runner_output(plugin_file_in, plugin_file_out)
        self.__clear_current_command(data)
        return RunnerOutcome(file_in, current_file_out, True, True)

    def __successful_runner_input(
        self, plugin_file_in: str, plugin_file_out: str | None, original_path: str, runner_id: str
    ) -> str:
        self.logger.info("Successfully ran worker process '%s' on file '%s'", runner_id, plugin_file_in)
        if not plugin_file_out:
            return plugin_file_in
        if not os.path.exists(plugin_file_out):
            return plugin_file_in
        self.__remove_intermediate_input_file(plugin_file_in, plugin_file_out, original_path)
        return plugin_file_out

    @staticmethod
    def __latest_runner_output(plugin_file_in: str, plugin_file_out: str | None) -> str:
        return plugin_file_out if plugin_file_out and os.path.exists(plugin_file_out) else plugin_file_in

    @staticmethod
    def __string_list_or_none(value: object) -> list[str] | None:
        return value if isinstance(value, list) and all(isinstance(item, str) for item in value) else None

    def __clear_current_command(self, data: dict[str, object]) -> None:
        self.current_command_ref = None
        data["current_command"] = []

    @staticmethod
    def __build_worker_runners_info(plugin_modules: list[dict[str, object]]) -> RunnerInfo:
        """
        Build the initial per-runner status map that is surfaced to the frontend.

        :param plugin_modules: Enabled ``worker.process`` plugin module dicts.
        :return: dict keyed by plugin_id with pending status entries.
        """
        runners_info: RunnerInfo = {}
        for plugin_module in plugin_modules:
            plugin_id = plugin_module.get("plugin_id")
            if not isinstance(plugin_id, str):
                continue
            runners_info[plugin_id] = {
                "plugin_id": plugin_id,
                "status": "pending",
                "name": plugin_module.get("name"),
                "author": plugin_module.get("author"),
                "version": plugin_module.get("version"),
                "icon": plugin_module.get("icon"),
                "description": plugin_module.get("description"),
            }
        return runners_info

    @staticmethod
    def __remove_intermediate_input_file(file_in: str, file_out: str, original_abspath: str) -> None:
        """
        Remove an intermediate worker input file once a runner has produced a new
        output, freeing cache space between passes.

        Three guards protect against ever deleting a file we must keep:
          1. never delete the original source file;
          2. only delete files that live inside a 'compresso_file_conversion' cache
             directory (never an arbitrary path);
          3. never delete file_in when the plugin set file_out to the same path.

        :param file_in: The intermediate input file that may be removed.
        :param file_out: The output file the runner produced.
        :param original_abspath: Absolute path of the original source file.
        """
        file_in_abs = os.path.abspath(file_in)
        # Guard 1: never touch the original source file.
        if file_in_abs == os.path.abspath(original_abspath):
            return
        # Guard 2: only ever delete from within a Compresso conversion cache directory.
        if "compresso_file_conversion" not in file_in_abs:
            return
        # Guard 3: never delete file_in if it is also the produced file_out.
        if os.path.abspath(file_out) == file_in_abs:
            return
        os.remove(file_in_abs)

    def __move_final_output_to_cache(
        self,
        current_file_out: str,
        cache_directory: str,
        original_abspath: str,
        fallback_cache_path: str,
    ) -> tuple[bool, str]:
        """
        Move the final worker output to the task cache path for the postprocessor.

        When the final output is still the original source (e.g. all plugins reset
        the output to preserve the source) a copy is made instead of a move, so the
        original is never relocated out from under the library.

        :param fallback_cache_path: Cache path to return unchanged if the move fails
                                    before a fresh cache path can be resolved.
        :return: tuple of (success: bool, task_cache_path: str).
        """
        # Start from the caller's cache path; resolve a fresh one once the final
        # extension is known. Kept as a local so the parameter is never reassigned.
        task_cache_path = fallback_cache_path
        try:
            # Set the new file out as the extension may have changed
            split_file_name = os.path.splitext(current_file_out)
            file_extension = split_file_name[1].lstrip(".")
            self.task.set_cache_path(cache_directory, file_extension)
            # Read the updated cache path
            task_cache_path = self.task.get_cache_path()

            # Move file to original cache path
            self.logger.info("Moving final cache file from '%s' to '%s'", current_file_out, task_cache_path)
            current_file_out = os.path.abspath(current_file_out)

            # There is a really odd intermittent bug with the shutil module that is causing it to
            #   sometimes report that the file does not exist.
            # This section adds a small pause and logs the error if that is the case.
            # I have not yet figured out a solution as this is difficult to reproduce.
            if not os.path.exists(current_file_out):
                self.logger.error("WORKER_FINAL_OUTPUT_MISSING file=%s", current_file_out)
                self.logger.error("Error - current_file_out path does not exist! '%s'", current_file_out)
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
            return True, task_cache_path
        except (OSError, PermissionError, shutil.Error) as e:
            self.logger.error("WORKER_FINAL_MOVE_FAILED source=%s dest=%s", current_file_out, task_cache_path)
            self.logger.exception(
                "Exception in final move operation of file %s to %s: %s", current_file_out, task_cache_path, e
            )
            return False, task_cache_path

    def __apply_parsed_progress(self, progress_value: object) -> None:
        # A parser returning a non-mapping must not reset progress to 0
        if isinstance(progress_value, Mapping):
            self.monitor.set_subprocess_percent(progress_value.get("percent", 0))

    def __exec_command_subprocess(self, data: dict[str, object]) -> bool:
        """
        Executes a command as a shell subprocess.
        Uses the given parser to record progress data from the shell STDOUT.

        :param data:
        :return:
        """
        # Fetch command to execute.
        exec_command = data.get("exec_command", [])

        # Fetch the command progress parser function
        parser_value = data.get("command_progress_parser", self.monitor.default_progress_parser)
        command_progress_parser = (
            cast("Callable[[object], object]", parser_value)
            if callable(parser_value)
            else self.monitor.default_progress_parser
        )

        # Log the command for debugging
        command_string = (
            shlex.join(exec_command)
            if isinstance(exec_command, list) and all(isinstance(argument, str) for argument in exec_command)
            else str(exec_command)
        )
        self.logger.debug("Executing: %s", command_string)
        current_command_ref = data.get("current_command")
        if isinstance(current_command_ref, list):
            current_command_ref.clear()
            current_command_ref.append(command_string)

        # Append start of command to worker subprocess stdout
        self.log.extend(
            [
                "\n\n",
                "COMMAND:\n",
                command_string,
                "\n\n",
                "LOG:\n",
            ]
        )

        # Create output path if file_out is present and the path does not exists
        file_out_value = data.get("file_out")
        if isinstance(file_out_value, str) and file_out_value:
            common.ensure_dir(file_out_value)

        # Convert file
        try:
            sub_proc = self._start_command_subprocess(exec_command)
            self.monitor.set_proc(sub_proc.pid)
            self._configure_process_priority(sub_proc.pid)
            self._stream_command_output(sub_proc, command_progress_parser)
            self._finish_command_subprocess(sub_proc)
            if isinstance(current_command_ref, list):
                current_command_ref.clear()

            if sub_proc.returncode == 0:
                return True
            else:
                self.logger.error("WORKER_COMMAND_FAILED file=%s command=%s", data.get("file_in"), exec_command)
                self.logger.error(
                    "Command run against '%s' exited with non-zero status. "
                    "Download command dump from history for more information. %s",
                    data.get("file_in"),
                    exec_command,
                )
                return False

        except (subprocess.SubprocessError, OSError, FileNotFoundError, TypeError) as e:
            self.logger.error("WORKER_COMMAND_EXCEPTION file=%s", data.get("file_in"))
            self.logger.error("Error while executing the command against file %s. %s", data.get("file_in"), e)

        return False

    @staticmethod
    def _start_command_subprocess(exec_command: object) -> subprocess.Popen[str]:
        if not isinstance(exec_command, list) or not exec_command or not all(isinstance(arg, str) for arg in exec_command):
            raise TypeError("Plugin 'exec_command' must be a non-empty argv list of strings; shell strings are forbidden")
        process = subprocess.Popen(  # noqa: S603 - explicit argv from an operator-trusted plugin
            exec_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            errors="replace",
            shell=False,
            start_new_session=True,
        )
        if process.stdout is None:
            raise RuntimeError("Worker subprocess did not expose stdout")
        return process

    def _configure_process_priority(self, pid: int) -> None:
        try:
            process = psutil.Process(pid=pid)
            if os.name == "nt":
                process.nice(cast("int", getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 0x4000)))
            else:
                process.nice(psutil.Process(os.getpid()).nice() + 1)
        except (psutil.AccessDenied, psutil.NoSuchProcess, OSError) as error:
            self.logger.warning("Unable to lower subprocess priority; continuing normally: %s", error)

    def _stream_command_output(self, process: subprocess.Popen[str], progress_parser: Callable[[object], object]) -> None:
        if process.stdout is None:
            raise RuntimeError("Worker subprocess did not expose stdout")
        while not self.redundant_flag.is_set():
            self._wait_while_paused()
            line_text = process.stdout.readline()
            self.log.append(line_text)
            if line_text == "" and process.poll() is not None:
                self.logger.debug("Subprocess task completed!")
                break
            self.monitor.parse_ffmpeg_speed(line_text)
            try:
                self.__apply_parsed_progress(progress_parser(line_text))
            except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
                self.logger.debug("Exception while parsing command progress: %s", error)

    def _wait_while_paused(self) -> None:
        if not self.paused_flag.is_set():
            return
        self.logger.debug("Pausing worker exec command subprocess loop")
        while self.paused_flag.is_set() and not self.redundant_flag.is_set():
            self.event.wait(1)
        self.logger.debug("Resuming worker exec command subprocess loop")

    def _finish_command_subprocess(self, process: subprocess.Popen[str]) -> None:
        if not self.redundant_flag.is_set():
            try:
                process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                self.logger.warning("Subprocess communicate() timed out after 30s, terminating")
        self.monitor.terminate_proc()
        self.monitor.unset_proc()


# Backward-compatible imports
from compresso.libs.worker_subprocess_monitor import WorkerCommandError as WorkerCommandError  # noqa: E402, F811, F401
from compresso.libs.worker_subprocess_monitor import (  # noqa: E402, F811, F401
    WorkerSubprocessMonitor as WorkerSubprocessMonitor,
)
