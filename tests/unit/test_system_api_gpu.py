#!/usr/bin/env python3

"""
tests.unit.test_system_api_gpu.py

Unit tests for the system API GPU metrics endpoint:
- GET /system/gpu-metrics returns gpus and history
"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType

SYSTEM_API_MOD = "compresso.webserver.api_v2.system_api"


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


# ------------------------------------------------------------------
# TestGpuMetricsEndpoint
# ------------------------------------------------------------------


@pytest.mark.unittest
class TestGpuMetricsEndpoint:
    """Tests for the GET /system/gpu-metrics handler."""

    @pytest.mark.asyncio
    async def test_returns_gpus_and_history(self):
        from compresso.webserver.api_v2.system_api import ApiSystemHandler

        handler = object.__new__(ApiSystemHandler)

        gpu_data = [
            {
                "index": 0,
                "type": "nvidia",
                "name": "RTX 3080",
                "utilization_percent": 55.0,
                "memory_used_mb": 2048,
                "memory_total_mb": 10240,
                "temperature_c": 72,
            },
        ]
        history_data = {
            0: [
                {
                    "utilization_percent": 50.0,
                    "memory_used_mb": 2000,
                    "memory_total_mb": 10240,
                    "temperature_c": 70,
                    "timestamp": 1000,
                },
                {
                    "utilization_percent": 55.0,
                    "memory_used_mb": 2048,
                    "memory_total_mb": 10240,
                    "temperature_c": 72,
                    "timestamp": 1001,
                },
            ],
        }

        written_data = {}

        def mock_write_success(data=None):
            written_data.update(data or {})

        handler.write_success = mock_write_success

        with patch(f"{SYSTEM_API_MOD}.GpuMonitor") as mock_gpu_cls:
            mock_monitor = MagicMock()
            mock_monitor.get_realtime_metrics.return_value = gpu_data
            mock_monitor.get_history.return_value = history_data
            mock_gpu_cls.return_value = mock_monitor

            await handler.get_gpu_metrics()

        assert "gpus" in written_data
        assert "history" in written_data
        assert len(written_data["gpus"]) == 1
        assert written_data["gpus"][0]["name"] == "RTX 3080"
        assert 0 in written_data["history"]
        assert len(written_data["history"][0]) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_gpus(self):
        from compresso.webserver.api_v2.system_api import ApiSystemHandler

        handler = object.__new__(ApiSystemHandler)

        written_data = {}

        def mock_write_success(data=None):
            written_data.update(data or {})

        handler.write_success = mock_write_success

        with patch(f"{SYSTEM_API_MOD}.GpuMonitor") as mock_gpu_cls:
            mock_monitor = MagicMock()
            mock_monitor.get_realtime_metrics.return_value = []
            mock_monitor.get_history.return_value = {}
            mock_gpu_cls.return_value = mock_monitor

            await handler.get_gpu_metrics()

        assert written_data["gpus"] == []
        assert written_data["history"] == {}

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        from compresso.webserver.api_v2.system_api import ApiSystemHandler

        handler = object.__new__(ApiSystemHandler)
        handler.route = {"call_method": "get_gpu_metrics"}
        handler.STATUS_ERROR_INTERNAL = 500
        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.write_success = MagicMock()

        with patch(f"{SYSTEM_API_MOD}.GpuMonitor") as mock_gpu_cls:
            mock_gpu_cls.side_effect = RuntimeError("GPU monitor init failed")

            await handler.get_gpu_metrics()

        handler.write_error.assert_called_once()
        handler.write_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_gpu_monitor_methods(self):
        from compresso.webserver.api_v2.system_api import ApiSystemHandler

        handler = object.__new__(ApiSystemHandler)
        handler.write_success = MagicMock()

        with patch(f"{SYSTEM_API_MOD}.GpuMonitor") as mock_gpu_cls:
            mock_monitor = MagicMock()
            mock_monitor.get_realtime_metrics.return_value = []
            mock_monitor.get_history.return_value = {}
            mock_gpu_cls.return_value = mock_monitor

            await handler.get_gpu_metrics()

        mock_monitor.get_realtime_metrics.assert_called_once()
        mock_monitor.get_history.assert_called_once()


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
