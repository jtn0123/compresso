#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_fileinfo.py

    Unit tests for compresso.webserver.helpers.fileinfo pure functions.
    No DB, no subprocess mocking needed.

"""

import pytest
from unittest.mock import patch

from compresso.webserver.helpers.fileinfo import format_probe_data, _is_hdr


# ------------------------------------------------------------------
# TestFormatProbeData
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestFormatProbeData(object):
    """Tests for format_probe_data()."""

    def test_none_input_returns_none(self):
        """None input returns None."""
        assert format_probe_data(None) is None

    def test_empty_dict_returns_none(self):
        """Empty dict returns None (falsy check)."""
        assert format_probe_data({}) is None

    def test_single_video_stream(self):
        """Single video stream is correctly extracted."""
        probe = {
            'streams': [{
                'codec_type': 'video',
                'index': 0,
                'codec_name': 'hevc',
                'codec_long_name': 'H.265',
                'profile': 'Main 10',
                'width': 1920,
                'height': 1080,
                'pix_fmt': 'yuv420p10le',
                'bit_rate': '5000000',
                'r_frame_rate': '24/1',
                'avg_frame_rate': '24/1',
                'duration': '120.5',
                'nb_frames': '2892',
                'color_space': 'bt709',
                'color_transfer': 'bt709',
                'color_primaries': 'bt709',
            }],
            'format': {},
        }
        result = format_probe_data(probe)
        assert result is not None
        assert len(result['video_streams']) == 1
        vs = result['video_streams'][0]
        assert vs['codec_name'] == 'hevc'
        assert vs['width'] == 1920
        assert vs['height'] == 1080
        assert vs['resolution_label'] == '1080p'
        assert vs['hdr'] is False
        assert vs['bit_rate'] == 5000000
        assert vs['duration'] == 120.5

    def test_audio_stream_with_tags(self):
        """Audio stream with language/title tags extracted."""
        probe = {
            'streams': [{
                'codec_type': 'audio',
                'index': 1,
                'codec_name': 'aac',
                'codec_long_name': 'AAC',
                'profile': 'LC',
                'sample_rate': '48000',
                'channels': 6,
                'channel_layout': '5.1',
                'bit_rate': '384000',
                'duration': '120.5',
                'tags': {
                    'language': 'eng',
                    'title': 'Surround Sound',
                },
            }],
            'format': {},
        }
        result = format_probe_data(probe)
        assert len(result['audio_streams']) == 1
        audio = result['audio_streams'][0]
        assert audio['language'] == 'eng'
        assert audio['title'] == 'Surround Sound'
        assert audio['channels'] == 6
        assert audio['sample_rate'] == 48000

    def test_subtitle_stream(self):
        """Subtitle stream language extracted."""
        probe = {
            'streams': [{
                'codec_type': 'subtitle',
                'index': 2,
                'codec_name': 'srt',
                'codec_long_name': 'SubRip',
                'profile': '',
                'tags': {'language': 'spa'},
            }],
            'format': {},
        }
        result = format_probe_data(probe)
        assert len(result['subtitle_streams']) == 1
        sub = result['subtitle_streams'][0]
        assert sub['language'] == 'spa'
        assert sub['codec_name'] == 'srt'

    def test_format_section(self):
        """Format section extracts duration/size/bitrate."""
        probe = {
            'streams': [],
            'format': {
                'filename': '/media/test.mkv',
                'format_name': 'matroska',
                'format_long_name': 'Matroska / WebM',
                'duration': '3600.0',
                'size': '5000000000',
                'bit_rate': '11111111',
                'nb_streams': '3',
            },
        }
        result = format_probe_data(probe)
        fmt = result['format']
        assert fmt['duration'] == 3600.0
        assert fmt['size'] == 5000000000
        assert fmt['bit_rate'] == 11111111
        assert fmt['nb_streams'] == 3
        assert fmt['filename'] == '/media/test.mkv'

    def test_multiple_stream_types_sorted(self):
        """Multiple stream types are sorted into correct lists."""
        probe = {
            'streams': [
                {'codec_type': 'video', 'index': 0, 'codec_name': 'h264',
                 'codec_long_name': '', 'profile': '', 'width': 1920, 'height': 1080},
                {'codec_type': 'audio', 'index': 1, 'codec_name': 'aac',
                 'codec_long_name': '', 'profile': ''},
                {'codec_type': 'subtitle', 'index': 2, 'codec_name': 'srt',
                 'codec_long_name': '', 'profile': ''},
                {'codec_type': 'audio', 'index': 3, 'codec_name': 'ac3',
                 'codec_long_name': '', 'profile': ''},
            ],
            'format': {},
        }
        result = format_probe_data(probe)
        assert len(result['video_streams']) == 1
        assert len(result['audio_streams']) == 2
        assert len(result['subtitle_streams']) == 1


# ------------------------------------------------------------------
# TestResolutionLabels
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestResolutionLabels(object):
    """Tests for resolution label assignment inside format_probe_data."""

    def _get_label(self, height):
        probe = {
            'streams': [{'codec_type': 'video', 'index': 0, 'codec_name': 'h264',
                         'codec_long_name': '', 'profile': '',
                         'width': int(height * 16 / 9), 'height': height}],
            'format': {},
        }
        result = format_probe_data(probe)
        return result['video_streams'][0]['resolution_label']

    def test_2160_is_4k(self):
        assert self._get_label(2160) == '4K'

    def test_3840_is_4k(self):
        assert self._get_label(3840) == '4K'

    def test_1440_is_1440p(self):
        assert self._get_label(1440) == '1440p'

    def test_1080_is_1080p(self):
        assert self._get_label(1080) == '1080p'

    def test_720_is_720p(self):
        assert self._get_label(720) == '720p'

    def test_480_is_480p(self):
        assert self._get_label(480) == '480p'

    def test_360_is_360p(self):
        assert self._get_label(360) == '360p'

    def test_0_is_empty(self):
        assert self._get_label(0) == ''


# ------------------------------------------------------------------
# TestHdrDetection
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestHdrDetection(object):
    """Tests for _is_hdr() function."""

    def test_smpte2084_is_hdr(self):
        assert _is_hdr({'color_transfer': 'smpte2084'}) is True

    def test_arib_std_b67_is_hdr(self):
        assert _is_hdr({'color_transfer': 'arib-std-b67'}) is True

    def test_smpte428_is_hdr(self):
        assert _is_hdr({'color_transfer': 'smpte428'}) is True

    def test_bt709_is_not_hdr(self):
        assert _is_hdr({'color_transfer': 'bt709'}) is False

    def test_empty_string_is_not_hdr(self):
        assert _is_hdr({'color_transfer': ''}) is False

    def test_missing_key_is_not_hdr(self):
        assert _is_hdr({}) is False

    def test_bt2020_primaries_is_hdr(self):
        assert _is_hdr({'color_primaries': 'bt2020'}) is True

    def test_bt2020_case_insensitive(self):
        assert _is_hdr({'color_primaries': 'BT2020'}) is True

    def test_smpte2084_case_insensitive(self):
        assert _is_hdr({'color_transfer': 'SMPTE2084'}) is True


# ------------------------------------------------------------------
# TestTagsSafety
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestTagsSafety(object):
    """Tests for non-dict tags handling in format_probe_data."""

    def test_audio_stream_with_non_dict_tags(self):
        """Audio stream with string tags → no crash, language/title empty."""
        probe = {
            'streams': [{
                'codec_type': 'audio',
                'index': 0,
                'codec_name': 'aac',
                'codec_long_name': 'AAC',
                'profile': 'LC',
                'tags': 'some string',
            }],
            'format': {},
        }
        result = format_probe_data(probe)
        audio = result['audio_streams'][0]
        assert audio['language'] == ''
        assert audio['title'] == ''

    def test_subtitle_stream_with_none_tags(self):
        """Subtitle stream with None tags → no crash, language/title empty."""
        probe = {
            'streams': [{
                'codec_type': 'subtitle',
                'index': 0,
                'codec_name': 'srt',
                'codec_long_name': 'SubRip',
                'profile': '',
                'tags': None,
            }],
            'format': {},
        }
        result = format_probe_data(probe)
        sub = result['subtitle_streams'][0]
        assert sub['language'] == ''
        assert sub['title'] == ''


# ------------------------------------------------------------------
# TestProbeAndFormat (B2)
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestProbeAndFormat(object):
    """Tests for probe_and_format()."""

    @patch('compresso.webserver.helpers.fileinfo.probe_file', return_value=None)
    def test_probe_failure_returns_none(self, mock_probe):
        """probe_and_format returns None when probe_file returns None."""
        from compresso.webserver.helpers.fileinfo import probe_and_format
        result = probe_and_format('/nonexistent/file.mkv')
        assert result is None

    @patch('compresso.webserver.helpers.fileinfo.probe_file')
    def test_probe_success_returns_formatted(self, mock_probe):
        """probe_and_format returns formatted result with expected keys."""
        mock_probe.return_value = {
            'streams': [
                {'codec_type': 'video', 'index': 0, 'codec_name': 'h264',
                 'codec_long_name': 'H.264', 'profile': 'High',
                 'width': 1920, 'height': 1080},
            ],
            'format': {
                'filename': '/test/file.mkv',
                'format_name': 'matroska',
                'format_long_name': 'Matroska',
                'duration': '120.0',
                'size': '1000000',
                'bit_rate': '66666',
                'nb_streams': '1',
            },
        }
        from compresso.webserver.helpers.fileinfo import probe_and_format
        result = probe_and_format('/test/file.mkv')
        assert result is not None
        assert 'video_streams' in result
        assert 'audio_streams' in result
        assert 'subtitle_streams' in result
        assert 'format' in result
        assert len(result['video_streams']) == 1
        assert result['video_streams'][0]['codec_name'] == 'h264'


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
