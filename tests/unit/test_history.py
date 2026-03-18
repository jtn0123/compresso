#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_history.py

    Unit tests for the History class from unmanic/libs/history.py:
    - get_historic_task_list
    - get_total_historic_task_list_count
    - get_historic_task_list_filtered_and_sorted
    - get_current_path_of_historic_tasks_by_id
    - get_historic_tasks_list_with_source_probe
    - get_historic_task_data_dictionary
    - delete_historic_tasks_recursively
    - delete_historic_task_command_logs
    - create_historic_task_entry
    - get_codec_distribution
    - get_resolution_distribution
    - get_container_distribution
    - get_space_saved_over_time

"""

import os
import pytest
import tempfile
import datetime

from unmanic.libs.unmodels.lib import Database


@pytest.mark.unittest
class TestHistory(object):
    """
    TestHistory

    Test History class methods with an in-memory SQLite database.
    """

    db_connection = None

    def setup_class(self):
        """
        Setup the class state for pytest.

        Creates an in-memory SQLite database and the required tables.
        """
        self.config_path = tempfile.mkdtemp(prefix='unmanic_tests_')
        self.db_file = os.path.join(self.config_path, 'test_history.db')

        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import CompletedTasks, CompletedTasksCommandLogs
        from unmanic.libs.unmodels.compressionstats import CompressionStats

        self.db_connection.create_tables([CompletedTasks, CompletedTasksCommandLogs, CompressionStats])
        self.db_connection.execute_sql('SELECT 1')

        from unmanic import config
        self.settings = config.Config(config_path=self.config_path)

    def teardown_class(self):
        pass

    def setup_method(self):
        from unmanic.libs.unmodels.compressionstats import CompressionStats
        from unmanic.libs.unmodels import CompletedTasks, CompletedTasksCommandLogs
        CompressionStats.delete().execute()
        CompletedTasksCommandLogs.delete().execute()
        CompletedTasks.delete().execute()
        self.db_connection.execute_sql('SELECT 1')

    def _make_history(self):
        from unmanic.libs.history import History
        return History()

    def _create_task(self, label='test_file.mkv', abspath=None, success=True,
                     start_time=None, finish_time=None, worker='worker-0'):
        from unmanic.libs.unmodels import CompletedTasks
        now = datetime.datetime.now()
        return CompletedTasks.create(
            task_label=label,
            abspath=abspath or ('/media/' + label),
            task_success=success,
            start_time=start_time or now,
            finish_time=finish_time or now,
            processed_by_worker=worker,
        )

    def _create_command_log(self, task, dump='ffmpeg output log'):
        from unmanic.libs.unmodels import CompletedTasksCommandLogs
        return CompletedTasksCommandLogs.create(
            completedtask_id=task,
            dump=dump,
        )

    def _create_stats(self, task, source_size=1000, dest_size=500,
                      source_codec='hevc', dest_codec='h264',
                      resolution='1920x1080', library_id=1,
                      source_container='mkv', dest_container='mp4'):
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
            destination_container=dest_container,
        )

    # ---------------------------------------------------------------
    # get_historic_task_list
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_historic_task_list_empty(self):
        history = self._make_history()
        result = list(history.get_historic_task_list())
        assert result == []

    @pytest.mark.unittest
    def test_get_historic_task_list_with_data(self):
        self._create_task(label='file_a.mkv')
        self._create_task(label='file_b.mkv')
        self._create_task(label='file_c.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_task_list())
        assert len(result) == 3
        # Should be ordered by id desc
        assert result[0]['task_label'] == 'file_c.mkv'
        assert result[2]['task_label'] == 'file_a.mkv'

    @pytest.mark.unittest
    def test_get_historic_task_list_with_limit(self):
        self._create_task(label='file_a.mkv')
        self._create_task(label='file_b.mkv')
        self._create_task(label='file_c.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_task_list(limit=2))
        assert len(result) == 2
        # First two by desc id should be c, b
        assert result[0]['task_label'] == 'file_c.mkv'
        assert result[1]['task_label'] == 'file_b.mkv'

    # ---------------------------------------------------------------
    # get_total_historic_task_list_count
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_total_historic_task_list_count_empty(self):
        history = self._make_history()
        assert history.get_total_historic_task_list_count() == 0

    @pytest.mark.unittest
    def test_get_total_historic_task_list_count_with_data(self):
        self._create_task(label='a.mkv')
        self._create_task(label='b.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        assert history.get_total_historic_task_list_count() == 2

    # ---------------------------------------------------------------
    # get_historic_task_list_filtered_and_sorted
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_filtered_and_sorted_no_filters(self):
        self._create_task(label='alpha.mkv')
        self._create_task(label='beta.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_task_list_filtered_and_sorted())
        assert len(result) == 2

    @pytest.mark.unittest
    def test_filtered_and_sorted_by_search_value(self):
        self._create_task(label='movie_alpha.mkv')
        self._create_task(label='movie_beta.mkv')
        self._create_task(label='show_gamma.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_task_list_filtered_and_sorted(search_value='movie'))
        assert len(result) == 2
        for r in result:
            assert 'movie' in r['task_label']

    @pytest.mark.unittest
    def test_filtered_and_sorted_by_id_list(self):
        t1 = self._create_task(label='a.mkv')
        self._create_task(label='b.mkv')
        t3 = self._create_task(label='c.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_task_list_filtered_and_sorted(id_list=[t1.id, t3.id]))
        assert len(result) == 2
        labels = {r['task_label'] for r in result}
        assert labels == {'a.mkv', 'c.mkv'}

    @pytest.mark.unittest
    def test_filtered_and_sorted_by_task_success(self):
        self._create_task(label='success.mkv', success=True)
        self._create_task(label='fail.mkv', success=False)
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_task_list_filtered_and_sorted(task_success=True))
        assert len(result) == 1
        assert result[0]['task_label'] == 'success.mkv'

    @pytest.mark.unittest
    def test_filtered_and_sorted_by_time_range(self):
        t1 = datetime.datetime(2024, 1, 1, 12, 0, 0)
        t2 = datetime.datetime(2024, 6, 15, 12, 0, 0)
        t3 = datetime.datetime(2024, 12, 31, 12, 0, 0)
        self._create_task(label='jan.mkv', finish_time=t1)
        self._create_task(label='jun.mkv', finish_time=t2)
        self._create_task(label='dec.mkv', finish_time=t3)
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        after = datetime.datetime(2024, 3, 1)
        before = datetime.datetime(2024, 9, 1)
        result = list(history.get_historic_task_list_filtered_and_sorted(
            after_time=after, before_time=before
        ))
        assert len(result) == 1
        assert result[0]['task_label'] == 'jun.mkv'

    @pytest.mark.unittest
    def test_filtered_and_sorted_order_asc(self):
        self._create_task(label='a.mkv')
        self._create_task(label='b.mkv')
        self._create_task(label='c.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_task_list_filtered_and_sorted(
            order={"column": "task_label", "dir": "asc"}
        ))
        assert result[0]['task_label'] == 'a.mkv'
        assert result[2]['task_label'] == 'c.mkv'

    @pytest.mark.unittest
    def test_filtered_and_sorted_order_invalid_column_falls_back_to_id(self):
        self._create_task(label='a.mkv')
        self._create_task(label='b.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        # Invalid column should fall back to 'id'
        result = list(history.get_historic_task_list_filtered_and_sorted(
            order={"column": "nonexistent_column", "dir": "desc"}
        ))
        assert len(result) == 2

    @pytest.mark.unittest
    def test_filtered_and_sorted_pagination(self):
        for i in range(5):
            self._create_task(label='file_{}.mkv'.format(i))
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_task_list_filtered_and_sorted(
            start=1, length=2
        ))
        assert len(result) == 2

    # ---------------------------------------------------------------
    # get_current_path_of_historic_tasks_by_id
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_current_path_by_id(self):
        t1 = self._create_task(label='a.mkv', abspath='/media/a.mkv')
        t2 = self._create_task(label='b.mkv', abspath='/media/b.mkv')
        self._create_task(label='c.mkv', abspath='/media/c.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_current_path_of_historic_tasks_by_id(id_list=[t1.id, t2.id]))
        assert len(result) == 2
        paths = {r['abspath'] for r in result}
        assert paths == {'/media/a.mkv', '/media/b.mkv'}

    @pytest.mark.unittest
    def test_get_current_path_no_filter_returns_all(self):
        self._create_task(label='a.mkv')
        self._create_task(label='b.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_current_path_of_historic_tasks_by_id())
        assert len(result) == 2

    # ---------------------------------------------------------------
    # get_historic_tasks_list_with_source_probe
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_with_source_probe_filter_by_abspath(self):
        self._create_task(label='a.mkv', abspath='/media/a.mkv')
        self._create_task(label='b.mkv', abspath='/media/b.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_tasks_list_with_source_probe(abspath='/media/a.mkv'))
        assert len(result) == 1
        assert result[0]['task_label'] == 'a.mkv'

    @pytest.mark.unittest
    def test_with_source_probe_filter_by_search_and_success(self):
        self._create_task(label='movie_good.mkv', success=True)
        self._create_task(label='movie_bad.mkv', success=False)
        self._create_task(label='show_good.mkv', success=True)
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = list(history.get_historic_tasks_list_with_source_probe(
            search_value='movie', task_success=True
        ))
        assert len(result) == 1
        assert result[0]['task_label'] == 'movie_good.mkv'

    # ---------------------------------------------------------------
    # get_historic_task_data_dictionary
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_historic_task_data_dictionary_found(self):
        task = self._create_task(label='found.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_historic_task_data_dictionary(task.id)
        assert isinstance(result, dict)
        assert result['task_label'] == 'found.mkv'

    @pytest.mark.unittest
    def test_get_historic_task_data_dictionary_not_found(self):
        history = self._make_history()
        result = history.get_historic_task_data_dictionary(99999)
        assert result is False

    # ---------------------------------------------------------------
    # delete_historic_tasks_recursively
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_delete_historic_tasks_recursively_success(self):
        t1 = self._create_task(label='del_a.mkv')
        t2 = self._create_task(label='del_b.mkv')
        self._create_task(label='keep.mkv')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.delete_historic_tasks_recursively(id_list=[t1.id, t2.id])
        assert result is True

        assert history.get_total_historic_task_list_count() == 1

    @pytest.mark.unittest
    def test_delete_historic_tasks_recursively_empty_list(self):
        history = self._make_history()
        result = history.delete_historic_tasks_recursively(id_list=[])
        assert result is False

    @pytest.mark.unittest
    def test_delete_historic_tasks_recursively_none(self):
        history = self._make_history()
        result = history.delete_historic_tasks_recursively(id_list=None)
        assert result is False

    @pytest.mark.unittest
    def test_delete_historic_tasks_recursively_cascades_command_logs(self):
        task = self._create_task(label='cascade.mkv')
        self._create_command_log(task, dump='log data here')
        self.db_connection.execute_sql('SELECT 1')

        from unmanic.libs.unmodels import CompletedTasksCommandLogs
        assert CompletedTasksCommandLogs.select().count() == 1

        history = self._make_history()
        result = history.delete_historic_tasks_recursively(id_list=[task.id])
        assert result is True
        self.db_connection.execute_sql('SELECT 1')

        assert CompletedTasksCommandLogs.select().count() == 0

    # ---------------------------------------------------------------
    # delete_historic_task_command_logs
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_delete_historic_task_command_logs_success(self):
        t1 = self._create_task(label='log_a.mkv')
        t2 = self._create_task(label='log_b.mkv')
        self._create_command_log(t1, dump='log 1')
        self._create_command_log(t2, dump='log 2')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.delete_historic_task_command_logs(id_list=[t1.id])
        assert result is True

        from unmanic.libs.unmodels import CompletedTasksCommandLogs
        remaining = list(CompletedTasksCommandLogs.select().dicts())
        assert len(remaining) == 1

    @pytest.mark.unittest
    def test_delete_historic_task_command_logs_empty_list(self):
        history = self._make_history()
        result = history.delete_historic_task_command_logs(id_list=[])
        assert result is False

    # ---------------------------------------------------------------
    # create_historic_task_entry
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_create_historic_task_entry_success(self):
        history = self._make_history()
        task_data = {
            'task_label': 'new_task.mkv',
            'abspath': '/media/new_task.mkv',
            'task_success': True,
            'start_time': datetime.datetime.now(),
            'finish_time': datetime.datetime.now(),
            'processed_by_worker': 'worker-1',
        }
        result = history.create_historic_task_entry(task_data)
        self.db_connection.execute_sql('SELECT 1')

        assert result is not None
        assert result.task_label == 'new_task.mkv'
        assert history.get_total_historic_task_list_count() == 1

    @pytest.mark.unittest
    def test_create_historic_task_entry_empty_data_raises(self):
        history = self._make_history()
        with pytest.raises(Exception, match='Task data param empty'):
            history.create_historic_task_entry({})

    @pytest.mark.unittest
    def test_create_historic_task_entry_none_data_raises(self):
        history = self._make_history()
        with pytest.raises(Exception, match='Task data param empty'):
            history.create_historic_task_entry(None)

    # ---------------------------------------------------------------
    # get_codec_distribution
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_codec_distribution_empty(self):
        history = self._make_history()
        result = history.get_codec_distribution()
        assert result['source_codecs'] == []
        assert result['destination_codecs'] == []

    @pytest.mark.unittest
    def test_get_codec_distribution_with_data(self):
        t1 = self._create_task(label='a.mkv')
        t2 = self._create_task(label='b.mkv')
        t3 = self._create_task(label='c.mkv')
        self._create_stats(t1, source_codec='hevc', dest_codec='h264')
        self._create_stats(t2, source_codec='hevc', dest_codec='h264')
        self._create_stats(t3, source_codec='mpeg2', dest_codec='hevc')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_codec_distribution()
        source_codecs = {c['codec']: c['count'] for c in result['source_codecs']}
        assert source_codecs['hevc'] == 2
        assert source_codecs['mpeg2'] == 1

    @pytest.mark.unittest
    def test_get_codec_distribution_library_filter(self):
        t1 = self._create_task(label='a.mkv')
        t2 = self._create_task(label='b.mkv')
        self._create_stats(t1, source_codec='hevc', dest_codec='h264', library_id=1)
        self._create_stats(t2, source_codec='av1', dest_codec='h264', library_id=2)
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_codec_distribution(library_id=1)
        source_codecs = [c['codec'] for c in result['source_codecs']]
        assert 'hevc' in source_codecs
        assert 'av1' not in source_codecs

    # ---------------------------------------------------------------
    # get_resolution_distribution
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_resolution_distribution_empty(self):
        history = self._make_history()
        result = history.get_resolution_distribution()
        assert result == []

    @pytest.mark.unittest
    def test_get_resolution_distribution_with_data(self):
        t1 = self._create_task(label='a.mkv')
        t2 = self._create_task(label='b.mkv')
        t3 = self._create_task(label='c.mkv')
        self._create_stats(t1, resolution='1920x1080')
        self._create_stats(t2, resolution='1920x1080')
        self._create_stats(t3, resolution='3840x2160')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_resolution_distribution()
        res_map = {r['resolution']: r['count'] for r in result}
        assert res_map['1920x1080'] == 2
        assert res_map['3840x2160'] == 1

    # ---------------------------------------------------------------
    # get_container_distribution
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_container_distribution_empty(self):
        history = self._make_history()
        result = history.get_container_distribution()
        assert result['source_containers'] == []
        assert result['destination_containers'] == []

    @pytest.mark.unittest
    def test_get_container_distribution_with_data(self):
        t1 = self._create_task(label='a.mkv')
        t2 = self._create_task(label='b.avi')
        self._create_stats(t1, source_container='mkv', dest_container='mp4')
        self._create_stats(t2, source_container='avi', dest_container='mp4')
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_container_distribution()
        src_map = {c['container']: c['count'] for c in result['source_containers']}
        assert src_map['mkv'] == 1
        assert src_map['avi'] == 1
        dst_map = {c['container']: c['count'] for c in result['destination_containers']}
        assert dst_map['mp4'] == 2

    # ---------------------------------------------------------------
    # get_space_saved_over_time
    # ---------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_space_saved_over_time_day_interval(self):
        day1 = datetime.datetime(2024, 3, 1, 10, 0, 0)
        day2 = datetime.datetime(2024, 3, 2, 10, 0, 0)
        t1 = self._create_task(label='a.mkv', finish_time=day1)
        t2 = self._create_task(label='b.mkv', finish_time=day1)
        t3 = self._create_task(label='c.mkv', finish_time=day2)
        self._create_stats(t1, source_size=1000, dest_size=600)
        self._create_stats(t2, source_size=2000, dest_size=1000)
        self._create_stats(t3, source_size=3000, dest_size=2500)
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_space_saved_over_time(interval='day')
        assert len(result) == 2
        # Day 1: (1000-600) + (2000-1000) = 1400
        assert result[0]['date'] == '2024-03-01'
        assert result[0]['space_saved'] == 1400
        assert result[0]['file_count'] == 2
        # Day 2: 3000-2500 = 500
        assert result[1]['date'] == '2024-03-02'
        assert result[1]['space_saved'] == 500
        assert result[1]['file_count'] == 1

    @pytest.mark.unittest
    def test_get_space_saved_over_time_week_interval(self):
        # Two dates in different ISO weeks
        week1 = datetime.datetime(2024, 1, 3, 10, 0, 0)   # Week 01
        week2 = datetime.datetime(2024, 1, 15, 10, 0, 0)  # Week 03
        t1 = self._create_task(label='a.mkv', finish_time=week1)
        t2 = self._create_task(label='b.mkv', finish_time=week2)
        self._create_stats(t1, source_size=1000, dest_size=500)
        self._create_stats(t2, source_size=2000, dest_size=1500)
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_space_saved_over_time(interval='week')
        assert len(result) == 2

    @pytest.mark.unittest
    def test_get_space_saved_over_time_month_interval(self):
        jan = datetime.datetime(2024, 1, 15, 10, 0, 0)
        feb = datetime.datetime(2024, 2, 15, 10, 0, 0)
        t1 = self._create_task(label='a.mkv', finish_time=jan)
        t2 = self._create_task(label='b.mkv', finish_time=feb)
        self._create_stats(t1, source_size=5000, dest_size=3000)
        self._create_stats(t2, source_size=8000, dest_size=4000)
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_space_saved_over_time(interval='month')
        assert len(result) == 2
        assert result[0]['date'] == '2024-01'
        assert result[0]['space_saved'] == 2000
        assert result[1]['date'] == '2024-02'
        assert result[1]['space_saved'] == 4000

    @pytest.mark.unittest
    def test_get_space_saved_over_time_library_filter(self):
        day1 = datetime.datetime(2024, 5, 1, 10, 0, 0)
        t1 = self._create_task(label='a.mkv', finish_time=day1)
        t2 = self._create_task(label='b.mkv', finish_time=day1)
        self._create_stats(t1, source_size=1000, dest_size=500, library_id=1)
        self._create_stats(t2, source_size=2000, dest_size=1000, library_id=2)
        self.db_connection.execute_sql('SELECT 1')

        history = self._make_history()
        result = history.get_space_saved_over_time(library_id=1, interval='day')
        assert len(result) == 1
        assert result[0]['space_saved'] == 500
        assert result[0]['file_count'] == 1
