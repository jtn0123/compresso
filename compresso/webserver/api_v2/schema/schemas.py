#!/usr/bin/env python3

"""
compresso.schemas.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     01 Aug 2021, (11:45 AM)

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

from marshmallow import Schema, fields, validate


class BaseSchema(Schema):
    pass


# RESPONSES
# =========


class BaseSuccessSchema(BaseSchema):
    success = fields.Boolean(
        required=True,
        metadata={"description": 'This is always "True" when a request succeeds', "example": True},
    )


class BaseErrorSchema(BaseSchema):
    error = fields.Str(
        required=True,
        metadata={"description": "Return status code and reason"},
    )
    messages = fields.Dict(
        required=True,
        metadata={
            "description": "Attached request body validation errors",
            "example": {"name": ["The thing that went wrong."]},
        },
    )
    traceback = fields.List(
        cls_or_instance=fields.Str,
        required=False,
        metadata={
            "description": "Attached exception traceback (if developer mode is enabled)",
            "example": [
                "Traceback (most recent call last):\n",
                "...",
                "json.decoder.JSONDecodeError: Expecting value: line 3 column 14 (char 45)\n",
            ],
        },
    )


class BadRequestSchema(BaseErrorSchema):
    """STATUS_ERROR_EXTERNAL = 400"""

    error = fields.Str(
        required=True,
        metadata={"description": "Return status code and reason", "example": "400: Failed request schema validation"},
    )


class BadEndpointSchema(BaseSchema):
    """STATUS_ERROR_ENDPOINT_NOT_FOUND = 404"""

    error = fields.Str(
        required=True,
        metadata={"description": "Return status code and reason", "example": "404: Endpoint not found"},
    )


class BadMethodSchema(BaseSchema):
    """STATUS_ERROR_METHOD_NOT_ALLOWED = 405"""

    error = fields.Str(
        required=True,
        metadata={"description": "Return status code and reason", "example": "405: Method 'GET' not allowed"},
    )


class InternalErrorSchema(BaseErrorSchema):
    """STATUS_ERROR_INTERNAL = 500"""

    error = fields.Str(
        required=True,
        metadata={"description": "Return status code and reason", "example": "500: Caught exception message"},
    )


# GENERIC
# =======


class RequestTableDataSchema(BaseSchema):
    """Table request schema"""

    start = fields.Int(
        required=False,
        metadata={"description": "Start row number to select from", "example": 0},
        load_default=0,
    )
    length = fields.Int(
        required=False,
        metadata={"description": "Number of rows to select", "example": 10},
        load_default=10,
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
    order_by = fields.Str(
        required=False,
        metadata={"description": "Column to order results by", "example": "finish_time"},
        load_default="",
    )
    order_direction = fields.Str(
        required=False,
        metadata={"description": "Order direction ('asc' or 'desc')", "example": "desc"},
        validate=validate.OneOf(["asc", "desc"]),
    )


class RequestTableUpdateByIdList(BaseSchema):
    """Schema for updating tables by ID"""

    id_list = fields.List(
        cls_or_instance=fields.Int,
        required=True,
        metadata={"description": "List of table IDs", "example": []},
        validate=validate.Length(min=1),
    )


class RequestTableUpdateByUuidList(BaseSchema):
    """Schema for updating tables by UUID"""

    uuid_list = fields.List(
        cls_or_instance=fields.Str,
        required=True,
        metadata={"description": "List of table UUIDs", "example": []},
        validate=validate.Length(min=1),
    )


class TableRecordsSuccessSchema(BaseSchema):
    """Schema for table results"""

    recordsTotal = fields.Int(
        required=False,
        metadata={"description": "Total number of records in this table", "example": 329},
    )
    recordsFiltered = fields.Int(
        required=False,
        metadata={"description": "Total number of records after filters have been applied", "example": 10},
        load_default=10,
    )
    results = fields.List(
        cls_or_instance=fields.Raw,
        required=False,
        metadata={"description": "Results", "example": []},
    )


class RequestDatabaseItemByIdSchema(BaseSchema):
    """Schema to request a single table item given its ID"""

    id = fields.Int(
        required=True,
        metadata={"description": "The ID of the table item", "example": 1},
    )


# Backward-compatible re-exports from split schema modules.
# New code should import directly from the domain-specific module.
from compresso.webserver.api_v2.schema.docs_schemas import (  # noqa: E402, F401
    DocumentContentSuccessSchema,
)
from compresso.webserver.api_v2.schema.filebrowser_schemas import (  # noqa: E402, F401
    DirectoryListingResultsSchema,
    RequestDirectoryListingDataSchema,
)
from compresso.webserver.api_v2.schema.history_schemas import (  # noqa: E402, F401
    CompletedTasksLogRequestSchema,
    CompletedTasksLogSchema,
    CompletedTasksSchema,
    CompletedTasksTableResultsSchema,
    MetadataEntrySchema,
    MetadataSearchResultsSchema,
    RequestAddCompletedToPendingTasksSchema,
    RequestCompletedTasksBulkActionSchema,
    RequestHistoryTableDataSchema,
    RequestMetadataByFingerprintSchema,
    RequestMetadataByTaskSchema,
    RequestMetadataDeleteSchema,
    RequestMetadataSearchSchema,
    RequestMetadataUpdateSchema,
)
from compresso.webserver.api_v2.schema.notification_schemas import (  # noqa: E402, F401
    NotificationDataSchema,
    RequestNotificationsDataSchema,
)
from compresso.webserver.api_v2.schema.pending_schemas import (  # noqa: E402, F401
    PendingTasksSchema,
    PendingTasksTableResultsSchema,
    PendingTaskTestResultSchema,
    RequestPendingTableDataSchema,
    RequestPendingTaskCreateSchema,
    RequestPendingTasksBulkActionSchema,
    RequestPendingTasksLibraryUpdateSchema,
    RequestPendingTasksReorderSchema,
    RequestPendingTaskTestSchema,
    TaskDownloadLinkSchema,
)
from compresso.webserver.api_v2.schema.plugin_schemas import (  # noqa: E402, F401
    PluginFlowDataResultsSchema,
    PluginFlowResultsSchema,
    PluginReposListResultsSchema,
    PluginReposMetadataResultsSchema,
    PluginsConfigInputItemSchema,
    PluginsDataPanelTypesDataSchema,
    PluginsDataSchema,
    PluginsInfoResultsSchema,
    PluginsInstallableResultsSchema,
    PluginsMetadataInstallableResultsSchema,
    PluginsMetadataResultsSchema,
    PluginsTableResultsSchema,
    PluginStatusSchema,
    PluginTypesResultsSchema,
    RequestPluginsByIdSchema,
    RequestPluginsFlowByPluginTypeSchema,
    RequestPluginsInfoSchema,
    RequestPluginsSettingsResetSchema,
    RequestPluginsSettingsSaveSchema,
    RequestPluginsTableDataSchema,
    RequestSavingPluginsFlowByPluginTypeSchema,
    RequestUpdatePluginReposListSchema,
)
from compresso.webserver.api_v2.schema.session_schemas import (  # noqa: E402, F401
    SessionAuthCodeSchema,
    SessionStateSuccessSchema,
)
from compresso.webserver.api_v2.schema.settings_schemas import (  # noqa: E402, F401
    LibraryResultsSchema,
    RequestLibraryByIdSchema,
    RequestRemoteInstallationLinkConfigSchema,
    RequestSettingsRemoteInstallationAddressValidationSchema,
    SettingsLibrariesListSchema,
    SettingsLibraryConfigReadAndWriteSchema,
    SettingsLibraryPluginConfigExportSchema,
    SettingsLibraryPluginConfigImportSchema,
    SettingsReadAndWriteSchema,
    SettingsRemoteInstallationDataSchema,
    SettingsRemoteInstallationLinkConfigSchema,
    SettingsSystemConfigSchema,
    SettingsWorkerGroupConfigSchema,
    WorkerEventScheduleResultsSchema,
    WorkerGroupsListSchema,
)
from compresso.webserver.api_v2.schema.system_schemas import (  # noqa: E402, F401
    SystemStatusCpuSchema,
    SystemStatusDiskSchema,
    SystemStatusGpuSchema,
    SystemStatusMemorySchema,
    SystemStatusPlatformSchema,
    SystemStatusSuccessSchema,
)
from compresso.webserver.api_v2.schema.version_schemas import (  # noqa: E402, F401
    VersionReadSuccessSchema,
)
from compresso.webserver.api_v2.schema.worker_schemas import (  # noqa: E402, F401
    RequestWorkerByIdSchema,
    WorkerStatusResultsSchema,
    WorkerStatusSuccessSchema,
)
