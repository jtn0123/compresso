#!/usr/bin/env python3

"""
    tests.unit.test_directoryinfo.py

    Unit tests for compresso.libs.directoryinfo.CompressoDirectoryInfo.
"""

import json
import os

import pytest

from compresso.libs.directoryinfo import CompressoDirectoryInfo, CompressoDirectoryInfoException


@pytest.mark.unittest
class TestCompressoDirectoryInfoJSON:

    def test_nonexistent_directory_gives_empty_json_data(self, tmp_config):
        subdir = os.path.join(tmp_config, 'nonexistent_sub')
        os.makedirs(subdir)
        info = CompressoDirectoryInfo(subdir)
        assert info.json_data == {}

    def test_reads_valid_json_file(self, tmp_config):
        data = {"section1": {"key1": "value1"}}
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            json.dump(data, f)
        info = CompressoDirectoryInfo(tmp_config)
        assert info.json_data == data

    def test_set_creates_new_section(self, tmp_config):
        info = CompressoDirectoryInfo(tmp_config)
        info.set('newsection', 'mykey', 'myvalue')
        assert info.get('newsection', 'mykey') == 'myvalue'

    def test_set_adds_key_to_existing_section(self, tmp_config):
        data = {"sect": {"existing": "val"}}
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            json.dump(data, f)
        info = CompressoDirectoryInfo(tmp_config)
        info.set('sect', 'newkey', 'newval')
        assert info.get('sect', 'existing') == 'val'
        assert info.get('sect', 'newkey') == 'newval'

    def test_get_returns_none_for_missing_section(self, tmp_config):
        info = CompressoDirectoryInfo(tmp_config)
        assert info.get('nonexistent', 'key') is None

    def test_get_returns_none_for_missing_option(self, tmp_config):
        data = {"sect": {"key1": "val1"}}
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            json.dump(data, f)
        info = CompressoDirectoryInfo(tmp_config)
        assert info.get('sect', 'missing_key') is None

    def test_option_keys_are_lowercased(self, tmp_config):
        info = CompressoDirectoryInfo(tmp_config)
        info.set('sect', 'MyKey', 'value')
        assert info.get('sect', 'mykey') == 'value'

    def test_save_writes_json_to_disk(self, tmp_config):
        info = CompressoDirectoryInfo(tmp_config)
        info.set('sect', 'key', 'value')
        info.save()
        with open(os.path.join(tmp_config, '.compresso')) as f:
            loaded = json.load(f)
        assert loaded['sect']['key'] == 'value'

    def test_save_and_reload_roundtrip(self, tmp_config):
        info = CompressoDirectoryInfo(tmp_config)
        info.set('sect', 'key', 'value')
        info.save()
        info2 = CompressoDirectoryInfo(tmp_config)
        assert info2.get('sect', 'key') == 'value'


@pytest.mark.unittest
class TestCompressoDirectoryInfoINIMigration:

    def test_reads_ini_format_and_migrates(self, tmp_config):
        ini_content = "[section1]\nkey1 = value1\nkey2 = value2\n"
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            f.write(ini_content)
        info = CompressoDirectoryInfo(tmp_config)
        assert info.get('section1', 'key1') == 'value1'
        assert info.get('section1', 'key2') == 'value2'

    def test_ini_keys_are_lowercased(self, tmp_config):
        ini_content = "[section1]\nMyKey = value1\n"
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            f.write(ini_content)
        info = CompressoDirectoryInfo(tmp_config)
        assert info.get('section1', 'mykey') == 'value1'

    def test_ini_multiple_sections(self, tmp_config):
        ini_content = "[sect_a]\nk1 = v1\n\n[sect_b]\nk2 = v2\n"
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            f.write(ini_content)
        info = CompressoDirectoryInfo(tmp_config)
        assert info.get('sect_a', 'k1') == 'v1'
        assert info.get('sect_b', 'k2') == 'v2'

    def test_ini_migration_persists_as_json(self, tmp_config):
        ini_content = "[section1]\nkey1 = value1\n"
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            f.write(ini_content)
        info = CompressoDirectoryInfo(tmp_config)
        info.save()
        # Verify the file is now valid JSON
        with open(os.path.join(tmp_config, '.compresso')) as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert data.get('section1', {}).get('key1') == 'value1'


@pytest.mark.unittest
class TestCompressoDirectoryInfoJSONMigration:

    def test_migrates_uppercase_keys_to_lowercase(self, tmp_config):
        data = {"section": {"UpperKey": "value"}}
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            json.dump(data, f)
        info = CompressoDirectoryInfo(tmp_config)
        assert info.get('section', 'upperkey') == 'value'
        # Original uppercase key should no longer exist
        assert 'UpperKey' not in info.json_data.get('section', {})

    def test_sections_remain_case_sensitive(self, tmp_config):
        data = {"MySection": {"key": "value"}}
        with open(os.path.join(tmp_config, '.compresso'), 'w') as f:
            json.dump(data, f)
        info = CompressoDirectoryInfo(tmp_config)
        assert info.get('MySection', 'key') == 'value'


@pytest.mark.unittest
class TestCompressoDirectoryInfoErrors:

    def test_raises_exception_for_unparseable_file(self, tmp_config):
        with open(os.path.join(tmp_config, '.compresso'), 'wb') as f:
            f.write(b'\x00\x01\x02garbage bytes')
        with pytest.raises(CompressoDirectoryInfoException):
            CompressoDirectoryInfo(tmp_config)

    def test_exception_contains_path(self, tmp_config):
        with open(os.path.join(tmp_config, '.compresso'), 'wb') as f:
            f.write(b'\x00\x01\x02garbage bytes')
        with pytest.raises(CompressoDirectoryInfoException) as exc_info:
            CompressoDirectoryInfo(tmp_config)
        assert exc_info.value.path == os.path.join(tmp_config, '.compresso')

    def test_exception_str_representation(self):
        exc = CompressoDirectoryInfoException("test message", "/test/path")
        assert str(exc) == "test message"
        assert exc.path == "/test/path"

    def test_exception_message_and_path_attributes(self):
        exc = CompressoDirectoryInfoException("msg", "/p")
        assert exc.message == "msg"
        assert exc.path == "/p"
        assert repr(exc) == "msg"
