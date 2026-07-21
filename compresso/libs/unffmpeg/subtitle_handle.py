#!/usr/bin/env python3

"""compresso.subtitle_handle.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     19 Sep 2019, (5:23 PM)

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

from collections.abc import Mapping

from ._contracts import EncodingArguments, probe_streams, stream_int, stream_text
from .base_containers import Containers


class SubtitleHandle:
    """
    SubtitleHandle

    Handle FFMPEG operations pertaining to subtitle streams
    """

    def __init__(self, file_probe: Mapping[str, object], container: Containers) -> None:
        self.file_probe = file_probe
        self.container = container
        self.subtitle_args = EncodingArguments(streams_to_map=[], streams_to_encode=[])

        # Configurable settings
        self.remove_subtitle_streams = False

        # Check if destination container supports subtitles
        if not container.container_supports_subtitles():
            # Destination container does not support subtitles,
            # Force them to be removed
            self.remove_subtitle_streams = True

    def _append_stream(self, stream: Mapping[str, object], track_index: int) -> int:
        if stream_text(stream, "codec_type") != "subtitle" or self.remove_subtitle_streams:
            return track_index

        supported = self.container.supported_subtitles()
        codec = stream_text(stream, "codec_name")
        if codec in supported:
            output_codec = "copy"
        elif codec in self.container.unsupported_subtitles() or not supported:
            return track_index
        else:
            output_codec = supported[0]

        self.subtitle_args["streams_to_encode"].extend([f"-c:s:{track_index}", output_codec])
        self.subtitle_args["streams_to_map"].extend(["-map", f"0:{stream_int(stream, 'index')}"])
        return track_index + 1

    def args(self) -> EncodingArguments:
        """Return the subtitle streams to map and encode."""
        self.subtitle_args["streams_to_map"] = []
        self.subtitle_args["streams_to_encode"] = []
        subtitle_tracks_count = 0
        for stream in probe_streams(self.file_probe):
            subtitle_tracks_count = self._append_stream(stream, subtitle_tracks_count)

        return self.subtitle_args

    def remove_subtitles(self) -> None:
        """
        Remove the subtitles stream from result file

        :return:
        """
        self.remove_subtitle_streams = True
