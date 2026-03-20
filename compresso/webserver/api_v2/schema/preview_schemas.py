#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.preview_schemas.py

    Marshmallow schemas for preview API endpoints.

"""

from marshmallow import fields, validate
from compresso.webserver.api_v2.schema.schemas import BaseSchema, BaseSuccessSchema


class RequestPreviewCreateSchema(BaseSchema):
    """Schema for creating a preview job"""
    source_path = fields.Str(
        required=True,
        metadata={'description': "Absolute path to the source media file"},
    )
    start_time = fields.Float(
        required=False,
        metadata={'description': "Start time in seconds"},
        load_default=0,
        validate=validate.Range(min=0),
    )
    duration = fields.Float(
        required=False,
        metadata={'description': "Duration in seconds (max 30)"},
        load_default=10,
        validate=validate.Range(min=0.1, max=30),
    )
    library_id = fields.Int(
        required=False,
        metadata={'description': "Library ID to use for pipeline config"},
        load_default=1,
    )


class PreviewCreateResponseSchema(BaseSuccessSchema):
    """Schema for preview create response"""
    job_id = fields.Str()


class RequestPreviewStatusSchema(BaseSchema):
    """Schema for checking preview status"""
    job_id = fields.Str(
        required=True,
        metadata={'description': "The preview job ID"},
    )


class PreviewStatusResponseSchema(BaseSuccessSchema):
    """Schema for preview status response"""
    job_id = fields.Str()
    status = fields.Str()
    error = fields.Str(allow_none=True)
    source_url = fields.Str(load_default='')
    encoded_url = fields.Str(load_default='')
    source_size = fields.Int(load_default=0)
    encoded_size = fields.Int(load_default=0)
    source_codec = fields.Str(load_default='')
    encoded_codec = fields.Str(load_default='')
    vmaf_score = fields.Float(allow_none=True, load_default=None)
    ssim_score = fields.Float(allow_none=True, load_default=None)
    encoded_by_pipeline = fields.Boolean(load_default=False)


class RequestPreviewCleanupSchema(BaseSchema):
    """Schema for cleaning up a preview job"""
    job_id = fields.Str(
        required=True,
        metadata={'description': "The preview job ID to clean up"},
    )
