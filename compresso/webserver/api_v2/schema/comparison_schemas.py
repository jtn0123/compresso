#!/usr/bin/env python3

"""Marshmallow schemas for sample bake-off comparisons."""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema, BaseSuccessSchema


class ComparisonProfileSchema(BaseSchema):
    key = fields.Str(required=True)
    label = fields.Str(required=True)
    description = fields.Str(required=True)
    encoder = fields.Str(required=True)
    codec = fields.Str(required=True)
    crf = fields.Int(required=True)
    preset = fields.Str(required=True)
    hardware = fields.Boolean(required=True)
    available = fields.Boolean(required=True)


class ComparisonProfilesResponseSchema(BaseSuccessSchema):
    profiles = fields.List(fields.Nested(ComparisonProfileSchema()), required=True)


class RequestComparisonCreateSchema(BaseSchema):
    source_path = fields.Str(required=True)
    start_time = fields.Float(load_default=0, validate=validate.Range(min=0))
    duration = fields.Float(load_default=10, validate=validate.Range(min=1, max=30))
    library_id = fields.Int(load_default=1)
    profile_keys = fields.List(
        fields.Str(),
        required=True,
        validate=validate.Length(min=2, max=4),
    )


class ComparisonCreateResponseSchema(BaseSuccessSchema):
    batch_uuid = fields.Str(required=True)


class RequestComparisonStatusSchema(BaseSchema):
    batch_uuid = fields.Str(required=True)


class ComparisonCandidateSchema(BaseSchema):
    id = fields.Int(required=True)
    candidate_uuid = fields.Str(required=True)
    profile_key = fields.Str(required=True)
    profile_label = fields.Str(required=True)
    encoder = fields.Str(required=True)
    codec = fields.Str(required=True)
    status = fields.Str(required=True)
    progress = fields.Float(required=True)
    output_path = fields.Str(load_default="")
    output_url = fields.Str(load_default="")
    output_size = fields.Int(load_default=0)
    source_size = fields.Int(load_default=0)
    size_saved_bytes = fields.Int(load_default=0)
    size_saved_percent = fields.Float(load_default=0)
    vmaf_score = fields.Float(allow_none=True, load_default=None)
    ssim_score = fields.Float(allow_none=True, load_default=None)
    error = fields.Str(allow_none=True, load_default=None)


class ComparisonStatusResponseSchema(BaseSuccessSchema):
    batch_uuid = fields.Str(required=True)
    source_path = fields.Str(required=True)
    source_size = fields.Int(load_default=0)
    source_url = fields.Str(load_default="")
    library_id = fields.Int(required=True)
    start_time = fields.Float(required=True)
    duration = fields.Float(required=True)
    status = fields.Str(required=True)
    progress = fields.Float(required=True)
    winner_candidate_id = fields.Int(allow_none=True, load_default=None)
    full_encode_task_id = fields.Int(allow_none=True, load_default=None)
    error = fields.Str(allow_none=True, load_default=None)
    candidates = fields.List(fields.Nested(ComparisonCandidateSchema()), required=True)


class RequestComparisonWinnerSchema(RequestComparisonStatusSchema):
    candidate_uuid = fields.Str(required=True)
    queue_full_encode = fields.Boolean(load_default=False)


class RequestComparisonCleanupSchema(RequestComparisonStatusSchema):
    pass
