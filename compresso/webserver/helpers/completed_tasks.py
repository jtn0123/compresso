#!/usr/bin/env python3

"""
compresso.completed_tasks.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     24 Jul 2021, (9:34 AM)

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
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from compresso.libs import history, narrowing, task
from compresso.libs.history import HistoryOrder
from compresso.libs.peewee_types import CountedRows
from compresso.libs.unmodels import FileMetadataPaths


def _parse_datetime_to_timestamp(value: object) -> float | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value, fmt).timestamp()
            except ValueError:
                continue
    return None


def parse_timestamp_value(value: object) -> float | None:
    """Best-effort conversion of a stored start/finish time to a POSIX timestamp."""
    numeric = narrowing.strict_float_or_none(value)
    return numeric if numeric is not None else _parse_datetime_to_timestamp(value)


def _history_order(params: Mapping[str, object]) -> HistoryOrder:
    value = params.get("order")
    if isinstance(value, Mapping):
        column = value.get("column")
        direction = value.get("dir")
        if isinstance(column, str) and isinstance(direction, str):
            return {"column": column, "dir": direction}
    return {"column": "finish_time", "dir": "desc"}


def prepare_filtered_completed_tasks(params: Mapping[str, object]) -> dict[str, object]:
    """
    Returns a object of historical records filtered and sorted
    according to the provided request.

    :param params:
    :return:
    """
    start = narrowing.coerce_int(params.get("start"), 0)
    length = narrowing.coerce_int(params.get("length"), 0)

    search_value = narrowing.strict_str(params.get("search_value"))
    status = narrowing.strict_str(params.get("status"), "all")

    order = _history_order(params)

    # Define filters
    task_success = None
    if status == "success":
        task_success = True
    elif status == "failed":
        task_success = False

    after_time = _parse_datetime_to_timestamp(params.get("after"))
    before_time = _parse_datetime_to_timestamp(params.get("before"))

    # Fetch historical tasks
    history_logging = history.History()
    # Get total count
    records_total_count = history_logging.get_total_historic_task_list_count()
    # Get total success count
    success_rows = cast(CountedRows, history_logging.get_historic_task_list_filtered_and_sorted(task_success=True))
    records_total_success_count = success_rows.count()
    # Get total failed count
    failed_rows = cast(CountedRows, history_logging.get_historic_task_list_filtered_and_sorted(task_success=False))
    records_total_failed_count = failed_rows.count()
    # Get quantity after filters (without pagination)
    filtered_rows = cast(
        CountedRows,
        history_logging.get_historic_task_list_filtered_and_sorted(
            order=order,
            start=0,
            length=0,
            search_value=search_value,
            task_success=task_success,
            after_time=after_time,
            before_time=before_time,
        ),
    )
    records_filtered_count = filtered_rows.count()
    # Get filtered/sorted results
    task_results = history_logging.get_historic_task_list_filtered_and_sorted(
        order=order,
        start=start,
        length=length,
        search_value=search_value,
        task_success=task_success,
        after_time=after_time,
        before_time=before_time,
    )

    # Build return data
    results: list[dict[str, object]] = []
    return_data: dict[str, object] = {
        "recordsTotal": records_total_count,
        "recordsFiltered": records_filtered_count,
        "successCount": records_total_success_count,
        "failedCount": records_total_failed_count,
        "results": results,
    }

    matched_paths: set[str] = set()
    task_paths = [path for row in task_results if isinstance((path := row.get("abspath")), str) and path]
    if task_paths:
        query = FileMetadataPaths.select(FileMetadataPaths.path).where(FileMetadataPaths.path.in_(task_paths))
        for row in query:
            if isinstance(row.path, str):
                matched_paths.add(row.path)

    # Iterate over tasks and append them to the task data
    for task in task_results:
        # Set params as required in template
        item = {
            "id": task["id"],
            "task_label": task["task_label"],
            "task_success": task["task_success"],
            "finish_time": int(_parse_datetime_to_timestamp(task["finish_time"]) or 0),
            "has_metadata": task.get("abspath") in matched_paths,
        }
        results.append(item)

    # Return results
    return return_data


def get_filtered_completed_task_ids(params: Mapping[str, object], exclude_ids: Sequence[int] | None = None) -> list[int]:
    """
    Returns a list of completed task IDs filtered according to the provided request.

    :param params:
    :param exclude_ids:
    :return:
    """
    search_value = narrowing.strict_str(params.get("search_value"))
    status = narrowing.strict_str(params.get("status"), "all")

    task_success = None
    if status == "success":
        task_success = True
    elif status == "failed":
        task_success = False

    after_time = _parse_datetime_to_timestamp(params.get("after"))
    before_time = _parse_datetime_to_timestamp(params.get("before"))

    exclude_set = set(exclude_ids or [])

    history_logging = history.History()
    query = history_logging.get_historic_task_list_filtered_and_sorted(
        order=None,
        start=0,
        length=0,
        search_value=search_value,
        task_success=task_success,
        after_time=after_time,
        before_time=before_time,
    )

    id_list: list[int] = []
    for record in query:
        task_id = record.get("id")
        if not isinstance(task_id, int):
            continue
        if task_id in exclude_set:
            continue
        id_list.append(task_id)

    return id_list


def remove_completed_tasks(completed_task_ids: Sequence[int]) -> bool:
    """
    Removes a list of completed tasks

    :param completed_task_ids:
    :return:
    """
    # Delete by ID
    task_handler = history.History()
    return task_handler.delete_historic_tasks_recursively(id_list=completed_task_ids)


def add_historic_tasks_to_pending_tasks_list(
    historic_task_ids: Sequence[int], library_id: int | None = None
) -> dict[int, str]:
    """
    Adds a list of historical tasks to the pending tasks list.

    :param historic_task_ids:
    :param library_id:
    :return:
    """
    errors: dict[int, str] = {}
    # Fetch historical tasks
    history_logging = history.History()
    # Get total count
    records_by_id = history_logging.get_current_path_of_historic_tasks_by_id(id_list=historic_task_ids)
    for record in records_by_id:
        # Fetch the abspath name
        path_value = record.get("abspath")
        record_id = record.get("id")
        if not isinstance(path_value, str) or not isinstance(record_id, int):
            continue
        abspath = os.path.abspath(path_value)

        # Ensure path exists
        if not os.path.exists(abspath):
            errors[record_id] = f"Path does not exist - '{abspath}'"
            continue

        # Create a new task
        new_task = task.Task()

        if not new_task.create_task_by_absolute_path(abspath, library_id=library_id if library_id is not None else 1):
            # If file exists in task queue already this will return false.
            # Do not carry on.
            errors[record_id] = f"File already in task queue - '{abspath}'"

        continue
    return errors


def read_command_log_for_task(task_id: int) -> dict[str, object]:
    command_log_lines: list[str] = []
    data: dict[str, object] = {
        "command_log": "",
        "command_log_lines": command_log_lines,
    }
    task_handler = history.History()
    task_data = task_handler.get_historic_task_data_dictionary(task_id=task_id)
    if not isinstance(task_data, dict):
        return data

    raw_logs = task_data.get("completedtaskscommandlogs_set", [])
    logs = raw_logs if isinstance(raw_logs, list) else []
    combined_log = ""
    for command_log in logs:
        if not isinstance(command_log, Mapping):
            continue
        dump = command_log.get("dump")
        if not isinstance(dump, str):
            continue
        combined_log += dump
        command_log_lines.extend(format_ffmpeg_log_text(dump.split("\n")))

    data["command_log"] = combined_log

    return data


def format_ffmpeg_log_text(log_lines: Sequence[str]) -> list[str]:
    return_list: list[str] = []
    pre_text = False
    termination_headers = {
        "WORKER TERMINATED!",
        "PLUGIN FAILED!",
        "REMOTE TASK FAILED!",
        "REMOTE LINK MANAGER TERMINATED!",
    }
    headers = {"RUNNER:", "COMMAND:", "LOG:"} | termination_headers
    for _i, line in enumerate(log_lines):
        line_text = line

        # Add PRE to lines
        if line_text and pre_text and line_text.rstrip() not in headers:
            line_text = f"<pre>{line_text}</pre>"

        # Add bold to headers
        if line_text.rstrip() in termination_headers:
            line_text = f'<b><span class="terminated">{line_text}</span></b>'
        elif line_text.rstrip() in headers:
            line_text = f"<b>{line_text}</b>"

        # Replace leading whitespace
        stripped = line.lstrip()
        line_text = "&nbsp;" * (len(line) - len(stripped)) + line_text

        # If log section is COMMAND:
        if "RUNNER:" in line_text:
            # prepend a horizontal rule
            return_list.append("<hr>")
            pre_text = False
        elif "COMMAND:" in line_text:
            pre_text = True
        elif "LOG:" in line_text:
            pre_text = False
        return_list.append(line_text)
    return return_list
