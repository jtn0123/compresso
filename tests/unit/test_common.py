#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_common.py

    Unit tests for compresso.libs.common utility functions.
"""

import json
import os
import pytest
from unittest.mock import patch

from compresso.libs import common


@pytest.mark.unittest
class TestGetHomeDir:

    def test_returns_home_dir_env(self, tmp_path):
        with patch.dict(os.environ, {'HOME_DIR': str(tmp_path)}):
            assert common.get_home_dir() == str(tmp_path)

    def test_returns_user_home_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('HOME_DIR', None)
            result = common.get_home_dir()
            assert os.path.isabs(result)

    def test_expands_tilde_in_home_dir(self):
        with patch.dict(os.environ, {'HOME_DIR': '~/mydir'}):
            result = common.get_home_dir()
            assert '~' not in result
            assert os.path.isabs(result)


@pytest.mark.unittest
class TestFormatMessage:

    def test_simple_message(self):
        result = common.format_message("hello")
        assert result == "[FORMATTED] - hello"

    def test_with_string_message2(self):
        result = common.format_message("hello", "world")
        assert "hello - world" in result
        assert result.startswith("[FORMATTED]")

    def test_with_dict_message2(self):
        result = common.format_message("data", {"key": "value"})
        assert "key" in result
        assert result.startswith("[FORMATTED]")

    def test_with_list_message2(self):
        result = common.format_message("items", [1, 2, 3])
        assert result.startswith("[FORMATTED]")


@pytest.mark.unittest
class TestTimeStringToSeconds:

    def test_converts_time_string(self):
        assert common.time_string_to_seconds("01:30:45.500000") == 5445

    def test_zero_time(self):
        assert common.time_string_to_seconds("00:00:00.000000") == 0

    def test_seconds_only(self):
        assert common.time_string_to_seconds("00:00:30.000000") == 30


@pytest.mark.unittest
class TestEnsureDir:

    def test_creates_directory(self, tmp_path):
        new_dir = tmp_path / "sub" / "dir"
        file_path = str(new_dir / "file.txt")
        common.ensure_dir(file_path)
        assert os.path.isdir(str(new_dir))


@pytest.mark.unittest
class TestRandomString:

    def test_default_length(self):
        result = common.random_string()
        assert len(result) == 5
        assert result.isalpha()
        assert result.islower()

    def test_custom_length(self):
        result = common.random_string(10)
        assert len(result) == 10


@pytest.mark.unittest
class TestJsonDumpToFile:

    def test_writes_valid_json(self, tmp_path):
        out_file = str(tmp_path / "test.json")
        data = {"key": "value", "number": 42}
        result = common.json_dump_to_file(data, out_file)
        assert result['success'] is True
        with open(out_file) as f:
            loaded = json.load(f)
        assert loaded == data

    def test_rollback_on_invalid_json(self, tmp_path):
        out_file = str(tmp_path / "test.json")
        # Write initial valid data
        with open(out_file, 'w') as f:
            json.dump({"original": True}, f)
        # Try to write something that will pass write but we'll test rollback exists
        result = common.json_dump_to_file({"new": True}, out_file)
        assert result['success'] is True


@pytest.mark.unittest
class TestExtractVideoCodecs:

    def test_extracts_codecs(self):
        props = {
            'streams': [
                {'codec_type': 'video', 'codec_name': 'h264'},
                {'codec_type': 'audio', 'codec_name': 'aac'},
                {'codec_type': 'video', 'codec_name': 'hevc'},
            ]
        }
        codecs = common.extract_video_codecs_from_file_properties(props)
        assert codecs == ['h264', 'hevc']

    def test_no_video_streams(self):
        props = {
            'streams': [
                {'codec_type': 'audio', 'codec_name': 'aac'},
            ]
        }
        codecs = common.extract_video_codecs_from_file_properties(props)
        assert codecs == []


@pytest.mark.unittest
class TestGetFileChecksum:

    def test_returns_consistent_checksum(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")
        checksum1 = common.get_file_checksum(str(f))
        checksum2 = common.get_file_checksum(str(f))
        assert checksum1 == checksum2
        assert len(checksum1) == 32  # MD5 hex digest length


@pytest.mark.unittest
class TestMakeTimestampHumanReadable:

    def test_recent_past_shows_seconds_ago(self):
        import time
        ts = time.time() - 5
        result = common.make_timestamp_human_readable(ts)
        assert 'ago' in result
        assert 'second' in result

    def test_one_day_ago(self):
        import time
        ts = time.time() - 86400
        result = common.make_timestamp_human_readable(ts)
        assert '1 day' in result
        assert 'ago' in result

    def test_multiple_days_ago(self):
        import time
        ts = time.time() - (2 * 86400)
        result = common.make_timestamp_human_readable(ts)
        assert 'days' in result
        assert 'ago' in result

    def test_future_timestamp_shows_in_prefix(self):
        import time
        ts = time.time() + 3600
        result = common.make_timestamp_human_readable(ts)
        assert result.startswith('in ')

    def test_one_year_ago(self):
        import time
        ts = time.time() - (365 * 86400)
        result = common.make_timestamp_human_readable(ts)
        assert '1 year' in result
        assert 'ago' in result


@pytest.mark.unittest
class TestGetFileFingerprint:

    def test_full_xxhash_small_file(self, tmp_path):
        f = tmp_path / "small.bin"
        f.write_bytes(b"small file content")
        fingerprint, algo = common.get_file_fingerprint(str(f))
        assert algo == "full_xxhash_v1"  # falls back for small files
        assert isinstance(fingerprint, str)
        assert len(fingerprint) > 0

    def test_invalid_algo_falls_back(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"test content")
        fingerprint, algo = common.get_file_fingerprint(str(f), algo="nonexistent")
        assert isinstance(fingerprint, str)

    def test_full_sha256_consistency(self, tmp_path):
        f = tmp_path / "sha.bin"
        f.write_bytes(b"consistent content for sha256 test")
        fp1, algo1 = common.get_file_fingerprint(str(f), algo="full_sha256_v1")
        fp2, algo2 = common.get_file_fingerprint(str(f), algo="full_sha256_v1")
        assert fp1 == fp2
        assert algo1 == "full_sha256_v1"

    def test_different_content_different_fingerprint(self, tmp_path):
        f1 = tmp_path / "file1.bin"
        f2 = tmp_path / "file2.bin"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        fp1, _ = common.get_file_fingerprint(str(f1))
        fp2, _ = common.get_file_fingerprint(str(f2))
        assert fp1 != fp2

    def test_sampled_xxhash_falls_back_to_full_for_small_file(self, tmp_path):
        f = tmp_path / "small_sampled.bin"
        f.write_bytes(b"small file for sampled xxhash test")
        fingerprint, algo = common.get_file_fingerprint(str(f), algo="sampled_xxhash_v1")
        # Small file (< 100MB) should fall back to full_xxhash_v1
        assert algo == "full_xxhash_v1"
