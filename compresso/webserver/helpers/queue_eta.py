#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.queue_eta.py

    Helper functions for estimating encoding queue ETA.

"""

from compresso.libs import history
from compresso.libs.logs import CompressoLogging

logger = CompressoLogging.get_logger(name=__name__)


def estimate_queue_eta(foreman, completed_tasks_model=None):
    """
    Estimate total time to process all pending tasks.

    Returns dict with:
    - active_workers_eta_seconds: max ETA among busy workers (they run in parallel)
    - pending_tasks_count: number of pending tasks
    - estimated_per_task_seconds: average from recent history
    - total_queue_eta_seconds: active_eta + (pending * avg / num_workers)
    - eta_confidence: 'high' (10+ history), 'medium' (3-9), 'low' (0-2)

    :param foreman: Foreman instance with get_all_worker_status()
    :param completed_tasks_model: Optional CompletedTasks model class (for testing)
    :return: dict with ETA estimates
    """
    try:
        workers_status = foreman.get_all_worker_status()
    except Exception:
        logger.exception("Failed to get worker status for queue ETA")
        workers_status = []

    # Count total workers and collect ETAs from active (non-idle) workers
    total_workers = len(workers_status)
    active_etas = []
    num_busy_workers = 0
    num_paused_workers = 0

    for worker in workers_status:
        if worker.get('paused'):
            num_paused_workers += 1
            continue
        if not worker.get('idle'):
            num_busy_workers += 1
            subprocess_stats = worker.get('subprocess') or {}
            eta = subprocess_stats.get('eta_seconds')
            if eta is not None:
                active_etas.append(eta)

    # The active workers run in parallel, so the bottleneck is the max ETA
    active_workers_eta_seconds = max(active_etas) if active_etas else 0

    # Query recent completed tasks for average processing time
    estimated_per_task_seconds, history_count = _get_avg_task_duration(
        completed_tasks_model
    )

    # Get pending task count
    pending_tasks_count = _get_pending_tasks_count()

    # Determine how many workers can process pending tasks
    # Workers that are not paused are available (busy ones will finish their current task)
    available_workers = total_workers - num_paused_workers
    if available_workers < 1:
        available_workers = 1

    # Calculate total queue ETA:
    # active_eta covers the current in-progress tasks (parallel),
    # then pending tasks are distributed across available workers
    if pending_tasks_count > 0 and estimated_per_task_seconds > 0:
        pending_eta = int(
            (pending_tasks_count * estimated_per_task_seconds) / available_workers
        )
    else:
        pending_eta = 0

    total_queue_eta_seconds = active_workers_eta_seconds + pending_eta

    # Confidence level based on historical data
    if history_count >= 10:
        eta_confidence = 'high'
    elif history_count >= 3:
        eta_confidence = 'medium'
    else:
        eta_confidence = 'low'

    return {
        'active_workers_eta_seconds': active_workers_eta_seconds,
        'pending_tasks_count':        pending_tasks_count,
        'estimated_per_task_seconds': estimated_per_task_seconds,
        'total_queue_eta_seconds':    total_queue_eta_seconds,
        'eta_confidence':             eta_confidence,
        'total_workers':              total_workers,
        'busy_workers':               num_busy_workers,
        'paused_workers':             num_paused_workers,
    }


def _get_avg_task_duration(completed_tasks_model=None):
    """
    Query the last 50 completed tasks and compute average processing duration.

    :param completed_tasks_model: Optional model class override (for testing)
    :return: (avg_seconds, count) tuple
    """
    try:
        if completed_tasks_model is not None:
            CompletedTasks = completed_tasks_model
        else:
            from compresso.libs.unmodels import CompletedTasks

        recent_tasks = (
            CompletedTasks
            .select(CompletedTasks.start_time, CompletedTasks.finish_time)
            .where(CompletedTasks.task_success == True)  # noqa: E712
            .order_by(CompletedTasks.finish_time.desc())
            .limit(50)
        )

        durations = []
        for task in recent_tasks:
            start = task.start_time
            finish = task.finish_time
            if start and finish:
                delta = (finish - start).total_seconds()
                if delta > 0:
                    durations.append(delta)

        if durations:
            avg = sum(durations) / len(durations)
            return round(avg, 1), len(durations)
        return 0, 0

    except Exception:
        logger.exception("Failed to query completed tasks for ETA estimation")
        return 0, 0


def _get_pending_tasks_count():
    """
    Get the count of pending tasks in the queue.

    :return: int count of pending tasks
    """
    try:
        from compresso.libs.unmodels import Tasks
        return Tasks.select().where(Tasks.status == 'pending').count()
    except Exception:
        logger.exception("Failed to query pending tasks count")
        return 0
