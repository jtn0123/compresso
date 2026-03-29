#!/usr/bin/env python3

"""
compresso.settings_link_mixin.py

Mixin providing remote installation link endpoints for ApiSettingsHandler.
"""

import tornado.log

from compresso.libs.installation_link import Links
from compresso.webserver.api_v2.base_api_handler import BaseApiError
from compresso.webserver.api_v2.schema.settings_schemas import (
    RequestRemoteInstallationLinkConfigSchema,
    RequestSettingsRemoteInstallationAddressValidationSchema,
    SettingsRemoteInstallationDataSchema,
    SettingsRemoteInstallationLinkConfigSchema,
)


class LinkSettingsMixin:
    """Mixin for remote installation link CRUD endpoints."""

    async def validate_remote_installation(self):
        """
        Settings - validate a remote installation address
        ---
        description: Validate a remote installation address
        requestBody:
            description: The details of the remote installation to validate
            required: True
            content:
                application/json:
                    schema:
                        RequestSettingsRemoteInstallationAddressValidationSchema
        responses:
            200:
                description: 'Sample response: Returns the remote installation data.'
                content:
                    application/json:
                        schema:
                            SettingsRemoteInstallationDataSchema
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
            json_request = self.read_json_request(RequestSettingsRemoteInstallationAddressValidationSchema())

            # Fetch all data from the remote installation
            # Throws exception if the provided address is invalid
            links = Links()
            data = links.validate_remote_installation(
                json_request.get("address"),
                auth=json_request.get("auth"),
                username=json_request.get("username"),
                password=json_request.get("password"),
            )

            response = self.build_response(
                SettingsRemoteInstallationDataSchema(),
                {
                    "installation": data,
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

    async def read_link_config(self):
        """
        Settings - read the configuration of a remote installation link
        ---
        description: Read the configuration of a remote installation link
        requestBody:
            description: The UUID of the remote installation
            required: True
            content:
                application/json:
                    schema:
                        RequestRemoteInstallationLinkConfigSchema
        responses:
            200:
                description: 'Sample response: Returns the remote installation link configuration.'
                content:
                    application/json:
                        schema:
                            SettingsRemoteInstallationLinkConfigSchema
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
            json_request = self.read_json_request(RequestRemoteInstallationLinkConfigSchema())

            # Fetch all data from the remote installation
            # Throws exception if the provided address is invalid
            links = Links()
            data = links.read_remote_installation_link_config(json_request.get("uuid"))

            response = self.build_response(
                SettingsRemoteInstallationLinkConfigSchema(),
                {
                    "link_config": {
                        "address": data.get("address"),
                        "auth": data.get("auth"),
                        "username": data.get("username"),
                        "password": data.get("password"),
                        "available": data.get("available", False),
                        "name": data.get("name"),
                        "version": data.get("version"),
                        "last_updated": data.get("last_updated", 1),
                        "enable_receiving_tasks": data.get("enable_receiving_tasks"),
                        "enable_sending_tasks": data.get("enable_sending_tasks"),
                        "enable_task_preloading": data.get("enable_task_preloading"),
                        "preloading_count": data.get("preloading_count"),
                        "enable_checksum_validation": data.get("enable_checksum_validation"),
                        "enable_config_missing_libraries": data.get("enable_config_missing_libraries"),
                        "enable_distributed_worker_count": data.get("enable_distributed_worker_count", False),
                    },
                    "distributed_worker_count_target": data.get("distributed_worker_count_target", 0),
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

    async def write_link_config(self):
        """
        Settings - write the configuration of a remote installation link
        ---
        description: Write the configuration of a remote installation link
        requestBody:
            description: The UUID of the remote installation and its configuration
            required: True
            content:
                application/json:
                    schema:
                        SettingsRemoteInstallationLinkConfigSchema
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
            json_request = self.read_json_request(SettingsRemoteInstallationLinkConfigSchema())

            # Update a single remote installation config by matching the UUID
            links = Links()
            links.update_single_remote_installation_link_config(
                json_request.get("link_config"), json_request.get("distributed_worker_count_target", 0)
            )

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

    async def remove_link_config(self):
        """
        Settings - remove a configuration for a remote installation link
        ---
        description: Remove a configuration for a remote installation link
        requestBody:
            description: Requested a remote installation link to remove.
            required: True
            content:
                application/json:
                    schema:
                        RequestRemoteInstallationLinkConfigSchema
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
            json_request = self.read_json_request(RequestRemoteInstallationLinkConfigSchema())

            # Delete the remote installation using the given uuid
            links = Links()
            if not links.delete_remote_installation_link_config(json_request.get("uuid")):
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Failed to remove link by its uuid")
                self.write_error()
                return

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
