#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.compressionstats.py

    Compression statistics model for tracking file size changes
    during transcoding operations.

"""

from peewee import *
from unmanic.libs.unmodels.lib import BaseModel
from unmanic.libs.unmodels.completedtasks import CompletedTasks


class CompressionStats(BaseModel):
    """
    CompressionStats

    Tracks compression data for each completed transcoding task.
    """
    completedtask = ForeignKeyField(CompletedTasks, backref='compression_stats', on_delete='CASCADE')
    source_size = BigIntegerField(null=False, default=0)
    destination_size = BigIntegerField(null=False, default=0)
    source_codec = TextField(null=True, default='')
    destination_codec = TextField(null=True, default='')
    source_resolution = TextField(null=True, default='')
    library_id = IntegerField(null=False, default=1, index=True)
