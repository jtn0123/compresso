#!/usr/bin/env python3

"""
compresso.settings_schemas.py

Marshmallow schemas for settings API endpoints.
"""

from marshmallow import INCLUDE, fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema

_EXAMPLE_LIBRARY_PATH = "/library"
_EXAMPLE_PLUGIN_NAME_AC3 = "Audio Encoder AC3"
_EXAMPLE_PLUGIN_DESC_AC3 = "Ensure all audio streams are encoded with the AC3 codec using the native FFmpeg ac3 encoder."
_EXAMPLE_PLUGIN_ICON_AC3 = "https://raw.githubusercontent.com/Josh5/compresso.plugin.encoder_audio_ac3/master/icon.png"


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
                "library_path": _EXAMPLE_LIBRARY_PATH,
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
    api_token = fields.Str(
        required=False,
        metadata={"description": "An optional API token unique to this remote installation", "example": ""},
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
                "api_token": "",
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
        metadata={"description": "The library path", "example": _EXAMPLE_LIBRARY_PATH},
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


class SettingsLibraryConfigSchema(BaseSchema):
    """Typed library settings accepted and returned by the settings API.

    Partial updates are supported: save_library_config falls back to the
    library's current values for any omitted field, so nothing is required
    and unknown keys are passed through rather than rejected.
    """

    class Meta:
        unknown = INCLUDE

    id = fields.Int(required=False, allow_none=True, metadata={"example": 1})
    locked = fields.Boolean(required=False, metadata={"example": False})
    name = fields.Str(required=False, metadata={"example": "Default"})
    path = fields.Str(required=False, metadata={"example": _EXAMPLE_LIBRARY_PATH})
    enable_remote_only = fields.Boolean(required=False, metadata={"example": False})
    enable_scanner = fields.Boolean(required=False, metadata={"example": False})
    enable_inotify = fields.Boolean(required=False, metadata={"example": False})
    priority_score = fields.Int(required=False, metadata={"example": 0})
    tags = fields.List(fields.Str(), required=False, metadata={"example": ["GPU", "priority"]})
    target_codecs = fields.List(fields.Str(), required=False, metadata={"example": ["h264"]})
    skip_codecs = fields.List(fields.Str(), required=False, metadata={"example": ["hevc", "av1"]})
    size_guardrail_enabled = fields.Boolean(required=False, metadata={"example": False})
    size_guardrail_min_pct = fields.Int(required=False, metadata={"example": 20})
    size_guardrail_max_pct = fields.Int(required=False, metadata={"example": 80})
    replacement_policy = fields.Str(required=False, metadata={"example": "approval_required"})


class SettingsLibraryEnabledPluginSchema(BaseSchema):
    """Plugin fields exchanged by the per-library configuration UI.

    Import/export payloads may also carry library_id and a settings blob;
    both are accepted (settings is applied by the import endpoint only).
    """

    class Meta:
        unknown = INCLUDE

    plugin_id = fields.Str(required=True, metadata={"example": "notify_plex"})
    name = fields.Str(required=False, metadata={"example": "Notify Plex"})
    library_id = fields.Int(required=False, allow_none=True, metadata={"example": 1})
    settings = fields.Dict(required=False, metadata={"example": {"notify_on_failure": True}})
    description = fields.Str(required=False, allow_none=True, metadata={"example": "Notify Plex on completion."})
    icon = fields.Str(required=False, allow_none=True, metadata={"example": "https://example.invalid/icon.png"})
    has_config = fields.Boolean(required=False, metadata={"example": True})
    author = fields.Str(required=False, metadata={"example": "Compresso"})
    version = fields.Str(required=False, metadata={"example": "1.0.0"})
    tags = fields.Str(required=False, metadata={"example": "notification,plex"})


class SettingsLibraryPluginsSchema(BaseSchema):
    enabled_plugins = fields.List(fields.Nested(SettingsLibraryEnabledPluginSchema), required=True)


class SettingsLibraryConfigReadAndWriteSchema(BaseSchema):
    """Schema to display the data from the remote installation"""

    library_config = fields.Nested(
        SettingsLibraryConfigSchema,
        required=True,
        metadata={
            "description": "The library configuration",
            "example": {
                "id": 1,
                "name": "Default",
                "path": _EXAMPLE_LIBRARY_PATH,
                "enable_scanner": False,
                "enable_inotify": False,
                "priority_score": 0,
                "tags": [],
            },
        },
    )

    plugins = fields.Nested(
        SettingsLibraryPluginsSchema,
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
                        "name": _EXAMPLE_PLUGIN_NAME_AC3,
                        "description": _EXAMPLE_PLUGIN_DESC_AC3,
                        "icon": _EXAMPLE_PLUGIN_ICON_AC3,
                    }
                ],
                "plugin_flow": {
                    "library_management.file_test": [
                        {
                            "plugin_id": "encoder_audio_ac3",
                            "name": _EXAMPLE_PLUGIN_NAME_AC3,
                            "author": "Josh.5",
                            "description": _EXAMPLE_PLUGIN_DESC_AC3,
                            "version": "0.0.2",
                            "icon": _EXAMPLE_PLUGIN_ICON_AC3,
                        }
                    ],
                    "worker.process": [
                        {
                            "plugin_id": "encoder_audio_ac3",
                            "name": _EXAMPLE_PLUGIN_NAME_AC3,
                            "author": "Josh.5",
                            "description": _EXAMPLE_PLUGIN_DESC_AC3,
                            "version": "0.0.2",
                            "icon": _EXAMPLE_PLUGIN_ICON_AC3,
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
                "path": _EXAMPLE_LIBRARY_PATH,
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
