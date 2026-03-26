#!/usr/bin/env python3

"""
    Phase 1: Tests for unffmpeg data classes — containers, codecs, subtitles, exceptions, base classes.
"""

import pytest

# ──────────────────────── Base Codecs ────────────────────────
from compresso.libs.unffmpeg.base_codecs import Codecs


@pytest.mark.unittest
class TestBaseCodecs:
    def test_default_attributes(self):
        c = Codecs()
        assert c.name == ''
        assert c.encoders == []
        assert c.default_encoder == ''
        assert c.codec_long_name == ''

    def test_codec_name(self):
        c = Codecs()
        c.name = 'test_codec'
        assert c.codec_name() == 'test_codec'

    def test_codec_encoders(self):
        c = Codecs()
        c.encoders = ['enc1', 'enc2']
        assert c.codec_encoders() == ['enc1', 'enc2']

    def test_codec_default_encoder(self):
        c = Codecs()
        c.default_encoder = 'enc1'
        assert c.codec_default_encoder() == 'enc1'

    def test_codec_description(self):
        c = Codecs()
        c.codec_long_name = 'A long name'
        assert c.codec_description() == 'A long name'


# ──────────────────────── Base Containers ────────────────────────

from compresso.libs.unffmpeg.base_containers import Containers


@pytest.mark.unittest
class TestBaseContainers:
    def test_container_extension(self):
        c = Containers()
        c.extension = 'mp4'
        assert c.container_extension() == 'mp4'

    def test_container_description(self):
        c = Containers()
        c.description = 'Test Container'
        assert c.container_description() == 'Test Container'

    def test_container_supports_subtitles_true(self):
        c = Containers()
        c.supports_subtitles = True
        assert c.container_supports_subtitles() is True

    def test_container_supports_subtitles_false(self):
        c = Containers()
        c.supports_subtitles = False
        assert c.container_supports_subtitles() is False

    def test_container_supports_subtitles_no_attr(self):
        c = Containers()
        assert c.container_supports_subtitles() is False

    def test_supported_subtitles_when_supported(self):
        c = Containers()
        c.supports_subtitles = True
        c.subtitle_codecs = ['srt', 'ass']
        assert c.supported_subtitles() == ['srt', 'ass']

    def test_supported_subtitles_when_not_supported(self):
        c = Containers()
        c.supports_subtitles = False
        assert c.supported_subtitles() == []

    def test_unsupported_subtitles_default(self):
        c = Containers()
        assert c.unsupported_subtitles() == ['hdmv_pgs_subtitle']

    def test_unsupported_subtitles_bug_attribute_mismatch(self):
        """Bug: unsupported_subtitles() checks 'unsupports_codecs' but reads 'unsubtitle_codecs'.
        Setting 'unsupports_codecs' without 'unsubtitle_codecs' should raise AttributeError.
        """
        c = Containers()
        c.unsupports_codecs = True
        with pytest.raises(AttributeError):
            c.unsupported_subtitles()

    def test_unsupported_subtitles_with_both_attrs(self):
        """When both attributes are set, returns unsubtitle_codecs."""
        c = Containers()
        c.unsupports_codecs = True
        c.unsubtitle_codecs = ['dvbsub']
        assert c.unsupported_subtitles() == ['dvbsub']


# ──────────────────────── Exceptions ────────────────────────

from compresso.libs.unffmpeg.exceptions.ffmpeg import FFMpegError
from compresso.libs.unffmpeg.exceptions.ffprobe import FFProbeError


@pytest.mark.unittest
class TestFFMpegError:
    def test_message_format(self):
        err = FFMpegError(['ffmpeg', '-i', 'test.mp4'], 'codec error')
        assert 'ffmpeg -i test.mp4' in str(err)
        assert 'codec error' in str(err)

    def test_attributes(self):
        cmd = ['ffmpeg', '-v']
        err = FFMpegError(cmd, 'some info')
        assert err.path == cmd
        assert err.info == 'some info'

    def test_is_exception(self):
        err = FFMpegError(['cmd'], 'info')
        assert isinstance(err, Exception)


@pytest.mark.unittest
class TestFFProbeError:
    def test_message_format(self):
        err = FFProbeError('/path/to/file.mp4', 'no streams')
        assert '/path/to/file.mp4' in str(err)
        assert 'no streams' in str(err)

    def test_attributes(self):
        err = FFProbeError('/some/path', 'detail')
        assert err.path == '/some/path'
        assert err.info == 'detail'

    def test_is_exception(self):
        err = FFProbeError('/p', 'i')
        assert isinstance(err, Exception)


# ──────────────────────── Video Codecs ────────────────────────

from compresso.libs.unffmpeg.video_codecs.h264 import H264
from compresso.libs.unffmpeg.video_codecs.hevc import Hevc

VIDEO_CODECS = [
    (H264, 'h264', 'libx264', ['h264_nvenc', 'h264_vaapi', 'libx264', 'libx264rgb'],
     'H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10'),
    (Hevc, 'hevc', 'libx265', ['hevc_nvenc', 'hevc_vaapi', 'libx265'],
     'HEVC (High Efficiency Video Coding)'),
]


@pytest.mark.unittest
class TestVideoCodecs:
    @pytest.mark.parametrize("cls,name,default,encoders,long_name", VIDEO_CODECS)
    def test_codec_name(self, cls, name, default, encoders, long_name):
        assert cls().codec_name() == name

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", VIDEO_CODECS)
    def test_codec_default_encoder(self, cls, name, default, encoders, long_name):
        assert cls().codec_default_encoder() == default

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", VIDEO_CODECS)
    def test_codec_encoders(self, cls, name, default, encoders, long_name):
        assert cls().codec_encoders() == encoders

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", VIDEO_CODECS)
    def test_codec_description(self, cls, name, default, encoders, long_name):
        assert cls().codec_description() == long_name

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", VIDEO_CODECS)
    def test_inherits_codecs(self, cls, name, default, encoders, long_name):
        assert isinstance(cls(), Codecs)


# ──────────────────────── Audio Codecs ────────────────────────

from compresso.libs.unffmpeg.audio_codecs.aac import Aac
from compresso.libs.unffmpeg.audio_codecs.ac3 import Ac3
from compresso.libs.unffmpeg.audio_codecs.mp3 import Mp3

AUDIO_CODECS = [
    (Aac, 'aac', 'aac', ['aac'], 'AAC (Advanced Audio Coding)'),
    (Ac3, 'ac3', 'ac3', ['ac3'], 'ATSC A/52A (AC-3)'),
    (Mp3, 'mp3', 'libmp3lame', ['libmp3lame'], 'MP3 (MPEG audio layer 3)'),
]


@pytest.mark.unittest
class TestAudioCodecs:
    @pytest.mark.parametrize("cls,name,default,encoders,long_name", AUDIO_CODECS)
    def test_codec_name(self, cls, name, default, encoders, long_name):
        assert cls().codec_name() == name

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", AUDIO_CODECS)
    def test_codec_default_encoder(self, cls, name, default, encoders, long_name):
        assert cls().codec_default_encoder() == default

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", AUDIO_CODECS)
    def test_codec_encoders(self, cls, name, default, encoders, long_name):
        assert cls().codec_encoders() == encoders

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", AUDIO_CODECS)
    def test_codec_description(self, cls, name, default, encoders, long_name):
        assert cls().codec_description() == long_name

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", AUDIO_CODECS)
    def test_inherits_codecs(self, cls, name, default, encoders, long_name):
        assert isinstance(cls(), Codecs)


# ──────────────────────── Subtitle Codecs ────────────────────────

from compresso.libs.unffmpeg.subtitle_codecs.ass import Ass
from compresso.libs.unffmpeg.subtitle_codecs.mov_text import MovText
from compresso.libs.unffmpeg.subtitle_codecs.srt import Srt
from compresso.libs.unffmpeg.subtitle_codecs.ssa import Ssa
from compresso.libs.unffmpeg.subtitle_codecs.subrip import Subrip
from compresso.libs.unffmpeg.subtitle_codecs.xsub import Xsub

SUBTITLE_CODECS = [
    (Ass, 'ass', 'ass', ['ass'], 'ASS (Advanced SubStation Alpha) subtitle'),
    (MovText, 'mov_text', 'mov_text', ['mov_text'], '3GPP Timed Text subtitle'),
    (Srt, 'srt', 'srt', ['srt'], 'SubRip subtitle (codec subrip)'),
    (Ssa, 'ssa', 'ssa', ['ssa'], 'ASS (Advanced SubStation Alpha) subtitle (codec ass)'),
    (Subrip, 'subrip', 'subrip', ['subrip'], 'SubRip subtitle'),
    (Xsub, 'xsub', 'xsub', ['xsub'], 'DivX subtitles (XSUB)'),
]


@pytest.mark.unittest
class TestSubtitleCodecs:
    @pytest.mark.parametrize("cls,name,default,encoders,long_name", SUBTITLE_CODECS)
    def test_codec_name(self, cls, name, default, encoders, long_name):
        assert cls().codec_name() == name

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", SUBTITLE_CODECS)
    def test_codec_default_encoder(self, cls, name, default, encoders, long_name):
        assert cls().codec_default_encoder() == default

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", SUBTITLE_CODECS)
    def test_codec_encoders(self, cls, name, default, encoders, long_name):
        assert cls().codec_encoders() == encoders

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", SUBTITLE_CODECS)
    def test_codec_description(self, cls, name, default, encoders, long_name):
        assert cls().codec_description() == long_name

    @pytest.mark.parametrize("cls,name,default,encoders,long_name", SUBTITLE_CODECS)
    def test_inherits_codecs(self, cls, name, default, encoders, long_name):
        assert isinstance(cls(), Codecs)


# ──────────────────────── Containers ────────────────────────

from compresso.libs.unffmpeg.containers.avi import Avi
from compresso.libs.unffmpeg.containers.flv import Flv
from compresso.libs.unffmpeg.containers.matroska import Matroska
from compresso.libs.unffmpeg.containers.mov import Mov
from compresso.libs.unffmpeg.containers.mp4 import Mp4
from compresso.libs.unffmpeg.containers.mpeg import Mpeg
from compresso.libs.unffmpeg.containers.mpegts import Mpegts
from compresso.libs.unffmpeg.containers.ogv import Ogv
from compresso.libs.unffmpeg.containers.psp import Psp
from compresso.libs.unffmpeg.containers.vob import Vob

CONTAINERS = [
    (Mp4, 'mp4', 'MP4 (MPEG-4 Part 14)', True,
     ['mov_text', 'srt', 'ass', 'ssa', 'dvbsub', 'dvdsub']),
    (Matroska, 'mkv', 'Matroska', True,
     ['ass', 'dvbsub', 'dvd_subtitle', 'dvdsub', 'srt', 'ssa', 'subrip']),
    (Avi, 'avi', 'AVI (Audio Video Interleaved)', True, ['xsub']),
    (Mov, 'mov', 'QuickTime / MOV', True, ['mov_text']),
    (Flv, 'flv', 'FLV (Flash Video)', False, []),
    (Vob, 'vob', 'MPEG-2 PS (VOB)', False, []),
    (Ogv, 'ogv', 'Ogg Video', False, []),
    (Mpeg, 'mpeg', 'MPEG-1 Systems / MPEG program stream', True, ['mov_text']),
    (Mpegts, 'ts', 'MPEG-TS (MPEG-2 Transport Stream)', False, []),
    (Psp, 'psp', 'PSP MP4 (MPEG-4 Part 14)', False, []),
]


@pytest.mark.unittest
class TestContainers:
    @pytest.mark.parametrize("cls,ext,desc,subs,sub_codecs", CONTAINERS)
    def test_container_extension(self, cls, ext, desc, subs, sub_codecs):
        assert cls().container_extension() == ext

    @pytest.mark.parametrize("cls,ext,desc,subs,sub_codecs", CONTAINERS)
    def test_container_description(self, cls, ext, desc, subs, sub_codecs):
        assert cls().container_description() == desc

    @pytest.mark.parametrize("cls,ext,desc,subs,sub_codecs", CONTAINERS)
    def test_container_supports_subtitles(self, cls, ext, desc, subs, sub_codecs):
        assert cls().container_supports_subtitles() is subs

    @pytest.mark.parametrize("cls,ext,desc,subs,sub_codecs", CONTAINERS)
    def test_supported_subtitles(self, cls, ext, desc, subs, sub_codecs):
        result = cls().supported_subtitles()
        if subs:
            assert result == sub_codecs
        else:
            assert result == []

    @pytest.mark.parametrize("cls,ext,desc,subs,sub_codecs", CONTAINERS)
    def test_inherits_containers(self, cls, ext, desc, subs, sub_codecs):
        assert isinstance(cls(), Containers)

    @pytest.mark.parametrize("cls,ext,desc,subs,sub_codecs", CONTAINERS)
    def test_unsupported_subtitles_defaults(self, cls, ext, desc, subs, sub_codecs):
        result = cls().unsupported_subtitles()
        assert isinstance(result, list)
        assert 'hdmv_pgs_subtitle' in result


# ──────────────────────── Package-level discovery ────────────────────────

from compresso.libs.unffmpeg.audio_codecs import get_all_audio_codecs
from compresso.libs.unffmpeg.audio_codecs import grab_module as grab_audio_codec
from compresso.libs.unffmpeg.containers import get_all_containers
from compresso.libs.unffmpeg.containers import grab_module as grab_container
from compresso.libs.unffmpeg.subtitle_codecs import get_all_subtitle_codecs
from compresso.libs.unffmpeg.subtitle_codecs import grab_module as grab_subtitle_codec
from compresso.libs.unffmpeg.video_codecs import get_all_video_codecs
from compresso.libs.unffmpeg.video_codecs import grab_module as grab_video_codec


@pytest.mark.unittest
class TestContainerDiscovery:
    def test_get_all_containers_returns_dict(self):
        result = get_all_containers()
        assert isinstance(result, dict)
        assert len(result) >= 10

    def test_get_all_containers_has_required_keys(self):
        result = get_all_containers()
        for _name, data in result.items():
            assert 'extension' in data
            assert 'description' in data
            assert 'supports_subtitles' in data

    def test_grab_container_mp4(self):
        inst = grab_container('mp4')
        assert inst.container_extension() == 'mp4'

    def test_grab_container_invalid(self):
        with pytest.raises(ImportError):
            grab_container('nonexistent_format')


@pytest.mark.unittest
class TestVideoCodecDiscovery:
    def test_get_all_video_codecs_returns_dict(self):
        result = get_all_video_codecs()
        assert isinstance(result, dict)
        assert len(result) >= 2

    def test_get_all_video_codecs_has_required_keys(self):
        result = get_all_video_codecs()
        for _name, data in result.items():
            assert 'name' in data
            assert 'encoders' in data
            assert 'default_encoder' in data
            assert 'description' in data

    def test_grab_video_codec_h264(self):
        inst = grab_video_codec('h264')
        assert inst.codec_name() == 'h264'

    def test_grab_video_codec_invalid(self):
        with pytest.raises(ImportError):
            grab_video_codec('nonexistent_codec')


@pytest.mark.unittest
class TestAudioCodecDiscovery:
    def test_get_all_audio_codecs_returns_dict(self):
        result = get_all_audio_codecs()
        assert isinstance(result, dict)
        assert len(result) >= 3

    def test_get_all_audio_codecs_has_required_keys(self):
        result = get_all_audio_codecs()
        for _name, data in result.items():
            assert 'name' in data
            assert 'encoders' in data
            assert 'default_encoder' in data
            assert 'description' in data

    def test_grab_audio_codec_aac(self):
        inst = grab_audio_codec('aac')
        assert inst.codec_name() == 'aac'

    def test_grab_audio_codec_invalid(self):
        with pytest.raises(ImportError):
            grab_audio_codec('nonexistent_codec')


@pytest.mark.unittest
class TestSubtitleCodecDiscovery:
    def test_get_all_subtitle_codecs_returns_dict(self):
        result = get_all_subtitle_codecs()
        assert isinstance(result, dict)
        assert len(result) >= 6

    def test_get_all_subtitle_codecs_has_required_keys(self):
        result = get_all_subtitle_codecs()
        for _name, data in result.items():
            assert 'name' in data
            assert 'encoders' in data
            assert 'default_encoder' in data
            assert 'description' in data

    def test_grab_subtitle_codec_srt(self):
        inst = grab_subtitle_codec('srt')
        assert inst.codec_name() == 'srt'

    def test_grab_subtitle_codec_mov_text(self):
        """Tests title-case conversion for underscore names."""
        inst = grab_subtitle_codec('mov_text')
        assert inst.codec_name() == 'mov_text'

    def test_grab_subtitle_codec_invalid(self):
        with pytest.raises(ImportError):
            grab_subtitle_codec('nonexistent_codec')
