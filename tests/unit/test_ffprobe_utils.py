#!/usr/bin/env python3

"""
    tests.unit.test_ffprobe_utils.py

    Unit tests for compresso.libs.ffprobe_utils.probe_file().
    All tests mock subprocess.run to avoid calling real ffprobe.

"""

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unittest
class TestProbeFile:
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
class TestExtractMediaMetadata:
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
    def test_resolution_1440p(self, mock_probe):
        """Height=1440 maps to 1440p."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'height': 1440}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['resolution'] == '1440p'

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_resolution_boundary_2159(self, mock_probe):
        """Height=2159 is below 4K threshold, maps to 1440p."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'height': 2159}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['resolution'] == '1440p'

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_resolution_boundary_1079(self, mock_probe):
        """Height=1079 is below 1080p threshold, maps to 720p."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'height': 1079}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['resolution'] == '720p'

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_height_zero_gives_empty_resolution(self, mock_probe):
        """Height=0 in stream results in empty resolution."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'height': 0}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['resolution'] == ''

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_height_none_gives_empty_resolution(self, mock_probe):
        """Height=None in stream results in empty resolution."""
        mock_probe.return_value = {
            'streams': [{'codec_type': 'video', 'codec_name': 'h264', 'height': None}],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['resolution'] == ''

    @patch('compresso.libs.ffprobe_utils.probe_file')
    def test_empty_streams_returns_empty(self, mock_probe):
        """Empty streams list returns empty codec and resolution."""
        mock_probe.return_value = {
            'streams': [],
            'format': {},
        }
        result = self._call('/test/file.mkv')
        assert result['codec'] == ''
        assert result['resolution'] == ''

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


@pytest.mark.unittest
class TestComputeQualityScores:
    """Tests for compute_quality_scores()."""

    def _call(self, *args, **kwargs):
        from compresso.libs.ffprobe_utils import compute_quality_scores
        return compute_quality_scores(*args, **kwargs)

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_returns_both_scores_when_available(self, mock_run):
        """Both VMAF and SSIM should be extracted from ffmpeg output."""
        def side_effect(cmd, **kwargs):
            if 'ssim' in ' '.join(cmd):
                return MagicMock(
                    returncode=0,
                    stderr='[Parsed_ssim_0 @ 0x...] SSIM Y:0.950 U:0.980 V:0.975 All:0.968',
                )
            elif 'libvmaf' in ' '.join(cmd):
                return MagicMock(
                    returncode=0,
                    stderr='[libvmaf @ 0x...] VMAF score: 92.5',
                )
            return MagicMock(returncode=1, stderr='')

        mock_run.side_effect = side_effect
        result = self._call('/source.mkv', '/encoded.mkv')
        assert result['ssim_score'] == pytest.approx(0.968)
        assert result['vmaf_score'] == pytest.approx(92.5)

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_returns_none_when_ffmpeg_fails(self, mock_run):
        """Non-zero returncode results in None scores."""
        mock_run.return_value = MagicMock(returncode=1, stderr='error')
        result = self._call('/source.mkv', '/encoded.mkv')
        assert result['vmaf_score'] is None
        assert result['ssim_score'] is None

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_returns_none_on_timeout(self, mock_run):
        """Timeouts result in None scores."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='ffmpeg', timeout=120)
        result = self._call('/source.mkv', '/encoded.mkv')
        assert result['vmaf_score'] is None
        assert result['ssim_score'] is None

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_ssim_without_vmaf(self, mock_run):
        """SSIM available but VMAF fails (no libvmaf)."""
        def side_effect(cmd, **kwargs):
            if 'ssim' in ' '.join(cmd):
                return MagicMock(
                    returncode=0,
                    stderr='SSIM Y:0.900 All:0.912',
                )
            # VMAF fails
            return MagicMock(returncode=1, stderr='No such filter: libvmaf')

        mock_run.side_effect = side_effect
        result = self._call('/source.mkv', '/encoded.mkv')
        assert result['ssim_score'] == pytest.approx(0.912)
        assert result['vmaf_score'] is None

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_vmaf_alternative_format(self, mock_run):
        """Supports vmaf_score: format (no 'VMAF score:')."""
        def side_effect(cmd, **kwargs):
            if 'ssim' in ' '.join(cmd):
                return MagicMock(returncode=1, stderr='')
            elif 'libvmaf' in ' '.join(cmd):
                return MagicMock(
                    returncode=0,
                    stderr='vmaf_score: 88.3',
                )
            return MagicMock(returncode=1, stderr='')

        mock_run.side_effect = side_effect
        result = self._call('/source.mkv', '/encoded.mkv')
        assert result['vmaf_score'] == pytest.approx(88.3)

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_duration_limit_passed_to_ffmpeg(self, mock_run):
        """When duration_limit > 0, -t flag should be in ffmpeg command."""
        mock_run.return_value = MagicMock(returncode=0, stderr='All:0.950')
        self._call('/source.mkv', '/encoded.mkv', duration_limit=15)

        # Check the first call (SSIM)
        first_call_cmd = mock_run.call_args_list[0][0][0]
        assert '-t' in first_call_cmd
        t_idx = first_call_cmd.index('-t')
        assert first_call_cmd[t_idx + 1] == '15'

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_no_duration_limit_omits_t_flag(self, mock_run):
        """When duration_limit=0, -t flag should NOT be in ffmpeg command."""
        mock_run.return_value = MagicMock(returncode=0, stderr='')
        self._call('/source.mkv', '/encoded.mkv', duration_limit=0)

        first_call_cmd = mock_run.call_args_list[0][0][0]
        assert '-t' not in first_call_cmd

    @patch('compresso.libs.ffprobe_utils.subprocess.run')
    def test_generic_exception_returns_none(self, mock_run):
        """Generic exception returns None for both scores."""
        mock_run.side_effect = OSError("ffmpeg not found")
        result = self._call('/source.mkv', '/encoded.mkv')
        assert result['vmaf_score'] is None
        assert result['ssim_score'] is None


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
