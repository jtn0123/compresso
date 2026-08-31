#!/usr/bin/env python3

"""
compresso.pending_api.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     26 Oct 2020, (2:26 PM)

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
from collections.abc import Mapping, Sequence

import tornado.escape

from compresso import config
from compresso.libs import task
from compresso.libs.uiserver import CompressoDataQueues, DataQueues
from compresso.webserver.api_v1.base_api_handler import BaseApiHandler
from compresso.webserver.api_v2.base_api_handler import integer_list_value
from compresso.webserver.helpers import pending_tasks


class ApiPendingHandler(BaseApiHandler):
    name: str
    config: config.Config
    params: object
    compresso_data_queues: DataQueues

    routes = [
        {
            "supported_methods": ["POST"],
            "call_method": "create_task_from_path",
            "path_pattern": r"/api/v1/pending/add/",
        },
        {
            "supported_methods": ["POST"],
            "call_method": "manage_pending_tasks_list",
            "path_pattern": r"/api/v1/pending/list",
        },
        {
            "supported_methods": ["GET"],
            "call_method": "trigger_library_rescan",
            "path_pattern": r"/api/v1/pending/rescan",
        },
    ]

    def initialize(self, **kwargs: object) -> None:
        self.name = "pending_api"
        self.config = config.Config()

        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()

    def set_default_headers(self) -> None:
        """Set the default response header to be JSON."""
        super().set_default_headers()

    async def get(self, path: str) -> None:
        self.action_route()

    async def post(self, path: str) -> None:
        self.action_route()

    def manage_pending_tasks_list(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        try:
            request_value = json.loads(self.request.body)
        except (json.JSONDecodeError, ValueError):
            self.write(json.dumps({"success": False}))
            return
        if not isinstance(request_value, Mapping):
            self.write(json.dumps({"success": False}))
            return
        request_dict = {str(key): value for key, value in request_value.items()}
        task_ids = integer_list_value(request_dict.get("id"))

        # Delete a list of tasks.
        #   (on success will continue to return the current list of tasks)
        if request_dict.get("customActionName") == "remove-from-task-list" and not self.delete_pending_tasks(task_ids):
            self.write(json.dumps({"success": False}))
            return

        # Move a list of tasks to the top of the queue
        if request_dict.get("customActionName") == "move-to-top-of-task-list" and not pending_tasks.reorder_pending_tasks(
            task_ids, "top"
        ):
            self.write(json.dumps({"success": False}))
            return

        # Move a list of tasks to the bottom of the queue
        if request_dict.get("customActionName") == "move-to-bottom-of-task-list" and not pending_tasks.reorder_pending_tasks(
            task_ids, "bottom"
        ):
            self.write(json.dumps({"success": False}))
            return

        # Return a list of tasks based on the request JSON body
        results = pending_tasks.prepare_filtered_pending_tasks_for_table(request_dict)
        self.finish(tornado.escape.json_encode(results))

    def trigger_library_rescan(self) -> None:
        """
        Adds a trigger ('library_scan') to the library_scanner_triggers
        data queue.
        This data queue is read by the LibraryScanner service which will
        then execute a library scan.

        :return:
        """
        # Handle request to manually trigger a rescan of the library
        # Check if we are able to start up a worker for another encoding job
        library_scanner_triggers = self.compresso_data_queues.get("library_scanner_triggers")
        if library_scanner_triggers is None:
            self.write(json.dumps({"success": False}))
            return
        if library_scanner_triggers.full():
            self.write(json.dumps({"success": False}))
            return
        else:
            library_scanner_triggers.put("library_scan")
            self.write(json.dumps({"success": True}))
            return

    def delete_pending_tasks(self, pending_task_ids: Sequence[int] | None) -> bool:
        """
        Deletes a list of pending tasks

        :param pending_task_ids:
        :return:
        """
        # Fetch tasks
        task_handler = task.Task()
        # Delete by ID
        return task_handler.delete_tasks_recursively(id_list=pending_task_ids)

    def reorder_pending_tasks(self, pending_task_ids: Sequence[int], direction: str = "top") -> int:
        """
        Moves a list of pending tasks to either the top of the
        list of bottom depending on the provided direction.

        :param pending_task_ids:
        :param direction:
        :return:
        """
        # Fetch tasks
        task_handler = task.Task()

        return task_handler.reorder_tasks(pending_task_ids, direction)

    def create_task_from_path(self, *args: object, **kwargs: object) -> None:
        """
        v1 endpoint kept for route-compatibility only. The implementation
        was never completed and the rewrite landed on the v2 API. Returns
        501 Not Implemented and points callers at the v2 equivalent.
        """
        del args, kwargs
        self.set_status(501)
        self.write(
            json.dumps(
                {
                    "success": False,
                    "error": "v1 /api/v1/pending/add/ is not implemented; use POST /compresso/api/v2/pending/add",
                }
            )
        )
