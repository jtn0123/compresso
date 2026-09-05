#!/usr/bin/env python3

"""Persistent candidate jobs for sample-comparison batches."""

import datetime

from peewee import BigIntegerField, DateTimeField, FloatField, ForeignKeyField, TextField

from compresso.libs.unmodels.comparisonbatches import ComparisonBatches
from compresso.libs.unmodels.lib import BaseModel


class ComparisonCandidates(BaseModel):
    """One short encode produced with a known comparison profile."""

    batch = ForeignKeyField(ComparisonBatches, backref="candidates", on_delete="CASCADE", index=True)
    candidate_uuid = TextField(null=False, unique=True, index=True)
    profile_key = TextField(null=False)
    profile_label = TextField(null=False)
    encoder = TextField(null=False)
    codec = TextField(null=False, default="")
    options_json = TextField(null=False, default="{}")
    status = TextField(null=False, default="queued", index=True)
    progress = FloatField(null=False, default=0)
    output_path = TextField(null=False, default="")
    preview_path = TextField(null=False, default="")
    output_url = TextField(null=False, default="")
    output_size = BigIntegerField(null=False, default=0)
    source_size = BigIntegerField(null=False, default=0)
    size_saved_bytes = BigIntegerField(null=False, default=0)
    size_saved_percent = FloatField(null=False, default=0)
    vmaf_score = FloatField(null=True, default=None)
    ssim_score = FloatField(null=True, default=None)
    error = TextField(null=True, default=None)
    created_at = DateTimeField(null=False, default=datetime.datetime.now)
    started_at = DateTimeField(null=True, default=None)
    completed_at = DateTimeField(null=True, default=None)

    class Meta:
        table_name = "comparison_candidates"
        indexes = ((("batch", "status"), False),)
