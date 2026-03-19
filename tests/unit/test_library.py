#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_library.py

    Unit tests for compresso.libs.library.Library class.
"""

import json
import os
import tempfile

import shutil

import pytest

from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels import Libraries, Tags, EnabledPlugins, LibraryPluginFlow, Plugins
from compresso.libs.unmodels.tasks import Tasks
from compresso.libs.unmodels.workergroups import WorkerGroups, WorkerGroupTags
from compresso.libs.unmodels.workerschedules import WorkerSchedules

LibraryTags = Libraries.tags.get_through_model()


@pytest.mark.unittest
class TestLibraryInit:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_library_')
        self.db_file = os.path.join(self.config_path, 'test_library.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([
            Tasks, Libraries, LibraryTags, Tags,
            WorkerGroups, WorkerGroupTags, WorkerSchedules,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        ])

    def teardown_class(self):
        if self.db_connection:
            self.db_connection.close()
        shutil.rmtree(self.config_path, ignore_errors=True)

    def setup_method(self):
        Tasks.delete().execute()
        EnabledPlugins.delete().execute()
        LibraryPluginFlow.delete().execute()
        # Keep at least one library for tests
        Libraries.delete().execute()
        self.lib_row = Libraries.create(
            name='Test Library',
            path='/media/test',
            locked=False,
            enable_remote_only=False,
            enable_scanner=False,
            enable_inotify=False,
            priority_score=0,
        )

    def test_raises_exception_for_id_zero(self):
        from compresso.libs.library import Library
        with pytest.raises(Exception, match="cannot be less than 1"):
            Library(0)

    def test_raises_exception_for_negative_id(self):
        from compresso.libs.library import Library
        with pytest.raises(Exception, match="cannot be less than 1"):
            Library(-1)

    def test_raises_exception_for_nonexistent_id(self):
        from compresso.libs.library import Library
        with pytest.raises(Exception, match="Unable to fetch library"):
            Library(99999)

    def test_successful_init_with_valid_id(self):
        from compresso.libs.library import Library
        lib = Library(self.lib_row.id)
        assert lib.get_name() == 'Test Library'


@pytest.mark.unittest
class TestLibraryGettersSetters:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_library_gs_')
        self.db_file = os.path.join(self.config_path, 'test.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([
            Tasks, Libraries, LibraryTags, Tags,
            WorkerGroups, WorkerGroupTags, WorkerSchedules,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        ])

    def setup_method(self):
        Libraries.delete().execute()
        self.lib_row = Libraries.create(
            name='getter_setter_lib',
            path='/media/gs',
            locked=False,
            enable_remote_only=False,
            enable_scanner=False,
            enable_inotify=False,
            priority_score=0,
        )

    def _lib(self):
        from compresso.libs.library import Library
        return Library(self.lib_row.id)

    def test_get_name_returns_model_name(self):
        assert self._lib().get_name() == 'getter_setter_lib'

    def test_set_name_updates_model(self):
        lib = self._lib()
        lib.set_name('new_name')
        assert lib.get_name() == 'new_name'

    def test_get_path_returns_model_path(self):
        assert self._lib().get_path() == '/media/gs'

    def test_set_path_updates_model(self):
        lib = self._lib()
        lib.set_path('/new/path')
        assert lib.get_path() == '/new/path'

    def test_get_locked_returns_model_locked(self):
        assert self._lib().get_locked() is False

    def test_set_locked_updates_model(self):
        lib = self._lib()
        lib.set_locked(True)
        assert lib.get_locked() is True

    def test_get_enable_remote_only(self):
        assert self._lib().get_enable_remote_only() is False

    def test_set_enable_remote_only(self):
        lib = self._lib()
        lib.set_enable_remote_only(True)
        assert lib.get_enable_remote_only() is True

    def test_get_enable_scanner(self):
        assert self._lib().get_enable_scanner() is False

    def test_set_enable_scanner(self):
        lib = self._lib()
        lib.set_enable_scanner(True)
        assert lib.get_enable_scanner() is True

    def test_get_enable_inotify(self):
        assert self._lib().get_enable_inotify() is False

    def test_set_enable_inotify(self):
        lib = self._lib()
        lib.set_enable_inotify(True)
        assert lib.get_enable_inotify() is True

    def test_get_priority_score(self):
        assert self._lib().get_priority_score() == 0

    def test_set_priority_score(self):
        lib = self._lib()
        lib.set_priority_score(50)
        assert lib.get_priority_score() == 50


@pytest.mark.unittest
class TestLibraryCodecFiltering:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_library_codec_')
        self.db_file = os.path.join(self.config_path, 'test.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([
            Tasks, Libraries, LibraryTags, Tags,
            WorkerGroups, WorkerGroupTags, WorkerSchedules,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        ])

    def setup_method(self):
        Libraries.delete().execute()
        self.lib_row = Libraries.create(
            name='codec_lib',
            path='/media/codec',
            locked=False,
            enable_remote_only=False,
            enable_scanner=False,
            enable_inotify=False,
            priority_score=0,
            target_codecs='',
            skip_codecs='',
        )

    def _lib(self):
        from compresso.libs.library import Library
        return Library(self.lib_row.id)

    # --- target_codecs ---

    def test_get_target_codecs_empty_string_returns_empty_list(self):
        assert self._lib().get_target_codecs() == []

    def test_get_target_codecs_valid_json_returns_list(self):
        self.lib_row.target_codecs = json.dumps(["h264", "hevc"])
        self.lib_row.save()
        assert self._lib().get_target_codecs() == ["h264", "hevc"]

    def test_get_target_codecs_invalid_json_returns_empty_list(self):
        self.lib_row.target_codecs = 'not json'
        self.lib_row.save()
        assert self._lib().get_target_codecs() == []

    def test_get_target_codecs_empty_field_returns_empty_list(self):
        # target_codecs defaults to '' which should return []
        lib = self._lib()
        lib.model.target_codecs = ''
        assert lib.get_target_codecs() == []

    def test_set_target_codecs_with_list_serializes_json(self):
        lib = self._lib()
        lib.set_target_codecs(["h264", "hevc"])
        assert lib.model.target_codecs == json.dumps(["h264", "hevc"])

    def test_set_target_codecs_with_string_stores_directly(self):
        lib = self._lib()
        lib.set_target_codecs('["h264"]')
        assert lib.model.target_codecs == '["h264"]'

    def test_set_target_codecs_with_none_stores_empty_string(self):
        lib = self._lib()
        lib.set_target_codecs(None)
        assert lib.model.target_codecs == ''

    # --- skip_codecs ---

    def test_get_skip_codecs_empty_string_returns_empty_list(self):
        assert self._lib().get_skip_codecs() == []

    def test_get_skip_codecs_valid_json_returns_list(self):
        self.lib_row.skip_codecs = json.dumps(["mpeg4"])
        self.lib_row.save()
        assert self._lib().get_skip_codecs() == ["mpeg4"]

    def test_get_skip_codecs_invalid_json_returns_empty_list(self):
        self.lib_row.skip_codecs = 'not json'
        self.lib_row.save()
        assert self._lib().get_skip_codecs() == []

    def test_set_skip_codecs_with_list_serializes_json(self):
        lib = self._lib()
        lib.set_skip_codecs(["vp9"])
        assert lib.model.skip_codecs == json.dumps(["vp9"])

    def test_set_skip_codecs_with_none_stores_empty_string(self):
        lib = self._lib()
        lib.set_skip_codecs(None)
        assert lib.model.skip_codecs == ''


@pytest.mark.unittest
class TestLibrarySizeGuardrails:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_library_guard_')
        self.db_file = os.path.join(self.config_path, 'test.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([
            Tasks, Libraries, LibraryTags, Tags,
            WorkerGroups, WorkerGroupTags, WorkerSchedules,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        ])

    def setup_method(self):
        Libraries.delete().execute()
        self.lib_row = Libraries.create(
            name='guard_lib',
            path='/media/guard',
            locked=False,
            enable_remote_only=False,
            enable_scanner=False,
            enable_inotify=False,
            priority_score=0,
        )

    def _lib(self):
        from compresso.libs.library import Library
        return Library(self.lib_row.id)

    def test_get_size_guardrail_enabled_returns_bool(self):
        assert self._lib().get_size_guardrail_enabled() is False

    def test_set_size_guardrail_enabled_converts_to_bool(self):
        lib = self._lib()
        lib.set_size_guardrail_enabled(1)
        assert lib.get_size_guardrail_enabled() is True

    def test_set_size_guardrail_min_pct_clamps_low(self):
        lib = self._lib()
        lib.set_size_guardrail_min_pct(1)
        assert lib.get_size_guardrail_min_pct() == 5

    def test_set_size_guardrail_min_pct_clamps_high(self):
        lib = self._lib()
        lib.set_size_guardrail_min_pct(100)
        assert lib.get_size_guardrail_min_pct() == 95

    def test_set_size_guardrail_min_pct_valid_value(self):
        lib = self._lib()
        lib.set_size_guardrail_min_pct(50)
        assert lib.get_size_guardrail_min_pct() == 50

    def test_set_size_guardrail_max_pct_clamps_low(self):
        lib = self._lib()
        lib.set_size_guardrail_max_pct(10)
        assert lib.get_size_guardrail_max_pct() == 50

    def test_set_size_guardrail_max_pct_clamps_high(self):
        lib = self._lib()
        lib.set_size_guardrail_max_pct(200)
        assert lib.get_size_guardrail_max_pct() == 100

    def test_set_size_guardrail_max_pct_valid_value(self):
        lib = self._lib()
        lib.set_size_guardrail_max_pct(80)
        assert lib.get_size_guardrail_max_pct() == 80


@pytest.mark.unittest
class TestLibraryReplacementPolicy:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_library_policy_')
        self.db_file = os.path.join(self.config_path, 'test.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([
            Tasks, Libraries, LibraryTags, Tags,
            WorkerGroups, WorkerGroupTags, WorkerSchedules,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        ])

    def setup_method(self):
        Libraries.delete().execute()
        self.lib_row = Libraries.create(
            name='policy_lib',
            path='/media/policy',
            locked=False,
            enable_remote_only=False,
            enable_scanner=False,
            enable_inotify=False,
            priority_score=0,
        )

    def _lib(self):
        from compresso.libs.library import Library
        return Library(self.lib_row.id)

    def test_get_replacement_policy_default_empty_string(self):
        assert self._lib().get_replacement_policy() == ''

    def test_set_replacement_policy_valid_replace(self):
        lib = self._lib()
        lib.set_replacement_policy('replace')
        assert lib.get_replacement_policy() == 'replace'

    def test_set_replacement_policy_valid_approval_required(self):
        lib = self._lib()
        lib.set_replacement_policy('approval_required')
        assert lib.get_replacement_policy() == 'approval_required'

    def test_set_replacement_policy_valid_keep_both(self):
        lib = self._lib()
        lib.set_replacement_policy('keep_both')
        assert lib.get_replacement_policy() == 'keep_both'

    def test_set_replacement_policy_invalid_falls_back_to_empty(self):
        lib = self._lib()
        lib.set_replacement_policy('invalid_policy')
        assert lib.get_replacement_policy() == ''

    def test_set_replacement_policy_none_stores_empty(self):
        lib = self._lib()
        lib.set_replacement_policy(None)
        assert lib.get_replacement_policy() == ''


@pytest.mark.unittest
class TestLibraryDelete:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_library_del_')
        self.db_file = os.path.join(self.config_path, 'test.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([
            Tasks, Libraries, LibraryTags, Tags,
            WorkerGroups, WorkerGroupTags, WorkerSchedules,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        ])

    def setup_method(self):
        Tasks.delete().execute()
        EnabledPlugins.delete().execute()
        LibraryPluginFlow.delete().execute()
        Libraries.delete().execute()

    def _create_library(self, **kwargs):
        defaults = dict(
            name='lib',
            path='/media/lib',
            locked=False,
            enable_remote_only=False,
            enable_scanner=False,
            enable_inotify=False,
            priority_score=0,
        )
        defaults.update(kwargs)
        return Libraries.create(**defaults)

    def test_delete_default_library_raises(self):
        from compresso.libs.library import Library
        row = self._create_library(id=1, name='default')
        lib = Library(row.id)
        with pytest.raises(Exception, match="Unable to remove the default library"):
            lib.delete()

    def test_delete_locked_library_raises(self):
        from compresso.libs.library import Library
        # Create default first so ID=1 exists
        self._create_library(id=1, name='default')
        row = self._create_library(name='locked_lib', locked=True)
        lib = Library(row.id)
        with pytest.raises(Exception, match="Unable to remove a locked library"):
            lib.delete()

    def test_delete_unlocked_non_default_succeeds(self):
        from compresso.libs.library import Library
        self._create_library(id=1, name='default')
        row = self._create_library(name='deletable', locked=False)
        lib = Library(row.id)
        lib.delete()
        assert Libraries.get_or_none(id=row.id) is None


@pytest.mark.unittest
class TestLibraryCreate:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_library_create_')
        self.db_file = os.path.join(self.config_path, 'test.db')
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([
            Tasks, Libraries, LibraryTags, Tags,
            WorkerGroups, WorkerGroupTags, WorkerSchedules,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        ])

    def setup_method(self):
        Libraries.delete().execute()

    def test_create_removes_id_from_data(self):
        from compresso.libs.library import Library
        data = {
            'id': 999,
            'name': 'new_lib',
            'path': '/media/new',
            'locked': False,
            'enable_remote_only': False,
            'enable_scanner': False,
            'enable_inotify': False,
            'priority_score': 0,
        }
        lib = Library.create(data)
        # ID should be auto-assigned, not 999
        assert lib.get_id() != 999

    def test_create_returns_library_instance(self):
        from compresso.libs.library import Library
        data = {
            'name': 'created_lib',
            'path': '/media/created',
            'locked': False,
            'enable_remote_only': False,
            'enable_scanner': False,
            'enable_inotify': False,
            'priority_score': 0,
        }
        lib = Library.create(data)
        assert lib.get_name() == 'created_lib'


@pytest.mark.unittest
class TestGenerateRandomLibraryName:

    def test_returns_string_with_expected_format(self):
        from compresso.libs.library import generate_random_library_name
        name = generate_random_library_name()
        assert ", the " in name
        assert " library" in name

    def test_returns_different_names(self):
        from compresso.libs.library import generate_random_library_name
        names = {generate_random_library_name() for _ in range(10)}
        # With the large word lists, 10 calls should produce at least 2 unique names
        assert len(names) >= 2
