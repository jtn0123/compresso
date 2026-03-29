#!/usr/bin/env python3

"""
compresso.worker_schemas.py

Marshmallow schemas for worker API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class RequestWorkerByIdSchema(BaseSchema):
    """Schema to request a worker by the worker's ID"""

    worker_id = fields.Str(
        required=True,
        metadata={"example": "1"},
    )


class WorkerStatusResultsSchema(BaseSchema):
    """Schema for worker status results"""

    id = fields.Str(
        required=True,
        metadata={"description": "", "example": "W0"},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "", "example": "Worker-W0"},
    )
    idle = fields.Boolean(
        required=True,
        metadata={"description": "Flag - is worker idle", "example": True},
    )
    paused = fields.Boolean(
        required=True,
        metadata={"description": "Flag - is worker paused", "example": False},
    )
    start_time = fields.Str(
        required=True,
        metadata={"description": "The time when this worker started processing a task", "example": "1635746377.0021548"},
        allow_none=True,
    )
    current_file = fields.Str(
        required=True,
        metadata={"description": "The basename of the file currently being processed", "example": "file.mp4"},
    )
    current_task = fields.Int(
        required=True,
        metadata={"description": "The Task ID", "example": 1},
        allow_none=True,
    )
    current_command = fields.Str(
        required=True,
        metadata={"description": "The command currently being executed", "example": "ffmpeg ...."},
        allow_none=True,
    )
    worker_log_tail = fields.List(
        cls_or_instance=fields.Str,
        required=True,
        metadata={
            "description": "The log lines produced by the worker",
            "example": [
                "\n\nRUNNER: \nRemux Video Files [Pass #1]\n\n",
                "\nExecuting plugin runner... Please wait",
                "\nRunner did not request to execute a command",
                "\n\nNo Plugin requested to run commands for this file"
                " '/tmp/compresso/compresso_remote_pending_library-1635746225.3336523/file.mp4'",
            ],
        },
        validate=validate.Length(min=0),
    )
    runners_info = fields.Dict(
        required=True,
        metadata={
            "description": "The status of the plugin runner currently processing the file",
            "example": {
                "video_remuxer": {
                    "plugin_id": "video_remuxer",
                    "status": "complete",
                    "name": "Remux Video Files",
                    "author": "Josh.5",
                    "version": "0.0.5",
                    "icon": "https://raw.githubusercontent.com/Josh5/compresso.plugin.video_remuxer/master/icon.png",
                    "description": "Remux a video file to the configured container",
                    "success": True,
                }
            },
        },
    )
    subprocess = fields.Dict(
        required=True,
        metadata={
            "description": "The status of the process currently being executed",
            "example": {"pid": 140408939493120, "percent": "None", "elapsed": "None"},
        },
    )


class WorkerStatusSuccessSchema(BaseSchema):
    """Schema for returning the status of all workers"""

    workers_status = fields.Nested(
        WorkerStatusResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )
