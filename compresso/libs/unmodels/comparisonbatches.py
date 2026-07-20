#!/usr/bin/env python3

"""Persistent sample-comparison batch models."""

import datetime

from peewee import BigIntegerField, DateTimeField, FloatField, IntegerField, TextField

from compresso.libs.unmodels.lib import BaseModel


class ComparisonBatches(BaseModel):
    """A source segment and the candidate encodes being compared."""

    batch_uuid = TextField(null=False, unique=True, index=True)
    source_path = TextField(null=False)
    source_size = BigIntegerField(null=False, default=0)
    source_url = TextField(null=False, default="")
    library_id = IntegerField(null=False, default=1, index=True)
    start_time = FloatField(null=False, default=0)
    duration = FloatField(null=False, default=10)
    status = TextField(null=False, default="queued", index=True)
    progress = FloatField(null=False, default=0)
    winner_candidate_id = IntegerField(null=True, default=None)
    full_encode_task_id = IntegerField(null=True, default=None)
    error = TextField(null=True, default=None)
    created_at = DateTimeField(null=False, default=datetime.datetime.now)
    updated_at = DateTimeField(null=False, default=datetime.datetime.now)

    class Meta:
        table_name = "comparison_batches"
