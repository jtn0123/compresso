#!/usr/bin/env python3

"""
compresso.compression_stats.py

Helper functions for compression statistics API endpoints.

"""

from collections.abc import Iterable
from typing import Protocol, TypedDict, cast

from peewee import fn

from compresso.libs import history
from compresso.libs.history import HistoryOrder
from compresso.libs.logs import CompressoLogging

logger = CompressoLogging.get_logger("compression_stats")


class CompressionStatsParams(TypedDict, total=False):
    start: int
    length: int
    search_value: str | None
    library_id: int | None
    order: HistoryOrder | None


class _EncodingSpeedRow(Protocol):
    date: object
    destination_codec: str | None
    avg_fps: float | None
    avg_speed: float | None
    avg_duration: float | None
    count: int | None


def get_compression_summary(library_id: int | None = None) -> dict[str, object]:
    """
    Get library-wide compression summary statistics.

    :param library_id: Optional library ID to filter by
    :return: dict with summary data
    """
    history_logging = history.History()
    return history_logging.get_library_compression_summary(library_id=library_id)


def get_compression_stats_paginated(params: CompressionStatsParams) -> dict[str, object]:
    """
    Get paginated per-file compression statistics.

    :param params: dict with start, length, search_value, library_id, order
    :return: dict with recordsTotal, recordsFiltered, results
    """
    history_logging = history.History()
    return history_logging.get_compression_stats_paginated(
        start=params.get("start", 0),
        length=params.get("length", 10),
        search_value=params.get("search_value", ""),
        library_id=params.get("library_id"),
        order=params.get("order"),
    )


def get_codec_distribution(library_id: int | None = None) -> dict[str, object]:
    """Get codec distribution data."""
    history_logging = history.History()
    return history_logging.get_codec_distribution(library_id=library_id)


def get_resolution_distribution(library_id: int | None = None) -> list[dict[str, object]]:
    """Get resolution distribution data."""
    history_logging = history.History()
    return history_logging.get_resolution_distribution(library_id=library_id)


def get_container_distribution(library_id: int | None = None) -> dict[str, object]:
    """Get container distribution data."""
    history_logging = history.History()
    return history_logging.get_container_distribution(library_id=library_id)


def get_space_saved_over_time(library_id: int | None = None, interval: str = "day") -> list[dict[str, object]]:
    """Get space saved over time data."""
    history_logging = history.History()
    return history_logging.get_space_saved_over_time(library_id=library_id, interval=interval)


def get_encoding_speed_timeline(library_id: int | None = None) -> list[dict[str, object]]:
    """
    Get encoding speed data over time for charting.

    :param library_id: Optional library ID to filter by
    :return: list of dicts with date, avg_fps, avg_speed_ratio, codec
    """
    from peewee import fn

    from compresso.libs.unmodels import CompletedTasks, CompressionStats

    query = (
        CompressionStats.select(
            fn.DATE(CompletedTasks.finish_time).alias("date"),
            CompressionStats.destination_codec,
            fn.AVG(CompressionStats.avg_encoding_fps).alias("avg_fps"),
            fn.AVG(CompressionStats.encoding_speed_ratio).alias("avg_speed"),
            fn.AVG(CompressionStats.encoding_duration_seconds).alias("avg_duration"),
            fn.COUNT(CompressionStats.id).alias("count"),
        )
        .join(CompletedTasks)
        .where(CompressionStats.avg_encoding_fps > 0)
    )

    if library_id is not None:
        query = query.where(CompressionStats.library_id == library_id)

    query = (
        query.group_by(fn.DATE(CompletedTasks.finish_time), CompressionStats.destination_codec)
        .order_by(fn.DATE(CompletedTasks.finish_time).desc())
        .limit(200)
    )

    results: list[dict[str, object]] = []
    rows = cast(Iterable[_EncodingSpeedRow], query)
    for row in rows:
        results.append(
            {
                "date": str(row.date) if hasattr(row, "date") else "",
                "codec": row.destination_codec or "unknown",
                "avg_fps": round(float(row.avg_fps or 0), 1),
                "avg_speed_ratio": round(float(row.avg_speed or 0), 2),
                "avg_duration": round(float(row.avg_duration or 0), 1),
                "count": int(row.count or 0),
            }
        )

    return results


def get_pending_estimate() -> dict[str, object]:
    """
    Estimate potential space savings for pending tasks based on historical compression ratio.

    :return: dict with estimated savings
    """
    from compresso.libs.unmodels import Tasks

    history_logging = history.History()
    summary = history_logging.get_library_compression_summary()

    # Get pending tasks and sum their source sizes
    try:
        aggregate = (
            Tasks.select(
                fn.COUNT(Tasks.id).alias("pending_count"),
                fn.COALESCE(fn.SUM(Tasks.source_size), 0).alias("total_pending_size"),
            )
            .where(Tasks.status.in_(["pending", "creating"]))
            .dicts()
            .get()
        )
        pending_count_value: object = aggregate.get("pending_count")
        total_pending_size_value: object = aggregate.get("total_pending_size")
        pending_count = int(pending_count_value) if isinstance(pending_count_value, (str, int, float)) else 0
        total_pending_size = int(total_pending_size_value) if isinstance(total_pending_size_value, (str, int, float)) else 0
    except Exception as e:
        logger.warning("Failed to query pending tasks: %s", str(e))
        pending_count = 0
        total_pending_size = 0

    avg_ratio_value = summary.get("avg_ratio", 1.0)
    avg_ratio = float(avg_ratio_value) if isinstance(avg_ratio_value, (str, int, float)) else 1.0
    if avg_ratio <= 0:
        avg_ratio = 1.0

    estimated_output_size = int(total_pending_size * avg_ratio)
    estimated_savings = total_pending_size - estimated_output_size

    return {
        "pending_count": pending_count,
        "total_pending_size": total_pending_size,
        "estimated_output_size": estimated_output_size,
        "estimated_savings": estimated_savings,
        "avg_ratio_used": avg_ratio,
    }
