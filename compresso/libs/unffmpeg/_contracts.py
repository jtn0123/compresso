"""Typed contracts and runtime narrowing for ffprobe-derived data."""

from collections.abc import Mapping
from typing import TypedDict, cast


class EncodingArguments(TypedDict):
    streams_to_map: list[str]
    streams_to_encode: list[str]


def string_keyed_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return None
    return cast("dict[str, object]", value)


def probe_streams(file_probe: Mapping[str, object]) -> list[dict[str, object]]:
    raw_streams = file_probe.get("streams")
    if not isinstance(raw_streams, list):
        return []
    return [stream for value in raw_streams if (stream := string_keyed_dict(value)) is not None]


def stream_text(stream: Mapping[str, object], key: str) -> str:
    value = stream.get(key)
    return value if isinstance(value, str) else ""


def stream_int(stream: Mapping[str, object], key: str) -> int:
    value = stream.get(key)
    if isinstance(value, (int, float, str)):
        try:
            return int(value)
        except (TypeError, ValueError):
            pass
    return 0
