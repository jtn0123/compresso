#!/usr/bin/env python3

"""
compresso.fileinfo.py

Helper functions for the File Info API.
Formats ffprobe output into structured sections.

"""

from collections.abc import Mapping
from os import PathLike

from compresso.libs.ffprobe_utils import probe_file


def format_probe_data(probe_data: Mapping[str, object]) -> dict[str, object] | None:
    """
    Format raw ffprobe output into structured sections.

    :param probe_data: Raw ffprobe JSON dict
    :return: dict with video_streams, audio_streams, subtitle_streams, format
    """
    if not probe_data:
        return None

    streams_value = probe_data.get("streams", [])
    streams = streams_value if isinstance(streams_value, list) else []
    format_value = probe_data.get("format", {})
    fmt = format_value if isinstance(format_value, Mapping) else {}

    video_streams: list[dict[str, object]] = []
    audio_streams: list[dict[str, object]] = []
    subtitle_streams: list[dict[str, object]] = []

    for stream_value in streams:
        if not isinstance(stream_value, Mapping):
            continue
        stream = stream_value
        codec_type = stream.get("codec_type", "")
        info: dict[str, object] = {
            "index": stream.get("index", 0),
            "codec_name": stream.get("codec_name", ""),
            "codec_long_name": stream.get("codec_long_name", ""),
            "profile": stream.get("profile", ""),
        }

        if codec_type == "video":
            info.update(
                {
                    "width": stream.get("width", 0),
                    "height": stream.get("height", 0),
                    "pix_fmt": stream.get("pix_fmt", ""),
                    "bit_rate": _safe_int(stream.get("bit_rate")),
                    "r_frame_rate": stream.get("r_frame_rate", ""),
                    "avg_frame_rate": stream.get("avg_frame_rate", ""),
                    "duration": _safe_float(stream.get("duration")),
                    "nb_frames": _safe_int(stream.get("nb_frames")),
                    "color_space": stream.get("color_space", ""),
                    "color_transfer": stream.get("color_transfer", ""),
                    "color_primaries": stream.get("color_primaries", ""),
                    "hdr": _is_hdr(stream),
                }
            )
            # Resolution label
            height = _safe_int(stream.get("height", 0))
            if height >= 2160:
                info["resolution_label"] = "4K"
            elif height >= 1440:
                info["resolution_label"] = "1440p"
            elif height >= 1080:
                info["resolution_label"] = "1080p"
            elif height >= 720:
                info["resolution_label"] = "720p"
            elif height >= 480:
                info["resolution_label"] = "480p"
            else:
                info["resolution_label"] = f"{height}p" if height > 0 else ""
            video_streams.append(info)

        elif codec_type == "audio":
            info.update(
                {
                    "sample_rate": _safe_int(stream.get("sample_rate")),
                    "channels": stream.get("channels", 0),
                    "channel_layout": stream.get("channel_layout", ""),
                    "bit_rate": _safe_int(stream.get("bit_rate")),
                    "duration": _safe_float(stream.get("duration")),
                }
            )
            tags_value = stream.get("tags")
            tags = tags_value if isinstance(tags_value, Mapping) else {}
            info["language"] = tags.get("language", "")
            info["title"] = tags.get("title", "")
            audio_streams.append(info)

        elif codec_type == "subtitle":
            tags_value = stream.get("tags")
            tags = tags_value if isinstance(tags_value, Mapping) else {}
            info.update(
                {
                    "language": tags.get("language", ""),
                    "title": tags.get("title", ""),
                }
            )
            subtitle_streams.append(info)

    format_info = {
        "filename": fmt.get("filename", ""),
        "format_name": fmt.get("format_name", ""),
        "format_long_name": fmt.get("format_long_name", ""),
        "duration": _safe_float(fmt.get("duration")),
        "size": _safe_int(fmt.get("size")),
        "bit_rate": _safe_int(fmt.get("bit_rate")),
        "nb_streams": _safe_int(fmt.get("nb_streams")),
    }

    return {
        "video_streams": video_streams,
        "audio_streams": audio_streams,
        "subtitle_streams": subtitle_streams,
        "format": format_info,
    }


def probe_and_format(filepath: str | PathLike[str]) -> dict[str, object] | None:
    """
    Probe a file and return formatted info.

    :param filepath: Absolute path to the media file
    :return: dict with formatted file info, or None on failure
    """
    probe_data = probe_file(filepath)
    if not probe_data:
        return None
    return format_probe_data(probe_data)


def _is_hdr(stream: Mapping[str, object]) -> bool:
    """Check if a video stream is HDR based on color metadata."""
    transfer_value = stream.get("color_transfer", "")
    transfer = transfer_value.lower() if isinstance(transfer_value, str) else ""
    hdr_transfers = {"smpte2084", "arib-std-b67", "smpte428"}
    if transfer in hdr_transfers:
        return True
    # Secondary signal: BT.2020 color primaries suggest HDR content
    primaries_value = stream.get("color_primaries", "")
    primaries = primaries_value.lower() if isinstance(primaries_value, str) else ""
    return primaries == "bt2020"


def _safe_int(value: object) -> int:
    """Safely convert to int."""
    if value is None:
        return 0
    try:
        return int(value) if isinstance(value, (str, bytes, int, float)) else 0
    except (ValueError, TypeError):
        return 0


def _safe_float(value: object) -> float:
    """Safely convert to float."""
    if value is None:
        return 0.0
    try:
        return float(value) if isinstance(value, (str, bytes, int, float)) else 0.0
    except (ValueError, TypeError):
        return 0.0
