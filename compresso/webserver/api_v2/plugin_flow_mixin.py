#!/usr/bin/env python3

"""
compresso.plugin_flow_mixin.py

Mixin providing plugin flow configuration endpoints for ApiPluginsHandler.
"""

import tornado.log

from compresso.webserver.api_v2.base_api_handler import BaseApiError
from compresso.webserver.api_v2.schema.plugin_schemas import (
    PluginFlowResultsSchema,
    PluginTypesResultsSchema,
    RequestPluginsFlowByPluginTypeSchema,
    RequestSavingPluginsFlowByPluginTypeSchema,
)
from compresso.webserver.helpers import plugins


class PluginFlowMixin:
    """Mixin for plugin flow configuration endpoints."""

    async def get_plugin_types_with_flows(self):
        """
        Plugins - Get a list of all plugin types that have flows
        ---
        description: Returns a list of all plugin types that have flows.
        responses:
            200:
                description: 'Sample response: Returns a list of all plugin types that have flows.'
                content:
                    application/json:
                        schema:
                            PluginTypesResultsSchema
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
            results = plugins.get_plugin_types_with_flows()
            response = self.build_response(
                PluginTypesResultsSchema(),
                {
                    "results": results,
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
            tornado.log.app_log.exception("Unhandled error in %s.%s", self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_enabled_plugins_flow_by_type(self):
        """
        Plugins - Get the plugin flow for a requested plugin type
        ---
        description: Returns the plugin flow for a requested plugin type.
        requestBody:
            description: Requests the plugin flow of a given plugin type.
            required: True
            content:
                application/json:
                    schema:
                        RequestPluginsFlowByPluginTypeSchema
        responses:
            200:
                description: 'Sample response: Returns the plugin flow for a requested plugin type.'
                content:
                    application/json:
                        schema:
                            PluginFlowResultsSchema
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
            json_request = self.read_json_request(RequestPluginsFlowByPluginTypeSchema())

            results = plugins.get_enabled_plugin_flows_for_plugin_type(
                json_request.get("plugin_type"), json_request.get("library_id")
            )
            response = self.build_response(
                PluginFlowResultsSchema(),
                {
                    "results": results,
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
            tornado.log.app_log.exception("Unhandled error in %s.%s", self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def save_enabled_plugin_flow(self):
        """
        Plugins - Save the plugin flow for a requested plugin type
        ---
        description: Saves the plugin flow for a requested plugin type.
        requestBody:
            description: Requests saving the plugin flow for a given plugin type.
            required: True
            content:
                application/json:
                    schema:
                        RequestSavingPluginsFlowByPluginTypeSchema
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
            json_request = self.read_json_request(RequestSavingPluginsFlowByPluginTypeSchema())

            if not plugins.save_enabled_plugin_flows_for_plugin_type(
                json_request.get("plugin_type"), json_request.get("library_id"), json_request.get("plugin_flow")
            ):
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Failed to update plugin flow by type")
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
            tornado.log.app_log.exception("Unhandled error in %s.%s", self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
