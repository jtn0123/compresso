#!/usr/bin/env python3

"""
compresso.settings_worker_groups_mixin.py

Mixin providing worker group management endpoints for ApiSettingsHandler.
"""

import tornado.log

from compresso.libs.worker_group import WorkerGroup
from compresso.webserver.api_v2.base_api_handler import BaseApiError
from compresso.webserver.api_v2.schema.schemas import RequestDatabaseItemByIdSchema
from compresso.webserver.api_v2.schema.settings_schemas import (
    SettingsWorkerGroupConfigSchema,
    WorkerGroupsListSchema,
)


class WorkerGroupsMixin:
    """Mixin for worker group CRUD endpoints."""

    async def get_all_worker_groups(self):
        """
        Settings - get list of all worker groups
        ---
        description: Returns a list of all worker groups.
        responses:
            200:
                description: 'Sample response: Returns a list of all worker groups.'
                content:
                    application/json:
                        schema:
                            WorkerGroupsListSchema
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
            worker_groups = WorkerGroup.get_all_worker_groups()
            response = self.build_response(
                WorkerGroupsListSchema(),
                {
                    "worker_groups": worker_groups,
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

    async def read_worker_group_config(self):
        """
        Settings - read the configuration of a worker group
        ---
        description: Read the configuration of a worker group
        requestBody:
            description: The ID of the worker group
            required: True
            content:
                application/json:
                    schema:
                        RequestDatabaseItemByIdSchema
        responses:
            200:
                description: 'Sample response: Returns the worker group configuration.'
                content:
                    application/json:
                        schema:
                            SettingsWorkerGroupConfigSchema
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
            json_request = self.read_json_request(RequestDatabaseItemByIdSchema())

            # Fetch all data for this worker group
            worker_group = WorkerGroup(json_request.get("id"))
            if not worker_group:
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Unable to find worker group config by its ID")
                self.write_error()
                return

            response = self.build_response(
                SettingsWorkerGroupConfigSchema(),
                {
                    "id": worker_group.get_id(),
                    "locked": worker_group.get_locked(),
                    "name": worker_group.get_name(),
                    "number_of_workers": worker_group.get_number_of_workers(),
                    "worker_type": worker_group.get_worker_type(),
                    "worker_event_schedules": worker_group.get_worker_event_schedules(),
                    "tags": worker_group.get_tags(),
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

    async def write_worker_group_config(self):
        """
        Settings - write the configuration of a worker group
        ---
        description: Write the configuration of a worker group
        requestBody:
            description: The config of a worker group that is to be saved
            required: True
            content:
                application/json:
                    schema:
                        SettingsWorkerGroupConfigSchema
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
            json_request = self.read_json_request(SettingsWorkerGroupConfigSchema())

            # Write config for this worker group
            from compresso.webserver.helpers import settings

            settings.save_worker_group_config(json_request)

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

    async def remove_worker_group(self):
        """
        Settings - remove a worker group
        ---
        description: Remove a worker group
        requestBody:
            description: Requested a worker group to remove.
            required: True
            content:
                application/json:
                    schema:
                        RequestDatabaseItemByIdSchema
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
            json_request = self.read_json_request(RequestDatabaseItemByIdSchema())

            # Fetch existing worker group by ID
            worker_group = WorkerGroup(json_request.get("id"))

            # Delete the worker group
            if not worker_group.delete():
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Failed to remove worker group by its ID")
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
