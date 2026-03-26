#!/usr/bin/env python3

"""
    tests.unit.test_metadata.py

    Unit tests for CompressoFileMetadata in compresso/libs/metadata.py.
    Focuses on pure-logic methods: JSON helpers, normalization, cache pruning, and context.
"""

import json
import time
from collections import OrderedDict
from unittest.mock import patch

import pytest


@pytest.mark.unittest
class TestMetadataJsonHelpers:

    def test_load_json_dict_none_returns_empty(self):
        from compresso.libs.metadata import CompressoFileMetadata
        assert CompressoFileMetadata._load_json_dict(None) == {}

    def test_load_json_dict_empty_string_returns_empty(self):
        from compresso.libs.metadata import CompressoFileMetadata
        assert CompressoFileMetadata._load_json_dict('') == {}

    def test_load_json_dict_valid_json(self):
        from compresso.libs.metadata import CompressoFileMetadata
        result = CompressoFileMetadata._load_json_dict('{"key": "value"}')
        assert result == {'key': 'value'}

    def test_load_json_dict_invalid_json_returns_empty(self):
        from compresso.libs.metadata import CompressoFileMetadata
        result = CompressoFileMetadata._load_json_dict('not json at all')
        assert result == {}

    def test_load_json_dict_non_dict_returns_empty(self):
        from compresso.libs.metadata import CompressoFileMetadata
        result = CompressoFileMetadata._load_json_dict('[1, 2, 3]')
        assert result == {}

    def test_dump_json_dict_valid(self):
        from compresso.libs.metadata import CompressoFileMetadata
        result = CompressoFileMetadata._dump_json_dict({'a': 1})
        parsed = json.loads(result)
        assert parsed == {'a': 1}

    def test_dump_json_dict_non_dict_raises(self):
        from compresso.libs.metadata import CompressoFileMetadata
        with pytest.raises(ValueError, match="must be a dict"):
            CompressoFileMetadata._dump_json_dict([1, 2, 3])


@pytest.mark.unittest
class TestMetadataSizeLimit:

    def test_enforce_plugin_size_limit_within_limit(self):
        from compresso.libs.metadata import CompressoFileMetadata
        small_data = {'key': 'value'}
        CompressoFileMetadata._enforce_plugin_size_limit(small_data)  # Should not raise

    def test_enforce_plugin_size_limit_exceeds_raises(self):
        from compresso.libs.metadata import CompressoFileMetadata
        # Create data larger than MAX_PLUGIN_JSON_BYTES (32768)
        large_data = {'key': 'x' * 40000}
        with pytest.raises(ValueError, match="exceeds size limit"):
            CompressoFileMetadata._enforce_plugin_size_limit(large_data)


@pytest.mark.unittest
class TestMetadataNormalizeScoped:

    def test_normalize_non_dict_returns_defaults(self):
        from compresso.libs.metadata import CompressoFileMetadata
        result = CompressoFileMetadata._normalize_scoped_staged(None)
        assert result == {'source': {}, 'destination': {}, '__meta__': {}}

    def test_normalize_already_scoped(self):
        from compresso.libs.metadata import CompressoFileMetadata
        staged = {
            'source': {'plug': {'k': 'v'}},
            'destination': {'plug': {'k2': 'v2'}},
            '__meta__': {'info': 'test'},
        }
        result = CompressoFileMetadata._normalize_scoped_staged(staged)
        assert result['source'] == {'plug': {'k': 'v'}}
        assert result['destination'] == {'plug': {'k2': 'v2'}}
        assert result['__meta__'] == {'info': 'test'}

    def test_normalize_legacy_format_treated_as_source(self):
        from compresso.libs.metadata import CompressoFileMetadata
        legacy = {'plugin_a': {'data': 1}, 'plugin_b': {'data': 2}}
        result = CompressoFileMetadata._normalize_scoped_staged(legacy)
        assert result['source'] == legacy
        assert result['destination'] == {}
        assert result['__meta__'] == {}

    def test_normalize_handles_non_dict_sub_keys(self):
        from compresso.libs.metadata import CompressoFileMetadata
        staged = {'source': 'bad', 'destination': 42, '__meta__': [1]}
        result = CompressoFileMetadata._normalize_scoped_staged(staged)
        assert result['source'] == {}
        assert result['destination'] == {}
        assert result['__meta__'] == {}

    def test_normalize_with_none_sub_keys(self):
        from compresso.libs.metadata import CompressoFileMetadata
        staged = {'source': None, 'destination': None, '__meta__': None}
        result = CompressoFileMetadata._normalize_scoped_staged(staged)
        assert result['source'] == {}
        assert result['destination'] == {}
        assert result['__meta__'] == {}


@pytest.mark.unittest
class TestMetadataCachePruning:

    def setup_method(self):
        from compresso.libs.metadata import CompressoFileMetadata
        self._orig_path_cache = CompressoFileMetadata._path_cache
        self._orig_last_prune = CompressoFileMetadata._last_prune
        CompressoFileMetadata._path_cache = OrderedDict()
        CompressoFileMetadata._last_prune = 0

    def teardown_method(self):
        from compresso.libs.metadata import CompressoFileMetadata
        CompressoFileMetadata._path_cache = self._orig_path_cache
        CompressoFileMetadata._last_prune = self._orig_last_prune

    def test_prune_removes_expired_entries(self):
        from compresso.libs.metadata import CompressoFileMetadata
        now = time.time()
        # Add an entry with an expired timestamp (TTL is 300s)
        CompressoFileMetadata._path_cache['/old/path'] = {
            'data': {},
            'fingerprint': 'abc',
            'fingerprint_algo': 'xxhash',
            'last_accessed': now - 600,
        }
        CompressoFileMetadata._path_cache['/new/path'] = {
            'data': {},
            'fingerprint': 'def',
            'fingerprint_algo': 'xxhash',
            'last_accessed': now,
        }
        CompressoFileMetadata._prune_path_cache(now)
        assert '/old/path' not in CompressoFileMetadata._path_cache
        assert '/new/path' in CompressoFileMetadata._path_cache

    def test_prune_respects_max_size(self):
        from compresso.libs.metadata import CompressoFileMetadata
        now = time.time()
        max_size = CompressoFileMetadata.CACHE_MAX_ENTRIES
        overflow = 10
        # Add more entries than the max
        for i in range(max_size + overflow):
            CompressoFileMetadata._path_cache[f'/path/{i}'] = {
                'data': {},
                'fingerprint': str(i),
                'fingerprint_algo': 'xxhash',
                'last_accessed': now,
            }
        CompressoFileMetadata._prune_path_cache(now)
        assert len(CompressoFileMetadata._path_cache) == max_size
        # Oldest entries (0..overflow-1) should be evicted, newest should remain
        for i in range(overflow):
            assert f'/path/{i}' not in CompressoFileMetadata._path_cache
        assert f'/path/{max_size + overflow - 1}' in CompressoFileMetadata._path_cache

    def test_get_cached_updates_lru_order(self):
        from compresso.libs.metadata import CompressoFileMetadata
        now = time.time()
        CompressoFileMetadata._path_cache['/first'] = {
            'data': {'plug': {'k': 'v'}},
            'fingerprint': 'aaa',
            'fingerprint_algo': 'xxhash',
            'last_accessed': now,
        }
        CompressoFileMetadata._path_cache['/second'] = {
            'data': {'plug': {'k': 'v2'}},
            'fingerprint': 'bbb',
            'fingerprint_algo': 'xxhash',
            'last_accessed': now,
        }
        # Access /first which should move it to end
        CompressoFileMetadata._get_cached_path_entry('/first')
        keys = list(CompressoFileMetadata._path_cache.keys())
        assert keys[-1] == '/first'


@pytest.mark.unittest
class TestMetadataContextBinding:

    def setup_method(self):
        import threading

        from compresso.libs.metadata import CompressoFileMetadata
        CompressoFileMetadata._ctx = threading.local()

    def test_bind_and_get_context(self):
        import os

        from compresso.libs.metadata import CompressoFileMetadata
        with patch.object(CompressoFileMetadata, '_main_pid', os.getpid()):
            CompressoFileMetadata.bind_runner_context(plugin_id='test_plug', task_id=1, path='/test')
            pid, tid, path = CompressoFileMetadata._get_context()
            assert pid == 'test_plug'
            assert tid == 1
            assert path == '/test'

    def test_get_context_without_bind_raises(self):
        from compresso.libs.metadata import CompressoFileMetadata
        with pytest.raises(RuntimeError, match="context not bound"):
            CompressoFileMetadata._get_context()

    def test_clear_context(self):
        import os

        from compresso.libs.metadata import CompressoFileMetadata
        with patch.object(CompressoFileMetadata, '_main_pid', os.getpid()):
            CompressoFileMetadata.bind_runner_context(plugin_id='test_plug', task_id=1)
            CompressoFileMetadata.clear_context()
            with pytest.raises(RuntimeError, match="context not bound"):
                CompressoFileMetadata._get_context()

    def test_bind_runner_context_wrong_process_raises(self):
        from compresso.libs.metadata import CompressoFileMetadata
        with (
            patch.object(CompressoFileMetadata, '_main_pid', -1),
            pytest.raises(RuntimeError, match="only available in the main process"),
        ):
            CompressoFileMetadata.bind_runner_context(plugin_id='test_plug')
