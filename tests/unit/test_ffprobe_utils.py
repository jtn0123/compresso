#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_ffprobe_utils.py

    Unit tests for compresso.libs.ffprobe_utils.probe_file().
    All tests mock subprocess.run to avoid calling real ffprobe.

"""

import json
import subprocess

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unittest
class TestProbeFile(object):
    """Tests for probe_file()."""

    def _call(self, *args, **kwargs):
        from compresso.libs.ffprobe_utils import probe_file
        return probe_file(*args, **kwargs)

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_success_returns_parsed_dict(self, mock_run):
        """returncode=0 with valid JSON returns parsed dict."""
        expected = {
            'format': {'duration': '120.5'},
            'streams': [{'codec_type': 'video', 'codec_name': 'hevc'}],
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(expected),
            stderr='',
        )
        result = self._call('/test/video.mkv')
        assert result == expected

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_nonzero_returncode_returns_none(self, mock_run):
        """Non-zero returncode returns None."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='error info',
        )
        result = self._call('/test/bad.mkv')
        assert result is None

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_timeout_returns_none(self, mock_run):
        """TimeoutExpired returns None."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='ffprobe', timeout=30)
        result = self._call('/test/slow.mkv')
        assert result is None

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_invalid_json_returns_none(self, mock_run):
        """returncode=0 with invalid JSON returns None."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='not valid json{{{',
            stderr='',
        )
        result = self._call('/test/garbled.mkv')
        assert result is None

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_generic_exception_returns_none(self, mock_run):
        """Generic exception (e.g. OSError) returns None."""
        mock_run.side_effect = OSError("ffprobe not found")
        result = self._call('/test/missing.mkv')
        assert result is None

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_correct_command_args(self, mock_run):
        """Verify ffprobe command is constructed correctly."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"format":{},"streams":[]}',
            stderr='',
        )
        self._call('/test/video.mkv')
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0] == 'ffprobe'
        assert '-v' in cmd and 'quiet' in cmd
        assert '-print_format' in cmd and 'json' in cmd
        assert '-show_format' in cmd
        assert '-show_streams' in cmd
        assert cmd[-1] == '/test/video.mkv'
        assert kwargs['timeout'] == 30

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_custom_timeout_passed_through(self, mock_run):
        """Custom timeout parameter is passed to subprocess.run."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"format":{},"streams":[]}',
            stderr='',
        )
        self._call('/test/video.mkv', timeout=120)
        _, kwargs = mock_run.call_args
        assert kwargs['timeout'] == 120


@pytest.mark.unittest
class TestExtractMediaMetadata(object):
    """Tests for extract_media_metadata()."""

    def _call(self, *args, **kwargs):
        from compresso.libs.ffprobe_utils import extract_media_metadata
        return extract_media_metadata(*args, **kwargs)

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_extracts_codec_from_video_stream(self, mock_probe):
        """Video stream codec is extracted."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video', 'codec_name': 'hevc', 'height': 1080}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['codec'] == 'hevc'

    @pytest.mark.parametrize('height,expected', [
        (2160, '4K'),
        (1080, '1080p'),
        (720, '720p'),
        (480, '480p'),
        (360, '360p'),
    ])
    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_extracts_resolution_labels(self, mock_probe, height, expected):
        """Resolution label matches height."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'height': height}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['resolution'] == expected

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_extracts_container_from_extension(self, mock_probe):
        """Container is derived from file extension."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'height': 1080}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['container'] == 'mkv'

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_no_video_stream_returns_empty_codec(self, mock_probe):
        """Probe with only audio → empty codec and resolution."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'audio', 'codec_name': 'aac'}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['codec'] == ''
        assert result['resolution'] == ''

    @patch('compresso.libs.ffprobe_utils.probe_file', return_value=None)
    def test_probe_failure_returns_empty_with_container(self, mock_probe):
        """probe_file returns None → estimated codec, container still set."""
        result = self._call('/test/file.mkv')
        assert 'h264' in result['codec']
        assert 'estimated' in result['codec']
        assert result['resolution'] == ''
        assert result['container'] == 'mkv'

    @patch('compresso.libs.ffprobe_utils.probe_file', return_value=None)
    def test_codec_fallback_on_probe_failure_mp4(self, mock_probe):
        """probe_file returns None on .mp4 → codec contains 'h264 (estimated)'."""
        result = self._call('/test/file.mp4')
        assert result['codec'] == 'h264 (estimated)'
        assert result['container'] == 'mp4'

    @patch('compresso.libs.ffprobe_utils.probe_file', return_value=None)
    def test_codec_fallback_on_probe_failure_webm(self, mock_probe):
        """probe_file returns None on .webm → codec contains 'vp9 (estimated)'."""
        result = self._call('/test/file.webm')
        assert result['codec'] == 'vp9 (estimated)'

    @patch('compresso.libs.ffprobe_utils.probe_file', return_value=None)
    def test_codec_fallback_unknown_extension(self, mock_probe):
        """probe_file returns None on unknown extension → empty codec."""
        result = self._call('/test/file.xyz')
        assert result['codec'] == ''

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_first_video_stream_used(self, mock_probe):
        """Multiple video streams → first one's codec used."""
        mock_probe.return_value = {
            'streams': [
                {'codec_type': 'video', 'codec_name': 'hevc', 'height': 2160},
                {'codec_type': 'video', 'codec_name': 'h264', 'height': 720},
            ],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['codec'] == 'hevc'
        assert result['resolution'] == '4K'


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
