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
