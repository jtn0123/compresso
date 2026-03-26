#!/usr/bin/env python3

"""
    compresso.healthcheck.py

    Helper functions for the Health Check API.

"""

from compresso.libs.healthcheck import HealthCheckManager
from compresso.libs.logs import CompressoLogging
from compresso.libs.startup import StartupState

logger = CompressoLogging.get_logger('healthcheck_helper')


def validate_library_exists(library_id):
    """
    Validate that a library ID exists in the database.
    Returns True if valid, raises ValueError if not.
    """
    if library_id is None:
        return True
    try:
        from compresso.libs.unmodels import Libraries
        Libraries.get_by_id(library_id)
        return True
    except Exception:
        raise ValueError(f"Library with ID {library_id} does not exist") from None


def check_single_file(filepath, library_id=1, mode='quick'):
    """Check a single file's health."""
    manager = HealthCheckManager()
    return manager.check_file(filepath, library_id=library_id, mode=mode)


def scan_library(library_id, mode='quick'):
    """Start a background library scan."""
    manager = HealthCheckManager()
    return manager.schedule_library_scan(library_id, mode=mode)


def get_health_summary(library_id=None):
    """Get aggregate health status counts."""
    manager = HealthCheckManager()
    return manager.get_health_summary(library_id=library_id)


def get_health_statuses_paginated(params):
    """Get paginated health status records."""
    manager = HealthCheckManager()
    return manager.get_health_statuses_paginated(
        start=params.get('start', 0),
        length=params.get('length', 10),
        search_value=params.get('search_value', ''),
        library_id=params.get('library_id'),
        status_filter=params.get('status_filter'),
        order=params.get('order'),
    )


def cancel_scan():
    """Cancel the current library scan."""
    return HealthCheckManager.cancel_scan()


def get_scan_progress():
    """Get current scan progress."""
    return {
        'scanning': HealthCheckManager.is_scanning(),
        'progress': HealthCheckManager.get_scan_progress(),
    }


def set_scan_workers(count):
    """Set the number of concurrent scan workers."""
    HealthCheckManager.set_worker_count(count)
    return HealthCheckManager.get_worker_count()


def get_scan_workers():
    """Get current worker count and scan status."""
    return {
        'worker_count': HealthCheckManager.get_worker_count(),
        'scanning': HealthCheckManager.is_scanning(),
        'progress': HealthCheckManager.get_scan_progress(),
    }


def get_startup_readiness():
    """Get deployment readiness state for startup-critical services."""
    return StartupState().snapshot()
