#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.healthcheck_api.py

    API handler for health check endpoints.

"""

import tornado.log

from unmanic.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from unmanic.webserver.api_v2.schema.healthcheck_schemas import (
    RequestHealthCheckScanSchema,
    RequestHealthCheckLibraryScanSchema,
    RequestHealthCheckStatusSchema,
    HealthCheckScanResponseSchema,
    HealthCheckLibraryScanResponseSchema,
    HealthCheckSummaryResponseSchema,
    HealthCheckStatusResponseSchema,
)
from unmanic.webserver.helpers import healthcheck


class ApiHealthcheckHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern":      r"/healthcheck/scan",
            "supported_methods": ["POST"],
            "call_method":       "scan_file",
        },
        {
            "path_pattern":      r"/healthcheck/scan-library",
            "supported_methods": ["POST"],
            "call_method":       "scan_library",
        },
        {
            "path_pattern":      r"/healthcheck/summary",
            "supported_methods": ["GET"],
            "call_method":       "get_summary",
        },
        {
            "path_pattern":      r"/healthcheck/status",
            "supported_methods": ["POST"],
            "call_method":       "get_status_list",
        },
    ]

    def initialize(self, **kwargs):
        self.params = kwargs.get("params")

    async def scan_file(self):
        """
        HealthCheck - scan single file
        ---
        description: Run a health check on a single file.
        requestBody:
            description: File path and check mode.
            required: True
            content:
                application/json:
                    schema:
                        RequestHealthCheckScanSchema
        responses:
            200:
                description: 'Returns health check result.'
                content:
                    application/json:
                        schema:
                            HealthCheckScanResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestHealthCheckScanSchema())

            result = healthcheck.check_single_file(
                filepath=json_request.get('file_path'),
                library_id=json_request.get('library_id', 1),
                mode=json_request.get('mode', 'quick'),
            )

            response = self.build_response(
                HealthCheckScanResponseSchema(),
                {
                    "success":       True,
                    "abspath":       result.get('abspath', ''),
                    "status":        result.get('status', ''),
                    "check_mode":    result.get('check_mode', ''),
                    "error_detail":  result.get('error_detail', ''),
                    "last_checked":  result.get('last_checked', ''),
                    "error_count":   result.get('error_count', 0),
                }
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def scan_library(self):
        """
        HealthCheck - scan library
        ---
        description: Start a background health scan of all files in a library.
        requestBody:
            description: Library ID and check mode.
            required: True
            content:
                application/json:
                    schema:
                        RequestHealthCheckLibraryScanSchema
        responses:
            200:
                description: 'Returns scan start status.'
                content:
                    application/json:
                        schema:
                            HealthCheckLibraryScanResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestHealthCheckLibraryScanSchema())

            started = healthcheck.scan_library(
                library_id=json_request.get('library_id'),
                mode=json_request.get('mode', 'quick'),
            )

            if started:
                message = "Library scan started"
            else:
                message = "A scan is already in progress"

            response = self.build_response(
                HealthCheckLibraryScanResponseSchema(),
                {
                    "success": True,
                    "started": started,
                    "message": message,
                }
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_summary(self):
        """
        HealthCheck - summary
        ---
        description: Get aggregate health status counts.
        responses:
            200:
                description: 'Returns health summary.'
                content:
                    application/json:
                        schema:
                            HealthCheckSummaryResponseSchema
        """
        try:
            library_id = self.get_argument('library_id', None)
            if library_id is not None:
                try:
                    library_id = int(library_id)
                except (ValueError, TypeError):
                    library_id = None

            summary = healthcheck.get_health_summary(library_id=library_id)
            progress = healthcheck.get_scan_progress()

            response = self.build_response(
                HealthCheckSummaryResponseSchema(),
                {
                    "success":        True,
                    "healthy":        summary.get('healthy', 0),
                    "corrupted":      summary.get('corrupted', 0),
                    "unchecked":      summary.get('unchecked', 0),
                    "checking":       summary.get('checking', 0),
                    "total":          summary.get('total', 0),
                    "scanning":       progress.get('scanning', False),
                    "scan_progress":  progress.get('progress', {}),
                }
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_status_list(self):
        """
        HealthCheck - status list
        ---
        description: Get paginated health status records.
        requestBody:
            description: Pagination and filter parameters.
            required: True
            content:
                application/json:
                    schema:
                        RequestHealthCheckStatusSchema
        responses:
            200:
                description: 'Returns paginated health status list.'
                content:
                    application/json:
                        schema:
                            HealthCheckStatusResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestHealthCheckStatusSchema())

            params = {
                'start':         json_request.get('start', 0),
                'length':        json_request.get('length', 10),
                'search_value':  json_request.get('search_value', ''),
                'library_id':    json_request.get('library_id'),
                'status_filter': json_request.get('status_filter'),
                'order':         {
                    "column": json_request.get('order_by', 'last_checked'),
                    "dir":    json_request.get('order_direction', 'desc'),
                }
            }
            statuses = healthcheck.get_health_statuses_paginated(params)

            response = self.build_response(
                HealthCheckStatusResponseSchema(),
                {
                    "success":         True,
                    "recordsTotal":    statuses.get('recordsTotal', 0),
                    "recordsFiltered": statuses.get('recordsFiltered', 0),
                    "results":         statuses.get('results', []),
                }
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
