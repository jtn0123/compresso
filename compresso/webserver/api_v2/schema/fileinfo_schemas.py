#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.fileinfo_schemas.py

    Marshmallow schemas for File Info API endpoints.

"""

from marshmallow import fields
from compresso.webserver.api_v2.schema.schemas import BaseSchema, BaseSuccessSchema


class RequestFileInfoProbeSchema(BaseSchema):
    """Schema for probing a file by path"""
    file_path = fields.Str(
        required=True,
        metadata={'description': "Absolute path to the media file to probe"},
    )


class RequestFileInfoTaskSchema(BaseSchema):
    """Schema for probing a file from a task"""
    task_id = fields.Int(
        required=True,
        metadata={'description': "Completed task ID to probe"},
    )


class VideoStreamSchema(BaseSchema):
    """Schema for a video stream"""
    index = fields.Int()
    codec_name = fields.Str()
    codec_long_name = fields.Str()
    profile = fields.Str()
    width = fields.Int()
    height = fields.Int()
    pix_fmt = fields.Str()
    bit_rate = fields.Int()
    r_frame_rate = fields.Str()
    avg_frame_rate = fields.Str()
    duration = fields.Float()
    nb_frames = fields.Int()
    color_space = fields.Str()
    color_transfer = fields.Str()
    color_primaries = fields.Str()
    hdr = fields.Boolean()
    resolution_label = fields.Str()


class AudioStreamSchema(BaseSchema):
    """Schema for an audio stream"""
    index = fields.Int()
    codec_name = fields.Str()
    codec_long_name = fields.Str()
    profile = fields.Str()
    sample_rate = fields.Int()
    channels = fields.Int()
    channel_layout = fields.Str()
    bit_rate = fields.Int()
    duration = fields.Float()
    language = fields.Str()
    title = fields.Str()


class SubtitleStreamSchema(BaseSchema):
    """Schema for a subtitle stream"""
    index = fields.Int()
    codec_name = fields.Str()
    codec_long_name = fields.Str()
    profile = fields.Str()
    language = fields.Str()
    title = fields.Str()


class FormatInfoSchema(BaseSchema):
    """Schema for format info"""
    filename = fields.Str()
    format_name = fields.Str()
    format_long_name = fields.Str()
    duration = fields.Float()
    size = fields.Int()
    bit_rate = fields.Int()
    nb_streams = fields.Int()


class FileInfoResponseSchema(BaseSuccessSchema):
    """Schema for file info probe response"""
    video_streams = fields.List(fields.Raw())
    audio_streams = fields.List(fields.Raw())
    subtitle_streams = fields.List(fields.Raw())
    format = fields.Raw()
