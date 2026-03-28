#!/usr/bin/env python3

"""
Encoding Presets Plugin

Configurable encoding quality controls for FFmpeg-based transcoding.
Supports CRF/quality, encoder preset, bitrate cap, resolution scaling,
and audio bitrate.
"""

import logging
import os
import re

from compresso.libs.unplugins.settings import PluginSettings

logger = logging.getLogger(__name__)


class Settings(PluginSettings):
    settings = {
        # Video codec — leave empty to use the source codec
        "video_codec": "",
        # Encoder — leave empty to auto-select based on codec
        "video_encoder": "",
        # CRF / quality value (0-51 for x264/x265, 0-63 for SVT-AV1/VP9)
        "crf": 23,
        # Encoder preset (speed/quality tradeoff)
        "encoder_preset": "medium",
        # Max video bitrate cap (e.g., "8000k", "15M"). Empty = no cap.
        "max_bitrate": "",
        # Resolution scaling — target height in pixels. 0 = no scaling.
        "scale_height": 0,
        # Audio codec — leave empty to copy audio
        "audio_codec": "",
        # Audio bitrate (e.g., "128k", "192k"). Empty = codec default.
        "audio_bitrate": "",
        # Output container format (e.g., "mkv", "mp4"). Empty = same as source.
        "output_format": "",
        # Extra FFmpeg output flags (advanced)
        "extra_flags": "",
    }

    form_settings = {
        "video_codec": {
            "label": "Video Codec",
            "description": "Target video codec. Leave empty to keep source codec.",
            "input_type": "select",
            "select_options": [
                {"value": "", "label": "Same as source"},
                {"value": "h264", "label": "H.264 (AVC)"},
                {"value": "hevc", "label": "H.265 (HEVC)"},
                {"value": "av1", "label": "AV1"},
                {"value": "vp9", "label": "VP9"},
            ],
        },
        "video_encoder": {
            "label": "Video Encoder",
            "description": "Specific encoder to use. Leave empty for auto-detection based on codec.",
            "input_type": "text",
            "placeholder": "e.g., libx265, libsvtav1, hevc_nvenc",
        },
        "crf": {
            "label": "Quality (CRF)",
            "description": "Constant Rate Factor. Lower = better quality, larger files. Typical: 18-28.",
            "input_type": "slider",
            "slider_min": 0,
            "slider_max": 63,
            "slider_step": 1,
        },
        "encoder_preset": {
            "label": "Encoder Preset",
            "description": "Speed/quality tradeoff. Slower = better compression at same quality.",
            "input_type": "select",
            "select_options": [
                {"value": "ultrafast", "label": "Ultrafast"},
                {"value": "superfast", "label": "Superfast"},
                {"value": "veryfast", "label": "Very Fast"},
                {"value": "faster", "label": "Faster"},
                {"value": "fast", "label": "Fast"},
                {"value": "medium", "label": "Medium (default)"},
                {"value": "slow", "label": "Slow"},
                {"value": "slower", "label": "Slower"},
                {"value": "veryslow", "label": "Very Slow"},
            ],
        },
        "max_bitrate": {
            "label": "Max Bitrate",
            "description": "Maximum video bitrate cap. Leave empty for no limit. Examples: 8000k, 15M",
            "input_type": "text",
            "placeholder": "e.g., 8000k",
        },
        "scale_height": {
            "label": "Scale to Height (px)",
            "description": "Downscale video to this height (width auto-calculated). 0 = no scaling.",
            "input_type": "slider",
            "slider_min": 0,
            "slider_max": 2160,
            "slider_step": 120,
        },
        "audio_codec": {
            "label": "Audio Codec",
            "description": "Target audio codec. Leave empty to copy audio stream.",
            "input_type": "select",
            "select_options": [
                {"value": "", "label": "Copy (no re-encode)"},
                {"value": "aac", "label": "AAC"},
                {"value": "opus", "label": "Opus"},
                {"value": "flac", "label": "FLAC (lossless)"},
                {"value": "ac3", "label": "AC3"},
                {"value": "mp3", "label": "MP3"},
            ],
        },
        "audio_bitrate": {
            "label": "Audio Bitrate",
            "description": "Audio bitrate. Leave empty for codec default. Examples: 128k, 192k, 320k",
            "input_type": "text",
            "placeholder": "e.g., 192k",
        },
        "output_format": {
            "label": "Output Container",
            "description": "Output file format. Leave empty to keep source format.",
            "input_type": "select",
            "select_options": [
                {"value": "", "label": "Same as source"},
                {"value": "mkv", "label": "Matroska (.mkv)"},
                {"value": "mp4", "label": "MP4 (.mp4)"},
                {"value": "webm", "label": "WebM (.webm)"},
            ],
        },
        "extra_flags": {
            "label": "Extra FFmpeg Flags",
            "description": "Additional FFmpeg output arguments (advanced). Appended to command.",
            "input_type": "text",
            "placeholder": "e.g., -map 0 -c:s copy",
        },
    }


# --- Codec-to-encoder defaults ---
CODEC_ENCODER_MAP = {
    "h264": "libx264",
    "hevc": "libx265",
    "av1": "libsvtav1",
    "vp9": "libvpx-vp9",
}

# Preset parameter name varies by encoder
PRESET_PARAM_MAP = {
    "libx264": "-preset",
    "libx265": "-preset",
    "libsvtav1": "-preset",  # SVT-AV1 uses numeric 0-13, mapped below
    "libaom-av1": "-cpu-used",
    "libvpx-vp9": "-cpu-used",
}

# SVT-AV1 preset mapping (name → number)
SVTAV1_PRESET_MAP = {
    "ultrafast": "12",
    "superfast": "10",
    "veryfast": "8",
    "faster": "7",
    "fast": "6",
    "medium": "5",
    "slow": "4",
    "slower": "2",
    "veryslow": "0",
}

# VP9/libaom cpu-used mapping (name → number)
CPU_USED_PRESET_MAP = {
    "ultrafast": "8",
    "superfast": "7",
    "veryfast": "6",
    "faster": "5",
    "fast": "4",
    "medium": "3",
    "slow": "2",
    "slower": "1",
    "veryslow": "0",
}

# CRF parameter name varies by encoder
CRF_PARAM_MAP = {
    "libx264": "-crf",
    "libx265": "-crf",
    "libsvtav1": "-crf",
    "libaom-av1": "-crf",
    "libvpx-vp9": "-crf",
}


def _get_source_extension(file_path):
    """Extract file extension without the dot."""
    _, ext = os.path.splitext(file_path)
    return ext.lstrip(".").lower()


def _build_ffmpeg_progress_parser(data):
    """
    Build a progress parser that extracts percentage from FFmpeg output.
    Uses duration from file_in to calculate percent.
    """
    import subprocess

    duration = 0

    try:
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            data.get("file_in", ""),
        ]
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)  # noqa: S603 - trusted ffprobe command built internally
        duration = float(result.stdout.strip())
    except Exception as e:
        logger.debug("Failed to probe duration for progress tracking: %s", e)

    def parser(line_text, pid=None, proc_start_time=None, unset=False):
        if unset or duration <= 0:
            return {}
        # Parse time=HH:MM:SS.ss from FFmpeg output
        match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", str(line_text))
        if match:
            h, m, s = float(match.group(1)), float(match.group(2)), float(match.group(3))
            current_time = h * 3600 + m * 60 + s
            percent = min(100, int(current_time / duration * 100))
            return {
                "percent": str(percent),
            }
        return {}

    return parser


def on_worker_process(data, **kwargs):
    """
    Runner function — builds an FFmpeg command based on the configured encoding presets.

    Reads settings, constructs the FFmpeg command with appropriate codec, quality,
    preset, bitrate, scaling, and audio parameters, then sets data['exec_command'].
    """
    settings = Settings(library_id=data.get("library_id"))
    settings.get_setting()

    s = settings.settings_configured

    file_in = data.get("file_in")
    if not file_in:
        data["worker_log"].append("[Encoding Presets] No input file — skipping.\n")
        return

    # Determine output format
    source_ext = _get_source_extension(file_in)
    output_format = s.get("output_format", "").strip() or source_ext
    if not output_format:
        output_format = "mkv"

    # Build output path
    file_in_basename = os.path.splitext(os.path.basename(file_in))[0]
    cache_dir = os.path.dirname(data.get("file_out") or file_in)
    file_out = os.path.join(cache_dir, f"{file_in_basename}.{output_format}")
    data["file_out"] = file_out

    # --- Build FFmpeg command ---
    cmd = ["ffmpeg", "-y", "-i", file_in]

    # Video settings
    video_codec = s.get("video_codec", "").strip()
    video_encoder = s.get("video_encoder", "").strip()

    if video_codec and not video_encoder:
        video_encoder = CODEC_ENCODER_MAP.get(video_codec, video_codec)

    if video_encoder:
        cmd.extend(["-c:v", video_encoder])

        # CRF / quality
        crf = s.get("crf", 23)
        crf_param = CRF_PARAM_MAP.get(video_encoder, "-crf")
        cmd.extend([crf_param, str(int(crf))])

        # Encoder preset
        preset = s.get("encoder_preset", "medium").strip()
        if preset:
            preset_param = PRESET_PARAM_MAP.get(video_encoder, "-preset")
            # Map named presets to numbers for SVT-AV1 and VP9/libaom
            if video_encoder == "libsvtav1":
                preset_value = SVTAV1_PRESET_MAP.get(preset, "5")
            elif video_encoder in ("libvpx-vp9", "libaom-av1"):
                preset_value = CPU_USED_PRESET_MAP.get(preset, "3")
            else:
                preset_value = preset
            cmd.extend([preset_param, preset_value])

        # Max bitrate
        max_bitrate = s.get("max_bitrate", "").strip()
        if max_bitrate:
            cmd.extend(["-maxrate", max_bitrate, "-bufsize", max_bitrate])
    else:
        # No video codec specified — copy video
        cmd.extend(["-c:v", "copy"])

    # Resolution scaling
    scale_height = int(s.get("scale_height", 0) or 0)
    if scale_height > 0 and video_encoder:
        # Scale to target height, auto-calculate width (divisible by 2)
        cmd.extend(["-vf", f"scale=-2:{scale_height}"])

    # Audio settings
    audio_codec = s.get("audio_codec", "").strip()
    if audio_codec:
        cmd.extend(["-c:a", audio_codec])
        audio_bitrate = s.get("audio_bitrate", "").strip()
        if audio_bitrate:
            cmd.extend(["-b:a", audio_bitrate])
    else:
        cmd.extend(["-c:a", "copy"])

    # Extra flags
    extra_flags = s.get("extra_flags", "").strip()
    if extra_flags:
        cmd.extend(extra_flags.split())

    # Output file
    cmd.append(file_out)

    # Set the command
    data["exec_command"] = cmd
    data["command_progress_parser"] = _build_ffmpeg_progress_parser(data)

    # Update current command display for the UI
    if isinstance(data.get("current_command"), list):
        data["current_command"].clear()
        data["current_command"].append(" ".join(cmd))

    data["worker_log"].append(f"[Encoding Presets] Command: {' '.join(cmd)}\n")
