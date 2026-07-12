#!/usr/bin/env python3

import math
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.worker_capabilities import WorkerCapabilities


@pytest.mark.unittest
def test_snapshot_detects_platform_encoders_storage_and_current_capacity():
    settings = MagicMock()
    settings.get_cache_path.return_value = "/cache"
    info = MagicMock()
    info.get_ffmpeg_video_encoders.return_value = {
        "libx265": {},
        "hevc_videotoolbox": {},
    }
    info.get_available_ffmpeg_hw_acceleration_methods.return_value = ["videotoolbox"]
    probe = WorkerCapabilities(ffmpeg_info=info)

    with (
        patch("compresso.libs.worker_capabilities.platform.system", return_value="Darwin"),
        patch("compresso.libs.worker_capabilities.platform.machine", return_value="arm64"),
        patch("compresso.libs.worker_capabilities.psutil.cpu_count", return_value=10),
        patch("compresso.libs.worker_capabilities.psutil.cpu_percent", return_value=20.0),
        patch(
            "compresso.libs.worker_capabilities.psutil.virtual_memory",
            return_value=SimpleNamespace(total=16 * 1024**3, available=8 * 1024**3, percent=50.0),
        ),
        patch(
            "compresso.libs.worker_capabilities.shutil.disk_usage",
            return_value=SimpleNamespace(total=512 * 1024**3, free=300 * 1024**3),
        ),
    ):
        snapshot = probe.snapshot(settings)

    assert snapshot["platform"] == {"system": "Darwin", "machine": "arm64"}
    assert "hevc_videotoolbox" in snapshot["video_encoders"]
    assert snapshot["hardware_accelerators"] == ["videotoolbox"]
    assert snapshot["cpu"]["count"] == 10
    assert snapshot["memory"]["available_bytes"] == 8 * 1024**3
    assert snapshot["cache_disk"]["free_bytes"] == 300 * 1024**3


@pytest.mark.unittest
def test_score_rejects_installation_without_required_encoder():
    capabilities = {
        "video_encoders": ["libx265"],
        "cpu": {"percent": 10},
        "memory": {"percent": 20},
        "cache_disk": {"free_bytes": 100 * 1024**3},
    }

    assert WorkerCapabilities.scheduling_score(capabilities, required_encoder="hevc_videotoolbox") is None


@pytest.mark.unittest
def test_score_prefers_lower_load_and_more_free_storage():
    low_load = {
        "video_encoders": ["hevc_videotoolbox"],
        "cpu": {"percent": 10},
        "memory": {"percent": 20},
        "cache_disk": {"free_bytes": 300 * 1024**3},
    }
    high_load = {
        "video_encoders": ["hevc_videotoolbox"],
        "cpu": {"percent": 90},
        "memory": {"percent": 80},
        "cache_disk": {"free_bytes": 20 * 1024**3},
    }

    assert WorkerCapabilities.scheduling_score(low_load, "hevc_videotoolbox") > WorkerCapabilities.scheduling_score(
        high_load, "hevc_videotoolbox"
    )


@pytest.mark.unittest
def test_score_prefers_measured_throughput_for_otherwise_equal_workers():
    baseline = {
        "video_encoders": ["hevc_videotoolbox"],
        "cpu": {"percent": 20},
        "memory": {"percent": 20},
        "cache_disk": {"free_bytes": 100 * 1024**3},
        "thermal": {"state": "nominal"},
    }
    fast = {**baseline, "performance": {"tasks_per_hour": 12}}
    unknown = {**baseline, "performance": {"tasks_per_hour": 0}}

    assert WorkerCapabilities.scheduling_score(fast) > WorkerCapabilities.scheduling_score(unknown)


@pytest.mark.unittest
def test_score_throttles_hot_or_critical_workers():
    baseline = {
        "video_encoders": ["hevc_videotoolbox"],
        "cpu": {"percent": 20},
        "memory": {"percent": 20},
        "cache_disk": {"free_bytes": 100 * 1024**3},
        "performance": {"tasks_per_hour": 8},
    }
    nominal = {**baseline, "thermal": {"state": "nominal"}}
    hot = {**baseline, "thermal": {"state": "hot"}}

    assert WorkerCapabilities.scheduling_score(hot) < WorkerCapabilities.scheduling_score(nominal)


@pytest.mark.unittest
def test_performance_snapshot_uses_persisted_recent_encode_samples():
    query = MagicMock()
    query.join.return_value = query
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = [
        SimpleNamespace(
            encoding_duration_seconds=600,
            source_duration_seconds=1200,
            destination_codec="hevc",
        ),
        SimpleNamespace(
            encoding_duration_seconds=1200,
            source_duration_seconds=1200,
            destination_codec="hevc",
        ),
    ]

    with patch("compresso.libs.worker_capabilities.CompressionStats.select", return_value=query):
        performance = WorkerCapabilities._performance_snapshot()

    assert performance["sample_count"] == 2
    assert performance["tasks_per_hour"] == 4.5
    assert performance["media_speed_ratio"] == 1.5
    assert performance["by_codec"]["hevc"]["sample_count"] == 2


@pytest.mark.unittest
def test_thermal_snapshot_reports_hottest_sensor_state():
    sensors = {
        "cpu": [SimpleNamespace(current=72.0), SimpleNamespace(current=88.0)],
    }
    with patch(
        "compresso.libs.worker_capabilities.psutil.sensors_temperatures", return_value=sensors, create=True
    ):
        thermal = WorkerCapabilities._thermal_snapshot()

    assert thermal == {"state": "hot", "max_celsius": 88.0}


@pytest.mark.unittest
@pytest.mark.parametrize("bad_value", [None, "", "nan", "inf", {}, [], float("nan"), float("inf")])
def test_score_fails_closed_for_malformed_remote_capacity_values(bad_value):
    capabilities = {
        "video_encoders": ["libx265"],
        "cpu": {"percent": bad_value},
        "memory": {"percent": bad_value},
        "cache_disk": {"free_bytes": bad_value},
    }

    score = WorkerCapabilities.scheduling_score(capabilities, "libx265")

    assert score is not None
    assert math.isfinite(score)
    assert score >= 0


@pytest.mark.unittest
def test_score_rejects_non_collection_encoder_payload_for_required_encoder():
    capabilities = {
        "video_encoders": "prefix-hevc_videotoolbox-suffix",
        "cpu": {"percent": 0},
        "memory": {"percent": 0},
        "cache_disk": {"free_bytes": 1},
    }

    assert WorkerCapabilities.scheduling_score(capabilities, "hevc_videotoolbox") is None
