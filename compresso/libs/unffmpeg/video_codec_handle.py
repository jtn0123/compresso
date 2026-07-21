#!/usr/bin/env python3

"""
compresso.video_codec_handle.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     20 Sep 2019, (5:42 PM)

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

from . import video_codecs
from ._contracts import EncodingArguments, probe_streams, stream_int, stream_text, string_keyed_dict


class VideoCodecHandle:
    """
    VideoCodecHandle

    Handle FFMPEG operations pertaining to video codec streams
    """

    def __init__(self, file_probe: Mapping[str, object]) -> None:
        self.file_probe = file_probe
        self.encoding_args = EncodingArguments(streams_to_map=[], streams_to_encode=[])
        self.video_tracks_count = 0

        # Configurable settings
        self.disable_video_encoding = False

        self.video_codec = "h264"  # Default to h264
        self.video_encoder = "libx264"  # Default to libx264

    def args(self) -> EncodingArguments:
        """
        Return a dictionary of streams to map and streams to encode
        :return:
        """
        # Read stream data
        self.encoding_args["streams_to_map"] = []
        self.encoding_args["streams_to_encode"] = []
        for stream in probe_streams(self.file_probe):
            # If this is a video stream, then process the args
            if stream_text(stream, "codec_type") == "video":
                # By default the video stream will be re-encoded
                just_copy_video_stream = False

                # Ignore certain codec types (images)
                if stream_text(stream, "codec_name") in ["mjpeg"]:
                    just_copy_video_stream = True

                # If this video stream is really an embedded jpeg file (image/jpeg), simply copy the stream
                tags = string_keyed_dict(stream.get("tags"))
                if tags is not None and stream_text(tags, "mimetype") == "image/jpeg":
                    just_copy_video_stream = True

                # If this video encoding is disabled. Then copy the stream
                if self.disable_video_encoding:
                    just_copy_video_stream = True

                # If the current video codec is the same as the configured destination
                # codec, then do not re-encode the video
                if stream_text(stream, "codec_name") == self.video_codec:
                    just_copy_video_stream = True

                if just_copy_video_stream:
                    # Video stream just needs to be copied
                    self.encoding_args["streams_to_encode"].extend([f"-c:v:{self.video_tracks_count}", "copy"])
                else:
                    # Video stream to be re-encoded
                    self.encoding_args["streams_to_encode"].extend([f"-c:v:{self.video_tracks_count}", self.video_encoder])

                self.video_tracks_count += 1

                # Map this video stream to be processed
                self.encoding_args["streams_to_map"].extend(["-map", f"0:{stream_int(stream, 'index')}"])

        return self.encoding_args

    def set_video_codec_with_default_encoder(self, codec_name: str) -> None:
        """
        Set the video encoder

        :return:
        """
        codec = video_codecs.grab_module(codec_name)
        self.video_codec = codec_name.lower()
        self.video_encoder = codec.codec_default_encoder()
