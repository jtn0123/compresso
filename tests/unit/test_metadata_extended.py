#!/usr/bin/env python3

"""
    tests.unit.test_metadata_extended.py

    Extended unit tests for CompressoFileMetadata in compresso/libs/metadata.py.
    Covers DB-backed operations: get, set, commit_task, find_by_path, find_all,
    delete_for_plugin, _ensure_task_cache_entry, _load_task_metadata,
    _load_file_metadata_for_task, _upsert_path, and path-based get.
"""

import json
import os
import threading
import time
from collections import OrderedDict
from unittest.mock import patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.libs.unmodels.filemetadata import FileMetadata
from compresso.libs.unmodels.filemetadatapaths import FileMetadataPaths
from compresso.libs.unmodels.taskmetadata import TaskMetadata
from compresso.libs.unmodels.tasks import Tasks


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture(autouse=True)
def metadata_db(in_memory_db):
    """Extend the shared in_memory_db fixture with metadata-specific tables."""
    in_memory_db.create_tables([FileMetadata, FileMetadataPaths, TaskMetadata])
    # SqliteQueueDatabase processes writes asynchronously. Issue a blocking read
    # via the queue to ensure the CREATE TABLE statements have been flushed.
    for _attempt in range(10):
        tables = [r[0] for r in in_memory_db.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if 'task_metadata' in tables:
            break
        time.sleep(0.2)
    yield in_memory_db
    # Clean up data between tests
    for model in [FileMetadataPaths, TaskMetadata, FileMetadata, Tasks]:
        try:  # noqa: SIM105 — best-effort cleanup; table may not exist
            model.delete().execute()
        except Exception:  # noqa: S110
            pass


@pytest.fixture(autouse=True)
def reset_metadata_state():
    """Reset class-level caches and context between tests."""
    from compresso.libs.metadata import CompressoFileMetadata
    orig_cache = CompressoFileMetadata._path_cache
    orig_task_cache = CompressoFileMetadata._task_cache
    orig_prune = CompressoFileMetadata._last_prune
    orig_pid = CompressoFileMetadata._main_pid
    CompressoFileMetadata._path_cache = OrderedDict()
    CompressoFileMetadata._task_cache = {}
    CompressoFileMetadata._last_prune = 0
    CompressoFileMetadata._main_pid = os.getpid()
    CompressoFileMetadata._ctx = threading.local()
    yield
    CompressoFileMetadata._path_cache = orig_cache
    CompressoFileMetadata._task_cache = orig_task_cache
    CompressoFileMetadata._last_prune = orig_prune
    CompressoFileMetadata._main_pid = orig_pid
    CompressoFileMetadata._ctx = threading.local()


@pytest.mark.unittest
class TestEnsureTaskCacheEntry:

    def test_creates_new_entry(self):
        from compresso.libs.metadata import CompressoFileMetadata
        entry = CompressoFileMetadata._ensure_task_cache_entry(42)
        assert entry['staged'] == {}
        assert entry['staged_loaded'] is False
        assert entry['file'] == {}
        assert entry['file_loaded'] is False
        assert entry['source_path'] is None

    def test_returns_existing_entry(self):
        from compresso.libs.metadata import CompressoFileMetadata
        entry1 = CompressoFileMetadata._ensure_task_cache_entry(42)
        entry1['staged'] = {'test': True}
        entry2 = CompressoFileMetadata._ensure_task_cache_entry(42)
        assert entry2['staged'] == {'test': True}


@pytest.mark.unittest
class TestLoadTaskMetadata:

    def test_load_from_db(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/test/file.mkv', status='pending', priority=0)
        TaskMetadata.create(task=task.id, json_blob='{"plug": {"key": "val"}}')
        result = CompressoFileMetadata._load_task_metadata(task.id)
        assert result == {"plug": {"key": "val"}}

    def test_load_missing_task_returns_empty(self):
        from compresso.libs.metadata import CompressoFileMetadata
        result = CompressoFileMetadata._load_task_metadata(99999)
        assert result == {}

    def test_cached_after_first_load(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/test/file.mkv', status='pending', priority=0)
        TaskMetadata.create(task=task.id, json_blob='{"plug": {"k": "v"}}')
        CompressoFileMetadata._load_task_metadata(task.id)
        # Modify DB directly - cache should still return old value
        tm = TaskMetadata.get(TaskMetadata.task == task.id)
        tm.json_blob = '{"changed": true}'
        tm.save()
        result = CompressoFileMetadata._load_task_metadata(task.id)
        assert result == {"plug": {"k": "v"}}


@pytest.mark.unittest
class TestLoadTaskSourcePath:

    def test_loads_source_path_from_task(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/media/video.mp4', status='pending', priority=0)
        result = CompressoFileMetadata._load_task_source_path(task.id)
        assert result == '/media/video.mp4'

    def test_missing_task_returns_none(self):
        from compresso.libs.metadata import CompressoFileMetadata
        result = CompressoFileMetadata._load_task_source_path(99999)
        assert result is None


@pytest.mark.unittest
class TestLoadFileMetadataForTask:

    def test_no_source_path(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/nonexistent/file.mkv', status='pending', priority=0)
        result = CompressoFileMetadata._load_file_metadata_for_task(task.id)
        assert result == {}

    @patch('compresso.libs.metadata.os.path.exists', return_value=True)
    @patch('compresso.libs.metadata.common.get_file_fingerprint', return_value=('fp123', 'sha256'))
    def test_with_existing_file_metadata(self, mock_fp, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/media/video.mp4', status='pending', priority=0)
        FileMetadata.create(
            fingerprint='fp123',
            fingerprint_algo='sha256',
            metadata_json='{"plug_a": {"codec": "hevc"}}',
        )
        result = CompressoFileMetadata._load_file_metadata_for_task(task.id)
        assert result == {"plug_a": {"codec": "hevc"}}

    @patch('compresso.libs.metadata.os.path.exists', return_value=True)
    @patch('compresso.libs.metadata.common.get_file_fingerprint', return_value=('fp_new', 'sha256'))
    def test_no_file_metadata_row(self, mock_fp, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/media/video.mp4', status='pending', priority=0)
        result = CompressoFileMetadata._load_file_metadata_for_task(task.id)
        assert result == {}


@pytest.mark.unittest
class TestMetadataGetWithTaskId:

    @patch('compresso.libs.metadata.os.path.exists', return_value=True)
    @patch('compresso.libs.metadata.common.get_file_fingerprint', return_value=('fp1', 'sha256'))
    def test_get_returns_destination_scope(self, mock_fp, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/media/video.mp4', status='pending', priority=0)
        # file-level metadata for a different plugin so it doesn't get overwritten
        FileMetadata.create(
            fingerprint='fp1',
            fingerprint_algo='sha256',
            metadata_json='{"other_plugin": {"from_file": true}}',
        )
        staged = {
            'source': {},
            'destination': {'test_plugin': {'from_dest': True}},
            '__meta__': {},
        }
        TaskMetadata.create(task=task.id, json_blob=json.dumps(staged))
        CompressoFileMetadata.bind_runner_context(plugin_id='test_plugin', task_id=task.id)
        result = CompressoFileMetadata.get()
        assert result == {'from_dest': True}

    def test_get_with_plugin_id_override(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/nonexistent.mkv', status='pending', priority=0)
        staged = {
            'source': {'other_plug': {'data': 42}},
            'destination': {},
            '__meta__': {},
        }
        TaskMetadata.create(task=task.id, json_blob=json.dumps(staged))
        CompressoFileMetadata.bind_runner_context(plugin_id='test_plugin', task_id=task.id)
        result = CompressoFileMetadata.get(plugin_id_override='other_plug')
        assert result == {'data': 42}

    def test_get_from_file_metadata_when_no_staged(self):
        """When staged data has no entry for the plugin, file-level metadata is returned."""
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/nonexistent.mkv', status='pending', priority=0)
        staged = {'source': {}, 'destination': {}, '__meta__': {}}
        TaskMetadata.create(task=task.id, json_blob=json.dumps(staged))
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', task_id=task.id)
        result = CompressoFileMetadata.get()
        assert result == {}


@pytest.mark.unittest
class TestMetadataGetWithPath:

    def test_get_raises_without_task_or_path(self):
        from compresso.libs.metadata import CompressoFileMetadata
        CompressoFileMetadata.bind_runner_context(plugin_id='plug')
        with pytest.raises(RuntimeError, match="requires a task_id or path"):
            CompressoFileMetadata.get()

    @patch('compresso.libs.metadata.os.path.exists', return_value=False)
    def test_get_nonexistent_path_returns_empty(self, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', path='/no/such/file')
        result = CompressoFileMetadata.get()
        assert result == {}

    @patch('compresso.libs.metadata.os.path.exists', return_value=True)
    @patch('compresso.libs.metadata.common.get_file_fingerprint', return_value=('fp_path', 'sha256'))
    def test_get_by_path_caches(self, mock_fp, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        FileMetadata.create(
            fingerprint='fp_path',
            fingerprint_algo='sha256',
            metadata_json='{"plug": {"cached": true}}',
        )
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', path='/media/file.mp4')
        result1 = CompressoFileMetadata.get()
        assert result1 == {'cached': True}
        # Second call uses cache
        result2 = CompressoFileMetadata.get()
        assert result2 == {'cached': True}
        # get_file_fingerprint should only be called once
        mock_fp.assert_called_once()


@pytest.mark.unittest
class TestMetadataSet:

    def test_set_without_task_raises(self):
        from compresso.libs.metadata import CompressoFileMetadata
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', path='/test')
        with pytest.raises(RuntimeError, match="requires a task_id context"):
            CompressoFileMetadata.set({'key': 'value'})

    def test_set_non_dict_raises(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/test.mkv', status='pending', priority=0)
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', task_id=task.id)
        with pytest.raises(ValueError, match="requires a dict"):
            CompressoFileMetadata.set("not a dict")

    def test_set_stores_in_destination_scope(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/test.mkv', status='pending', priority=0)
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', task_id=task.id)
        CompressoFileMetadata.set({'codec': 'hevc'})
        # Verify the in-memory cache was updated
        entry = CompressoFileMetadata._task_cache[task.id]
        assert entry['staged']['destination']['plug'] == {'codec': 'hevc'}

    @patch('compresso.libs.metadata.os.path.exists', return_value=True)
    @patch('compresso.libs.metadata.common.get_file_fingerprint', return_value=('src_fp', 'sha256'))
    def test_set_source_scope_records_fingerprint(self, mock_fp, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/media/source.mkv', status='pending', priority=0)
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', task_id=task.id)
        CompressoFileMetadata.set({'info': 'test'}, use_source_scope=True)
        entry = CompressoFileMetadata._task_cache[task.id]
        assert entry['staged']['source']['plug'] == {'info': 'test'}
        assert entry['staged']['__meta__']['source_fingerprint'] == 'src_fp'

    def test_set_removes_none_values(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/test.mkv', status='pending', priority=0)
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', task_id=task.id)
        CompressoFileMetadata.set({'a': 1, 'b': 2})
        CompressoFileMetadata.set({'b': None})
        entry = CompressoFileMetadata._task_cache[task.id]
        assert 'b' not in entry['staged']['destination']['plug']
        assert entry['staged']['destination']['plug']['a'] == 1

    def test_set_size_limit_exceeded(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/test.mkv', status='pending', priority=0)
        CompressoFileMetadata.bind_runner_context(plugin_id='plug', task_id=task.id)
        with pytest.raises(ValueError, match="exceeds size limit"):
            CompressoFileMetadata.set({'big': 'x' * 40000})


@pytest.mark.unittest
class TestCommitTask:

    def test_commit_empty_staged_deletes_taskmetadata(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/test.mkv', status='pending', priority=0)
        TaskMetadata.create(task=task.id, json_blob='{}')
        result = CompressoFileMetadata.commit_task(task.id, True, '/test.mkv')
        assert result == 0
        assert TaskMetadata.select().where(TaskMetadata.task == task.id).count() == 0

    @patch('compresso.libs.metadata.os.path.exists', return_value=True)
    @patch('compresso.libs.metadata.common.get_file_fingerprint', return_value=('dest_fp', 'sha256'))
    def test_commit_with_destination(self, mock_fp, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/source.mkv', status='pending', priority=0)
        staged = {
            'source': {},
            'destination': {'plug': {'codec': 'hevc'}},
            '__meta__': {},
        }
        TaskMetadata.create(task=task.id, json_blob=json.dumps(staged))
        result = CompressoFileMetadata.commit_task(
            task.id, True, '/source.mkv',
            destination_paths=['/dest.mkv'],
        )
        assert result >= 1
        fm = FileMetadata.get(FileMetadata.fingerprint == 'dest_fp')
        assert json.loads(fm.metadata_json)['plug'] == {'codec': 'hevc'}

    @patch('compresso.libs.metadata.os.path.exists', return_value=True)
    @patch('compresso.libs.metadata.common.get_file_fingerprint', return_value=('src_fp', 'sha256'))
    def test_commit_with_source_scope(self, mock_fp, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/source.mkv', status='pending', priority=0)
        staged = {
            'source': {'plug': {'info': 'src_data'}},
            'destination': {},
            '__meta__': {
                'source_path_at_set': '/source.mkv',
                'source_fingerprint': 'src_fp',
                'source_fingerprint_algo': 'sha256',
            },
        }
        TaskMetadata.create(task=task.id, json_blob=json.dumps(staged))
        result = CompressoFileMetadata.commit_task(task.id, True, '/source.mkv')
        assert result >= 1
        fm = FileMetadata.get(FileMetadata.fingerprint == 'src_fp')
        assert json.loads(fm.metadata_json)['plug'] == {'info': 'src_data'}

    def test_commit_cleans_task_cache(self):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/test.mkv', status='pending', priority=0)
        TaskMetadata.create(task=task.id, json_blob='{}')
        CompressoFileMetadata._ensure_task_cache_entry(task.id)
        CompressoFileMetadata.commit_task(task.id, True, '/test.mkv')
        assert task.id not in CompressoFileMetadata._task_cache

    @patch('compresso.libs.metadata.os.path.exists', return_value=False)
    def test_commit_source_missing_drops_source_metadata(self, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        task = Tasks.create(abspath='/missing.mkv', status='pending', priority=0)
        staged = {
            'source': {'plug': {'data': 'dropped'}},
            'destination': {},
            '__meta__': {},
        }
        TaskMetadata.create(task=task.id, json_blob=json.dumps(staged))
        result = CompressoFileMetadata.commit_task(task.id, True, '/missing.mkv')
        assert result == 0  # No fingerprint groups because source file is missing

    @patch('compresso.libs.metadata.os.path.exists', return_value=True)
    @patch('compresso.libs.metadata.common.get_file_fingerprint', return_value=('upd_fp', 'sha256'))
    def test_commit_updates_existing_file_metadata(self, mock_fp, mock_exists):
        from compresso.libs.metadata import CompressoFileMetadata
        # Pre-create a FileMetadata row
        FileMetadata.create(
            fingerprint='upd_fp',
            fingerprint_algo='sha256',
            metadata_json='{"existing_plug": {"old": true}}',
        )
        task = Tasks.create(abspath='/source.mkv', status='pending', priority=0)
        staged = {
            'source': {},
            'destination': {'new_plug': {'new': True}},
            '__meta__': {},
        }
        TaskMetadata.create(task=task.id, json_blob=json.dumps(staged))
        CompressoFileMetadata.commit_task(task.id, True, '/source.mkv', destination_paths=['/dest.mkv'])
        fm = FileMetadata.get(FileMetadata.fingerprint == 'upd_fp')
        data = json.loads(fm.metadata_json)
        assert data['existing_plug'] == {'old': True}
        assert data['new_plug'] == {'new': True}


@pytest.mark.unittest
class TestFindByPath:

    def test_find_by_path_empty_returns_empty(self):
        from compresso.libs.metadata import CompressoFileMetadata
        assert CompressoFileMetadata.find_by_path('') == []
        assert CompressoFileMetadata.find_by_path(None) == []
        assert CompressoFileMetadata.find_by_path('   ') == []

    def test_find_by_path_with_results(self):
        from compresso.libs.metadata import CompressoFileMetadata
        fm = FileMetadata.create(
            fingerprint='fp1',
            fingerprint_algo='sha256',
            metadata_json='{"plug": {"key": "val"}}',
        )
        FileMetadataPaths.create(file_metadata=fm.id, path='/media/test/video.mp4', path_type='source')
        results = CompressoFileMetadata.find_by_path('video.mp4')
        assert len(results) == 1
        assert results[0]['fingerprint'] == 'fp1'
        assert len(results[0]['paths']) == 1

    def test_find_by_path_no_match(self):
        from compresso.libs.metadata import CompressoFileMetadata
        fm = FileMetadata.create(
            fingerprint='fp1',
            fingerprint_algo='sha256',
            metadata_json='{}',
        )
        FileMetadataPaths.create(file_metadata=fm.id, path='/media/video.mp4', path_type='source')
        results = CompressoFileMetadata.find_by_path('nonexistent')
        assert results == []


@pytest.mark.unittest
class TestFindAll:

    def test_find_all_empty(self):
        from compresso.libs.metadata import CompressoFileMetadata
        results = CompressoFileMetadata.find_all()
        assert results == []

    def test_find_all_with_data(self):
        from compresso.libs.metadata import CompressoFileMetadata
        fm1 = FileMetadata.create(fingerprint='fp1', fingerprint_algo='sha256', metadata_json='{"a": {}}')
        fm2 = FileMetadata.create(fingerprint='fp2', fingerprint_algo='sha256', metadata_json='{"b": {}}')
        FileMetadataPaths.create(file_metadata=fm1.id, path='/path/a', path_type='source')
        FileMetadataPaths.create(file_metadata=fm2.id, path='/path/b', path_type='destination')
        results = CompressoFileMetadata.find_all()
        assert len(results) == 2


@pytest.mark.unittest
class TestDeleteForPlugin:

    def test_delete_no_fingerprint(self):
        from compresso.libs.metadata import CompressoFileMetadata
        assert CompressoFileMetadata.delete_for_plugin('') is False
        assert CompressoFileMetadata.delete_for_plugin(None) is False

    def test_delete_nonexistent_fingerprint(self):
        from compresso.libs.metadata import CompressoFileMetadata
        assert CompressoFileMetadata.delete_for_plugin('nonexistent') is False

    def test_delete_entire_record(self):
        from compresso.libs.metadata import CompressoFileMetadata
        FileMetadata.create(fingerprint='fp1', fingerprint_algo='sha256', metadata_json='{}')
        assert CompressoFileMetadata.delete_for_plugin('fp1') is True
        assert FileMetadata.select().where(FileMetadata.fingerprint == 'fp1').count() == 0

    def test_delete_specific_plugin(self):
        from compresso.libs.metadata import CompressoFileMetadata
        FileMetadata.create(
            fingerprint='fp1', fingerprint_algo='sha256',
            metadata_json='{"plug_a": {"x": 1}, "plug_b": {"y": 2}}',
        )
        assert CompressoFileMetadata.delete_for_plugin('fp1', plugin_id='plug_a') is True
        row = FileMetadata.get(FileMetadata.fingerprint == 'fp1')
        data = json.loads(row.metadata_json)
        assert 'plug_a' not in data
        assert data['plug_b'] == {'y': 2}


@pytest.mark.unittest
class TestUpsertPath:

    def test_upsert_creates_new_path(self):
        from compresso.libs.metadata import CompressoFileMetadata
        fm = FileMetadata.create(fingerprint='fp1', fingerprint_algo='sha256', metadata_json='{}')
        CompressoFileMetadata._upsert_path(fm.id, '/media/test.mp4', 'source')
        rows = FileMetadataPaths.select().where(FileMetadataPaths.file_metadata == fm.id)
        assert rows.count() == 1
        assert rows[0].path == '/media/test.mp4'

    def test_upsert_updates_existing_path(self):
        from compresso.libs.metadata import CompressoFileMetadata
        fm = FileMetadata.create(fingerprint='fp1', fingerprint_algo='sha256', metadata_json='{}')
        CompressoFileMetadata._upsert_path(fm.id, '/media/test.mp4', 'source')
        CompressoFileMetadata._upsert_path(fm.id, '/media/test.mp4', 'destination')
        rows = FileMetadataPaths.select().where(
            (FileMetadataPaths.file_metadata == fm.id) & (FileMetadataPaths.path == '/media/test.mp4')
        )
        assert rows.count() == 1
        assert rows[0].path_type == 'destination'

    def test_upsert_empty_path_skips(self):
        from compresso.libs.metadata import CompressoFileMetadata
        fm = FileMetadata.create(fingerprint='fp1', fingerprint_algo='sha256', metadata_json='{}')
        CompressoFileMetadata._upsert_path(fm.id, '', 'source')
        CompressoFileMetadata._upsert_path(fm.id, None, 'source')
        assert FileMetadataPaths.select().count() == 0


@pytest.mark.unittest
class TestSetCachedPathEntry:

    def test_set_and_get_cached(self):
        from compresso.libs.metadata import CompressoFileMetadata
        entry = {'fingerprint': 'fp1', 'fingerprint_algo': 'sha', 'metadata': {'plug': {'k': 'v'}}}
        CompressoFileMetadata._set_cached_path_entry('/test/path', entry)
        result = CompressoFileMetadata._get_cached_path_entry('/test/path')
        assert result is not None
        assert result['fingerprint'] == 'fp1'

    def test_get_nonexistent_returns_none(self):
        from compresso.libs.metadata import CompressoFileMetadata
        result = CompressoFileMetadata._get_cached_path_entry('/nonexistent')
        assert result is None


@pytest.mark.unittest
class TestEnsureMainProcess:

    def test_wrong_pid_raises(self):
        from compresso.libs.metadata import CompressoFileMetadata
        with (
            patch.object(CompressoFileMetadata, '_main_pid', -1),
            pytest.raises(RuntimeError, match="only available in the main process"),
        ):
            CompressoFileMetadata._ensure_main_process()

    def test_correct_pid_passes(self):
        from compresso.libs.metadata import CompressoFileMetadata
        CompressoFileMetadata._ensure_main_process()  # Should not raise
