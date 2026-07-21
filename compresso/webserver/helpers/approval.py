#!/usr/bin/env python3

"""
compresso.approval.py

Helper functions for the approval workflow API.
Manages tasks in 'awaiting_approval' status — listing, approving, rejecting,
and fetching detail/comparison data.
"""

import datetime
import os
import shutil
from collections.abc import Mapping, Sequence
from typing import TypedDict

from compresso import config
from compresso.libs import narrowing, task
from compresso.libs.ffprobe_utils import extract_media_metadata
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_write
from compresso.libs.task import TaskOrder
from compresso.libs.unmodels.tasks import Tasks
from compresso.webserver.api_v2.schema.approval_schemas import APPROVAL_TASK_ORDER_COLUMNS
from compresso.webserver.helpers.pagination import parse_page_params

logger = CompressoLogging.get_logger(name=__name__)


class StagedFileInfo(TypedDict):
    size: int
    path: str


def _normalise_codec_filter(codec: object) -> str:
    return str(codec or "").strip().lower()


def _normalise_quality_min(value: object) -> float:
    if not isinstance(value, (str, int, float)):
        return 0.0
    try:
        return max(0.0, min(100.0, float(value or 0)))
    except ValueError:
        return 0.0


def _build_order(params: Mapping[str, object]) -> TaskOrder:
    order_by = narrowing.strict_str(params.get("order_by"), "finish_time")
    if order_by not in APPROVAL_TASK_ORDER_COLUMNS:
        order_by = "finish_time"

    order_direction = narrowing.strict_str(params.get("order_direction"), "desc")
    return {
        "column": order_by if order_by else "finish_time",
        "dir": order_direction if order_direction in ("asc", "desc") else "desc",
    }


def _build_approval_item(
    approval_task: Mapping[str, object], staging_path: str, include_library: bool = False
) -> dict[str, object]:
    task_id = narrowing.strict_int(approval_task["id"])
    source_path = narrowing.strict_str(approval_task.get("abspath"))
    source_size = narrowing.strict_int(approval_task.get("source_size"))
    item: dict[str, object] = {
        "id": task_id,
        "abspath": approval_task["abspath"],
        "priority": approval_task["priority"],
        "type": approval_task["type"],
        "status": approval_task["status"],
        "source_size": source_size,
        "finish_time": str(approval_task.get("finish_time", "")),
    }

    staged_info = _get_staged_file_info(task_id, staging_path)
    stored_staged_size = narrowing.strict_int(approval_task.get("staged_size"))
    staged_size = staged_info["size"] or stored_staged_size
    item["staged_size"] = staged_size
    item["staged_path"] = staged_info["path"]
    item["size_delta"] = staged_size - source_size if staged_size else 0

    metadata_updates: dict[str, object] = {}
    stored_source_codec = narrowing.strict_str(approval_task.get("source_codec"))
    source_meta = extract_media_metadata(source_path) if source_path else None
    if stored_source_codec:
        source_codec = stored_source_codec
    else:
        source_codec = source_meta["codec"] if source_meta else ""
        if source_codec:
            metadata_updates["source_codec"] = source_codec
    item["source_codec"] = source_codec
    item["source_resolution"] = source_meta["resolution"] if source_meta else ""

    staged_path = staged_info["path"]
    stored_staged_codec = narrowing.strict_str(approval_task.get("staged_codec"))
    if staged_path:
        staged_meta = extract_media_metadata(staged_path)
        item["staged_codec"] = stored_staged_codec or staged_meta.get("codec", "")
        item["staged_resolution"] = staged_meta.get("resolution", "")
        if item["staged_codec"] and not stored_staged_codec:
            metadata_updates["staged_codec"] = item["staged_codec"]
    elif stored_staged_codec:
        item["staged_codec"] = stored_staged_codec
        item["staged_resolution"] = ""
    else:
        item["staged_codec"] = ""
        item["staged_resolution"] = ""
    if staged_path and staged_info["size"]:
        metadata_updates["staged_size"] = staged_info["size"]

    item["vmaf_score"] = approval_task.get("vmaf_score")
    item["ssim_score"] = approval_task.get("ssim_score")

    _backfill_approval_metadata(task_id, approval_task, metadata_updates)

    if include_library:
        library = Library(narrowing.strict_int(approval_task["library_id"], 1))
        item["library_id"] = library.get_id()
        item["library_name"] = library.get_name()

    return item


def _backfill_approval_metadata(
    task_id: int,
    approval_task: Mapping[str, object],
    metadata_updates: Mapping[str, object],
) -> None:
    if not metadata_updates:
        return

    changed = {
        key: value
        for key, value in metadata_updates.items()
        if value not in ("", None) and approval_task.get(key) in ("", None, 0)
    }
    if not changed:
        return

    try:
        changed["metadata_updated_at"] = datetime.datetime.now()
        execute_write(Tasks.update(**changed).where(Tasks.id == task_id))
    except Exception as e:
        logger.debug("Failed to backfill approval metadata for task %s: %s", task_id, e)


def _approval_summary_item_from_task(approval_task: Mapping[str, object], staging_path: str) -> dict[str, object]:
    task_id = narrowing.strict_int(approval_task["id"])
    item: dict[str, object] = {
        "id": task_id,
        "abspath": approval_task.get("abspath", ""),
        "source_size": narrowing.strict_int(approval_task.get("source_size")),
        "vmaf_score": approval_task.get("vmaf_score"),
        "source_codec": approval_task.get("source_codec") or "",
        "staged_codec": approval_task.get("staged_codec") or "",
        "staged_size": narrowing.strict_int(approval_task.get("staged_size")),
    }

    metadata_updates: dict[str, object] = {}
    source_codec = narrowing.strict_str(item["source_codec"])
    source_path = narrowing.strict_str(item["abspath"])
    if not source_codec and source_path:
        source_meta = extract_media_metadata(source_path)
        item["source_codec"] = source_meta.get("codec", "")
        if item["source_codec"]:
            metadata_updates["source_codec"] = item["source_codec"]

    if not narrowing.strict_str(item["staged_codec"]) or not narrowing.strict_int(item["staged_size"]):
        staged_info = _get_staged_file_info(task_id, staging_path)
        staged_path = staged_info.get("path", "")
        if staged_info.get("size"):
            item["staged_size"] = staged_info.get("size", 0)
            metadata_updates["staged_size"] = item["staged_size"]
        if staged_path and not item["staged_codec"]:
            staged_meta = extract_media_metadata(staged_path)
            item["staged_codec"] = staged_meta.get("codec", "")
            if item["staged_codec"]:
                metadata_updates["staged_codec"] = item["staged_codec"]

    staged_size = narrowing.strict_int(item["staged_size"])
    source_size = narrowing.strict_int(item["source_size"])
    item["size_delta"] = staged_size - source_size if staged_size else 0
    _backfill_approval_metadata(task_id, approval_task, metadata_updates)
    return item


def _matches_approval_filters(item: Mapping[str, object], codec_filter: object = "", quality_min: object = 0) -> bool:
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
        if not isinstance(vmaf_score, (str, int, float)):
            return False
        try:
            if float(vmaf_score) < quality_min:
                return False
        except ValueError:
            return False

    return True


def _get_approval_items(
    params: Mapping[str, object], include_library: bool = False, force_all: bool = False
) -> tuple[int, int, list[dict[str, object]]]:
    page = parse_page_params(params)
    codec_filter = narrowing.strict_str(params.get("codec"))
    quality_min = _normalise_quality_min(params.get("quality_min", 0))
    has_derived_filters = bool(_normalise_codec_filter(codec_filter)) or quality_min > 0

    order = _build_order(params)

    task_handler = task.Task()
    records_total_count = task_handler.get_total_task_list_count()
    count_query = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=0,
        length=0,
        search_value=page.search_value,
        status="awaiting_approval",
        library_ids=page.library_ids,
    )

    data_start = 0 if has_derived_filters or force_all else page.start
    data_length = 0 if has_derived_filters or force_all else page.length
    approval_task_results = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=data_start,
        length=data_length,
        search_value=page.search_value,
        status="awaiting_approval",
        library_ids=page.library_ids,
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
    if (has_derived_filters or force_all) and page.length:
        items = items[page.start : page.start + page.length]

    return records_total_count, records_filtered_count, items


def prepare_filtered_approval_tasks(params: Mapping[str, object], include_library: bool = False) -> dict[str, object]:
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


def prepare_approval_summary(params: Mapping[str, object]) -> dict[str, object]:
    """
    Return aggregate summary data for tasks awaiting approval.

    :param params: dict with search/filter parameters
    :return: dict with counts, aggregate sizes, VMAF average, and codec options
    """
    page = parse_page_params(params)
    codec_filter = narrowing.strict_str(params.get("codec"))
    quality_min = _normalise_quality_min(params.get("quality_min", 0))
    order = _build_order(params)

    task_handler = task.Task()
    approval_task_results = task_handler.get_task_list_filtered_and_sorted(
        order=order,
        start=0,
        length=0,
        search_value=page.search_value,
        status="awaiting_approval",
        library_ids=page.library_ids,
    )

    settings = config.Config()
    staging_path = settings.get_staging_path()
    items = [_approval_summary_item_from_task(approval_task, staging_path) for approval_task in approval_task_results]
    items = [item for item in items if _matches_approval_filters(item, codec_filter=codec_filter, quality_min=quality_min)]

    codec_options = sorted(
        {
            codec
            for item in items
            for value in (item.get("source_codec"), item.get("staged_codec"))
            if (codec := narrowing.strict_str(value))
        }
    )
    with_vmaf = [narrowing.strict_float(value) for item in items if (value := item.get("vmaf_score")) is not None]
    items_with_staged_files = [item for item in items if narrowing.strict_int(item.get("staged_size")) > 0]
    total_source_size = sum(narrowing.strict_int(item.get("source_size")) for item in items)
    total_staged_size = sum(narrowing.strict_int(item.get("staged_size")) for item in items)
    total_space_saved = sum(abs(delta) for item in items if (delta := narrowing.strict_int(item.get("size_delta"))) < 0)
    savings_percentages = [
        (
            (narrowing.strict_int(item.get("source_size")) - narrowing.strict_int(item.get("staged_size")))
            / narrowing.strict_int(item.get("source_size"))
        )
        * 100
        for item in items_with_staged_files
        if narrowing.strict_int(item.get("source_size")) > 0
    ]
    largest: dict[str, object] | None = None
    for item in items_with_staged_files:
        size_delta = narrowing.strict_int(item.get("size_delta"))
        if size_delta >= 0:
            continue
        if largest is None or abs(size_delta) > abs(narrowing.strict_int(largest.get("size_delta"))):
            largest = item

    return {
        "total_count": len(items),
        "total_source_size": total_source_size,
        "total_staged_size": total_staged_size,
        "total_space_saved": total_space_saved,
        "average_savings_percent": sum(savings_percentages) / len(savings_percentages) if savings_percentages else 0,
        "largest_savings_file": largest.get("abspath", "") if largest else "",
        "largest_savings_bytes": abs(narrowing.strict_int(largest.get("size_delta"))) if largest else 0,
        "average_vmaf": sum(with_vmaf) / len(with_vmaf) if with_vmaf else None,
        "codec_options": codec_options,
    }


def get_approval_task_detail(task_id: int) -> dict[str, object] | None:
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

    source_size = narrowing.strict_int(task_data.get("source_size"))
    staged_size = staged_info["size"]

    # Extract media metadata for source and staged files
    source_path = narrowing.strict_str(task_data.get("abspath"))
    source_meta = extract_media_metadata(source_path) if source_path else None
    staged_path = staged_info["path"]
    staged_meta = extract_media_metadata(staged_path) if staged_path else None

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
        "source_codec": source_meta["codec"] if source_meta else "",
        "source_resolution": source_meta["resolution"] if source_meta else "",
        "source_container": source_meta["container"] if source_meta else "",
        "staged_codec": staged_meta["codec"] if staged_meta else "",
        "staged_resolution": staged_meta["resolution"] if staged_meta else "",
        "staged_container": staged_meta["container"] if staged_meta else "",
        "vmaf_score": vmaf_score,
        "ssim_score": ssim_score,
    }


def approve_tasks(task_ids: Sequence[int]) -> int:
    """
    Approve tasks — sets their status to 'approved' so the postprocessor
    picks them up and finalizes the file replacement.

    :param task_ids: list of int
    :return: int count of updated tasks
    """
    return task.Task.set_tasks_status(task_ids, "approved")


def reject_tasks(task_ids: Sequence[int], requeue: bool = False) -> int | bool:
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


def get_all_matching_task_ids(
    search_value: str = "",
    library_ids: Sequence[int] | None = None,
    codec: str = "",
    quality_min: float = 0,
) -> list[int]:
    """
    Return all task IDs that match the given search filter and are awaiting approval.
    Used for "select all matching" across pages.

    :param search_value: text search on file path
    :param library_ids: optional list of library IDs to filter by
    :return: list of int task IDs
    """
    if not _normalise_codec_filter(codec) and _normalise_quality_min(quality_min) == 0:
        task_handler = task.Task()
        query_results = task_handler.get_task_list_filtered_and_sorted(
            order={"column": "finish_time", "dir": "desc"},
            start=0,
            length=0,
            search_value=search_value,
            status="awaiting_approval",
            library_ids=list(library_ids or []),
        )
        return [task_id for row in query_results if isinstance((task_id := row.get("id")), int)]

    _records_total, _records_filtered, filtered_results = _get_approval_items(
        params={
            "start": 0,
            "length": 0,
            "search_value": search_value,
            "library_ids": list(library_ids or []),
            "order_by": "finish_time",
            "order_direction": "desc",
            "codec": codec,
            "quality_min": quality_min,
        },
        force_all=True,
    )
    return [task_id for row in filtered_results if isinstance((task_id := row.get("id")), int)]


def get_approval_count() -> int:
    """Return the count of tasks awaiting approval."""
    query = Tasks.select().where(Tasks.status == "awaiting_approval").limit(1000)
    return int(query.count())


def _get_staged_file_info(task_id: int, staging_path: str) -> StagedFileInfo:
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
