#!/usr/bin/env python3

"""
Tests for compresso.libs.unffmpeg.info.Info class.
All cli.* functions are mocked so no subprocess calls occur.
"""

from unittest.mock import patch

import pytest

from compresso.libs.unffmpeg.info import Info

# ---------------------------------------------------------------------------
# Realistic raw ffmpeg output used in multiple tests
# ---------------------------------------------------------------------------

ENCODER_OUTPUT = (
    " Encoders:\n"
    " V..... = Video\n"
    " A..... = Audio\n"
    " S..... = Subtitle\n"
    " ------\n"
    " V..... libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)\n"
    " V..... h264_nvenc           NVIDIA NVENC H.264 encoder (codec h264)\n"
    " V..... libx265              libx265 H.265 / HEVC (codec hevc)\n"
    " A..... aac                  AAC (Advanced Audio Coding) (codec aac)\n"
    " A..... libmp3lame           libmp3lame MP3 (codec mp3)\n"
    " S..... srt                  SubRip subtitle (codec subrip)\n"
    " S..... ass                  ASS subtitle (codec ass)\n"
)

DECODER_OUTPUT = (
    " Decoders:\n"
    " V..... = Video\n"
    " A..... = Audio\n"
    " S..... = Subtitle\n"
    " ------\n"
    " V..... h264                 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10\n"
    " V..... hevc                 HEVC (High Efficiency Video Coding)\n"
    " A..... aac                  AAC (Advanced Audio Coding)\n"
    " A..... mp3                  MP3 (MPEG audio layer 3)\n"
    " S..... srt                  SubRip subtitle\n"
)

HWACCEL_OUTPUT = "Hardware acceleration methods:\nvdpau\ncuda\nvaapi\n"


# ---------------------------------------------------------------------------
# Info.versions
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestInfoVersions:
    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_version_info")
    def test_versions_returns_cli_result(self, mock_ver):
        expected = {"program_version": {"version": "4.3.1"}}
        mock_ver.return_value = expected
        assert Info.versions() == expected
        mock_ver.assert_called_once()


# ---------------------------------------------------------------------------
# Info.file_probe
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestInfoFileProbe:
    @patch("compresso.libs.unffmpeg.info.cli.ffprobe_file")
    def test_file_probe_delegates_to_cli(self, mock_probe):
        probe_data = {"streams": [], "format": {}}
        mock_probe.return_value = probe_data
        info = Info()
        result = info.file_probe("/some/file.mkv")
        assert result == probe_data
        mock_probe.assert_called_once_with("/some/file.mkv")


# ---------------------------------------------------------------------------
# Info.get_available_ffmpeg_encoders
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetAvailableEncoders:
    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_parses_video_encoders(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_encoders()
        assert "libx264" in result["video"]
        assert "h264_nvenc" in result["video"]
        assert "libx265" in result["video"]

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_parses_audio_encoders(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_encoders()
        assert "aac" in result["audio"]
        assert "libmp3lame" in result["audio"]

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_parses_subtitle_encoders(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_encoders()
        assert "srt" in result["subtitle"]
        assert "ass" in result["subtitle"]

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_encoder_has_capabilities_and_description(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_encoders()
        libx264 = result["video"]["libx264"]
        assert "capabilities" in libx264
        assert "description" in libx264
        assert libx264["capabilities"] == "V....."

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_skips_header_lines(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_encoders()
        # The header "V..... = Video" should not appear as an encoder key
        for section in result.values():
            assert "=" not in section

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_empty_output_returns_empty_dicts(self, mock_enc):
        mock_enc.return_value = ""
        info = Info()
        result = info.get_available_ffmpeg_encoders()
        assert result == {"audio": {}, "subtitle": {}, "video": {}}

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_sets_available_encoders_attribute(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        assert info.available_encoders is None
        info.get_available_ffmpeg_encoders()
        assert info.available_encoders is not None


# ---------------------------------------------------------------------------
# Info.get_available_ffmpeg_decoders
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetAvailableDecoders:
    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_decoders")
    def test_parses_video_decoders(self, mock_dec):
        mock_dec.return_value = DECODER_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_decoders()
        assert "h264" in result["video"]
        assert "hevc" in result["video"]

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_decoders")
    def test_parses_audio_decoders(self, mock_dec):
        mock_dec.return_value = DECODER_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_decoders()
        assert "aac" in result["audio"]
        assert "mp3" in result["audio"]

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_decoders")
    def test_parses_subtitle_decoders(self, mock_dec):
        mock_dec.return_value = DECODER_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_decoders()
        assert "srt" in result["subtitle"]

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_decoders")
    def test_sets_available_decoders_attribute(self, mock_dec):
        mock_dec.return_value = DECODER_OUTPUT
        info = Info()
        info.get_available_ffmpeg_decoders()
        assert info.available_decoders is not None


# ---------------------------------------------------------------------------
# Info.get_available_ffmpeg_hw_acceleration_methods
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetHwAccelMethods:
    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_hw_acceleration_methods")
    def test_parses_methods(self, mock_hw):
        mock_hw.return_value = HWACCEL_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_hw_acceleration_methods()
        assert "vdpau" in result
        assert "cuda" in result
        assert "vaapi" in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_hw_acceleration_methods")
    def test_skips_header_line(self, mock_hw):
        mock_hw.return_value = HWACCEL_OUTPUT
        info = Info()
        result = info.get_available_ffmpeg_hw_acceleration_methods()
        assert "Hardware acceleration methods:" not in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_hw_acceleration_methods")
    def test_empty_output_returns_empty_list(self, mock_hw):
        mock_hw.return_value = ""
        info = Info()
        result = info.get_available_ffmpeg_hw_acceleration_methods()
        assert result == []


# ---------------------------------------------------------------------------
# Lazy-loading wrappers: get_ffmpeg_audio/video/subtitle_encoders
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestLazyEncoderWrappers:
    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_get_ffmpeg_audio_encoders_lazy_loads(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        assert info.available_encoders is None
        result = info.get_ffmpeg_audio_encoders()
        assert "aac" in result
        # Should now be cached
        assert info.available_encoders is not None

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_get_ffmpeg_video_encoders_lazy_loads(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        result = info.get_ffmpeg_video_encoders()
        assert "libx264" in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_get_ffmpeg_subtitle_encoders_lazy_loads(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        result = info.get_ffmpeg_subtitle_encoders()
        assert "srt" in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_does_not_reload_if_already_cached(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        info.get_ffmpeg_audio_encoders()
        info.get_ffmpeg_video_encoders()
        info.get_ffmpeg_subtitle_encoders()
        # get_available_ffmpeg_encoders should only be called once
        mock_enc.assert_called_once()


# ---------------------------------------------------------------------------
# Info.filter_available_encoders_for_codec
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFilterAvailableEncoders:
    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_filters_out_unavailable_encoders(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        # "libx264" is available, "nonexistent_encoder" is not
        codec_encoders = ["libx264", "nonexistent_encoder"]
        result = info.filter_available_encoders_for_codec(codec_encoders, "video")
        assert "libx264" in result
        assert "nonexistent_encoder" not in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_filters_audio_encoders(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        codec_encoders = ["aac", "fake_encoder"]
        result = info.filter_available_encoders_for_codec(codec_encoders, "audio")
        assert "aac" in result
        assert "fake_encoder" not in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_filters_subtitle_encoders(self, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        codec_encoders = ["srt", "missing"]
        result = info.filter_available_encoders_for_codec(codec_encoders, "subtitle")
        assert "srt" in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    def test_all_unavailable_filters_what_it_can(self, mock_enc):
        """
        Note: the source code modifies the list while iterating, so not all
        unavailable entries are removed in a single pass.  We test the actual
        behaviour here (single unavailable encoder is fully removed).
        """
        mock_enc.return_value = ENCODER_OUTPUT
        info = Info()
        codec_encoders = ["fake_only"]
        result = info.filter_available_encoders_for_codec(codec_encoders, "video")
        assert result == []


# ---------------------------------------------------------------------------
# Info.get_all_supported_codecs_of_type / get_all_supported_video_codecs / get_all_supported_codecs
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetAllSupportedCodecs:
    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    @patch("compresso.libs.unffmpeg.info.video_codecs.get_all_video_codecs")
    def test_get_all_supported_codecs_of_type_video(self, mock_get_codecs, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        mock_get_codecs.return_value = {
            "h264": {
                "name": "h264",
                "encoders": ["libx264", "h264_nvenc"],
                "default_encoder": "libx264",
                "description": "H.264",
            },
            "fakevid": {
                "name": "fakevid",
                "encoders": ["fake_only"],
                "default_encoder": "fake_only",
                "description": "Fake",
            },
        }
        info = Info()
        result = info.get_all_supported_codecs_of_type("video")
        # h264 should be present (libx264 is available), fakevid should be absent
        assert "h264" in result
        assert "fakevid" not in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    @patch("compresso.libs.unffmpeg.info.audio_codecs.get_all_audio_codecs")
    def test_get_all_supported_codecs_of_type_audio(self, mock_get_codecs, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        mock_get_codecs.return_value = {
            "aac": {
                "name": "aac",
                "encoders": ["aac"],
                "default_encoder": "aac",
                "description": "AAC",
            },
        }
        info = Info()
        result = info.get_all_supported_codecs_of_type("audio")
        assert "aac" in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    @patch("compresso.libs.unffmpeg.info.video_codecs.get_all_video_codecs")
    def test_get_all_supported_video_codecs(self, mock_get_codecs, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        mock_get_codecs.return_value = {
            "hevc": {
                "name": "hevc",
                "encoders": ["libx265"],
                "default_encoder": "libx265",
                "description": "HEVC",
            },
        }
        info = Info()
        result = info.get_all_supported_video_codecs()
        assert "hevc" in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    @patch("compresso.libs.unffmpeg.info.subtitle_codecs.get_all_subtitle_codecs")
    def test_get_all_supported_codecs_of_type_subtitle(self, mock_get_codecs, mock_enc):
        """Verify subtitle codec type calls subtitle_codecs, not audio_codecs."""
        mock_enc.return_value = ENCODER_OUTPUT
        mock_get_codecs.return_value = {
            "srt": {
                "name": "srt",
                "encoders": ["srt"],
                "default_encoder": "srt",
                "description": "SubRip subtitle",
            },
        }
        info = Info()
        result = info.get_all_supported_codecs_of_type("subtitle")
        mock_get_codecs.assert_called_once()
        assert "srt" in result

    @patch("compresso.libs.unffmpeg.info.cli.ffmpeg_available_encoders")
    @patch("compresso.libs.unffmpeg.info.video_codecs.get_all_video_codecs")
    @patch("compresso.libs.unffmpeg.info.subtitle_codecs.get_all_subtitle_codecs")
    @patch("compresso.libs.unffmpeg.info.audio_codecs.get_all_audio_codecs")
    def test_get_all_supported_codecs_combines_audio_video_and_subtitle(self, mock_audio, mock_subtitle, mock_video, mock_enc):
        mock_enc.return_value = ENCODER_OUTPUT
        mock_video.return_value = {
            "h264": {
                "name": "h264",
                "encoders": ["libx264"],
                "default_encoder": "libx264",
                "description": "H.264",
            },
        }
        mock_audio.return_value = {
            "aac": {
                "name": "aac",
                "encoders": ["aac"],
                "default_encoder": "aac",
                "description": "AAC",
            },
        }
        mock_subtitle.return_value = {
            "srt": {
                "name": "srt",
                "encoders": ["srt"],
                "default_encoder": "srt",
                "description": "SubRip subtitle",
            },
        }
        info = Info()
        result = info.get_all_supported_codecs()
        assert "audio" in result
        assert "video" in result
        assert "subtitle" in result
        assert "aac" in result["audio"]
        assert "h264" in result["video"]
        assert "srt" in result["subtitle"]
