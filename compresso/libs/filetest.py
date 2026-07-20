#!/usr/bin/env python3

"""
compresso.filetest.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     28 Mar 2021, (7:28 PM)

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
import queue
import subprocess
import threading
from copy import deepcopy

import peewee

from compresso import config
from compresso.libs import history
from compresso.libs.logs import CompressoLogging
from compresso.libs.plugins import PluginsHandler


class FileTest:
    """
    FileTest

    Object to manage tests carried out on files discovered
    during a library scan or inode event

    """

    def __init__(self, library_id: int):
        self.settings = config.Config()
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)  # type: ignore[name-defined]

        # Init plugins
        self.library_id = library_id
        self.plugin_handler = PluginsHandler()
        self.plugin_modules = self.plugin_handler.get_enabled_plugin_modules_by_type(
            "library_management.file_test", library_id=library_id
        )

        # Hoist the library codec pre-filter configuration out of the per-file
        # path: one DB fetch per FileTest instance instead of one per file.
        self.target_codecs = []
        self.skip_codecs = []
        try:
            from compresso.libs.library import Library

            library = Library(self.library_id)
            self.target_codecs = [c.lower() for c in (library.get_target_codecs() or [])]
            self.skip_codecs = [c.lower() for c in (library.get_skip_codecs() or [])]
        except (ValueError, AttributeError, TypeError, peewee.PeeweeException) as e:
            self.logger.debug("Codec pre-filter config unavailable for library %s: %s", library_id, str(e))
        except Exception as e:
            self.logger.debug("Codec pre-filter config unexpected error for library %s: %s", library_id, str(e))

    def file_failed_in_history(self, path):
        """
        Check if file has already failed in history

        :return:
        """
        return history.History().failed_path_exists(path)

    def file_in_compresso_ignore_lockfile(self, path):
        """
        Check if folder contains a '.compressoignore' lockfile

        :return:
        """
        # Get file parent directory
        dirname = os.path.dirname(path)
        # Check if lockfile (.compressoignore) exists
        compresso_ignore_file = os.path.join(dirname, ".compressoignore")
        if os.path.exists(compresso_ignore_file):
            # Get file basename
            basename = os.path.basename(path)
            # Read the file and check for any entry with this file name
            with open(compresso_ignore_file) as f:
                for line in f:
                    entry = line.strip()
                    if not entry or entry.startswith("#"):
                        continue
                    if basename == entry:
                        return True
        return False

    def should_file_be_added_to_task_list(self, path):
        """
        Test if this file needs to be added to the task list

        :return:
        """
        return_value = None
        decision_plugin = None
        file_issues = []

        # Cheap checks run first: the .compressoignore lockfile read and the
        # indexed failed-history lookup are near-free, while the codec
        # pre-filter below can fork an ffprobe process per file.

        # Per-directory .compressoignore lockfile — users can opt files out
        # of processing without modifying server config.
        if self.file_in_compresso_ignore_lockfile(path):
            file_issues.append(
                {
                    "id": "compressoignore",
                    "message": f"File found in compresso ignore file - '{path}'",
                }
            )
            return_value = False

        # Check if file has failed in history (indexed lookup — still cheap).
        if self.file_failed_in_history(path):
            file_issues.append(
                {
                    "id": "blacklisted",
                    "message": f"File found already failed in history - '{path}'",
                }
            )
            return_value = False

        # Codec pre-filter (before plugins, for speed); uses the library codec
        # configuration hoisted into __init__.
        if return_value is None and (self.target_codecs or self.skip_codecs):
            from compresso.libs.ffprobe_utils import extract_media_metadata

            try:
                meta = extract_media_metadata(path)
                file_codec = meta.get("codec", "").lower()
                # Strip "(estimated)" suffix from codec hint
                if " (estimated)" in file_codec:
                    file_codec = file_codec.replace(" (estimated)", "")
                if file_codec:
                    if self.skip_codecs and file_codec in self.skip_codecs:
                        return (
                            False,
                            [{"id": "codec_skip", "message": f"Codec '{file_codec}' in skip list — '{path}'"}],
                            0,
                            None,
                        )
                    if self.target_codecs and file_codec not in self.target_codecs:
                        return (
                            False,
                            [{"id": "codec_target", "message": f"Codec '{file_codec}' not in target list — '{path}'"}],
                            0,
                            None,
                        )
            except (subprocess.SubprocessError, OSError, json.JSONDecodeError, ValueError) as e:
                self.logger.debug("Codec pre-filter probe failed for '%s': %s", path, str(e))
            except Exception as e:
                self.logger.debug("Codec pre-filter probe unexpected error for '%s': %s", path, str(e))

        # Only run checks with plugins if other tests were not conclusive
        priority_score_modification = 0
        if return_value is None:
            # Set the initial data with just the priority score.
            data = {
                "priority_score": 0,
                "shared_info": {},
            }
            # Run tests against plugins
            for plugin_module in self.plugin_modules:
                data["library_id"] = self.library_id
                data["path"] = path
                data["issues"] = deepcopy(file_issues)
                data["add_file_to_pending_tasks"] = None

                # Run plugin to update data
                if not self.plugin_handler.exec_plugin_runner(
                    data, plugin_module.get("plugin_id"), "library_management.file_test"
                ):
                    continue

                # Append any file issues found during previous tests
                file_issues = data.get("issues")

                # Set the return_value based on the plugin results
                # If the add_file_to_pending_tasks returned an answer (True/False) then break the loop.
                # No need to continue.
                if data.get("add_file_to_pending_tasks") is not None:
                    return_value = data.get("add_file_to_pending_tasks")
                    decision_plugin = {
                        "plugin_id": plugin_module.get("plugin_id"),
                        "plugin_name": plugin_module.get("name"),
                    }
                    break
            # Set the priority score modification
            priority_score_modification = data.get("priority_score", 0)

        return return_value, file_issues, priority_score_modification, decision_plugin


class FileTesterThread(threading.Thread):
    def __init__(self, name, files_to_test, files_to_process, status_updates, library_id, event):
        super().__init__(name=name)
        self.settings = config.Config()
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)
        self.event = event
        self.files_to_test = files_to_test
        self.files_to_process = files_to_process
        self.library_id = library_id
        self.status_updates = status_updates
        self.abort_flag = threading.Event()
        self.abort_flag.clear()
        self._testing_lock = threading.Lock()
        self._currently_testing = False

    def stop(self):
        self.abort_flag.set()

    def _set_testing_state(self, state):
        with self._testing_lock:
            self._currently_testing = state

    def is_testing_file(self):
        with self._testing_lock:
            return self._currently_testing

    def run(self):
        self.logger.info("Starting %s", self.name)
        file_test = FileTest(self.library_id)
        plugin_handler = PluginsHandler()
        while not self.abort_flag.is_set():
            try:
                # Block briefly for the next queued file. A short timeout (not
                # a long idle sleep) keeps testers responsive the moment the
                # scanner enqueues the next directory's files, while still
                # re-checking the abort flag regularly.
                next_file = self.files_to_test.get(timeout=0.25)
                self._set_testing_state(True)
                self.status_updates.put(next_file)
            except queue.Empty:
                self._set_testing_state(False)
                continue
            except (AttributeError, TypeError, OSError):
                self.logger.exception("Exception in fetching library scan result for path %s:", self.name)
                self._set_testing_state(False)
                continue

            # Test file to be added to task list. Add it if required
            try:
                result, issues, priority_score, _ = file_test.should_file_be_added_to_task_list(next_file)
                # Log any error messages
                for issue in issues:
                    if type(issue) is dict:
                        self.logger.info(issue.get("message"))
                    else:
                        self.logger.info(issue)
                # If file needs to be added, then add it
                if result:
                    self.add_path_to_queue(
                        {
                            "path": next_file,
                            "priority_score": priority_score,
                        }
                    )
                    # Execute event plugin runners (only when added to queue)
                    plugin_handler.run_event_plugins_for_plugin_type(
                        "events.file_queued",
                        {
                            "library_id": self.library_id,
                            "file_path": next_file,
                            "priority_score": priority_score,
                            "issues": issues,
                        },
                    )

            except UnicodeEncodeError:
                self.logger.warning("File contains Unicode characters that cannot be processed. Ignoring.")
            except (OSError, PermissionError):
                self.logger.exception("File system error testing file path in %s. Ignoring.", self.name)
            except Exception:
                self.logger.exception("Exception testing file path in %s. Ignoring.", self.name)
            finally:
                self._set_testing_state(False)
                self.files_to_test.task_done()

        self.logger.info("Exiting %s", self.name)

    def add_path_to_queue(self, item):
        self.files_to_process.put(item)
