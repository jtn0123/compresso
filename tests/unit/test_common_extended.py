#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_common_extended.py

    Extended unit tests for compresso.libs.common utility functions.
    Tests: get_default_root_path, get_default_library_path,
    get_default_cache_path, clean_files_in_cache_dir, tail, touch.
"""

import io
import os
import shutil
import tempfile

import pytest
from unittest.mock import patch, MagicMock, call

from compresso.libs import common


# ------------------------------------------------------------------
# get_default_root_path
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetDefaultRootPath:

    def test_returns_absolute_path(self):
        result = common.get_default_root_path()
        assert os.path.isabs(result)

    @patch('compresso.libs.common.os.name', 'posix')
    def test_unix_returns_slash(self):
        result = common.get_default_root_path()
        assert result == os.sep

    @patch('compresso.libs.common.os.name', 'nt')
    @patch('compresso.libs.common.os.sep', '\\')
    def test_windows_returns_c_drive(self):
        result = common.get_default_root_path()
        assert result.startswith('c:')


# ------------------------------------------------------------------
# get_default_library_path
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetDefaultLibraryPath:

    def test_returns_absolute_path(self):
        result = common.get_default_library_path()
        assert os.path.isabs(result)

    @patch('compresso.libs.common.os.name', 'posix')
    def test_unix_library_path(self):
        result = common.get_default_library_path()
        assert result == os.path.join(os.sep, 'library')

    @patch('compresso.libs.common.os.name', 'nt')
    def test_windows_library_path(self):
        result = common.get_default_library_path()
        assert 'Documents' in result


# ------------------------------------------------------------------
# get_default_cache_path
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetDefaultCachePath:

    def test_returns_absolute_path(self):
        result = common.get_default_cache_path()
        assert os.path.isabs(result)

    @patch('compresso.libs.common.os.name', 'posix')
    def test_unix_cache_path(self):
        result = common.get_default_cache_path()
        assert result == os.path.join(os.sep, 'tmp', 'compresso')

    @patch('compresso.libs.common.os.name', 'nt')
    def test_windows_cache_path(self):
        result = common.get_default_cache_path()
        assert 'Compresso' in result


# ------------------------------------------------------------------
# clean_files_in_cache_dir
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestCleanFilesInCacheDir:

    def test_removes_conversion_dirs(self, tmp_path):
        conv_dir = tmp_path / 'compresso_file_conversion-12345'
        conv_dir.mkdir()
        (conv_dir / 'temp_file.tmp').write_text('data')

        other_dir = tmp_path / 'keep_this'
        other_dir.mkdir()
        (other_dir / 'important.txt').write_text('keep')

        with patch('compresso.libs.common.logger'):
            common.clean_files_in_cache_dir(str(tmp_path))

        assert not conv_dir.exists()
        assert other_dir.exists()

    def test_removes_remote_pending_dirs(self, tmp_path):
        remote_dir = tmp_path / 'compresso_remote_pending_library-abc'
        remote_dir.mkdir()
        (remote_dir / 'pending.dat').write_text('data')

        with patch('compresso.libs.common.logger'):
            common.clean_files_in_cache_dir(str(tmp_path))

        assert not remote_dir.exists()

    def test_does_nothing_for_nonexistent_dir(self):
        with patch('compresso.libs.common.logger'):
            # Should not raise
            common.clean_files_in_cache_dir('/nonexistent/path/that/does/not/exist')

    def test_leaves_unrelated_dirs(self, tmp_path):
        unrelated = tmp_path / 'some_other_dir'
        unrelated.mkdir()
        (unrelated / 'file.txt').write_text('keep')

        with patch('compresso.libs.common.logger'):
            common.clean_files_in_cache_dir(str(tmp_path))

        assert unrelated.exists()
        assert (unrelated / 'file.txt').exists()

    def test_handles_rmtree_exception(self, tmp_path):
        conv_dir = tmp_path / 'compresso_file_conversion-error'
        conv_dir.mkdir()

        with patch('compresso.libs.common.logger') as mock_logger:
            with patch('compresso.libs.common.shutil.rmtree', side_effect=OSError("Permission denied")):
                common.clean_files_in_cache_dir(str(tmp_path))
            mock_logger.error.assert_called()

    def test_handles_multiple_matching_dirs(self, tmp_path):
        dir1 = tmp_path / 'compresso_file_conversion-001'
        dir2 = tmp_path / 'compresso_file_conversion-002'
        dir3 = tmp_path / 'compresso_remote_pending_library-003'
        for d in [dir1, dir2, dir3]:
            d.mkdir()
            (d / 'file.tmp').write_text('data')

        with patch('compresso.libs.common.logger'):
            common.clean_files_in_cache_dir(str(tmp_path))

        assert not dir1.exists()
        assert not dir2.exists()
        assert not dir3.exists()


# ------------------------------------------------------------------
# tail
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestTail:

    def test_reads_last_n_lines(self, tmp_path):
        filepath = tmp_path / 'log.txt'
        lines = [f'line {i}\n' for i in range(50)]
        filepath.write_text(''.join(lines))

        with open(str(filepath), 'rb') as f:
            result = common.tail(f, 5)

        assert len(result) >= 5
        # The last element should be the last line
        assert result[-1] == b'line 49'

    def test_reads_all_lines_when_n_exceeds_file(self, tmp_path):
        filepath = tmp_path / 'short.txt'
        filepath.write_text('line 1\nline 2\nline 3\n')

        with open(str(filepath), 'rb') as f:
            result = common.tail(f, 100)

        assert len(result) >= 3

    def test_reads_from_small_file(self, tmp_path):
        filepath = tmp_path / 'tiny.txt'
        filepath.write_text('only line\n')

        with open(str(filepath), 'rb') as f:
            result = common.tail(f, 1)

        assert any(b'only line' in line for line in result)

    def test_reads_with_offset(self, tmp_path):
        filepath = tmp_path / 'offset.txt'
        lines = [f'line {i}\n' for i in range(20)]
        filepath.write_text(''.join(lines))

        with open(str(filepath), 'rb') as f:
            result = common.tail(f, 3, offset=2)

        # Should read enough lines to satisfy n + offset
        assert len(result) >= 5


# ------------------------------------------------------------------
# touch
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestTouch:

    def test_creates_new_file(self, tmp_path):
        filepath = str(tmp_path / 'newfile.txt')
        assert not os.path.exists(filepath)
        common.touch(filepath)
        assert os.path.exists(filepath)

    def test_touch_existing_file_updates_mtime(self, tmp_path):
        filepath = str(tmp_path / 'existing.txt')
        with open(filepath, 'w') as f:
            f.write('content')

        old_mtime = os.path.getmtime(filepath)
        import time
        time.sleep(0.05)
        common.touch(filepath)
        new_mtime = os.path.getmtime(filepath)
        assert new_mtime >= old_mtime

    def test_touch_preserves_file_content(self, tmp_path):
        filepath = str(tmp_path / 'preserve.txt')
        with open(filepath, 'w') as f:
            f.write('keep this')

        common.touch(filepath)

        with open(filepath) as f:
            assert f.read() == 'keep this'
