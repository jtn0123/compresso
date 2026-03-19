#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_db_migrate.py

    Unit tests for compresso.libs.db_migrate.Migrations.
    Tests schema creation, auto-sync of columns/indexes, and migration execution.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from peewee import Model, CharField


@pytest.mark.unittest
class TestMigrationsInit:

    def test_creates_db_directory_if_missing(self, tmp_path):
        db_dir = tmp_path / "subdir"
        db_file = str(db_dir / "compresso.db")
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
        assert os.path.isdir(str(db_dir))
        assert m.database is not None

    def test_database_is_none_for_unknown_type(self, tmp_path):
        config = {
            'TYPE': 'POSTGRES',
            'FILE': str(tmp_path / "db.sqlite"),
        }
        with patch('compresso.libs.db_migrate.CompressoLogging'):
            from compresso.libs.db_migrate import Migrations
            m = Migrations(config)
        assert m.database is None


@pytest.mark.unittest
class TestMigrationsUpdateSchema:

    def _make_migrations(self, tmp_path):
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

    @patch('compresso.libs.db_migrate.inspect')
    def test_update_schema_creates_tables(self, mock_inspect, tmp_path):
        """Test that update_schema creates tables for discovered models."""
        m = self._make_migrations(tmp_path)

        # Create a simple test model bound to our test database
        class TestModel(Model):
            name = CharField(default='')
            class Meta:
                database = m.database
                table_name = 'test_model'

        # Mock inspect to return our test model
        mock_inspect.getmembers.return_value = [('TestModel', TestModel)]
        mock_inspect.isclass = lambda x: isinstance(x, type)

        m.update_schema()

        # Verify the table was created
        tables = m.database.get_tables()
        assert 'test_model' in tables

    @patch('compresso.libs.db_migrate.inspect')
    def test_update_schema_runs_migrations(self, mock_inspect, tmp_path):
        """Test that update_schema calls the migration router."""
        m = self._make_migrations(tmp_path)
        mock_inspect.getmembers.return_value = []
        mock_inspect.isclass = lambda x: isinstance(x, type)
        m.router = MagicMock()

        m.update_schema()

        m.router.run.assert_called_once()
