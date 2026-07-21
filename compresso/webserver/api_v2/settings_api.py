#!/usr/bin/env python3

"""
compresso.settings_api.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     20 Aug 2021, (2:30 PM)

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

from collections.abc import Mapping

from compresso import config
from compresso.libs.uiserver import CompressoDataQueues, DataQueues
from compresso.webserver.api_v2.base_api_handler import BaseApiError
from compresso.webserver.api_v2.schema.settings_schemas import (
    SettingsReadAndWriteSchema,
    SettingsSystemConfigSchema,
)
from compresso.webserver.api_v2.settings_library_mixin import LibrarySettingsMixin
from compresso.webserver.api_v2.settings_link_mixin import LinkSettingsMixin
from compresso.webserver.api_v2.settings_worker_groups_mixin import WorkerGroupsMixin

PROTECTED_SETTINGS = frozenset({"api_auth_token", "notification_channels", "remote_installations"})
PUBLIC_REMOTE_INSTALLATION_FIELDS = (
    "address",
    "name",
    "uuid",
    "available",
    "version",
    "last_updated",
    "enable_receiving_tasks",
    "enable_sending_tasks",
    "enable_task_preloading",
    "preloading_count",
    "enable_checksum_validation",
    "enable_config_missing_libraries",
    "enable_distributed_worker_count",
    "distributed_worker_count_target",
    "task_count",
    "runnable_task_count",
    "capabilities",
)


def serialize_public_settings(raw_settings: Mapping[str, object]) -> dict[str, object]:
    """Return settings safe for browser clients and logs."""
    settings = dict(raw_settings)
    settings.pop("api_auth_token", None)
    settings.pop("notification_channels", None)

    public_remotes: list[dict[str, object]] = []
    remote_installations = settings.get("remote_installations", [])
    if isinstance(remote_installations, list):
        for remote in remote_installations:
            if not isinstance(remote, Mapping):
                continue
            public_remotes.append({field: remote[field] for field in PUBLIC_REMOTE_INSTALLATION_FIELDS if field in remote})
    settings["remote_installations"] = public_remotes
    return settings


class ApiSettingsHandler(WorkerGroupsMixin, LinkSettingsMixin, LibrarySettingsMixin):
    config: config.Config
    params: object
    compresso_data_queues: DataQueues

    routes = [
        {
            "path_pattern": r"/settings/read",
            "supported_methods": ["GET"],
            "call_method": "get_all_settings",
        },
        {
            "path_pattern": r"/settings/write",
            "supported_methods": ["POST"],
            "call_method": "write_settings",
        },
        {
            "path_pattern": r"/settings/configuration",
            "supported_methods": ["GET"],
            "call_method": "get_system_configuration",
        },
        {
            "path_pattern": r"/settings/link/validate",
            "supported_methods": ["POST"],
            "call_method": "validate_remote_installation",
        },
        {
            "path_pattern": r"/settings/worker_groups",
            "supported_methods": ["GET"],
            "call_method": "get_all_worker_groups",
        },
        {
            "path_pattern": r"/settings/worker_group/read",
            "supported_methods": ["POST"],
            "call_method": "read_worker_group_config",
        },
        {
            "path_pattern": r"/settings/worker_group/write",
            "supported_methods": ["POST"],
            "call_method": "write_worker_group_config",
        },
        {
            "path_pattern": r"/settings/worker_group/remove",
            "supported_methods": ["DELETE"],
            "call_method": "remove_worker_group",
        },
        {
            "path_pattern": r"/settings/link/read",
            "supported_methods": ["POST"],
            "call_method": "read_link_config",
        },
        {
            "path_pattern": r"/settings/link/write",
            "supported_methods": ["POST"],
            "call_method": "write_link_config",
        },
        {
            "path_pattern": r"/settings/link/remove",
            "supported_methods": ["DELETE"],
            "call_method": "remove_link_config",
        },
        {
            "path_pattern": r"/settings/libraries",
            "supported_methods": ["GET"],
            "call_method": "get_all_libraries",
        },
        {
            "path_pattern": r"/settings/library/read",
            "supported_methods": ["POST"],
            "call_method": "read_library_config",
        },
        {
            "path_pattern": r"/settings/library/write",
            "supported_methods": ["POST"],
            "call_method": "write_library_config",
        },
        {
            "path_pattern": r"/settings/library/remove",
            "supported_methods": ["DELETE"],
            "call_method": "remove_library",
        },
        {
            "path_pattern": r"/settings/library/export",
            "supported_methods": ["POST"],
            "call_method": "export_library_plugin_config",
        },
        {
            "path_pattern": r"/settings/library/import",
            "supported_methods": ["POST"],
            "call_method": "import_library_plugin_config",
        },
    ]

    def initialize(self, **kwargs: object) -> None:
        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()
        self.config = config.Config()

    async def get_all_settings(self) -> None:
        """
        Settings - read
        ---
        description: Returns the application settings.
        responses:
            200:
                description: 'Sample response: Returns the application settings.'
                content:
                    application/json:
                        schema:
                            SettingsReadAndWriteSchema
            400:
                description: Bad request; Check `messages` for any validation errors
                content:
                    application/json:
                        schema:
                            BadRequestSchema
            404:
                description: Bad request; Requested endpoint not found
                content:
                    application/json:
                        schema:
                            BadEndpointSchema
            405:
                description: Bad request; Requested method is not allowed
                content:
                    application/json:
                        schema:
                            BadMethodSchema
            500:
                description: Internal error; Check `error` for exception
                content:
                    application/json:
                        schema:
                            InternalErrorSchema
        """
        try:
            settings = serialize_public_settings(self.config.get_config_as_dict())
            response = self.build_response(
                SettingsReadAndWriteSchema(),
                {
                    "settings": settings,
                },
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def write_settings(self) -> None:
        """
        Settings - save a dictionary of settings
        ---
        description: Save a given dictionary of settings.
        requestBody:
            description: Requested a dictionary of settings to save.
            required: True
            content:
                application/json:
                    schema:
                        SettingsReadAndWriteSchema
        responses:
            200:
                description: 'Successful request; Returns success status'
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
            400:
                description: Bad request; Check `messages` for any validation errors
                content:
                    application/json:
                        schema:
                            BadRequestSchema
            404:
                description: Bad request; Requested endpoint not found
                content:
                    application/json:
                        schema:
                            BadEndpointSchema
            405:
                description: Bad request; Requested method is not allowed
                content:
                    application/json:
                        schema:
                            BadMethodSchema
            500:
                description: Internal error; Check `error` for exception
                content:
                    application/json:
                        schema:
                            InternalErrorSchema
        """
        try:
            json_request = self.read_json_request(SettingsReadAndWriteSchema())

            # Get settings dict from request
            settings_value = json_request.get("settings", {})
            if not isinstance(settings_value, Mapping) or not all(isinstance(key, str) for key in settings_value):
                raise BaseApiError("Settings must be an object")
            settings_dict = {str(key): value for key, value in settings_value.items()}

            protected_keys = sorted(PROTECTED_SETTINGS.intersection(settings_dict))
            if protected_keys:
                raise BaseApiError(
                    "Protected settings require their dedicated endpoint",
                    messages={"settings": protected_keys},
                    private_detail=f"Rejected protected settings: {', '.join(protected_keys)}",
                )

            # Save settings - writing to file.
            # Throws exception if settings fail to save
            self.config.set_bulk_config_items(settings_dict)

            self.write_success()
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_system_configuration(self) -> None:
        """
        Settings - read the system configuration
        ---
        description: Returns the system configuration.
        responses:
            200:
                description: 'Sample response: Returns the system configuration.'
                content:
                    application/json:
                        schema:
                            SettingsSystemConfigSchema
            400:
                description: Bad request; Check `messages` for any validation errors
                content:
                    application/json:
                        schema:
                            BadRequestSchema
            404:
                description: Bad request; Requested endpoint not found
                content:
                    application/json:
                        schema:
                            BadEndpointSchema
            405:
                description: Bad request; Requested method is not allowed
                content:
                    application/json:
                        schema:
                            BadMethodSchema
            500:
                description: Internal error; Check `error` for exception
                content:
                    application/json:
                        schema:
                            InternalErrorSchema
        """
        try:
            from compresso.libs.system import System

            system = System()
            system_info = system.info()
            response = self.build_response(
                SettingsSystemConfigSchema(),
                {
                    "configuration": system_info,
                },
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)
