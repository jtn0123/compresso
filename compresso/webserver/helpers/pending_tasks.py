#!/usr/bin/env python3

"""
compresso.pending_tasks.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     23 Jul 2021, (6:27 PM)

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

from compresso.libs import filetest, task
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_count
from compresso.libs.task import TaskOrder
from compresso.libs.unmodels.tasks import Tasks
from compresso.webserver.helpers.pagination import parse_page_params

logger = CompressoLogging.get_logger(name=__name__)


def _task_order(params: Mapping[str, object]) -> TaskOrder:
    value = params.get("order")
    if isinstance(value, Mapping):
        column = value.get("column")
        direction = value.get("dir")
        if isinstance(column, str) and isinstance(direction, str):
            return {"column": column, "dir": direction}
    return {"column": "priority", "dir": "desc"}


def prepare_filtered_pending_tasks_for_table(request_dict: Mapping[str, object]) -> dict[str, object]:
    """
    Returns a object of records filtered and sorted
    according to the provided request.

    :param request_dict:
    :return:
    """

    # Generate filters for query
    page = parse_page_params(request_dict, data_tables=True)

    # Force sort order always by ID desc
    order: TaskOrder = {
        "column": "priority",
        "dir": "desc",
    }

    # Fetch tasks
    task_handler = task.Task()
    # Get total count
    records_total_count = task_handler.get_total_task_list_count()
    # Get quantity after filters (without pagination)
    filtered_rows = task_handler.get_task_list_filtered_and_sorted(
        order=order, start=0, length=0, search_value=page.search_value, status="pending"
    )
    records_filtered_count = filtered_rows.count()
    # Get filtered/sorted results
    pending_task_results = task_handler.get_task_list_filtered_and_sorted(
        order=order, start=page.start, length=page.length, search_value=page.search_value, status="pending"
    )

    # Build return data
    data: list[dict[str, object]] = []
    return_data: dict[str, object] = {
        "draw": page.draw,
        "recordsTotal": records_total_count,
        "recordsFiltered": records_filtered_count,
        "successCount": 0,
        "failedCount": 0,
        "data": data,
    }

    # Iterate over tasks and append them to the task data
    for pending_task in pending_task_results:
        # Set params as required in template
        item = {
            "id": pending_task["id"],
            "selected": False,
            "abspath": pending_task["abspath"],
            "status": pending_task["status"],
        }
        data.append(item)

    # Return results
    return return_data


def prepare_filtered_pending_tasks(params: Mapping[str, object], include_library: bool = False) -> dict[str, object]:
    """
    Returns a object of records filtered and sorted
    according to the provided request.

    :param params:
    :param include_library:
    :return:
    """
    page = parse_page_params(params)

    order = _task_order(params)

    # Fetch tasks
    task_handler = task.Task()
    # Get total count
    records_total_count = task_handler.get_total_task_list_count()
    # Get quantity after filters (without pagination)
    filtered_rows = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=0,
        length=0,
        search_value=page.search_value,
        status="pending",
        library_ids=page.library_ids,
    )
    records_filtered_count = filtered_rows.count()
    # Get filtered/sorted results
    pending_task_results = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=page.start,
        length=page.length,
        search_value=page.search_value,
        status="pending",
        library_ids=page.library_ids,
    )

    # Build return data
    results: list[dict[str, object]] = []
    return_data: dict[str, object] = {
        "recordsTotal": records_total_count,
        "recordsFiltered": records_filtered_count,
        "runnableRecords": task_handler.get_runnable_task_count(),
        "results": results,
    }

    # Iterate over tasks and append them to the task data
    for pending_task in pending_task_results:
        # Set params as required in template
        item = {
            "id": pending_task["id"],
            "abspath": pending_task["abspath"],
            "priority": pending_task["priority"],
            "type": pending_task["type"],
            "status": pending_task["status"],
        }
        # Include retry fields when present
        if pending_task.get("retry_count"):
            item["retry_count"] = pending_task["retry_count"]
        if pending_task.get("deferred_until"):
            item["deferred_until"] = str(pending_task["deferred_until"])
        if include_library:
            # Get library
            library_id_value = pending_task["library_id"]
            if not isinstance(library_id_value, int):
                continue
            library = Library(library_id_value)
            item["library_id"] = library.get_id()
            item["library_name"] = library.get_name()
        results.append(item)

    # Return results
    return return_data


def get_filtered_pending_task_ids(params: Mapping[str, object], exclude_ids: Sequence[int] | None = None) -> list[int]:
    """
    Returns a list of pending task IDs filtered according to the provided request.

    :param params:
    :param exclude_ids:
    :return:
    """
    page = parse_page_params(params)

    exclude_set = set(exclude_ids or [])

    task_handler = task.Task()
    query = task_handler.get_task_list_filtered_and_sorted(
        order=None,
        start=0,
        length=0,
        search_value=page.search_value,
        status="pending",
        library_ids=page.library_ids,
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


def remove_pending_tasks(pending_task_ids: Sequence[int]) -> bool:
    """
    Removes a list of pending tasks

    :param pending_task_ids:
    :return:
    """
    # Delete by ID
    task_handler = task.Task()
    return task_handler.delete_tasks_recursively(id_list=pending_task_ids)


def reorder_pending_tasks(pending_task_ids: Sequence[int], direction: str = "top") -> int:
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


def add_remote_tasks(pathname: str, job_id: str | None = None) -> dict[str, object] | bool:
    """
    Adds an upload file path to the pending task list as a 'remote' task
    Returns the task ID

    :param pathname:
    :return:
    """
    abspath = os.path.abspath(pathname)

    # Create a new task
    new_task = task.Task()

    if job_id:
        existing_task = Tasks.get_or_none(Tasks.job_id == job_id)
        if existing_task is not None:
            new_task.task = existing_task
            return new_task.get_task_data()

    if not new_task.create_task_by_absolute_path(abspath, task_type="remote", job_id=job_id):
        # File was not created.
        # Do not carry on.
        return False
    return new_task.get_task_data()


def update_pending_tasks_status(pending_task_ids: Sequence[int], status: str = "pending") -> int:
    """
    Updates the status of a number pending tasks given their table IDs

    :param pending_task_ids:
    :param status:
    :return:
    """
    # Update tasks
    return task.Task.set_tasks_status(pending_task_ids, status)


def update_pending_tasks_library(pending_task_ids: Sequence[int], library_name: str) -> int | bool:
    """
    Updates the status of a number pending tasks given their table IDs

    :param pending_task_ids:
    :param library_name:
    :return:
    """
    # Fetch Library ID by it's name
    library_id = None
    libraries = Library.get_all_libraries()
    for library in libraries:
        if library.get("name") == library_name:
            candidate_id = library.get("id")
            library_id = candidate_id if isinstance(candidate_id, int) else None
            break
    # Ensure a library was found matching the name
    if library_id is None:
        return False
    # Update the tasks
    return task.Task.set_tasks_library_id(pending_task_ids, library_id)


def fetch_tasks_status(pending_task_ids: Sequence[int]) -> list[dict[str, object]]:
    """
    Fetch the status of a number of pending remote tasks given their table IDs

    :param pending_task_ids:
    :return:
    """
    # Fetch tasks
    task_handler = task.Task()
    remote_pending_tasks = task_handler.get_task_list_filtered_and_sorted(id_list=pending_task_ids)

    # Iterate over tasks and append them to the task data
    return_data: list[dict[str, object]] = []
    for pending_task in remote_pending_tasks:
        # Set params as required in template
        item = {
            "id": pending_task["id"],
            "abspath": pending_task["abspath"],
            "priority": pending_task["priority"],
            "type": pending_task["type"],
            "status": pending_task["status"],
        }
        return_data.append(item)
    return return_data


def check_if_task_exists_matching_path(abspath: str) -> bool:
    from compresso.libs.taskhandler import TaskHandler

    return bool(TaskHandler.check_if_task_exists_matching_path(abspath))


def create_task(
    abspath: str,
    library_id: int = 1,
    library_name: str | None = None,
    task_type: str = "local",
    priority_score: int = 0,
    job_id: str | None = None,
) -> dict[str, object] | bool:
    """
    Create a pending task given the path to a file and a library ID or name

    :param abspath:
    :param library_id:
    :param library_name:
    :param task_type:
    :param priority_score:
    :return:
    """
    if library_name is not None:
        for library_config in Library.get_all_libraries():
            if library_name == library_config.get("name"):
                candidate_id = library_config.get("id")
                if isinstance(candidate_id, int):
                    library_id = candidate_id

    # Ensure the library provided exists (prevents errors as the task library_id column is not a foreign key
    selected_library = Library(library_id)

    # Create a new task
    new_task = task.Task()

    # Create the task as a local task as the path provided is local
    if not new_task.create_task_by_absolute_path(
        abspath,
        task_type=task_type,
        library_id=selected_library.get_id(),
        priority_score=priority_score,
        job_id=job_id,
    ):
        # File was not created.
        # Do not carry on.
        return False

    # Return task info (same as the data returned in a file upload
    task_info = new_task.get_task_data()
    return {
        "id": task_info.get("id"),
        "abspath": task_info.get("abspath"),
        "priority": task_info.get("priority"),
        "type": task_info.get("type"),
        "status": task_info.get("status"),
        "library_id": task_info.get("library_id"),
        "job_id": task_info.get("job_id"),
    }


def get_task_by_job_id(job_id: str | None) -> dict[str, object] | None:
    if not job_id:
        return None
    task_model = Tasks.get_or_none(Tasks.job_id == job_id)
    if task_model is None:
        return None
    task_object = task.Task()
    task_object.task = task_model
    return task_object.get_task_data()


def bind_remote_task_identity(
    task_id: int,
    lease_token: str | None = None,
    origin_installation_uuid: str | None = None,
) -> bool:
    values: dict[str, str] = {}
    if lease_token:
        values["lease_token"] = lease_token
    if origin_installation_uuid:
        values["remote_installation_uuid"] = origin_installation_uuid
    if not values:
        return True
    condition = Tasks.id == task_id
    if lease_token:
        condition &= Tasks.lease_token.is_null() | (Tasks.lease_token == lease_token)
    if origin_installation_uuid:
        condition &= Tasks.remote_installation_uuid.is_null() | (Tasks.remote_installation_uuid == origin_installation_uuid)
    return bool(execute_count(Tasks.update(**values).where(condition)))


def test_path_for_pending_task(abspath: str, library_id: int) -> dict[str, object]:
    """
    Test a file path against library file test plugins without queueing a task.

    :param abspath:
    :param library_id:
    :return:
    """
    file_tester = filetest.FileTest(library_id)
    add_file_to_pending_tasks, file_issues, priority_score_modification, decision_plugin = (
        file_tester.should_file_be_added_to_task_list(abspath)
    )

    for issue in file_issues:
        if isinstance(issue, dict):
            logger.info(issue.get("message"))
        else:
            logger.info(issue)

    return {
        "add_file_to_pending_tasks": add_file_to_pending_tasks,
        "issues": file_issues,
        "priority_score": priority_score_modification,
        "decision_plugin": decision_plugin,
    }
