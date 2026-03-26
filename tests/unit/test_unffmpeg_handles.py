#!/usr/bin/env python3

"""
Tests for unffmpeg handle classes:
  - VideoCodecHandle
  - AudioCodecHandle
  - SubtitleHandle
  - HardwareAccelerationHandle
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.unffmpeg.audio_codec_handle import AudioCodecHandle
from compresso.libs.unffmpeg.hardware_acceleration_handle import HardwareAccelerationHandle
from compresso.libs.unffmpeg.subtitle_handle import SubtitleHandle
from compresso.libs.unffmpeg.video_codec_handle import VideoCodecHandle

# ===========================================================================
# Shared probe data helpers
# ===========================================================================


def _probe_video(codec_name="h264", index=0, tags=None):
    stream = {"codec_type": "video", "codec_name": codec_name, "index": index}
    if tags is not None:
        stream["tags"] = tags
    return stream


def _probe_audio(codec_name="aac", index=1, channels=2, tags=None):
    stream = {"codec_type": "audio", "codec_name": codec_name, "index": index, "channels": channels}
    if tags is not None:
        stream["tags"] = tags
    return stream


def _probe_subtitle(codec_name="srt", index=2):
    return {"codec_type": "subtitle", "codec_name": codec_name, "index": index}


# ===========================================================================
# VideoCodecHandle
# ===========================================================================


@pytest.mark.unittest
class TestVideoCodecHandle:
    def test_default_codec_and_encoder(self):
        handle = VideoCodecHandle({"streams": []})
        assert handle.video_codec == "h264"
        assert handle.video_encoder == "libx264"

    def test_args_encodes_video_when_codec_differs(self):
        probe = {"streams": [_probe_video("mpeg4", index=0)]}
        handle = VideoCodecHandle(probe)
        result = handle.args()
        assert "-map" in result["streams_to_map"]
        assert "0:0" in result["streams_to_map"]
        # Should encode, not copy
        assert "libx264" in result["streams_to_encode"]
        assert "copy" not in result["streams_to_encode"]

    def test_args_copies_when_codec_matches(self):
        probe = {"streams": [_probe_video("h264", index=0)]}
        handle = VideoCodecHandle(probe)
        result = handle.args()
        assert "copy" in result["streams_to_encode"]
        assert "libx264" not in result["streams_to_encode"]

    def test_args_copies_mjpeg_stream(self):
        probe = {"streams": [_probe_video("mjpeg", index=0)]}
        handle = VideoCodecHandle(probe)
        handle.video_codec = "hevc"  # target is different
        result = handle.args()
        assert "copy" in result["streams_to_encode"]

    def test_args_copies_when_mimetype_is_image_jpeg(self):
        probe = {"streams": [_probe_video("png", index=0, tags={"mimetype": "image/jpeg"})]}
        handle = VideoCodecHandle(probe)
        handle.video_codec = "hevc"
        result = handle.args()
        assert "copy" in result["streams_to_encode"]

    def test_args_copies_when_encoding_disabled(self):
        probe = {"streams": [_probe_video("mpeg4", index=0)]}
        handle = VideoCodecHandle(probe)
        handle.disable_video_encoding = True
        result = handle.args()
        assert "copy" in result["streams_to_encode"]

    def test_args_skips_non_video_streams(self):
        probe = {"streams": [_probe_audio("aac", index=0)]}
        handle = VideoCodecHandle(probe)
        result = handle.args()
        assert result["streams_to_map"] == []
        assert result["streams_to_encode"] == []

    def test_args_multiple_video_streams(self):
        probe = {
            "streams": [
                _probe_video("mpeg4", index=0),
                _probe_video("h264", index=1),
            ]
        }
        handle = VideoCodecHandle(probe)
        result = handle.args()
        # Stream 0 should encode (mpeg4 != h264), stream 1 should copy
        assert "-c:v:0" in result["streams_to_encode"]
        assert "-c:v:1" in result["streams_to_encode"]
        # First track encodes
        idx0 = result["streams_to_encode"].index("-c:v:0")
        assert result["streams_to_encode"][idx0 + 1] == "libx264"
        # Second track copies
        idx1 = result["streams_to_encode"].index("-c:v:1")
        assert result["streams_to_encode"][idx1 + 1] == "copy"

    @patch("compresso.libs.unffmpeg.video_codec_handle.video_codecs.grab_module")
    def test_set_video_codec_with_default_encoder(self, mock_grab):
        mock_module = MagicMock()
        mock_module.codec_default_encoder.return_value = "libx265"
        mock_grab.return_value = mock_module
        handle = VideoCodecHandle({"streams": []})
        handle.set_video_codec_with_default_encoder("hevc")
        assert handle.video_codec == "hevc"
        assert handle.video_encoder == "libx265"
        mock_grab.assert_called_once_with("hevc")


# ===========================================================================
# AudioCodecHandle
# ===========================================================================


@pytest.mark.unittest
class TestAudioCodecHandle:
    def test_default_settings(self):
        handle = AudioCodecHandle({"streams": []})
        assert handle.audio_codec_transcoding == "aac"
        assert handle.audio_encoder_transcoding == "aac"
        assert handle.enable_audio_stream_transcoding is False
        assert handle.enable_audio_stream_stereo_cloning is False

    def test_args_copies_audio_when_encoding_disabled(self):
        probe = {"streams": [_probe_audio("mp3", index=0)]}
        handle = AudioCodecHandle(probe)
        handle.disable_audio_encoding = True
        result = handle.args()
        assert "copy" in result["streams_to_encode"]
        assert "0:0" in result["streams_to_map"]

    def test_args_copies_when_no_transcoding_enabled(self):
        probe = {"streams": [_probe_audio("mp3", index=0)]}
        handle = AudioCodecHandle(probe)
        result = handle.args()
        assert "copy" in result["streams_to_encode"]

    def test_args_transcodes_when_codec_differs(self):
        probe = {"streams": [_probe_audio("mp3", index=0)]}
        handle = AudioCodecHandle(probe)
        handle.enable_audio_stream_transcoding = True
        handle.audio_codec_transcoding = "aac"
        handle.audio_encoder_transcoding = "aac"
        result = handle.args()
        assert "aac" in result["streams_to_encode"]
        assert "copy" not in result["streams_to_encode"]

    def test_args_copies_when_transcoding_enabled_but_codec_matches(self):
        probe = {"streams": [_probe_audio("aac", index=0)]}
        handle = AudioCodecHandle(probe)
        handle.enable_audio_stream_transcoding = True
        handle.audio_codec_transcoding = "aac"
        result = handle.args()
        assert "copy" in result["streams_to_encode"]

    def test_args_clones_stereo_when_channels_gt_2(self):
        probe = {"streams": [_probe_audio("aac", index=0, channels=6)]}
        handle = AudioCodecHandle(probe)
        handle.enable_audio_stream_stereo_cloning = True
        result = handle.args()
        # Original stream copied + cloned stream
        assert handle.audio_tracks_count == 2
        # Cloned stream should have bitrate and channel args
        assert "-ac:a:1" in result["streams_to_encode"]
        assert "2" in result["streams_to_encode"]

    def test_args_does_not_clone_stereo_when_channels_lte_2(self):
        probe = {"streams": [_probe_audio("aac", index=0, channels=2)]}
        handle = AudioCodecHandle(probe)
        handle.enable_audio_stream_stereo_cloning = True
        handle.args()
        assert handle.audio_tracks_count == 1

    def test_copy_stream_method(self):
        probe = {"streams": []}
        handle = AudioCodecHandle(probe)
        handle.encoding_args["streams_to_map"] = []
        handle.encoding_args["streams_to_encode"] = []
        stream = {"index": 3}
        handle.copy_stream(stream)
        assert "-c:a:0" in handle.encoding_args["streams_to_encode"]
        assert "copy" in handle.encoding_args["streams_to_encode"]
        assert "0:3" in handle.encoding_args["streams_to_map"]

    def test_transcode_stream_method(self):
        probe = {"streams": []}
        handle = AudioCodecHandle(probe)
        handle.encoding_args["streams_to_map"] = []
        handle.encoding_args["streams_to_encode"] = []
        handle.audio_encoder_transcoding = "libopus"
        stream = {"index": 1}
        handle.transcode_stream(stream)
        assert "-c:a:0" in handle.encoding_args["streams_to_encode"]
        assert "libopus" in handle.encoding_args["streams_to_encode"]

    def test_clone_stereo_stream_with_title_tag(self):
        probe = {"streams": []}
        handle = AudioCodecHandle(probe)
        handle.encoding_args["streams_to_map"] = []
        handle.encoding_args["streams_to_encode"] = []
        stream = {"index": 1, "tags": {"title": "Surround5.1"}}
        handle.clone_stereo_stream(stream)
        assert handle.audio_tracks_count == 1
        # Should have bitrate and channel count args
        assert "-b:a:0" in handle.encoding_args["streams_to_encode"]
        assert "-ac:a:0" in handle.encoding_args["streams_to_encode"]

    def test_clone_stereo_stream_without_tags(self):
        probe = {"streams": []}
        handle = AudioCodecHandle(probe)
        handle.encoding_args["streams_to_map"] = []
        handle.encoding_args["streams_to_encode"] = []
        stream = {"index": 1}
        handle.clone_stereo_stream(stream)
        # Should still work, using default 'Stereo' tag
        assert handle.audio_tracks_count == 1

    @patch("compresso.libs.unffmpeg.audio_codec_handle.audio_codecs.grab_module")
    def test_set_audio_codec_with_default_encoder_cloning(self, mock_grab):
        mock_module = MagicMock()
        mock_module.codec_default_encoder.return_value = "libopus"
        mock_grab.return_value = mock_module
        handle = AudioCodecHandle({"streams": []})
        handle.set_audio_codec_with_default_encoder_cloning("opus")
        assert handle.audio_codec_cloning == "opus"
        assert handle.audio_encoder_cloning == "libopus"

    @patch("compresso.libs.unffmpeg.audio_codec_handle.audio_codecs.grab_module")
    def test_set_audio_codec_with_default_encoder_transcoding(self, mock_grab):
        mock_module = MagicMock()
        mock_module.codec_default_encoder.return_value = "libfdk_aac"
        mock_grab.return_value = mock_module
        handle = AudioCodecHandle({"streams": []})
        handle.set_audio_codec_with_default_encoder_transcoding("aac")
        assert handle.audio_codec_transcoding == "aac"
        assert handle.audio_encoder_transcoding == "libfdk_aac"

    def test_args_skips_non_audio_streams(self):
        probe = {"streams": [_probe_video("h264", index=0)]}
        handle = AudioCodecHandle(probe)
        result = handle.args()
        assert result["streams_to_map"] == []
        assert result["streams_to_encode"] == []


# ===========================================================================
# SubtitleHandle
# ===========================================================================


@pytest.mark.unittest
class TestSubtitleHandle:
    def _make_container(self, supports_subs=True, supported=None, unsupported=None):
        container = MagicMock()
        container.container_supports_subtitles.return_value = supports_subs
        container.supported_subtitles.return_value = supported or ["srt", "ass"]
        container.unsupported_subtitles.return_value = unsupported or ["hdmv_pgs_subtitle"]
        return container

    def test_copies_supported_subtitle_stream(self):
        probe = {"streams": [_probe_subtitle("srt", index=2)]}
        container = self._make_container(supports_subs=True, supported=["srt", "ass"])
        handle = SubtitleHandle(probe, container)
        result = handle.args()
        assert "copy" in result["streams_to_encode"]
        assert "0:2" in result["streams_to_map"]

    def test_transcodes_unsupported_but_convertible_subtitle(self):
        probe = {"streams": [_probe_subtitle("mov_text", index=2)]}
        container = self._make_container(
            supports_subs=True,
            supported=["srt", "ass"],
            unsupported=["hdmv_pgs_subtitle"],
        )
        handle = SubtitleHandle(probe, container)
        result = handle.args()
        # Should use the first supported subtitle codec for transcoding
        assert "srt" in result["streams_to_encode"]

    def test_skips_unsupported_subtitle_in_unsupported_list(self):
        probe = {"streams": [_probe_subtitle("hdmv_pgs_subtitle", index=2)]}
        container = self._make_container(
            supports_subs=True,
            supported=["srt"],
            unsupported=["hdmv_pgs_subtitle"],
        )
        handle = SubtitleHandle(probe, container)
        result = handle.args()
        assert result["streams_to_map"] == []
        assert result["streams_to_encode"] == []

    def test_removes_subtitles_when_container_does_not_support(self):
        probe = {"streams": [_probe_subtitle("srt", index=2)]}
        container = self._make_container(supports_subs=False)
        handle = SubtitleHandle(probe, container)
        assert handle.remove_subtitle_streams is True
        result = handle.args()
        assert result["streams_to_map"] == []
        assert result["streams_to_encode"] == []

    def test_remove_subtitles_method(self):
        probe = {"streams": [_probe_subtitle("srt", index=2)]}
        container = self._make_container(supports_subs=True)
        handle = SubtitleHandle(probe, container)
        handle.remove_subtitles()
        assert handle.remove_subtitle_streams is True
        result = handle.args()
        assert result["streams_to_map"] == []

    def test_skips_non_subtitle_streams(self):
        probe = {"streams": [_probe_video("h264", index=0)]}
        container = self._make_container(supports_subs=True)
        handle = SubtitleHandle(probe, container)
        result = handle.args()
        assert result["streams_to_map"] == []
        assert result["streams_to_encode"] == []

    def test_multiple_subtitle_streams(self):
        probe = {
            "streams": [
                _probe_subtitle("srt", index=2),
                _probe_subtitle("ass", index=3),
            ]
        }
        container = self._make_container(supports_subs=True, supported=["srt", "ass"])
        handle = SubtitleHandle(probe, container)
        result = handle.args()
        assert "0:2" in result["streams_to_map"]
        assert "0:3" in result["streams_to_map"]


# ===========================================================================
# HardwareAccelerationHandle
# ===========================================================================


@pytest.mark.unittest
class TestHardwareAccelerationHandle:
    def test_default_state(self):
        handle = HardwareAccelerationHandle({"streams": []})
        assert handle.hardware_device is None
        assert handle.video_encoder is None
        assert handle.main_options == []
        assert handle.advanced_options == []
        assert handle.enable_hardware_accelerated_decoding is False

    def test_set_hwaccel_args_no_device(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.set_hwaccel_args()
        assert handle.main_options == []

    def test_set_hwaccel_args_cuda_device(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.hardware_device = {"hwaccel": "cuda", "hwaccel_device": "0"}
        handle.set_hwaccel_args()
        assert "-hwaccel" in handle.main_options
        assert "cuda" in handle.main_options
        assert "-hwaccel_device" in handle.main_options
        assert "0" in handle.main_options

    def test_set_hwaccel_args_vaapi_decode_only(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.hardware_device = {"hwaccel": "vaapi", "hwaccel_device": "/dev/dri/renderD128"}
        handle.set_hwaccel_args()
        assert "-hwaccel" in handle.main_options
        assert "vaapi" in handle.main_options
        assert "/dev/dri/renderD128" in handle.main_options

    def test_set_hwaccel_args_vaapi_with_vaapi_encoder_encode_only(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.hardware_device = {"hwaccel": "vaapi", "hwaccel_device": "/dev/dri/renderD128"}
        handle.video_encoder = "h264_vaapi"
        handle.enable_hardware_accelerated_decoding = False
        handle.set_hwaccel_args()
        assert "-vaapi_device" in handle.main_options
        assert "/dev/dri/renderD128" in handle.main_options
        assert "-vf" in handle.advanced_options

    def test_set_hwaccel_args_vaapi_with_vaapi_encoder_and_hw_decoding(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.hardware_device = {"hwaccel": "vaapi", "hwaccel_device": "/dev/dri/renderD128"}
        handle.video_encoder = "h264_vaapi"
        handle.enable_hardware_accelerated_decoding = True
        handle.set_hwaccel_args()
        assert "-init_hw_device" in handle.main_options
        assert "-hwaccel_output_format" in handle.main_options
        assert "-filter_hw_device" in handle.advanced_options

    @patch("compresso.libs.unffmpeg.hardware_acceleration_handle.HardwareAccelerationHandle.list_available_vaapi_devices")
    def test_set_hwaccel_args_auto_detects_vaapi_for_vaapi_encoder(self, mock_vaapi):
        mock_vaapi.return_value = [{"hwaccel": "vaapi", "hwaccel_device": "/dev/dri/renderD128"}]
        handle = HardwareAccelerationHandle({"streams": []})
        handle.video_encoder = "h264_vaapi"
        handle.hardware_device = None
        handle.set_hwaccel_args()
        # Should auto-detect and set vaapi args
        assert handle.hardware_device is not None
        assert len(handle.main_options) > 0

    @patch("compresso.libs.unffmpeg.hardware_acceleration_handle.HardwareAccelerationHandle.list_available_vaapi_devices")
    def test_set_hwaccel_args_no_auto_detect_for_non_vaapi_encoder(self, mock_vaapi):
        mock_vaapi.return_value = [{"hwaccel": "vaapi", "hwaccel_device": "/dev/dri/renderD128"}]
        handle = HardwareAccelerationHandle({"streams": []})
        handle.video_encoder = "libx264"
        handle.hardware_device = None
        handle.set_hwaccel_args()
        assert handle.main_options == []

    def test_update_main_options(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.main_options = ["-hwaccel", "cuda"]
        result = handle.update_main_options(["-i", "input.mp4"])
        assert result == ["-i", "input.mp4", "-hwaccel", "cuda"]

    def test_update_advanced_options(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.advanced_options = ["-vf", "format=nv12"]
        result = handle.update_advanced_options(["-preset", "fast"])
        assert result == ["-preset", "fast", "-vf", "format=nv12"]

    def test_generate_cuda_main_args(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.hardware_device = {"hwaccel": "cuda", "hwaccel_device": "1"}
        handle.generate_cuda_main_args()
        assert handle.main_options == ["-hwaccel", "cuda", "-hwaccel_device", "1"]

    def test_generate_vaapi_main_args_decode_only(self):
        handle = HardwareAccelerationHandle({"streams": []})
        handle.hardware_device = {"hwaccel": "vaapi", "hwaccel_device": "/dev/dri/renderD128"}
        handle.video_encoder = "libx264"  # non-vaapi encoder
        handle.generate_vaapi_main_args()
        assert handle.main_options == ["-hwaccel", "vaapi", "-hwaccel_device", "/dev/dri/renderD128"]

    @patch("compresso.libs.unffmpeg.hardware_acceleration_handle.ctypes.CDLL")
    def test_list_available_cuda_decoders_found(self, mock_cdll):
        cuda_mock = MagicMock()
        mock_cdll.return_value = cuda_mock
        cuda_mock.cuInit.return_value = 0

        def fake_get_count(byref_arg):
            byref_arg._obj.value = 2
            return 0

        cuda_mock.cuDeviceGetCount.side_effect = fake_get_count
        cuda_mock.cuDeviceGet.return_value = 0

        handle = HardwareAccelerationHandle({"streams": []})
        # We need to handle ctypes.byref properly; patch at a higher level
        with patch("compresso.libs.unffmpeg.hardware_acceleration_handle.ctypes") as mock_ctypes:
            mock_ctypes.CDLL.return_value = cuda_mock
            mock_ctypes.c_int.return_value = MagicMock(value=0)

            # Make nGpus value accessible
            n_gpus = MagicMock()
            n_gpus.value = 2
            device = MagicMock()

            call_count = [0]

            def c_int_factory():
                call_count[0] += 1
                if call_count[0] == 1:
                    return n_gpus
                return device

            mock_ctypes.c_int.side_effect = c_int_factory
            mock_ctypes.byref.side_effect = lambda x: x

            cuda_mock.cuInit.return_value = 0
            cuda_mock.cuDeviceGetCount.return_value = 0
            cuda_mock.cuDeviceGet.return_value = 0

            result = handle.list_available_cuda_decoders()
            assert len(result) == 2
            assert result[0]["hwaccel"] == "cuda"
            assert result[1]["hwaccel"] == "cuda"

    @patch("compresso.libs.unffmpeg.hardware_acceleration_handle.ctypes.CDLL")
    def test_list_available_cuda_decoders_no_cuda_lib(self, mock_cdll):
        mock_cdll.side_effect = OSError("not found")
        handle = HardwareAccelerationHandle({"streams": []})
        result = handle.list_available_cuda_decoders()
        assert result == []

    @patch("compresso.libs.unffmpeg.hardware_acceleration_handle.os.path.exists")
    @patch("compresso.libs.unffmpeg.hardware_acceleration_handle.os.listdir")
    def test_list_available_vaapi_devices_found(self, mock_listdir, mock_exists):
        mock_exists.return_value = True
        mock_listdir.return_value = ["card0", "renderD128", "renderD129"]
        handle = HardwareAccelerationHandle({"streams": []})
        result = handle.list_available_vaapi_devices()
        assert len(result) == 2
        assert result[0]["hwaccel"] == "vaapi"
        assert result[0]["hwaccel_device"] == os.path.join("/", "dev", "dri", "renderD128")
        assert result[1]["hwaccel_device"] == os.path.join("/", "dev", "dri", "renderD129")

    @patch("compresso.libs.unffmpeg.hardware_acceleration_handle.os.path.exists")
    def test_list_available_vaapi_devices_no_dri_dir(self, mock_exists):
        mock_exists.return_value = False
        handle = HardwareAccelerationHandle({"streams": []})
        result = handle.list_available_vaapi_devices()
        assert result == []

    @patch.object(HardwareAccelerationHandle, "list_available_cuda_decoders")
    @patch.object(HardwareAccelerationHandle, "list_available_vaapi_devices")
    def test_get_hwaccel_devices_combines_cuda_and_vaapi(self, mock_vaapi, mock_cuda):
        mock_cuda.return_value = [{"hwaccel": "cuda", "hwaccel_device": "0"}]
        mock_vaapi.return_value = [{"hwaccel": "vaapi", "hwaccel_device": "/dev/dri/renderD128"}]
        handle = HardwareAccelerationHandle({"streams": []})
        result = handle.get_hwaccel_devices()
        assert len(result) == 2
        assert result[0]["hwaccel"] == "cuda"
        assert result[1]["hwaccel"] == "vaapi"

    @patch.object(HardwareAccelerationHandle, "list_available_cuda_decoders")
    @patch.object(HardwareAccelerationHandle, "list_available_vaapi_devices")
    def test_get_hwaccel_devices_empty(self, mock_vaapi, mock_cuda):
        mock_cuda.return_value = []
        mock_vaapi.return_value = []
        handle = HardwareAccelerationHandle({"streams": []})
        result = handle.get_hwaccel_devices()
        assert result == []
