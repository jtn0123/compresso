#!/usr/bin/env python3

"""
tests.unit.test_models.py

Isolated unit tests for ORM models: Tasks, Libraries, WorkerGroups,
CompletedTasks, and FileMetadata.
"""

import datetime
import os

import peewee
import pytest

from compresso.libs.unmodels import Libraries, Tags
from compresso.libs.unmodels.completedtasks import CompletedTasks
from compresso.libs.unmodels.filemetadata import FileMetadata
from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels.tasks import Tasks
from compresso.libs.unmodels.workergroups import WorkerGroups, WorkerGroupTags
from compresso.libs.unmodels.workerschedules import WorkerSchedules

LibraryTags = Libraries.tags.get_through_model()


@pytest.fixture
def model_db(tmp_path):
    """Create a temporary SQLite DB file with all tables needed for model tests."""
    db_file = os.path.join(str(tmp_path), "models_test.db")
    database_settings = {
        "TYPE": "SQLITE",
        "FILE": db_file,
        "MIGRATIONS_DIR": os.path.join(str(tmp_path), "migrations"),
    }
    db_connection = Database.select_database(database_settings)
    db_connection.create_tables(
        [
            Tasks,
            Libraries,
            LibraryTags,
            Tags,
            WorkerGroups,
            WorkerGroupTags,
            WorkerSchedules,
            CompletedTasks,
            FileMetadata,
        ]
    )
    yield db_connection
    db_connection.close()


# ==================== Tasks ====================


@pytest.mark.unittest
class TestTasksModel:
    def test_create_task(self, model_db):
        task = Tasks.create(
            abspath="/media/movies/test.mkv",
            type="local",
            library_id=1,
            status="pending",
        )
        assert task.id is not None
        assert task.abspath == "/media/movies/test.mkv"
        assert task.type == "local"
        assert task.status == "pending"

    def test_unique_abspath(self, model_db):
        Tasks.create(abspath="/media/unique.mkv", type="local", library_id=1, status="pending")
        with pytest.raises(peewee.IntegrityError):
            Tasks.create(abspath="/media/unique.mkv", type="local", library_id=1, status="pending")

    def test_default_values(self, model_db):
        task = Tasks.create(abspath="/media/defaults.mkv", type="local", library_id=1, status="pending")
        assert task.retry_count == 0
        assert task.max_retries == 3
        assert task.source_size == 0
        assert task.log == ""
        assert task.success is None

    def test_status_field(self, model_db):
        task = Tasks.create(abspath="/media/status.mkv", type="local", library_id=1, status="pending")
        task.status = "in_progress"
        task.save()
        refreshed = Tasks.get_by_id(task.id)
        assert refreshed.status == "in_progress"

    def test_priority_ordering(self, model_db):
        Tasks.create(abspath="/media/low.mkv", type="local", library_id=1, status="pending", priority=10)
        Tasks.create(abspath="/media/high.mkv", type="local", library_id=1, status="pending", priority=100)
        Tasks.create(abspath="/media/mid.mkv", type="local", library_id=1, status="pending", priority=50)
        ordered = list(Tasks.select().order_by(Tasks.priority.desc()))
        assert ordered[0].abspath == "/media/high.mkv"
        assert ordered[2].abspath == "/media/low.mkv"

    def test_retry_fields(self, model_db):
        task = Tasks.create(abspath="/media/retry.mkv", type="local", library_id=1, status="pending")
        task.retry_count = 2
        task.save()
        refreshed = Tasks.get_by_id(task.id)
        assert refreshed.retry_count == 2
        assert refreshed.max_retries == 3

    def test_delete_task(self, model_db):
        task = Tasks.create(abspath="/media/delete_me.mkv", type="local", library_id=1, status="pending")
        task_id = task.id
        task.delete_instance()
        with pytest.raises(Tasks.DoesNotExist):
            Tasks.get_by_id(task_id)


# ==================== Libraries ====================


@pytest.mark.unittest
class TestLibrariesModel:
    def test_create_library(self, model_db):
        lib = Libraries.create(name="Movies", path="/media/movies")
        assert lib.id is not None
        assert lib.name == "Movies"
        assert lib.path == "/media/movies"

    def test_unique_name(self, model_db):
        Libraries.create(name="UniqueLib", path="/media/a")
        with pytest.raises(peewee.IntegrityError):
            Libraries.create(name="UniqueLib", path="/media/b")

    def test_default_values(self, model_db):
        lib = Libraries.create(name="Defaults", path="/media/defaults")
        assert lib.locked is False
        assert lib.enable_remote_only is False
        assert lib.enable_scanner is False
        assert lib.enable_inotify is False
        assert lib.priority_score == 0
        assert lib.size_guardrail_enabled is False
        assert lib.size_guardrail_min_pct == 20
        assert lib.size_guardrail_max_pct == 80

    def test_tag_relationship(self, model_db):
        lib = Libraries.create(name="TagTest", path="/media/tagged")
        tag = Tags.create(name="h265")
        lib.tags.add(tag)
        tag_names = [t.name for t in lib.tags]
        assert "h265" in tag_names

    def test_guardrail_fields(self, model_db):
        lib = Libraries.create(
            name="Guarded",
            path="/media/guarded",
            size_guardrail_enabled=True,
            size_guardrail_min_pct=10,
            size_guardrail_max_pct=90,
        )
        assert lib.size_guardrail_enabled is True
        assert lib.size_guardrail_min_pct == 10
        assert lib.size_guardrail_max_pct == 90

    def test_replacement_policy(self, model_db):
        lib = Libraries.create(name="PolicyTest", path="/media/policy", replacement_policy="approval_required")
        refreshed = Libraries.get_by_id(lib.id)
        assert refreshed.replacement_policy == "approval_required"

    def test_delete_library(self, model_db):
        lib = Libraries.create(name="DeleteMe", path="/media/deleteme")
        lib_id = lib.id
        lib.delete_instance()
        with pytest.raises(Libraries.DoesNotExist):
            Libraries.get_by_id(lib_id)


# ==================== WorkerGroups ====================


@pytest.mark.unittest
class TestWorkerGroupsModel:
    def test_create_worker_group(self, model_db):
        wg = WorkerGroups.create(name="GPU Workers", number_of_workers=4, worker_type="gpu")
        assert wg.id is not None
        assert wg.name == "GPU Workers"
        assert wg.number_of_workers == 4
        assert wg.worker_type == "gpu"

    def test_default_values(self, model_db):
        wg = WorkerGroups.create(name="Defaults")
        assert wg.locked is False
        assert wg.number_of_workers == 0
        assert wg.worker_type == "cpu"

    def test_tag_relationship(self, model_db):
        wg = WorkerGroups.create(name="Tagged Workers")
        tag = Tags.create(name="fast")
        wg.tags.add(tag)
        tag_names = [t.name for t in wg.tags]
        assert "fast" in tag_names

    def test_delete_worker_group(self, model_db):
        wg = WorkerGroups.create(name="DeleteWG")
        wg_id = wg.id
        wg.delete_instance()
        with pytest.raises(WorkerGroups.DoesNotExist):
            WorkerGroups.get_by_id(wg_id)


# ==================== CompletedTasks ====================


@pytest.mark.unittest
class TestCompletedTasksModel:
    def test_create_completed_task(self, model_db):
        ct = CompletedTasks.create(
            task_label="Encode test.mkv",
            abspath="/media/test.mkv",
            task_success=True,
            processed_by_worker="worker-1",
        )
        assert ct.id is not None
        assert ct.task_label == "Encode test.mkv"
        assert ct.task_success is True

    def test_failed_task(self, model_db):
        ct = CompletedTasks.create(
            task_label="Failed encode",
            abspath="/media/fail.mkv",
            task_success=False,
            processed_by_worker="worker-2",
        )
        assert ct.task_success is False

    def test_timestamps_default(self, model_db):
        before = datetime.datetime.now()
        ct = CompletedTasks.create(
            task_label="Timed",
            abspath="/media/timed.mkv",
            task_success=True,
            processed_by_worker="worker-1",
        )
        after = datetime.datetime.now()
        assert before <= ct.start_time <= after
        assert before <= ct.finish_time <= after

    def test_filter_by_success(self, model_db):
        CompletedTasks.create(task_label="ok", abspath="/a", task_success=True, processed_by_worker="w1")
        CompletedTasks.create(task_label="fail", abspath="/b", task_success=False, processed_by_worker="w1")
        CompletedTasks.create(task_label="ok2", abspath="/c", task_success=True, processed_by_worker="w1")
        successes = CompletedTasks.select().where(CompletedTasks.task_success == True)  # noqa: E712
        assert successes.count() == 2


# ==================== FileMetadata ====================


@pytest.mark.unittest
class TestFileMetadataModel:
    def test_create_file_metadata(self, model_db):
        fm = FileMetadata.create(fingerprint="abc123def456")
        assert fm.id is not None
        assert fm.fingerprint == "abc123def456"
        assert fm.fingerprint_algo == "sampled_sha256_v1"
        assert fm.metadata_json == "{}"

    def test_unique_fingerprint(self, model_db):
        FileMetadata.create(fingerprint="unique_fp_001")
        with pytest.raises(peewee.IntegrityError):
            FileMetadata.create(fingerprint="unique_fp_001")

    def test_metadata_json_storage(self, model_db):
        import json

        meta = {"codec": "h265", "resolution": "1920x1080", "bitrate": 5000}
        fm = FileMetadata.create(fingerprint="json_test", metadata_json=json.dumps(meta))
        refreshed = FileMetadata.get_by_id(fm.id)
        loaded = json.loads(refreshed.metadata_json)
        assert loaded["codec"] == "h265"
        assert loaded["resolution"] == "1920x1080"

    def test_last_task_id_nullable(self, model_db):
        fm = FileMetadata.create(fingerprint="no_task")
        assert fm.last_task_id is None
        fm.last_task_id = 42
        fm.save()
        refreshed = FileMetadata.get_by_id(fm.id)
        assert refreshed.last_task_id == 42

    def test_timestamps(self, model_db):
        before = datetime.datetime.now()
        fm = FileMetadata.create(fingerprint="ts_test")
        after = datetime.datetime.now()
        assert before <= fm.created_at <= after
        assert before <= fm.updated_at <= after
