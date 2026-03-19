#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.fileinfo.py

    Helper functions for the File Info API.
    Formats ffprobe output into structured sections.

"""

from compresso.libs.ffprobe_utils import probe_file


def format_probe_data(probe_data):
    """
    Format raw ffprobe output into structured sections.

    :param probe_data: Raw ffprobe JSON dict
    :return: dict with video_streams, audio_streams, subtitle_streams, format
    """
    if not probe_data:
        return None

    streams = probe_data.get('streams', [])
    fmt = probe_data.get('format', {})

    video_streams = []
    audio_streams = []
    subtitle_streams = []

    for stream in streams:
        codec_type = stream.get('codec_type', '')
        info = {
            'index': stream.get('index', 0),
            'codec_name': stream.get('codec_name', ''),
            'codec_long_name': stream.get('codec_long_name', ''),
            'profile': stream.get('profile', ''),
        }

        if codec_type == 'video':
            info.update({
                'width': stream.get('width', 0),
                'height': stream.get('height', 0),
                'pix_fmt': stream.get('pix_fmt', ''),
                'bit_rate': _safe_int(stream.get('bit_rate')),
                'r_frame_rate': stream.get('r_frame_rate', ''),
                'avg_frame_rate': stream.get('avg_frame_rate', ''),
                'duration': _safe_float(stream.get('duration')),
                'nb_frames': _safe_int(stream.get('nb_frames')),
                'color_space': stream.get('color_space', ''),
                'color_transfer': stream.get('color_transfer', ''),
                'color_primaries': stream.get('color_primaries', ''),
                'hdr': _is_hdr(stream),
            })
            # Resolution label
            height = stream.get('height', 0)
            if height >= 2160:
                info['resolution_label'] = '4K'
            elif height >= 1440:
                info['resolution_label'] = '1440p'
            elif height >= 1080:
                info['resolution_label'] = '1080p'
            elif height >= 720:
                info['resolution_label'] = '720p'
            elif height >= 480:
                info['resolution_label'] = '480p'
            else:
                info['resolution_label'] = '{}p'.format(height) if height > 0 else ''
            video_streams.append(info)

        elif codec_type == 'audio':
            info.update({
                'sample_rate': _safe_int(stream.get('sample_rate')),
                'channels': stream.get('channels', 0),
                'channel_layout': stream.get('channel_layout', ''),
                'bit_rate': _safe_int(stream.get('bit_rate')),
                'duration': _safe_float(stream.get('duration')),
            })
            tags = stream.get('tags') or {}
            if not isinstance(tags, dict):
                tags = {}
            info['language'] = tags.get('language', '')
            info['title'] = tags.get('title', '')
            audio_streams.append(info)

        elif codec_type == 'subtitle':
            tags = stream.get('tags') or {}
            if not isinstance(tags, dict):
                tags = {}
            info.update({
                'language': tags.get('language', ''),
                'title': tags.get('title', ''),
            })
            subtitle_streams.append(info)

    format_info = {
        'filename': fmt.get('filename', ''),
        'format_name': fmt.get('format_name', ''),
        'format_long_name': fmt.get('format_long_name', ''),
        'duration': _safe_float(fmt.get('duration')),
        'size': _safe_int(fmt.get('size')),
        'bit_rate': _safe_int(fmt.get('bit_rate')),
        'nb_streams': _safe_int(fmt.get('nb_streams')),
    }

    return {
        'video_streams': video_streams,
        'audio_streams': audio_streams,
        'subtitle_streams': subtitle_streams,
        'format': format_info,
    }


def probe_and_format(filepath):
    """
    Probe a file and return formatted info.

    :param filepath: Absolute path to the media file
    :return: dict with formatted file info, or None on failure
    """
    probe_data = probe_file(filepath)
    if not probe_data:
        return None
    return format_probe_data(probe_data)


def _is_hdr(stream):
    """Check if a video stream is HDR based on color metadata."""
    transfer = stream.get('color_transfer', '').lower()
    hdr_transfers = {'smpte2084', 'arib-std-b67', 'smpte428'}
    if transfer in hdr_transfers:
        return True
    # Secondary signal: BT.2020 color primaries suggest HDR content
    primaries = stream.get('color_primaries', '').lower()
    if primaries == 'bt2020':
        return True
    return False


def _safe_int(value):
    """Safely convert to int."""
    if value is None:
        return 0
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _safe_float(value):
    """Safely convert to float."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0
