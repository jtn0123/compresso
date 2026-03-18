#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.healthstatus.py

    Health status model for tracking file health check results.

"""

import datetime

from peewee import *
from unmanic.libs.unmodels.lib import BaseModel


class HealthStatus(BaseModel):
    """
    HealthStatus

    Tracks health check results for media files.
    """
    abspath = TextField(null=False, unique=True)
    library_id = IntegerField(null=False, default=1, index=True)
    status = TextField(null=False, default='unchecked', index=True)  # unchecked, healthy, warning, corrupted, checking
    check_mode = TextField(null=True, default='quick')  # quick, thorough
    error_detail = TextField(null=True, default='')
    last_checked = DateTimeField(null=True, default=None, index=True)
    error_count = IntegerField(null=False, default=0)

    class Meta:
        indexes = (
            (('library_id', 'status'), False),
        )
