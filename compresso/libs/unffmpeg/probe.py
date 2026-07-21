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
    def file(path: str) -> dict[str, object]:
        """Probe ``path`` with ffprobe and return the parsed result.

        The CLI boundary validates that ffprobe returned a JSON object.

        :param path: filesystem path of the media file to probe.
        """
        return cli.ffprobe_file(path)
