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
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

import peewee

from compresso import config
from compresso.libs import common, history
from compresso.libs.disk_space_guard import DiskSpaceCheck, DiskSpaceGuard
from compresso.libs.ffprobe_utils import MediaMetadata, extract_media_metadata
from compresso.libs.file_operation_tracker import (
    FileOperationTracker,
    FinalizationPhase,
    PostProcessError,
)
from compresso.libs.frontend_push_messages import FrontendPushMessages
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.metadata import CompressoFileMetadata
from compresso.libs.notifications import Notifications
from compresso.libs.plugins import PluginsHandler
from compresso.libs.resumable_transfer import file_sha256
from compresso.libs.safety_state import SafetyForeman, record_safety_event
from compresso.libs.task import Task, TaskDataStore, TaskPathData
from compresso.libs.taskqueue import TaskQueue
from compresso.libs.thread_health import ThreadHealthMixin
from compresso.libs.unmodels.tasks import Tasks


@dataclass(frozen=True)
class PostprocessCompletionTransition:
    commit_journal: bool
    rollback_journal: bool
    cleanup_cache: bool
    succeeded: bool


class SafetyEventRecorder(Protocol):
    def __call__(
        self,
        settings: config.Config,
        foreman: SafetyForeman | None,
        code: str,
        message: str,
        **details: object,
    ) -> dict[str, object]: ...


type FinalizationEvent = Literal["history_persisted", "metadata_persisted", "task_removed"]


FINALIZATION_PHASE_ORDER: dict[FinalizationPhase | None, int] = {
    None: 0,
    "file_committed": 0,
    "history_committed": 1,
    "metadata_committed": 2,
    "task_deleted": 3,
}


def _empty_media_metadata() -> MediaMetadata:
    return MediaMetadata(codec="", resolution="", container="", duration=0.0, bitrate_mbps=0.0)


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

    def __init__(
        self,
        data_queues: Mapping[str, object],
        task_queue: TaskQueue,
        event: threading.Event,
    ) -> None:
        super().__init__(name="PostProcessor")
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)
        self.event = event
        self.data_queues = data_queues
        self.settings = config.Config()
        self.task_queue = task_queue
        self.abort_flag = threading.Event()
        self.current_task: Task | None = None
        self._last_destination_files: list[str] = []
        self._keep_source_file = False
        self._file_operation_tracker: FileOperationTracker | None = None
        self._disk_space_guard: DiskSpaceGuard | None = None
        self._safety_event_recorder: SafetyEventRecorder = record_safety_event
        self.ffmpeg: object | None = None
        self.abort_flag.clear()
        self._init_thread_health()

    def _log(self, message: object, message2: object = "", level: str = "info") -> None:
        message = common.format_message(message, message2)
        getattr(self.logger, level)(message)

    def _require_current_task(self) -> Task:
        current_task = self.current_task
        if current_task is None:
            raise RuntimeError("postprocessor has no current task")
        return current_task

    @property
    def task(self) -> Task:
        """Return the task owned by the currently executing lifecycle step."""
        return self._require_current_task()

    @property
    def model(self) -> Tasks:
        """Return the hydrated database row owned by the current task."""
        task_model = self.task.task
        if task_model is None:
            raise RuntimeError("postprocessor current task is not loaded")
        return task_model

    def stop(self) -> None:
        self.abort_flag.set()

    def run(self) -> None:
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

    def _process_available_tasks(self) -> None:
        if not self.system_configuration_is_valid():
            self.event.wait(2)
            return

        # Process completed transcodes (status='processed')
        while not self.abort_flag.is_set() and not self.task_queue.task_list_processed_is_empty():
            self.event.wait(0.2)
            next_task = self.task_queue.get_next_processed_tasks()
            if next_task:
                self.current_task = next_task
                self._handle_task_safely(self._handle_processed_task)

        # Process approved tasks (status='approved') — finalize file replacement
        while not self.abort_flag.is_set() and not self.task_queue.task_list_approved_is_empty():
            self.event.wait(0.2)
            next_task = self.task_queue.get_next_approved_tasks()
            if next_task:
                self.current_task = next_task
                self._handle_task_safely(self._handle_approved_task)

    def _handle_task_safely(self, handler: Callable[[], object]) -> None:
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

    def _handle_processed_task(self) -> None:
        """Handle a task that just finished transcoding (status='processed')."""
        # Execute event plugin runners
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type(
            "events.postprocessor_started",
            {
                "library_id": self.task.get_task_library_id(),
                "task_id": self.task.get_task_id(),
                "task_type": self.task.get_task_type(),
                "cache_path": self.task.get_cache_path(),
                "source_data": self.task.get_source_data(),
            },
        )

        try:
            self._log(f"Post-processing task - {self.task.get_source_abspath()}")
        except (AttributeError, KeyError, TypeError) as e:
            self._log("Exception in fetching task absolute path", message2=str(e), level="exception")

        if self.task.get_task_type() == "local":
            self._handle_processed_local_task()
        else:
            self._finalize_remote_task()

    def _handle_processed_local_task(self) -> None:
        if self.model.success:
            self._apply_size_guardrail()
        policy = self._replacement_policy()
        if not self.model.success:
            if not self._attempt_retry():
                self._finalize_local_task()
            return
        if policy == "approval_required":
            self._stage_for_approval()
        elif policy == "keep_both":
            self._finalize_local_task_keep_both()
        else:
            self._finalize_local_task()

    def _apply_size_guardrail(self) -> None:
        try:
            library = Library(self.task.get_task_library_id())
            source_size = self.model.source_size or 0
            cache_path = self.task.get_cache_path()
            if (
                not library.get_size_guardrail_enabled()
                or source_size <= 0
                or not cache_path
                or not os.path.exists(cache_path)
            ):
                return
            ratio = os.path.getsize(cache_path) / source_size * 100
            minimum, maximum = library.get_size_guardrail_min_pct(), library.get_size_guardrail_max_pct()
            if minimum <= ratio <= maximum:
                return
            message = f"Size guardrail REJECTED: {ratio:.1f}% (allowed {minimum}-{maximum}%)"
            self._log(message)
            self.model.success = False
            self.model.log = ((self.model.log or "") + "\n" + message).strip()
            self.model.save()
        except Exception as error:
            self._log("Exception in size guardrail check", message2=str(error), level="warning")

    def _replacement_policy(self) -> str:
        try:
            policy = Library(self.task.get_task_library_id()).get_replacement_policy()
        except Exception as error:
            self._log("Could not determine replacement policy", message2=str(error), level="warning")
            policy = ""
        return policy or ("approval_required" if self.settings.get_approval_required() else "replace")

    def _handle_approved_task(self) -> None:
        """Handle a task that was approved by the user — finalize file replacement from staging."""
        try:
            self._log(f"Finalizing approved task - {self.task.get_source_abspath()}")
        except (AttributeError, KeyError, TypeError) as e:
            self._log("Exception in fetching task absolute path", message2=str(e), level="exception")

        self._finalize_local_task()

    def _is_guardrail_rejection(self) -> bool:
        """Check if the current task's failure was caused by a size guardrail rejection."""
        try:
            task_log = self.model.log or ""
            return "Size guardrail REJECTED" in task_log
        except Exception as e:
            self._log("Guardrail rejection check unavailable", message2=str(e), level="debug")
            return False

    def _attempt_retry(self) -> bool:
        """
        Check if a failed task should be retried with exponential backoff.
        Returns True if the task was re-queued for retry, False otherwise.
        """
        try:
            # Don't retry guardrail rejections — those are intentional
            if self._is_guardrail_rejection():
                return False

            retry_count = self.model.retry_count or 0
            max_retries = self.model.max_retries or self.settings.get_default_max_retries()

            if retry_count >= max_retries:
                return False

            # Exponential backoff: 30s, 2min, 8min
            delay_seconds = 30 * (4**retry_count)
            deferred_until = datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)

            self.model.retry_count = retry_count + 1
            self.model.deferred_until = deferred_until
            self.model.status = "pending"
            self.model.success = None
            self.model.log = ""
            self.model.save()

            source_path = self.task.get_source_abspath()
            filename = os.path.basename(source_path)
            self._log(
                "Retrying task (attempt {}/{}) after {} - {}".format(
                    retry_count + 1, max_retries, deferred_until.strftime("%H:%M:%S"), source_path
                )
            )

            # Push a transient notification to the frontend via the frontend_message stream
            try:
                frontend_messages = FrontendPushMessages()
                msg_id = f"taskRetry_{self.task.get_task_id()}"
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
            cache_path = self.task.get_cache_path()
            if cache_path:
                self.__cleanup_cache_files(cache_path)

            return True
        except (AttributeError, TypeError, OSError) as e:
            self._log("Exception during retry attempt", message2=str(e), level="warning")
            return False
        except Exception as e:
            self._log("Unexpected error during retry attempt", message2=str(e), level="warning")
            return False

    def _stage_for_approval(self) -> None:
        """
        Stage the transcoded file for user review instead of replacing the original.
        Copies the cache file to the staging directory, computes quality metrics,
        and sets status to 'awaiting_approval'.
        """
        try:
            cache_path = self.task.get_cache_path()
            staging_dir = self.settings.get_staging_path()
            task_id = self.task.get_task_id()

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

                source_path = self.task.get_source_abspath()
                scores = compute_quality_scores(source_path, staged_path, duration_limit=30)
                if scores:
                    self.model.vmaf_score = scores.get("vmaf_score")
                    self.model.ssim_score = scores.get("ssim_score")
                    self.model.save()
                    self._log(
                        "Quality scores computed - VMAF: {}, SSIM: {}".format(
                            scores.get("vmaf_score"), scores.get("ssim_score")
                        ),
                        level="debug",
                    )
            except (subprocess.SubprocessError, OSError, ValueError) as e:
                self._log("Quality metric computation failed (non-fatal)", message2=str(e), level="warning")

            # Set the task status to awaiting_approval (keeps cache and task alive)
            self.task.set_status("awaiting_approval")

            # Dispatch approval_needed notification
            try:
                from compresso.libs.external_notifications import ExternalNotificationDispatcher

                source_data = self.task.get_source_data()
                context: dict[str, object] = {
                    "file_name": os.path.basename(source_data.get("abspath", "")),
                    "task_id": task_id,
                    "staged_path": staged_path,
                    "message": "A transcoded file is awaiting approval.",
                }
                # Include quality scores if computed
                try:
                    quality_scores: dict[str, float | None] = {}
                    if getattr(self.model, "vmaf_score", None) is not None:
                        quality_scores["vmaf"] = self.model.vmaf_score
                    if getattr(self.model, "ssim_score", None) is not None:
                        quality_scores["ssim"] = self.model.ssim_score
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

    def _record_approval_metadata(self, staged_path: str) -> None:
        """Persist approval queue metadata while the staged file is fresh."""
        try:
            source_meta = extract_media_metadata(self.task.get_source_abspath())
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            self._log("Failed to extract source approval metadata", message2=str(e), level="debug")
            source_meta = _empty_media_metadata()
        try:
            staged_meta = extract_media_metadata(staged_path)
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            self._log("Failed to extract staged approval metadata", message2=str(e), level="debug")
            staged_meta = _empty_media_metadata()

        try:
            self.model.source_codec = source_meta.get("codec", "")
            self.model.staged_codec = staged_meta.get("codec", "")
            self.model.staged_size = os.path.getsize(staged_path) if os.path.exists(staged_path) else 0
            self.model.metadata_updated_at = datetime.datetime.now()
            self.model.save()
        except (OSError, AttributeError, TypeError) as e:
            self._log("Failed to persist approval metadata", message2=str(e), level="debug")

    def _finalize_local_task(self) -> None:
        """Run the standard local task postprocessing: file move, history, metadata, cleanup."""
        if not self._has_finalization_capacity():
            return
        self._finalize_local_task_with_capacity()

    def _finalize_local_task_with_capacity(self) -> None:
        """Finalize a local task after disk-capacity preflight succeeds."""
        if not self._postprocess_local_file_safely():
            return
        phase = self._current_finalization_phase()
        if self._finalization_step_pending(phase, "history_committed"):
            if not self._persist_local_history():
                return
            self._mark_finalization_transition("history_persisted")
        if self._finalization_step_pending(phase, "metadata_committed"):
            if not self._persist_local_metadata():
                return
            self._mark_finalization_transition("metadata_persisted")
        if self._finalization_step_pending(phase, "task_deleted"):
            if not self._remove_finalized_local_task():
                return
            self._mark_finalization_transition("task_removed")

        self._finalize_file_operation_journal(True)
        self._dispatch_completion_notification()

    def _persist_local_history(self) -> bool:
        try:
            history_written = self.write_history_log()
        except (OSError, AttributeError, TypeError) as e:
            self._log("Exception in writing history log", message2=str(e), level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        except Exception as e:
            self._log(f"TaskMetadataError in history log: {e}", level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        if history_written is False:
            message = "history persistence returned false"
            self._log("Failed to write history log", message2=message, level="error")
            self._defer_postprocess_failure(message)
            return False
        return True

    def _persist_local_metadata(self) -> bool:
        try:
            self.commit_task_metadata()
        except (OSError, AttributeError, TypeError) as e:
            self._log("Exception in committing task metadata", message2=str(e), level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        except Exception as e:
            self._log(f"TaskMetadataError in commit: {e}", level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        return True

    def _remove_finalized_local_task(self) -> bool:
        try:
            # Clean up the staging directory for this task if it exists
            self._cleanup_staging_files()
            # Remove file from task queue
            self.task.delete()
        except (OSError, AttributeError, TypeError) as e:
            self._log("Exception in removing task from task list", message2=str(e), level="exception")
            self._defer_postprocess_failure(str(e))
            return False
        return True

    def _dispatch_completion_notification(self) -> None:
        """Dispatch the best-effort external completion notification."""
        try:
            from compresso.libs.external_notifications import ExternalNotificationDispatcher

            dispatcher = ExternalNotificationDispatcher()
            context = self._completion_notification_context()
            if self.model.success:
                dispatcher.dispatch("task_completed", context)
            else:
                dispatcher.dispatch("task_failed", context)
        except (ImportError, AttributeError, TypeError):
            pass  # notification failure is non-fatal

    def _completion_notification_context(self) -> dict[str, object]:
        source_data = self.task.get_source_data()
        cache_path = self.task.get_cache_path()
        source_size = self.model.source_size or 0
        destination_size = self._completion_destination_size(cache_path)
        context: dict[str, object] = {
            "file_name": os.path.basename(source_data.get("abspath", "")),
            "source_size": source_size or None,
            "destination_size": destination_size,
        }
        self._add_completion_codec(context, cache_path)
        if source_size > 0 and destination_size:
            saved = source_size - destination_size
            context["size_saved"] = f"{saved / (1024 * 1024):.1f} MB ({saved / source_size * 100:.0f}%)"
        scores = {
            name: value for name in ("vmaf", "ssim") if (value := getattr(self.model, f"{name}_score", None)) is not None
        }
        if scores:
            context["quality_scores"] = scores
        return context

    @staticmethod
    def _completion_destination_size(cache_path: str | None) -> int | None:
        try:
            return os.path.getsize(cache_path) if cache_path and os.path.exists(cache_path) else None
        except OSError:
            return None

    @staticmethod
    def _add_completion_codec(context: dict[str, object], cache_path: str | None) -> None:
        try:
            if cache_path and os.path.exists(cache_path):
                context["codec"] = extract_media_metadata(cache_path).get("codec", "")
        except (subprocess.SubprocessError, OSError, ValueError):
            pass

    @staticmethod
    def _next_finalization_phase(
        current_phase: FinalizationPhase | None,
        event: FinalizationEvent,
    ) -> FinalizationPhase:
        """Resolve idempotent journal transitions without changing phase names."""
        target_phases: dict[FinalizationEvent, FinalizationPhase] = {
            "history_persisted": "history_committed",
            "metadata_persisted": "metadata_committed",
            "task_removed": "task_deleted",
        }
        target = target_phases[event]
        if FINALIZATION_PHASE_ORDER.get(current_phase, 0) >= FINALIZATION_PHASE_ORDER[target]:
            return current_phase or target
        return target

    def _current_finalization_phase(self) -> FinalizationPhase | None:
        if self._file_operation_tracker is None:
            return None
        phase = self._file_operation_tracker.finalization_phase
        return phase if phase in FINALIZATION_PHASE_ORDER else None

    @staticmethod
    def _finalization_step_pending(
        current_phase: FinalizationPhase | None,
        target_phase: FinalizationPhase,
    ) -> bool:
        return FINALIZATION_PHASE_ORDER.get(current_phase, 0) < FINALIZATION_PHASE_ORDER[target_phase]

    def _mark_finalization_transition(self, event: FinalizationEvent) -> None:
        current_phase = None
        if self._file_operation_tracker is not None:
            current_phase = self._file_operation_tracker.finalization_phase
        self._mark_finalization_phase(self._next_finalization_phase(current_phase, event))

    @staticmethod
    def _postprocess_completion_transition(
        task_success: bool | None,
        movement_success: bool,
    ) -> PostprocessCompletionTransition:
        """Describe journal/cache actions after the file-movement phase."""
        return PostprocessCompletionTransition(
            commit_journal=bool(task_success and movement_success),
            rollback_journal=bool(task_success and not movement_success),
            cleanup_cache=bool(movement_success or not task_success),
            succeeded=bool(movement_success),
        )

    def _transition_postprocess_journal(
        self,
        tracker: FileOperationTracker,
        task_success: bool | None,
        movement_success: bool,
        cache_path: str,
    ) -> PostprocessCompletionTransition:
        transition = self._postprocess_completion_transition(task_success, movement_success)
        if transition.commit_journal:
            if not tracker.commit():
                self._log("File-operation journal commit remains pending", level="warning")
                return PostprocessCompletionTransition(
                    commit_journal=False,
                    rollback_journal=False,
                    cleanup_cache=False,
                    succeeded=False,
                )
            tracker.mark_finalization_phase("file_committed")
        elif transition.rollback_journal:
            self._log("Rolling back all tracked file operations due to failures", level="warning")
            tracker.rollback()
            self._log(
                f"Error while running postprocessor file movement on file '{cache_path}'."
                " Not all postprocessor file movement functions completed.",
                level="error",
            )
        return transition

    def _postprocess_local_file_safely(self) -> bool:
        """Run the destructive file phase and defer all later finalization on failure."""
        resumed = FileOperationTracker.resume_committed(
            self._get_file_operation_journal_dir(),
            task_id=self.task.get_task_id(),
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

    def _get_file_operation_journal_dir(self) -> str | None:
        config_path = self.settings.get_config_path()
        return os.path.join(config_path, "recovery", "file_operations") if isinstance(config_path, str) else None

    def _mark_finalization_phase(self, phase: FinalizationPhase) -> None:
        if self._file_operation_tracker is not None:
            self._file_operation_tracker.mark_finalization_phase(phase)

    def _defer_postprocess_failure(self, reason: str) -> None:
        """Keep the task and encoded cache available for a safe later retry."""
        try:
            retry_seconds = max(1, int(self.settings.get_disk_space_retry_seconds()))
        except (AttributeError, TypeError, ValueError):
            retry_seconds = 60
        self.model.deferred_until = datetime.datetime.now() + datetime.timedelta(seconds=retry_seconds)
        self.model.save()
        self._log(
            f"POSTPROCESS_DEFERRED task_id={self.task.get_task_id()} retry_seconds={retry_seconds} reason={reason}",
            level="error",
        )

    def _get_disk_space_guard(self) -> DiskSpaceGuard:
        if self._disk_space_guard is None:
            self._disk_space_guard = DiskSpaceGuard(self.settings)
        return self._disk_space_guard

    def _has_finalization_capacity(self) -> bool:
        if not self.model.success:
            return True
        source_path = self.task.get_source_abspath()
        cache_path = self.task.get_cache_path()
        destination_path = self.task.get_destination_data()["abspath"]
        disk_check = self._get_disk_space_guard().check_finalization_capacity(
            source_path,
            cache_path,
            destination_path,
        )
        if not disk_check.ok:
            self._defer_for_disk_pressure(disk_check, self.model.status)
            return False
        if self.model.deferred_until is not None:
            self.model.deferred_until = None
            self.model.save()
        return True

    def _defer_for_disk_pressure(self, disk_check: DiskSpaceCheck, retry_status: str) -> None:
        retry_seconds = self.settings.get_disk_space_retry_seconds()
        self.model.status = retry_status
        self.model.deferred_until = datetime.datetime.now() + datetime.timedelta(seconds=retry_seconds)
        self.model.save()
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

    def _finalize_file_operation_journal(self, task_deleted: bool) -> None:
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

    def _finalize_local_task_keep_both(self) -> None:
        """Finalize task but keep original — save output alongside with codec suffix."""
        try:
            dest_data = self.task.get_destination_data()
            source_data = self.task.get_source_data()
            if dest_data["abspath"] == source_data["abspath"]:
                # Same filename — add codec suffix to avoid overwriting
                base, ext = os.path.splitext(dest_data["abspath"])
                try:
                    meta = extract_media_metadata(self.task.get_cache_path())
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
                self.task.set_destination_path(new_path)
        except (OSError, AttributeError, KeyError, TypeError) as e:
            self._log("Exception in keep_both path adjustment", message2=str(e), level="warning")
        # The adjusted destination differs from the source, which would normally
        # trigger source-file removal in post_process_file. The whole point of
        # 'keep_both' is that the original survives, so suppress that removal.
        self._keep_source_file = True
        try:
            self._finalize_local_task()
        finally:
            self._keep_source_file = False

    def _finalize_remote_task(self) -> bool:
        """Finalize a remote task only after its file and history are durable."""
        original_path = self.task.get_source_abspath()
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
            self.task.modify_path(final_path)
            self.task.set_status("complete")
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
        self.__cleanup_cache_files(self.task.get_cache_path())
        return True

    def _rollback_prepared_remote_output(self, final_path: str, original_path: str) -> bool:
        """Restore task identity before removing a prepared remote copy."""
        try:
            self.task.modify_path(original_path)
        except Exception as error:
            self._log("Unable to roll back remote task path", message2=str(error), level="exception")
            return False
        self._discard_prepared_remote_output(final_path, original_path)
        return True

    def _discard_prepared_remote_output(self, final_path: str, original_path: str) -> None:
        """Remove a failed prepared copy while retaining the encoded cache."""
        if not final_path or os.path.realpath(final_path) == os.path.realpath(original_path):
            return
        final_directory = os.path.dirname(final_path)
        if os.path.basename(final_directory).startswith("compresso_remote_pending_library-"):
            shutil.rmtree(final_directory, ignore_errors=True)
            return
        with contextlib.suppress(FileNotFoundError, OSError):
            os.remove(final_path)

    def _cleanup_staging_files(self) -> None:
        """Remove the staging directory for the current task if it exists."""
        try:
            task_id = self.task.get_task_id()
            staging_dir = self.settings.get_staging_path()
            task_staging_dir = os.path.join(staging_dir, f"task_{task_id}")
            if os.path.exists(task_staging_dir):
                self._log(f"Removing staging directory '{task_staging_dir}'")
                shutil.rmtree(task_staging_dir)
        except (OSError, PermissionError, shutil.Error) as e:
            self._log("Exception while cleaning up staging files", message2=str(e), level="warning")

    def system_configuration_is_valid(self) -> bool:
        """
        Check and ensure the system configuration is correct for running

        :return:
        """
        plugin_handler = PluginsHandler()
        return not plugin_handler.get_incompatible_enabled_plugins()

    def post_process_file(self) -> bool:
        # Init plugins handler
        plugin_handler = PluginsHandler()

        # Read current task data
        # task_data = self.task.get_task_data()
        library_id = self.task.get_task_library_id()
        cache_path = self.task.get_cache_path()
        source_data = self.task.get_source_data()
        destination_data = self.task.get_destination_data()
        # Move file back to original folder and remove source
        # Create a list for filling with destination paths
        destination_files: list[str] = []
        # Create a tracker for safe file operations with rollback support
        journal_dir = self._get_file_operation_journal_dir()
        tracker = FileOperationTracker(
            self.logger,
            journal_dir=journal_dir,
            operation_id=f"task-{self.task.get_task_id()}",
            task_id=self.task.get_task_id(),
            failure_callback=lambda **details: self._safety_event_recorder(
                self.settings,
                None,
                "rollback-failure",
                "A destructive file operation could not be rolled back",
                **details,
            ),
        )
        self._file_operation_tracker = tracker
        file_move_processes_success = True
        if self.model.success:
            file_move_processes_success = self._run_file_movements(
                plugin_handler, library_id, cache_path, source_data, destination_data, destination_files, tracker
            )

        else:
            self._log(f"Skipping file movement post-processor as the task was not successful '{cache_path}'", level="warning")

        completion = self._transition_postprocess_journal(
            tracker,
            self.model.success,
            file_move_processes_success,
            cache_path,
        )

        self._run_task_result_plugins(
            plugin_handler, library_id, cache_path, source_data, destination_files, file_move_processes_success
        )

        # Retain a valid encode when movement failed so the postprocessor can
        # retry without destroying the only completed output.
        if completion.cleanup_cache:
            self.__cleanup_cache_files(cache_path)
        self._last_destination_files = destination_files
        return completion.succeeded

    def _run_file_movements(
        self,
        plugin_handler: PluginsHandler,
        library_id: int,
        cache_path: str,
        source_data: TaskPathData,
        destination_data: TaskPathData,
        destination_files: list[str],
        tracker: FileOperationTracker,
    ) -> bool:
        remove_source = source_data["abspath"] != destination_data["abspath"] and not self._keep_source_file
        data: dict[str, object] = {
            "library_id": library_id,
            "task_id": self.task.get_task_id(),
            "source_data": source_data,
            "remove_source_file": remove_source,
            "copy_file": False,
            "file_in": cache_path,
            "file_out": destination_data["abspath"],
            "run_default_file_copy": True,
        }
        success = self._run_file_move_plugins(plugin_handler, library_id, data, destination_files, tracker)
        if success and data.get("run_default_file_copy"):
            same_path = destination_data["abspath"] == source_data["abspath"]
            if not same_path or not data.get("remove_source_file"):
                success = self.__copy_file(
                    cache_path, destination_data["abspath"], destination_files, "DEFAULT", move=True, tracker=tracker
                )
        if success and data.get("remove_source_file") and os.path.exists(source_data["abspath"]):
            try:
                tracker.safe_remove(source_data["abspath"])
            except (OSError, PermissionError, shutil.Error) as error:
                self._log("Failed to safely remove source file", message2=str(error), level="error")
                success = False
        return success

    def _run_file_move_plugins(
        self,
        plugin_handler: PluginsHandler,
        library_id: int,
        data: dict[str, object],
        destination_files: list[str],
        tracker: FileOperationTracker,
    ) -> bool:
        success = True
        modules = plugin_handler.get_enabled_plugin_modules_by_type("postprocessor.file_move", library_id=library_id)
        for module in modules:
            plugin_id = module.get("plugin_id")
            if not isinstance(plugin_id, str):
                continue
            data.update({"copy_file": False})
            if not plugin_handler.exec_plugin_runner(data, plugin_id, "postprocessor.file_move") or not data.get("copy_file"):
                continue
            file_in, file_out = data.get("file_in"), data.get("file_out")
            if not isinstance(file_in, str) or not isinstance(file_out, str):
                success = False
                continue
            if not self.__copy_file(
                os.path.abspath(file_in), os.path.abspath(file_out), destination_files, plugin_id, tracker=tracker
            ):
                success = False
        return success

    def _run_task_result_plugins(
        self,
        plugin_handler: PluginsHandler,
        library_id: int,
        cache_path: str,
        source_data: TaskPathData,
        destination_files: list[str],
        move_success: bool,
    ) -> None:
        result_data: dict[str, object] = {
            "library_id": library_id,
            "task_id": self.task.get_task_id(),
            "task_type": self.task.get_task_type(),
            "final_cache_path": cache_path,
            "task_processing_success": self.task.get_task_success(),
            "file_move_processes_success": move_success,
            "destination_files": list(destination_files),
            "source_data": source_data,
            "start_time": self.task.get_start_time(),
            "finish_time": self.task.get_finish_time(),
        }
        for module in plugin_handler.get_enabled_plugin_modules_by_type("postprocessor.task_result", library_id=library_id):
            plugin_id = module.get("plugin_id")
            if isinstance(plugin_id, str):
                plugin_handler.exec_plugin_runner(result_data, plugin_id, "postprocessor.task_result")

    def post_process_remote_file(self) -> str | Literal[False]:
        """
        Copy a remote task's encoded cache to its pending final location.

        The cache is deliberately retained until the caller has durably written
        history and marked the task complete. The returned path is therefore a
        prepared result, not permission to clean up the cache yet.
        """
        cache_path = self.task.get_cache_path()
        source_data = self.task.get_source_data()
        destination_data = self.task.get_destination_data()
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
    def _path_is_within(path: str, directory: str) -> bool:
        if not path or not directory:
            return False
        normalized_path = os.path.normcase(os.path.realpath(path))
        normalized_directory = os.path.normcase(os.path.realpath(directory))
        try:
            return os.path.commonpath([normalized_directory, normalized_path]) == normalized_directory
        except ValueError:
            return False

    def __cleanup_cache_files(self, cache_path: str) -> None:
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

    def __copy_file(
        self,
        file_in: str,
        file_out: str,
        destination_files: list[str],
        plugin_id: str,
        move: bool = False,
        tracker: FileOperationTracker | None = None,
    ) -> bool:
        if move:
            self._log(f"Move file triggered by ({plugin_id}) {file_in} --> {file_out}")
        else:
            self._log(f"Copy file triggered by ({plugin_id}) {file_in} --> {file_out}")

        # Use a '.part' suffix for the file movement, then rename it after. Defined
        # up-front so a partial failure can clean it up rather than orphaning it next
        # to the destination file.
        part_file_out = os.path.join(f"{file_out}.compresso.part")
        try:
            return self._perform_file_copy(file_in, file_out, part_file_out, destination_files, move, tracker)
        except (OSError, PermissionError, shutil.SameFileError, shutil.Error) as e:
            self.logger.error("POSTPROCESS_FILE_COPY_FAILED source=%s dest=%s", file_in, file_out)
            self._log(f"Exception while copying file {file_in} to {file_out}:", message2=str(e), level="exception")
            if tracker:
                self._log("Rolling back file operations due to copy failure", level="warning")
                tracker.rollback()
            # Remove the staging '.part' file if it was left behind by a failed
            # move/rename so it is not orphaned next to the destination file.
            self._cleanup_failed_file_copy(file_in, part_file_out, move)
            return False

    def _perform_file_copy(
        self,
        file_in: str,
        file_out: str,
        part_file_out: str,
        destination_files: list[str],
        move: bool,
        tracker: FileOperationTracker | None,
    ) -> bool:
        if os.path.exists(file_out) and os.path.samefile(file_in, file_out):
            self._log(f"The file_in and file_out path are the same file. Nothing will be done! '{file_in}'", level="warning")
            return False
        if not os.path.exists(file_in):
            self._log(f"The file_in path does not exist! '{file_in}'", level="warning")
            self.event.wait(1)
        if move:
            self._log(f"Moving file '{file_in}' --> '{part_file_out}'.", level="debug")
            if os.path.exists(part_file_out):
                os.remove(part_file_out)
            shutil.move(file_in, part_file_out, copy_function=shutil.copyfile)
        else:
            self._log(f"Copying file '{file_in}' --> '{part_file_out}'.", level="debug")
            shutil.copyfile(file_in, part_file_out)
        if os.path.exists(file_out):
            self._log(f"The file_out path already exists. Removing file '{file_out}'", level="debug")
            tracker.safe_remove(file_out) if tracker else os.remove(file_out)
        self._log(f"Renaming file '{part_file_out}' --> '{file_out}'.", level="debug")
        if tracker:
            tracker.record_created(file_out)
        shutil.move(part_file_out, file_out, copy_function=shutil.copyfile)
        destination_files.append(file_out)
        return True

    def _cleanup_failed_file_copy(self, file_in: str, part_file_out: str, move: bool) -> None:
        if not os.path.exists(part_file_out):
            return
        try:
            if move and not os.path.exists(file_in):
                shutil.copyfile(part_file_out, file_in)
            os.remove(part_file_out)
        except OSError as cleanup_error:
            self._log(f"Failed to remove staging file '{part_file_out}'", message2=str(cleanup_error), level="warning")

    def write_history_log(self) -> bool:
        """
        Record task history

        :return:
        """
        self._log("Writing task history log.", level="debug")
        history_logging = history.History()
        task_dump = self.task.task_dump()
        destination_data = self.task.get_destination_data()
        source_data = self.task.get_source_data()

        if not self.model.success:
            self._notify_failed_history_task()

        self._log_completed_task_data(task_dump, source_data, destination_data)

        destination_size, source_meta, dest_meta, source_duration_seconds = self._history_media_details(
            task_dump, source_data, destination_data
        )

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

        self._bump_analysis_cache(task_dump.get("library_id", 1))

        # Execute event plugin runners
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type(
            "events.postprocessor_complete",
            {
                "library_id": self.task.get_task_library_id(),
                "task_id": self.task.get_task_id(),
                "task_type": self.task.get_task_type(),
                "source_data": self.task.get_source_data(),
                "destination_data": self.task.get_destination_data(),
                "task_success": task_dump.get("task_success", False),
                "start_time": task_dump.get("start_time", ""),
                "finish_time": task_dump.get("finish_time", ""),
                "processed_by_worker": task_dump.get("processed_by_worker", ""),
                "log": task_dump.get("log", ""),
            },
        )
        return True

    @staticmethod
    def _notify_failed_history_task() -> None:
        Notifications().add(
            {
                "uuid": "newFailedTask",
                "type": "error",
                "icon": "report",
                "label": "failedTaskLabel",
                "message": "You have a new failed task in your completed tasks list",
                "navigation": {"push": "/ui/dashboard", "events": ["completedTasksShowFailed"]},
            }
        )

    def _history_media_details(
        self,
        task_dump: Mapping[str, object],
        source_data: TaskPathData,
        destination_data: TaskPathData,
    ) -> tuple[int, MediaMetadata, MediaMetadata, float]:
        success = bool(task_dump.get("task_success", False))
        source_path = source_data.get("abspath", "")
        dest_path = destination_data.get("abspath", "") if success else ""
        destination_size = 0
        try:
            destination_size = os.path.getsize(dest_path) if dest_path and os.path.exists(dest_path) else 0
        except OSError:
            self.logger.warning("POSTPROCESS_DESTINATION_SIZE_UNAVAILABLE path=%s", dest_path)
        source_meta = self._extract_history_metadata(source_path, "source")
        dest_meta = self._extract_history_metadata(dest_path, "destination")
        with contextlib.suppress(TypeError, ValueError):
            return destination_size, source_meta, dest_meta, float(source_meta.get("duration", 0))
        return destination_size, source_meta, dest_meta, 0.0

    def _extract_history_metadata(self, path: str, label: str) -> MediaMetadata:
        if not path or not os.path.exists(path):
            return _empty_media_metadata()
        try:
            return extract_media_metadata(path)
        except (subprocess.SubprocessError, OSError, ValueError) as error:
            self.logger.warning("POSTPROCESS_%s_METADATA_UNAVAILABLE path=%s", label.upper(), path)
            self._log(f"Could not extract {label} metadata: {error}", level="warning")
            return _empty_media_metadata()

    def _bump_analysis_cache(self, library_id: object) -> None:
        try:
            from compresso.libs.unmodels import LibraryAnalysisCache

            cache_entry = LibraryAnalysisCache.get_or_none(LibraryAnalysisCache.library_id == library_id)
            if cache_entry:
                cache_entry.version += 1
                cache_entry.save()
        except (ImportError, AttributeError, TypeError, peewee.PeeweeException) as error:
            self.logger.debug("Failed to bump analysis cache version: %s", error)

    def commit_task_metadata(self) -> int:
        """
        Commit task metadata after all postprocessor runners have finished.
        """
        source_data = self.task.get_source_data()
        destination_data = self.task.get_destination_data()
        task_success = self.task.get_task_success()
        destination_files = list(self._last_destination_files or [])
        if not destination_files and destination_data:
            destination_files = [destination_data.get("abspath")]
        committed = CompressoFileMetadata.commit_task(
            task_id=self.task.get_task_id(),
            task_success=bool(task_success),
            source_path=source_data.get("abspath"),
            destination_paths=destination_files,
        )
        if committed:
            self._log(f"Committed file metadata entries: {committed}", level="debug")
        return committed

    def dump_history_log(self, destination_path: str | None = None) -> None:
        self._log("Dumping remote task history log.", level="debug")
        task_dump = self.task.task_dump()
        destination_path = destination_path or self.task.get_destination_data().get("abspath")
        task_dump["abspath"] = destination_path

        # Dump history log & task state as metadata in the file's path
        tasks_data_file = os.path.join(os.path.dirname(destination_path), "data.json")
        task_state = TaskDataStore.export_task_state(self.task.get_task_id())
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
            file_mode=0o600,
        )
        if not result["success"]:
            for message in result["errors"]:
                self._log("Exception:", message2=str(message), level="exception")
            raise Exception("Exception in dumping completed task data to file")

    def _log_completed_task_data(
        self,
        task_dump: Mapping[str, object],
        source_data: TaskPathData,
        destination_data: TaskPathData,
    ) -> None:
        status = "success" if task_dump.get("task_success", False) else "failed"
        start_time = task_dump.get("start_time", "")
        finish_time = task_dump.get("finish_time", "")
        command_error_log_tail = ""
        if status != "success":
            task_log_value = task_dump.get("log", "")
            task_log = task_log_value if isinstance(task_log_value, str) else str(task_log_value)
            if task_log:
                command_error_log_tail = "\n".join(task_log.splitlines()[-20:])
        try:
            library_id = self.task.get_task_library_id()
            library_name = self.task.get_task_library_name()
        except (AttributeError, KeyError, TypeError):
            library_id = None
            library_name = None

        CompressoLogging.log_data(
            "completed_task",
            data_search_key=f"{library_id} | {finish_time} | {source_data.get('abspath', '')}",
            task_id=self.task.get_task_id(),
            task_type=self.task.get_task_type(),
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
