#!/usr/bin/env python3

"""
compresso.pending_schemas.py

Marshmallow schemas for pending tasks API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import (
    BaseSchema,
    RequestTableDataSchema,
    RequestTableUpdateByIdList,
    TableRecordsSuccessSchema,
)

_EXAMPLE_FILE_PATH = "/library/TEST_FILE.mkv"


class RequestPendingTableDataSchema(RequestTableDataSchema):
    """Schema for requesting pending tasks from the table"""

    order_by = fields.Str(
        metadata={"example": "priority"},
        load_default="priority",
    )
    library_ids = fields.List(
        cls_or_instance=fields.Int,
        required=False,
        metadata={"description": "Filter pending tasks by library IDs", "example": [1, 3]},
        load_default=[],
        validate=validate.Length(min=0),
    )


class RequestPendingTasksBulkActionSchema(BaseSchema):
    """Schema for bulk actions on pending tasks"""

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
    library_ids = fields.List(
        cls_or_instance=fields.Int,
        required=False,
        metadata={"description": "Filter pending tasks by library IDs", "example": [1, 3]},
        load_default=[],
        validate=validate.Length(min=0),
    )


class PendingTasksTableResultsSchema(BaseSchema):
    """Schema for pending task results returned by the table"""

    id = fields.Int(
        required=True,
        metadata={"description": "Item ID", "example": 1},
    )
    abspath = fields.Str(
        required=True,
        metadata={"description": "File absolute path", "example": "example.mp4"},
    )
    priority = fields.Int(
        required=True,
        metadata={"description": "The current priority (higher is greater)", "example": 100},
    )
    type = fields.Str(
        required=True,
        metadata={"description": "The type of the pending task - local or remote", "example": "local"},
    )
    status = fields.Str(
        required=True,
        metadata={"description": "The current status of the pending task", "example": "pending"},
    )
    checksum = fields.Str(
        required=False,
        metadata={"description": "The uploaded file md5 checksum", "example": "5425ab3df5cdbad2e1099bb4cb963a4f"},
    )
    library_id = fields.Int(
        required=False,
        metadata={"description": "The ID of the library for which this task was created", "example": 1},
    )
    library_name = fields.Str(
        required=False,
        metadata={"description": "The name of the library for which this task was created", "example": "Default"},
    )


class PendingTasksSchema(TableRecordsSuccessSchema):
    """Schema for returning a list of pending task results"""

    results = fields.Nested(  # type: ignore[assignment]
        PendingTasksTableResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )


class RequestPendingTasksReorderSchema(RequestPendingTasksBulkActionSchema):
    """Schema for moving pending items to top or bottom of table by ID"""

    position = fields.Str(
        required=True,
        metadata={"description": "Position to move given list of items to ('top' or 'bottom')", "example": "top"},
        validate=validate.OneOf(["top", "bottom"]),
    )


class RequestPendingTaskCreateSchema(BaseSchema):
    """Schema for requesting the creation of a pending task"""

    path = fields.Str(
        required=True,
        metadata={"description": "The absolute path to a file", "example": _EXAMPLE_FILE_PATH},
    )
    library_id = fields.Int(
        required=False,
        metadata={"description": "The ID of the library to append this task to", "example": 1},
    )
    library_name = fields.Str(
        required=False,
        metadata={"description": "The name of the library to append this task to", "example": "Default"},
    )
    type = fields.Str(
        required=False,
        metadata={"description": "The type of pending task to create (local/remote)", "example": "local"},
    )
    priority_score = fields.Int(
        required=False,
        metadata={
            "description": "Apply a priority score to the created task to either"
            " increase or decrease its position in the queue",
            "example": 1000,
        },
    )


class RequestPendingTaskTestSchema(BaseSchema):
    """Schema for requesting a file test without creating a pending task"""

    path = fields.Str(
        required=True,
        metadata={
            "description": "The path to a file (absolute or relative to the selected library)",
            "example": _EXAMPLE_FILE_PATH,
        },
    )
    library_id = fields.Int(
        required=False,
        metadata={"description": "The ID of the library to use for plugin configuration", "example": 1},
    )
    library_name = fields.Str(
        required=False,
        metadata={"description": "The name of the library to use for plugin configuration", "example": "Default"},
    )


class PendingTaskTestResultSchema(BaseSchema):
    """Schema for file test results without queueing a task"""

    path = fields.Str(
        required=True,
        metadata={"description": "The absolute path to the tested file", "example": _EXAMPLE_FILE_PATH},
    )
    library_id = fields.Int(
        required=True,
        metadata={"description": "The library ID used to run the file tests", "example": 1},
    )
    library_name = fields.Str(
        required=True,
        metadata={"description": "The library name used to run the file tests", "example": "Default"},
    )
    add_file_to_pending_tasks = fields.Boolean(
        required=False,
        allow_none=True,
        metadata={
            "description": "Final decision after file tests (true: plugin requested queueing,"
            " false: plugin rejected, null: no plugin decided)",
            "example": True,
        },
    )
    issues = fields.List(
        fields.Dict(),
        required=False,
        metadata={"description": "Any issues that prevented the file from being queued", "example": []},
    )
    decision_plugin = fields.Dict(
        required=False,
        allow_none=True,
        metadata={
            "description": "The plugin that set add_file_to_pending_tasks (null if no plugin decided)",
            "example": {
                "plugin_id": "example_library_management_file_test",
                "plugin_name": "Example Library Test",
            },
        },
    )


class TaskDownloadLinkSchema(BaseSchema):
    """Schema for returning a download link ID"""

    link_id = fields.Str(
        required=True,
        metadata={
            "description": "The ID used to download the file /compresso/downloads/{link_id}",
            "example": "2960645c-a4e2-4b05-8866-7bd469ee9ef8",
        },
    )


class RequestPendingTasksLibraryUpdateSchema(RequestTableUpdateByIdList):
    """Schema for updating the library for a list of created tasks"""

    library_name = fields.Str(
        required=True,
        metadata={"example": "Default"},
    )
