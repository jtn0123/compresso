#!/usr/bin/env python3

"""
compresso.history_api.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     25 Oct 2020, (8:49 PM)

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
import time
from collections.abc import Mapping, Sequence

import tornado.escape

from compresso import config
from compresso.libs import history, narrowing
from compresso.libs.history import HistoryOrder
from compresso.webserver.api_v1.base_api_handler import BaseApiHandler
from compresso.webserver.helpers import completed_tasks
from compresso.webserver.helpers.pagination import parse_page_params


class ApiHistoryHandler(BaseApiHandler):
    name: str
    config: config.Config
    params: object

    routes = [
        {
            "supported_methods": ["GET", "POST"],
            "call_method": "fetch_by_id",
            "path_pattern": r"/api/v1/history/id/(?P<id>[0-9]+)?",
        },
        {
            "supported_methods": ["POST"],
            "call_method": "manage_historic_tasks_list",
            "path_pattern": r"/api/v1/history/list",
        },
    ]

    def initialize(self, **kwargs: object) -> None:
        self.name = "history_api"
        self.config = config.Config()
        self.params = kwargs.get("params")

    def set_default_headers(self) -> None:
        """Set the default response header to be JSON."""
        super().set_default_headers()

    async def post(self, path: str) -> None:
        self.action_route()

    def fetch_by_id(self, *args: object, **kwargs: object) -> None:
        """
        v1 endpoint kept for route-compatibility only. Fetch-by-id was
        never implemented and the supported surface is v2 going forward.
        """
        del args, kwargs
        self.set_status(501)
        self.write(
            json.dumps(
                {
                    "success": False,
                    "error": "v1 /api/v1/history/id/<id> is not implemented; use the v2 history API",
                }
            )
        )

    def manage_historic_tasks_list(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        request_value = json.loads(self.request.body)
        if not isinstance(request_value, Mapping):
            self.write({"success": False})
            return
        request_dict = {str(key): value for key, value in request_value.items()}

        # Delete a list of historical tasks.
        #   (on success will continue to return the current list of historical tasks)
        if request_dict.get("customActionName") == "delete-from-history":
            success = self.delete_historic_tasks(self._integer_list(request_dict.get("id")))
            if not success:
                self.write({"success": False})
                return

        # Return a list of historical tasks based on the request JSON body
        results = self.prepare_filtered_historic_tasks(request_dict)
        self.finish(tornado.escape.json_encode(results))

    @staticmethod
    def _integer_list(value: object) -> list[int]:
        return narrowing.int_list(value, coerce=True)

    def delete_historic_tasks(self, historic_task_ids: Sequence[int]) -> bool:
        """
        Deletes a list of historic tasks

        :param historic_task_ids:
        :return:
        """
        # Fetch historical tasks
        history_logging = history.History()
        # Delete by ID
        return history_logging.delete_historic_tasks_recursively(id_list=historic_task_ids)

    def prepare_filtered_historic_tasks(self, request_dict: Mapping[str, object]) -> dict[str, object]:
        """
        Returns a object of historical records filtered and sorted
        according to the provided request.

        :param request_dict:
        :return:
        """

        # Generate filters for query
        page = parse_page_params(request_dict, data_tables=True)

        # Get sort order
        order_entries = request_dict.get("order")
        filter_order_value = order_entries[0] if isinstance(order_entries, list) and order_entries else {}
        filter_order = filter_order_value if isinstance(filter_order_value, Mapping) else {}
        order_direction_value = filter_order.get("dir")
        order_direction = order_direction_value if isinstance(order_direction_value, str) else "desc"
        column_index = narrowing.coerce_int(filter_order.get("column"), 0)
        columns_value = request_dict.get("columns")
        columns = columns_value if isinstance(columns_value, list) else []
        column_value = columns[column_index] if 0 <= column_index < len(columns) else {}
        column = column_value if isinstance(column_value, Mapping) else {}
        order_column_value = column.get("name")
        order_column_name = order_column_value if isinstance(order_column_value, str) else "finish_time"
        order: HistoryOrder = {
            "column": order_column_name,
            "dir": order_direction,
        }

        # Fetch historical tasks
        history_logging = history.History()
        # Get total count
        records_total_count = history_logging.get_total_historic_task_list_count()
        # Get quantity after filters (without pagination)
        records_filtered_count = history_logging.get_historic_task_list_filtered_and_sorted(
            order=order, start=0, length=0, search_value=page.search_value
        ).count()
        # Get filtered/sorted results
        task_results = history_logging.get_historic_task_list_filtered_and_sorted(
            order=order, start=page.start, length=page.length, search_value=page.search_value
        )

        # Build return data
        data = [self._historic_task_item(task) for task in task_results]
        success_count = sum(bool(item["task_success"]) for item in data)
        failed_count = len(data) - success_count

        # Return results
        return {
            "draw": page.draw,
            "recordsTotal": records_total_count,
            "recordsFiltered": records_filtered_count,
            "successCount": success_count,
            "failedCount": failed_count,
            "data": data,
        }

    @staticmethod
    def _historic_task_item(task: Mapping[str, object]) -> dict[str, object]:
        finish_time = task.get("finish_time")
        timestamp = completed_tasks.parse_timestamp_value(finish_time)
        display_time = (
            (str(finish_time) if finish_time else "")
            if timestamp is None
            else time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
        )
        return {
            "id": task["id"],
            "selected": False,
            "finish_time": display_time,
            "task_label": task["task_label"],
            "task_success": task["task_success"],
        }
