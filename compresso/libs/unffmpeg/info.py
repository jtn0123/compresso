#!/usr/bin/env python3

"""
compresso.main.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     21 Sep 2019, (2:08 PM)

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

from collections.abc import Sequence
from typing import TypedDict

from . import audio_codecs, subtitle_codecs, video_codecs
from .base_codecs import CodecDescription
from .lib import cli
from .probe import Probe


class EncoderDescription(TypedDict):
    capabilities: str
    description: str


type EncoderIndex = dict[str, EncoderDescription]


class AvailableEncoders(TypedDict):
    audio: EncoderIndex
    subtitle: EncoderIndex
    video: EncoderIndex


class SupportedCodecs(TypedDict):
    audio: dict[str, CodecDescription]
    subtitle: dict[str, CodecDescription]
    video: dict[str, CodecDescription]


class Info:
    """
    Info

    Provide information on FFMPEG commands and configuration
    """

    available_encoders: AvailableEncoders | None = None
    available_decoders: AvailableEncoders | None = None

    @staticmethod
    def versions() -> dict[str, object]:
        """
        Return the system ffmpeg version as a string

        :return:
        """
        return cli.ffmpeg_version_info()

    def file_probe(self, vid_file_path: str) -> dict[str, object]:
        """
        Probe a media file and return the result dictionary.

        Thin compatibility wrapper around :class:`Probe`. New code
        should call ``Probe.file(path)`` directly; this stays on
        ``Info`` so existing callers keep working.
        """
        return Probe.file(vid_file_path)

    @staticmethod
    def _parse_codec_listing(info: str) -> AvailableEncoders:
        available = AvailableEncoders(audio={}, subtitle={}, video={})
        headers = {"A..... = Audio", "S..... = Subtitle", "V..... = Video"}
        for raw_line in info.splitlines():
            line = raw_line.strip()
            if not line or line in headers:
                continue
            if line[0] == "A":
                codec_index = available["audio"]
            elif line[0] == "S":
                codec_index = available["subtitle"]
            elif line[0] == "V":
                codec_index = available["video"]
            else:
                continue
            data = line.split()
            if len(data) < 2:
                continue
            capabilities, codec, *description = data
            codec_index[codec] = EncoderDescription(capabilities=capabilities, description=" ".join(description))
        return available

    def get_available_ffmpeg_encoders(self) -> AvailableEncoders:
        """
        Sets a dictionary of encoders supported by ffmpeg
        """
        # Get raw ffmpeg output of available encoders
        info = cli.ffmpeg_available_encoders()
        self.available_encoders = self._parse_codec_listing(info)

        return self.available_encoders

    def get_available_ffmpeg_decoders(self) -> AvailableEncoders:
        """
        Sets a dictionary of decoders supported by ffmpeg
        """
        # Get raw ffmpeg output of available decoders
        info = cli.ffmpeg_available_decoders()
        self.available_decoders = self._parse_codec_listing(info)

        return self.available_decoders

    def get_available_ffmpeg_hw_acceleration_methods(self) -> list[str]:
        methods: list[str] = []

        # Get raw ffmpeg output of available encoders
        info = cli.ffmpeg_available_hw_acceleration_methods()

        # Sort through the lines and create a list of methods
        for line in info.splitlines():
            line = line.rstrip().lstrip()
            if not line or line.startswith("Hardware acceleration"):
                continue
            else:
                methods.append(line)

        return methods

    def get_ffmpeg_audio_encoders(self) -> EncoderIndex:
        """
        Fetch all audio encoders supported by ffmpeg

        :return:
        """
        if self.available_encoders is None:
            self.get_available_ffmpeg_encoders()
        return self.available_encoders["audio"] if self.available_encoders is not None else {}

    def get_ffmpeg_subtitle_encoders(self) -> EncoderIndex:
        """
        Fetch all subtitle encoders supported by ffmpeg

        :return:
        """
        if self.available_encoders is None:
            self.get_available_ffmpeg_encoders()
        return self.available_encoders["subtitle"] if self.available_encoders is not None else {}

    def get_ffmpeg_video_encoders(self) -> EncoderIndex:
        """
        Fetch all video encoders supported by ffmpeg

        :return:
        """
        if self.available_encoders is None:
            self.get_available_ffmpeg_encoders()
        return self.available_encoders["video"] if self.available_encoders is not None else {}

    def filter_available_encoders_for_codec(self, codec_encoders: Sequence[str], codec_type: str) -> list[str]:
        """
        Filter a given list of encoders. Removes any that are not available with FFMPEG

        :param codec_type:
        :param codec_encoders:
        :return:
        """
        available_encoders: EncoderIndex = {}
        if codec_type == "audio":
            available_encoders = self.get_ffmpeg_audio_encoders()
        elif codec_type == "subtitle":
            available_encoders = self.get_ffmpeg_subtitle_encoders()
        elif codec_type == "video":
            available_encoders = self.get_ffmpeg_video_encoders()
        # Build a new list rather than mutating in place: removing while iterating
        # skips the element after each removal, and the input list is the codec
        # class attribute shared across calls.
        return [encoder for encoder in codec_encoders if encoder in available_encoders]

    def get_all_supported_codecs_of_type(self, codec_type: str) -> dict[str, CodecDescription]:
        """
        Fetch a list of supported codecs and
        return a dictionary of their data

        :return:
        """
        codec_dict: dict[str, CodecDescription] = {}
        return_codec_dict: dict[str, CodecDescription] = {}
        if codec_type == "audio":
            codec_dict = audio_codecs.get_all_audio_codecs()
        elif codec_type == "subtitle":
            codec_dict = subtitle_codecs.get_all_subtitle_codecs()
        elif codec_type == "video":
            codec_dict = video_codecs.get_all_video_codecs()
        # Iterate through the list of codecs.
        for codec_name in codec_dict:
            codec = codec_dict[codec_name]
            # Get list of encoders for this codec that are available in ffmpeg
            codec_encoders = self.filter_available_encoders_for_codec(codec["encoders"], codec_type)
            # Check if any encoders were found
            if not codec_encoders:
                continue
            # At least one encoder is found for that codec.
            # Add codec to codec_list if one encoder exists
            return_codec_dict[codec_name] = codec
        return return_codec_dict

    def get_all_supported_video_codecs(self) -> dict[str, CodecDescription]:
        """
        Fetch a list of supported video codecs and
        return a dictionary of their data

        :return:
        """
        return_codec_dict: dict[str, CodecDescription] = {}
        codec_dict = video_codecs.get_all_video_codecs()
        for codec_name in codec_dict:
            codec = codec_dict[codec_name]
            # Get list of encoders for this codec that are available in ffmpeg
            codec_encoders = self.filter_available_encoders_for_codec(codec["encoders"], "video")
            # Check if any encoders were found
            if not codec_encoders:
                continue
            # At least one encoder is found for that codec.
            # Add codec to codec_list if one encoder exists
            return_codec_dict[codec_name] = codec
        return return_codec_dict

    def get_all_supported_codecs(self) -> SupportedCodecs:
        supported_audio_codecs = self.get_all_supported_codecs_of_type("audio")
        supported_subtitle_codecs = self.get_all_supported_codecs_of_type("subtitle")
        supported_video_codecs = self.get_all_supported_codecs_of_type("video")

        # Combine dictionaries into one and return
        return SupportedCodecs(
            audio=supported_audio_codecs,
            subtitle=supported_subtitle_codecs,
            video=supported_video_codecs,
        )
