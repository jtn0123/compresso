#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.ffprobe_utils.py

    Shared ffprobe utility for probing media files.
    Used by File Info, Health Check, and other features.

"""

import json
import subprocess

from unmanic.libs.logs import UnmanicLogging

logger = UnmanicLogging.get_logger('ffprobe_utils')


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
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("ffprobe parse error for %s: %s", filepath, str(e))
        return None
