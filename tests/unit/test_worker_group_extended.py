#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_worker_group_extended.py

    Extended unit tests for compresso.libs.worker_group.WorkerGroup.
    Covers error paths, edge cases, schedule management, setters/getters.
"""

import os
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType
from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels import Tags
from compresso.libs.unmodels.workergroups import WorkerGroups, WorkerGroupTags
from compresso.libs.unmodels.workerschedules import WorkerSchedules


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


class TestWorkerGroupExtended:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_wg_ext_')
        self.db_file = os.path.join(self.config_path, 'test_wg_ext.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([WorkerGroups, WorkerGroupTags, Tags, WorkerSchedules])

    def setup_method(self):
        WorkerSchedules.delete().execute()
        WorkerGroupTags.delete().execute()
        WorkerGroups.delete().execute()
        Tags.delete().execute()

    @pytest.mark.unittest
    def test_worker_group_id_less_than_1_raises(self):
        from compresso.libs.worker_group import WorkerGroup
        with pytest.raises(Exception, match="cannot be less than 1"):
            WorkerGroup(0)

    @pytest.mark.unittest
    def test_worker_group_nonexistent_id_raises(self):
        from compresso.libs.worker_group import WorkerGroup
        with pytest.raises(Exception, match="Unable to fetch"):
            WorkerGroup(9999)

    @pytest.mark.unittest
    def test_get_id(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='id-test', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        assert wg.get_id() == group.id

    @pytest.mark.unittest
    def test_set_and_get_name(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='original', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        wg.set_name('renamed')
        assert wg.get_name() == 'renamed'

    @pytest.mark.unittest
    def test_set_and_get_locked(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='lock-test', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        assert wg.get_locked() is False
        wg.set_locked(True)
        assert wg.get_locked() is True

    @pytest.mark.unittest
    def test_set_and_get_number_of_workers(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='workers-test', locked=False, number_of_workers=2)
        wg = WorkerGroup(group.id)
        assert wg.get_number_of_workers() == 2
        wg.set_number_of_workers(5)
        assert wg.get_number_of_workers() == 5

    @pytest.mark.unittest
    def test_set_and_get_worker_type(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='type-test', locked=False, number_of_workers=1, worker_type='cpu')
        wg = WorkerGroup(group.id)
        assert wg.get_worker_type() == 'cpu'
        wg.set_worker_type('gpu')
        assert wg.get_worker_type() == 'gpu'

    @pytest.mark.unittest
    def test_set_worker_type_invalid_raises(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='type-invalid', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        with pytest.raises(ValueError, match="must be 'cpu' or 'gpu'"):
            wg.set_worker_type('tpu')

    @pytest.mark.unittest
    def test_set_and_get_tags(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='tag-test', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        wg.set_tags(['alpha', 'beta'])
        tags = wg.get_tags()
        assert 'alpha' in tags
        assert 'beta' in tags

    @pytest.mark.unittest
    def test_set_tags_replaces_existing(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='tag-replace', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        wg.set_tags(['first'])
        wg.set_tags(['second'])
        tags = wg.get_tags()
        assert 'second' in tags
        # 'first' should no longer be linked
        assert 'first' not in tags

    @pytest.mark.unittest
    def test_set_and_get_worker_event_schedules(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='sched-test', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        schedules = [
            {'repetition': 'daily', 'schedule_task': 'pause', 'schedule_time': '02:00', 'schedule_worker_count': 0},
        ]
        wg.set_worker_event_schedules(schedules)
        result = wg.get_worker_event_schedules()
        assert len(result) == 1
        assert result[0]['repetition'] == 'daily'

    @pytest.mark.unittest
    def test_set_worker_event_schedules_replaces(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='sched-replace', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        wg.set_worker_event_schedules([
            {'repetition': 'daily', 'schedule_task': 'pause', 'schedule_time': '01:00', 'schedule_worker_count': 0},
        ])
        wg.set_worker_event_schedules([
            {'repetition': 'weekly', 'schedule_task': 'resume', 'schedule_time': '03:00', 'schedule_worker_count': 2},
        ])
        result = wg.get_worker_event_schedules()
        assert len(result) == 1
        assert result[0]['repetition'] == 'weekly'

    @pytest.mark.unittest
    def test_set_empty_schedules_clears(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='sched-clear', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        wg.set_worker_event_schedules([
            {'repetition': 'daily', 'schedule_task': 'pause', 'schedule_time': '01:00', 'schedule_worker_count': 0},
        ])
        wg.set_worker_event_schedules([])
        result = wg.get_worker_event_schedules()
        assert len(result) == 0

    @pytest.mark.unittest
    def test_save_generates_name_if_blank(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        wg.save()
        assert wg.get_name() != ''

    @pytest.mark.unittest
    def test_save_persists(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='persist-test', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        wg.set_number_of_workers(10)
        wg.save()
        refreshed = WorkerGroups.get_by_id(group.id)
        assert refreshed.number_of_workers == 10

    @pytest.mark.unittest
    def test_delete_removes_group(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='delete-test', locked=False, number_of_workers=1)
        gid = group.id
        wg = WorkerGroup(gid)
        wg.delete()
        assert WorkerGroups.get_or_none(id=gid) is None

    @pytest.mark.unittest
    def test_delete_locked_raises(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='locked-delete', locked=True, number_of_workers=1)
        wg = WorkerGroup(group.id)
        with pytest.raises(Exception, match="locked"):
            wg.delete()

    @pytest.mark.unittest
    def test_delete_clears_schedules(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='delete-sched', locked=False, number_of_workers=1)
        wg = WorkerGroup(group.id)
        wg.set_worker_event_schedules([
            {'repetition': 'daily', 'schedule_task': 'pause', 'schedule_time': '01:00', 'schedule_worker_count': 0},
        ])
        gid = group.id
        wg.delete()
        remaining = WorkerSchedules.select().where(WorkerSchedules.worker_group_id == gid).count()
        assert remaining == 0

    @pytest.mark.unittest
    def test_create_static_method(self):
        from compresso.libs.worker_group import WorkerGroup
        WorkerGroup.create({
            'name': 'static-create',
            'locked': False,
            'number_of_workers': 3,
            'worker_type': 'cpu',
            'tags': ['tag1'],
            'worker_event_schedules': [],
        })
        groups = list(WorkerGroups.select().where(WorkerGroups.name == 'static-create'))
        assert len(groups) == 1

    @pytest.mark.unittest
    def test_create_generates_name_if_blank(self):
        from compresso.libs.worker_group import WorkerGroup
        WorkerGroup.create({
            'name': '',
            'locked': False,
            'number_of_workers': 1,
        })
        groups = list(WorkerGroups.select())
        assert len(groups) == 1
        assert groups[0].name != ''

    @pytest.mark.unittest
    def test_random_name_returns_string(self):
        from compresso.libs.worker_group import WorkerGroup
        name = WorkerGroup.random_name()
        assert isinstance(name, str)
        assert len(name) > 0

    @pytest.mark.unittest
    def test_get_all_worker_groups_empty_with_legacy_settings(self):
        """When no groups exist and legacy settings are present, creates default."""
        from compresso.libs.worker_group import WorkerGroup
        mock_settings = MagicMock()
        mock_settings.number_of_workers = 4
        mock_settings.worker_event_schedules = []
        with patch('compresso.libs.worker_group.config.Config', return_value=mock_settings):
            result = WorkerGroup.get_all_worker_groups()
        assert len(result) == 1
        assert result[0]['number_of_workers'] == 4

    @pytest.mark.unittest
    def test_create_schedules_static(self):
        from compresso.libs.worker_group import WorkerGroup
        group = WorkerGroups.create(name='cs-test', locked=False, number_of_workers=1)
        WorkerGroup.create_schedules(group.id, [
            {'repetition': 'daily', 'schedule_task': 'pause', 'schedule_time': '00:00', 'schedule_worker_count': 0},
            {'repetition': 'weekly', 'schedule_task': 'resume', 'schedule_time': '06:00', 'schedule_worker_count': 2},
        ])
        count = WorkerSchedules.select().where(WorkerSchedules.worker_group_id == group.id).count()
        assert count == 2
