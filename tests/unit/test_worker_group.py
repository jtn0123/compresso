#!/usr/bin/env python3

"""
tests.unit.test_worker_group.py

Unit tests for compresso/libs/worker_group.py:
- generate_random_worker_group_name
- WorkerGroup.get_all_worker_groups
- WorkerGroup by ID / get_name

"""

import os
import tempfile

import pytest

from compresso.libs.unmodels import Tags
from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels.workergroups import WorkerGroups, WorkerGroupTags
from compresso.libs.unmodels.workerschedules import WorkerSchedules


class TestWorkerGroup:
    db_connection = None

    def setup_class(self):
        self.config_path = tempfile.mkdtemp(prefix="compresso_test_wg_")
        self.db_file = os.path.join(self.config_path, "test_wg.db")
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": self.db_file,
            "MIGRATIONS_DIR": os.path.join(self.config_path, "migrations"),
        }
        self.db_connection = Database.select_database(database_settings)
        self.db_connection.create_tables([WorkerGroups, WorkerGroupTags, Tags, WorkerSchedules])
        self.db_connection.execute_sql("SELECT 1")

    def teardown_class(self):
        pass

    def setup_method(self):
        WorkerSchedules.delete().execute()
        WorkerGroupTags.delete().execute()
        WorkerGroups.delete().execute()
        Tags.delete().execute()

    @pytest.mark.unittest
    def test_generate_random_worker_group_name(self):
        from compresso.libs.worker_group import generate_random_worker_group_name

        name = generate_random_worker_group_name()
        assert isinstance(name, str)
        assert len(name) > 0

    @pytest.mark.unittest
    def test_get_all_worker_groups(self):
        WorkerGroups.create(name="test-group-1", locked=False, number_of_workers=2)
        WorkerGroups.create(name="test-group-2", locked=False, number_of_workers=1)

        from compresso.libs.worker_group import WorkerGroup

        result = WorkerGroup.get_all_worker_groups()
        assert isinstance(result, list)
        assert len(result) == 2
        names = [g["name"] for g in result]
        assert "test-group-1" in names
        assert "test-group-2" in names

    @pytest.mark.unittest
    def test_get_worker_group_by_id(self):
        group = WorkerGroups.create(name="my-group", locked=False, number_of_workers=3)

        from compresso.libs.worker_group import WorkerGroup

        wg = WorkerGroup(group.id)
        assert wg.get_name() == "my-group"


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
