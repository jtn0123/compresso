#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_library_extended.py

    Extended unit tests for compresso.libs.library.Library class,
    covering get_all_libraries, save, export, tags, enabled_plugins, plugin_flow.
"""

import json
import os
import shutil
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType
from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels import Libraries, Tags, EnabledPlugins, LibraryPluginFlow, Plugins
from compresso.libs.unmodels.tasks import Tasks
from compresso.libs.unmodels.workergroups import WorkerGroups, WorkerGroupTags
from compresso.libs.unmodels.workerschedules import WorkerSchedules

LibraryTags = Libraries.tags.get_through_model()


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


# ------------------------------------------------------------------
# TestGetAllLibraries
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetAllLibraries:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_lib_getall_')
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

    def teardown_class(self):
        if self.db_connection:
            self.db_connection.close()
        shutil.rmtree(self.config_path, ignore_errors=True)

    def setup_method(self):
        LibraryTags.delete().execute()
        Tags.delete().execute()
        Libraries.delete().execute()

    def test_creates_default_library_when_none_exist(self):
        from compresso.libs.library import Library
        with patch('compresso.config.Config') as mock_config_cls, \
             patch('compresso.libs.library.common.get_default_library_path', return_value='/default/library'):
            mock_config = MagicMock()
            mock_config.get_library_path.return_value = '/default/library'
            mock_config_cls.return_value = mock_config

            result = Library.get_all_libraries()

            assert len(result) == 1
            assert result[0]['path'] == '/default/library'
            assert result[0]['id'] == 1

    def test_returns_existing_libraries(self):
        from compresso.libs.library import Library
        Libraries.create(
            id=1, name='Default', path='/default/library', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        Libraries.create(
            name='Movies', path='/movies', locked=False,
            enable_remote_only=False, enable_scanner=True, enable_inotify=False,
            priority_score=0,
        )
        with patch('compresso.config.Config') as mock_config_cls, \
             patch('compresso.libs.library.common.get_default_library_path', return_value='/default/library'):
            mock_config = MagicMock()
            mock_config.get_library_path.return_value = '/default/library'
            mock_config_cls.return_value = mock_config

            result = Library.get_all_libraries()

            assert len(result) == 2
            # Default library should come first
            assert result[0]['id'] == 1

    def test_updates_default_library_path(self):
        from compresso.libs.library import Library
        Libraries.create(
            id=1, name='Default', path='/old/path', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        with patch('compresso.config.Config') as mock_config_cls, \
             patch('compresso.libs.library.common.get_default_library_path', return_value='/new/default/path'):
            mock_config = MagicMock()
            mock_config.get_library_path.return_value = '/new/default/path'
            mock_config_cls.return_value = mock_config

            result = Library.get_all_libraries()

            assert result[0]['path'] == '/new/default/path'

    def test_includes_tags(self):
        from compresso.libs.library import Library
        lib = Libraries.create(
            id=1, name='Default', path='/default', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        tag1 = Tags.create(name='movies')
        tag2 = Tags.create(name='tv')
        lib.tags.add([tag1, tag2])
        with patch('compresso.config.Config') as mock_config_cls, \
             patch('compresso.libs.library.common.get_default_library_path', return_value='/default'):
            mock_config = MagicMock()
            mock_config.get_library_path.return_value = '/default'
            mock_config_cls.return_value = mock_config

            result = Library.get_all_libraries()

            assert 'movies' in result[0]['tags']
            assert 'tv' in result[0]['tags']

    def test_sorted_by_name(self):
        from compresso.libs.library import Library
        Libraries.create(
            id=1, name='Default', path='/default', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        Libraries.create(
            name='Zebra', path='/zebra', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        Libraries.create(
            name='Alpha', path='/alpha', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        with patch('compresso.config.Config') as mock_config_cls, \
             patch('compresso.libs.library.common.get_default_library_path', return_value='/default'):
            mock_config = MagicMock()
            mock_config.get_library_path.return_value = '/default'
            mock_config_cls.return_value = mock_config

            result = Library.get_all_libraries()

            # Default first, then sorted: Alpha, Zebra
            assert result[0]['id'] == 1
            assert result[1]['name'] == 'Alpha'
            assert result[2]['name'] == 'Zebra'


# ------------------------------------------------------------------
# TestLibrarySave
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestLibrarySave:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_lib_save_')
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

    def teardown_class(self):
        if self.db_connection:
            self.db_connection.close()
        shutil.rmtree(self.config_path, ignore_errors=True)

    def setup_method(self):
        Libraries.delete().execute()

    @patch('compresso.libs.library.Config')
    def test_save_persists_changes(self, mock_config_cls):
        from compresso.libs.library import Library
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config

        row = Libraries.create(
            id=1, name='Default', path='/default', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        lib = Library(row.id)
        lib.set_name('Updated')
        lib.save()

        # Reload from DB
        lib2 = Library(row.id)
        assert lib2.get_name() == 'Updated'

    @patch('compresso.libs.library.Config')
    def test_save_default_library_updates_config(self, mock_config_cls):
        from compresso.libs.library import Library
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config

        row = Libraries.create(
            id=1, name='Default', path='/default', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        lib = Library(row.id)
        lib.set_path('/new/path')
        lib.save()

        mock_config.set_config_item.assert_called_with('library_path', '/new/path')

    @patch('compresso.libs.library.Config')
    def test_save_non_default_library_does_not_update_config(self, mock_config_cls):
        from compresso.libs.library import Library
        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config

        Libraries.create(
            id=1, name='Default', path='/default', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        row = Libraries.create(
            name='Movies', path='/movies', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        lib = Library(row.id)
        lib.set_path('/new/movies')
        lib.save()

        mock_config.set_config_item.assert_not_called()


# ------------------------------------------------------------------
# TestLibraryTags
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestLibraryTags:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_lib_tags_')
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

    def teardown_class(self):
        if self.db_connection:
            self.db_connection.close()
        shutil.rmtree(self.config_path, ignore_errors=True)

    def setup_method(self):
        LibraryTags.delete().execute()
        Tags.delete().execute()
        Libraries.delete().execute()

    def test_get_tags_empty(self):
        from compresso.libs.library import Library
        row = Libraries.create(
            name='TestLib', path='/test', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        lib = Library(row.id)
        assert lib.get_tags() == []

    def test_set_and_get_tags(self):
        from compresso.libs.library import Library
        row = Libraries.create(
            name='TestLib', path='/test', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        lib = Library(row.id)
        lib.set_tags(['movies', 'tv', 'anime'])
        tags = lib.get_tags()
        assert sorted(tags) == ['anime', 'movies', 'tv']

    def test_set_tags_replaces_existing(self):
        from compresso.libs.library import Library
        row = Libraries.create(
            name='TestLib', path='/test', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        lib = Library(row.id)
        lib.set_tags(['old_tag'])
        lib.set_tags(['new_tag'])
        tags = lib.get_tags()
        assert tags == ['new_tag']


# ------------------------------------------------------------------
# TestWithinLibraryCountLimits
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestWithinLibraryCountLimits:

    @patch('compresso.libs.library.FrontendPushMessages')
    def test_always_returns_true(self, mock_fpm_cls):
        from compresso.libs.library import Library
        mock_fpm = MagicMock()
        mock_fpm_cls.return_value = mock_fpm

        assert Library.within_library_count_limits() is True
        mock_fpm.remove_item.assert_called_with('libraryEnabledLimits')


# ------------------------------------------------------------------
# TestLibraryExport
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestLibraryExport:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_lib_export_')
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

    def teardown_class(self):
        if self.db_connection:
            self.db_connection.close()
        shutil.rmtree(self.config_path, ignore_errors=True)

    def setup_method(self):
        EnabledPlugins.delete().execute()
        LibraryPluginFlow.delete().execute()
        Libraries.delete().execute()

    @patch('compresso.libs.plugins.PluginsHandler')
    def test_export_returns_expected_structure(self, mock_ph_cls):
        from compresso.libs.library import Library
        row = Libraries.create(
            name='ExportLib', path='/export', locked=False,
            enable_remote_only=False, enable_scanner=True, enable_inotify=False,
            priority_score=0,
        )

        mock_ph = MagicMock()
        mock_ph.get_plugin_types_with_flows.return_value = ['worker.process_item']
        mock_ph.get_enabled_plugin_flows_for_plugin_type.return_value = []
        mock_ph_cls.return_value = mock_ph

        with patch.object(Library, 'get_enabled_plugins', return_value=[]), \
             patch.object(Library, 'get_tags', return_value=[]):
            result = Library.export(row.id)

        assert 'plugins' in result
        assert 'library_config' in result
        assert result['library_config']['name'] == 'ExportLib'
        assert result['library_config']['enable_scanner'] is True


# ------------------------------------------------------------------
# TestLibraryDeleteExtended
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestLibraryDeleteExtended:

    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix='compresso_test_lib_delex_')
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

    def teardown_class(self):
        if self.db_connection:
            self.db_connection.close()
        shutil.rmtree(self.config_path, ignore_errors=True)

    def setup_method(self):
        Tasks.delete().execute()
        EnabledPlugins.delete().execute()
        LibraryPluginFlow.delete().execute()
        Libraries.delete().execute()

    def test_delete_removes_associated_tasks(self):
        from compresso.libs.library import Library

        Libraries.create(
            id=1, name='default', path='/default', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        row = Libraries.create(
            name='deletable', path='/del', locked=False,
            enable_remote_only=False, enable_scanner=False, enable_inotify=False,
            priority_score=0,
        )
        # Create a task for this library
        Tasks.create(
            abspath='/del/test.mkv', library_id=row.id,
            priority=0, status='pending', type='local',
        )

        lib = Library(row.id)
        with patch('compresso.libs.library.Library._Library__remove_associated_tasks') as mock_remove:
            lib.delete()
            mock_remove.assert_called_once()


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
