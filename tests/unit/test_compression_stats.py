#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_compression_stats.py

    Unit tests for compression statistics functionality:
    - CompressionStats model creation
    - History.get_library_compression_summary()
    - History.get_compression_stats_for_task()
    - History.get_compression_stats_paginated()
    - Per-library breakdown with multiple libraries

"""

import os
import pytest
import tempfile
import datetime

from unmanic.libs.unmodels.lib import Database


class TestCompressionStats(object):
    """
    TestCompressionStats

    Test compression statistics with an in-memory SQLite database.
    """

    db_connection = None

    def setup_class(self):
        """
        Setup the class state for pytest.

        Creates an in-memory SQLite database and the required tables
        (CompletedTasks and CompressionStats).
        """
        self.config_path = tempfile.mkdtemp(prefix='unmanic_tests_')
        self.db_file = os.path.join(self.config_path, 'test_compression.db')

        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import CompletedTasks
        from unmanic.libs.unmodels.compressionstats import CompressionStats

        self.db_connection.create_tables([CompletedTasks, CompressionStats])

        # Wait for the queue-based writes to complete
        import time
        time.sleep(0.5)

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def _create_completed_task(self, label='test_file.mkv', success=True):
        """Helper to create a CompletedTasks row and return it."""
        from unmanic.libs.unmodels import CompletedTasks
        return CompletedTasks.create(
            task_label=label,
            abspath='/media/' + label,
            task_success=success,
            start_time=datetime.datetime.now(),
            finish_time=datetime.datetime.now(),
            processed_by_worker='worker-0',
        )

    def _create_stats(self, task, source_size, dest_size,
                      source_codec='hevc', dest_codec='h264',
                      resolution='1920x1080', library_id=1):
        """Helper to create a CompressionStats row."""
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        return CompressionStats.create(
            completedtask=task,
            source_size=source_size,
            destination_size=dest_size,
            source_codec=source_codec,
            destination_codec=dest_codec,
            source_resolution=resolution,
            library_id=library_id,
        )

    # ------------------------------------------------------------------
    # Basic model creation
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_create_compression_stats_entry(self):
        """A CompressionStats row can be created and read back."""
        from unmanic.libs.unmodels.compressionstats import CompressionStats

        task = self._create_completed_task(label='creation_test.mkv')
        stats = self._create_stats(task, source_size=1000000, dest_size=500000)

        fetched = CompressionStats.get_by_id(stats.id)
        assert fetched.source_size == 1000000
        assert fetched.destination_size == 500000
        assert fetched.source_codec == 'hevc'
        assert fetched.destination_codec == 'h264'

    # ------------------------------------------------------------------
    # get_library_compression_summary
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_library_compression_summary_returns_correct_aggregates(self):
        """Summary should aggregate source/dest sizes and compute avg_ratio."""
        from unmanic.libs.history import History

        # Clear existing data
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

        # Create two tasks in library 1
        t1 = self._create_completed_task(label='summary_a.mkv')
        t2 = self._create_completed_task(label='summary_b.mkv')
        self._create_stats(t1, source_size=2000, dest_size=1000, library_id=1)
        self._create_stats(t2, source_size=4000, dest_size=2000, library_id=1)

        history = History()
        summary = history.get_library_compression_summary()

        assert summary['total_source_size'] == 6000
        assert summary['total_destination_size'] == 3000
        assert summary['file_count'] == 2
        assert summary['space_saved'] == 3000
        # avg_ratio = 3000/6000 = 0.5
        assert summary['avg_ratio'] == 0.5

    @pytest.mark.unittest
    def test_summary_with_library_filter(self):
        """Summary filtered by library_id returns only that library's data."""
        from unmanic.libs.history import History
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

        t1 = self._create_completed_task(label='lib1.mkv')
        t2 = self._create_completed_task(label='lib2.mkv')
        self._create_stats(t1, source_size=1000, dest_size=800, library_id=1)
        self._create_stats(t2, source_size=5000, dest_size=2500, library_id=2)

        history = History()
        summary = history.get_library_compression_summary(library_id=2)

        assert summary['total_source_size'] == 5000
        assert summary['total_destination_size'] == 2500
        assert summary['file_count'] == 1

    @pytest.mark.unittest
    def test_summary_multiple_libraries_per_library_breakdown(self):
        """Summary without filter returns per_library breakdown for each library."""
        from unmanic.libs.history import History
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

        t1 = self._create_completed_task(label='multi_lib1.mkv')
        t2 = self._create_completed_task(label='multi_lib2.mkv')
        t3 = self._create_completed_task(label='multi_lib3.mkv')
        self._create_stats(t1, source_size=1000, dest_size=500, library_id=1)
        self._create_stats(t2, source_size=2000, dest_size=1000, library_id=2)
        self._create_stats(t3, source_size=3000, dest_size=1500, library_id=2)

        history = History()
        summary = history.get_library_compression_summary()

        assert summary['file_count'] == 3
        assert summary['total_source_size'] == 6000
        assert summary['total_destination_size'] == 3000

        per_lib = {entry['library_id']: entry for entry in summary['per_library']}
        assert 1 in per_lib
        assert 2 in per_lib
        assert per_lib[1]['file_count'] == 1
        assert per_lib[1]['total_source_size'] == 1000
        assert per_lib[2]['file_count'] == 2
        assert per_lib[2]['total_source_size'] == 5000
        assert per_lib[2]['space_saved'] == 2500

    # ------------------------------------------------------------------
    # get_compression_stats_for_task
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_compression_stats_for_task_returns_correct_data(self):
        """Stats for a single task should return the correct dict."""
        from unmanic.libs.history import History
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

        task = self._create_completed_task(label='single_task.mkv')
        self._create_stats(task, source_size=10000, dest_size=7500,
                           source_codec='mpeg2video', dest_codec='hevc',
                           resolution='3840x2160', library_id=3)

        history = History()
        result = history.get_compression_stats_for_task(task.id)

        assert result is not None
        assert result['source_size'] == 10000
        assert result['destination_size'] == 7500
        assert result['source_codec'] == 'mpeg2video'
        assert result['destination_codec'] == 'hevc'
        assert result['source_resolution'] == '3840x2160'
        assert result['library_id'] == 3
        # ratio = 7500/10000 = 0.75
        assert result['ratio'] == 0.75
        assert result['space_saved'] == 2500

    @pytest.mark.unittest
    def test_get_compression_stats_for_nonexistent_task_returns_none(self):
        """Stats for a task that does not exist should return None."""
        from unmanic.libs.history import History
        history = History()
        result = history.get_compression_stats_for_task(999999)
        assert result is None

    # ------------------------------------------------------------------
    # get_compression_stats_paginated
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_compression_stats_paginated_returns_correct_results(self):
        """Paginated stats should return the expected structure."""
        from unmanic.libs.history import History
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

        # Create 5 tasks with stats
        for i in range(5):
            t = self._create_completed_task(label='paginated_{}.mkv'.format(i))
            self._create_stats(t, source_size=(i + 1) * 1000,
                               dest_size=(i + 1) * 500, library_id=1)

        history = History()
        result = history.get_compression_stats_paginated(start=0, length=3)

        assert 'recordsTotal' in result
        assert 'recordsFiltered' in result
        assert 'results' in result
        assert result['recordsTotal'] == 5
        assert result['recordsFiltered'] == 5
        assert len(result['results']) == 3

    @pytest.mark.unittest
    def test_get_compression_stats_paginated_offset(self):
        """Pagination with an offset should skip initial rows."""
        from unmanic.libs.history import History
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

        for i in range(5):
            t = self._create_completed_task(label='offset_{}.mkv'.format(i))
            self._create_stats(t, source_size=(i + 1) * 1000,
                               dest_size=(i + 1) * 500, library_id=1)

        history = History()
        result = history.get_compression_stats_paginated(start=3, length=10)

        assert result['recordsTotal'] == 5
        assert len(result['results']) == 2  # 5 total, skip 3

    @pytest.mark.unittest
    def test_get_compression_stats_paginated_library_filter(self):
        """Paginated stats filtered by library_id should only return matching rows."""
        from unmanic.libs.history import History
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

        t1 = self._create_completed_task(label='libfilter_1.mkv')
        t2 = self._create_completed_task(label='libfilter_2.mkv')
        t3 = self._create_completed_task(label='libfilter_3.mkv')
        self._create_stats(t1, source_size=1000, dest_size=500, library_id=1)
        self._create_stats(t2, source_size=2000, dest_size=1000, library_id=2)
        self._create_stats(t3, source_size=3000, dest_size=1500, library_id=2)

        history = History()
        result = history.get_compression_stats_paginated(library_id=2)

        assert result['recordsFiltered'] == 2
        assert len(result['results']) == 2
        for row in result['results']:
            assert row['library_id'] == 2

    @pytest.mark.unittest
    def test_paginated_result_contains_expected_fields(self):
        """Each paginated result row should have the required keys."""
        from unmanic.libs.history import History
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

        t = self._create_completed_task(label='fields_test.mkv')
        self._create_stats(t, source_size=8000, dest_size=4000, library_id=1)

        history = History()
        result = history.get_compression_stats_paginated(start=0, length=10)

        assert len(result['results']) == 1
        row = result['results'][0]

        expected_keys = [
            'id', 'completedtask_id', 'task_label', 'task_success',
            'finish_time', 'source_size', 'destination_size',
            'source_codec', 'destination_codec', 'source_resolution',
            'library_id', 'ratio', 'space_saved',
        ]
        for key in expected_keys:
            assert key in row, "Missing key: {}".format(key)


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
