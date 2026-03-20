#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_db_migrate_extended.py

    Extended unit tests for compresso.libs.db_migrate.Migrations.
    Covers column auto-sync, index management, error paths,
    and missing required columns detection.
"""

import os

import pytest
from unittest.mock import patch, MagicMock

from peewee import CharField, IntegerField

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_migrations(tmp_path):
    db_file = str(tmp_path / "test.db")
    migrations_dir = str(tmp_path / "migrations")
    os.makedirs(migrations_dir, exist_ok=True)
    config = {
        'TYPE': 'SQLITE',
        'FILE': db_file,
        'MIGRATIONS_DIR': migrations_dir,
        'MIGRATIONS_HISTORY_VERSION': 'v1',
    }
    with patch('compresso.libs.db_migrate.CompressoLogging'):
        from compresso.libs.db_migrate import Migrations
        m = Migrations(config)
    return m


@pytest.mark.unittest
class TestUpdateSchemaColumnSync:

    @patch('compresso.libs.db_migrate.inspect')
    def test_adds_missing_nullable_column(self, mock_inspect, tmp_path):
        """Auto-sync should add a nullable column with a default."""
        from compresso.libs.unmodels.lib import BaseModel

        m = _make_migrations(tmp_path)

        # Create a model with only 'name', then add 'extra' later
        class TestAutoSync(BaseModel):
            name = CharField(default='')
            class Meta:
                database = m.database
                table_name = 'test_auto_sync'
                indexes = ()

        # Create the table without 'extra'
        m.database.create_tables([TestAutoSync])

        # Now define the model with a new nullable column
        class TestAutoSync2(BaseModel):
            name = CharField(default='')
            extra = CharField(null=True, default=None)
            class Meta:
                database = m.database
                table_name = 'test_auto_sync'
                indexes = ()

        mock_inspect.getmembers.return_value = [('TestAutoSync2', TestAutoSync2)]
        mock_inspect.isclass = lambda x: isinstance(x, type)
        m.router = MagicMock()

        m.update_schema()

        # Verify the column was added
        columns = [c.name for c in m.database.get_columns('test_auto_sync')]
        assert 'extra' in columns

    @patch('compresso.libs.db_migrate.inspect')
    def test_raises_for_non_null_without_default(self, mock_inspect, tmp_path):
        """Missing non-null columns without default should raise RuntimeError."""
        from compresso.libs.unmodels.lib import BaseModel

        m = _make_migrations(tmp_path)

        class TestNonNull(BaseModel):
            name = CharField(default='')
            class Meta:
                database = m.database
                table_name = 'test_non_null'
                indexes = ()

        m.database.create_tables([TestNonNull])

        # Define model with a non-null field without default
        class TestNonNull2(BaseModel):
            name = CharField(default='')
            required_field = CharField(null=False)
            class Meta:
                database = m.database
                table_name = 'test_non_null'
                indexes = ()

        mock_inspect.getmembers.return_value = [('TestNonNull2', TestNonNull2)]
        mock_inspect.isclass = lambda x: isinstance(x, type)
        m.router = MagicMock()

        with pytest.raises(RuntimeError, match="non-additive migrations"):
            m.update_schema()


@pytest.mark.unittest
class TestUpdateSchemaIndexes:

    @patch('compresso.libs.db_migrate.inspect')
    def test_adds_missing_index(self, mock_inspect, tmp_path):
        """Auto-sync should add missing non-unique indexes."""
        from compresso.libs.unmodels.lib import BaseModel

        m = _make_migrations(tmp_path)

        class TestIndexModel(BaseModel):
            name = CharField(default='', index=True)
            class Meta:
                database = m.database
                table_name = 'test_index_model'
                indexes = ()

        m.database.create_tables([TestIndexModel])

        mock_inspect.getmembers.return_value = [('TestIndexModel', TestIndexModel)]
        mock_inspect.isclass = lambda x: isinstance(x, type)
        m.router = MagicMock()

        m.update_schema()

        indexes = m.database.get_indexes('test_index_model')
        index_cols = [tuple(getattr(idx, 'columns', [])) for idx in indexes]
        assert ('name',) in index_cols

    @patch('compresso.libs.db_migrate.inspect')
    def test_skips_existing_index(self, mock_inspect, tmp_path):
        """Should not duplicate an existing index."""
        from compresso.libs.unmodels.lib import BaseModel

        m = _make_migrations(tmp_path)

        class TestDupIndex(BaseModel):
            name = CharField(default='', index=True)
            class Meta:
                database = m.database
                table_name = 'test_dup_index'
                indexes = ()

        m.database.create_tables([TestDupIndex])

        mock_inspect.getmembers.return_value = [('TestDupIndex', TestDupIndex)]
        mock_inspect.isclass = lambda x: isinstance(x, type)
        m.router = MagicMock()

        # Run twice - second run should not fail
        m.update_schema()
        m.update_schema()

        indexes = m.database.get_indexes('test_dup_index')
        name_indexes = [idx for idx in indexes if tuple(getattr(idx, 'columns', [])) == ('name',)]
        assert len(name_indexes) == 1


@pytest.mark.unittest
class TestUpdateSchemaTableCreation:

    @patch('compresso.libs.db_migrate.inspect')
    def test_create_tables_exception_propagates(self, mock_inspect, tmp_path):
        """If table creation fails, the exception should propagate."""
        m = _make_migrations(tmp_path)

        mock_inspect.getmembers.return_value = [('BadModel', MagicMock)]
        mock_inspect.isclass = lambda x: isinstance(x, type)
        m.migrator = MagicMock()
        m.migrator.create_model.side_effect = Exception("table creation failed")

        with pytest.raises(Exception, match="table creation failed"):
            m.update_schema()


@pytest.mark.unittest
class TestMigrationsInitExtended:

    def test_sqlite_creates_router_and_migrator(self, tmp_path):
        m = _make_migrations(tmp_path)
        assert m.database is not None
        assert m.router is not None
        assert m.migrator is not None

    @patch('compresso.libs.db_migrate.inspect')
    def test_update_schema_with_no_models(self, mock_inspect, tmp_path):
        """Should complete without error when no models exist."""
        m = _make_migrations(tmp_path)
        mock_inspect.getmembers.return_value = []
        mock_inspect.isclass = lambda x: isinstance(x, type)
        m.router = MagicMock()
        m.update_schema()
        m.router.run.assert_called_once()


@pytest.mark.unittest
class TestColumnWithDefault:

    @patch('compresso.libs.db_migrate.inspect')
    def test_adds_column_with_default_value(self, mock_inspect, tmp_path):
        from compresso.libs.unmodels.lib import BaseModel

        m = _make_migrations(tmp_path)

        class BaseTable(BaseModel):
            name = CharField(default='')
            class Meta:
                database = m.database
                table_name = 'test_default_col'
                indexes = ()

        m.database.create_tables([BaseTable])

        class ExtendedTable(BaseModel):
            name = CharField(default='')
            count = IntegerField(default=0, null=True)
            class Meta:
                database = m.database
                table_name = 'test_default_col'
                indexes = ()

        mock_inspect.getmembers.return_value = [('ExtendedTable', ExtendedTable)]
        mock_inspect.isclass = lambda x: isinstance(x, type)
        m.router = MagicMock()

        m.update_schema()

        columns = [c.name for c in m.database.get_columns('test_default_col')]
        assert 'count' in columns


@pytest.mark.unittest
class TestAddColumnCompatibility:

    def test_prefers_add_fields_when_available(self, tmp_path):
        m = _make_migrations(tmp_path)
        m.migrator = MagicMock()
        m.migrator.add_fields = MagicMock()
        m.migrator.add_columns = MagicMock()

        field = CharField(null=True, default=None)
        m._Migrations__add_column_to_model(MagicMock(), 'extra', field)

        m.migrator.add_fields.assert_called_once()
        m.migrator.add_columns.assert_not_called()

    def test_falls_back_to_add_columns(self, tmp_path):
        m = _make_migrations(tmp_path)
        m.migrator = MagicMock()
        m.migrator.add_fields = None
        m.migrator.add_columns = MagicMock()

        field = CharField(null=True, default=None)
        m._Migrations__add_column_to_model(MagicMock(), 'extra', field)

        m.migrator.add_columns.assert_called_once()

    def test_raises_when_no_supported_api_exists(self, tmp_path):
        m = _make_migrations(tmp_path)
        m.migrator = MagicMock()
        m.migrator.add_fields = None
        m.migrator.add_columns = None

        field = CharField(null=True, default=None)
        with pytest.raises(AttributeError, match="expected add_fields or add_columns"):
            m._Migrations__add_column_to_model(MagicMock(), 'extra', field)
