#!/usr/bin/env python3

"""
compresso.test_taskhandler.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     08 May 2020, (12:28 PM)

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
import tempfile
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.taskhandler import TaskHandler
from compresso.libs.unmodels.tasks import Tasks
from tests.support_.test_data import data_queues, mock_jobqueue_class


class TestClass:
    """
    TestClass

    Test the TaskHandler object

    """

    db_connection = None

    def setup_class(self):
        """
        Setup the class state for pytest

        :return:
        """
        self.project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_queues = data_queues.data_queues
        self.scheduledtasks = self.data_queues["scheduledtasks"]
        self.inotifytasks = self.data_queues["inotifytasks"]
        self.progress_reports = self.data_queues["progress_reports"]
        self.task_queue = mock_jobqueue_class.MockJobQueue()
        self.event = None
        self.task_handler = None

        # Create temp config path
        config_path = tempfile.mkdtemp(prefix="compresso_tests_")

        # Create connection to a test DB (use temp file, not :memory:, for sqliteq compatibility)
        self.db_file = os.path.join(config_path, "test_taskhandler.db")
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(config_path, "migrations"),
        }
        from compresso.libs.unmodels.lib import Database

        self.db_connection = Database.select_database(database_settings)

        # Create required tables
        self.db_connection.create_tables([Tasks])
        time.sleep(0.5)

        # import config
        from compresso import config

        self.settings = config.Config(config_path=config_path)
        self.settings.set_config_item("debugging", True, save_settings=False)

    def teardown_class(self):
        """
        Teardown any state that was previously setup with a call to
        setup_class.

        :return:
        """

    def setup_method(self):
        """
        Setup any state tied to the execution of the given method in a
        class.
        setup_method is invoked for every test method of a class.

        :return:
        """
        self.event = threading.Event()
        self.task_handler = TaskHandler(self.data_queues, self.task_queue, self.event)
        self.task_handler.daemon = True
        self.task_handler.start()
        self.task_queue.added_item = None

    def teardown_method(self):
        """
        Teardown any state that was previously setup with a setup_method
        call.

        :return:
        """
        self.task_handler.stop()
        self.task_handler.join()

    @pytest.mark.integrationtest
    def test_task_handler_runs_as_a_thread(self):
        assert self.task_handler.is_alive()

    @pytest.mark.integrationtest
    def test_task_handler_thread_can_stop_in_less_than_two_seconds(self):
        self.event.set()
        self.task_handler.stop()
        time.sleep(2)
        assert not self.task_handler.is_alive()

    @pytest.mark.integrationtest
    @patch("compresso.libs.taskhandler.PluginsHandler")
    def test_task_handler_can_process_scheduled_tasks_queue(self, mock_plugin_handler):
        """Scheduled tasks queue items (dicts) are added to the Tasks DB table."""
        mock_plugin_handler.return_value = MagicMock()

        # Create a real temp file so os.path.getsize works
        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            test_path = f.name

        try:
            Tasks.delete().execute()
            time.sleep(0.2)

            item = {
                "pathname": test_path,
                "library_id": 1,
                "priority_score": 0,
            }
            self.scheduledtasks.put(item)
            self.task_handler.process_scheduledtasks_queue()
            time.sleep(0.5)

            abspath = os.path.abspath(test_path)
            task_row = Tasks.select().where(Tasks.abspath == abspath)
            assert task_row.count() == 1
            assert task_row.get().library_id == 1
        finally:
            Tasks.delete().execute()
            os.unlink(test_path)

    @pytest.mark.integrationtest
    @patch("compresso.libs.taskhandler.PluginsHandler")
    def test_task_handler_can_process_inotify_tasks_queue(self, mock_plugin_handler):
        """Inotify tasks queue items (dicts) are added to the Tasks DB table."""
        mock_plugin_handler.return_value = MagicMock()

        # Create a real temp file so os.path.getsize works
        with tempfile.NamedTemporaryFile(suffix=".3gp", delete=False) as f:
            test_path = f.name

        try:
            Tasks.delete().execute()
            time.sleep(0.2)

            item = {
                "pathname": test_path,
                "library_id": 1,
                "priority_score": 0,
            }
            self.inotifytasks.put(item)
            self.task_handler.process_inotifytasks_queue()
            time.sleep(0.5)

            abspath = os.path.abspath(test_path)
            task_row = Tasks.select().where(Tasks.abspath == abspath)
            assert task_row.count() == 1
            assert task_row.get().library_id == 1
        finally:
            Tasks.delete().execute()
            os.unlink(test_path)

    @pytest.mark.integrationtest
    @patch("compresso.libs.taskhandler.PluginsHandler")
    def test_task_handler_skips_duplicate_scheduled_tasks(self, mock_plugin_handler):
        mock_plugin_handler.return_value = MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            test_path = f.name

        try:
            Tasks.delete().execute()
            time.sleep(0.2)

            item = {
                "pathname": test_path,
                "library_id": 1,
                "priority_score": 0,
            }
            self.scheduledtasks.put(item)
            self.scheduledtasks.put(item)
            self.task_handler.process_scheduledtasks_queue()
            time.sleep(0.5)

            abspath = os.path.abspath(test_path)
            task_row = Tasks.select().where(Tasks.abspath == abspath)
            assert task_row.count() == 1
        finally:
            Tasks.delete().execute()
            os.unlink(test_path)

    @pytest.mark.integrationtest
    @patch("compresso.libs.taskhandler.PluginsHandler")
    def test_task_handler_skips_duplicate_inotify_tasks(self, mock_plugin_handler):
        mock_plugin_handler.return_value = MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as f:
            test_path = f.name

        try:
            Tasks.delete().execute()
            time.sleep(0.2)

            item = {
                "pathname": test_path,
                "library_id": 1,
                "priority_score": 0,
            }
            self.inotifytasks.put(item)
            self.inotifytasks.put(item)
            self.task_handler.process_inotifytasks_queue()
            time.sleep(0.5)

            abspath = os.path.abspath(test_path)
            task_row = Tasks.select().where(Tasks.abspath == abspath)
            assert task_row.count() == 1
        finally:
            Tasks.delete().execute()
            os.unlink(test_path)

    @pytest.mark.integrationtest
    @patch("compresso.libs.taskhandler.PluginsHandler")
    def test_task_handler_restart_preserves_dedupe_and_accepts_new_work(self, mock_plugin_handler):
        mock_plugin_handler.return_value = MagicMock()

        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as first_file:
            first_path = first_file.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as second_file:
            second_path = second_file.name

        try:
            Tasks.delete().execute()
            time.sleep(0.2)

            first_item = {
                "pathname": first_path,
                "library_id": 1,
                "priority_score": 0,
            }
            self.scheduledtasks.put(first_item)
            self.task_handler.process_scheduledtasks_queue()
            time.sleep(0.5)

            self.task_handler.stop()
            self.task_handler.join()

            self.event = threading.Event()
            self.task_handler = TaskHandler(self.data_queues, self.task_queue, self.event)
            self.task_handler.daemon = True
            self.task_handler.start()

            self.scheduledtasks.put(first_item)
            self.task_handler.process_scheduledtasks_queue()

            second_item = {
                "pathname": second_path,
                "library_id": 2,
                "priority_score": 5,
            }
            self.inotifytasks.put(second_item)
            self.task_handler.process_inotifytasks_queue()
            time.sleep(0.5)

            first_task = Tasks.select().where(Tasks.abspath == os.path.abspath(first_path))
            second_task = Tasks.select().where(Tasks.abspath == os.path.abspath(second_path))
            assert first_task.count() == 1
            assert second_task.count() == 1
            assert second_task.get().library_id == 2
        finally:
            Tasks.delete().execute()
            os.unlink(first_path)
            os.unlink(second_path)


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
