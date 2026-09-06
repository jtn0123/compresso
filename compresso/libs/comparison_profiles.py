"""Typed built-in profiles for sample comparisons."""

from typing import TypedDict


class ComparisonProfile(TypedDict):
    label: str
    description: str
    encoder: str
    codec: str
    crf: int
    preset: str
    hardware: bool
    ffmpeg_args: list[str]


PROFILE_CATALOG: dict[str, ComparisonProfile] = {
    "x265_crf_22": {
        "label": "x265 CRF 22",
        "description": "High-quality HEVC software encode",
        "encoder": "libx265",
        "codec": "hevc",
        "crf": 22,
        "preset": "medium",
        "hardware": False,
        "ffmpeg_args": ["-c:v", "libx265", "-crf", "22", "-preset", "medium"],
    },
    "x265_crf_26": {
        "label": "x265 CRF 26",
        "description": "Smaller HEVC software encode",
        "encoder": "libx265",
        "codec": "hevc",
        "crf": 26,
        "preset": "slow",
        "hardware": False,
        "ffmpeg_args": ["-c:v", "libx265", "-crf", "26", "-preset", "slow"],
    },
    "svt_av1_crf_30": {
        "label": "SVT-AV1 CRF 30",
        "description": "Efficient AV1 software encode",
        "encoder": "libsvtav1",
        "codec": "av1",
        "crf": 30,
        "preset": "8",
        "hardware": False,
        "ffmpeg_args": ["-c:v", "libsvtav1", "-crf", "30", "-preset", "8"],
    },
    "amd_amf_hevc_quality": {
        "label": "AMD AMF HEVC Quality",
        "description": "Fast HEVC encode on supported AMD GPUs",
        "encoder": "hevc_amf",
        "codec": "hevc",
        "crf": 24,
        "preset": "quality",
        "hardware": True,
        "ffmpeg_args": ["-c:v", "hevc_amf", "-quality", "quality", "-rc", "cqp", "-qp_i", "24", "-qp_p", "24"],
    },
    "x264_crf_23": {
        "label": "x264 CRF 23",
        "description": "Compatible H.264 software baseline",
        "encoder": "libx264",
        "codec": "h264",
        "crf": 23,
        "preset": "medium",
        "hardware": False,
        "ffmpeg_args": ["-c:v", "libx264", "-crf", "23", "-preset", "medium"],
    },
}
