#!/usr/bin/env python3

"""
Tests for compresso.libs.unffmpeg.lib.cli module.
Covers ffmpeg/ffprobe subprocess wrappers and convenience functions.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.unffmpeg.exceptions.ffmpeg import FFMpegError
from compresso.libs.unffmpeg.exceptions.ffprobe import FFProbeError
from compresso.libs.unffmpeg.lib import cli

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_popen(stdout_bytes, returncode=0):
    """Return a MagicMock that behaves like subprocess.Popen."""
    proc = MagicMock()
    proc.communicate.return_value = (stdout_bytes, None)
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# ffmpeg_cmd
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFfmpegCmd:
    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_success_returns_decoded_output(self, mock_popen):
        mock_popen.return_value = _mock_popen(b"success output", returncode=0)
        result = cli.ffmpeg_cmd(["-version"])
        assert result == "success output"
        mock_popen.assert_called_once()
        args = mock_popen.call_args
        assert args[0][0] == ["ffmpeg", "-version"]

    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_nonzero_returncode_raises_ffmpeg_error(self, mock_popen):
        mock_popen.return_value = _mock_popen(b"some output", returncode=1)
        with pytest.raises(FFMpegError):
            cli.ffmpeg_cmd(["-bad"])

    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_output_containing_error_raises_ffmpeg_error(self, mock_popen):
        mock_popen.return_value = _mock_popen(b"error: something went wrong", returncode=0)
        with pytest.raises(FFMpegError):
            cli.ffmpeg_cmd(["-x"])

    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_empty_output_raises_ffmpeg_error(self, mock_popen):
        mock_popen.return_value = _mock_popen(b"", returncode=0)
        with pytest.raises(FFMpegError):
            cli.ffmpeg_cmd(["-x"])

    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_decode_failure_raises_ffmpeg_error(self, mock_popen):
        proc = MagicMock()
        bad_bytes = MagicMock()
        bad_bytes.decode.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "bad")
        proc.communicate.return_value = (bad_bytes, None)
        proc.returncode = 0
        mock_popen.return_value = proc
        with pytest.raises(FFMpegError):
            cli.ffmpeg_cmd(["-x"])


# ---------------------------------------------------------------------------
# ffprobe_cmd
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFfprobeCmd:
    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_success_returns_decoded_output(self, mock_popen):
        mock_popen.return_value = _mock_popen(b"probe output", returncode=0)
        result = cli.ffprobe_cmd(["-version"])
        assert result == "probe output"
        args = mock_popen.call_args
        assert args[0][0] == ["ffprobe", "-version"]

    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_nonzero_returncode_raises_ffprobe_error(self, mock_popen):
        mock_popen.return_value = _mock_popen(b"output", returncode=1)
        with pytest.raises(FFProbeError):
            cli.ffprobe_cmd(["-bad"])

    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_output_containing_error_raises_ffprobe_error(self, mock_popen):
        mock_popen.return_value = _mock_popen(b"error: not found", returncode=0)
        with pytest.raises(FFProbeError):
            cli.ffprobe_cmd(["-x"])

    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_empty_output_raises_ffprobe_error(self, mock_popen):
        mock_popen.return_value = _mock_popen(b"", returncode=0)
        with pytest.raises(FFProbeError):
            cli.ffprobe_cmd(["-x"])

    @patch("compresso.libs.unffmpeg.lib.cli.subprocess.Popen")
    def test_decode_failure_raises_ffprobe_error(self, mock_popen):
        proc = MagicMock()
        bad_bytes = MagicMock()
        bad_bytes.decode.side_effect = UnicodeDecodeError("utf-8", b"", 0, 1, "bad")
        proc.communicate.return_value = (bad_bytes, None)
        proc.returncode = 0
        mock_popen.return_value = proc
        with pytest.raises(FFProbeError):
            cli.ffprobe_cmd(["-x"])


# ---------------------------------------------------------------------------
# ffprobe_file
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFfprobeFile:
    @patch("compresso.libs.unffmpeg.lib.cli.ffprobe_cmd")
    def test_returns_parsed_json(self, mock_cmd):
        probe_data = {"streams": [{"codec_type": "video"}], "format": {"filename": "test.mp4"}}
        mock_cmd.return_value = json.dumps(probe_data)
        result = cli.ffprobe_file("/path/to/test.mp4")
        assert result == probe_data
        # Verify the params passed to ffprobe_cmd
        call_args = mock_cmd.call_args[0][0]
        assert "-show_format" in call_args
        assert "-show_streams" in call_args
        assert "-print_format" in call_args
        assert "json" in call_args
        assert "/path/to/test.mp4" in call_args

    @patch("compresso.libs.unffmpeg.lib.cli.ffprobe_cmd")
    def test_invalid_json_raises_ffprobe_error(self, mock_cmd):
        mock_cmd.return_value = "not valid json {{"
        with pytest.raises(FFProbeError):
            cli.ffprobe_file("/path/to/bad.mp4")

    def test_non_string_path_raises_exception(self):
        with pytest.raises(Exception, match="Give ffprobe a full file path"):
            cli.ffprobe_file(12345)


# ---------------------------------------------------------------------------
# ffmpeg_version_info
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFfmpegVersionInfo:
    @patch("compresso.libs.unffmpeg.lib.cli.ffprobe_cmd")
    def test_returns_parsed_version_json(self, mock_cmd):
        version_data = {"program_version": {"version": "4.3.1"}}
        mock_cmd.return_value = json.dumps(version_data)
        result = cli.ffmpeg_version_info()
        assert result == version_data
        call_args = mock_cmd.call_args[0][0]
        assert "-show_versions" in call_args

    @patch("compresso.libs.unffmpeg.lib.cli.ffprobe_cmd")
    def test_invalid_json_raises_ffprobe_error(self, mock_cmd):
        mock_cmd.return_value = "not json"
        with pytest.raises(FFProbeError):
            cli.ffmpeg_version_info()


# ---------------------------------------------------------------------------
# ffmpeg_available_encoders / decoders / hw_acceleration
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFfmpegAvailableEncoders:
    @patch("compresso.libs.unffmpeg.lib.cli.ffmpeg_cmd")
    def test_returns_raw_encoder_text(self, mock_cmd):
        raw = " V..... libx264  libx264 H.264 encoder\n A..... aac  AAC encoder\n"
        mock_cmd.return_value = raw
        result = cli.ffmpeg_available_encoders()
        assert result == raw
        call_args = mock_cmd.call_args[0][0]
        assert "-encoders" in call_args


@pytest.mark.unittest
class TestFfmpegAvailableDecoders:
    @patch("compresso.libs.unffmpeg.lib.cli.ffmpeg_cmd")
    def test_returns_raw_decoder_text(self, mock_cmd):
        raw = " V..... h264  H.264 decoder\n"
        mock_cmd.return_value = raw
        result = cli.ffmpeg_available_decoders()
        assert result == raw
        call_args = mock_cmd.call_args[0][0]
        assert "-decoders" in call_args


@pytest.mark.unittest
class TestFfmpegAvailableHwAccelMethods:
    @patch("compresso.libs.unffmpeg.lib.cli.ffmpeg_cmd")
    def test_returns_raw_hwaccel_text(self, mock_cmd):
        raw = "Hardware acceleration methods:\nvdpau\ncuda\nvaapi\n"
        mock_cmd.return_value = raw
        result = cli.ffmpeg_available_hw_acceleration_methods()
        assert result == raw
        call_args = mock_cmd.call_args[0][0]
        assert "-hwaccels" in call_args
