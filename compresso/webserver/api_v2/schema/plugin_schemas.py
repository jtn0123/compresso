#!/usr/bin/env python3

"""
compresso.plugin_schemas.py

Marshmallow schemas for plugin API endpoints.
"""

from marshmallow import fields, validate

from compresso.webserver.api_v2.schema.schemas import BaseSchema, RequestTableDataSchema, TableRecordsSuccessSchema


class RequestPluginsTableDataSchema(RequestTableDataSchema):
    """Schema for requesting plugins from the table"""

    order_by = fields.Str(
        metadata={"example": "name"},
        load_default="name",
    )


class PluginStatusSchema(BaseSchema):
    installed = fields.Boolean(
        required=False,
        metadata={"description": "Is the plugin installed", "example": True},
    )
    update_available = fields.Boolean(
        required=False,
        metadata={"description": "Does the plugin have an update available", "example": True},
    )


class RequestPluginsByIdSchema(BaseSchema):
    """Schema to request data pertaining to a plugin by it's Plugin ID"""

    plugin_id = fields.Str(
        required=True,
        metadata={"example": "encoder_video_hevc_vaapi"},
    )
    repo_id = fields.Str(
        required=False,
        metadata={
            "description": "The ID of the repository that this plugin is in",
            "example": "158899500680826593283708490873332175078",
        },
    )


class PluginsMetadataResultsSchema(BaseSchema):
    """Schema for plugin metadata that will be returned by various requests"""

    plugin_id = fields.Str(
        required=True,
        metadata={"description": "The plugin ID", "example": "encoder_video_h264_nvenc"},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "The plugin name", "example": "Video Encoder H264 - h264_nvenc"},
    )
    author = fields.Str(
        required=True,
        metadata={"description": "The plugin author", "example": "encoder_video_h264_nvenc"},
    )
    description = fields.Str(
        required=True,
        metadata={
            "description": "The plugin description",
            "example": "Ensure all video streams are encoded with the H264 codec using the h264_nvenc encoder.",
        },
    )
    version = fields.Str(
        required=True,
        metadata={"description": "The plugin version", "example": "Josh.5"},
    )
    icon = fields.Str(
        required=True,
        metadata={
            "description": "The plugin icon",
            "example": "https://raw.githubusercontent.com/Josh5/compresso-plugins/master/source/encoder_video_h264_nvenc/icon.png",
        },
    )
    tags = fields.Str(
        required=True,
        metadata={"description": "The plugin tags", "example": "video,encoder,ffmpeg,worker,nvenc,nvdec,nvidia"},
    )
    status = fields.Nested(
        PluginStatusSchema,
        required=True,
        metadata={"description": "The plugin status"},
    )
    changelog = fields.Str(
        required=False,
        metadata={"description": "The plugin changelog", "example": "[b][color=56adda]0.0.1[/color][/b]• initial version"},
    )
    has_config = fields.Boolean(
        required=False,
        metadata={"description": "The plugin has the ability to be configured", "example": True},
    )


class PluginsTableResultsSchema(PluginsMetadataResultsSchema):
    """Schema for pending task results returned by the table"""

    id = fields.Int(
        required=True,
        metadata={"description": "Item table ID", "example": 1},
    )


class PluginsDataSchema(TableRecordsSuccessSchema):
    """Schema for returning a list of plugin table results"""

    results = fields.Nested(  # type: ignore[assignment]
        PluginsTableResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )


class RequestPluginsInfoSchema(RequestPluginsByIdSchema):
    """Schema for requesting plugins info by a given Plugin ID"""

    prefer_local = fields.Boolean(
        required=False,
        load_default=True,
        metadata={"example": True},
    )
    library_id = fields.Int(
        required=False,
        load_default=0,
        metadata={"example": 1},
    )


class PluginsConfigInputItemSchema(BaseSchema):
    """Schema for plugin config input items"""

    key_id = fields.Str(
        required=True,
        metadata={
            "description": "The config input base64 encoded key (used for linking keys containing spaces, etc.)",
            "example": "c8f122656ed2acabde9b57101a4c8ec7",
        },
    )
    key = fields.Str(
        required=True,
        metadata={"description": "The config input key or name", "example": "downmix_dts_hd_ma"},
    )
    value = fields.Raw(
        required=True,
        metadata={"description": "The current value of this config input", "example": False},
    )
    input_type = fields.Str(
        required=True,
        metadata={"description": "The config input type", "example": "checkbox"},
    )
    label = fields.Str(
        required=True,
        metadata={
            "description": "The label used to define this config input",
            "example": "Downmix DTS-HD Master Audio (max 5.1 channels)?",
        },
    )
    description = fields.Str(
        required=True,
        metadata={
            "description": "Description of input field",
            "example": "Will automatically downmix DTS-HD Master Audio to 5.1 channels ",
        },
        allow_none=True,
    )
    tooltip = fields.Str(
        required=True,
        metadata={
            "description": "Description of input field",
            "example": "Will automatically downmix DTS-HD Master Audio to 5.1 channels ",
        },
        allow_none=True,
    )
    select_options = fields.List(
        cls_or_instance=fields.Dict,
        required=True,
        metadata={
            "description": "Additional options if the input_type is set to 'select'",
            "example": [
                {
                    "value": "first",
                    "label": "First Option",
                },
                {
                    "value": "second",
                    "label": "Second Option",
                },
            ],
        },
    )
    slider_options = fields.Dict(
        required=True,
        metadata={
            "description": "Additional options if the input_type is set to 'slider'",
            "example": {"min": 1, "max": 8, "suffix": "M"},
        },
    )
    display = fields.Str(
        required=True,
        metadata={"description": "Should the setting input be displayed (visible, hidden)", "example": "visible"},
    )
    sub_setting = fields.Boolean(
        required=True,
        metadata={"description": "Should the setting be a nested sub-setting field", "example": False},
    )


class PluginsInfoResultsSchema(PluginsMetadataResultsSchema):
    """Schema for pending task results returned by the table"""

    settings = fields.Nested(
        PluginsConfigInputItemSchema,
        required=False,
        many=True,
        metadata={"description": "The plugin settings"},
    )


class RequestPluginsSettingsSaveSchema(BaseSchema):
    """Schema for requesting the update of a plugins settings by the plugin install ID"""

    plugin_id = fields.Str(
        required=True,
        metadata={"example": "encoder_video_hevc_vaapi"},
    )
    settings = fields.Nested(
        PluginsConfigInputItemSchema,
        required=True,
        many=True,
        metadata={"description": "The plugin settings"},
    )
    library_id = fields.Int(
        required=False,
        load_default=0,
        metadata={"example": 1},
    )


class RequestPluginsSettingsResetSchema(BaseSchema):
    """Schema for requesting the reset of a plugins settings by the plugin install ID"""

    plugin_id = fields.Str(
        required=True,
        metadata={"example": "encoder_video_hevc_vaapi"},
    )
    library_id = fields.Int(
        required=False,
        load_default=0,
        metadata={"example": 1},
    )


class PluginsMetadataInstallableResultsSchema(PluginsMetadataResultsSchema):
    """Schema for plugin metadata that will be returned when fetching installable plugins"""

    package_url = fields.Str(
        required=False,
        metadata={
            "description": "The plugin package download URL",
            "example": "https://raw.githubusercontent.com/Compresso/compresso-plugins/repo/plugin_id/plugin_id-1.0.0.zip",
        },
    )
    changelog_url = fields.Str(
        required=False,
        metadata={
            "description": "The plugin package download URL",
            "example": "https://raw.githubusercontent.com/Compresso/compresso-plugins/repo/plugin_id/changelog.md",
        },
    )
    repo_name = fields.Str(
        required=False,
        metadata={"description": "The name of the repository that this plugin is in", "example": "Official Repo"},
    )
    repo_id = fields.Str(
        required=False,
        metadata={
            "description": "The ID of the repository that this plugin is in",
            "example": "158899500680826593283708490873332175078",
        },
    )


class PluginsInstallableResultsSchema(BaseSchema):
    """Schema for installable plugins lists that are returned"""

    plugins = fields.Nested(
        PluginsMetadataInstallableResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )


class PluginTypesResultsSchema(BaseSchema):
    """Schema for installable plugins lists that are returned"""

    results = fields.List(
        cls_or_instance=fields.Str,
        required=True,
        metadata={
            "description": "List of Plugin Type IDs supported by this installation",
            "example": [
                "library_management.file_test",
                "postprocessor.file_move",
                "postprocessor.task_result",
                "worker.process",
            ],
        },
    )


class RequestPluginsFlowByPluginTypeSchema(BaseSchema):
    """Schema to request the plugin flow of a given plugin type"""

    plugin_type = fields.Str(
        required=True,
        metadata={"example": "library_management.file_test"},
    )
    library_id = fields.Int(
        required=False,
        load_default=1,
        metadata={"example": 1},
    )


class PluginFlowDataResultsSchema(BaseSchema):
    """Schema for plugin flow data items"""

    plugin_id = fields.Str(
        required=True,
        metadata={"description": "The plugin ID", "example": "encoder_video_h264_nvenc"},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "The plugin name", "example": "Video Encoder H264 - h264_nvenc"},
    )
    author = fields.Str(
        required=True,
        metadata={"description": "The plugin author", "example": "encoder_video_h264_nvenc"},
    )
    description = fields.Str(
        required=True,
        metadata={
            "description": "The plugin description",
            "example": "Ensure all video streams are encoded with the H264 codec using the h264_nvenc encoder.",
        },
    )
    version = fields.Str(
        required=True,
        metadata={"description": "The plugin version", "example": "Josh.5"},
    )
    icon = fields.Str(
        required=True,
        metadata={
            "description": "The plugin icon",
            "example": "https://raw.githubusercontent.com/Josh5/compresso-plugins/master/source/encoder_video_h264_nvenc/icon.png",
        },
    )


class PluginFlowResultsSchema(BaseSchema):
    """Schema for returned plugin flow list"""

    results = fields.Nested(
        PluginFlowDataResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )


class RequestSavingPluginsFlowByPluginTypeSchema(RequestPluginsFlowByPluginTypeSchema):
    """Schema to request saving the plugin flow of a given plugin type"""

    plugin_flow = fields.Nested(
        PluginFlowDataResultsSchema,
        required=True,
        metadata={"description": "Saved flow"},
        many=True,
        validate=validate.Length(min=1),
    )
    library_id = fields.Int(
        required=False,
        load_default=1,
        metadata={"example": 1},
    )


class PluginReposMetadataResultsSchema(BaseSchema):
    """Schema for plugin repo metadata that will be returned when fetching repo lists"""

    id = fields.Str(
        required=True,
        metadata={"description": "The plugin repo ID", "example": "repository.josh5"},
    )
    name = fields.Str(
        required=True,
        metadata={"description": "The plugin repo name", "example": "Josh.5 Development Plugins for Compresso"},
    )
    icon = fields.Str(
        required=True,
        metadata={
            "description": "The plugin repo icon",
            "example": "https://raw.githubusercontent.com/Josh5/compresso-plugins/master/icon.png",
        },
    )
    path = fields.Str(
        required=True,
        metadata={
            "description": "The plugin repo URL path",
            "example": "https://raw.githubusercontent.com/Josh5/compresso-plugins/repo/repo.json",
        },
    )
    repo_html_url = fields.Str(
        required=False,
        metadata={
            "description": "The plugin repo HTML URL (e.g. GitHub repository page)",
            "example": "https://github.com/Josh5/compresso-plugins",
        },
    )


class RequestUpdatePluginReposListSchema(BaseSchema):
    """Schema to request an update of the plugin repos list"""

    repos_list = fields.List(
        cls_or_instance=fields.Str,
        required=True,
        metadata={
            "description": "A list of repos to save",
            "example": [
                "https://raw.githubusercontent.com/Josh5/compresso-plugins/repo/repo.json",
            ],
        },
        validate=validate.Length(min=0),
    )


class PluginReposListResultsSchema(BaseSchema):
    """Schema for plugin repo lists that are returned"""

    repos = fields.Nested(
        PluginReposMetadataResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )


class PluginsDataPanelTypesDataSchema(BaseSchema):
    """Schema for returning a list of data panel plugins results"""

    results = fields.Nested(
        PluginFlowDataResultsSchema,
        required=True,
        metadata={"description": "Results"},
        many=True,
        validate=validate.Length(min=0),
    )
