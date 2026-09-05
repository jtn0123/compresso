#!/usr/bin/env python3

"""
compresso.settings_library_mixin.py

Mixin providing library configuration endpoints for ApiSettingsHandler.
"""

from collections.abc import Mapping

from compresso.libs.library import Library
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler, integer_value
from compresso.webserver.api_v2.schema.settings_schemas import (
    RequestLibraryByIdSchema,
    SettingsLibrariesListSchema,
    SettingsLibraryConfigReadAndWriteSchema,
    SettingsLibraryPluginConfigExportSchema,
    SettingsLibraryPluginConfigImportSchema,
)


class LibrarySettingsMixin(BaseApiHandler):
    """Mixin for library configuration CRUD endpoints."""

    def _save_library_payload(
        self,
        json_request: Mapping[str, object],
        *,
        library_id: object,
        invalid_reason: str,
        failure_reason: str,
    ) -> bool:
        """Parse and save the shared library write/import payload shape."""
        from compresso.webserver.helpers import settings

        try:
            request = settings.parse_library_save_request(
                library_id,
                json_request.get("library_config"),
                json_request.get("plugins", {}),
            )
        except ValueError as error:
            raise BaseApiError(invalid_reason) from error
        if settings.save_library_request(request):
            return True
        self.set_status(self.STATUS_ERROR_INTERNAL, reason=failure_reason)
        self.write_error()
        return False

    async def get_all_libraries(self) -> None:
        """
        Settings - get list of all libraries
        ---
        description: Returns a list of all libraries.
        responses:
            200:
                description: 'Sample response: Returns a list of all libraries.'
                content:
                    application/json:
                        schema:
                            SettingsLibrariesListSchema
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
            libraries = Library.get_all_libraries()
            response = self.build_response(
                SettingsLibrariesListSchema(),
                {
                    "libraries": libraries,
                },
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def read_library_config(self) -> None:
        """
        Settings - read the configuration of one library
        ---
        description: Read the configuration of one library
        requestBody:
            description: The ID of the library
            required: True
            content:
                application/json:
                    schema:
                        RequestLibraryByIdSchema
        responses:
            200:
                description: 'Sample response: Returns the remote installation link configuration.'
                content:
                    application/json:
                        schema:
                            SettingsLibraryConfigReadAndWriteSchema
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
            json_request = self.read_json_request(RequestLibraryByIdSchema())

            library_settings = {
                "library_config": {
                    "id": 0,
                    "name": "",
                    "path": "/",
                    "enable_remote_only": False,
                    "enable_scanner": False,
                    "enable_inotify": False,
                    "priority_score": 0,
                },
                "plugins": {
                    "enabled_plugins": [],
                },
            }
            if json_request.get("id"):
                # Read the library
                library_config = Library(integer_value(json_request.get("id")))
                library_settings = {
                    "library_config": {
                        "id": library_config.get_id(),
                        "name": library_config.get_name(),
                        "path": library_config.get_path(),
                        "locked": library_config.get_locked(),
                        "enable_remote_only": library_config.get_enable_remote_only(),
                        "enable_scanner": library_config.get_enable_scanner(),
                        "enable_inotify": library_config.get_enable_inotify(),
                        "priority_score": library_config.get_priority_score(),
                        "tags": library_config.get_tags(),
                        "target_codecs": library_config.get_target_codecs(),
                        "skip_codecs": library_config.get_skip_codecs(),
                        "size_guardrail_enabled": library_config.get_size_guardrail_enabled(),
                        "size_guardrail_min_pct": library_config.get_size_guardrail_min_pct(),
                        "size_guardrail_max_pct": library_config.get_size_guardrail_max_pct(),
                        "replacement_policy": library_config.get_replacement_policy(),
                    },
                    "plugins": {
                        "enabled_plugins": library_config.get_enabled_plugins(),
                    },
                }

            response = self.build_response(SettingsLibraryConfigReadAndWriteSchema(), library_settings)

            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def write_library_config(self) -> None:
        """
        Settings - write the configuration of one library
        ---
        description: Write the configuration of one library
        requestBody:
            description: Requested a dictionary of settings to save.
            required: True
            content:
                application/json:
                    schema:
                        SettingsLibraryConfigReadAndWriteSchema
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
            json_request = self.read_json_request(SettingsLibraryConfigReadAndWriteSchema())

            library_config = json_request.get("library_config")
            library_id = library_config.get("id") if isinstance(library_config, Mapping) else None
            if not self._save_library_payload(
                json_request,
                library_id=library_id,
                invalid_reason="Library configuration must contain objects",
                failure_reason="Failed to write library config",
            ):
                return

            self.write_success()
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def remove_library(self) -> None:
        """
        Settings - remove a library
        ---
        description: Remove a library
        requestBody:
            description: Requested a library to remove.
            required: True
            content:
                application/json:
                    schema:
                        RequestLibraryByIdSchema
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
            json_request = self.read_json_request(RequestLibraryByIdSchema())

            # Fetch existing library by ID
            library = Library(integer_value(json_request.get("id")))

            # Delete the library
            if not library.delete():
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="Failed to remove library by its ID")
                self.write_error()
                return

            self.write_success()
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def export_library_plugin_config(self) -> None:
        """
        Settings - export the plugin configuration of one library
        ---
        description: Export the plugin configuration of one library
        requestBody:
            description: The ID of the library
            required: True
            content:
                application/json:
                    schema:
                        RequestLibraryByIdSchema
        responses:
            200:
                description: 'Sample response: Returns the remote installation link configuration.'
                content:
                    application/json:
                        schema:
                            SettingsLibraryPluginConfigExportSchema
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
            json_request = self.read_json_request(RequestLibraryByIdSchema())

            # Fetch library config
            library_config = Library.export(integer_value(json_request.get("id")))

            response = self.build_response(SettingsLibraryPluginConfigExportSchema(), library_config)

            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def import_library_plugin_config(self) -> None:
        """
        Settings - import the plugin configuration of one library
        ---
        description: Import the configuration of one library
        requestBody:
            description: Requested a dictionary of settings to save.
            required: True
            content:
                application/json:
                    schema:
                        SettingsLibraryPluginConfigImportSchema
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
            json_request = self.read_json_request(SettingsLibraryPluginConfigImportSchema())

            if not self._save_library_payload(
                json_request,
                library_id=json_request.get("library_id"),
                invalid_reason="Imported library configuration must contain objects",
                failure_reason="Failed to import library config",
            ):
                return

            self.write_success()
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)
