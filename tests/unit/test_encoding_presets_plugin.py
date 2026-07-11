#!/usr/bin/env python3

from unittest.mock import MagicMock, patch

import pytest

from compresso.bundled_plugins.encoding_presets import plugin


def _build_command(settings):
    data = {
        "library_id": 1,
        "file_in": "/media/movie.mkv",
        "file_out": "/cache/fallback.mkv",
        "worker_log": [],
        "current_command": [],
    }
    configured = {
        "video_codec": "hevc",
        "video_encoder": "",
        "crf": 23,
        "encoder_preset": "medium",
        "max_bitrate": "",
        "scale_height": 0,
        "audio_codec": "",
        "audio_bitrate": "",
        "output_format": "mp4",
        "extra_flags": "",
    }
    configured.update(settings)

    with (
        patch.object(plugin, "Settings") as settings_class,
        patch.object(plugin, "_build_ffmpeg_progress_parser", return_value=MagicMock()),
    ):
        settings_class.return_value.settings_configured = configured
        plugin.on_worker_process(data)
    return data["exec_command"]


@pytest.mark.unittest
def test_videotoolbox_maps_crf_to_native_quality_and_skips_software_preset():
    command = _build_command({"video_encoder": "hevc_videotoolbox", "crf": 23})

    assert command[command.index("-q:v") + 1] == "64"
    assert "-crf" not in command
    assert "-preset" not in command


@pytest.mark.unittest
def test_videotoolbox_uses_target_bitrate_when_cap_is_configured():
    command = _build_command({"video_encoder": "hevc_videotoolbox", "max_bitrate": "15M"})

    assert command[command.index("-b:v") + 1] == "15M"
    assert command[command.index("-maxrate") + 1] == "15M"


@pytest.mark.unittest
def test_software_encoder_keeps_crf_and_preset_behavior():
    command = _build_command({"video_encoder": "libx265", "crf": 20, "encoder_preset": "slow"})

    assert command[command.index("-crf") + 1] == "20"
    assert command[command.index("-preset") + 1] == "slow"
    assert "-q:v" not in command


@pytest.mark.unittest
def test_command_preserves_all_streams_metadata_chapters_and_subtitles():
    command = _build_command({"output_format": "mkv"})

    assert command[command.index("-map") + 1] == "0"
    assert command[command.index("-map_metadata") + 1] == "0"
    assert command[command.index("-map_chapters") + 1] == "0"
    assert command[command.index("-c:s") + 1] == "copy"
    assert command[command.index("-c:d") + 1] == "copy"
    assert command[command.index("-c:t") + 1] == "copy"


@pytest.mark.unittest
@pytest.mark.parametrize(
    ("crf", "quality"),
    [(0, 100), (63, 1), (-10, 100), (100, 1)],
)
def test_videotoolbox_quality_mapping_is_bounded(crf, quality):
    assert plugin._videotoolbox_quality_from_crf(crf) == quality
