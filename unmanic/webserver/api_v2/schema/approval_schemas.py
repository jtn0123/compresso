#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.approval_schemas.py

    Marshmallow schemas for approval workflow API endpoints.
"""

from marshmallow import fields, validate
from unmanic.webserver.api_v2.schema.schemas import BaseSchema, BaseSuccessSchema


class RequestApprovalTasksSchema(BaseSchema):
    """Schema for listing tasks awaiting approval"""
    start = fields.Int(
        load_default=0,
        description="Pagination offset",
    )
    length = fields.Int(
        load_default=10,
        description="Number of records to return",
    )
    search_value = fields.Str(
        load_default="",
        description="Filter by file path substring",
    )
    library_ids = fields.List(
        fields.Int(),
        load_default=[],
        description="Filter by library IDs",
    )
    include_library = fields.Boolean(
        load_default=False,
        description="Include library name in results",
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
    library_id = fields.Int(load_default=None, allow_none=True)
    library_name = fields.Str(load_default=None, allow_none=True)


class ApprovalTasksResponseSchema(BaseSuccessSchema):
    """Schema for the approval tasks list response"""
    recordsTotal = fields.Int()
    recordsFiltered = fields.Int()
    results = fields.List(fields.Nested(ApprovalTaskItemSchema))


class RequestApprovalActionSchema(BaseSchema):
    """Schema for approve/reject actions"""
    id_list = fields.List(
        fields.Int(),
        required=True,
        description="List of task IDs to approve or reject",
        validate=validate.Length(min=1),
    )


class RequestRejectActionSchema(BaseSchema):
    """Schema for reject action with optional requeue"""
    id_list = fields.List(
        fields.Int(),
        required=True,
        description="List of task IDs to reject",
        validate=validate.Length(min=1),
    )
    requeue = fields.Boolean(
        load_default=False,
        description="If true, requeue the tasks as pending instead of deleting them",
    )


class RequestApprovalDetailSchema(BaseSchema):
    """Schema for getting detail of a single approval task"""
    id = fields.Int(
        required=True,
        description="Task ID to get details for",
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


class ApprovalCountResponseSchema(BaseSuccessSchema):
    """Schema for the approval count response"""
    count = fields.Int()
