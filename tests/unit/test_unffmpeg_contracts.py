"""Tests for ffprobe boundary contracts."""

from compresso.libs.unffmpeg._contracts import stream_int


def test_stream_int_rejects_boolean_and_fractional_values() -> None:
    assert stream_int({"index": True}, "index") == 0
    assert stream_int({"index": 2.9}, "index") == 0


def test_stream_int_accepts_integer_and_integer_string_values() -> None:
    assert stream_int({"index": 2}, "index") == 2
    assert stream_int({"index": "3"}, "index") == 3
