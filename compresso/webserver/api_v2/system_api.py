#!/usr/bin/env python3

"""
compresso.system_api.py

Written by:               Justin
Date:                     19 Mar 2026

Exposes system-level metrics (CPU, RAM, disk, GPU, platform) via REST.
"""

import time

import psutil
import tornado.log

from compresso import config
from compresso.libs import session
from compresso.libs.gpu_monitor import GpuMonitor
from compresso.libs.system import System
from compresso.libs.uiserver import CompressoDataQueues
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.schemas import SystemStatusSuccessSchema


class ApiSystemHandler(BaseApiHandler):
    session = None
    config = None
    params = None
    compresso_data_queues = None

    routes = [
        {
            "path_pattern": r"/system/status",
            "supported_methods": ["GET"],
            "call_method": "get_system_status",
        },
        {
            "path_pattern": r"/system/gpu-metrics",
            "supported_methods": ["GET"],
            "call_method": "get_gpu_metrics",
        },
    ]

    def initialize(self, **kwargs):
        self.session = session.Session()
        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()
        self.config = config.Config()

    async def get_system_status(self):
        """
        System - status
        ---
        description: Returns system-level metrics including CPU, memory, disk, GPU, and platform info.
        responses:
            200:
                description: 'Sample response: Returns system status metrics.'
                content:
                    application/json:
                        schema:
                            SystemStatusSuccessSchema
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
            system = System()
            system_info = system.info()

            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            cpu_brand = system_info.get("devices", {}).get("cpu_info", {}).get("brand_raw", "Unknown")

            mem = psutil.virtual_memory()

            disk = psutil.disk_usage("/")

            gpu_list = system_info.get("devices", {}).get("gpu_info", [])

            platform_info = system_info.get("platform", {})
            platform_data = {
                "system": getattr(platform_info, "system", str(platform_info)),
                "node": getattr(platform_info, "node", ""),
                "release": getattr(platform_info, "release", ""),
            }

            uptime_seconds = int(time.time() - psutil.boot_time())

            data = {
                "cpu": {
                    "count": cpu_count,
                    "percent": cpu_percent,
                    "brand": cpu_brand,
                },
                "memory": {
                    "total_gb": round(mem.total / (1024**3), 1),
                    "used_gb": round(mem.used / (1024**3), 1),
                    "percent": mem.percent,
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 1),
                    "used_gb": round(disk.used / (1024**3), 1),
                    "percent": disk.percent,
                    "path": "/",
                },
                "gpus": gpu_list,
                "platform": platform_data,
                "uptime_seconds": uptime_seconds,
            }

            response = self.build_response(
                SystemStatusSuccessSchema(),
                data,
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get("call_method"), str(bae)))
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            tornado.log.app_log.exception("Unhandled error in %s.%s", self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def get_gpu_metrics(self):
        """
        System - gpu-metrics
        ---
        description: Returns real-time GPU utilization metrics and rolling history.
        responses:
            200:
                description: 'Sample response: Returns GPU metrics and history.'
                content:
                    application/json:
                        schema:
                            SystemStatusSuccessSchema
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
            gpu_monitor = GpuMonitor()
            data = {
                "gpus": gpu_monitor.get_realtime_metrics(),
                "history": gpu_monitor.get_history(),
            }
            self.write_success(data)
            return
        except Exception as e:
            tornado.log.app_log.exception("Unhandled error in %s.%s", self.__class__.__name__, self.route.get("call_method"))
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
