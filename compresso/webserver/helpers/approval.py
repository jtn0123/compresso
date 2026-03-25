#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.approval.py

    Helper functions for the approval workflow API.
    Manages tasks in 'awaiting_approval' status — listing, approving, rejecting,
    and fetching detail/comparison data.
"""

import os
import shutil

from compresso import config
from compresso.libs import task
from compresso.libs.ffprobe_utils import extract_media_metadata
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.unmodels.tasks import Tasks

logger = CompressoLogging.get_logger(name=__name__)


def prepare_filtered_approval_tasks(params, include_library=False):
    """
    Returns a paginated, filtered list of tasks awaiting approval.

    :param params: dict with start, length, search_value, library_ids, order
    :param include_library: include library name in results
    :return: dict with recordsTotal, recordsFiltered, results
    """
    start = params.get('start', 0)
    length = params.get('length', 0)
    search_value = params.get('search_value', '')
    library_ids = params.get('library_ids') or []

    order_by = params.get('order_by', 'finish_time')
    order_direction = params.get('order_direction', 'desc')
    order = {
        "column": order_by if order_by else 'finish_time',
        "dir":    order_direction if order_direction in ('asc', 'desc') else 'desc',
    }

    task_handler = task.Task()
    records_total_count = task_handler.get_total_task_list_count()
    records_filtered_count = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=0,
        length=0,
        search_value=search_value,
        status='awaiting_approval',
        library_ids=library_ids,
    ).count()

    approval_task_results = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=start,
        length=length,
        search_value=search_value,
        status='awaiting_approval',
        library_ids=library_ids,
    )

    return_data = {
        "recordsTotal":    records_total_count,
        "recordsFiltered": records_filtered_count,
        "results":         [],
    }

    settings = config.Config()
    staging_path = settings.get_staging_path()

    for approval_task in approval_task_results:
        task_id = approval_task['id']
        item = {
            'id':          task_id,
            'abspath':     approval_task['abspath'],
            'priority':    approval_task['priority'],
            'type':        approval_task['type'],
            'status':      approval_task['status'],
            'source_size': approval_task.get('source_size', 0),
            'finish_time': str(approval_task.get('finish_time', '')),
        }

        # Add staged file info
        staged_info = _get_staged_file_info(task_id, staging_path)
        item['staged_size'] = staged_info.get('size', 0)
        item['staged_path'] = staged_info.get('path', '')
        item['size_delta'] = item['staged_size'] - item['source_size'] if item['staged_size'] else 0

        # Add codec metadata
        source_meta = extract_media_metadata(approval_task['abspath']) if approval_task.get('abspath') else {}
        item['source_codec'] = source_meta.get('codec', '')
        item['source_resolution'] = source_meta.get('resolution', '')

        staged_path = staged_info.get('path', '')
        if staged_path:
            staged_meta = extract_media_metadata(staged_path)
            item['staged_codec'] = staged_meta.get('codec', '')
            item['staged_resolution'] = staged_meta.get('resolution', '')
        else:
            item['staged_codec'] = ''
            item['staged_resolution'] = ''

        # Add quality scores from the task record
        try:
            task_record = Tasks.get_by_id(task_id)
            item['vmaf_score'] = task_record.vmaf_score
            item['ssim_score'] = task_record.ssim_score
        except Exception:
            item['vmaf_score'] = None
            item['ssim_score'] = None

        if include_library:
            library = Library(approval_task['library_id'])
            item['library_id'] = library.get_id()
            item['library_name'] = library.get_name()

        return_data["results"].append(item)

    return return_data


def get_approval_task_detail(task_id):
    """
    Get detailed comparison data for a single task awaiting approval.

    :param task_id: int
    :return: dict with source and staged file details, or None
    """
    task_handler = task.Task()
    results = task_handler.get_task_list_filtered_and_sorted(
        id_list=[task_id], status='awaiting_approval'
    )

    task_data = None
    for t in results:
        task_data = t
        break

    if not task_data:
        return None

    settings = config.Config()
    staging_path = settings.get_staging_path()
    staged_info = _get_staged_file_info(task_id, staging_path)

    source_size = task_data.get('source_size', 0)
    staged_size = staged_info.get('size', 0)

    # Extract media metadata for source and staged files
    source_meta = extract_media_metadata(task_data['abspath']) if task_data.get('abspath') else {}
    staged_path = staged_info.get('path', '')
    staged_meta = extract_media_metadata(staged_path) if staged_path else {}

    # Fetch quality scores from the task record
    vmaf_score = None
    ssim_score = None
    try:
        task_record = Tasks.get_by_id(task_id)
        vmaf_score = task_record.vmaf_score
        ssim_score = task_record.ssim_score
    except Exception:
        pass

    return {
        'id':                task_id,
        'abspath':           task_data['abspath'],
        'source_size':       source_size,
        'staged_size':       staged_size,
        'staged_path':       staged_info.get('path', ''),
        'size_delta':        staged_size - source_size if staged_size else 0,
        'size_ratio':        round(staged_size / source_size, 3) if source_size > 0 and staged_size > 0 else 0,
        'cache_path':        task_data.get('cache_path', ''),
        'success':           task_data.get('success', False),
        'start_time':        str(task_data.get('start_time', '')),
        'finish_time':       str(task_data.get('finish_time', '')),
        'log':               task_data.get('log', ''),
        'library_id':        task_data.get('library_id', 1),
        'source_codec':      source_meta.get('codec', ''),
        'source_resolution': source_meta.get('resolution', ''),
        'source_container':  source_meta.get('container', ''),
        'staged_codec':      staged_meta.get('codec', ''),
        'staged_resolution': staged_meta.get('resolution', ''),
        'staged_container':  staged_meta.get('container', ''),
        'vmaf_score':        vmaf_score,
        'ssim_score':        ssim_score,
    }


def approve_tasks(task_ids):
    """
    Approve tasks — sets their status to 'approved' so the postprocessor
    picks them up and finalizes the file replacement.

    :param task_ids: list of int
    :return: int count of updated tasks
    """
    return task.Task.set_tasks_status(task_ids, 'approved')


def reject_tasks(task_ids, requeue=False):
    """
    Reject tasks — removes staged files and either deletes the task
    or requeues it with 'pending' status.

    :param task_ids: list of int
    :param requeue: if True, set status back to 'pending' instead of deleting
    :return: bool success
    """
    settings = config.Config()
    staging_path = settings.get_staging_path()

    for task_id in task_ids:
        # Clean up staged files
        task_staging_dir = os.path.join(staging_path, "task_{}".format(task_id))
        if os.path.exists(task_staging_dir):
            try:
                shutil.rmtree(task_staging_dir)
                logger.info("Removed staging directory for rejected task %s", task_id)
            except Exception as e:
                logger.error("Failed to remove staging directory for task %s: %s", task_id, e)

        # Also clean up cache files for the task
        try:
            task_record = Tasks.get_by_id(task_id)
            if task_record.cache_path:
                cache_dir = os.path.dirname(task_record.cache_path)
                if os.path.exists(cache_dir) and "compresso_file_conversion" in cache_dir:
                    shutil.rmtree(cache_dir)
                    logger.info("Removed cache directory for rejected task %s", task_id)
        except Exception as e:
            logger.warning("Could not clean cache for task %s: %s", task_id, e)

    if requeue:
        return task.Task.set_tasks_status(task_ids, 'pending')
    else:
        task_handler = task.Task()
        return task_handler.delete_tasks_recursively(task_ids)


def get_all_matching_task_ids(search_value=''):
    """
    Return all task IDs that match the given search filter and are awaiting approval.
    Used for "select all matching" across pages.

    :param search_value: text search on file path
    :return: list of int task IDs
    """
    task_handler = task.Task()
    results = task_handler.get_task_list_filtered_and_sorted(
        order={"column": "finish_time", "dir": "desc"},
        start=0,
        length=0,
        search_value=search_value,
        status='awaiting_approval',
    )
    return [t['id'] for t in results]


def get_approval_count():
    """Return the count of tasks awaiting approval."""
    query = Tasks.select().where(Tasks.status == 'awaiting_approval').limit(1000)
    return query.count()


def _get_staged_file_info(task_id, staging_path):
    """
    Get size and path of the staged file for a given task.

    :param task_id: int
    :param staging_path: str base staging directory
    :return: dict with 'size' and 'path'
    """
    task_staging_dir = os.path.join(staging_path, "task_{}".format(task_id))
    if not os.path.exists(task_staging_dir):
        return {'size': 0, 'path': ''}

    # Find the first file in the staging directory
    try:
        for filename in os.listdir(task_staging_dir):
            filepath = os.path.join(task_staging_dir, filename)
            if os.path.isfile(filepath):
                return {
                    'size': os.path.getsize(filepath),
                    'path': filepath,
                }
    except OSError:
        pass

    return {'size': 0, 'path': ''}
