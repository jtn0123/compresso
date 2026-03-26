#!/usr/bin/env python3

"""
    compresso.compressionstats.py

    Compression statistics model for tracking file size changes
    during transcoding operations.

"""

from peewee import *

from compresso.libs.unmodels.completedtasks import CompletedTasks
from compresso.libs.unmodels.lib import BaseModel


class CompressionStats(BaseModel):
    """
    CompressionStats

    Tracks compression data for each completed transcoding task.
    """
    completedtask = ForeignKeyField(CompletedTasks, backref='compression_stats', on_delete='CASCADE')
    source_size = BigIntegerField(null=False, default=0)
    destination_size = BigIntegerField(null=False, default=0)
    source_codec = TextField(null=True, default='', index=True)
    destination_codec = TextField(null=True, default='', index=True)
    source_resolution = TextField(null=True, default='', index=True)
    library_id = IntegerField(null=False, default=1, index=True)
    source_container = TextField(null=True, default='', index=True)
    destination_container = TextField(null=True, default='', index=True)
    encoding_duration_seconds = FloatField(null=True, default=0)
    avg_encoding_fps = FloatField(null=True, default=0)
    source_duration_seconds = FloatField(null=True, default=0)
    encoding_speed_ratio = FloatField(null=True, default=0)
