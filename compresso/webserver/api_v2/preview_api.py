#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.preview_api.py

    API handler for A/B preview comparison endpoints.

"""

import tornado.log

from compresso.libs.preview import PreviewManager
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.preview_schemas import (
    RequestPreviewCreateSchema,
    PreviewCreateResponseSchema,
    RequestPreviewStatusSchema,
    PreviewStatusResponseSchema,
    RequestPreviewCleanupSchema,
)


class ApiPreviewHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern":      r"/preview/create",
            "supported_methods": ["POST"],
            "call_method":       "create_preview",
        },
        {
            "path_pattern":      r"/preview/status",
            "supported_methods": ["POST"],
            "call_method":       "get_preview_status",
        },
        {
            "path_pattern":      r"/preview/cleanup",
            "supported_methods": ["POST"],
            "call_method":       "cleanup_preview",
        },
    ]

    async def create_preview(self):
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
            validate_library_exists(json_request.get('library_id'))

            # Validate source_path is within an allowed directory
            source_path = json_request.get('source_path')
            if source_path:
                import os
                real_path = os.path.realpath(source_path)
                allowed_roots = set()
                try:
                    from compresso.libs.unmodels import Libraries
                    for lib in Libraries.select(Libraries.path):
                        if lib.path:
                            allowed_roots.add(os.path.realpath(lib.path))
                except Exception:
                    pass
                try:
                    from compresso import config
                    cache_path = config.Config().get_cache_path()
                    if cache_path:
                        allowed_roots.add(os.path.realpath(cache_path))
                except Exception:
                    pass
                if allowed_roots and not any(real_path.startswith(root + os.sep) or real_path == root for root in allowed_roots):
                    raise ValueError("Source path is not within an allowed directory")

            preview_manager = PreviewManager()
            job_id = preview_manager.create_preview(
                source_path=json_request.get('source_path'),
                start_time=json_request.get('start_time', 0),
                duration=json_request.get('duration', 10),
                library_id=json_request.get('library_id', 1),
            )

            response = self.build_response(
                PreviewCreateResponseSchema(),
                {
                    "success": True,
                    "job_id":  job_id,
                }
            )
            self.write_success(response)
            return
        except (ValueError, RuntimeError) as e:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(e))
            self.write_error()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_preview_status(self):
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
            status = preview_manager.get_job_status(json_request.get('job_id'))

            if status is None:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Preview job not found")
                self.write_error()
                return

            response_data = {
                "success":       True,
                "job_id":        status.get('job_id', ''),
                "status":        status.get('status', 'unknown'),
                "error":         status.get('error'),
                "source_url":    status.get('source_url', ''),
                "encoded_url":   status.get('encoded_url', ''),
                "source_size":   status.get('source_size', 0),
                "encoded_size":  status.get('encoded_size', 0),
                "source_codec":  status.get('source_codec', ''),
                "encoded_codec": status.get('encoded_codec', ''),
                "vmaf_score":    status.get('vmaf_score'),
                "ssim_score":    status.get('ssim_score'),
            }

            response = self.build_response(PreviewStatusResponseSchema(), response_data)
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def cleanup_preview(self):
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
            preview_manager.cleanup_job(json_request.get('job_id'))

            self.write_success()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
