#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.worker_subprocess_monitor.py

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
import re
import threading
import time

import psutil

from compresso.libs.logs import CompressoLogging


class WorkerCommandError(Exception):
    def __init__(self, command):
        Exception.__init__(self, "Worker command returned non 0 status. Command: {}".format(command))
        self.command = command


class WorkerSubprocessMonitor(threading.Thread):
    def __init__(self, parent_worker):
        super().__init__(daemon=True)
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)
        self._stop_event = threading.Event()
        self._terminate_lock = threading.Lock()

        self.parent_worker = parent_worker
        self.event = parent_worker.event
        self.redundant_flag = parent_worker.redundant_flag
        self.paused_flag = parent_worker.paused_flag
        self.paused = False

        # Set current subprocess to None
        self.subprocess_pid = None
        self.subprocess = None
        self.subprocess_start_time = 0
        self.subprocess_pause_time = 0
        self._pause_time_counter = None

        # Subprocess stats
        self.subprocess_percent = 0
        self.subprocess_elapsed = 0
        self.subprocess_cpu_percent = 0
        self.subprocess_mem_percent = 0
        self.subprocess_rss_bytes = 0
        self.subprocess_vms_bytes = 0

        # Encoding speed tracking
        self.last_encoding_fps = 0
        self.last_encoding_speed = 0
        self._fps_samples = []
        self._speed_samples = []

    def set_proc(self, pid):
        try:
            if pid != self.subprocess_pid:
                self.subprocess_pid = pid
                self.subprocess = psutil.Process(pid=pid)
                # Reset pause time
                self.subprocess_start_time = time.time()
                self.subprocess_pause_time = 0
                # Reset subprocess progress
                self.subprocess_percent = 0
                self.subprocess_elapsed = 0
            if self.redundant_flag.is_set():
                # If the redundant flag is set then we should terminate any set procs straight away as the worker needs to stop
                self.logger.debug("A new subprocess was spawned, but the worker is trying to terminate. Subprocess PID %s",
                                  self.subprocess_pid)
                self.terminate_proc()

        except Exception:
            self.logger.exception("Exception in set_proc()")

    def unset_proc(self):
        try:
            # Preserve the final elapsed time before clearing the subprocess
            self.subprocess_elapsed = self.get_subprocess_elapsed()
            self.subprocess_pid = None
            self.subprocess = None
            # Reset subprocess progress
            self.subprocess_percent = 0
            # Reset resource values
            self.set_proc_resources_in_parent_worker(0, 0, 0, 0)
        except Exception:
            self.logger.exception("Exception in unset_proc()")

    def set_proc_resources_in_parent_worker(self, normalised_cpu_percent, rss_bytes, vms_bytes, mem_percent):
        self.subprocess_cpu_percent = normalised_cpu_percent
        self.subprocess_rss_bytes = rss_bytes
        self.subprocess_vms_bytes = vms_bytes
        self.subprocess_mem_percent = mem_percent

    def suspend_proc(self):
        # Stop the process if the worker is paused.
        # Resume is handled separately so the monitor loop can keep running.
        try:
            if not self.subprocess or not self.subprocess.is_running():
                return

            # Create list of all subprocesses - parent + all children
            procs = [self.subprocess] + self.subprocess.children(recursive=True)

            # Suspend them all
            for p in procs:
                try:
                    self.logger.debug("Pausing PID %s", p.pid)
                    p.suspend()
                except psutil.NoSuchProcess:
                    continue

            self.paused = True

        except Exception:
            self.logger.exception("Exception in suspend_proc()")

    def resume_proc(self):
        try:
            if not self.subprocess or not self.subprocess.is_running():
                return

            # Create list of all subprocesses - parent + all children
            procs = [self.subprocess] + self.subprocess.children(recursive=True)

            # Resume in reverse order
            for p in reversed(procs):
                try:
                    self.logger.debug("Resuming PID %s", p.pid)
                    p.resume()
                    # Force anything to shut down straight away if we are exiting the thread
                    if self.redundant_flag.is_set() or self._stop_event.is_set():
                        p.terminate()
                except psutil.NoSuchProcess:
                    continue
            self.paused = False

        except Exception:
            self.logger.exception("Exception in resume_proc()")

    def terminate_proc(self):
        with self._terminate_lock:
            try:
                # If the process is still running, kill it
                if self.subprocess is not None:
                    self.logger.info("Terminating subprocess PID: %s", self.subprocess_pid)
                    self.__terminate_proc_tree(self.subprocess)
                    self.logger.info("Subprocess terminated")
                    self.unset_proc()
            except Exception:
                self.logger.exception("Exception in terminate_proc()")

    def __log_proc_terminated(self, proc: psutil.Process):
        try:
            self.logger.info("Process %s terminated with exit code %s", proc, proc.returncode)
        except Exception:
            self.logger.exception("Exception in __log_proc_terminated()")

    def __terminate_proc_tree(self, proc: psutil.Process):
        """
        Terminate the process tree (including grandchildren).
        Ensures any suspended processes are first resumed so that
        terminate() will actually take effect.  Processes that
        fail to stop with terminate() within 3s will be killed.

        :param proc:
        :return:
        """
        try:
            # Build the full tree
            all_procs = proc.children(recursive=True) + [proc]

            # Resume all suspended processes so they can handle signals
            for p in all_procs:
                try:
                    p.resume()
                except (psutil.NoSuchProcess, NotImplementedError):
                    pass

            # Attempt graceful shutdown
            for p in all_procs:
                try:
                    p.terminate()
                except psutil.NoSuchProcess:
                    pass

            # Wait up to 3s for them to exit
            gone, alive = psutil.wait_procs(all_procs, timeout=3, callback=self.__log_proc_terminated)

            # Force-kill any remaining processes
            for p in alive:
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass

            # Final wait to reap
            psutil.wait_procs(alive, timeout=3, callback=self.__log_proc_terminated)

        except Exception:
            self.logger.exception("Exception in __terminate_proc_tree()")

    def get_subprocess_elapsed(self):
        try:
            subprocess_elapsed = self.subprocess_elapsed
            if self.subprocess is not None:
                # Get the time now
                now = int(time.time())
                # Get the total running time (including time being paused)
                total_run_time = int(now - self.subprocess_start_time)
                # Get the time when we started being paused
                # Calculate elapsed time of the subprocess subtracting the pause duration
                subprocess_elapsed = int(total_run_time - self.subprocess_pause_time)
            self.subprocess_elapsed = subprocess_elapsed
            return subprocess_elapsed
        except Exception:
            self.logger.exception("Exception in get_subprocess_elapsed()")
            return self.subprocess_elapsed

    def get_subprocess_stats(self):
        try:
            elapsed = self.get_subprocess_elapsed()
            percent = self.subprocess_percent

            # Calculate ETA: time remaining based on elapsed time and progress
            eta_seconds = None
            if percent > 0 and elapsed > 0:
                eta_seconds = int((elapsed / percent) * (100 - percent))

            return {
                'pid':            str(self.subprocess_pid),
                'percent':        str(self.subprocess_percent),
                'elapsed':        elapsed,
                'cpu_percent':    str(self.subprocess_cpu_percent),
                'mem_percent':    str(self.subprocess_mem_percent),
                'rss_bytes':      str(self.subprocess_rss_bytes),
                'vms_bytes':      str(self.subprocess_vms_bytes),
                'eta_seconds':    eta_seconds,
                'encoding_fps':   self.last_encoding_fps,
                'encoding_speed': self.last_encoding_speed,
            }
        except Exception:
            self.logger.exception("Exception in get_subprocess_stats()")
            # Return something minimal so UI won't break
            return {
                'pid':            '0', 'percent': '0', 'elapsed': '0',
                'cpu_percent':    '0', 'mem_percent': '0',
                'rss_bytes':      '0', 'vms_bytes': '0',
                'eta_seconds':    None,
                'encoding_fps':   0,
                'encoding_speed': 0,
            }

    def parse_ffmpeg_speed(self, line_text):
        """Parse FFmpeg progress output for fps and speed values."""
        try:
            line = str(line_text).strip()
            if 'fps=' not in line and 'speed=' not in line:
                return
            fps_match = re.search(r'fps=\s*([\d.]+)', line)
            if fps_match:
                fps_val = float(fps_match.group(1))
                if fps_val > 0:
                    self.last_encoding_fps = fps_val
                    self._fps_samples.append(fps_val)
            speed_match = re.search(r'speed=\s*([\d.]+)x', line)
            if speed_match:
                speed_val = float(speed_match.group(1))
                if speed_val > 0:
                    self.last_encoding_speed = speed_val
                    self._speed_samples.append(speed_val)
        except Exception as e:
            self.logger.debug("Failed to parse FFmpeg speed output: %s", e)

    def get_encoding_speed_stats(self):
        """Return average encoding speed metrics collected during processing."""
        avg_fps = 0
        avg_speed = 0
        if self._fps_samples:
            avg_fps = sum(self._fps_samples) / len(self._fps_samples)
        if self._speed_samples:
            avg_speed = sum(self._speed_samples) / len(self._speed_samples)
        return {
            'avg_encoding_fps': round(avg_fps, 2),
            'encoding_speed_ratio': round(avg_speed, 2),
        }

    def reset_encoding_speed_stats(self):
        """Reset encoding speed tracking for a new task."""
        self.last_encoding_fps = 0
        self.last_encoding_speed = 0
        self._fps_samples = []
        self._speed_samples = []

    def set_subprocess_start_time(self, proc_start_time):
        try:
            self.subprocess_start_time = proc_start_time
        except Exception:
            self.logger.exception("Exception in set_subprocess_start_time()")

    def set_subprocess_percent(self, percent):
        try:
            self.subprocess_percent = max(0, min(100, int(float(percent))))
        except (TypeError, ValueError):
            self.subprocess_percent = 0
        except Exception:
            self.logger.exception("Exception in set_subprocess_percent()")

    def default_progress_parser(self, line_text, pid=None, proc_start_time=None, unset=False):
        if unset:
            # Here we provide a plugin with the ability to unset a subprocess (indicating that it completed)
            self.unset_proc()
            return {
                'killed':  self.redundant_flag.is_set(),
                'paused':  self.paused,
                'percent': str(self.subprocess_percent),
            }
        try:
            if pid is not None:
                self.set_proc(pid)
            if proc_start_time is not None:
                self.set_subprocess_start_time(proc_start_time)
            try:
                stripped_text = str(line_text).strip()
                text_float = float(stripped_text)
                self.subprocess_percent = int(text_float)
            except (TypeError, ValueError):
                pass
            return {
                'killed':  self.redundant_flag.is_set(),
                'paused':  self.paused,
                'percent': str(self.subprocess_percent),
            }
        except Exception:
            self.logger.exception("Exception in default_progress_parser()")
            return {
                'killed':  self.redundant_flag.is_set(),
                'paused':  self.paused,
                'percent': str(self.subprocess_percent),
            }

    def run(self):
        # First fetch the number of CPUs for normalising the CPU percent
        cpu_count = psutil.cpu_count(logical=True)
        # Loop while thread is expected to be running
        self.logger.warning("Starting WorkerMonitor loop")
        while True:
            try:
                if self._stop_event.is_set():
                    self.event.wait(1)
                    break

                if self.redundant_flag.is_set():
                    # If the worker needs to exit, then terminate the subprocess
                    self.terminate_proc()
                    self.event.wait(1)
                    continue

                if self.subprocess is None:
                    self.event.wait(1)
                    continue

                if not self.subprocess.is_running():
                    self.event.wait(1)
                    continue

                # Fetch CPU info
                cpu_percent = self.subprocess.cpu_percent(interval=None)
                normalised_cpu_percent = cpu_percent / cpu_count

                # Fetch Memory info
                mem_info = self.subprocess.memory_info()
                total_rss = mem_info.rss
                total_vms = mem_info.vms
                for child in self.subprocess.children(recursive=True):
                    try:
                        mem = child.memory_info()
                        total_rss += mem.rss
                        total_vms += mem.vms
                    except psutil.NoSuchProcess:
                        continue

                # Calculate percentage of memory used relative to total system RAM
                total_system_ram = psutil.virtual_memory().total
                mem_percent = (total_rss / total_system_ram) * 100

                # Set values in parent worker thread
                self.set_proc_resources_in_parent_worker(normalised_cpu_percent, total_rss, total_vms, mem_percent)

                # Pause/resume subprocesses while keeping the monitor loop alive
                if self.paused_flag.is_set():
                    if not self.paused:
                        self.suspend_proc()
                        self._pause_time_counter = time.time()
                    elif self._pause_time_counter is not None:
                        self.subprocess_pause_time += int(time.time() - self._pause_time_counter)
                        self._pause_time_counter = time.time()
                    self.event.wait(1)
                elif self.paused:
                    if self._pause_time_counter is not None:
                        self.subprocess_pause_time += int(time.time() - self._pause_time_counter)
                    self.resume_proc()
                    self._pause_time_counter = None

            except psutil.NoSuchProcess:
                self.logger.debug("No such process: %s", self.subprocess_pid)
            except Exception:
                self.logger.exception("Unhandled exception in WorkerMonitor.run()")

            # Poll interval
            try:
                self.event.wait(1)
            except Exception:
                # In case event.wait itself misbehaves
                self.logger.exception("Exception while waiting in WorkerMonitor.run()")
                time.sleep(1)

        self.logger.info("Exiting WorkerMonitor loop")

    def stop(self):
        self.terminate_proc()
        self._stop_event.set()
