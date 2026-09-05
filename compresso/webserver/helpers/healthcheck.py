#!/usr/bin/env python3

"""
compresso.healthcheck.py

Helper functions for the Health Check API.

"""

from typing import TypedDict

from compresso.libs.healthcheck import HealthCheckManager, HealthOrder
from compresso.libs.logs import CompressoLogging
from compresso.libs.startup import StartupState

logger = CompressoLogging.get_logger("healthcheck_helper")


class HealthPaginationParams(TypedDict, total=False):
    start: int
    length: int
    search_value: str | None
    library_id: int | None
    status_filter: str | None
    order: HealthOrder | None


def validate_library_exists(library_id: int | None) -> bool:
    """
    Validate that a library ID exists in the database.
    Raises ValueError if the library does not exist.
    Returns True on success (including when library_id is None).
    """
    if library_id is not None:
        try:
            from compresso.libs.unmodels import Libraries

            Libraries.get_by_id(library_id)
        except Exception:
            raise ValueError(f"Library with ID {library_id} does not exist") from None
    return True


def check_single_file(filepath: str, library_id: int = 1, mode: str = "quick") -> dict[str, object]:
    """Check a single file's health."""
    manager = HealthCheckManager()
    return manager.check_file(filepath, library_id=library_id, mode=mode)


def scan_library(library_id: int, mode: str = "quick") -> bool:
    """Start a background library scan."""
    manager = HealthCheckManager()
    return manager.schedule_library_scan(library_id, mode=mode)


def get_health_summary(library_id: int | None = None) -> dict[str, int]:
    """Get aggregate health status counts."""
    manager = HealthCheckManager()
    return manager.get_health_summary(library_id=library_id)


def get_health_statuses_paginated(params: HealthPaginationParams) -> dict[str, object]:
    """Get paginated health status records."""
    manager = HealthCheckManager()
    return manager.get_health_statuses_paginated(
        start=params.get("start", 0),
        length=params.get("length", 10),
        search_value=params.get("search_value", ""),
        library_id=params.get("library_id"),
        status_filter=params.get("status_filter"),
        order=params.get("order"),
    )


def cancel_scan() -> bool:
    """Cancel the current library scan."""
    return HealthCheckManager.cancel_scan()


def get_scan_progress() -> dict[str, object]:
    """Get current scan progress."""
    return {
        "scanning": HealthCheckManager.is_scanning(),
        "progress": HealthCheckManager.get_scan_progress(),
    }


def set_scan_workers(count: int) -> int:
    """Set the number of concurrent scan workers."""
    HealthCheckManager.set_worker_count(count)
    return HealthCheckManager.get_worker_count()


def get_scan_workers() -> dict[str, object]:
    """Get current worker count and scan status."""
    return {
        "worker_count": HealthCheckManager.get_worker_count(),
        "scanning": HealthCheckManager.is_scanning(),
        "progress": HealthCheckManager.get_scan_progress(),
    }


def get_startup_readiness() -> dict[str, object]:
    """Get deployment readiness state for startup-critical services."""
    return StartupState().snapshot()
