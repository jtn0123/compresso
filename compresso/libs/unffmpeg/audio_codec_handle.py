#!/usr/bin/env python3

"""
compresso.audio_codec_handle.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     21 Sep 2019, (7:53 AM)

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

from . import audio_codecs
from ._contracts import EncodingArguments, probe_streams, stream_int, stream_text, string_keyed_dict


class AudioCodecHandle:
    """
    AudioCodecHandle

    Handle FFMPEG operations pertaining to audio codec streams
    """

    def __init__(self, file_probe: Mapping[str, object]) -> None:
        self.file_probe = file_probe
        self.encoding_args = EncodingArguments(streams_to_map=[], streams_to_encode=[])
        self.audio_tracks_count = 0

        # Configurable settings
        self.disable_audio_encoding = False

        self.enable_audio_stream_transcoding = False
        self.audio_codec_transcoding = "aac"  # Default to aac
        self.audio_encoder_transcoding = "aac"  # Default to aac

        self.enable_audio_stream_stereo_cloning = False
        self.audio_codec_cloning = "aac"  # Default to aac
        self.audio_encoder_cloning = "aac"  # Default to aac
        self.audio_stereo_stream_bitrate = "128k"  # Default to 128k

    def copy_stream(self, stream: Mapping[str, object]) -> None:
        """
        Copy the audio stream. It will not be modified

        :param stream:
        :return:
        """
        self.encoding_args["streams_to_encode"].extend(
            [
                f"-c:a:{self.audio_tracks_count}",
                "copy",
            ]
        )
        # Map this stream
        self.encoding_args["streams_to_map"].extend(["-map", f"0:{stream_int(stream, 'index')}"])
        self.audio_tracks_count += 1

    def transcode_stream(self, stream: Mapping[str, object]) -> None:
        """
        Transcode the audio stream to the configured audio codec

        :param stream:
        :return:
        """
        self.encoding_args["streams_to_encode"].extend([f"-c:a:{self.audio_tracks_count}", self.audio_encoder_transcoding])
        # Map this stream
        self.encoding_args["streams_to_map"].extend(["-map", f"0:{stream_int(stream, 'index')}"])
        self.audio_tracks_count += 1

    def clone_stereo_stream(self, stream: Mapping[str, object]) -> None:
        """
        Generate a stereo clone of a given stream

        :param stream:
        :return:
        """
        tags = string_keyed_dict(stream.get("tags"))
        title = stream_text(tags, "title") if tags is not None else ""
        audio_tag = "".join(character for character in title if not character.isdigit()).rstrip(".") + "Stereo"

        # Map a duplicated stream
        self.encoding_args["streams_to_map"].extend(["-map", f" 0:{stream_int(stream, 'index')}"])

        self.encoding_args["streams_to_encode"].extend(
            [
                f"-c:a:{self.audio_tracks_count}",
                self.audio_encoder_cloning,
                f"-b:a:{self.audio_tracks_count}",
                self.audio_stereo_stream_bitrate,
                f"-ac:a:{self.audio_tracks_count}",
                "2",
                f"-metadata:s:a:{self.audio_tracks_count}",
                f"title='{audio_tag}'",
            ]
        )
        self.audio_tracks_count += 1

    def args(self) -> EncodingArguments:
        """
        Return a dictionary of streams to map and streams to encode
        :return:
        """
        # Read stream data
        self.encoding_args["streams_to_map"] = []
        self.encoding_args["streams_to_encode"] = []
        for stream in probe_streams(self.file_probe):
            # If this is a audio stream, then process the args
            if stream_text(stream, "codec_type") == "audio":
                if self.disable_audio_encoding:
                    # Audio re-encoding is disabled. Just copy the stream
                    self.copy_stream(stream)
                else:
                    # Transcode stream if configured to do so
                    if self.enable_audio_stream_transcoding:
                        # If the current audio codec of this stream is the same as the configured
                        # destination codec, then do not re-encode this audio stream
                        if stream_text(stream, "codec_name") == self.audio_codec_transcoding:
                            self.copy_stream(stream)
                        else:
                            self.transcode_stream(stream)
                    else:
                        self.copy_stream(stream)

                    # If we have enabled stream cloning and this stream has more than 2 channels
                    if self.enable_audio_stream_stereo_cloning and stream_int(stream, "channels") > 2:
                        self.clone_stereo_stream(stream)

        return self.encoding_args

    def set_audio_codec_with_default_encoder_cloning(self, codec_name: str) -> None:
        """
        Set the audio encoder for cloned streams

        :return:
        """
        codec = audio_codecs.grab_module(codec_name)
        self.audio_codec_cloning = codec_name
        self.audio_encoder_cloning = codec.codec_default_encoder()

    def set_audio_codec_with_default_encoder_transcoding(self, codec_name: str) -> None:
        """
        Set the audio encoder for transcoding streams

        :return:
        """
        codec = audio_codecs.grab_module(codec_name)
        self.audio_codec_transcoding = codec_name
        self.audio_encoder_transcoding = codec.codec_default_encoder()
