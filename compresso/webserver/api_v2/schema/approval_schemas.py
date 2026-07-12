#!/usr/bin/env python3

"""
compresso.approval_schemas.py

Marshmallow schemas for approval workflow API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema, BaseSuccessSchema

APPROVAL_TASK_ORDER_COLUMNS = (
    "id",
    "abspath",
    "priority",
    "type",
    "status",
    "library_id",
    "start_time",
    "finish_time",
    "source_size",
    "vmaf_score",
    "ssim_score",
)


class RequestApprovalTasksSchema(BaseSchema):
    """Schema for listing tasks awaiting approval"""

    start = fields.Int(
        load_default=0,
        metadata={"description": "Pagination offset"},
        validate=validate.Range(min=0),
    )
    length = fields.Int(
        load_default=10,
        metadata={"description": "Number of records to return"},
        validate=validate.Range(min=1, max=1000),
    )
    search_value = fields.Str(
        load_default="",
        metadata={"description": "Filter by file path substring"},
    )
    library_ids = fields.List(
        fields.Int(),
        load_default=[],
        metadata={"description": "Filter by library IDs"},
    )
    include_library = fields.Boolean(
        load_default=False,
        metadata={"description": "Include library name in results"},
    )
    order_by = fields.Str(
        load_default="finish_time",
        metadata={"description": "Column to order results by", "example": "finish_time"},
        validate=validate.OneOf(APPROVAL_TASK_ORDER_COLUMNS),
    )
    order_direction = fields.Str(
        load_default="desc",
        metadata={"description": "Order direction ('asc' or 'desc')", "example": "desc"},
        validate=validate.OneOf(["asc", "desc"]),
    )
    codec = fields.Str(
        load_default="",
        allow_none=True,
        metadata={"description": "Filter by source or staged codec", "example": "hevc"},
    )
    quality_min = fields.Float(
        load_default=0,
        metadata={"description": "Minimum VMAF score to include", "example": 85},
        validate=validate.Range(min=0, max=100),
    )


class ApprovalTaskItemSchema(BaseSchema):
    """Schema for a single approval task in the list"""

    id = fields.Int()
    abspath = fields.Str()
    priority = fields.Int()
    type = fields.Str()
    status = fields.Str()
    source_size = fields.Int()
    staged_size = fields.Int()
    staged_path = fields.Str()
    size_delta = fields.Int()
    finish_time = fields.Str()
    source_codec = fields.Str(load_default="")
    source_resolution = fields.Str(load_default="")
    staged_codec = fields.Str(load_default="")
    staged_resolution = fields.Str(load_default="")
    vmaf_score = fields.Float(load_default=None, allow_none=True)
    ssim_score = fields.Float(load_default=None, allow_none=True)
    library_id = fields.Int(load_default=None, allow_none=True)
    library_name = fields.Str(load_default=None, allow_none=True)


class ApprovalTasksResponseSchema(BaseSuccessSchema):
    """Schema for the approval tasks list response"""

    recordsTotal = fields.Int()
    recordsFiltered = fields.Int()
    results = fields.List(fields.Nested(ApprovalTaskItemSchema))


class ApprovalBulkFilterMixin:
    """Shared filters for approval bulk actions."""

    search_value = fields.Str(
        load_default="",
        metadata={"description": "Search filter when all_matching is true"},
    )
    library_ids = fields.List(
        fields.Int(),
        load_default=[],
        metadata={"description": "Library filter when all_matching is true"},
    )
    codec = fields.Str(
        load_default="",
        allow_none=True,
        metadata={"description": "Codec filter when all_matching is true"},
    )
    quality_min = fields.Float(
        load_default=0,
        metadata={"description": "Minimum VMAF filter when all_matching is true"},
        validate=validate.Range(min=0, max=100),
    )


class RequestApprovalActionSchema(ApprovalBulkFilterMixin, BaseSchema):
    """Schema for approve/reject actions"""

    id_list = fields.List(
        fields.Int(),
        load_default=[],
        metadata={"description": "List of task IDs to approve or reject"},
    )
    all_matching = fields.Boolean(
        load_default=False,
        metadata={"description": "If true, approve all tasks matching the current filter instead of explicit IDs"},
    )


class RequestRejectActionSchema(ApprovalBulkFilterMixin, BaseSchema):
    """Schema for reject action with optional requeue"""

    id_list = fields.List(
        fields.Int(),
        load_default=[],
        metadata={"description": "List of task IDs to reject"},
    )
    requeue = fields.Boolean(
        load_default=False,
        metadata={"description": "If true, requeue the tasks as pending instead of deleting them"},
    )
    all_matching = fields.Boolean(
        load_default=False,
        metadata={"description": "If true, reject all tasks matching the current filter instead of explicit IDs"},
    )


class RequestApprovalDetailSchema(BaseSchema):
    """Schema for getting detail of a single approval task"""

    id = fields.Int(
        required=True,
        metadata={"description": "Task ID to get details for"},
    )


class ApprovalDetailResponseSchema(BaseSuccessSchema):
    """Schema for the detail response"""

    id = fields.Int()
    abspath = fields.Str()
    source_size = fields.Int()
    staged_size = fields.Int()
    staged_path = fields.Str()
    size_delta = fields.Int()
    size_ratio = fields.Float()
    cache_path = fields.Str()
    success = fields.Boolean()
    start_time = fields.Str()
    finish_time = fields.Str()
    log = fields.Str()
    library_id = fields.Int()
    source_codec = fields.Str(load_default="")
    source_resolution = fields.Str(load_default="")
    source_container = fields.Str(load_default="")
    staged_codec = fields.Str(load_default="")
    staged_resolution = fields.Str(load_default="")
    staged_container = fields.Str(load_default="")
    vmaf_score = fields.Float(load_default=None, allow_none=True)
    ssim_score = fields.Float(load_default=None, allow_none=True)


class ApprovalCountResponseSchema(BaseSuccessSchema):
    """Schema for the approval count response"""

    count = fields.Int()


class ApprovalSummaryResponseSchema(BaseSuccessSchema):
    """Schema for aggregate approval queue summary data"""

    total_count = fields.Int()
    total_source_size = fields.Int()
    total_staged_size = fields.Int()
    total_space_saved = fields.Int()
    average_savings_percent = fields.Float()
    largest_savings_file = fields.Str()
    largest_savings_bytes = fields.Int()
    average_vmaf = fields.Float(allow_none=True)
    codec_options = fields.List(fields.Str())
