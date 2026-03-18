#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_ffprobe_utils.py

    Unit tests for unmanic.libs.ffprobe_utils.probe_file().
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
        from unmanic.libs.ffprobe_utils import probe_file
        return probe_file(*args, **kwargs)

    @patch('unmanic.libs.ffprobe_utils.subprocess.run')
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

    @patch('unmanic.libs.ffprobe_utils.subprocess.run')
    def test_nonzero_returncode_returns_none(self, mock_run):
        """Non-zero returncode returns None."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='error info',
        )
        result = self._call('/test/bad.mkv')
        assert result is None

    @patch('unmanic.libs.ffprobe_utils.subprocess.run')
    def test_timeout_returns_none(self, mock_run):
        """TimeoutExpired returns None."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='ffprobe', timeout=30)
        result = self._call('/test/slow.mkv')
        assert result is None

    @patch('unmanic.libs.ffprobe_utils.subprocess.run')
    def test_invalid_json_returns_none(self, mock_run):
        """returncode=0 with invalid JSON returns None."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='not valid json{{{',
            stderr='',
        )
        result = self._call('/test/garbled.mkv')
        assert result is None

    @patch('unmanic.libs.ffprobe_utils.subprocess.run')
    def test_generic_exception_returns_none(self, mock_run):
        """Generic exception (e.g. OSError) returns None."""
        mock_run.side_effect = OSError("ffprobe not found")
        result = self._call('/test/missing.mkv')
        assert result is None

    @patch('unmanic.libs.ffprobe_utils.subprocess.run')
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

    @patch('unmanic.libs.ffprobe_utils.subprocess.run')
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


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
