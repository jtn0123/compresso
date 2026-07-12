#!/usr/bin/env python3

"""
tests.unit.test_system_api.py

Tests for the system API handler endpoints.

"""

from collections import namedtuple
from unittest.mock import MagicMock, patch

import pytest

from compresso.webserver.api_v2.system_api import ApiSystemHandler
from tests.unit.api_test_base import ApiTestBase


def _mock_initialize(self, **kwargs):
    """Stub out ApiSystemHandler.initialize to avoid loading real session/config."""
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}
    self.config = MagicMock()
    self.foreman = MagicMock()


SYSTEM_API = "compresso.webserver.api_v2.system_api"


@pytest.mark.unittest
@patch.object(ApiSystemHandler, "initialize", _mock_initialize)
class TestSystemApiStatus(ApiTestBase):
    __test__ = True
    handler_class = ApiSystemHandler

    @patch(SYSTEM_API + ".time")
    @patch(SYSTEM_API + ".psutil")
    @patch(SYSTEM_API + ".System")
    def test_get_system_status_success(self, mock_system_cls, mock_psutil, mock_time):
        mock_system = MagicMock()
        PlatformInfo = namedtuple("PlatformInfo", ["system", "node", "release"])
        mock_system.info.return_value = {
            "devices": {
                "cpu_info": {"brand_raw": "Intel Core i7"},
                "gpu_info": [
                    {
                        "type": "nvidia",
                        "name": "NVIDIA GTX 1080",
                        "memory_total_mb": 8192,
                        "driver_version": "535.129.03",
                        "hwaccel": "cuda",
                        "index": 0,
                    },
                ],
            },
            "platform": PlatformInfo(system="Linux", node="myhost", release="5.15.0"),
        }
        mock_system_cls.return_value = mock_system

        mock_psutil.cpu_percent.return_value = 25.5
        mock_psutil.cpu_count.return_value = 8

        VirtualMemory = namedtuple("VirtualMemory", ["total", "used", "percent"])
        mock_psutil.virtual_memory.return_value = VirtualMemory(
            total=17179869184,
            used=8589934592,
            percent=50.0,
        )

        DiskUsage = namedtuple("DiskUsage", ["total", "used", "percent"])
        mock_psutil.disk_usage.return_value = DiskUsage(
            total=500107862016,
            used=250053931008,
            percent=50.0,
        )

        mock_psutil.boot_time.return_value = 1000.0
        mock_time.time.return_value = 87400.0

        resp = self.get_json("/system/status")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["cpu"]["count"] == 8
        assert data["cpu"]["brand"] == "Intel Core i7"
        assert data["memory"]["percent"] == 50.0
        assert data["disk"]["percent"] == 50.0
        assert data["uptime_seconds"] == 86400
        assert len(data["gpus"]) == 1
        assert data["gpus"][0]["hwaccel"] == "cuda"
        assert data["gpus"][0]["index"] == 0

    @patch(SYSTEM_API + ".time")
    @patch(SYSTEM_API + ".psutil")
    @patch(SYSTEM_API + ".System")
    def test_get_system_status_no_gpus(self, mock_system_cls, mock_psutil, mock_time):
        mock_system = MagicMock()
        PlatformInfo = namedtuple("PlatformInfo", ["system", "node", "release"])
        mock_system.info.return_value = {
            "devices": {
                "cpu_info": {"brand_raw": "AMD Ryzen"},
                "gpu_info": [],
            },
            "platform": PlatformInfo(system="Linux", node="myhost", release="5.15.0"),
        }
        mock_system_cls.return_value = mock_system

        mock_psutil.cpu_percent.return_value = 10.0
        mock_psutil.cpu_count.return_value = 16

        VirtualMemory = namedtuple("VirtualMemory", ["total", "used", "percent"])
        mock_psutil.virtual_memory.return_value = VirtualMemory(
            total=34359738368,
            used=17179869184,
            percent=50.0,
        )

        DiskUsage = namedtuple("DiskUsage", ["total", "used", "percent"])
        mock_psutil.disk_usage.return_value = DiskUsage(
            total=1000215724032,
            used=500107862016,
            percent=50.0,
        )

        mock_psutil.boot_time.return_value = 0.0
        mock_time.time.return_value = 3600.0

        resp = self.get_json("/system/status")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["gpus"] == []

    @patch(SYSTEM_API + ".System")
    def test_get_system_status_internal_error(self, mock_system_cls):
        mock_system_cls.side_effect = Exception("System info unavailable")
        resp = self.get_json("/system/status")
        assert resp.code == 500

    @patch(SYSTEM_API + ".WorkerCapabilities")
    def test_get_worker_capabilities(self, mock_capabilities_cls):
        mock_capabilities_cls.return_value.snapshot.return_value = {
            "platform": {"system": "Darwin", "machine": "arm64"},
            "video_encoders": ["hevc_videotoolbox"],
            "hardware_accelerators": ["videotoolbox"],
            "cpu": {"count": 10, "percent": 15.0},
            "memory": {"total_bytes": 16, "available_bytes": 8, "percent": 50.0},
            "cache_disk": {"path": "/cache", "total_bytes": 100, "free_bytes": 80},
        }

        resp = self.get_json("/system/capabilities")

        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["video_encoders"] == ["hevc_videotoolbox"]
        assert data["platform"]["machine"] == "arm64"

    @patch(SYSTEM_API + ".OperationsStatus")
    def test_get_operations_status(self, mock_status_cls):
        mock_status_cls.return_value.snapshot.return_value = {
            "tasks": {"pending": 2, "total": 2},
            "transfers": {"active": 1},
        }

        resp = self.get_json("/system/operations")

        assert resp.code == 200
        assert self.parse_response(resp)["tasks"]["pending"] == 2
