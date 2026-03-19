#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.compression_stats.py

    Helper functions for compression statistics API endpoints.

"""

from compresso.libs import history
from compresso.libs.logs import CompressoLogging

logger = CompressoLogging.get_logger('compression_stats')


def get_compression_summary(library_id=None):
    """
    Get library-wide compression summary statistics.

    :param library_id: Optional library ID to filter by
    :return: dict with summary data
    """
    history_logging = history.History()
    return history_logging.get_library_compression_summary(library_id=library_id)


def get_compression_stats_paginated(params):
    """
    Get paginated per-file compression statistics.

    :param params: dict with start, length, search_value, library_id, order
    :return: dict with recordsTotal, recordsFiltered, results
    """
    history_logging = history.History()
    return history_logging.get_compression_stats_paginated(
        start=params.get('start', 0),
        length=params.get('length', 10),
        search_value=params.get('search_value', ''),
        library_id=params.get('library_id'),
        order=params.get('order'),
    )


def get_codec_distribution(library_id=None):
    """Get codec distribution data."""
    history_logging = history.History()
    return history_logging.get_codec_distribution(library_id=library_id)


def get_resolution_distribution(library_id=None):
    """Get resolution distribution data."""
    history_logging = history.History()
    return history_logging.get_resolution_distribution(library_id=library_id)


def get_container_distribution(library_id=None):
    """Get container distribution data."""
    history_logging = history.History()
    return history_logging.get_container_distribution(library_id=library_id)


def get_space_saved_over_time(library_id=None, interval='day'):
    """Get space saved over time data."""
    history_logging = history.History()
    return history_logging.get_space_saved_over_time(library_id=library_id, interval=interval)


def get_pending_estimate():
    """
    Estimate potential space savings for pending tasks based on historical compression ratio.

    :return: dict with estimated savings
    """
    from compresso.libs.unmodels import Tasks

    history_logging = history.History()
    summary = history_logging.get_library_compression_summary()

    # Get pending tasks and sum their source sizes
    try:
        pending_query = Tasks.select().where(Tasks.status.in_(['pending', 'creating']))
        pending_count = pending_query.count()
        total_pending_size = 0
        for t in pending_query:
            total_pending_size += (t.source_size or 0)
    except Exception as e:
        logger.warning("Failed to query pending tasks: %s", str(e))
        pending_count = 0
        total_pending_size = 0

    avg_ratio = summary.get('avg_ratio', 1.0)
    if avg_ratio <= 0:
        avg_ratio = 1.0

    estimated_output_size = int(total_pending_size * avg_ratio)
    estimated_savings = total_pending_size - estimated_output_size

    return {
        'pending_count': pending_count,
        'total_pending_size': total_pending_size,
        'estimated_output_size': estimated_output_size,
        'estimated_savings': estimated_savings,
        'avg_ratio_used': avg_ratio,
    }
