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

import contextlib
import json
import os
import shutil
import tempfile


class FileOperationTracker:
    """Track destructive file operations for rollback on failure."""

    def __init__(self, logger, journal_dir=None, operation_id=None, task_id=None):
        self._logger = logger
        self._backups = []  # list of (backup_path, original_path)
        self._created_paths = []
        self._journal_dir = journal_dir
        self._operation_id = operation_id
        self._task_id = task_id
        self._state = "active"
        self._finalization_phase = None
        self._journal_path = None
        if journal_dir and operation_id:
            safe_operation_id = str(operation_id).replace(os.sep, "_")
            self._journal_path = os.path.join(journal_dir, f"{safe_operation_id}.json")
            if os.path.exists(self._journal_path):
                raise FileExistsError(f"Unrecovered file-operation journal already exists: {self._journal_path}")

    def _journal_data(self):
        return {
            "version": 1,
            "operation_id": self._operation_id,
            "task_id": self._task_id,
            "state": self._state,
            "finalization_phase": self._finalization_phase,
            "backups": [list(item) for item in self._backups],
            "created_paths": list(self._created_paths),
        }

    def _persist(self):
        if not self._journal_path:
            return
        os.makedirs(self._journal_dir, exist_ok=True)
        fd, temporary_path = tempfile.mkstemp(prefix=".file-operation-", suffix=".tmp", dir=self._journal_dir)
        try:
            with os.fdopen(fd, "w") as journal_file:
                json.dump(self._journal_data(), journal_file, sort_keys=True)
                journal_file.flush()
                os.fsync(journal_file.fileno())
            os.replace(temporary_path, self._journal_path)
        except Exception:
            with contextlib.suppress(OSError):
                os.remove(temporary_path)
            raise

    def record_created(self, filepath):
        """Persist that rollback must remove a newly created destination."""
        filepath = os.path.realpath(filepath)
        if filepath not in self._created_paths:
            self._created_paths.append(filepath)
            self._persist()

    def safe_remove(self, filepath):
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

    def commit(self):
        """Commit file changes while retaining a recovery marker until finalized."""
        self._state = "committing"
        self._persist()
        remaining_backups = []
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
    def finalization_phase(self):
        return self._finalization_phase

    def mark_finalization_phase(self, phase):
        """Persist progress after the destructive file transaction commits."""
        if self._state != "committed":
            return
        self._finalization_phase = str(phase)
        self._persist()

    @classmethod
    def resume_committed(cls, journal_dir, task_id, logger):
        """Load a committed task journal so later finalization phases can replay."""
        if not journal_dir:
            return None
        operation_id = f"task-{task_id}"
        journal_path = os.path.join(journal_dir, f"{operation_id}.json")
        if not os.path.isfile(journal_path):
            return None
        with open(journal_path) as journal_file:
            data = json.load(journal_file)
        if data.get("state") not in {"committing", "commit_cleanup_pending", "committed"}:
            return None
        tracker = cls(logger)
        tracker._journal_dir = journal_dir
        tracker._operation_id = operation_id
        tracker._task_id = task_id
        tracker._journal_path = journal_path
        tracker._state = data.get("state", "committed")
        tracker._finalization_phase = data.get("finalization_phase")
        tracker._backups = [tuple(item) for item in data.get("backups", [])]
        tracker._created_paths = list(data.get("created_paths", []))
        return tracker

    def finalize(self):
        """Remove the recovery marker after the owning task is fully finalized."""
        if self._journal_path and os.path.exists(self._journal_path):
            os.remove(self._journal_path)

    def rollback(self):
        """Restore all backed-up files to their original paths."""
        self._state = "rolling_back"
        self._persist()
        backup_by_original = {os.path.realpath(original): backup for backup, original in self._backups}
        failed = False
        remaining_created_paths = []
        for created_path in reversed(self._created_paths):
            backup_path = backup_by_original.get(os.path.realpath(created_path))
            if backup_path and not os.path.exists(backup_path):
                self._logger.error(
                    "FileOperationTracker: refusing to remove '%s'; required backup '%s' is missing",
                    created_path,
                    backup_path,
                )
                failed = True
                remaining_created_paths.append(created_path)
                continue
            try:
                if os.path.exists(created_path):
                    os.remove(created_path)
            except (OSError, PermissionError) as e:
                self._logger.error("FileOperationTracker: failed to remove created path '%s': %s", created_path, e)
                failed = True
                remaining_created_paths.append(created_path)
        remaining_backups = []
        for backup_path, original_path in reversed(self._backups):
            try:
                if os.path.exists(backup_path):
                    shutil.move(backup_path, original_path)
                    self._logger.info("FileOperationTracker: restored '%s' from backup", original_path)
                else:
                    failed = True
                    remaining_backups.append((backup_path, original_path))
            except (OSError, PermissionError, shutil.Error) as e:
                self._logger.error(
                    "FileOperationTracker: FAILED to restore '%s' from backup '%s': %s", original_path, backup_path, e
                )
                failed = True
                remaining_backups.append((backup_path, original_path))
        self._backups = list(reversed(remaining_backups))
        self._created_paths = list(reversed(remaining_created_paths))
        if failed:
            self._state = "rollback_failed"
            self._persist()
            return False
        self.finalize()
        return True

    @classmethod
    def recover_all(cls, journal_dir, logger):
        """Recover durable file-operation journals left by an interrupted run."""
        result = {"rolled_back_task_ids": [], "committed_task_ids": [], "finalization_task_ids": []}
        if not journal_dir or not os.path.isdir(journal_dir):
            return result

        recovery_errors = []
        for journal_name in sorted(os.listdir(journal_dir)):
            if not journal_name.endswith(".json"):
                continue
            journal_path = os.path.join(journal_dir, journal_name)
            try:
                with open(journal_path) as journal_file:
                    data = json.load(journal_file)
                task_id = data.get("task_id")
                state = data.get("state", "active")
                finalization_phase = data.get("finalization_phase")
                backups = [tuple(item) for item in data.get("backups", [])]
                created_paths = [os.path.realpath(path) for path in data.get("created_paths", [])]

                if state in {"committing", "commit_cleanup_pending", "committed"}:
                    for backup_path, _original_path in backups:
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                    if task_id is not None:
                        target = "committed_task_ids" if finalization_phase == "task_deleted" else "finalization_task_ids"
                        result[target].append(task_id)
                else:
                    missing_backups = [
                        backup_path for backup_path, _original_path in backups if not os.path.exists(backup_path)
                    ]
                    if missing_backups:
                        raise FileNotFoundError(f"required backup is missing: {missing_backups[0]}")
                    for created_path in reversed(created_paths):
                        if os.path.exists(created_path):
                            os.remove(created_path)
                    for backup_path, original_path in reversed(backups):
                        if os.path.exists(backup_path):
                            os.makedirs(os.path.dirname(os.path.abspath(original_path)), exist_ok=True)
                            os.replace(backup_path, original_path)
                    if task_id is not None:
                        result["rolled_back_task_ids"].append(task_id)

                    os.remove(journal_path)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                logger.error("FILE_OPERATION_RECOVERY_FAILED journal=%s error=%s", journal_path, error)
                recovery_errors.append(journal_path)

        if recovery_errors:
            raise RuntimeError(f"Unable to recover {len(recovery_errors)} file-operation journal(s)")

        return result

    @staticmethod
    def finalize_committed(journal_dir):
        """Remove committed markers after their task rows have been reconciled."""
        if not journal_dir or not os.path.isdir(journal_dir):
            return
        for journal_name in sorted(os.listdir(journal_dir)):
            if not journal_name.endswith(".json"):
                continue
            journal_path = os.path.join(journal_dir, journal_name)
            with open(journal_path) as journal_file:
                data = json.load(journal_file)
            state = data.get("state", "active")
            if (
                state in {"committing", "commit_cleanup_pending", "committed"}
                and data.get("finalization_phase") == "task_deleted"
            ):
                os.remove(journal_path)


class PostProcessError(Exception):
    def __init__(self, expected_var, result_var):
        Exception.__init__(
            self,
            f"Errors found during post process checks. Expected {expected_var}, but instead found {result_var}",
        )
        self.expected_var = expected_var
        self.result_var = result_var
