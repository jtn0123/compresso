#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.ffprobe_utils.py

    Shared ffprobe utility for probing media files.
    Used by File Info, Health Check, and other features.

"""

import json
import re
import subprocess

from compresso.libs.logs import CompressoLogging

logger = CompressoLogging.get_logger('ffprobe_utils')


def probe_file(filepath, timeout=30):
    """
    Run ffprobe on a file and return parsed JSON output.

    :param filepath: Absolute path to the media file
    :param timeout: Timeout in seconds
    :return: dict with ffprobe output (format + streams), or None on failure
    """
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        filepath,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            logger.warning("ffprobe failed for %s: %s", filepath, result.stderr[:500] if result.stderr else '')
            return None
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out for %s", filepath)
        return None
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as e:
        logger.warning("ffprobe parse error for %s: %s", filepath, str(e))
        return None


CONTAINER_CODEC_HINTS = {
    'mp4': 'h264',
    'mkv': 'h264',
    'webm': 'vp9',
    'avi': 'mpeg4',
    'm4v': 'h264',
    'mov': 'h264',
    'ts': 'h264',
    'flv': 'h264',
}


def extract_media_metadata(filepath):
    """
    Extract codec, resolution, and container metadata from a media file.

    :param filepath: Absolute path to the media file
    :return: dict with 'codec', 'resolution', 'container' keys
    """
    import os

    result = {
        'codec': '',
        'resolution': '',
        'container': '',
        'duration': 0,
    }

    # Container from file extension
    ext = os.path.splitext(filepath)[1].lower().lstrip('.')
    if ext:
        result['container'] = ext

    probe_data = probe_file(filepath, timeout=30)
    if not probe_data:
        # Fallback: estimate codec from container extension
        hint = CONTAINER_CODEC_HINTS.get(ext, '')
        if hint:
            result['codec'] = '{} (estimated)'.format(hint)
        return result

    # Extract duration from format level
    try:
        result['duration'] = float(probe_data.get('format', {}).get('duration', 0) or 0)
    except (TypeError, ValueError):
        pass

    # Find the first video stream
    for stream in probe_data.get('streams', []):
        if stream.get('codec_type') == 'video':
            result['codec'] = stream.get('codec_name', '')
            height = int(stream.get('height', 0) or 0)
            if height >= 2160:
                result['resolution'] = '4K'
            elif height >= 1440:
                result['resolution'] = '1440p'
            elif height >= 1080:
                result['resolution'] = '1080p'
            elif height >= 720:
                result['resolution'] = '720p'
            elif height >= 480:
                result['resolution'] = '480p'
            elif height > 0:
                result['resolution'] = '{}p'.format(height)
            break

    return result


def compute_quality_scores(source_path, encoded_path, duration_limit=30):
    """
    Compare source and encoded files using SSIM and VMAF quality metrics.
    Limits comparison to the first `duration_limit` seconds for performance.

    :param source_path: Path to the original/reference video
    :param encoded_path: Path to the encoded/distorted video
    :param duration_limit: Max seconds to compare (0 = full file)
    :return: dict with 'vmaf_score' (float|None) and 'ssim_score' (float|None)
    """
    scores = {'vmaf_score': None, 'ssim_score': None}

    time_limit_args = ['-t', str(duration_limit)] if duration_limit > 0 else []

    # Try SSIM first (more widely available)
    try:
        ssim_cmd = (
            ['ffmpeg', '-y']
            + time_limit_args + ['-i', encoded_path]
            + time_limit_args + ['-i', source_path]
            + ['-lavfi', '[0:v][1:v]ssim', '-f', 'null', '-']
        )
        result = subprocess.run(ssim_cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0 and result.stderr:
            match = re.search(r'All:(\d+(?:\.\d+)?)', result.stderr)
            if match:
                scores['ssim_score'] = float(match.group(1))
    except subprocess.TimeoutExpired:
        logger.debug("SSIM computation timed out for %s", encoded_path)
    except Exception as e:
        logger.debug("SSIM computation failed for %s: %s", encoded_path, str(e))

    # Try VMAF (requires libvmaf filter in FFmpeg)
    try:
        vmaf_cmd = (
            ['ffmpeg', '-y']
            + time_limit_args + ['-i', encoded_path]
            + time_limit_args + ['-i', source_path]
            + ['-lavfi', '[0:v][1:v]libvmaf', '-f', 'null', '-']
        )
        result = subprocess.run(vmaf_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and result.stderr:
            match = re.search(r'VMAF score:\s*(\d+(?:\.\d+)?)', result.stderr)
            if not match:
                match = re.search(r'vmaf_score:\s*(\d+(?:\.\d+)?)', result.stderr)
            if match:
                scores['vmaf_score'] = float(match.group(1))
    except subprocess.TimeoutExpired:
        logger.debug("VMAF computation timed out for %s", encoded_path)
    except Exception as e:
        logger.debug("VMAF computation failed for %s (libvmaf may not be available): %s", encoded_path, str(e))

    return scores
