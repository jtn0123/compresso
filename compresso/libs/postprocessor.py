#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
import os
import shutil
import threading
import time

from compresso import config
from compresso.libs import common, history
from compresso.libs.ffprobe_utils import extract_media_metadata
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.metadata import CompressoFileMetadata
from compresso.libs.notifications import Notifications
from compresso.libs.plugins import PluginsHandler
from compresso.libs.task import TaskDataStore

"""

The post-processor handles all tasks carried out on completion of a workers task.
This may be on either success or failure of the task.

The post-processor runs as a single thread, processing completed jobs one at a time.
This prevents conflicting copy operations or deleting a file that is also being post processed.

"""


class PostProcessError(Exception):
    def __init__(self, expected_var, result_var):
        Exception.__init__(self, "Errors found during post process checks. Expected {}, but instead found {}".format(
            expected_var, result_var))
        self.expected_var = expected_var
        self.result_var = result_var


class PostProcessor(threading.Thread):
    """
    PostProcessor

    """

    def __init__(self, data_queues, task_queue, event):
        super(PostProcessor, self).__init__(name='PostProcessor')
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)
        self.event = event
        self.data_queues = data_queues
        self.settings = config.Config()
        self.task_queue = task_queue
        self.abort_flag = threading.Event()
        self.current_task = None
        self._last_destination_files = []
        self.ffmpeg = None
        self.abort_flag.clear()

    def _log(self, message, message2='', level="info"):
        message = common.format_message(message, message2)
        getattr(self.logger, level)(message)

    def stop(self):
        self.abort_flag.set()

    def run(self):
        self._log("Starting PostProcessor Monitor loop...")
        while not self.abort_flag.is_set():
            self.event.wait(1)

            if not self.system_configuration_is_valid():
                self.event.wait(2)
                continue

            # Process completed transcodes (status='processed')
            while not self.abort_flag.is_set() and not self.task_queue.task_list_processed_is_empty():
                self.event.wait(.2)
                self.current_task = self.task_queue.get_next_processed_tasks()
                if self.current_task:
                    self._handle_processed_task()

            # Process approved tasks (status='approved') — finalize file replacement
            while not self.abort_flag.is_set() and not self.task_queue.task_list_approved_is_empty():
                self.event.wait(.2)
                self.current_task = self.task_queue.get_next_approved_tasks()
                if self.current_task:
                    self._handle_approved_task()

        self._log("Leaving PostProcessor Monitor loop...")

    def _handle_processed_task(self):
        """Handle a task that just finished transcoding (status='processed')."""
        # Execute event plugin runners
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type('events.postprocessor_started', {
            'library_id':  self.current_task.get_task_library_id(),
            'task_id':     self.current_task.get_task_id(),
            'task_type':   self.current_task.get_task_type(),
            'cache_path':  self.current_task.get_cache_path(),
            'source_data': self.current_task.get_source_data(),
        })

        try:
            self._log("Post-processing task - {}".format(self.current_task.get_source_abspath()))
        except Exception as e:
            self._log("Exception in fetching task absolute path", message2=str(e), level="exception")

        if self.current_task.get_task_type() == 'local':
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
                                self._log("Size guardrail REJECTED: {:.1f}% (allowed {}-{}%)".format(
                                    ratio_pct, min_pct, max_pct))
                                self.current_task.task.success = False
                                self.current_task.task.save()
                except Exception as e:
                    self._log("Exception in size guardrail check", message2=str(e), level="warning")

            # Determine replacement policy (per-library with global fallback)
            try:
                library = Library(self.current_task.get_task_library_id())
                policy = library.get_replacement_policy()
            except Exception:
                policy = ''
            if not policy:
                policy = 'approval_required' if self.settings.get_approval_required() else 'replace'

            if self.current_task.task.success:
                if policy == 'approval_required':
                    self._stage_for_approval()
                elif policy == 'keep_both':
                    self._finalize_local_task_keep_both()
                else:
                    self._finalize_local_task()
            else:
                self._finalize_local_task()
        else:
            self._finalize_remote_task()

    def _handle_approved_task(self):
        """Handle a task that was approved by the user — finalize file replacement from staging."""
        try:
            self._log("Finalizing approved task - {}".format(self.current_task.get_source_abspath()))
        except Exception as e:
            self._log("Exception in fetching task absolute path", message2=str(e), level="exception")

        self._finalize_local_task()

    def _stage_for_approval(self):
        """
        Stage the transcoded file for user review instead of replacing the original.
        Copies the cache file to the staging directory and sets status to 'awaiting_approval'.
        """
        try:
            cache_path = self.current_task.get_cache_path()
            staging_dir = self.settings.get_staging_path()
            task_id = self.current_task.get_task_id()

            # Create a per-task staging subdirectory
            task_staging_dir = os.path.join(staging_dir, "task_{}".format(task_id))
            os.makedirs(task_staging_dir, exist_ok=True)

            # Copy cache file to staging
            staged_filename = os.path.basename(cache_path)
            staged_path = os.path.join(task_staging_dir, staged_filename)
            shutil.copy2(cache_path, staged_path)

            self._log("Staged transcoded file for approval: {} -> {}".format(cache_path, staged_path))

            # Set the task status to awaiting_approval (keeps cache and task alive)
            self.current_task.set_status('awaiting_approval')

        except Exception as e:
            self._log("Exception in staging file for approval", message2=str(e), level="exception")
            # Fall back to normal processing on staging failure
            self._finalize_local_task()

    def _finalize_local_task(self):
        """Run the standard local task postprocessing: file move, history, metadata, cleanup."""
        try:
            self.post_process_file()
        except Exception as e:
            self._log("Exception in post-processing local task file",
                      message2=str(e), level="exception")
        try:
            self.write_history_log()
        except Exception as e:
            self._log("Exception in writing history log", message2=str(e), level="exception")
        try:
            self.commit_task_metadata()
        except Exception as e:
            self._log("Exception in committing task metadata", message2=str(e), level="exception")
        try:
            # Clean up the staging directory for this task if it exists
            self._cleanup_staging_files()
            # Remove file from task queue
            self.current_task.delete()
        except Exception as e:
            self._log("Exception in removing task from task list", message2=str(e), level="exception")

    def _finalize_local_task_keep_both(self):
        """Finalize task but keep original — save output alongside with codec suffix."""
        try:
            dest_data = self.current_task.get_destination_data()
            source_data = self.current_task.get_source_data()
            if dest_data['abspath'] == source_data['abspath']:
                # Same filename — add codec suffix to avoid overwriting
                base, ext = os.path.splitext(dest_data['abspath'])
                try:
                    meta = extract_media_metadata(self.current_task.get_cache_path())
                    codec = meta.get('codec', 'transcoded')
                except Exception:
                    codec = 'transcoded'
                new_path = "{}.{}{}".format(base, codec, ext)
                counter = 1
                while os.path.exists(new_path) and counter <= 100:
                    new_path = "{}.{}.{}{}".format(base, codec, counter, ext)
                    counter += 1
                self.current_task.set_destination_path(new_path)
        except Exception as e:
            self._log("Exception in keep_both path adjustment", message2=str(e), level="warning")
        self._finalize_local_task()

    def _finalize_remote_task(self):
        """Run the standard remote task postprocessing."""
        try:
            self.post_process_remote_file()
        except Exception as e:
            self._log("Exception in post-processing remote task file",
                      message2=str(e), level="exception")
        try:
            self.dump_history_log()
        except Exception as e:
            self._log("Exception in dumping history log for remote task",
                      message2=str(e), level="exception")
        try:
            self.current_task.set_status('complete')
        except Exception as e:
            self._log("Exception in marking remote task as complete",
                      message2=str(e), level="exception")

    def _cleanup_staging_files(self):
        """Remove the staging directory for the current task if it exists."""
        try:
            task_id = self.current_task.get_task_id()
            staging_dir = self.settings.get_staging_path()
            task_staging_dir = os.path.join(staging_dir, "task_{}".format(task_id))
            if os.path.exists(task_staging_dir):
                self._log("Removing staging directory '{}'".format(task_staging_dir))
                shutil.rmtree(task_staging_dir)
        except Exception as e:
            self._log("Exception while cleaning up staging files", message2=str(e), level="warning")

    def system_configuration_is_valid(self):
        """
        Check and ensure the system configuration is correct for running

        :return:
        """
        valid = True
        plugin_handler = PluginsHandler()
        if plugin_handler.get_incompatible_enabled_plugins():
            valid = False
        if not Library.within_library_count_limits():
            valid = False
        return valid

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
        if self.current_task.task.success:
            # Run a postprocess file movement on the cache file for each plugin that configures it

            # Fetch all 'postprocessor.file_move' plugin modules
            plugin_modules = plugin_handler.get_enabled_plugin_modules_by_type('postprocessor.file_move',
                                                                               library_id=library_id)

            # Check if the source file needs to be removed by default (only if it does not match the destination file)
            remove_source_file = False
            if source_data['abspath'] != destination_data['abspath']:
                remove_source_file = True

            # Set initial data (some fields will be overwritten further down)
            # - 'library_id'                - The library ID for this task
            # - 'source_data'               - Dictionary of data pertaining to the source file
            # - 'remove_source_file'        - True to remove the original file (default is True if file name has changed)
            # - 'copy_file'                 - True to run a plugin initiated file copy (default is False unless the plugin says otherwise)
            # - 'file_in'                   - Source path to copy from (if 'copy_file' is True)
            # - 'file_out'                  - Destination path to copy to (if 'copy_file' is True)
            # - 'run_default_file_copy'     - Prevent the final Compresso post-process file movement (if different from the original file name)
            data = {
                'library_id':            library_id,
                'task_id':               self.current_task.get_task_id(),
                'source_data':           None,
                'remove_source_file':    remove_source_file,
                'copy_file':             None,
                'file_in':               None,
                'file_out':              None,
                'run_default_file_copy': True,
            }

            for plugin_module in plugin_modules:
                # Always set source_data to the original file's source_data
                data["source_data"] = source_data
                # Always set copy_file to False
                data["copy_file"] = False
                # Always set file in to cache path
                data["file_in"] = cache_path
                # Always set file out to destination data absolute path
                data["file_out"] = destination_data.get('abspath')

                # Run plugin to update data
                if not plugin_handler.exec_plugin_runner(data, plugin_module.get('plugin_id'), 'postprocessor.file_move'):
                    # Do not continue with this plugin module's loop
                    continue

                if data.get('copy_file'):
                    # Copy the file
                    file_in = os.path.abspath(data.get('file_in'))
                    file_out = os.path.abspath(data.get('file_out'))
                    if not self.__copy_file(file_in, file_out, destination_files, plugin_module.get('plugin_id')):
                        file_move_processes_success = False
                else:
                    self._log("Plugin did not request a file copy ({})".format(
                        plugin_module.get('plugin_id')), level='debug')

            # Compresso's default file movement process
            # Only carry out final post-processor file moments if all others were successful
            if file_move_processes_success and data.get('run_default_file_copy'):
                # Run the default post-process file movement.
                # This will always move the file back to the original location.
                # If that original location is the same file name, it will overwrite the original file.
                if destination_data.get('abspath') == source_data.get('abspath'):
                    # Only run the final file copy to overwrite the source file if the remove_source_file flag was never set
                    # The remove_source_file flag will remove the source file in later lines after this copy operation,
                    #   so if we did copy the file here, it would be a waste of time
                    if not data.get('remove_source_file'):
                        if not self.__copy_file(cache_path, destination_data.get('abspath'), destination_files, 'DEFAULT',
                                                move=True):
                            file_move_processes_success = False
                elif not self.__copy_file(cache_path, destination_data.get('abspath'), destination_files, 'DEFAULT',
                                          move=True):
                    file_move_processes_success = False

            # Source file removal process
            # Only run if all final post-processor file moments were successful
            if file_move_processes_success:
                # Check if the remove source flag is still True after all plugins have run. If so, we will remove the source file
                if data.get('remove_source_file'):
                    # Only carry out a source removal if the file exists and the final copy was also successful
                    if file_move_processes_success and os.path.exists(source_data.get('abspath')):
                        self._log("Removing source: {}".format(source_data.get('abspath')))
                        os.remove(source_data.get('abspath'))
                    else:
                        self._log("Keeping source file '{}'. Not all postprocessor file movement functions completed.".format(
                            source_data.get('abspath')), level="warning")

            # Log a final error if not all file moments were successful
            if not file_move_processes_success:
                self._log(
                    "Error while running postprocessor file movement on file '{}'. Not all postprocessor file movement functions completed.".format(
                        cache_path), level="error")

        else:
            self._log("Skipping file movement post-processor as the task was not successful '{}'".format(cache_path),
                      level='warning')

        # Fetch all 'postprocessor.task_result' plugin modules
        plugin_modules = plugin_handler.get_enabled_plugin_modules_by_type(
            'postprocessor.task_result', library_id=library_id)

        for plugin_module in plugin_modules:
            data = {
                'library_id':                  library_id,
                "task_id":                     self.current_task.get_task_id(),
                "task_type":                   self.current_task.get_task_type(),
                'final_cache_path':            cache_path,
                'task_processing_success':     self.current_task.get_task_success(),
                'file_move_processes_success': file_move_processes_success,
                'destination_files':           destination_files,
                'source_data':                 source_data,
                'start_time':                  self.current_task.get_start_time(),
                'finish_time':                 self.current_task.get_finish_time(),
            }

            # Run plugin to update data
            if not plugin_handler.exec_plugin_runner(data, plugin_module.get('plugin_id'), 'postprocessor.task_result'):
                # Do not continue with this plugin module's loop
                continue

        # Cleanup cache files
        self.__cleanup_cache_files(cache_path)
        self._last_destination_files = destination_files

    def post_process_remote_file(self):
        """
        Process remote files.
        Remote files are not processed by plugins. They are just sent back to the OG installation and then the cache files are cleaned up here.
        A remote file's source_data will be the download path where this installation initial received and stored it.

        TODO: Should we move remote tasks to a permanent download location within the cache path? Possibly not...

        :return:
        """
        # Read current task data
        cache_path = self.current_task.get_cache_path()
        source_data = self.current_task.get_source_data()
        destination_data = self.current_task.get_destination_data()
        def_cache_path = self.settings.get_cache_path()

        remove_source_file = True
        if def_cache_path not in destination_data['abspath']:
            remove_source_file = False

        self._log("Cache path: {}".format(def_cache_path), level='debug')
        self._log(
            "Remote source: {}, destination file: {}.".format(source_data['abspath'], destination_data['abspath']), level='debug')
        self._log("Task cache path: {}".format(cache_path), level='debug')

        # Remove the source
        if os.path.exists(source_data.get('abspath')) and remove_source_file:
            self._log("Removing remote source: {}".format(source_data.get('abspath')))
            os.remove(source_data.get('abspath'))
        elif os.path.exists(source_data.get('abspath')) and not remove_source_file:
            self._log("Keep remote source: {}, remote file source is in library and not cache.".format(
                source_data.get('abspath')))
        else:
            self._log("Remote source file '{}' does not exist!".format(source_data.get('abspath')), level="warning")

        # Copy final cache file to original directory
        random_string = '{}-{}'.format(common.random_string(), int(time.time()))
        library_tdir = os.path.join(os.path.dirname(source_data.get('abspath')),
                                    "compresso_remote_pending_library-" + random_string)
        cache_tdir = os.path.join(def_cache_path, "compresso_remote_pending_library-" + random_string)

        if os.path.exists(cache_path) and remove_source_file:
            self.__copy_file(cache_path, destination_data.get('abspath'), [], 'DEFAULT', move=True)
            tdir = cache_tdir
        elif os.path.exists(cache_path) and not remove_source_file:
            try:
                tdir = library_tdir
                os.mkdir(library_tdir)
                capture_success = self.__copy_file(cache_path, os.path.join(
                    library_tdir, os.path.basename(cache_path)), [], 'DEFAULT', move=True)
                if not capture_success:
                    raise Exception("Failed to copy back to network share")
            except Exception:
                os.mkdir(cache_tdir)
                self.__copy_file(cache_path, os.path.join(
                    cache_tdir, os.path.basename(cache_path)), [], 'DEFAULT', move=True)
                tdir = cache_tdir
            finally:
                self._log("tdir: {}".format(tdir), level='debug')
        else:
            self._log("Final cache file '{}' does not exist!".format(cache_path), level="warning")

        # Cleanup cache files
        self.__cleanup_cache_files(cache_path)

        # Modify the task abspath - this may be different now
        if remove_source_file:
            self.current_task.modify_path(destination_data.get('abspath'))
        else:
            self.current_task.modify_path(os.path.join(tdir, os.path.basename(cache_path)))

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
            self._log("Removing task cache directory '{}'".format(task_cache_directory))
            try:
                shutil.rmtree(task_cache_directory)
            except Exception as e:
                self._log("Exception while clearing cache path '{}'".format(str(e)), level='error')

    def __copy_file(self, file_in, file_out, destination_files, plugin_id, move=False):
        if move:
            self._log("Move file triggered by ({}) {} --> {}".format(plugin_id, file_in, file_out))
        else:
            self._log("Copy file triggered by ({}) {} --> {}".format(plugin_id, file_in, file_out))

        file_move_processes_success = True
        try:
            # Ensure the src and dst are not the same file
            if os.path.exists(file_out) and os.path.samefile(file_in, file_out):
                self._log("The file_in and file_out path are the same file. Nothing will be done! '{}'".format(file_in),
                          level="warning")
                return False

            # Get a checksum prior to copy
            if not os.path.exists(file_in):
                self._log("The file_in path does not exist! '{}'".format(file_in), level="warning")
                self.event.wait(1)
            self._log("Fetching checksum of source file '{}'.".format(file_in), level='debug')

            # Use a '.part' suffix for the file movement, then rename it after
            part_file_out = os.path.join("{}.compresso.part".format(file_out))

            # Carry out the file movement
            if move:
                self._log("Moving file '{}' --> '{}'.".format(file_in, part_file_out), level='debug')
                if os.path.exists(part_file_out):
                    os.remove(part_file_out)
                shutil.move(file_in, part_file_out, copy_function=shutil.copyfile)
            else:
                self._log("Copying file '{}' --> '{}'.".format(file_in, part_file_out), level='debug')
                shutil.copyfile(file_in, part_file_out)

            # Remove dest file if it already exists (required only for moves)
            if os.path.exists(file_out):
                self._log("The file_out path already exists. Removing file '{}'".format(file_out), level="debug")
                os.remove(file_out)

            # Move file from part to final destination
            self._log("Renaming file '{}' --> '{}'.".format(part_file_out, file_out), level='debug')
            shutil.move(part_file_out, file_out, copy_function=shutil.copyfile)
            # Write final path to destination_files list
            destination_files.append(file_out)
            # Mark move process a success
            return True
        except Exception as e:
            self.logger.error("POSTPROCESS_FILE_COPY_FAILED source=%s dest=%s", file_in, file_out)
            self._log("Exception while copying file {} to {}:".format(file_in, file_out),
                      message2=str(e), level="exception")
            file_move_processes_success = False

        return file_move_processes_success

    def write_history_log(self):
        """
        Record task history

        :return:
        """
        self._log("Writing task history log.", level='debug')
        history_logging = history.History()
        task_dump = self.current_task.task_dump()
        destination_data = self.current_task.get_destination_data()
        source_data = self.current_task.get_source_data()

        # If task fails, the add a notification that a task has failed
        if not self.current_task.task.success:
            notifications = Notifications()
            notifications.add(
                {
                    'uuid':       'newFailedTask',
                    'type':       'error',
                    'icon':       'report',
                    'label':      'failedTaskLabel',
                    'message':    'You have a new failed task in your completed tasks list',
                    'navigation': {
                        'push':   '/ui/dashboard',
                        'events': [
                            'completedTasksShowFailed',
                        ],
                    },
                })

        self._log_completed_task_data(task_dump, source_data, destination_data)

        # Capture destination file size for compression stats
        destination_size = 0
        dest_path = ''
        if task_dump.get('task_success', False) and destination_data:
            dest_path = destination_data.get('abspath', '')
            if dest_path and os.path.exists(dest_path):
                try:
                    destination_size = os.path.getsize(dest_path)
                except OSError:
                    self.logger.warning("POSTPROCESS_DESTINATION_SIZE_UNAVAILABLE path=%s", dest_path)
                    self._log("Could not get destination file size for '{}'".format(dest_path), level='warning')

        # Extract media metadata for compression stats (codec, resolution, container)
        # Always extract source metadata (even on failure, for stats tracking)
        source_meta = {}
        dest_meta = {}
        source_abspath = source_data.get('abspath', '') if source_data else ''
        if source_abspath and os.path.exists(source_abspath):
            try:
                source_meta = extract_media_metadata(source_abspath)
            except Exception as e:
                self.logger.warning("POSTPROCESS_SOURCE_METADATA_UNAVAILABLE path=%s", source_abspath)
                self._log("Could not extract source metadata: {}".format(e), level='warning')
        # Destination metadata only on success
        if task_dump.get('task_success', False):
            if dest_path and os.path.exists(dest_path):
                try:
                    dest_meta = extract_media_metadata(dest_path)
                except Exception as e:
                    self._log("Could not extract destination metadata: {}".format(e), level='debug')

        history_logging.save_task_history(
            {
                'task_label':            task_dump.get('task_label', ''),
                'abspath':               task_dump.get('abspath', ''),
                'task_success':          task_dump.get('task_success', False),
                'start_time':            task_dump.get('start_time', ''),
                'finish_time':           task_dump.get('finish_time', ''),
                'processed_by_worker':   task_dump.get('processed_by_worker', ''),
                'log':                   task_dump.get('log', ''),
                'source_size':           task_dump.get('source_size', 0),
                'destination_size':      destination_size,
                'library_id':            task_dump.get('library_id', 1),
                'source_codec':          source_meta.get('codec', ''),
                'destination_codec':     dest_meta.get('codec', ''),
                'source_resolution':     source_meta.get('resolution', ''),
                'source_container':      source_meta.get('container', ''),
                'destination_container': dest_meta.get('container', ''),
            }
        )

        # Bump analysis cache version so frontend knows estimates may have changed
        try:
            from compresso.libs.unmodels import LibraryAnalysisCache
            lib_id = task_dump.get('library_id', 1)
            cache_entry = LibraryAnalysisCache.get_or_none(LibraryAnalysisCache.library_id == lib_id)
            if cache_entry:
                cache_entry.version += 1
                cache_entry.save()
        except Exception:
            pass  # Non-critical — don't break postprocessor for cache bump

        # Execute event plugin runners
        plugin_handler = PluginsHandler()
        plugin_handler.run_event_plugins_for_plugin_type('events.postprocessor_complete', {
            'library_id':          self.current_task.get_task_library_id(),
            'task_id':             self.current_task.get_task_id(),
            'task_type':           self.current_task.get_task_type(),
            'source_data':         self.current_task.get_source_data(),
            'destination_data':    self.current_task.get_destination_data(),
            'task_success':        task_dump.get('task_success', False),
            'start_time':          task_dump.get('start_time', ''),
            'finish_time':         task_dump.get('finish_time', ''),
            'processed_by_worker': task_dump.get('processed_by_worker', ''),
            'log':                 task_dump.get('log', ''),
        })

    def commit_task_metadata(self):
        """
        Commit task metadata after all postprocessor runners have finished.
        """
        source_data = self.current_task.get_source_data()
        destination_data = self.current_task.get_destination_data()
        task_success = self.current_task.get_task_success()
        destination_files = list(self._last_destination_files or [])
        if not destination_files and destination_data:
            destination_files = [destination_data.get('abspath')]
        committed = CompressoFileMetadata.commit_task(
            task_id=self.current_task.get_task_id(),
            task_success=task_success,
            source_path=source_data.get('abspath'),
            destination_paths=destination_files,
        )
        if committed:
            self._log("Committed file metadata entries: {}".format(committed), level='debug')
        return committed

    def dump_history_log(self):
        self._log("Dumping remote task history log.", level='debug')
        task_dump = self.current_task.task_dump()
        destination_data = self.current_task.get_destination_data()

        # Dump history log & task state as metadata in the file's path
        tasks_data_file = os.path.join(os.path.dirname(destination_data.get('abspath')), 'data.json')
        task_state = TaskDataStore.export_task_state(self.current_task.get_task_id())
        result = common.json_dump_to_file(
            {
                'task_label':          task_dump.get('task_label', ''),
                'abspath':             task_dump.get('abspath', ''),
                'task_success':        task_dump.get('task_success', False),
                'start_time':          task_dump.get('start_time', ''),
                'finish_time':         task_dump.get('finish_time', ''),
                'processed_by_worker': task_dump.get('processed_by_worker', ''),
                'log':                 task_dump.get('log', ''),
                'checksum':            'UNKNOWN',
                'task_state':          task_state,
            }, tasks_data_file)
        if not result['success']:
            for message in result['errors']:
                self._log("Exception:", message2=str(message), level="exception")
            raise Exception("Exception in dumping completed task data to file")

    def _log_completed_task_data(self, task_dump, source_data, destination_data):
        status = "success" if task_dump.get('task_success', False) else "failed"
        start_time = task_dump.get('start_time', '')
        finish_time = task_dump.get('finish_time', '')
        command_error_log_tail = ""
        if status != "success":
            task_log = task_dump.get('log', '')
            if task_log:
                command_error_log_tail = "\n".join(task_log.splitlines()[-20:])
        try:
            library_id = self.current_task.get_task_library_id()
            library_name = self.current_task.get_task_library_name()
        except Exception:
            library_id = None
            library_name = None

        CompressoLogging.data(
            "completed_task",
            data_search_key=f"{library_id} | {finish_time} | {source_data.get('abspath', '')}",
            task_id=self.current_task.get_task_id(),
            task_type=self.current_task.get_task_type(),
            library_id=library_id,
            library_name=library_name,
            status=status,
            start_time=start_time,
            finish_time=finish_time,
            source_file=source_data.get('basename', ''),
            source_path=source_data.get('abspath', ''),
            dest_file=destination_data.get('basename', ''),
            dest_path=destination_data.get('abspath', ''),
            command_error_log_tail=command_error_log_tail,
        )
