#!/usr/bin/env python3

"""
tests.unit.test_workers_fileops.py

Focused tests for the safety-critical file-lifecycle helpers extracted from
Worker.__exec_worker_runners_on_set_task: the intermediate-input deletion guards
and the final output move/copy. These paths were previously only exercised
through the fully-mocked worker process loop.
"""

import os
import queue
from unittest.mock import MagicMock, patch

import pytest


def _make_worker(thread_id="w-0", name="W-1", group_id="g-1"):
    with patch("compresso.libs.workers.CompressoLogging"):
        from compresso.libs.workers import Worker

        event = MagicMock()
        worker = Worker(thread_id, name, group_id, queue.Queue(), queue.Queue(), event)
    worker.logger = MagicMock()
    return worker


# Name-mangled accessors for the private helpers under test.
def _build_runners_info(plugin_modules):
    from compresso.libs.workers import Worker

    return Worker._Worker__build_worker_runners_info(plugin_modules)


def _remove_intermediate(file_in, file_out, original_abspath):
    from compresso.libs.workers import Worker

    return Worker._Worker__remove_intermediate_input_file(file_in, file_out, original_abspath)


@pytest.mark.unittest
class TestBuildWorkerRunnersInfo:
    def test_builds_pending_map_keyed_by_plugin_id(self):
        modules = [
            {"plugin_id": "a", "name": "A", "author": "x", "version": "1", "icon": "i", "description": "d"},
            {"plugin_id": "b", "name": "B", "author": "y", "version": "2", "icon": "j", "description": "e"},
        ]
        info = _build_runners_info(modules)
        assert set(info) == {"a", "b"}
        assert info["a"]["status"] == "pending"
        assert info["a"]["name"] == "A"
        assert info["b"]["version"] == "2"

    def test_empty_modules_returns_empty(self):
        assert _build_runners_info([]) == {}


@pytest.mark.unittest
class TestRemoveIntermediateInputFile:
    def _cache_file(self, tmp_path, name="compresso_file_conversion-x/inter.mkv"):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("data")
        return str(p)

    def test_removes_intermediate_cache_file(self, tmp_path):
        file_in = self._cache_file(tmp_path)
        file_out = str(tmp_path / "compresso_file_conversion-x" / "out.mkv")
        original = str(tmp_path / "library" / "movie.mkv")
        _remove_intermediate(file_in, file_out, original)
        assert not os.path.exists(file_in)

    def test_never_deletes_the_original_source(self, tmp_path):
        # file_in IS the original — guard 1 must prevent deletion.
        original_dir = tmp_path / "compresso_file_conversion-x"
        original_dir.mkdir(parents=True)
        original = str(original_dir / "movie.mkv")
        with open(original, "w") as fh:
            fh.write("original")
        _remove_intermediate(original, str(tmp_path / "out.mkv"), original)
        assert os.path.exists(original), "guard 1 must never delete the original source"

    def test_never_deletes_outside_conversion_cache(self, tmp_path):
        # file_in is not under a compresso_file_conversion dir — guard 2.
        outside = tmp_path / "somewhere" / "keep.mkv"
        outside.parent.mkdir(parents=True)
        outside.write_text("keep")
        _remove_intermediate(str(outside), str(tmp_path / "out.mkv"), str(tmp_path / "orig.mkv"))
        assert os.path.exists(outside), "guard 2 must not delete files outside the conversion cache"

    def test_never_deletes_when_file_out_equals_file_in(self, tmp_path):
        # Plugin produced output in place — guard 3 must keep it.
        file_in = self._cache_file(tmp_path)
        _remove_intermediate(file_in, file_in, str(tmp_path / "orig.mkv"))
        assert os.path.exists(file_in), "guard 3 must not delete file_in when it equals file_out"


@pytest.mark.unittest
class TestMoveFinalOutputToCache:
    def _worker_with_task(self, cache_path):
        worker = _make_worker()
        task = MagicMock()
        task.get_cache_path.return_value = cache_path
        worker.current_task = task
        worker.event = MagicMock()
        return worker

    def test_moves_cache_file_to_task_cache_path(self, tmp_path):
        cache_dir = tmp_path / "compresso_file_conversion-x"
        cache_dir.mkdir(parents=True)
        current = cache_dir / "final.mkv"
        current.write_text("encoded")
        dest = str(cache_dir / "task-cache.mkv")
        original = str(tmp_path / "library" / "movie.mkv")

        worker = self._worker_with_task(dest)
        ok, returned = worker._Worker__move_final_output_to_cache(str(current), str(cache_dir), original, dest)

        assert ok is True
        assert returned == dest
        assert os.path.exists(dest)
        assert not os.path.exists(current), "source should be moved, not copied"

    def test_copies_when_output_is_the_original(self, tmp_path):
        # When the final output is still the original source, it must be copied
        # (so the original is never moved out of the library), not moved.
        lib = tmp_path / "library"
        lib.mkdir()
        original = lib / "movie.mkv"
        original.write_text("source")
        cache_dir = tmp_path / "compresso_file_conversion-x"
        cache_dir.mkdir()
        dest = str(cache_dir / "task-cache.mkv")

        worker = self._worker_with_task(dest)
        ok, returned = worker._Worker__move_final_output_to_cache(str(original), str(cache_dir), str(original), dest)

        assert ok is True
        assert os.path.exists(original), "original must be preserved (copied, not moved)"
        assert os.path.exists(dest)

    def test_returns_false_on_oserror(self, tmp_path):
        cache_dir = tmp_path / "compresso_file_conversion-x"
        cache_dir.mkdir()
        dest = str(cache_dir / "task-cache.mkv")
        worker = self._worker_with_task(dest)
        # current_file_out does not exist -> shutil.move raises -> helper returns False.
        ok, returned = worker._Worker__move_final_output_to_cache(
            str(cache_dir / "missing.mkv"), str(cache_dir), str(tmp_path / "orig.mkv"), dest
        )
        assert ok is False
        assert returned == dest
