#!/usr/bin/env python3

"""
compresso.healthcheck_schemas.py

Marshmallow schemas for Health Check API endpoints.

"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema, BaseSuccessSchema, RequestTableDataSchema


class RequestHealthCheckScanSchema(BaseSchema):
    """Schema for scanning a single file"""

    file_path = fields.Str(
        required=True,
        metadata={"description": "Absolute path to the file to check"},
    )
    library_id = fields.Int(
        required=False,
        load_default=1,
        metadata={"description": "Library ID"},
    )
    mode = fields.Str(
        required=False,
        load_default="quick",
        metadata={"description": "Check mode: 'quick' or 'thorough'"},
        validate=validate.OneOf(["quick", "thorough"]),
    )


class RequestHealthCheckLibraryScanSchema(BaseSchema):
    """Schema for scanning an entire library"""

    library_id = fields.Int(
        required=True,
        metadata={"description": "Library ID to scan"},
    )
    mode = fields.Str(
        required=False,
        load_default="quick",
        metadata={"description": "Check mode: 'quick' or 'thorough'"},
        validate=validate.OneOf(["quick", "thorough"]),
    )


class RequestHealthCheckStatusSchema(RequestTableDataSchema):
    """Schema for paginated health status list"""

    library_id = fields.Int(
        required=False,
        allow_none=True,
        metadata={"description": "Optional library ID filter"},
    )
    status_filter = fields.Str(
        required=False,
        allow_none=True,
        metadata={"description": "Optional status filter: healthy, corrupted, warning, unchecked, checking"},
        validate=validate.OneOf(["healthy", "corrupted", "warning", "unchecked", "checking"]),
    )


class HealthCheckScanResponseSchema(BaseSuccessSchema):
    """Schema for single file scan response"""

    abspath = fields.Str()
    status = fields.Str()
    check_mode = fields.Str()
    error_detail = fields.Str()
    last_checked = fields.Str()
    error_count = fields.Int()


class HealthCheckLibraryScanResponseSchema(BaseSuccessSchema):
    """Schema for library scan response"""

    started = fields.Boolean()
    message = fields.Str()


class HealthCheckProgressSchema(BaseSchema):
    """Backward-compatible progress with explicit discovery and terminal state."""

    phase = fields.Str(metadata={"description": "idle, discovering, checking, cancelling, complete, cancelled, or failed"})
    total = fields.Int()
    discovered = fields.Int()
    discovery_complete = fields.Boolean()
    checked = fields.Int()
    cancelled = fields.Boolean()
    error = fields.Str(allow_none=True)
    library_id = fields.Int(allow_none=True)
    worker_count = fields.Int()
    max_workers = fields.Int()
    workers = fields.Dict(keys=fields.Str(), values=fields.Raw())
    start_time = fields.Float(allow_none=True)
    files_per_second = fields.Float()
    eta_seconds = fields.Int()


class HealthCheckSummaryResponseSchema(BaseSuccessSchema):
    """Schema for health summary response"""

    healthy = fields.Int()
    corrupted = fields.Int()
    warning = fields.Int()
    unchecked = fields.Int()
    checking = fields.Int()
    total = fields.Int()
    scanning = fields.Boolean()
    scan_progress = fields.Nested(HealthCheckProgressSchema)


class HealthCheckStatusResponseSchema(BaseSuccessSchema):
    """Schema for paginated health status response"""

    recordsTotal = fields.Int()
    recordsFiltered = fields.Int()
    results = fields.List(fields.Raw())


class RequestHealthCheckWorkersSchema(BaseSchema):
    """Schema for setting worker count"""

    worker_count = fields.Int(
        required=True,
        metadata={"description": "Number of concurrent scan workers (1-16)"},
        validate=validate.Range(min=1, max=16),
    )


class HealthCheckWorkersResponseSchema(BaseSuccessSchema):
    """Schema for worker count response"""

    worker_count = fields.Int()
    scanning = fields.Boolean()
    scan_progress = fields.Nested(HealthCheckProgressSchema)


class HealthCheckReadinessErrorSchema(BaseSchema):
    stage = fields.Str()
    message = fields.Str()


class HealthCheckReadinessResponseSchema(BaseSuccessSchema):
    """Schema for deployment readiness response"""

    ready = fields.Boolean()
    stages = fields.Dict(keys=fields.Str(), values=fields.Boolean())
    details = fields.Dict(keys=fields.Str(), values=fields.Raw())
    errors = fields.List(fields.Nested(HealthCheckReadinessErrorSchema))
