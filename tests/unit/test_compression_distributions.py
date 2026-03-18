#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_compression_distributions.py

    Unit tests for compression distribution statistics:
    - History.get_codec_distribution()
    - History.get_resolution_distribution()
    - History.get_container_distribution()
    - History.get_space_saved_over_time()

"""

import datetime
import os
import tempfile
import pytest

from unmanic.libs.unmodels.lib import Database


@pytest.mark.unittest
class TestCompressionDistributions(object):
    """
    Tests for codec, resolution, container distributions and space-saved timeline.
    Uses a real SQLite database following test_compression_stats.py patterns.
    """

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='unmanic_tests_dist_')
        self.db_file = os.path.join(self.config_path, 'test_distributions.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import CompletedTasks
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        self.db_connection.create_tables([CompletedTasks, CompressionStats])
        self.db_connection.execute_sql('SELECT 1')

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def setup_method(self):
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks
        CompressionStats.delete().execute()
        CompletedTasks.delete().execute()

    def _create_completed_task(self, label='test_file.mkv', finish_time=None):
        from unmanic.libs.unmodels import CompletedTasks
        return CompletedTasks.create(
            task_label=label,
            abspath='/media/' + label,
            task_success=True,
            start_time=finish_time or datetime.datetime.now(),
            finish_time=finish_time or datetime.datetime.now(),
            processed_by_worker='worker-0',
        )

    def _create_stats(self, task, source_size=1000, dest_size=500,
                      source_codec='hevc', dest_codec='h264',
                      resolution='1920x1080', library_id=1,
                      source_container='', destination_container=''):
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        return CompressionStats.create(
            completedtask=task,
            source_size=source_size,
            destination_size=dest_size,
            source_codec=source_codec,
            destination_codec=dest_codec,
            source_resolution=resolution,
            library_id=library_id,
            source_container=source_container,
            destination_container=destination_container,
        )

    # ------------------------------------------------------------------
    # Codec Distribution
    # ------------------------------------------------------------------

    def test_source_codecs_grouped_correctly(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='c1.mkv')
        t2 = self._create_completed_task(label='c2.mkv')
        t3 = self._create_completed_task(label='c3.mkv')
        self._create_stats(t1, source_codec='hevc', dest_codec='h264')
        self._create_stats(t2, source_codec='hevc', dest_codec='h264')
        self._create_stats(t3, source_codec='h264', dest_codec='hevc')

        history = History()
        result = history.get_codec_distribution()
        source = {r['codec']: r['count'] for r in result['source_codecs']}
        assert source['hevc'] == 2
        assert source['h264'] == 1

    def test_destination_codecs_grouped_correctly(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='d1.mkv')
        t2 = self._create_completed_task(label='d2.mkv')
        t3 = self._create_completed_task(label='d3.mkv')
        self._create_stats(t1, dest_codec='h264')
        self._create_stats(t2, dest_codec='h264')
        self._create_stats(t3, dest_codec='hevc')

        history = History()
        result = history.get_codec_distribution()
        dest = {r['codec']: r['count'] for r in result['destination_codecs']}
        assert dest['h264'] == 2
        assert dest['hevc'] == 1

    def test_codec_distribution_library_filter(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='cf1.mkv')
        t2 = self._create_completed_task(label='cf2.mkv')
        self._create_stats(t1, source_codec='hevc', library_id=1)
        self._create_stats(t2, source_codec='h264', library_id=2)

        history = History()
        result = history.get_codec_distribution(library_id=1)
        codecs = [r['codec'] for r in result['source_codecs']]
        assert 'hevc' in codecs
        assert 'h264' not in codecs

    def test_empty_codecs_excluded(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='ec.mkv')
        self._create_stats(t1, source_codec='', dest_codec='h264')

        history = History()
        result = history.get_codec_distribution()
        assert len(result['source_codecs']) == 0
        assert len(result['destination_codecs']) == 1

    # ------------------------------------------------------------------
    # Resolution Distribution
    # ------------------------------------------------------------------

    def test_resolution_groups_correctly(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='r1.mkv')
        t2 = self._create_completed_task(label='r2.mkv')
        t3 = self._create_completed_task(label='r3.mkv')
        self._create_stats(t1, resolution='1920x1080')
        self._create_stats(t2, resolution='1920x1080')
        self._create_stats(t3, resolution='3840x2160')

        history = History()
        result = history.get_resolution_distribution()
        res_map = {r['resolution']: r['count'] for r in result}
        assert res_map['1920x1080'] == 2
        assert res_map['3840x2160'] == 1

    def test_resolution_library_filter(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='rf1.mkv')
        t2 = self._create_completed_task(label='rf2.mkv')
        self._create_stats(t1, resolution='1920x1080', library_id=1)
        self._create_stats(t2, resolution='3840x2160', library_id=2)

        history = History()
        result = history.get_resolution_distribution(library_id=1)
        assert len(result) == 1
        assert result[0]['resolution'] == '1920x1080'

    def test_empty_resolutions_excluded(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='er.mkv')
        self._create_stats(t1, resolution='')

        history = History()
        result = history.get_resolution_distribution()
        assert len(result) == 0

    # ------------------------------------------------------------------
    # Container Distribution
    # ------------------------------------------------------------------

    def test_source_containers_grouped_correctly(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='sc1.mkv')
        t2 = self._create_completed_task(label='sc2.mkv')
        t3 = self._create_completed_task(label='sc3.mkv')
        self._create_stats(t1, source_container='mkv', destination_container='mp4')
        self._create_stats(t2, source_container='mkv', destination_container='mp4')
        self._create_stats(t3, source_container='avi', destination_container='mkv')

        history = History()
        result = history.get_container_distribution()
        src = {r['container']: r['count'] for r in result['source_containers']}
        assert src['mkv'] == 2
        assert src['avi'] == 1

    def test_destination_containers_grouped_correctly(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='dc1.mkv')
        t2 = self._create_completed_task(label='dc2.mkv')
        t3 = self._create_completed_task(label='dc3.mkv')
        self._create_stats(t1, source_container='mkv', destination_container='mp4')
        self._create_stats(t2, source_container='mkv', destination_container='mp4')
        self._create_stats(t3, source_container='avi', destination_container='mkv')

        history = History()
        result = history.get_container_distribution()
        dest = {r['container']: r['count'] for r in result['destination_containers']}
        assert dest['mp4'] == 2
        assert dest['mkv'] == 1

    def test_container_distribution_library_filter(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='clf1.mkv')
        t2 = self._create_completed_task(label='clf2.mkv')
        self._create_stats(t1, source_container='mkv', library_id=1)
        self._create_stats(t2, source_container='avi', library_id=2)

        history = History()
        result = history.get_container_distribution(library_id=1)
        containers = [r['container'] for r in result['source_containers']]
        assert 'mkv' in containers
        assert 'avi' not in containers

    def test_empty_containers_excluded(self):
        from unmanic.libs.history import History
        t1 = self._create_completed_task(label='ec2.mkv')
        self._create_stats(t1, source_container='', destination_container='')

        history = History()
        result = history.get_container_distribution()
        assert len(result['source_containers']) == 0
        assert len(result['destination_containers']) == 0

    # ------------------------------------------------------------------
    # Space Saved Over Time
    # ------------------------------------------------------------------

    def test_space_saved_day_interval(self):
        from unmanic.libs.history import History
        day1 = datetime.datetime(2024, 1, 15, 10, 0, 0)
        day2 = datetime.datetime(2024, 1, 16, 14, 0, 0)

        t1 = self._create_completed_task(label='day1.mkv', finish_time=day1)
        t2 = self._create_completed_task(label='day2.mkv', finish_time=day2)
        self._create_stats(t1, source_size=2000, dest_size=1000)
        self._create_stats(t2, source_size=3000, dest_size=1500)

        history = History()
        result = history.get_space_saved_over_time(interval='day')
        assert len(result) == 2
        dates = [r['date'] for r in result]
        assert '2024-01-15' in dates
        assert '2024-01-16' in dates

    def test_space_saved_week_interval(self):
        from unmanic.libs.history import History
        # Week 2 and Week 4 of 2024
        week2 = datetime.datetime(2024, 1, 10, 10, 0, 0)
        week4 = datetime.datetime(2024, 1, 24, 14, 0, 0)

        t1 = self._create_completed_task(label='w2.mkv', finish_time=week2)
        t2 = self._create_completed_task(label='w4.mkv', finish_time=week4)
        self._create_stats(t1, source_size=2000, dest_size=1000)
        self._create_stats(t2, source_size=3000, dest_size=1500)

        history = History()
        result = history.get_space_saved_over_time(interval='week')
        assert len(result) == 2
        # All dates should match %Y-W%W format
        for r in result:
            assert r['date'].startswith('2024-W')

    def test_space_saved_month_interval(self):
        from unmanic.libs.history import History
        jan = datetime.datetime(2024, 1, 15, 10, 0, 0)
        feb = datetime.datetime(2024, 2, 15, 14, 0, 0)

        t1 = self._create_completed_task(label='jan.mkv', finish_time=jan)
        t2 = self._create_completed_task(label='feb.mkv', finish_time=feb)
        self._create_stats(t1, source_size=2000, dest_size=1000)
        self._create_stats(t2, source_size=3000, dest_size=1500)

        history = History()
        result = history.get_space_saved_over_time(interval='month')
        assert len(result) == 2
        dates = [r['date'] for r in result]
        assert '2024-01' in dates
        assert '2024-02' in dates

    def test_space_saved_library_filter(self):
        from unmanic.libs.history import History
        day = datetime.datetime(2024, 1, 15, 10, 0, 0)

        t1 = self._create_completed_task(label='lib1.mkv', finish_time=day)
        t2 = self._create_completed_task(label='lib2.mkv', finish_time=day)
        self._create_stats(t1, source_size=2000, dest_size=1000, library_id=1)
        self._create_stats(t2, source_size=3000, dest_size=1500, library_id=2)

        history = History()
        result = history.get_space_saved_over_time(library_id=1, interval='day')
        assert len(result) == 1
        assert result[0]['space_saved'] == 1000

    # ------------------------------------------------------------------
    # Container Fields
    # ------------------------------------------------------------------

    def test_container_fields_saved_correctly(self):
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        t1 = self._create_completed_task(label='cont.mkv')
        self._create_stats(t1, source_container='mkv', destination_container='mp4')

        row = CompressionStats.get(CompressionStats.completedtask == t1.id)
        assert row.source_container == 'mkv'
        assert row.destination_container == 'mp4'


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
