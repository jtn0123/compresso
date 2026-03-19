#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.compression_api.py

    API handler for compression statistics endpoints.

"""

import tornado.log

from unmanic.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from unmanic.webserver.api_v2.schema.compression_schemas import (
    RequestCompressionStatsSchema,
    CompressionStatsSchema,
    CompressionSummarySchema,
    PendingEstimateSchema,
    CodecDistributionSchema,
    ResolutionDistributionSchema,
    ContainerDistributionSchema,
    TimelineSchema,
)
from unmanic.webserver.helpers import compression_stats
from unmanic.webserver.helpers.healthcheck import validate_library_exists


class ApiCompressionHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern":      r"/compression/stats",
            "supported_methods": ["POST"],
            "call_method":       "get_compression_stats",
        },
        {
            "path_pattern":      r"/compression/summary",
            "supported_methods": ["GET"],
            "call_method":       "get_compression_summary",
        },
        {
            "path_pattern":      r"/compression/pending-estimate",
            "supported_methods": ["GET"],
            "call_method":       "get_pending_estimate",
        },
        {
            "path_pattern":      r"/compression/codec-distribution",
            "supported_methods": ["GET"],
            "call_method":       "get_codec_distribution",
        },
        {
            "path_pattern":      r"/compression/resolution-distribution",
            "supported_methods": ["GET"],
            "call_method":       "get_resolution_distribution",
        },
        {
            "path_pattern":      r"/compression/container-distribution",
            "supported_methods": ["GET"],
            "call_method":       "get_container_distribution",
        },
        {
            "path_pattern":      r"/compression/timeline",
            "supported_methods": ["GET"],
            "call_method":       "get_timeline",
        },
    ]

    async def get_compression_stats(self):
        """
        Compression - per-file stats
        ---
        description: Returns paginated per-file compression statistics.
        requestBody:
            description: Pagination and filter parameters.
            required: True
            content:
                application/json:
                    schema:
                        RequestCompressionStatsSchema
        responses:
            200:
                description: 'Returns paginated compression stats.'
                content:
                    application/json:
                        schema:
                            CompressionStatsSchema
        """
        try:
            json_request = self.read_json_request(RequestCompressionStatsSchema())

            validate_library_exists(json_request.get('library_id'))

            params = {
                'start':        json_request.get('start', 0),
                'length':       json_request.get('length', 10),
                'search_value': json_request.get('search_value', ''),
                'library_id':   json_request.get('library_id'),
                'order':        {
                    "column": json_request.get('order_by', 'finish_time'),
                    "dir":    json_request.get('order_direction', 'desc'),
                }
            }
            stats = compression_stats.get_compression_stats_paginated(params)

            response = self.build_response(
                CompressionStatsSchema(),
                {
                    "success":         True,
                    "recordsTotal":    stats.get('recordsTotal', 0),
                    "recordsFiltered": stats.get('recordsFiltered', 0),
                    "results":         stats.get('results', []),
                }
            )
            self.write_success(response)
            return
        except ValueError as ve:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(ve))
            self.write_error()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_compression_summary(self):
        """
        Compression - summary
        ---
        description: Returns library-wide compression summary statistics.
        responses:
            200:
                description: 'Returns compression summary.'
                content:
                    application/json:
                        schema:
                            CompressionSummarySchema
        """
        try:
            library_id = self._parse_library_id_arg()
            validate_library_exists(library_id)
            summary = compression_stats.get_compression_summary(library_id=library_id)

            response = self.build_response(
                CompressionSummarySchema(),
                {
                    "success":                True,
                    "total_source_size":      summary.get('total_source_size', 0),
                    "total_destination_size": summary.get('total_destination_size', 0),
                    "file_count":            summary.get('file_count', 0),
                    "avg_ratio":             summary.get('avg_ratio', 0),
                    "space_saved":           summary.get('space_saved', 0),
                    "per_library":           summary.get('per_library', []),
                }
            )
            self.write_success(response)
            return
        except ValueError as ve:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(ve))
            self.write_error()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_pending_estimate(self):
        """
        Compression - pending estimate
        ---
        description: Returns estimated savings for pending queue based on historical compression ratio.
        responses:
            200:
                description: 'Returns pending estimate data.'
                content:
                    application/json:
                        schema:
                            PendingEstimateSchema
        """
        try:
            estimate = compression_stats.get_pending_estimate()

            response = self.build_response(
                PendingEstimateSchema(),
                {
                    "success":              True,
                    "pending_count":        estimate.get('pending_count', 0),
                    "total_pending_size":   estimate.get('total_pending_size', 0),
                    "estimated_output_size": estimate.get('estimated_output_size', 0),
                    "estimated_savings":    estimate.get('estimated_savings', 0),
                    "avg_ratio_used":       estimate.get('avg_ratio_used', 1.0),
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

    def _parse_library_id_arg(self):
        """Parse optional library_id from query string."""
        library_id = self.get_argument('library_id', None)
        if library_id is not None:
            try:
                return int(library_id)
            except (ValueError, TypeError):
                return None
        return None

    async def get_codec_distribution(self):
        """
        Compression - codec distribution
        ---
        description: Returns codec distribution data for charts.
        responses:
            200:
                description: 'Returns codec distribution.'
                content:
                    application/json:
                        schema:
                            CodecDistributionSchema
        """
        try:
            library_id = self._parse_library_id_arg()
            validate_library_exists(library_id)
            data = compression_stats.get_codec_distribution(library_id=library_id)

            response = self.build_response(
                CodecDistributionSchema(),
                {
                    "success":             True,
                    "source_codecs":       data.get('source_codecs', []),
                    "destination_codecs":  data.get('destination_codecs', []),
                }
            )
            self.write_success(response)
            return
        except ValueError as ve:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(ve))
            self.write_error()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_resolution_distribution(self):
        """
        Compression - resolution distribution
        ---
        description: Returns resolution distribution data for charts.
        responses:
            200:
                description: 'Returns resolution distribution.'
                content:
                    application/json:
                        schema:
                            ResolutionDistributionSchema
        """
        try:
            library_id = self._parse_library_id_arg()
            validate_library_exists(library_id)
            data = compression_stats.get_resolution_distribution(library_id=library_id)

            response = self.build_response(
                ResolutionDistributionSchema(),
                {
                    "success":      True,
                    "resolutions":  data,
                }
            )
            self.write_success(response)
            return
        except ValueError as ve:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(ve))
            self.write_error()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_container_distribution(self):
        """
        Compression - container distribution
        ---
        description: Returns container distribution data for charts.
        responses:
            200:
                description: 'Returns container distribution.'
                content:
                    application/json:
                        schema:
                            ContainerDistributionSchema
        """
        try:
            library_id = self._parse_library_id_arg()
            validate_library_exists(library_id)
            data = compression_stats.get_container_distribution(library_id=library_id)

            response = self.build_response(
                ContainerDistributionSchema(),
                {
                    "success":                True,
                    "source_containers":      data.get('source_containers', []),
                    "destination_containers": data.get('destination_containers', []),
                }
            )
            self.write_success(response)
            return
        except ValueError as ve:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(ve))
            self.write_error()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_timeline(self):
        """
        Compression - space saved timeline
        ---
        description: Returns space saved over time for charting.
        responses:
            200:
                description: 'Returns timeline data.'
                content:
                    application/json:
                        schema:
                            TimelineSchema
        """
        try:
            library_id = self._parse_library_id_arg()
            validate_library_exists(library_id)
            interval = self.get_argument('interval', 'day')
            if interval not in ('day', 'week', 'month'):
                interval = 'day'

            data = compression_stats.get_space_saved_over_time(library_id=library_id, interval=interval)

            response = self.build_response(
                TimelineSchema(),
                {
                    "success": True,
                    "data":    data,
                }
            )
            self.write_success(response)
            return
        except ValueError as ve:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(ve))
            self.write_error()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
