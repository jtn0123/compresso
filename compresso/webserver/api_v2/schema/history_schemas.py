#!/usr/bin/env python3

"""
compresso.history_schemas.py

Marshmallow schemas for history (completed tasks) API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema, RequestTableDataSchema, TableRecordsSuccessSchema


class RequestHistoryTableDataSchema(RequestTableDataSchema):
    """Schema for requesting completed tasks from the table"""

    order_by = fields.Str(
        metadata={"example": "finish_time"},
        load_default="finish_time",
    )


class CompletedTasksTableResultsSchema(BaseSchema):
    """Schema for completed tasks results returned by the table"""

    id = fields.Int(
        required=True,
        metadata={"description": "Item ID", "example": 1},
    )
    task_label = fields.Str(
        required=True,
        metadata={"description": "Item label", "example": "example.mp4"},
    )
    task_success = fields.Boolean(
        required=True,
        metadata={"description": "Item success status", "example": True},
    )
    finish_time = fields.Int(
        required=True,
        metadata={"description": "Item finish time", "example": 1627392616.6400812},
    )
    has_metadata = fields.Boolean(
        required=True,
        metadata={"description": "Item has linked file metadata", "example": False},
    )


class CompletedTasksSchema(TableRecordsSuccessSchema):
    """Schema for returning a list of completed task results"""

    successCount = fields.Int(
        required=True,
        metadata={"description": "Total count of times with a success status in the results list", "example": 337},
    )
    failedCount = fields.Int(
        required=True,
        metadata={"description": "Total count of times with a failed status in the results list", "example": 2},
    )
    results = fields.Nested(  # type: ignore[assignment]
        CompletedTasksTableResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )


class CompletedTasksLogRequestSchema(BaseSchema):
    """Schema for requesting a task log"""

    task_id = fields.Int(
        required=True,
        metadata={"description": "The ID of the task", "example": 1},
    )


class CompletedTasksLogSchema(BaseSchema):
    """Schema for returning a list of completed task results"""

    command_log = fields.Str(
        required=True,
        metadata={"description": "Long string...", "example": "Long string..."},
    )
    command_log_lines = fields.List(
        cls_or_instance=fields.Str,
        required=True,
        metadata={
            "description": "The long string broken up into an array of lines",
            "example": [
                "",
                "<b>RUNNER: </b>",
                "Video Encoder H264 - libx264 [Pass #1]",
                "",
                "<b>COMMAND:</b>",
                "",
                "...",
            ],
        },
    )


class RequestMetadataByTaskSchema(BaseSchema):
    """Schema for requesting metadata by task ID"""

    task_id = fields.Int(
        required=True,
        metadata={"description": "The ID of the completed task", "example": 1},
    )


class RequestMetadataSearchSchema(BaseSchema):
    """Schema for searching metadata by file path"""

    path = fields.Str(
        required=False,
        allow_none=True,
        metadata={"description": "Absolute path to search for metadata", "example": "/mnt/user/Movies/Example.mkv"},
    )
    offset = fields.Int(
        required=False,
        allow_none=True,
        metadata={"description": "Pagination offset", "example": 0},
    )
    limit = fields.Int(
        required=False,
        allow_none=True,
        metadata={"description": "Pagination limit", "example": 50},
    )


class MetadataEntrySchema(BaseSchema):
    """Schema for a metadata record"""

    fingerprint = fields.Str(
        required=True,
        metadata={"description": "File fingerprint", "example": "abc123"},
    )
    fingerprint_algo = fields.Str(
        required=True,
        metadata={"description": "Fingerprint algorithm identifier", "example": "sampled_sha256_v1"},
    )
    metadata_json = fields.Dict(
        required=True,
        metadata={
            "description": "Metadata blob keyed by plugin ID",
            "example": {
                "example_plugin": {"status": "ignored"},
            },
        },
    )
    last_task_id = fields.Int(
        required=False,
        allow_none=True,
        metadata={"description": "Most recent completed task ID that wrote metadata", "example": 42},
    )
    paths = fields.List(
        fields.Dict(),
        required=False,
        metadata={
            "description": "Associated file paths for this fingerprint",
            "example": [{"path": "/mnt/user/Movies/Example.mkv", "path_type": "destination"}],
        },
    )


class MetadataSearchResultsSchema(BaseSchema):
    """Schema for returning metadata search results"""

    results = fields.Nested(
        MetadataEntrySchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )
    total_count = fields.Int(
        required=True,
        metadata={"description": "Total number of matching records", "example": 120},
    )


class RequestMetadataUpdateSchema(BaseSchema):
    """Schema for updating metadata for a fingerprint"""

    fingerprint = fields.Str(
        required=True,
        metadata={"description": "File fingerprint", "example": "abc123"},
    )
    plugin_id = fields.Str(
        required=True,
        metadata={"description": "Plugin identifier", "example": "mover2"},
    )
    json_blob = fields.Dict(
        required=True,
        metadata={"description": "Plugin metadata dict to merge", "example": {"status": "ignored"}},
    )


class RequestMetadataByFingerprintSchema(BaseSchema):
    """Schema for requesting metadata by fingerprint"""

    fingerprint = fields.Str(
        required=True,
        metadata={"description": "File fingerprint", "example": "abc123"},
    )


class RequestMetadataDeleteSchema(BaseSchema):
    """Schema for deleting metadata"""

    fingerprint = fields.Str(
        required=True,
        metadata={"description": "File fingerprint", "example": "abc123"},
    )
    plugin_id = fields.Str(
        required=False,
        allow_none=True,
        metadata={"description": "Plugin identifier to delete (omit to delete all)", "example": "mover2"},
    )


class RequestCompletedTasksBulkActionSchema(BaseSchema):
    """Schema for bulk actions on completed tasks"""

    selection_mode = fields.Str(
        required=False,
        load_default="explicit",
        validate=validate.OneOf(["explicit", "all_filtered"]),
        metadata={"example": "explicit"},
    )
    id_list = fields.List(
        cls_or_instance=fields.Int,
        required=False,
        metadata={"description": "List of table IDs", "example": []},
        validate=validate.Length(min=1),
    )
    exclude_ids = fields.List(
        cls_or_instance=fields.Int,
        required=False,
        metadata={"description": "List of table IDs to exclude when using a filtered selection", "example": []},
        load_default=[],
        validate=validate.Length(min=0),
    )
    search_value = fields.Str(
        required=False,
        metadata={"description": "String to filter search results by", "example": "items with this text in the value"},
        load_default="",
    )
    status = fields.Str(
        required=False,
        metadata={"description": "Filter on the status", "example": "all"},
        load_default="all",
    )
    after = fields.DateTime(
        required=False,
        metadata={"description": "Filter entries since datetime", "example": "2022-04-07 01:45"},
        allow_none=True,
    )
    before = fields.DateTime(
        required=False,
        metadata={"description": "Filter entries prior to datetime", "example": "2022-04-07 01:55"},
        allow_none=True,
    )


class RequestAddCompletedToPendingTasksSchema(RequestCompletedTasksBulkActionSchema):
    """Schema for adding a completed task to the pending task queue"""

    library_id = fields.Int(
        required=False,
        load_default=0,
        metadata={"example": 1},
    )
