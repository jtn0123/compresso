#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_fileinfo_lib.py

    Unit tests for FileInfo and Entry classes in compresso/libs/fileinfo.py.
"""


import pytest


@pytest.mark.unittest
class TestEntry:

    def test_entry_stores_names(self):
        from compresso.libs.fileinfo import Entry
        e = Entry('new.mkv', 'original.avi')
        assert e.newname == 'new.mkv'
        assert e.originalname == 'original.avi'


@pytest.mark.unittest
class TestFileInfoAppend:

    def test_append_adds_entry(self):
        from compresso.libs.fileinfo import FileInfo
        fi = FileInfo('/tmp/test')
        fi.append('new.mkv', 'original.avi')
        assert len(fi.entries) == 1
        assert fi.entries[0].newname == 'new.mkv'
        assert fi.entries[0].originalname == 'original.avi'

    def test_append_tracks_oldest_name(self):
        from compresso.libs.fileinfo import FileInfo
        fi = FileInfo('/tmp/test')
        # First rename: a.avi -> b.mkv
        fi.append('b.mkv', 'a.avi')
        # Second rename: b.mkv -> c.mp4
        # Since b.mkv exists in entries as newname, _find_oldest_name returns a.avi
        fi.append('c.mp4', 'b.mkv')
        assert fi.entries[1].newname == 'c.mp4'
        assert fi.entries[1].originalname == 'a.avi'

    def test_append_unknown_original_uses_self(self):
        from compresso.libs.fileinfo import FileInfo
        fi = FileInfo('/tmp/test')
        fi.append('new.mkv', 'unknown.avi')
        assert fi.entries[0].originalname == 'unknown.avi'


@pytest.mark.unittest
class TestFileInfoFindOldest:

    def test_find_oldest_name_returns_original(self):
        from compresso.libs.fileinfo import FileInfo
        fi = FileInfo('/tmp/test')
        fi.append('b.mkv', 'a.avi')
        result = fi._find_oldest_name('b.mkv')
        assert result == 'a.avi'

    def test_find_oldest_name_returns_self_when_not_found(self):
        from compresso.libs.fileinfo import FileInfo
        fi = FileInfo('/tmp/test')
        result = fi._find_oldest_name('notfound.mkv')
        assert result == 'notfound.mkv'


@pytest.mark.unittest
class TestFileInfoLoadSave:

    def test_load_parses_entries_from_file(self, tmp_path):
        from compresso.libs.fileinfo import FileInfo
        p = tmp_path / "file_info"
        p.write_text('new.mkv="original.avi"\nsecond.mp4="first.mkv"\n')
        fi = FileInfo(str(p))
        fi.load()
        assert len(fi.entries) == 2
        assert fi.entries[0].newname == 'new.mkv'
        assert fi.entries[0].originalname == 'original.avi'
        assert fi.entries[1].newname == 'second.mp4'
        assert fi.entries[1].originalname == 'first.mkv'

    def test_load_nonexistent_file_no_error(self, tmp_path):
        from compresso.libs.fileinfo import FileInfo
        fi = FileInfo(str(tmp_path / "missing"))
        fi.load()
        assert fi.entries == []

    def test_save_writes_entries_to_file(self, tmp_path):
        from compresso.libs.fileinfo import FileInfo
        p = tmp_path / "file_info"
        fi = FileInfo(str(p))
        fi.append('new.mkv', 'original.avi')
        fi.save()
        content = p.read_text()
        assert 'new.mkv="original.avi"' in content

    def test_load_save_roundtrip(self, tmp_path):
        from compresso.libs.fileinfo import FileInfo
        p = tmp_path / "file_info"

        fi1 = FileInfo(str(p))
        fi1.append('b.mkv', 'a.avi')
        fi1.append('c.mp4', 'b.mkv')
        fi1.save()

        fi2 = FileInfo(str(p))
        fi2.load()
        assert len(fi2.entries) == 2
        assert fi2.entries[0].newname == 'b.mkv'
        assert fi2.entries[0].originalname == 'a.avi'
        assert fi2.entries[1].newname == 'c.mp4'
        assert fi2.entries[1].originalname == 'a.avi'
