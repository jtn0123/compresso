#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.healthcheck.py

    Helper functions for the Health Check API.

"""

from unmanic.libs.healthcheck import HealthCheckManager


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


def get_scan_progress():
    """Get current scan progress."""
    return {
        'scanning': HealthCheckManager.is_scanning(),
        'progress': HealthCheckManager.get_scan_progress(),
    }
