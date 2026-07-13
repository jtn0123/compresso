#!/usr/bin/env python3

"""
compresso.postprocessor.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     23 Apr 2019, (7:33 PM)

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

import contextlib
import datetime
import os
import shutil
import subprocess
import threading
import time

import peewee

from compresso import config
from compresso.libs import common, history
from compresso.libs.disk_space_guard import DiskSpaceGuard
from compresso.libs.ffprobe_utils import extract_media_metadata
from compresso.libs.file_operation_tracker import FileOperationTracker, PostProcessError
from compresso.libs.frontend_push_messages import FrontendPushMessages
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.metadata import CompressoFileMetadata
from compresso.libs.notifications import Notifications
from compresso.libs.plugins import PluginsHandler
from compresso.libs.resumable_transfer import file_sha256
from compresso.libs.safety_state import record_safety_event
from compresso.libs.task import TaskDataStore
from compresso.libs.thread_health import ThreadHealthMixin

"""

The post-processor handles all tasks carried out on completion of a workers task.
This may be on either success or failure of the task.

The post-processor runs as a single thread, processing completed jobs one at a time.
This prevents conflicting copy operations or deleting a file that is also being post processed.

"""


class PostProcessor(ThreadHealthMixin, threading.Thread):
    """
    PostProcessor

    """

    def __init__(self, data_queues, task_queue, event):
        super().__init__(name="PostProcessor")
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)
        self.event = event
        self.data_queues = data_queues
        self.settings = config.Config()
        self.task_queue = task_queue
        self.abort_flag = threading.Event()
        self.current_task = None
        self._last_destination_files = []
        self._file_operation_tracker = None
        self._disk_space_guard = None
        self._safety_event_recorder = record_safety_event
        self.ffmpeg = None
        self.abort_flag.clear()
        self._init_thread_health()

    def _log(self, message, message2="", level="info"):
        message = common.format_message(message, message2)
        getattr(self.logger, level)(message)

    def stop(self):
        self.abort_flag.set()

    def run(self):
        self._log("Starting PostProcessor Monitor loop...")
        while not self.abort_flag.is_set():
            self.event.wait(1)
            self._mark_thread_heartbeat()
            try:
                self._process_available_tasks()
            except Exception as e:
                self._mark_thread_error(e)
                self._log("PostProcessor loop iteration failed; continuing", message2=str(e), level="exception")
                self.event.wait(2)

        self._log("Leaving PostProcessor Monitor loop...")

    def _process_available_tasks(self):
        if not self.system_configuration_is_valid():
            self.event.wait(2)
            return

        # Process completed transcodes (status='processed')
        while not self.abort_flag.is_set() and not self.task_queue.task_list_processed_is_empty():
            self.event.wait(0.2)
            self.current_task = self.task_queue.get_next_processed_tasks()
            if self.current_task:
                self._handle_task_safely(self._handle_processed_task)

        # Process approved tasks (status='approved') — finalize file replacement
        while not self.abort_flag.is_set() and not self.task_queue.task_list_approved_is_empty():
            self.event.wait(0.2)
            self.current_task = self.task_queue.get_next_approved_tasks()
            if self.current_task:
                self._handle_task_safely(self._handle_approved_task)

    def _handle_task_safely(self, handler):
        """Contain a single task failure so the postprocessor thread stays alive."""
        try:
            handler()
            self._mark_thread_success()
        except Exception as e:
            self._mark_thread_error(e)
            self._log("Unexpected post-processing task failure", message2=str(e), level="exception")
            try:
                self._defer_postprocess_failure(str(e))
            except Exception:
                self._log("Unable to defer failed post-processing task", level="exception")
        finally:
            self.current_task = None

    def _handle_processed_task(self):
        """Handle a task that just finished transcoding (status='processed')."""
        # Execute event plugin runners
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type(
            "events.postprocessor_started",
            {
                "library_id": self.current_task.get_task_library_id(),
                "task_id": self.current_task.get_task_id(),
                "task_type": self.current_task.get_task_type(),
                "cache_path": self.current_task.get_cache_path(),
                "source_data": self.current_task.get_source_data(),
            },
        )

        try:
            self._log(f"Post-processing task - {self.current_task.get_source_abspath()}")
        except (AttributeError, KeyError, TypeError) as e:
            self._log("Exception in fetching task absolute path", message2=str(e), level="exception")

        if self.current_task.get_task_type() == "local":
            # Size guardrail check (before staging or finalization)
            if self.current_task.task.success:
                try:
                    library = Library(self.current_task.get_task_library_id())
                    if library.get_size_guardrail_enabled():
                        source_size = self.current_task.task.source_size or 0
                        cache_path = self.current_task.get_cache_path()
                        if source_size > 0 and cache_path and os.path.exists(cache_path):
                            output_size = os.path.getsize(cache_path)
                            ratio_pct = (output_size / source_size) * 100
                            min_pct = library.get_size_guardrail_min_pct()
                            max_pct = library.get_size_guardrail_max_pct()
                            if ratio_pct < min_pct or ratio_pct > max_pct:
                                rejection_msg = f"Size guardrail REJECTED: {ratio_pct:.1f}% (allowed {min_pct}-{max_pct}%)"
                                self._log(rejection_msg)
                                self.current_task.task.success = False
                                # Write rejection reason into task log so retry logic can detect it
                                existing_log = self.current_task.task.log or ""
                                self.current_task.task.log = (existing_log + "\n" + rejection_msg).strip()
                                self.current_task.task.save()
                except (OSError, ZeroDivisionError, peewee.PeeweeException) as e:
                    self._log("Exception in size guardrail check", message2=str(e), level="warning")
                except Exception as e:
                    self._log(f"GuardrailRejectionError: {e}", level="warning")

            # Determine replacement policy (per-library with global fallback)
            try:
                library = Library(self.current_task.get_task_library_id())
                policy = library.get_replacement_policy()
            except (peewee.PeeweeException, AttributeError, KeyError, TypeError) as e:
                self._log("Could not determine replacement policy for library", message2=str(e), level="warning")
                policy = ""
            except Exception as e:
                self._log(f"PolicyResolutionError: {e}", level="warning")
                policy = ""
            if not policy:
                policy = "approval_required" if self.settings.get_approval_required() else "replace"

            if self.current_task.task.success:
                if policy == "approval_required":
                    self._stage_for_approval()
                elif policy == "keep_both":
                    self._finalize_local_task_keep_both()
                else:
                    self._finalize_local_task()
            else:
                # Check if this failure is eligible for retry (not a guardrail rejection)
                if self._attempt_retry():
                    return  # Task re-queued as pending with backoff; skip finalization
                self._finalize_local_task()
        else:
            self._finalize_remote_task()

    def _handle_approved_task(self):
        """Handle a task that was approved by the user — finalize file replacement from staging."""
        try:
            self._log(f"Finalizing approved task - {self.current_task.get_source_abspath()}")
        except (AttributeError, KeyError, TypeError) as e:
            self._log("Exception in fetching task absolute path", message2=str(e), level="exception")

        self._finalize_local_task()

    def _is_guardrail_rejection(self):
        """Check if the current task's failure was caused by a size guardrail rejection."""
        try:
            task_log = self.current_task.task.log or ""
            return "Size guardrail REJECTED" in task_log
        except Exception as e:
            self._log("Guardrail rejection check unavailable", message2=str(e), level="debug")
            return False

    def _attempt_retry(self):
        """
        Check if a failed task should be retried with exponential backoff.
        Returns True if the task was re-queued for retry, False otherwise.
        """
        try:
            # Don't retry guardrail rejections — those are intentional
            if self._is_guardrail_rejection():
                return False

            retry_count = self.current_task.task.retry_count or 0
            max_retries = self.current_task.task.max_retries or self.settings.get_default_max_retries()

            if retry_count >= max_retries:
                return False

            # Exponential backoff: 30s, 2min, 8min
            delay_seconds = 30 * (4**retry_count)
            deferred_until = datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)

            self.current_task.task.retry_count = retry_count + 1
            self.current_task.task.deferred_until = deferred_until
            self.current_task.task.status = "pending"
            self.current_task.task.success = None
            self.current_task.task.log = ""
            self.current_task.task.save()

            source_path = self.current_task.get_source_abspath()
            filename = os.path.basename(source_path)
            self._log(
                "Retrying task (attempt {}/{}) after {} - {}".format(
                    retry_count + 1, max_retries, deferred_until.strftime("%H:%M:%S"), source_path
                )
            )

            # Push a transient notification to the frontend via the frontend_message stream
            try:
                frontend_messages = FrontendPushMessages()
                msg_id = f"taskRetry_{self.current_task.get_task_id()}"
                frontend_messages.update(
                    {
                        "id": msg_id,
                        "type": "warning",
                        "code": "taskRetrying",
                        "message": "{} (attempt {}/{}, next at {})".format(
                            filename, retry_count + 1, max_retries, deferred_until.strftime("%H:%M:%S")
                        ),
                        "timeout": 15000,
                    }
                )
            except (AttributeError, KeyError, TypeError) as e:
                self._log("Failed to push retry notification", message2=str(e), level="debug")

            # Clean up cache but don't finalize — task goes back to pending
            cache_path = self.current_task.get_cache_path()
            if cache_path:
                self.__cleanup_cache_files(cache_path)

            return True
        except (AttributeError, TypeError, OSError) as e:
            self._log("Exception during retry attempt", message2=str(e), level="warning")
            return False
        except Exception as e:
            self._log("Unexpected error during retry attempt", message2=str(e), level="warning")
            return False

    def _stage_for_approval(self):
        """
        Stage the transcoded file for user review instead of replacing the original.
        Copies the cache file to the staging directory, computes quality metrics,
        and sets status to 'awaiting_approval'.
        """
        try:
            cache_path = self.current_task.get_cache_path()
            staging_dir = self.settings.get_staging_path()
            task_id = self.current_task.get_task_id()

            # Create a per-task staging subdirectory
            task_staging_dir = os.path.join(staging_dir, f"task_{task_id}")

            # Copy cache file to staging
            staged_filename = os.path.basename(cache_path)
            staged_path = os.path.join(task_staging_dir, staged_filename)
            disk_check = self._get_disk_space_guard().check_staging_capacity(cache_path, staged_path)
            if not disk_check.ok:
                self._defer_for_disk_pressure(disk_check, "processed")
                return
            os.makedirs(task_staging_dir, exist_ok=True)
            shutil.copy2(cache_path, staged_path)

            self._log(f"Staged transcoded file for approval: {cache_path} -> {staged_path}")
            self._record_approval_metadata(staged_path)

            # Compute quality metrics (non-blocking, best-effort)
            try:
                from compresso.libs.ffprobe_utils import compute_quality_scores

                source_path = self.current_task.get_source_abspath()
                scores = compute_quality_scores(source_path, staged_path, duration_limit=30)
                if scores:
                    self.current_task.task.vmaf_score = scores.get("vmaf_score")
                    self.current_task.task.ssim_score = scores.get("ssim_score")
                    self.current_task.task.save()
                    self._log(
                        "Quality scores computed - VMAF: {}, SSIM: {}".format(
                            scores.get("vmaf_score"), scores.get("ssim_score")
                        ),
                        level="debug",
                    )
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                self._log("Quality metric computation failed (non-fatal)", message2=str(e), level="warning")

            # Set the task status to awaiting_approval (keeps cache and task alive)
            self.current_task.set_status("awaiting_approval")

            # Dispatch approval_needed notification
            try:
                from compresso.libs.external_notifications import ExternalNotificationDispatcher

                source_data = self.current_task.get_source_data()
                context = {
                    "file_name": os.path.basename(source_data.get("abspath", "")),
                    "task_id": task_id,
                    "staged_path": staged_path,
                    "message": "A transcoded file is awaiting approval.",
                }
                # Include quality scores if computed
                try:
                    quality_scores = {}
                    if getattr(self.current_task.task, "vmaf_score", None) is not None:
                        quality_scores["vmaf"] = self.current_task.task.vmaf_score
                    if getattr(self.current_task.task, "ssim_score", None) is not None:
                        quality_scores["ssim"] = self.current_task.task.ssim_score
                    if quality_scores:
                        context["quality_scores"] = quality_scores
                except (AttributeError, TypeError):
                    pass
                ExternalNotificationDispatcher().dispatch("approval_needed", context)
            except (ImportError, AttributeError, TypeError):
                pass  # notification failure is non-fatal

        except (OSError, PermissionError, shutil.Error) as e:
            self._log("Exception in staging file for approval", message2=str(e), level="exception")
            # Fall back to normal processing on staging failure
            self._finalize_local_task()

    def _record_approval_metadata(self, staged_path):
        """Persist approval queue metadata while the staged file is fresh."""
        try:
            source_meta = extract_media_metadata(self.current_task.get_source_abspath())
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            self._log("Failed to extract source approval metadata", message2=str(e), level="debug")
            source_meta = {}
        try:
            staged_meta = extract_media_metadata(staged_path)
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            self._log("Failed to extract staged approval metadata", message2=str(e), level="debug")
            staged_meta = {}

        try:
            self.current_task.task.source_codec = source_meta.get("codec", "")
            self.current_task.task.staged_codec = staged_meta.get("codec", "")
            self.current_task.task.staged_size = os.path.getsize(staged_path) if os.path.exists(staged_path) else 0
            self.current_task.task.metadata_updated_at = datetime.datetime.now()
            self.current_task.task.save()
        except (OSError, AttributeError, TypeError) as e:
            self._log("Failed to persist approval metadata", message2=str(e), level="debug")

    def _finalize_local_task(self):
        """Run the standard local task postprocessing: file move, history, metadata, cleanup."""
        if not self._has_finalization_capacity():
            return
        self._finalize_local_task_with_capacity()

    def _finalize_local_task_with_capacity(self):
        """Finalize a local task after disk-capacity preflight succeeds."""
        if not self._postprocess_local_file_safely():
            return
        try:
            history_written = self.write_history_log()
        except (OSError, AttributeError, TypeError) as e:
            self._log("Exception in writing history log", message2=str(e), level="exception")
            self._defer_postprocess_failure(str(e))
            return
        except Exception as e:
            self._log(f"TaskMetadataError in history log: {e}", level="exception")
            self._defer_postprocess_failure(str(e))
            return
        if history_written is False:
            message = "history persistence returned false"
            self._log("Failed to write history log", message2=message, level="error")
            self._defer_postprocess_failure(message)
            return
        self._mark_finalization_phase("history_committed")
        try:
            self.commit_task_metadata()
        except (OSError, AttributeError, TypeError) as e:
            self._log("Exception in committing task metadata", message2=str(e), level="exception")
            self._defer_postprocess_failure(str(e))
            return
        except Exception as e:
            self._log(f"TaskMetadataError in commit: {e}", level="exception")
            self._defer_postprocess_failure(str(e))
            return
        self._mark_finalization_phase("metadata_committed")
        try:
            # Clean up the staging directory for this task if it exists
            self._cleanup_staging_files()
            # Remove file from task queue
            self.current_task.delete()
        except (OSError, AttributeError, TypeError) as e:
            self._log("Exception in removing task from task list", message2=str(e), level="exception")
            self._defer_postprocess_failure(str(e))
            return

        self._mark_finalization_phase("task_deleted")
        self._finalize_file_operation_journal(True)

        # Dispatch external notification for task completion or failure
        try:
            from compresso.libs.external_notifications import ExternalNotificationDispatcher

            dispatcher = ExternalNotificationDispatcher()
            source_data = self.current_task.get_source_data()
            cache_path = self.current_task.get_cache_path()

            # Source size comes from the task record (the source_data/dest_data dicts
            # only carry abspath/basename, never a "size" key).
            source_size = self.current_task.task.source_size or 0
            # Destination size is the size of the encoded output in the cache path.
            destination_size = None
            try:
                if cache_path and os.path.exists(cache_path):
                    destination_size = os.path.getsize(cache_path)
            except OSError:
                destination_size = None

            context = {
                "file_name": os.path.basename(source_data.get("abspath", "")),
                "source_size": source_size or None,
                "destination_size": destination_size,
            }
            # Include codec from destination metadata if available
            try:
                if cache_path and os.path.exists(cache_path):
                    meta = extract_media_metadata(cache_path)
                    context["codec"] = meta.get("codec", "")
            except (subprocess.SubprocessError, OSError, ValueError):
                pass
            # Include size savings
            try:
                if source_size > 0 and destination_size:
                    saved = source_size - destination_size
                    pct = (saved / source_size) * 100
                    context["size_saved"] = f"{saved / (1024 * 1024):.1f} MB ({pct:.0f}%)"
            except (AttributeError, TypeError, ZeroDivisionError):
                pass
            # Include quality scores if available
            try:
                scores = {}
                if getattr(self.current_task.task, "vmaf_score", None) is not None:
                    scores["vmaf"] = self.current_task.task.vmaf_score
                if getattr(self.current_task.task, "ssim_score", None) is not None:
                    scores["ssim"] = self.current_task.task.ssim_score
                if scores:
                    context["quality_scores"] = scores
            except (AttributeError, TypeError):
                pass
            if self.current_task.task.success:
                dispatcher.dispatch("task_completed", context)
            else:
                dispatcher.dispatch("task_failed", context)
        except (ImportError, AttributeError, TypeError):
            pass  # notification failure is non-fatal

    def _postprocess_local_file_safely(self):
        """Run the destructive file phase and defer all later finalization on failure."""
        resumed = FileOperationTracker.resume_committed(
            self._get_file_operation_journal_dir(),
            task_id=self.current_task.get_task_id(),
            logger=self.logger,
        )
        if resumed is not None:
            self._file_operation_tracker = resumed
            self._last_destination_files = list(resumed._created_paths)
            self._log(
                f"Resuming task finalization from phase {resumed.finalization_phase or 'file_committed'}",
                level="warning",
            )
            return True
        try:
            if self.post_process_file() is False:
                self._defer_postprocess_failure("file movement did not complete")
                return False
        except (OSError, PermissionError, shutil.Error) as e:
            self._log("Exception in post-processing local task file", message2=str(e), level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        except Exception as e:
            self._log(f"FileOperationError: {e}", level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        return True

    def _get_file_operation_journal_dir(self):
        config_path = self.settings.get_config_path()
        return os.path.join(config_path, "recovery", "file_operations") if isinstance(config_path, str) else None

    def _mark_finalization_phase(self, phase):
        if self._file_operation_tracker is not None:
            self._file_operation_tracker.mark_finalization_phase(phase)

    def _defer_postprocess_failure(self, reason):
        """Keep the task and encoded cache available for a safe later retry."""
        try:
            retry_seconds = max(1, int(self.settings.get_disk_space_retry_seconds()))
        except (AttributeError, TypeError, ValueError):
            retry_seconds = 60
        self.current_task.task.deferred_until = datetime.datetime.now() + datetime.timedelta(seconds=retry_seconds)
        self.current_task.task.save()
        self._log(
            f"POSTPROCESS_DEFERRED task_id={self.current_task.get_task_id()} retry_seconds={retry_seconds} reason={reason}",
            level="error",
        )

    def _get_disk_space_guard(self):
        if self._disk_space_guard is None:
            self._disk_space_guard = DiskSpaceGuard(self.settings)
        return self._disk_space_guard

    def _has_finalization_capacity(self):
        if not self.current_task.task.success:
            return True
        source_path = self.current_task.get_source_abspath()
        cache_path = self.current_task.get_cache_path()
        destination_path = self.current_task.get_destination_data()["abspath"]
        disk_check = self._get_disk_space_guard().check_finalization_capacity(
            source_path,
            cache_path,
            destination_path,
        )
        if not disk_check.ok:
            self._defer_for_disk_pressure(disk_check, self.current_task.task.status)
            return False
        if self.current_task.task.deferred_until is not None:
            self.current_task.task.deferred_until = None
            self.current_task.task.save()
        return True

    def _defer_for_disk_pressure(self, disk_check, retry_status):
        retry_seconds = self.settings.get_disk_space_retry_seconds()
        self.current_task.task.status = retry_status
        self.current_task.task.deferred_until = datetime.datetime.now() + datetime.timedelta(seconds=retry_seconds)
        self.current_task.task.save()
        self._safety_event_recorder(
            self.settings,
            None,
            "disk-reserve",
            "Destination disk free space is below the safe file-operation reserve",
            phase=disk_check.phase,
            path=disk_check.path,
            free_bytes=disk_check.free_bytes,
            required_bytes=disk_check.required_bytes,
        )
        self._log(
            f"DISK_PRESSURE_DEFERRED phase={disk_check.phase} path={disk_check.path} "
            f"free_bytes={disk_check.free_bytes} required_bytes={disk_check.required_bytes} "
            f"retry_seconds={retry_seconds}",
            level="warning",
        )

    def _finalize_file_operation_journal(self, task_deleted):
        if task_deleted and self._file_operation_tracker is not None:
            if self._file_operation_tracker._state != "committed":
                self._log(
                    f"Retaining file-operation journal in state {self._file_operation_tracker._state}",
                    level="warning",
                )
                self._file_operation_tracker = None
                return
            try:
                self._file_operation_tracker.finalize()
            except OSError as e:
                self._log("Failed to finalize file-operation recovery journal", message2=str(e), level="warning")
            finally:
                self._file_operation_tracker = None

    def _finalize_local_task_keep_both(self):
        """Finalize task but keep original — save output alongside with codec suffix."""
        try:
            dest_data = self.current_task.get_destination_data()
            source_data = self.current_task.get_source_data()
            if dest_data["abspath"] == source_data["abspath"]:
                # Same filename — add codec suffix to avoid overwriting
                base, ext = os.path.splitext(dest_data["abspath"])
                try:
                    meta = extract_media_metadata(self.current_task.get_cache_path())
                    codec = meta.get("codec", "transcoded")
                except (subprocess.SubprocessError, OSError, ValueError) as e:
                    self._log("Failed to extract codec from cache path", message2=str(e), level="warning")
                    codec = "transcoded"
                except Exception as e:
                    self._log(f"QualityMetricsError extracting codec: {e}", level="warning")
                    codec = "transcoded"
                new_path = f"{base}.{codec}{ext}"
                counter = 1
                while os.path.exists(new_path) and counter <= 100:
                    new_path = f"{base}.{codec}.{counter}{ext}"
                    counter += 1
                self.current_task.set_destination_path(new_path)
        except (OSError, AttributeError, KeyError, TypeError) as e:
            self._log("Exception in keep_both path adjustment", message2=str(e), level="warning")
        self._finalize_local_task()

    def _finalize_remote_task(self):
        """Finalize a remote task only after its file and history are durable."""
        original_path = self.current_task.get_source_abspath()
        try:
            final_path = self.post_process_remote_file()
            if not final_path:
                self._defer_postprocess_failure("remote file movement did not complete")
                return False
        except (OSError, PermissionError, shutil.Error) as e:
            self._log("Exception in post-processing remote task file", message2=str(e), level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        except Exception as e:
            self._log(f"FileOperationError in remote task: {e}", level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        try:
            self.dump_history_log(destination_path=final_path)
        except (OSError, AttributeError, TypeError) as e:
            self._log("Exception in dumping history log for remote task", message2=str(e), level="exception")
            self._discard_prepared_remote_output(final_path, original_path)
            self._defer_postprocess_failure(str(e))
            return False
        except Exception as e:
            self._log(f"TaskMetadataError in remote history: {e}", level="exception")
            self._discard_prepared_remote_output(final_path, original_path)
            self._defer_postprocess_failure(str(e))
            return False
        try:
            self.current_task.modify_path(final_path)
            self.current_task.set_status("complete")
        except (AttributeError, TypeError) as e:
            self._log("Exception in marking remote task as complete", message2=str(e), level="exception")
            self._rollback_prepared_remote_output(final_path, original_path)
            self._defer_postprocess_failure(str(e))
            return False
        except Exception as e:
            self._log(f"TaskMetadataError marking complete: {e}", level="exception")
            self._rollback_prepared_remote_output(final_path, original_path)
            self._defer_postprocess_failure(str(e))
            return False

        # The encoded cache remains available until the file, history, path, and
        # completion state are all durable. Cleanup is best-effort after success.
        self.__cleanup_cache_files(self.current_task.get_cache_path())
        return True

    def _rollback_prepared_remote_output(self, final_path, original_path):
        """Restore task identity before removing a prepared remote copy."""
        try:
            self.current_task.modify_path(original_path)
        except Exception as error:
            self._log("Unable to roll back remote task path", message2=str(error), level="exception")
            return False
        self._discard_prepared_remote_output(final_path, original_path)
        return True

    def _discard_prepared_remote_output(self, final_path, original_path):
        """Remove a failed prepared copy while retaining the encoded cache."""
        if not final_path or os.path.realpath(final_path) == os.path.realpath(original_path):
            return
        final_directory = os.path.dirname(final_path)
        if os.path.basename(final_directory).startswith("compresso_remote_pending_library-"):
            shutil.rmtree(final_directory, ignore_errors=True)
            return
        with contextlib.suppress(FileNotFoundError, OSError):
            os.remove(final_path)

    def _cleanup_staging_files(self):
        """Remove the staging directory for the current task if it exists."""
        try:
            task_id = self.current_task.get_task_id()
            staging_dir = self.settings.get_staging_path()
            task_staging_dir = os.path.join(staging_dir, f"task_{task_id}")
            if os.path.exists(task_staging_dir):
                self._log(f"Removing staging directory '{task_staging_dir}'")
                shutil.rmtree(task_staging_dir)
        except (OSError, PermissionError, shutil.Error) as e:
            self._log("Exception while cleaning up staging files", message2=str(e), level="warning")

    def system_configuration_is_valid(self):
        """
        Check and ensure the system configuration is correct for running

        :return:
        """
        plugin_handler = PluginsHandler()
        return not plugin_handler.get_incompatible_enabled_plugins()

    def post_process_file(self):
        # Init plugins handler
        plugin_handler = PluginsHandler()

        # Read current task data
        # task_data = self.current_task.get_task_data()
        library_id = self.current_task.get_task_library_id()
        cache_path = self.current_task.get_cache_path()
        source_data = self.current_task.get_source_data()
        destination_data = self.current_task.get_destination_data()
        # Move file back to original folder and remove source
        file_move_processes_success = True
        # Create a list for filling with destination paths
        destination_files = []
        # Create a tracker for safe file operations with rollback support
        journal_dir = self._get_file_operation_journal_dir()
        tracker = FileOperationTracker(
            self.logger,
            journal_dir=journal_dir,
            operation_id=f"task-{self.current_task.get_task_id()}",
            task_id=self.current_task.get_task_id(),
            failure_callback=lambda **details: self._safety_event_recorder(
                self.settings,
                None,
                "rollback-failure",
                "A destructive file operation could not be rolled back",
                **details,
            ),
        )
        self._file_operation_tracker = tracker
        if self.current_task.task.success:
            # Run a postprocess file movement on the cache file for each plugin that configures it

            # Fetch all 'postprocessor.file_move' plugin modules
            plugin_modules = plugin_handler.get_enabled_plugin_modules_by_type(
                "postprocessor.file_move", library_id=library_id
            )

            # Check if the source file needs to be removed by default (only if it does not match the destination file)
            remove_source_file = False
            if source_data["abspath"] != destination_data["abspath"]:
                remove_source_file = True

            # Set initial data (some fields will be overwritten further down)
            # - 'library_id'                - The library ID for this task
            # - 'source_data'               - Dictionary of data pertaining to the source file
            # - 'remove_source_file'    - True to remove the original file
            #                             (default is True if file name has changed)
            # - 'copy_file'             - True to run a plugin initiated file copy
            #                             (default is False unless the plugin says otherwise)
            # - 'file_in'               - Source path to copy from (if 'copy_file' is True)
            # - 'file_out'              - Destination path to copy to (if 'copy_file' is True)
            # - 'run_default_file_copy' - Prevent the final Compresso post-process
            #                             file movement (if different from the original file name)
            data = {
                "library_id": library_id,
                "task_id": self.current_task.get_task_id(),
                "source_data": None,
                "remove_source_file": remove_source_file,
                "copy_file": None,
                "file_in": None,
                "file_out": None,
                "run_default_file_copy": True,
            }

            for plugin_module in plugin_modules:
                # Always set source_data to the original file's source_data
                data["source_data"] = source_data
                # Always set copy_file to False
                data["copy_file"] = False
                # Always set file in to cache path
                data["file_in"] = cache_path
                # Always set file out to destination data absolute path
                data["file_out"] = destination_data.get("abspath")

                # Run plugin to update data
                if not plugin_handler.exec_plugin_runner(data, plugin_module.get("plugin_id"), "postprocessor.file_move"):
                    # Do not continue with this plugin module's loop
                    continue

                if data.get("copy_file"):
                    # Copy the file
                    file_in = os.path.abspath(data.get("file_in"))
                    file_out = os.path.abspath(data.get("file_out"))
                    if not self.__copy_file(
                        file_in, file_out, destination_files, plugin_module.get("plugin_id"), tracker=tracker
                    ):
                        file_move_processes_success = False
                else:
                    self._log(f"Plugin did not request a file copy ({plugin_module.get('plugin_id')})", level="debug")

            # Compresso's default file movement process
            # Only carry out final post-processor file moments if all others were successful
            if file_move_processes_success and data.get("run_default_file_copy"):
                # Run the default post-process file movement.
                # This will always move the file back to the original location.
                # If that original location is the same file name, it will overwrite the original file.
                if destination_data.get("abspath") == source_data.get("abspath"):
                    # Only run the final file copy to overwrite the source file if the remove_source_file flag was never set
                    # The remove_source_file flag will remove the source file in later lines after this copy operation,
                    #   so if we did copy the file here, it would be a waste of time
                    if not data.get("remove_source_file") and not self.__copy_file(
                        cache_path,
                        destination_data.get("abspath"),
                        destination_files,
                        "DEFAULT",
                        move=True,
                        tracker=tracker,
                    ):
                        file_move_processes_success = False
                elif not self.__copy_file(
                    cache_path, destination_data.get("abspath"), destination_files, "DEFAULT", move=True, tracker=tracker
                ):
                    file_move_processes_success = False

            # Source file removal process
            # Only run if all final post-processor file moments were successful
            if file_move_processes_success and data.get("remove_source_file"):
                # Only carry out a source removal if the file exists and the final copy was also successful
                if file_move_processes_success and os.path.exists(source_data.get("abspath")):
                    self._log(f"Removing source: {source_data.get('abspath')}")
                    try:
                        tracker.safe_remove(source_data.get("abspath"))
                    except (OSError, PermissionError, shutil.Error) as e:
                        self._log("Failed to safely remove source file", message2=str(e), level="error")
                        file_move_processes_success = False
                else:
                    self._log(
                        "Keeping source file '{}'. Not all postprocessor file movement functions completed.".format(
                            source_data.get("abspath")
                        ),
                        level="warning",
                    )

            # Commit or rollback tracked file operations
            if file_move_processes_success:
                tracker.commit()
                tracker.mark_finalization_phase("file_committed")
            else:
                self._log("Rolling back all tracked file operations due to failures", level="warning")
                tracker.rollback()

            # Log a final error if not all file moments were successful
            if not file_move_processes_success:
                self._log(
                    f"Error while running postprocessor file movement on file '{cache_path}'."
                    " Not all postprocessor file movement functions completed.",
                    level="error",
                )

        else:
            self._log(f"Skipping file movement post-processor as the task was not successful '{cache_path}'", level="warning")

        # Fetch all 'postprocessor.task_result' plugin modules
        plugin_modules = plugin_handler.get_enabled_plugin_modules_by_type("postprocessor.task_result", library_id=library_id)

        for plugin_module in plugin_modules:
            data = {
                "library_id": library_id,
                "task_id": self.current_task.get_task_id(),
                "task_type": self.current_task.get_task_type(),
                "final_cache_path": cache_path,
                "task_processing_success": self.current_task.get_task_success(),
                "file_move_processes_success": file_move_processes_success,
                "destination_files": destination_files,
                "source_data": source_data,
                "start_time": self.current_task.get_start_time(),
                "finish_time": self.current_task.get_finish_time(),
            }

            # Run plugin to update data
            if not plugin_handler.exec_plugin_runner(data, plugin_module.get("plugin_id"), "postprocessor.task_result"):
                # Do not continue with this plugin module's loop
                continue

        # Retain a valid encode when movement failed so the postprocessor can
        # retry without destroying the only completed output.
        if file_move_processes_success or not self.current_task.task.success:
            self.__cleanup_cache_files(cache_path)
        self._last_destination_files = destination_files
        return file_move_processes_success

    def post_process_remote_file(self):
        """
        Copy a remote task's encoded cache to its pending final location.

        The cache is deliberately retained until the caller has durably written
        history and marked the task complete. The returned path is therefore a
        prepared result, not permission to clean up the cache yet.
        """
        cache_path = self.current_task.get_cache_path()
        source_data = self.current_task.get_source_data()
        destination_data = self.current_task.get_destination_data()
        def_cache_path = self.settings.get_cache_path()
        remove_source_file = self._path_is_within(source_data.get("abspath"), def_cache_path)

        self._log(f"Cache path: {def_cache_path}", level="debug")
        self._log(
            "Remote source: {}, destination file: {}.".format(
                source_data["abspath"],
                destination_data["abspath"],
            ),
            level="debug",
        )
        self._log(f"Task cache path: {cache_path}", level="debug")

        if not os.path.exists(cache_path):
            self._log(f"Final cache file '{cache_path}' does not exist!", level="warning")
            return False

        # Remove a temporary downloaded source only after confirming that the
        # completed encoded cache exists and can be retained for recovery.
        if os.path.exists(source_data.get("abspath")) and remove_source_file:
            self._log(f"Removing remote source: {source_data.get('abspath')}")
            os.remove(source_data.get("abspath"))
        elif os.path.exists(source_data.get("abspath")) and not remove_source_file:
            self._log(f"Keep remote source: {source_data.get('abspath')}, remote file source is in library and not cache.")
        else:
            self._log(f"Remote source file '{source_data.get('abspath')}' does not exist!", level="warning")

        random_string = f"{common.random_string()}-{int(time.time())}"
        library_tdir = os.path.join(
            os.path.dirname(source_data.get("abspath")), "compresso_remote_pending_library-" + random_string
        )
        cache_tdir = os.path.join(def_cache_path, "compresso_remote_pending_library-" + random_string)

        if remove_source_file:
            if not self.__copy_file(cache_path, destination_data.get("abspath"), [], "DEFAULT", move=False):
                return False
            return destination_data.get("abspath")

        final_directory = library_tdir
        try:
            os.mkdir(library_tdir)
            final_path = os.path.join(library_tdir, os.path.basename(cache_path))
            if not self.__copy_file(cache_path, final_path, [], "DEFAULT", move=False):
                raise OSError("Failed to copy back to network share")
            return final_path
        except (OSError, PermissionError, shutil.Error):
            final_directory = cache_tdir
            os.mkdir(cache_tdir)
            final_path = os.path.join(cache_tdir, os.path.basename(cache_path))
            if not self.__copy_file(cache_path, final_path, [], "DEFAULT", move=False):
                return False
            return final_path
        finally:
            self._log(f"tdir: {final_directory}", level="debug")

    @staticmethod
    def _path_is_within(path, directory):
        if not path or not directory:
            return False
        normalized_path = os.path.normcase(os.path.realpath(path))
        normalized_directory = os.path.normcase(os.path.realpath(directory))
        try:
            return os.path.commonpath([normalized_directory, normalized_path]) == normalized_directory
        except ValueError:
            return False

    def __cleanup_cache_files(self, cache_path):
        """
        Remove cache files and the cache directory
        This ensures we are not simply blindly removing a whole directory.
        It ensures were are in-fact only deleting this task's cache files.

        :param cache_path:
        :return:
        """
        task_cache_directory = os.path.dirname(cache_path)
        if os.path.exists(task_cache_directory) and "compresso_file_conversion" in task_cache_directory:
            self._log(f"Removing task cache directory '{task_cache_directory}'")
            try:
                shutil.rmtree(task_cache_directory)
            except (OSError, PermissionError, shutil.Error) as e:
                self._log(f"Exception while clearing cache path '{str(e)}'", level="error")

    def __copy_file(self, file_in, file_out, destination_files, plugin_id, move=False, tracker=None):
        if move:
            self._log(f"Move file triggered by ({plugin_id}) {file_in} --> {file_out}")
        else:
            self._log(f"Copy file triggered by ({plugin_id}) {file_in} --> {file_out}")

        file_move_processes_success = True
        # Use a '.part' suffix for the file movement, then rename it after. Defined
        # up-front so a partial failure can clean it up rather than orphaning it next
        # to the destination file.
        part_file_out = os.path.join(f"{file_out}.compresso.part")
        try:
            # Ensure the src and dst are not the same file
            if os.path.exists(file_out) and os.path.samefile(file_in, file_out):
                self._log(
                    f"The file_in and file_out path are the same file. Nothing will be done! '{file_in}'", level="warning"
                )
                return False

            # Get a checksum prior to copy
            if not os.path.exists(file_in):
                self._log(f"The file_in path does not exist! '{file_in}'", level="warning")
                self.event.wait(1)
            self._log(f"Fetching checksum of source file '{file_in}'.", level="debug")

            # Carry out the file movement
            if move:
                self._log(f"Moving file '{file_in}' --> '{part_file_out}'.", level="debug")
                if os.path.exists(part_file_out):
                    os.remove(part_file_out)
                shutil.move(file_in, part_file_out, copy_function=shutil.copyfile)
            else:
                self._log(f"Copying file '{file_in}' --> '{part_file_out}'.", level="debug")
                shutil.copyfile(file_in, part_file_out)

            # Remove dest file if it already exists (required only for moves)
            if os.path.exists(file_out):
                self._log(f"The file_out path already exists. Removing file '{file_out}'", level="debug")
                if tracker:
                    tracker.safe_remove(file_out)
                else:
                    os.remove(file_out)

            # Move file from part to final destination
            self._log(f"Renaming file '{part_file_out}' --> '{file_out}'.", level="debug")
            if tracker:
                tracker.record_created(file_out)
            shutil.move(part_file_out, file_out, copy_function=shutil.copyfile)
            # Write final path to destination_files list
            destination_files.append(file_out)
            # Mark move process a success
            return True
        except (OSError, PermissionError, shutil.SameFileError, shutil.Error) as e:
            self.logger.error("POSTPROCESS_FILE_COPY_FAILED source=%s dest=%s", file_in, file_out)
            self._log(f"Exception while copying file {file_in} to {file_out}:", message2=str(e), level="exception")
            if tracker:
                self._log("Rolling back file operations due to copy failure", level="warning")
                tracker.rollback()
            # Remove the staging '.part' file if it was left behind by a failed
            # move/rename so it is not orphaned next to the destination file.
            if os.path.exists(part_file_out):
                try:
                    if move and not os.path.exists(file_in):
                        shutil.copyfile(part_file_out, file_in)
                    os.remove(part_file_out)
                except OSError as cleanup_error:
                    self._log(f"Failed to remove staging file '{part_file_out}'", message2=str(cleanup_error), level="warning")
            file_move_processes_success = False

        return file_move_processes_success

    def write_history_log(self):
        """
        Record task history

        :return:
        """
        self._log("Writing task history log.", level="debug")
        history_logging = history.History()
        task_dump = self.current_task.task_dump()
        destination_data = self.current_task.get_destination_data()
        source_data = self.current_task.get_source_data()

        # If task fails, the add a notification that a task has failed
        if not self.current_task.task.success:
            notifications = Notifications()
            notifications.add(
                {
                    "uuid": "newFailedTask",
                    "type": "error",
                    "icon": "report",
                    "label": "failedTaskLabel",
                    "message": "You have a new failed task in your completed tasks list",
                    "navigation": {
                        "push": "/ui/dashboard",
                        "events": [
                            "completedTasksShowFailed",
                        ],
                    },
                }
            )

        self._log_completed_task_data(task_dump, source_data, destination_data)

        # Capture destination file size for compression stats
        destination_size = 0
        dest_path = ""
        if task_dump.get("task_success", False) and destination_data:
            dest_path = destination_data.get("abspath", "")
            if dest_path and os.path.exists(dest_path):
                try:
                    destination_size = os.path.getsize(dest_path)
                except OSError:
                    self.logger.warning("POSTPROCESS_DESTINATION_SIZE_UNAVAILABLE path=%s", dest_path)
                    self._log(f"Could not get destination file size for '{dest_path}'", level="warning")

        # Extract media metadata for compression stats (codec, resolution, container)
        # Always extract source metadata (even on failure, for stats tracking)
        source_meta = {}
        dest_meta = {}
        source_abspath = source_data.get("abspath", "") if source_data else ""
        if source_abspath and os.path.exists(source_abspath):
            try:
                source_meta = extract_media_metadata(source_abspath)
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                self.logger.warning("POSTPROCESS_SOURCE_METADATA_UNAVAILABLE path=%s", source_abspath)
                self._log(f"Could not extract source metadata: {e}", level="warning")
        # Destination metadata only on success
        if task_dump.get("task_success", False) and dest_path and os.path.exists(dest_path):
            try:
                dest_meta = extract_media_metadata(dest_path)
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                self._log(f"Could not extract destination metadata: {e}", level="debug")

        # Extract source duration for encoding speed context
        source_duration_seconds = 0
        with contextlib.suppress(TypeError, ValueError):
            source_duration_seconds = float(source_meta.get("duration", 0))

        history_saved = history_logging.save_task_history(
            {
                "task_label": task_dump.get("task_label", ""),
                "abspath": task_dump.get("abspath", ""),
                "task_success": task_dump.get("task_success", False),
                "start_time": task_dump.get("start_time", ""),
                "finish_time": task_dump.get("finish_time", ""),
                "processed_by_worker": task_dump.get("processed_by_worker", ""),
                "log": task_dump.get("log", ""),
                "source_size": task_dump.get("source_size", 0),
                "destination_size": destination_size,
                "library_id": task_dump.get("library_id", 1),
                "source_codec": source_meta.get("codec", ""),
                "destination_codec": dest_meta.get("codec", ""),
                "source_resolution": source_meta.get("resolution", ""),
                "source_container": source_meta.get("container", ""),
                "destination_container": dest_meta.get("container", ""),
                "encoding_duration_seconds": task_dump.get("encoding_duration_seconds", 0),
                "avg_encoding_fps": task_dump.get("avg_encoding_fps", 0),
                "source_duration_seconds": source_duration_seconds,
                "encoding_speed_ratio": task_dump.get("encoding_speed_ratio", 0),
            }
        )

        if not history_saved:
            return False

        # Bump analysis cache version so frontend knows estimates may have changed
        try:
            from compresso.libs.unmodels import LibraryAnalysisCache

            lib_id = task_dump.get("library_id", 1)
            cache_entry = LibraryAnalysisCache.get_or_none(LibraryAnalysisCache.library_id == lib_id)
            if cache_entry:
                cache_entry.version += 1
                cache_entry.save()
        except (ImportError, AttributeError, TypeError, peewee.PeeweeException) as e:
            self.logger.debug("Failed to bump analysis cache version: %s", e)

        # Execute event plugin runners
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type(
            "events.postprocessor_complete",
            {
                "library_id": self.current_task.get_task_library_id(),
                "task_id": self.current_task.get_task_id(),
                "task_type": self.current_task.get_task_type(),
                "source_data": self.current_task.get_source_data(),
                "destination_data": self.current_task.get_destination_data(),
                "task_success": task_dump.get("task_success", False),
                "start_time": task_dump.get("start_time", ""),
                "finish_time": task_dump.get("finish_time", ""),
                "processed_by_worker": task_dump.get("processed_by_worker", ""),
                "log": task_dump.get("log", ""),
            },
        )
        return True

    def commit_task_metadata(self):
        """
        Commit task metadata after all postprocessor runners have finished.
        """
        source_data = self.current_task.get_source_data()
        destination_data = self.current_task.get_destination_data()
        task_success = self.current_task.get_task_success()
        destination_files = list(self._last_destination_files or [])
        if not destination_files and destination_data:
            destination_files = [destination_data.get("abspath")]
        committed = CompressoFileMetadata.commit_task(
            task_id=self.current_task.get_task_id(),
            task_success=task_success,
            source_path=source_data.get("abspath"),
            destination_paths=destination_files,
        )
        if committed:
            self._log(f"Committed file metadata entries: {committed}", level="debug")
        return committed

    def dump_history_log(self, destination_path=None):
        self._log("Dumping remote task history log.", level="debug")
        task_dump = self.current_task.task_dump()
        destination_path = destination_path or self.current_task.get_destination_data().get("abspath")
        task_dump["abspath"] = destination_path

        # Dump history log & task state as metadata in the file's path
        tasks_data_file = os.path.join(os.path.dirname(destination_path), "data.json")
        task_state = TaskDataStore.export_task_state(self.current_task.get_task_id())
        checksum = None
        if task_dump.get("task_success", False):
            checksum = file_sha256(destination_path)
        result = common.json_dump_to_file(
            {
                "task_label": task_dump.get("task_label", ""),
                "abspath": task_dump.get("abspath", ""),
                "task_success": task_dump.get("task_success", False),
                "start_time": task_dump.get("start_time", ""),
                "finish_time": task_dump.get("finish_time", ""),
                "processed_by_worker": task_dump.get("processed_by_worker", ""),
                "log": task_dump.get("log", ""),
                "checksum": checksum,
                "task_state": task_state,
            },
            tasks_data_file,
        )
        if not result["success"]:
            for message in result["errors"]:
                self._log("Exception:", message2=str(message), level="exception")
            raise Exception("Exception in dumping completed task data to file")

    def _log_completed_task_data(self, task_dump, source_data, destination_data):
        status = "success" if task_dump.get("task_success", False) else "failed"
        start_time = task_dump.get("start_time", "")
        finish_time = task_dump.get("finish_time", "")
        command_error_log_tail = ""
        if status != "success":
            task_log = task_dump.get("log", "")
            if task_log:
                command_error_log_tail = "\n".join(task_log.splitlines()[-20:])
        try:
            library_id = self.current_task.get_task_library_id()
            library_name = self.current_task.get_task_library_name()
        except (AttributeError, KeyError, TypeError):
            library_id = None
            library_name = None

        CompressoLogging.log_data(
            "completed_task",
            data_search_key=f"{library_id} | {finish_time} | {source_data.get('abspath', '')}",
            task_id=self.current_task.get_task_id(),
            task_type=self.current_task.get_task_type(),
            library_id=library_id,
            library_name=library_name,
            status=status,
            start_time=start_time,
            finish_time=finish_time,
            source_file=source_data.get("basename", ""),
            source_path=source_data.get("abspath", ""),
            dest_file=destination_data.get("basename", ""),
            dest_path=destination_data.get("abspath", ""),
            command_error_log_tail=command_error_log_tail,
        )


# Backward-compatible imports
from compresso.libs.file_operation_tracker import FileOperationTracker, PostProcessError  # noqa: E402, F811, F401
