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

import tornado.log

from compresso import config
from compresso.libs.uiserver import CompressoDataQueues
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.settings_schemas import (
    SettingsReadAndWriteSchema,
    SettingsSystemConfigSchema,
)
from compresso.webserver.api_v2.settings_library_mixin import LibrarySettingsMixin
from compresso.webserver.api_v2.settings_link_mixin import LinkSettingsMixin
from compresso.webserver.api_v2.settings_worker_groups_mixin import WorkerGroupsMixin


class ApiSettingsHandler(WorkerGroupsMixin, LinkSettingsMixin, LibrarySettingsMixin, BaseApiHandler):
    config = None
    params = None
    compresso_data_queues = None

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

    def initialize(self, **kwargs):
        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()
        self.config = config.Config()

    async def get_all_settings(self):
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
            settings = self.config.get_config_as_dict()
            response = self.build_response(
                SettingsReadAndWriteSchema(),
                {
                    "settings": settings,
                },
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error(f"BaseApiError.{self.route.get('call_method')}: {bae!s}")
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def write_settings(self):
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
            settings_dict = json_request.get("settings", {})

            # Remove config items that should not be saved through this API endpoint
            remove_settings = ["remote_installations"]
            for remove_setting in remove_settings:
                if settings_dict.get(remove_setting):
                    del settings_dict[remove_setting]

            # Save settings - writing to file.
            # Throws exception if settings fail to save
            self.config.set_bulk_config_items(json_request.get("settings", {}))

            self.write_success()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error(f"BaseApiError.{self.route.get('call_method')}: {bae!s}")
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_system_configuration(self):
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
            tornado.log.app_log.error(f"BaseApiError.{self.route.get('call_method')}: {bae!s}")
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
