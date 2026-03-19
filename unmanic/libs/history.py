#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.history.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     23 Jun 2019, (10:42 AM)

    Copyright:
           Copyright (C) Josh Sunnex - All Rights Reserved

           Permission is hereby granted, free of charge, to any person obtaining a copy
           of this software and associated documentation files (the "Software"), to deal
           in the Software without restriction, including without limitation the rights
           to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
           copies of the Software, and to permit persons to whom the Software is
           furnished to do so, subject to the following conditions:

           The above copyright notice and this permission notice shall be included in all
           copies or substantial portions of the Software.

           THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
           EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
           MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
           IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
           DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
           OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
           OR OTHER DEALINGS IN THE SOFTWARE.

"""

import json

from unmanic import config
from unmanic.libs.logs import UnmanicLogging
from peewee import fn
from unmanic.libs.unmodels import CompletedTasks, CompletedTasksCommandLogs, CompressionStats

try:
    from json.decoder import JSONDecodeError
except ImportError:
    JSONDecodeError = ValueError


class History(object):
    """
    History

    Record statistical data for historical jobs
    """

    def __init__(self):
        self.name = __class__.__name__
        self.settings = config.Config()
        self.logger = UnmanicLogging.get_logger(name=__class__.__name__)

    def get_historic_task_list(self, limit=None):
        """
        Read all historic tasks entries

        :return:
        """
        try:
            # Fetch a single row (get() will raise DoesNotExist exception if no results are found)
            if limit:
                historic_tasks = CompletedTasks.select().order_by(CompletedTasks.id.desc()).limit(limit)
            else:
                historic_tasks = CompletedTasks.select().order_by(CompletedTasks.id.desc())
        except CompletedTasks.DoesNotExist:
            # No historic entries exist yet
            self.logger.warning("No historic tasks exist yet.")
            historic_tasks = []

        return historic_tasks.dicts()

    def get_total_historic_task_list_count(self):
        query = CompletedTasks.select().order_by(CompletedTasks.id.desc())
        return query.count()

    def get_historic_task_list_filtered_and_sorted(self, order=None, start=0, length=None, search_value=None, id_list=None,
                                                   task_success=None, after_time=None, before_time=None):
        try:
            query = (CompletedTasks.select())

            if id_list:
                query = query.where(CompletedTasks.id.in_(id_list))

            if search_value:
                query = query.where(CompletedTasks.task_label.contains(search_value))

            if task_success is not None:
                query = query.where(CompletedTasks.task_success.in_([task_success]))

            if after_time is not None:
                query = query.where(CompletedTasks.finish_time >= after_time)

            if before_time is not None:
                query = query.where(CompletedTasks.finish_time <= before_time)

            # Get order by
            ALLOWED_ORDER_COLUMNS = {'id', 'task_label', 'task_success', 'start_time', 'finish_time', 'processed_by_worker', 'abspath'}
            if order:
                col = order.get("column", "id")
                if col not in ALLOWED_ORDER_COLUMNS:
                    col = "id"
                order_field = getattr(CompletedTasks, col, CompletedTasks.id)
                if order.get("dir") == "asc":
                    order_by = order_field.asc()
                else:
                    order_by = order_field.desc()

                query = query.order_by(order_by)

            if length:
                query = query.limit(length).offset(start)

        except CompletedTasks.DoesNotExist:
            # No historic entries exist yet
            self.logger.warning("No historic tasks exist yet.")
            query = []

        return query.dicts()

    def get_current_path_of_historic_tasks_by_id(self, id_list=None):
        """
        Returns a list of CompletedTasks filtered by id_list and joined with the current absolute path of that file.
        For failures this will be the source path
        For success, this will be the destination path

        :param id_list:
        :return:
        """
        # noinspection SqlDialectInspection
        """
            SELECT
                t1.*,
                t2.type,
                t2.abspath
            FROM completedtasks AS "t1"
            WHERE t1.id IN ( %s)
        """
        query = (
            CompletedTasks.select(CompletedTasks.id, CompletedTasks.task_label, CompletedTasks.task_success,
                                  CompletedTasks.abspath)
        )

        if id_list:
            query = query.where(CompletedTasks.id.in_(id_list))

        return query.dicts()

    def get_historic_tasks_list_with_source_probe(self, order=None, start=0, length=None, search_value=None, id_list=None,
                                                  task_success=None, abspath=None):
        """
        Return a list of matching historic tasks with their source file's ffmpeg probe.

        :param order:
        :param start:
        :param length:
        :param search_value:
        :param id_list:
        :param task_success:
        :param abspath:
        :return:
        """
        query = (
            CompletedTasks.select(CompletedTasks.id, CompletedTasks.task_label, CompletedTasks.task_success,
                                  CompletedTasks.abspath))

        if id_list:
            query = query.where(CompletedTasks.id.in_(id_list))

        if search_value:
            query = query.where(CompletedTasks.task_label.contains(search_value))

        if task_success is not None:
            query = query.where(CompletedTasks.task_success.in_([task_success]))

        if abspath:
            query = query.where(CompletedTasks.abspath.in_([abspath]))

        return query.dicts()

    def get_historic_task_data_dictionary(self, task_id):
        """
        Read all data for a task and return a dictionary of that data

        :return:
        """
        # Get historic task matching the id
        try:
            # Fetch the historic task (get() will raise DoesNotExist exception if no results are found)
            historic_tasks = CompletedTasks.get_by_id(task_id)
        except CompletedTasks.DoesNotExist:
            self.logger.exception("Failed to retrieve historic task from database for id %s.", task_id)
            return False
        # Get all saved data for this task and create dictionary of task data
        historic_task = historic_tasks.model_to_dict()
        # Return task data dictionary
        return historic_task

    def delete_historic_tasks_recursively(self, id_list=None):
        """
        Deletes a given list of historic tasks based on their IDs

        :param id_list:
        :return:
        """
        # Prevent running if no list of IDs was given
        if not id_list:
            return False

        try:
            query = (CompletedTasks.select())

            if id_list:
                query = query.where(CompletedTasks.id.in_(id_list))

            for historic_task_id in query:
                try:
                    historic_task_id.delete_instance(recursive=True)
                except Exception:
                    # Catch delete exceptions
                    self.logger.exception("An error occurred while deleting historic task ID: %s.", historic_task_id)
                    return False

            return True

        except CompletedTasks.DoesNotExist:
            # No historic entries exist yet
            self.logger.warning("No historic tasks exist yet.")

    def delete_historic_task_command_logs(self, id_list=None):
        """
        Deletes command logs for a given list of historic task IDs.

        :param id_list:
        :return:
        """
        # Prevent running if no list of IDs was given
        if not id_list:
            return False

        try:
            query = CompletedTasksCommandLogs.delete().where(
                CompletedTasksCommandLogs.completedtask_id.in_(id_list)
            )
            query.execute()
            return True
        except Exception:
            self.logger.exception("An error occurred while deleting historic task command logs.")
            return False

    def save_task_history(self, task_data):
        """
        Record a task's data and state to the database.

        :param task_data:
        :return:
        """
        try:
            # Create the new historical task entry
            new_historic_task = self.create_historic_task_entry(task_data)
            # Create an entry of the data from the source ffprobe
            self.create_historic_task_ffmpeg_log_entry(new_historic_task, task_data.get('log', ''))
            # Create compression stats entry for successful tasks
            source_size = task_data.get('source_size', 0)
            destination_size = task_data.get('destination_size', 0)
            if task_data.get('task_success', False):
                self.create_compression_stats_entry(
                    new_historic_task,
                    source_size=source_size,
                    destination_size=destination_size,
                    source_codec=task_data.get('source_codec', ''),
                    destination_codec=task_data.get('destination_codec', ''),
                    source_resolution=task_data.get('source_resolution', ''),
                    library_id=task_data.get('library_id', 1),
                    source_container=task_data.get('source_container', ''),
                    destination_container=task_data.get('destination_container', ''),
                )
        except Exception as error:
            self.logger.exception("Failed to save historic task entry to database. %s", error)
            return False
        return True

    @staticmethod
    def create_historic_task_ffmpeg_log_entry(historic_task, log):
        """
        Create an entry of the stdout log from the ffmpeg command

        :param historic_task:
        :param log:
        :return:
        """
        CompletedTasksCommandLogs.create(
            completedtask_id=historic_task,
            dump=log
        )

    def create_historic_task_entry(self, task_data):
        """
        Create a historic task entry

        Required task_data params:
            - task_label
            - task_success
            - start_time
            - finish_time
            - processed_by_worker

        :param task_data:
        :return:
        """
        if not task_data:
            self.logger.debug('Task data param empty: %s', json.dumps(task_data))
            raise Exception('Task data param empty. This should not happen - Something has gone really wrong.')

        new_historic_task = CompletedTasks.create(task_label=task_data['task_label'],
                                                  abspath=task_data['abspath'],
                                                  task_success=task_data['task_success'],
                                                  start_time=task_data['start_time'],
                                                  finish_time=task_data['finish_time'],
                                                  processed_by_worker=task_data['processed_by_worker'])
        return new_historic_task

    @staticmethod
    def create_compression_stats_entry(historic_task, source_size=0, destination_size=0,
                                       source_codec='', destination_codec='',
                                       source_resolution='', library_id=1,
                                       source_container='', destination_container=''):
        """
        Create a compression stats entry for a completed task.

        :param historic_task:
        :param source_size:
        :param destination_size:
        :param source_codec:
        :param destination_codec:
        :param source_resolution:
        :param library_id:
        :param source_container:
        :param destination_container:
        :return:
        """
        CompressionStats.create(
            completedtask=historic_task,
            source_size=source_size,
            destination_size=destination_size,
            source_codec=source_codec or '',
            destination_codec=destination_codec or '',
            source_resolution=source_resolution or '',
            library_id=library_id,
            source_container=source_container or '',
            destination_container=destination_container or '',
        )

    def get_library_compression_summary(self, library_id=None):
        """
        Get aggregate compression statistics, optionally filtered by library.

        :param library_id: Optional library ID to filter by
        :return: dict with total_source_size, total_destination_size, file_count, avg_ratio, per_library breakdown
        """
        query = CompressionStats.select(
            CompressionStats.library_id,
            fn.SUM(CompressionStats.source_size).alias('total_source'),
            fn.SUM(CompressionStats.destination_size).alias('total_dest'),
            fn.COUNT(CompressionStats.id).alias('file_count'),
        )

        if library_id is not None:
            query = query.where(CompressionStats.library_id == library_id)

        query = query.group_by(CompressionStats.library_id)

        per_library = []
        grand_total_source = 0
        grand_total_dest = 0
        grand_file_count = 0

        for row in query:
            total_source = row.total_source or 0
            total_dest = row.total_dest or 0
            file_count = row.file_count or 0
            avg_ratio = (total_dest / total_source) if total_source > 0 else 0

            per_library.append({
                'library_id': row.library_id,
                'total_source_size': total_source,
                'total_destination_size': total_dest,
                'file_count': file_count,
                'avg_ratio': round(avg_ratio, 4),
                'space_saved': total_source - total_dest,
            })

            grand_total_source += total_source
            grand_total_dest += total_dest
            grand_file_count += file_count

        grand_avg_ratio = (grand_total_dest / grand_total_source) if grand_total_source > 0 else 0

        return {
            'total_source_size': grand_total_source,
            'total_destination_size': grand_total_dest,
            'file_count': grand_file_count,
            'avg_ratio': round(grand_avg_ratio, 4),
            'space_saved': grand_total_source - grand_total_dest,
            'per_library': per_library,
        }

    def get_compression_stats_for_task(self, task_id):
        """
        Get compression stats for a single completed task.

        :param task_id: The completed task ID
        :return: dict or None
        """
        try:
            stats = CompressionStats.get(CompressionStats.completedtask == task_id)
            ratio = (stats.destination_size / stats.source_size) if stats.source_size > 0 else 0
            return {
                'source_size': stats.source_size,
                'destination_size': stats.destination_size,
                'source_codec': stats.source_codec,
                'destination_codec': stats.destination_codec,
                'source_resolution': stats.source_resolution,
                'library_id': stats.library_id,
                'ratio': round(ratio, 4),
                'space_saved': stats.source_size - stats.destination_size,
            }
        except CompressionStats.DoesNotExist:
            return None

    def get_compression_stats_paginated(self, start=0, length=10, search_value=None,
                                         library_id=None, order=None):
        """
        Get paginated compression stats joined with completed task labels.

        :return: dict with recordsTotal, recordsFiltered, results
        """
        query = (
            CompressionStats
            .select(
                CompressionStats,
                CompletedTasks.task_label,
                CompletedTasks.task_success,
                CompletedTasks.finish_time,
            )
            .join(CompletedTasks, on=(CompressionStats.completedtask == CompletedTasks.id))
        )

        if library_id is not None:
            query = query.where(CompressionStats.library_id == library_id)

        if search_value:
            query = query.where(CompletedTasks.task_label.contains(search_value))

        records_total = CompressionStats.select().count()
        records_filtered = query.count()

        # Default order
        ALLOWED_CS_COLUMNS = {'source_size', 'destination_size', 'library_id'}
        ALLOWED_CT_COLUMNS = {'finish_time', 'task_label', 'task_success'}
        if order:
            col = order.get('column', 'finish_time')
            direction = order.get('dir', 'desc')
            if col in ALLOWED_CS_COLUMNS:
                order_field = getattr(CompressionStats, col)
            elif col in ALLOWED_CT_COLUMNS:
                order_field = getattr(CompletedTasks, col)
            else:
                order_field = CompletedTasks.finish_time
            if direction == 'asc':
                query = query.order_by(order_field.asc())
            else:
                query = query.order_by(order_field.desc())
        else:
            query = query.order_by(CompletedTasks.finish_time.desc())

        if length:
            query = query.limit(length).offset(start)

        results = []
        for row in query:
            source_size = row.source_size or 0
            dest_size = row.destination_size or 0
            ratio = (dest_size / source_size) if source_size > 0 else 0
            results.append({
                'id': row.id,
                'completedtask_id': row.completedtask_id,
                'task_label': row.completedtask.task_label,
                'task_success': row.completedtask.task_success,
                'finish_time': row.completedtask.finish_time,
                'source_size': source_size,
                'destination_size': dest_size,
                'source_codec': row.source_codec or '',
                'destination_codec': row.destination_codec or '',
                'source_resolution': row.source_resolution or '',
                'library_id': row.library_id,
                'ratio': round(ratio, 4),
                'space_saved': source_size - dest_size,
            })

        return {
            'recordsTotal': records_total,
            'recordsFiltered': records_filtered,
            'results': results,
        }

    def get_codec_distribution(self, library_id=None):
        """
        Get distribution of source and destination codecs.

        :param library_id: Optional library ID filter
        :return: dict with source_codecs and destination_codecs lists
        """
        source_query = CompressionStats.select(
            CompressionStats.source_codec,
            fn.COUNT(CompressionStats.id).alias('count'),
        )
        dest_query = CompressionStats.select(
            CompressionStats.destination_codec,
            fn.COUNT(CompressionStats.id).alias('count'),
        )

        if library_id is not None:
            source_query = source_query.where(CompressionStats.library_id == library_id)
            dest_query = dest_query.where(CompressionStats.library_id == library_id)

        source_query = source_query.where(CompressionStats.source_codec != '').group_by(CompressionStats.source_codec)
        dest_query = dest_query.where(CompressionStats.destination_codec != '').group_by(CompressionStats.destination_codec)

        source_codecs = [{'codec': row.source_codec, 'count': row.count} for row in source_query]
        dest_codecs = [{'codec': row.destination_codec, 'count': row.count} for row in dest_query]

        return {
            'source_codecs': source_codecs,
            'destination_codecs': dest_codecs,
        }

    def get_resolution_distribution(self, library_id=None):
        """
        Get distribution of source resolutions.

        :param library_id: Optional library ID filter
        :return: list of {resolution, count}
        """
        query = CompressionStats.select(
            CompressionStats.source_resolution,
            fn.COUNT(CompressionStats.id).alias('count'),
        )

        if library_id is not None:
            query = query.where(CompressionStats.library_id == library_id)

        query = query.where(CompressionStats.source_resolution != '').group_by(CompressionStats.source_resolution)

        return [{'resolution': row.source_resolution, 'count': row.count} for row in query]

    def get_container_distribution(self, library_id=None):
        """
        Get distribution of source and destination containers.

        :param library_id: Optional library ID filter
        :return: dict with source_containers and destination_containers lists
        """
        source_query = CompressionStats.select(
            CompressionStats.source_container,
            fn.COUNT(CompressionStats.id).alias('count'),
        )
        dest_query = CompressionStats.select(
            CompressionStats.destination_container,
            fn.COUNT(CompressionStats.id).alias('count'),
        )

        if library_id is not None:
            source_query = source_query.where(CompressionStats.library_id == library_id)
            dest_query = dest_query.where(CompressionStats.library_id == library_id)

        source_query = source_query.where(CompressionStats.source_container != '').group_by(CompressionStats.source_container)
        dest_query = dest_query.where(CompressionStats.destination_container != '').group_by(CompressionStats.destination_container)

        source_containers = [{'container': row.source_container, 'count': row.count} for row in source_query]
        dest_containers = [{'container': row.destination_container, 'count': row.count} for row in dest_query]

        return {
            'source_containers': source_containers,
            'destination_containers': dest_containers,
        }

    def get_space_saved_over_time(self, library_id=None, interval='day'):
        """
        Get space saved over time, grouped by date interval.

        :param library_id: Optional library ID filter
        :param interval: 'day', 'week', or 'month'
        :return: list of {date, space_saved, file_count}
        """
        if interval == 'month':
            date_trunc = fn.strftime('%Y-%m', CompletedTasks.finish_time)
        elif interval == 'week':
            date_trunc = fn.strftime('%Y-W%W', CompletedTasks.finish_time)
        else:
            date_trunc = fn.strftime('%Y-%m-%d', CompletedTasks.finish_time)

        query = (
            CompressionStats
            .select(
                date_trunc.alias('date_group'),
                fn.SUM(CompressionStats.source_size - CompressionStats.destination_size).alias('space_saved'),
                fn.COUNT(CompressionStats.id).alias('file_count'),
            )
            .join(CompletedTasks, on=(CompressionStats.completedtask == CompletedTasks.id))
        )

        if library_id is not None:
            query = query.where(CompressionStats.library_id == library_id)

        query = query.group_by(date_trunc).order_by(date_trunc.asc())

        results = []
        for row in query:
            results.append({
                'date': row.date_group,
                'space_saved': row.space_saved or 0,
                'file_count': row.file_count or 0,
            })

        return results
