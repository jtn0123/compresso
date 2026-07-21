#!/usr/bin/env python3

"""
compresso.file_operation_tracker.py

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

import json
import os
import shutil
from typing import Literal, Protocol, TypedDict, cast

from compresso.libs.json_state import atomic_json_write

JournalState = Literal[
    "active",
    "rolling_back",
    "rollback_failed",
    "committing",
    "commit_cleanup_pending",
    "committed",
]
FinalizationPhase = Literal[
    "file_committed",
    "history_committed",
    "metadata_committed",
    "task_deleted",
]


class Logger(Protocol):
    def info(self, message: object, *args: object) -> object: ...

    def warning(self, message: object, *args: object) -> object: ...

    def error(self, message: object, *args: object) -> object: ...


class FailureCallback(Protocol):
    def __call__(self, **details: object) -> object: ...


class ValidatedJournal(TypedDict):
    operation_id: str
    task_id: int | None
    state: JournalState
    finalization_phase: FinalizationPhase | None
    backups: list[tuple[str, str]]
    created_paths: list[str]


class RecoveryResult(TypedDict):
    rolled_back_task_ids: list[int]
    committed_task_ids: list[int]
    finalization_task_ids: list[int]


JOURNAL_STATES: set[JournalState] = {
    "active",
    "rolling_back",
    "rollback_failed",
    "committing",
    "commit_cleanup_pending",
    "committed",
}
JOURNAL_FINALIZATION_PHASES: set[FinalizationPhase | None] = {
    None,
    "file_committed",
    "history_committed",
    "metadata_committed",
    "task_deleted",
}
COMMITTED_STATES: set[JournalState] = {"committing", "commit_cleanup_pending", "committed"}


class FileOperationTracker:
    """Track destructive file operations for rollback on failure."""

    def __init__(
        self,
        logger: Logger,
        journal_dir: str | None = None,
        operation_id: str | None = None,
        task_id: int | None = None,
        failure_callback: FailureCallback | None = None,
    ) -> None:
        self._logger = logger
        self._backups: list[tuple[str, str]] = []
        self._created_paths: list[str] = []
        self._journal_dir = journal_dir
        self._operation_id = operation_id
        self._task_id = task_id
        self._state: JournalState = "active"
        self._failure_callback = failure_callback
        self._finalization_phase: FinalizationPhase | None = None
        self._journal_path: str | None = None
        if journal_dir and operation_id:
            safe_operation_id = str(operation_id).replace(os.sep, "_")
            self._journal_path = os.path.join(journal_dir, f"{safe_operation_id}.json")
            if os.path.exists(self._journal_path):
                raise FileExistsError(f"Unrecovered file-operation journal already exists: {self._journal_path}")

    def _journal_data(self) -> dict[str, object]:
        return {
            "version": 1,
            "operation_id": self._operation_id,
            "task_id": self._task_id,
            "state": self._state,
            "finalization_phase": self._finalization_phase,
            "backups": [list(item) for item in self._backups],
            "created_paths": list(self._created_paths),
        }

    @staticmethod
    def _validate_journal(
        data: object,
        journal_name: str,
        *,
        expected_operation_id: str | None = None,
        expected_task_id: int | None = None,
    ) -> ValidatedJournal:
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("file-operation journal schema is invalid")
        operation_id, task_id = FileOperationTracker._validated_journal_identity(
            data, journal_name, expected_operation_id, expected_task_id
        )
        state = data.get("state")
        if state not in JOURNAL_STATES:
            raise ValueError("file-operation journal state is invalid")
        finalization_phase = data.get("finalization_phase")
        if finalization_phase not in JOURNAL_FINALIZATION_PHASES:
            raise ValueError("file-operation journal finalization phase is invalid")
        if finalization_phase is not None and state not in COMMITTED_STATES:
            raise ValueError("file-operation journal phase is inconsistent with its state")
        backups = data.get("backups")
        created_paths = data.get("created_paths")
        if not isinstance(backups, list) or not isinstance(created_paths, list):
            raise ValueError("file-operation journal paths are invalid")
        normalized_backups = FileOperationTracker._validated_journal_backups(backups)
        if not all(isinstance(path, str) and path for path in created_paths):
            raise ValueError("file-operation journal created paths are invalid")
        return {
            "operation_id": operation_id,
            "task_id": task_id,
            "state": cast("JournalState", state),
            "finalization_phase": cast("FinalizationPhase | None", finalization_phase),
            "backups": normalized_backups,
            "created_paths": cast("list[str]", created_paths),
        }

    @staticmethod
    def _validated_journal_identity(
        data: dict[object, object],
        journal_name: str,
        expected_operation_id: str | None,
        expected_task_id: int | None,
    ) -> tuple[str, int | None]:
        operation_id = data.get("operation_id")
        if not isinstance(operation_id, str) or not operation_id or f"{operation_id}.json" != journal_name:
            raise ValueError("file-operation journal identity is invalid")
        task_id = data.get("task_id")
        if task_id is not None and (not isinstance(task_id, int) or isinstance(task_id, bool)):
            raise ValueError("file-operation journal task identity is invalid")
        if expected_operation_id is not None and operation_id != expected_operation_id:
            raise ValueError("file-operation journal identity does not match the requested operation")
        if expected_task_id is not None and task_id != expected_task_id:
            raise ValueError("file-operation journal identity does not match the requested task")
        return operation_id, task_id

    @staticmethod
    def _validated_journal_backups(backups: list[object]) -> list[tuple[str, str]]:
        normalized: list[tuple[str, str]] = []
        for pair in backups:
            if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(item, str) and item for item in pair):
                raise ValueError("file-operation journal backup pair is invalid")
            backup_path, original_path = pair
            if os.path.abspath(backup_path) != f"{os.path.abspath(original_path)}.compresso.bak":
                raise ValueError("file-operation journal backup is not owned by its original path")
            normalized.append((backup_path, original_path))
        return normalized

    def _persist(self) -> None:
        if not self._journal_path:
            return
        if self._journal_dir is None:
            raise RuntimeError("file-operation journal path has no owning directory")
        os.makedirs(self._journal_dir, exist_ok=True)
        atomic_json_write(self._journal_path, self._journal_data(), mode=0o600)

    def record_created(self, filepath: str) -> None:
        """Persist that rollback must remove a newly created destination."""
        filepath = os.path.realpath(filepath)
        if filepath not in self._created_paths:
            self._created_paths.append(filepath)
            self._persist()

    def safe_remove(self, filepath: str) -> None:
        """Back up a file before removing it, enabling rollback."""
        if not os.path.exists(filepath):
            return
        backup_path = filepath + ".compresso.bak"
        try:
            if os.path.exists(backup_path):
                raise FileExistsError(f"Refusing to overwrite existing recovery backup: {backup_path}")
            shutil.copy2(filepath, backup_path)
            self._backups.append((backup_path, filepath))
            self._persist()
            os.remove(filepath)
        except (OSError, PermissionError, shutil.Error) as e:
            self._logger.warning("FileOperationTracker: failed to back up '%s': %s", filepath, e)
            raise

    def commit(self) -> bool:
        """Commit file changes while retaining a recovery marker until finalized."""
        self._state = "committing"
        self._persist()
        remaining_backups: list[tuple[str, str]] = []
        for backup_path, original_path in self._backups:
            try:
                if os.path.exists(backup_path):
                    os.remove(backup_path)
            except (OSError, PermissionError) as e:
                self._logger.warning("FileOperationTracker: failed to remove backup '%s': %s", backup_path, e)
                remaining_backups.append((backup_path, original_path))
        self._backups = remaining_backups
        if self._backups:
            self._state = "commit_cleanup_pending"
            self._persist()
            return False
        self._state = "committed"
        self._persist()
        return True

    @property
    def finalization_phase(self) -> FinalizationPhase | None:
        return self._finalization_phase

    def mark_finalization_phase(self, phase: FinalizationPhase) -> None:
        """Persist progress after the destructive file transaction commits."""
        if self._state != "committed":
            return
        self._finalization_phase = phase
        self._persist()

    @classmethod
    def resume_committed(cls, journal_dir: str | None, task_id: int, logger: Logger) -> "FileOperationTracker | None":
        """Load a committed task journal so later finalization phases can replay."""
        if not journal_dir:
            return None
        operation_id = f"task-{task_id}"
        journal_path = os.path.join(journal_dir, f"{operation_id}.json")
        if not os.path.isfile(journal_path):
            return None
        with open(journal_path) as journal_file:
            data: object = json.load(journal_file)
        data = cls._validate_journal(
            data,
            os.path.basename(journal_path),
            expected_operation_id=operation_id,
            expected_task_id=task_id,
        )
        if data.get("state") not in COMMITTED_STATES:
            return None
        tracker = cls(logger)
        tracker._journal_dir = journal_dir
        tracker._operation_id = operation_id
        tracker._task_id = task_id
        tracker._journal_path = journal_path
        tracker._state = data["state"]
        tracker._finalization_phase = data["finalization_phase"]
        tracker._backups = data["backups"]
        tracker._created_paths = data["created_paths"]
        return tracker

    def finalize(self) -> None:
        """Remove the recovery marker after the owning task is fully finalized."""
        if self._journal_path and os.path.exists(self._journal_path):
            os.remove(self._journal_path)

    def rollback(self) -> bool:
        """Restore all backed-up files to their original paths."""
        self._state = "rolling_back"
        self._persist()
        backup_by_original = {os.path.realpath(original): backup for backup, original in self._backups}
        remaining_created_paths = self._remove_created_paths_for_rollback(backup_by_original)
        remaining_backups = self._restore_backups_for_rollback()
        self._backups = list(reversed(remaining_backups))
        self._created_paths = list(reversed(remaining_created_paths))
        if self._backups or self._created_paths:
            self._state = "rollback_failed"
            self._persist()
            self._notify_rollback_failure()
            return False
        self.finalize()
        return True

    def _remove_created_paths_for_rollback(self, backup_by_original: dict[str, str]) -> list[str]:
        remaining_created_paths: list[str] = []
        for created_path in reversed(self._created_paths):
            backup_path = backup_by_original.get(os.path.realpath(created_path))
            if backup_path and not os.path.exists(backup_path):
                self._logger.error(
                    "FileOperationTracker: refusing to remove '%s'; required backup '%s' is missing",
                    created_path,
                    backup_path,
                )
                remaining_created_paths.append(created_path)
                continue
            try:
                if os.path.exists(created_path):
                    os.remove(created_path)
            except OSError as e:
                self._logger.error("FileOperationTracker: failed to remove created path '%s': %s", created_path, e)
                remaining_created_paths.append(created_path)
        return remaining_created_paths

    def _restore_backups_for_rollback(self) -> list[tuple[str, str]]:
        remaining_backups: list[tuple[str, str]] = []
        for backup_path, original_path in reversed(self._backups):
            try:
                if os.path.exists(backup_path):
                    shutil.move(backup_path, original_path)
                    self._logger.info("FileOperationTracker: restored '%s' from backup", original_path)
                else:
                    remaining_backups.append((backup_path, original_path))
            except OSError as e:
                self._logger.error(
                    "FileOperationTracker: FAILED to restore '%s' from backup '%s': %s", original_path, backup_path, e
                )
                remaining_backups.append((backup_path, original_path))
        return remaining_backups

    def _notify_rollback_failure(self) -> None:
        if self._failure_callback is None:
            return
        try:
            self._failure_callback(
                operation_id=self._operation_id,
                task_id=self._task_id,
                remaining_backups=len(self._backups),
                remaining_created_paths=len(self._created_paths),
            )
        except Exception as error:
            self._logger.error("FileOperationTracker: failed to record rollback safety event: %s", error)

    @classmethod
    def recover_all(cls, journal_dir: str | None, logger: Logger) -> RecoveryResult:
        """Recover durable file-operation journals left by an interrupted run."""
        result: RecoveryResult = {
            "rolled_back_task_ids": [],
            "committed_task_ids": [],
            "finalization_task_ids": [],
        }
        if not journal_dir or not os.path.isdir(journal_dir):
            return result

        recovery_errors: list[str] = []
        for journal_name in sorted(os.listdir(journal_dir)):
            if not journal_name.endswith(".json"):
                continue
            journal_path = os.path.join(journal_dir, journal_name)
            try:
                cls._recover_journal(journal_path, journal_name, result)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                logger.error("FILE_OPERATION_RECOVERY_FAILED journal=%s error=%s", journal_path, error)
                recovery_errors.append(journal_path)

        if recovery_errors:
            raise RuntimeError(f"Unable to recover {len(recovery_errors)} file-operation journal(s)")

        return result

    @classmethod
    def _recover_journal(cls, journal_path: str, journal_name: str, result: RecoveryResult) -> None:
        with open(journal_path) as journal_file:
            raw_data: object = json.load(journal_file)
        data = cls._validate_journal(raw_data, journal_name)
        task_id = data.get("task_id")
        backups = data["backups"]
        if data.get("state", "active") in COMMITTED_STATES:
            cls._recover_committed_journal(backups)
            if task_id is not None:
                if data.get("finalization_phase") == "task_deleted":
                    result["committed_task_ids"].append(task_id)
                else:
                    result["finalization_task_ids"].append(task_id)
            return
        cls._rollback_journal_paths(backups, data.get("created_paths", []))
        if task_id is not None:
            result["rolled_back_task_ids"].append(task_id)
        os.remove(journal_path)

    @staticmethod
    def _recover_committed_journal(backups: list[tuple[str, str]]) -> None:
        for backup_path, _original_path in backups:
            if os.path.exists(backup_path):
                os.remove(backup_path)

    @staticmethod
    def _rollback_journal_paths(backups: list[tuple[str, str]], created_paths: list[str]) -> None:
        missing = [backup for backup, _original in backups if not os.path.exists(backup)]
        if missing:
            raise FileNotFoundError(f"required backup is missing: {missing[0]}")
        for created_path in reversed(created_paths):
            if os.path.exists(created_path):
                os.remove(created_path)
        for backup_path, original_path in reversed(backups):
            os.makedirs(os.path.dirname(os.path.abspath(original_path)), exist_ok=True)
            os.replace(backup_path, original_path)

    @staticmethod
    def finalize_committed(journal_dir: str | None) -> None:
        """Remove committed markers after their task rows have been reconciled."""
        if not journal_dir or not os.path.isdir(journal_dir):
            return
        for journal_name in sorted(os.listdir(journal_dir)):
            if not journal_name.endswith(".json"):
                continue
            journal_path = os.path.join(journal_dir, journal_name)
            with open(journal_path) as journal_file:
                data: object = json.load(journal_file)
            if not isinstance(data, dict):
                continue
            state = data.get("state", "active")
            if (
                state in {"committing", "commit_cleanup_pending", "committed"}
                and data.get("finalization_phase") == "task_deleted"
            ):
                os.remove(journal_path)


class PostProcessError(Exception):
    def __init__(self, expected_var: object, result_var: object) -> None:
        Exception.__init__(
            self,
            f"Errors found during post process checks. Expected {expected_var}, but instead found {result_var}",
        )
        self.expected_var = expected_var
        self.result_var = result_var
