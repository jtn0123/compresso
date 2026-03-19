#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.compression_schemas.py

    Marshmallow schemas for compression statistics API endpoints.

"""

from marshmallow import fields
from compresso.webserver.api_v2.schema.schemas import BaseSchema, BaseSuccessSchema, RequestTableDataSchema


class RequestCompressionStatsSchema(RequestTableDataSchema):
    """Schema for requesting paginated compression stats"""
    library_id = fields.Int(
        required=False,
        description="Optional library ID to filter by",
        allow_none=True,
    )


class RequestCompressionSummarySchema(BaseSchema):
    """Schema for requesting compression summary"""
    library_id = fields.Int(
        required=False,
        description="Optional library ID to filter by",
        allow_none=True,
    )


class CompressionStatsResultSchema(BaseSchema):
    """Schema for a single compression stats result"""
    id = fields.Int()
    completedtask_id = fields.Int()
    task_label = fields.Str()
    task_success = fields.Boolean()
    finish_time = fields.Raw()
    source_size = fields.Int()
    destination_size = fields.Int()
    source_codec = fields.Str()
    destination_codec = fields.Str()
    source_resolution = fields.Str()
    library_id = fields.Int()
    ratio = fields.Float()
    space_saved = fields.Int()


class CompressionStatsSchema(BaseSuccessSchema):
    """Schema for paginated compression stats response"""
    recordsTotal = fields.Int()
    recordsFiltered = fields.Int()
    results = fields.List(fields.Raw())


class PerLibraryCompressionSchema(BaseSchema):
    """Schema for per-library compression summary"""
    library_id = fields.Int()
    total_source_size = fields.Int()
    total_destination_size = fields.Int()
    file_count = fields.Int()
    avg_ratio = fields.Float()
    space_saved = fields.Int()


class CompressionSummarySchema(BaseSuccessSchema):
    """Schema for compression summary response"""
    total_source_size = fields.Int()
    total_destination_size = fields.Int()
    file_count = fields.Int()
    avg_ratio = fields.Float()
    space_saved = fields.Int()
    per_library = fields.List(fields.Raw())


class PendingEstimateSchema(BaseSuccessSchema):
    """Schema for pending estimate response"""
    pending_count = fields.Int()
    total_pending_size = fields.Int()
    estimated_output_size = fields.Int()
    estimated_savings = fields.Int()
    avg_ratio_used = fields.Float()


class CodecDistributionSchema(BaseSuccessSchema):
    """Schema for codec distribution response"""
    source_codecs = fields.List(fields.Raw())
    destination_codecs = fields.List(fields.Raw())


class ResolutionDistributionSchema(BaseSuccessSchema):
    """Schema for resolution distribution response"""
    resolutions = fields.List(fields.Raw())


class ContainerDistributionSchema(BaseSuccessSchema):
    """Schema for container distribution response"""
    source_containers = fields.List(fields.Raw())
    destination_containers = fields.List(fields.Raw())


class TimelineSchema(BaseSuccessSchema):
    """Schema for space saved timeline response"""
    data = fields.List(fields.Raw())


class LibraryAnalysisRequestSchema(BaseSchema):
    """Schema for library analysis request"""
    library_id = fields.Int(required=True, description="Library ID to analyze")


class LibraryAnalysisStatusSchema(BaseSuccessSchema):
    """Schema for library analysis status response"""
    status = fields.Str()
    progress = fields.Raw()
    version = fields.Int()
    results = fields.Raw(allow_none=True)


class OptimizationProgressSchema(BaseSuccessSchema):
    """Schema for optimization progress response"""
    total_files = fields.Int()
    processed_files = fields.Int()
    percent = fields.Float()
