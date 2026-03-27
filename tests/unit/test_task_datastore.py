#!/usr/bin/env python3

"""
tests.unit.test_task_datastore.py

Unit tests for the TaskDataStore class in compresso/libs/task.py.
TaskDataStore is a thread-safe in-memory store with immutable runner state
and mutable task state.
"""

import json
import threading

import pytest


@pytest.mark.unittest
class TestTaskDataStoreClearTask:
    def setup_method(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore._runner_state = {}
        TaskDataStore._task_state = {}
        TaskDataStore._ctx = threading.local()

    def test_clear_removes_runner_state(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.bind_runner_context(task_id=1, plugin_id="plug", runner="run")
        TaskDataStore.set_runner_value("key", "value")
        TaskDataStore.clear_task(1)
        assert 1 not in TaskDataStore._runner_state

    def test_clear_removes_task_state(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("key", "value", task_id=1)
        TaskDataStore.clear_task(1)
        assert 1 not in TaskDataStore._task_state

    def test_clear_nonexistent_task_is_noop(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.clear_task(999)  # Should not raise


@pytest.mark.unittest
class TestTaskDataStoreRunnerContext:
    def setup_method(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore._runner_state = {}
        TaskDataStore._task_state = {}
        TaskDataStore._ctx = threading.local()

    def test_bind_and_clear_context(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.bind_runner_context(task_id=1, plugin_id="plug", runner="run")
        assert TaskDataStore._ctx.task_id == 1
        assert TaskDataStore._ctx.plugin_id == "plug"
        assert TaskDataStore._ctx.runner == "run"
        TaskDataStore.clear_context()
        assert TaskDataStore._ctx.task_id is None
        assert TaskDataStore._ctx.plugin_id is None
        assert TaskDataStore._ctx.runner is None

    def test_set_runner_value_stores_immutably(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.bind_runner_context(task_id=1, plugin_id="plug", runner="run")
        result1 = TaskDataStore.set_runner_value("key", "value1")
        assert result1 is True
        result2 = TaskDataStore.set_runner_value("key", "value2")
        assert result2 is False
        # Original value preserved
        val = TaskDataStore.get_runner_value("key")
        assert val == "value1"

    def test_get_runner_value_returns_stored_value(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.bind_runner_context(task_id=1, plugin_id="plug", runner="run")
        TaskDataStore.set_runner_value("data", {"nested": True})
        val = TaskDataStore.get_runner_value("data")
        assert val == {"nested": True}

    def test_get_runner_value_returns_none_for_missing(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.bind_runner_context(task_id=1, plugin_id="plug", runner="run")
        val = TaskDataStore.get_runner_value("missing")
        assert val is None

    def test_get_runner_value_returns_default_for_missing(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.bind_runner_context(task_id=1, plugin_id="plug", runner="run")
        val = TaskDataStore.get_runner_value("missing", default="fallback")
        assert val == "fallback"

    def test_get_runner_value_with_plugin_override(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.bind_runner_context(task_id=1, plugin_id="plug_a", runner="run")
        TaskDataStore.set_runner_value("key", "from_a")
        TaskDataStore.bind_runner_context(task_id=1, plugin_id="plug_b", runner="run")
        TaskDataStore.set_runner_value("key", "from_b")
        # Override to read from plug_a
        val = TaskDataStore.get_runner_value("key", plugin_id="plug_a")
        assert val == "from_a"

    def test_set_runner_value_without_context_raises(self):
        from compresso.libs.task import TaskDataStore

        with pytest.raises(RuntimeError, match="Runner context not bound"):
            TaskDataStore.set_runner_value("key", "value")

    def test_get_runner_value_without_context_raises(self):
        from compresso.libs.task import TaskDataStore

        with pytest.raises(RuntimeError, match="Runner context not bound"):
            TaskDataStore.get_runner_value("key")


@pytest.mark.unittest
class TestTaskDataStoreTaskState:
    def setup_method(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore._runner_state = {}
        TaskDataStore._task_state = {}
        TaskDataStore._ctx = threading.local()

    def test_set_and_get_task_state(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("progress", 0.5, task_id=1)
        val = TaskDataStore.get_task_state("progress", task_id=1)
        assert val == 0.5

    def test_set_task_state_overwrites(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("progress", 0.5, task_id=1)
        TaskDataStore.set_task_state("progress", 0.9, task_id=1)
        val = TaskDataStore.get_task_state("progress", task_id=1)
        assert val == 0.9

    def test_get_task_state_missing_returns_default(self):
        from compresso.libs.task import TaskDataStore

        val = TaskDataStore.get_task_state("missing", default="nope", task_id=1)
        assert val == "nope"

    def test_get_task_state_without_task_id_raises(self):
        from compresso.libs.task import TaskDataStore

        with pytest.raises(RuntimeError, match="Task ID not provided or bound"):
            TaskDataStore.get_task_state("key")

    def test_delete_task_state(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("key", "val", task_id=1)
        TaskDataStore.delete_task_state("key", task_id=1)
        val = TaskDataStore.get_task_state("key", default="gone", task_id=1)
        assert val == "gone"

    def test_delete_nonexistent_key_is_noop(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("other", "val", task_id=1)
        TaskDataStore.delete_task_state("missing", task_id=1)  # Should not raise

    def test_delete_last_key_removes_task_entry(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("only", "val", task_id=1)
        TaskDataStore.delete_task_state("only", task_id=1)
        assert 1 not in TaskDataStore._task_state

    def test_set_task_state_uses_bound_context(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.bind_runner_context(task_id=42, plugin_id="p", runner="r")
        TaskDataStore.set_task_state("key", "val")
        val = TaskDataStore.get_task_state("key", task_id=42)
        assert val == "val"


@pytest.mark.unittest
class TestTaskDataStoreExportImport:
    def setup_method(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore._runner_state = {}
        TaskDataStore._task_state = {}
        TaskDataStore._ctx = threading.local()

    def test_export_task_state_returns_deep_copy(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("nested", {"a": 1}, task_id=1)
        exported = TaskDataStore.export_task_state(1)
        exported["nested"]["a"] = 999
        # Original unchanged
        val = TaskDataStore.get_task_state("nested", task_id=1)
        assert val["a"] == 1

    def test_export_task_state_empty_returns_empty_dict(self):
        from compresso.libs.task import TaskDataStore

        exported = TaskDataStore.export_task_state(999)
        assert exported == {}

    def test_export_task_state_json_returns_valid_json(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("key", "value", task_id=1)
        json_str = TaskDataStore.export_task_state_json(1)
        parsed = json.loads(json_str)
        assert parsed == {"key": "value"}

    def test_import_task_state_merges_dict(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.set_task_state("existing", "keep", task_id=1)
        TaskDataStore.import_task_state(1, {"new_key": "added"})
        assert TaskDataStore.get_task_state("existing", task_id=1) == "keep"
        assert TaskDataStore.get_task_state("new_key", task_id=1) == "added"

    def test_import_task_state_json_parses_and_merges(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore.import_task_state_json(1, '{"imported": true}')
        val = TaskDataStore.get_task_state("imported", task_id=1)
        assert val is True

    def test_import_task_state_json_non_dict_raises(self):
        from compresso.libs.task import TaskDataStore

        with pytest.raises(ValueError, match="must be an object/dict"):
            TaskDataStore.import_task_state_json(1, '"just a string"')


@pytest.mark.unittest
class TestTaskDataStoreThreadSafety:
    def setup_method(self):
        from compresso.libs.task import TaskDataStore

        TaskDataStore._runner_state = {}
        TaskDataStore._task_state = {}
        TaskDataStore._ctx = threading.local()

    def test_concurrent_set_and_get_no_corruption(self):
        from compresso.libs.task import TaskDataStore

        errors = []

        def worker(thread_id):
            try:
                for i in range(50):
                    key = f"thread_{thread_id}_key_{i}"
                    TaskDataStore.set_task_state(key, i, task_id=1)
                    val = TaskDataStore.get_task_state(key, task_id=1)
                    if val != i:
                        errors.append(f"Thread {thread_id}: expected {i}, got {val}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread safety errors: {errors}"
