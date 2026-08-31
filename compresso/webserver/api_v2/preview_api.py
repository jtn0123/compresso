#!/usr/bin/env python3

"""
compresso.preview_api.py

API handler for A/B preview comparison endpoints.

"""

from tornado.log import app_log

from compresso.libs.preview import PreviewManager
from compresso.webserver.api_v2.base_api_handler import (
    BaseApiError,
    BaseApiHandler,
    float_value,
    optional_integer_value,
    string_value,
)
from compresso.webserver.api_v2.schema.preview_schemas import (
    PreviewCreateResponseSchema,
    PreviewStatusResponseSchema,
    RequestPreviewCleanupSchema,
    RequestPreviewCreateSchema,
    RequestPreviewStatusSchema,
)


class ApiPreviewHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern": r"/preview/create",
            "supported_methods": ["POST"],
            "call_method": "create_preview",
        },
        {
            "path_pattern": r"/preview/status",
            "supported_methods": ["POST"],
            "call_method": "get_preview_status",
        },
        {
            "path_pattern": r"/preview/cleanup",
            "supported_methods": ["POST"],
            "call_method": "cleanup_preview",
        },
    ]

    async def create_preview(self) -> None:
        """
        Preview - create
        ---
        description: Create a new A/B preview comparison job.
        requestBody:
            description: Source file path, time range, and library ID.
            required: True
            content:
                application/json:
                    schema:
                        RequestPreviewCreateSchema
        responses:
            200:
                description: 'Returns the job ID for the new preview.'
                content:
                    application/json:
                        schema:
                            PreviewCreateResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestPreviewCreateSchema())

            from compresso.webserver.helpers.healthcheck import validate_library_exists

            # Only validate an explicitly provided library id (absent means default)
            library_id_value = optional_integer_value(json_request.get("library_id"))
            validate_library_exists(library_id_value)
            library_id = 1 if library_id_value is None else library_id_value

            source_path = string_value(json_request.get("source_path"))
            self._validate_preview_source_path(source_path)

            preview_manager = PreviewManager()
            job_id = preview_manager.create_preview(
                source_path=source_path,
                start_time=float_value(json_request.get("start_time")),
                duration=float_value(json_request.get("duration"), 10.0),
                library_id=library_id,
            )

            response = self.build_response(
                PreviewCreateResponseSchema(),
                {
                    "success": True,
                    "job_id": job_id,
                },
            )
            self.write_success(response)
            return
        except (ValueError, RuntimeError) as exc:
            self.handle_base_api_error(
                BaseApiError("Preview request could not be processed", private_detail=f"{type(exc).__name__}: {exc}")
            )
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    @staticmethod
    def _validate_preview_source_path(source_path: str) -> None:
        if not source_path:
            return
        import os

        allowed_roots: set[str] = set()
        try:
            from compresso.libs.unmodels import Libraries

            allowed_roots.update(os.path.realpath(lib.path) for lib in Libraries.select(Libraries.path) if lib.path)
        except Exception:
            app_log.exception("Failed to load library paths for path validation")
        try:
            from compresso import config

            if cache_path := config.Config().get_cache_path():
                allowed_roots.add(os.path.realpath(cache_path))
        except Exception:
            app_log.exception("Failed to load cache path for path validation")
        real_path = os.path.realpath(source_path)
        if not allowed_roots or not any(real_path == root or real_path.startswith(root + os.sep) for root in allowed_roots):
            raise ValueError("Source path is not within an allowed directory")

    async def get_preview_status(self) -> None:
        """
        Preview - status
        ---
        description: Get the status of a preview job.
        requestBody:
            description: The job ID to check.
            required: True
            content:
                application/json:
                    schema:
                        RequestPreviewStatusSchema
        responses:
            200:
                description: 'Returns preview status, URLs, and size info.'
                content:
                    application/json:
                        schema:
                            PreviewStatusResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestPreviewStatusSchema())

            preview_manager = PreviewManager()
            status = preview_manager.get_job_status(string_value(json_request.get("job_id")))

            if status is None:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Preview job not found")
                self.write_error()
                return

            response_data = {
                "success": True,
                "job_id": status.get("job_id", ""),
                "status": status.get("status", "unknown"),
                "error": status.get("error"),
                "source_url": status.get("source_url", ""),
                "encoded_url": status.get("encoded_url", ""),
                "source_size": status.get("source_size", 0),
                "encoded_size": status.get("encoded_size", 0),
                "source_codec": status.get("source_codec", ""),
                "encoded_codec": status.get("encoded_codec", ""),
                "vmaf_score": status.get("vmaf_score"),
                "ssim_score": status.get("ssim_score"),
            }

            response = self.build_response(PreviewStatusResponseSchema(), response_data)
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def cleanup_preview(self) -> None:
        """
        Preview - cleanup
        ---
        description: Clean up a preview job and its files.
        requestBody:
            description: The job ID to clean up.
            required: True
            content:
                application/json:
                    schema:
                        RequestPreviewCleanupSchema
        responses:
            200:
                description: 'Success response.'
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
        """
        try:
            json_request = self.read_json_request(RequestPreviewCleanupSchema())

            preview_manager = PreviewManager()
            preview_manager.cleanup_job(string_value(json_request.get("job_id")))

            self.write_success()
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)
