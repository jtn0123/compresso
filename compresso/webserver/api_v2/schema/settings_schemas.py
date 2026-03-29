#!/usr/bin/env python3

"""
compresso.settings_schemas.py

Marshmallow schemas for settings API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema


class SettingsReadAndWriteSchema(BaseSchema):
    """Schema to request the current settings"""

    settings = fields.Dict(
        required=True,
        metadata={
            "description": "The current settings, including fork-specific deployment"
            " defaults such as safe startup behavior and worker caps",
            "example": {
                "ui_port": 8888,
                "debugging": False,
                "log_buffer_retention": 0,
                "library_path": "/library",
                "enable_library_scanner": False,
                "schedule_full_scan_minutes": 1440,
                "follow_symlinks": True,
                "run_full_scan_on_start": False,
                "cache_path": "/tmp/compresso",  # noqa: S108 — Linux default cache path
                "large_library_safe_defaults": True,
                "startup_readiness_timeout_seconds": 30,
                "default_worker_cap": 2,
            },
        },
    )


class SettingsSystemConfigSchema(BaseSchema):
    """Schema to display the current system configuration"""

    configuration = fields.Dict(
        required=True,
        metadata={"description": "The current system configuration", "example": {}},
    )


class WorkerEventScheduleResultsSchema(BaseSchema):
    """Schema for worker status results"""

    repetition = fields.Str(
        required=True,
        metadata={"description": "", "example": "daily"},
    )
    schedule_task = fields.Str(
        required=True,
        metadata={"description": "The type of task. ['count', 'pause', 'resume']", "example": "count"},
    )
    schedule_time = fields.Str(
        required=True,
        metadata={"description": "The time when the task should be executed", "example": "09:30"},
    )
    schedule_worker_count = fields.Int(
        required=False,
        metadata={"description": "The worker count to set (only valid if schedule_task is count)", "example": 4},
    )


class SettingsWorkerGroupConfigSchema(BaseSchema):
    """Schema to display the config of a single worker group"""

    id = fields.Int(
        required=True,
        metadata={"description": "", "example": 1},
        allow_none=True,
    )
    locked = fields.Boolean(
        required=True,
        metadata={"description": "If the worker group is locked and cannot be deleted", "example": False},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "The name of the worker group", "example": "Default Group"},
    )
    number_of_workers = fields.Int(
        required=True,
        metadata={"description": "The number of workers in this group", "example": 3},
    )
    worker_event_schedules = fields.Nested(
        WorkerEventScheduleResultsSchema,
        required=True,
        metadata={"description": "Any scheduled events for this worker group"},
        many=True,
        validate=validate.Length(min=0),
    )
    worker_type = fields.Str(
        required=False,
        load_default="cpu",
        metadata={"description": "The worker type for this group (cpu or gpu)", "example": "cpu"},
        validate=validate.OneOf(["cpu", "gpu"]),
    )
    tags = fields.List(
        cls_or_instance=fields.Str,
        required=True,
        metadata={"description": "A list of tags associated with this worker", "example": ["GPU", "priority"]},
    )


class WorkerGroupsListSchema(BaseSchema):
    """Schema to list all worker groups"""

    worker_groups = fields.Nested(
        SettingsWorkerGroupConfigSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )


class RequestSettingsRemoteInstallationAddressValidationSchema(BaseSchema):
    """Schema to request validation of remote installation address"""

    address = fields.Str(
        required=True,
        metadata={"description": "The address of the remote installation", "example": "192.168.1.2:8888"},
    )
    auth = fields.Str(
        required=False,
        metadata={"description": "Authentication type", "example": "Basic"},
        allow_none=True,
    )
    username = fields.Str(
        required=False,
        metadata={"description": "An optional username", "example": "foo"},
        allow_none=True,
    )
    password = fields.Str(
        required=False,
        metadata={"description": "An optional password", "example": "bar"},
        allow_none=True,
    )


class SettingsRemoteInstallationDataSchema(BaseSchema):
    """Schema to display the data from the remote installation"""

    installation = fields.Dict(
        required=True,
        metadata={"description": "The data from the remote installation", "example": {}},
    )


class RequestRemoteInstallationLinkConfigSchema(BaseSchema):
    """Schema to request a single remote installation link configuration given its UUID"""

    uuid = fields.Str(
        required=True,
        metadata={"description": "The uuid of the remote installation", "example": "7cd35429-76ab-4a29-8649-8c91236b5f8b"},
    )


class SettingsRemoteInstallationLinkConfigSchema(BaseSchema):
    """Schema to display the data from the remote installation"""

    link_config = fields.Dict(
        required=True,
        metadata={
            "description": "The configuration for the remote installation link",
            "example": {
                "address": "10.0.0.2:8888",
                "auth": "None",
                "username": "",
                "password": "",
                "available": True,
                "name": "API schema generated",
                "version": "0.1.3",
                "last_updated": 1636166593.013826,
                "enable_receiving_tasks": False,
                "enable_sending_tasks": False,
                "enable_task_preloading": True,
                "enable_distributed_worker_count": False,
                "preloading_count": 2,
                "enable_checksum_validation": False,
                "enable_config_missing_libraries": False,
            },
        },
    )
    distributed_worker_count_target = fields.Int(
        required=False,
        metadata={
            "description": "The target count of workers to be distributed across any configured linked installations",
            "example": 4,
        },
    )


class LibraryResultsSchema(BaseSchema):
    """Schema for library results"""

    id = fields.Int(
        required=True,
        metadata={"description": "", "example": 1},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "The name of the library", "example": "Default"},
    )
    path = fields.Str(
        required=True,
        metadata={"description": "The library path", "example": "/library"},
    )
    locked = fields.Boolean(
        required=True,
        metadata={"description": "If the library is locked and cannot be deleted", "example": False},
    )
    enable_remote_only = fields.Boolean(
        required=True,
        metadata={"description": "If the library is configured for remote files only", "example": False},
    )
    enable_scanner = fields.Boolean(
        required=True,
        metadata={"description": "If the library is configured to execute library scans", "example": False},
    )
    enable_inotify = fields.Boolean(
        required=True,
        metadata={"description": "If the library is configured to monitor for file changes", "example": False},
    )
    target_codecs = fields.Str(
        required=False,
        load_default="",
        metadata={"description": "Comma-separated list of target codecs", "example": ""},
    )
    skip_codecs = fields.Str(
        required=False,
        load_default="",
        metadata={"description": "Comma-separated list of codecs to skip", "example": ""},
    )
    size_guardrail_enabled = fields.Boolean(
        required=False,
        load_default=False,
        metadata={"description": "If size guardrails are enabled for this library", "example": False},
    )
    size_guardrail_min_pct = fields.Int(
        required=False,
        load_default=20,
        metadata={"description": "Minimum size percentage guardrail", "example": 20},
    )
    size_guardrail_max_pct = fields.Int(
        required=False,
        load_default=80,
        metadata={"description": "Maximum size percentage guardrail", "example": 80},
    )
    replacement_policy = fields.Str(
        required=False,
        load_default="",
        metadata={"description": "Per-library replacement policy", "example": ""},
    )
    tags = fields.List(
        cls_or_instance=fields.Str,
        required=True,
        metadata={"description": "A list of tags associated with this library", "example": ["GPU", "priority"]},
    )


class SettingsLibrariesListSchema(BaseSchema):
    """Schema to list all libraries"""

    libraries = fields.Nested(
        LibraryResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=1),
    )


class RequestLibraryByIdSchema(BaseSchema):
    """Schema to request a single library given its ID"""

    id = fields.Int(
        required=True,
        metadata={"description": "The ID of the library", "example": 1},
    )


class SettingsLibraryConfigReadAndWriteSchema(BaseSchema):
    """Schema to display the data from the remote installation"""

    library_config = fields.Dict(
        required=True,
        metadata={
            "description": "The library configuration",
            "example": {
                "id": 1,
                "name": "Default",
                "path": "/library",
                "enable_scanner": False,
                "enable_inotify": False,
                "priority_score": 0,
                "tags": [],
            },
        },
    )

    plugins = fields.Dict(
        required=False,
        metadata={
            "description": "The library's enabled plugins",
            "example": {
                "enabled_plugins": [
                    {
                        "library_id": 1,
                        "plugin_id": "notify_plex",
                        "name": "Notify Plex",
                        "description": "Notify Plex on completion of a task.",
                        "icon": "https://raw.githubusercontent.com/Josh5/compresso.plugin.notify_plex/master/icon.png",
                    }
                ]
            },
        },
    )


class SettingsLibraryPluginConfigExportSchema(BaseSchema):
    """Schema for exporting a library's plugin config"""

    plugins = fields.Dict(
        required=True,
        metadata={
            "description": "The library's enabled plugins",
            "example": {
                "enabled_plugins": [
                    {
                        "library_id": 1,
                        "plugin_id": "encoder_audio_ac3",
                        "name": "Audio Encoder AC3",
                        "description": "Ensure all audio streams are encoded with the AC3 codec"
                        " using the native FFmpeg ac3 encoder.",
                        "icon": "https://raw.githubusercontent.com/Josh5/compresso.plugin.encoder_audio_ac3/master/icon.png",
                    }
                ],
                "plugin_flow": {
                    "library_management.file_test": [
                        {
                            "plugin_id": "encoder_audio_ac3",
                            "name": "Audio Encoder AC3",
                            "author": "Josh.5",
                            "description": "Ensure all audio streams are encoded with the AC3 codec"
                            " using the native FFmpeg ac3 encoder.",
                            "version": "0.0.2",
                            "icon": "https://raw.githubusercontent.com/Josh5/compresso.plugin.encoder_audio_ac3/master/icon.png",
                        }
                    ],
                    "worker.process": [
                        {
                            "plugin_id": "encoder_audio_ac3",
                            "name": "Audio Encoder AC3",
                            "author": "Josh.5",
                            "description": "Ensure all audio streams are encoded with the AC3 codec"
                            " using the native FFmpeg ac3 encoder.",
                            "version": "0.0.2",
                            "icon": "https://raw.githubusercontent.com/Josh5/compresso.plugin.encoder_audio_ac3/master/icon.png",
                        }
                    ],
                    "postprocessor.file_move": [],
                    "postprocessor.task_result": [],
                },
            },
        },
    )

    library_config = fields.Dict(
        required=False,
        metadata={
            "description": "The library configuration",
            "example": {
                "id": 1,
                "name": "Default",
                "path": "/library",
                "enable_scanner": False,
                "enable_inotify": False,
                "priority_score": 0,
                "tags": [],
            },
        },
    )


class SettingsLibraryPluginConfigImportSchema(SettingsLibraryPluginConfigExportSchema):
    """Schema for import a library's plugin config"""

    library_id = fields.Int(
        required=True,
        metadata={"example": 1},
    )
