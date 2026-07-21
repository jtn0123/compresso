"""Typed contracts and runtime narrowing for ffprobe-derived data."""

from collections.abc import Mapping
from typing import TypedDict

from compresso.libs import narrowing


class EncodingArguments(TypedDict):
    streams_to_map: list[str]
    streams_to_encode: list[str]


def string_keyed_dict(value: object) -> dict[str, object] | None:
    return narrowing.string_keyed_dict_or_none(value)


def probe_streams(file_probe: Mapping[str, object]) -> list[dict[str, object]]:
    raw_streams = file_probe.get("streams")
    if not isinstance(raw_streams, list):
        return []
    return [stream for value in raw_streams if (stream := string_keyed_dict(value)) is not None]


def stream_text(stream: Mapping[str, object], key: str) -> str:
    return narrowing.strict_str(stream.get(key))


def stream_int(stream: Mapping[str, object], key: str) -> int:
    return narrowing.coerce_int(stream.get(key))
