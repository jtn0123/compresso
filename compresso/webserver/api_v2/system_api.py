#!/usr/bin/env python3

"""
compresso.system_api.py

Written by:               Justin
Date:                     19 Mar 2026

Exposes system-level metrics (CPU, RAM, disk, GPU, platform) via REST.
"""

import shutil
import time
from collections.abc import Mapping
from datetime import UTC, datetime

import psutil

from compresso import config
from compresso.libs import session
from compresso.libs.foreman import Foreman
from compresso.libs.gpu_monitor import GpuMonitor
from compresso.libs.operations_status import OperationsStatus
from compresso.libs.safety_state import SafetyState
from compresso.libs.system import System
from compresso.libs.uiserver import CompressoDataQueues, CompressoRunningThreads, DataQueues
from compresso.libs.worker_capabilities import WorkerCapabilities
from compresso.ops.doctor import load_latest_report
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler, string_value
from compresso.webserver.api_v2.schema.system_schemas import SafetyAcknowledgeRequestSchema, SystemStatusSuccessSchema


class ApiSystemHandler(BaseApiHandler):
    session: session.Session
    config: config.Config
    params: object
    compresso_data_queues: DataQueues
    foreman: Foreman | None

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
        {
            "path_pattern": r"/system/capabilities",
            "supported_methods": ["GET"],
            "call_method": "get_worker_capabilities",
        },
        {
            "path_pattern": r"/system/operations",
            "supported_methods": ["GET"],
            "call_method": "get_operations_status",
        },
        {
            "path_pattern": r"/system/readiness",
            "supported_methods": ["GET"],
            "call_method": "get_readiness",
        },
        {
            "path_pattern": r"/system/safety",
            "supported_methods": ["GET"],
            "call_method": "get_safety",
        },
        {
            "path_pattern": r"/system/safety/acknowledge",
            "supported_methods": ["POST"],
            "call_method": "acknowledge_safety",
        },
        {
            "path_pattern": r"/system/safety/resume",
            "supported_methods": ["POST"],
            "call_method": "resume_safety",
        },
    ]

    def initialize(self, **kwargs: object) -> None:
        self.session = session.Session()
        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()
        self.foreman = CompressoRunningThreads().get_compresso_running_thread("foreman")
        self.config = config.Config()

    async def get_system_status(self) -> None:
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
            devices_value = system_info.get("devices", {})
            devices = devices_value if isinstance(devices_value, Mapping) else {}
            cpu_info_value = devices.get("cpu_info", {})
            cpu_info = cpu_info_value if isinstance(cpu_info_value, Mapping) else {}
            cpu_brand = string_value(cpu_info.get("brand_raw"), "Unknown")

            mem = psutil.virtual_memory()

            disk = psutil.disk_usage("/")

            gpu_value = devices.get("gpu_info", [])
            gpu_list = gpu_value if isinstance(gpu_value, list) else []

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
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_gpu_metrics(self) -> None:
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
            self.handle_unhandled_error(e)

    async def get_worker_capabilities(self) -> None:
        """
        System - worker capabilities
        ---
        description: Return hardware, encoder, and current-capacity data for scheduling.
        responses:
            200:
                description: Current worker capabilities.
                content:
                    application/json:
                        schema:
                            type: object
                            additionalProperties: true
        """
        try:
            self.write_success(WorkerCapabilities().snapshot(self.config))
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_operations_status(self) -> None:
        """
        System - operations
        ---
        description: Return queue, worker, transfer, checkpoint, and disk-pressure counters.
        responses:
            200:
                description: Current operational counters.
                content:
                    application/json:
                        schema:
                            type: object
                            additionalProperties: true
        """
        try:
            self.write_success(
                OperationsStatus().snapshot(
                    self.config,
                    foreman=self.foreman,
                    data_queues=self.compresso_data_queues,
                )
            )
        except Exception as e:
            self.handle_unhandled_error(e)

    def _safety_store(self) -> SafetyState:
        return SafetyState(self.config.get_userdata_path())

    async def get_safety(self) -> None:
        """
        System - safety
        ---
        description: Return the persistent safety latch and its bounded event history.
        responses:
            200:
                description: Current safety state.
                content:
                    application/json:
                        schema:
                            type: object
                            additionalProperties: true
        """
        try:
            self.write_success(self._safety_store().snapshot())
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_readiness(self) -> None:
        """
        System - readiness
        ---
        description: Combine the latest deployment-doctor evidence with the safety latch.
        responses:
            200:
                description: Current deployment readiness and safety evidence.
                content:
                    application/json:
                        schema:
                            type: object
                            additionalProperties: true
        """
        try:
            report = load_latest_report(self.config.get_userdata_path())
            expired = None
            if report is not None:
                try:
                    expires_at = datetime.fromisoformat(str(report["expires_at"]).replace("Z", "+00:00"))
                    expired = expires_at.astimezone(UTC) <= datetime.now(UTC)
                except (KeyError, TypeError, ValueError):
                    expired = True
            safety = self._safety_store().snapshot()
            ready = bool(
                report and report.get("overall_status") == "pass" and expired is False and not safety.get("pause_required")
            )
            self.write_success(
                {
                    "ready": ready,
                    "doctor_report": report,
                    "doctor_report_expired": expired,
                    "safety": safety,
                }
            )
        except Exception as e:
            self.handle_unhandled_error(e)

    async def acknowledge_safety(self) -> None:
        """
        System - acknowledge safety
        ---
        description: Record that an operator investigated and resolved a safety event.
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        SafetyAcknowledgeRequestSchema
        responses:
            200:
                description: Updated safety state.
                content:
                    application/json:
                        schema:
                            type: object
                            additionalProperties: true
        """
        try:
            request = self.read_json_request(SafetyAcknowledgeRequestSchema())
            actor = string_value(request.get("actor"), "operator") or "operator"
            store = self._safety_store()
            event = store.acknowledge(string_value(request["event_id"]), actor=actor)
            if event.get("active"):
                store.clear(string_value(event.get("code")), resolution=f"Acknowledged as resolved by {actor}")
            self.write_success(store.snapshot())
        except KeyError as exc:
            self.handle_base_api_error(BaseApiError("Unknown safety event", status_code=404, private_detail=str(exc)))
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as e:
            self.handle_unhandled_error(e)

    async def resume_safety(self) -> None:
        """
        System - resume after safety pause
        ---
        description: Recheck local capacity, release the latch, then resume local workers.
        responses:
            200:
                description: Updated safety state after the release attempt.
                content:
                    application/json:
                        schema:
                            type: object
                            additionalProperties: true
        """
        try:
            store = self._safety_store()
            minimum_free = float(self.config.get_minimum_free_space_gb()) * 1024**3
            cache_path = self.config.get_cache_path()
            free_bytes = shutil.disk_usage(cache_path).free
            if free_bytes < minimum_free:
                store.trigger(
                    "disk-reserve",
                    "Cache disk free space is below the configured reserve",
                    details={"free_bytes": free_bytes, "required_bytes": int(minimum_free)},
                )
                if self.foreman is not None:
                    self.foreman.safety_latched = True
                    self.foreman.pause_all_worker_threads(record_paused=True)
                raise BaseApiError(
                    "Safety recheck failed",
                    messages={"disk_reserve": ["Cache disk free space remains below the configured reserve"]},
                    status_code=409,
                )

            snapshot = store.snapshot()
            events_value = snapshot.get("events", [])
            events = [event for event in events_value if isinstance(event, Mapping)] if isinstance(events_value, list) else []
            active_disk = next(
                (event for event in events if event.get("code") == "disk-reserve" and event.get("active")), None
            )
            if active_disk and active_disk.get("acknowledged_at"):
                store.clear("disk-reserve", resolution="Cache disk reserve recheck passed")

            allowed, reasons = store.can_release()
            if not allowed:
                raise BaseApiError(
                    "Safety pause cannot be released",
                    messages={"safety": reasons},
                    status_code=409,
                )
            result = store.release_pause()
            if self.foreman is not None:
                self.foreman.safety_latched = False
                if not self.foreman.resume_all_worker_threads(recorded_paused_only=True):
                    self.foreman.safety_latched = True
                    store.trigger("worker-resume-failure", "One or more workers could not be resumed")
                    raise BaseApiError("Workers could not be resumed", status_code=409)
            self.write_success(result)
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as e:
            self.handle_unhandled_error(e)
