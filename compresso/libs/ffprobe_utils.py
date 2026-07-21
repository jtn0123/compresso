#!/usr/bin/env python3

"""
compresso.ffprobe_utils.py

Shared ffprobe utility for probing media files.
Used by File Info, Health Check, and other features.

"""

import contextlib
import json
import os
import re
import subprocess
from typing import TypedDict

from compresso.libs import narrowing
from compresso.libs.logs import CompressoLogging

logger = CompressoLogging.get_logger("ffprobe_utils")


class MediaMetadata(TypedDict):
    codec: str
    resolution: str
    container: str
    duration: float
    bitrate_mbps: float


class QualityScores(TypedDict):
    vmaf_score: float | None
    ssim_score: float | None


def _to_float(value: object) -> float:
    if isinstance(value, (str, bytes, int, float)):
        return float(value or 0)
    return 0.0


def _to_int(value: object) -> int:
    if isinstance(value, (str, bytes, int, float)):
        return int(value or 0)
    return 0


def probe_file(filepath: str | os.PathLike[str], timeout: float = 30) -> dict[str, object] | None:
    """
    Run ffprobe on a file and return parsed JSON output.

    :param filepath: Absolute path to the media file
    :param timeout: Timeout in seconds
    :return: dict with ffprobe output (format + streams), or None on failure
    """
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        filepath,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)  # noqa: S603 - trusted ffprobe command built internally
        if result.returncode != 0:
            logger.warning("ffprobe failed for %s: %s", filepath, result.stderr[:500] if result.stderr else "")
            return None
        return narrowing.string_keyed_dict_or_none(json.loads(result.stdout))
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out for %s", filepath)
        return None
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.warning("ffprobe parse error for %s: %s", filepath, str(e))
        return None


CONTAINER_CODEC_HINTS = {
    "mp4": "h264",
    "mkv": "h264",
    "webm": "vp9",
    "avi": "mpeg4",
    "m4v": "h264",
    "mov": "h264",
    "ts": "h264",
    "flv": "h264",
}


def extract_media_metadata(filepath: str | os.PathLike[str]) -> MediaMetadata:
    """
    Extract codec, resolution, and container metadata from a media file.

    :param filepath: Absolute path to the media file
    :return: dict with 'codec', 'resolution', 'container' keys
    """
    result = MediaMetadata(codec="", resolution="", container="", duration=0.0, bitrate_mbps=0.0)

    # Container from file extension
    ext = os.path.splitext(filepath)[1].lower().lstrip(".")
    if ext:
        result["container"] = ext

    probe_data = probe_file(filepath, timeout=30)
    if not probe_data:
        # Fallback: estimate codec from container extension
        hint = CONTAINER_CODEC_HINTS.get(ext, "")
        if hint:
            result["codec"] = f"{hint} (estimated)"
        return result

    # Extract duration from format level
    format_info = narrowing.string_keyed_dict_or_none(probe_data.get("format")) or {}
    with contextlib.suppress(TypeError, ValueError):
        result["duration"] = _to_float(format_info.get("duration"))
    with contextlib.suppress(TypeError, ValueError):
        result["bitrate_mbps"] = _to_float(format_info.get("bit_rate")) / 1000000

    raw_streams = probe_data.get("streams")
    streams = raw_streams if isinstance(raw_streams, list) else []
    video_stream = next(
        (
            stream
            for raw_stream in streams
            if (stream := narrowing.string_keyed_dict_or_none(raw_stream)) is not None and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video_stream is not None:
        codec_name = video_stream.get("codec_name")
        result["codec"] = codec_name if isinstance(codec_name, str) else ""
        result["resolution"] = _resolution_from_height(_to_int(video_stream.get("height")))

    return result


def _resolution_from_height(height: int) -> str:
    for threshold, label in ((2160, "4K"), (1440, "1440p"), (1080, "1080p"), (720, "720p"), (480, "480p")):
        if height >= threshold:
            return label
    return f"{height}p" if height > 0 else ""


def compute_quality_scores(
    source_path: str | os.PathLike[str],
    encoded_path: str | os.PathLike[str],
    duration_limit: float = 30,
) -> QualityScores:
    """
    Compare source and encoded files using SSIM and VMAF quality metrics.
    Limits comparison to the first `duration_limit` seconds for performance.

    :param source_path: Path to the original/reference video
    :param encoded_path: Path to the encoded/distorted video
    :param duration_limit: Max seconds to compare (0 = full file)
    :return: dict with 'vmaf_score' (float|None) and 'ssim_score' (float|None)
    """
    scores = QualityScores(vmaf_score=None, ssim_score=None)

    time_limit_args = ["-t", str(duration_limit)] if duration_limit > 0 else []

    # Try SSIM first (more widely available)
    try:
        ssim_cmd = (
            ["ffmpeg", "-y"]
            + time_limit_args
            + ["-i", encoded_path]
            + time_limit_args
            + ["-i", source_path]
            + ["-lavfi", "[0:v][1:v]ssim", "-f", "null", "-"]
        )
        result = subprocess.run(ssim_cmd, capture_output=True, text=True, timeout=120)  # noqa: S603 - trusted ffmpeg command built internally
        if result.returncode == 0 and result.stderr:
            match = re.search(r"All:(\d+(?:\.\d+)?)", result.stderr)
            if match:
                scores["ssim_score"] = float(match.group(1))
    except subprocess.TimeoutExpired:
        logger.debug("SSIM computation timed out for %s", encoded_path)
    except Exception as e:
        logger.debug("SSIM computation failed for %s: %s", encoded_path, str(e))

    # Try VMAF (requires libvmaf filter in FFmpeg)
    try:
        vmaf_cmd = (
            ["ffmpeg", "-y"]
            + time_limit_args
            + ["-i", encoded_path]
            + time_limit_args
            + ["-i", source_path]
            + ["-lavfi", "[0:v][1:v]libvmaf", "-f", "null", "-"]
        )
        result = subprocess.run(vmaf_cmd, capture_output=True, text=True, timeout=300)  # noqa: S603 - trusted ffmpeg command built internally
        if result.returncode == 0 and result.stderr:
            match = re.search(r"VMAF score:\s*(\d+(?:\.\d+)?)", result.stderr)
            if not match:
                match = re.search(r"vmaf_score:\s*(\d+(?:\.\d+)?)", result.stderr)
            if match:
                scores["vmaf_score"] = float(match.group(1))
    except subprocess.TimeoutExpired:
        logger.debug("VMAF computation timed out for %s", encoded_path)
    except Exception as e:
        logger.debug("VMAF computation failed for %s (libvmaf may not be available): %s", encoded_path, str(e))

    return scores
