#!/usr/bin/env python3

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
from compresso.webserver.api_v2.schema.approval_schemas import APPROVAL_TASK_ORDER_COLUMNS

logger = CompressoLogging.get_logger(name=__name__)


def _normalise_codec_filter(codec):
    return str(codec or "").strip().lower()


def _normalise_quality_min(value):
    try:
        return max(0.0, min(100.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


def _build_order(params):
    order_by = params.get("order_by", "finish_time")
    if order_by not in APPROVAL_TASK_ORDER_COLUMNS:
        order_by = "finish_time"

    order_direction = params.get("order_direction", "desc")
    return {
        "column": order_by if order_by else "finish_time",
        "dir": order_direction if order_direction in ("asc", "desc") else "desc",
    }


def _build_approval_item(approval_task, staging_path, include_library=False):
    task_id = approval_task["id"]
    item = {
        "id": task_id,
        "abspath": approval_task["abspath"],
        "priority": approval_task["priority"],
        "type": approval_task["type"],
        "status": approval_task["status"],
        "source_size": approval_task.get("source_size", 0),
        "finish_time": str(approval_task.get("finish_time", "")),
    }

    staged_info = _get_staged_file_info(task_id, staging_path)
    item["staged_size"] = staged_info.get("size", 0)
    item["staged_path"] = staged_info.get("path", "")
    item["size_delta"] = item["staged_size"] - item["source_size"] if item["staged_size"] else 0

    source_meta = extract_media_metadata(approval_task["abspath"]) if approval_task.get("abspath") else {}
    item["source_codec"] = source_meta.get("codec", "")
    item["source_resolution"] = source_meta.get("resolution", "")

    staged_path = staged_info.get("path", "")
    if staged_path:
        staged_meta = extract_media_metadata(staged_path)
        item["staged_codec"] = staged_meta.get("codec", "")
        item["staged_resolution"] = staged_meta.get("resolution", "")
    else:
        item["staged_codec"] = ""
        item["staged_resolution"] = ""

    item["vmaf_score"] = approval_task.get("vmaf_score")
    item["ssim_score"] = approval_task.get("ssim_score")

    if include_library:
        library = Library(approval_task["library_id"])
        item["library_id"] = library.get_id()
        item["library_name"] = library.get_name()

    return item


def _matches_approval_filters(item, codec_filter="", quality_min=0):
    codec_filter = _normalise_codec_filter(codec_filter)
    quality_min = _normalise_quality_min(quality_min)

    if codec_filter:
        codecs = {
            _normalise_codec_filter(item.get("source_codec")),
            _normalise_codec_filter(item.get("staged_codec")),
        }
        if codec_filter not in codecs:
            return False

    if quality_min > 0:
        vmaf_score = item.get("vmaf_score")
        if vmaf_score is None:
            return False
        try:
            if float(vmaf_score) < quality_min:
                return False
        except (TypeError, ValueError):
            return False

    return True


def _get_approval_items(params, include_library=False, force_all=False):
    start = params.get("start", 0)
    length = params.get("length", 0)
    search_value = params.get("search_value", "")
    library_ids = params.get("library_ids") or []
    codec_filter = params.get("codec") or ""
    quality_min = _normalise_quality_min(params.get("quality_min", 0))
    has_derived_filters = bool(_normalise_codec_filter(codec_filter)) or quality_min > 0

    order = _build_order(params)

    task_handler = task.Task()
    records_total_count = task_handler.get_total_task_list_count()
    count_query = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=0,
        length=0,
        search_value=search_value,
        status="awaiting_approval",
        library_ids=library_ids,
    )

    data_start = 0 if has_derived_filters or force_all else start
    data_length = 0 if has_derived_filters or force_all else length
    approval_task_results = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=data_start,
        length=data_length,
        search_value=search_value,
        status="awaiting_approval",
        library_ids=library_ids,
    )

    settings = config.Config()
    staging_path = settings.get_staging_path()
    items = [
        _build_approval_item(approval_task, staging_path, include_library=include_library)
        for approval_task in approval_task_results
    ]

    if has_derived_filters:
        items = [item for item in items if _matches_approval_filters(item, codec_filter=codec_filter, quality_min=quality_min)]

    records_filtered_count = len(items) if has_derived_filters or force_all else count_query.count()
    if (has_derived_filters or force_all) and length:
        items = items[start : start + length]

    return records_total_count, records_filtered_count, items


def prepare_filtered_approval_tasks(params, include_library=False):
    """
    Returns a paginated, filtered list of tasks awaiting approval.

    :param params: dict with start, length, search_value, library_ids, order
    :param include_library: include library name in results
    :return: dict with recordsTotal, recordsFiltered, results
    """
    records_total_count, records_filtered_count, approval_task_results = _get_approval_items(
        params=params,
        include_library=include_library,
    )

    return_data = {
        "recordsTotal": records_total_count,
        "recordsFiltered": records_filtered_count,
        "results": approval_task_results,
    }

    return return_data


def prepare_approval_summary(params):
    """
    Return aggregate summary data for tasks awaiting approval.

    :param params: dict with search/filter parameters
    :return: dict with counts, aggregate sizes, VMAF average, and codec options
    """
    _records_total, _records_filtered, items = _get_approval_items(
        params=params,
        include_library=False,
        force_all=True,
    )

    codec_options = sorted(
        {codec for item in items for codec in (item.get("source_codec"), item.get("staged_codec")) if codec}
    )
    with_vmaf = [float(item["vmaf_score"]) for item in items if item.get("vmaf_score") is not None]
    items_with_staged_files = [item for item in items if item.get("staged_size", 0) > 0]
    total_source_size = sum(item.get("source_size") or 0 for item in items)
    total_staged_size = sum(item.get("staged_size") or 0 for item in items)
    total_space_saved = sum(abs(item.get("size_delta") or 0) for item in items if (item.get("size_delta") or 0) < 0)
    savings_percentages = [
        ((item.get("source_size", 0) - item.get("staged_size", 0)) / item.get("source_size", 0)) * 100
        for item in items_with_staged_files
        if item.get("source_size", 0) > 0
    ]
    largest = None
    for item in items_with_staged_files:
        size_delta = item.get("size_delta") or 0
        if size_delta >= 0:
            continue
        if largest is None or abs(size_delta) > abs(largest.get("size_delta") or 0):
            largest = item

    return {
        "total_count": len(items),
        "total_source_size": total_source_size,
        "total_staged_size": total_staged_size,
        "total_space_saved": total_space_saved,
        "average_savings_percent": sum(savings_percentages) / len(savings_percentages) if savings_percentages else 0,
        "largest_savings_file": largest.get("abspath", "") if largest else "",
        "largest_savings_bytes": abs(largest.get("size_delta") or 0) if largest else 0,
        "average_vmaf": sum(with_vmaf) / len(with_vmaf) if with_vmaf else None,
        "codec_options": codec_options,
    }


def get_approval_task_detail(task_id):
    """
    Get detailed comparison data for a single task awaiting approval.

    :param task_id: int
    :return: dict with source and staged file details, or None
    """
    task_handler = task.Task()
    results = task_handler.get_task_list_filtered_and_sorted(id_list=[task_id], status="awaiting_approval")

    task_data = None
    for t in results:
        task_data = t
        break

    if not task_data:
        return None

    settings = config.Config()
    staging_path = settings.get_staging_path()
    staged_info = _get_staged_file_info(task_id, staging_path)

    source_size = task_data.get("source_size", 0)
    staged_size = staged_info.get("size", 0)

    # Extract media metadata for source and staged files
    source_meta = extract_media_metadata(task_data["abspath"]) if task_data.get("abspath") else {}
    staged_path = staged_info.get("path", "")
    staged_meta = extract_media_metadata(staged_path) if staged_path else {}

    # Fetch quality scores from the task record
    vmaf_score = None
    ssim_score = None
    try:
        task_record = Tasks.get_by_id(task_id)
        vmaf_score = task_record.vmaf_score
        ssim_score = task_record.ssim_score
    except Exception:  # noqa: S110 — scores are optional; task record may not exist yet
        pass

    return {
        "id": task_id,
        "abspath": task_data["abspath"],
        "source_size": source_size,
        "staged_size": staged_size,
        "staged_path": staged_info.get("path", ""),
        "size_delta": staged_size - source_size if staged_size else 0,
        "size_ratio": round(staged_size / source_size, 3) if source_size > 0 and staged_size > 0 else 0,
        "cache_path": task_data.get("cache_path", ""),
        "success": task_data.get("success", False),
        "start_time": str(task_data.get("start_time", "")),
        "finish_time": str(task_data.get("finish_time", "")),
        "log": task_data.get("log", ""),
        "library_id": task_data.get("library_id", 1),
        "source_codec": source_meta.get("codec", ""),
        "source_resolution": source_meta.get("resolution", ""),
        "source_container": source_meta.get("container", ""),
        "staged_codec": staged_meta.get("codec", ""),
        "staged_resolution": staged_meta.get("resolution", ""),
        "staged_container": staged_meta.get("container", ""),
        "vmaf_score": vmaf_score,
        "ssim_score": ssim_score,
    }


def approve_tasks(task_ids):
    """
    Approve tasks — sets their status to 'approved' so the postprocessor
    picks them up and finalizes the file replacement.

    :param task_ids: list of int
    :return: int count of updated tasks
    """
    return task.Task.set_tasks_status(task_ids, "approved")


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
        task_staging_dir = os.path.join(staging_path, f"task_{task_id}")
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
        return task.Task.set_tasks_status(task_ids, "pending")
    else:
        task_handler = task.Task()
        return task_handler.delete_tasks_recursively(task_ids)


def get_all_matching_task_ids(search_value="", library_ids=None, codec="", quality_min=0):
    """
    Return all task IDs that match the given search filter and are awaiting approval.
    Used for "select all matching" across pages.

    :param search_value: text search on file path
    :param library_ids: optional list of library IDs to filter by
    :return: list of int task IDs
    """
    if not _normalise_codec_filter(codec) and _normalise_quality_min(quality_min) == 0:
        task_handler = task.Task()
        results = task_handler.get_task_list_filtered_and_sorted(
            order={"column": "finish_time", "dir": "desc"},
            start=0,
            length=0,
            search_value=search_value,
            status="awaiting_approval",
            library_ids=library_ids or [],
        )
        return [t["id"] for t in results]

    _records_total, _records_filtered, results = _get_approval_items(
        params={
            "start": 0,
            "length": 0,
            "search_value": search_value,
            "library_ids": library_ids or [],
            "order_by": "finish_time",
            "order_direction": "desc",
            "codec": codec,
            "quality_min": quality_min,
        },
        force_all=True,
    )
    return [t["id"] for t in results]


def get_approval_count():
    """Return the count of tasks awaiting approval."""
    query = Tasks.select().where(Tasks.status == "awaiting_approval").limit(1000)
    return query.count()


def _get_staged_file_info(task_id, staging_path):
    """
    Get size and path of the staged file for a given task.

    :param task_id: int
    :param staging_path: str base staging directory
    :return: dict with 'size' and 'path'
    """
    task_staging_dir = os.path.join(staging_path, f"task_{task_id}")
    if not os.path.exists(task_staging_dir):
        return {"size": 0, "path": ""}

    # Find the first file in the staging directory
    try:
        for filename in os.listdir(task_staging_dir):
            filepath = os.path.join(task_staging_dir, filename)
            if os.path.isfile(filepath):
                return {
                    "size": os.path.getsize(filepath),
                    "path": filepath,
                }
    except OSError:
        pass

    return {"size": 0, "path": ""}
