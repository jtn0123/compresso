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
import os
import shutil


class FileOperationTracker:
    """Track destructive file operations for rollback on failure."""

    def __init__(self, logger):
        self._logger = logger
        self._backups = []  # list of (backup_path, original_path)

    def safe_remove(self, filepath):
        """Back up a file before removing it, enabling rollback."""
        if not os.path.exists(filepath):
            return
        backup_path = filepath + '.compresso.bak'
        try:
            shutil.copy2(filepath, backup_path)
            self._backups.append((backup_path, filepath))
            os.remove(filepath)
        except (OSError, PermissionError, shutil.Error) as e:
            self._logger.warning("FileOperationTracker: failed to back up '%s': %s", filepath, e)
            raise

    def commit(self):
        """Remove all backups -- operations are finalized."""
        for backup_path, _ in self._backups:
            try:
                if os.path.exists(backup_path):
                    os.remove(backup_path)
            except (OSError, PermissionError) as e:
                self._logger.warning("FileOperationTracker: failed to remove backup '%s': %s", backup_path, e)
        self._backups.clear()

    def rollback(self):
        """Restore all backed-up files to their original paths."""
        for backup_path, original_path in reversed(self._backups):
            try:
                if os.path.exists(backup_path):
                    shutil.move(backup_path, original_path)
                    self._logger.info("FileOperationTracker: restored '%s' from backup", original_path)
            except (OSError, PermissionError, shutil.Error) as e:
                self._logger.error("FileOperationTracker: FAILED to restore '%s' from backup '%s': %s",
                                   original_path, backup_path, e)
        self._backups.clear()


class PostProcessError(Exception):
    def __init__(self, expected_var, result_var):
        Exception.__init__(
            self,
            f"Errors found during post process checks. Expected {expected_var},"
            f" but instead found {result_var}",
        )
        self.expected_var = expected_var
        self.result_var = result_var
