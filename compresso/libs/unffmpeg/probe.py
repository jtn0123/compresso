#!/usr/bin/env python3

"""
compresso.libs.unffmpeg.probe

ffprobe wrapper. Pulled out of ``Info`` so probing has its own
import path; ``Info`` no longer mixes "list available encoders /
versions" with "probe a single file".
"""

from .lib import cli


class Probe:
    """Wrap ffprobe so callers don't reach into ``cli`` directly."""

    @staticmethod
    def file(path: str):
        """Probe ``path`` with ffprobe and return the parsed result.

        Return type is whatever ``cli.ffprobe_file`` returns — typically
        a dict from the parsed JSON output, but typed as ``Any`` here so
        callers don't get a misleadingly-narrow annotation while the
        underlying helper remains untyped.

        :param path: filesystem path of the media file to probe.
        """
        return cli.ffprobe_file(path)
