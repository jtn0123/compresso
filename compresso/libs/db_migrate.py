#!/usr/bin/env python3

"""
compresso.database.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     14 Aug 2021, (12:03 PM)

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

import inspect
import logging
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Protocol, cast
from unittest import mock

from peewee import Database, Field, Model, Proxy, SqliteDatabase
from peewee_migrate import Migrator, Router

from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_write
from compresso.libs.unmodels.lib import BaseModel

_logger = logging.getLogger(__name__)


class MigrationFunction(Protocol):
    def __call__(self, migrator: Migrator, database: Database | Proxy, *, fake: bool) -> object: ...


class AddFieldsFunction(Protocol):
    def __call__(self, model: type[Model], **fields: Field) -> object: ...


class PatchedRouter(Router):
    """
    Subclass of peewee-migrate Router that fixes an incompatibility between
    peewee-migrate 1.15.0 and peewee >= 3.17.

    peewee-migrate's run_one mocks cursor.fetch_one, but peewee's get_columns()
    calls cursor.fetchall(). This override adds the missing mock attributes.
    """

    def read(self, name: str) -> tuple[MigrationFunction, MigrationFunction]:
        """Load a migration module while keeping the dynamic code boundary explicit."""
        migrate_dir = Path(self.migrate_dir)
        scope: dict[str, object] = {}
        code = compile((migrate_dir / f"{name}.py").read_text(encoding="utf-8"), "<migration>", "exec")
        exec(code, scope, None)  # noqa: S102 - migrations are trusted application code loaded from the configured directory
        migrate = scope.get("migrate")
        rollback = scope.get("rollback")
        if not callable(migrate) or not callable(rollback):
            raise RuntimeError(f"Migration {name!r} does not define migrate and rollback callables")
        return cast("MigrationFunction", migrate), cast("MigrationFunction", rollback)

    def run_one(
        self,
        name: str,
        migrator: Migrator,
        *,
        fake: bool = True,
        downgrade: bool = False,
        force: bool = False,
    ) -> str:
        try:
            migrate_fn, rollback_fn = self.read(name)
            if fake:
                mocked_cursor = mock.Mock()
                mocked_cursor.fetch_one.return_value = None
                mocked_cursor.fetchone.return_value = None
                mocked_cursor.fetchall.return_value = []
                with (
                    mock.patch("peewee.Model.select"),
                    mock.patch("peewee.Database.execute_sql", return_value=mocked_cursor),
                ):
                    migrate_fn(migrator, self.database, fake=fake)

                if force:
                    self.model.create(name=name)
                    self.logger.info("Done %s", name)

                migrator.__ops__ = []
                return name

            with self.database.transaction():
                if not downgrade:
                    self.logger.info('Migrate "%s"', name)
                    migrate_fn(migrator, self.database, fake=fake)
                    migrator()
                    self.model.create(name=name)
                else:
                    self.logger.info("Rolling back %s", name)
                    rollback_fn(migrator, self.database, fake=fake)
                    migrator()
                    execute_write(self.model.delete().where(self.model.name == name))

                self.logger.info("Done %s", name)
                return name

        except Exception:
            try:
                self.database.rollback()
            except Exception:
                _logger.debug("Rollback failed (no active transaction)", exc_info=True)
            operation = "Migration" if not downgrade else "Rollback"
            self.logger.exception("%s failed: %s", operation, name)
            raise


class Migrations:
    """
    Migrations

    Handle all migrations during application start.
    """

    database: SqliteDatabase | None
    router: PatchedRouter | None
    migrator: Migrator | None

    def __init__(self, config: Mapping[str, object]) -> None:
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)
        self.database = None
        self.router = None
        self.migrator = None

        # Based on configuration, select database to connect to.
        if config.get("TYPE") == "SQLITE":
            database_file = config.get("FILE")
            if not isinstance(database_file, str):
                raise ValueError("SQLite migration config requires a FILE path")
            # Create SQLite directory if not exists
            db_file_directory = os.path.dirname(database_file)
            if not os.path.exists(db_file_directory):
                os.makedirs(db_file_directory)
            self.database = SqliteDatabase(
                database_file,
                pragmas=(
                    ("foreign_keys", 1),
                    ("journal_mode", "wal"),
                ),
            )

            self.router = PatchedRouter(
                database=self.database,
                migrate_table=f"migratehistory_{config.get('MIGRATIONS_HISTORY_VERSION')}",
                migrate_dir=str(config["MIGRATIONS_DIR"]) if config.get("MIGRATIONS_DIR") is not None else None,
                logger=self.logger,
            )

            self.migrator = Migrator(self.database)

    def __run_all_migrations(self) -> None:
        """
        Run all new migrations.
        Migrations that have already been run will be ignored.

        :return:
        """
        if self.router is None:
            raise RuntimeError("Migration router is unavailable")
        self.router.run()

    def __add_column_to_model(self, model: type[Model], field_name: str, field: Field) -> None:
        """
        Add a field/column for a model using whichever migrator API is available.

        peewee-migrate versions have exposed both `add_fields` and `add_columns`
        across releases. We prefer `add_fields` when present and fall back to
        `add_columns` for compatibility with older variants.
        """
        if self.migrator is None:
            raise RuntimeError("Database migrator is unavailable")
        add_fields = cast("AddFieldsFunction | None", getattr(self.migrator, "add_fields", None))
        if callable(add_fields):
            add_fields(model, **{field_name: field})
            return

        add_columns = cast("AddFieldsFunction | None", getattr(self.migrator, "add_columns", None))
        if callable(add_columns):
            add_columns(model, **{field_name: field})
            return

        raise AttributeError("Migrator does not support adding columns (expected add_fields or add_columns).")

    def update_schema(self) -> None:
        """
        Bring the database schema up-to-date at application startup.

        This function intentionally does a two-step upgrade:

        1) Auto-sync (additive baseline):
        - Create any missing tables for the discovered models.
        - Add any missing columns to existing tables.
        - Add any missing non-unique indexes declared on models (simple column-name indexes only).

        This step is designed to make a new or slightly-behind database usable
        without requiring hand-written migrations for simple additions.

        2) Explicit migrations (non-additive changes):
        - Run peewee-migrate scripts to perform schema changes that SQLite (and
            this auto-sync) cannot safely or reliably do, e.g.:
            - rename tables/columns
            - drop tables/columns
            - rebuild tables to change constraints (FK/UNIQUE/NOT NULL) or to
                enforce new FK constraints
            - create/modify/drop indexes that are unique, partial, or expression-based
            - data migrations/backfills

        IMPORTANT:
        Because tables/columns are created/added *before* migrations run, migration
        scripts must NOT create tables or add columns unconditionally. Migrations
        must be written defensively (e.g. IF NOT EXISTS for indexes) to avoid
        clashes on fresh installs and should focus on the non-additive operations above.

        NOTE:
        Auto-added indexes are matched only on simple column lists and do not account
        for partial indexes or expression indexes. Any special index requirements
        should be handled explicitly in migrations.

        :return:
        """
        database = self.database
        migrator = self.migrator
        if database is None or migrator is None:
            raise RuntimeError("Database migrations are not configured")

        # Fetch all model classes
        discovered_models = inspect.getmembers(sys.modules["compresso.libs.unmodels"], inspect.isclass)
        all_models = [cast("type[Model]", candidate) for _name, candidate in discovered_models]

        self._create_discovered_models(all_models, database, migrator)

        # Migrations will only be used for removing obsolete columns
        self.__run_all_migrations()

        # Newly added fields can be auto added with this function... no need for a migration script
        # Ensure all files are also present for each of the model classes
        self.logger.info("Updating database fields")
        missing_required_columns = [
            missing
            for model in all_models
            if issubclass(model, BaseModel)
            for missing in self._sync_model_fields(model, database, migrator)
        ]

        if missing_required_columns:
            details = "; ".join(f"{table}.{column} ({reason})" for table, column, reason in missing_required_columns)
            raise RuntimeError(
                f"Database schema requires non-additive migrations for: {details}. "
                "Create a migration to add these columns safely."
            )

        self.logger.info("Updating database indexes")
        for model in all_models:
            if issubclass(model, BaseModel):
                self._sync_model_indexes(model, database, migrator)

    def _create_discovered_models(self, models: list[type[Model]], database: Database, migrator: Migrator) -> None:
        self.logger.info("Initialising database tables")
        try:
            with database.transaction():
                for model in models:
                    migrator.create_model(model)
                migrator()
        except Exception:
            self.logger.exception("Initialising tables failed")
            raise

    def _sync_model_fields(self, model: type[Model], database: Database, migrator: Migrator) -> list[tuple[str, str, str]]:
        missing_required: list[tuple[str, str, str]] = []
        table_name = str(model._meta.table_name)
        existing_columns = {column.name for column in database.get_columns(table_name)}
        # The migrator may replace Peewee field metadata while adding a column,
        # so iterate over a stable snapshot rather than the live dictionary.
        for field in list(model._meta.fields.values()):
            if not isinstance(field, Field):
                continue
            column_name = str(getattr(field, "column_name", field.name))
            if column_name in existing_columns:
                continue
            if getattr(field, "primary_key", False):
                missing_required.append((table_name, column_name, "primary key"))
            elif not field.null and field.default is None:
                missing_required.append((table_name, column_name, "non-null without default"))
            else:
                with database.transaction():
                    self.__add_column_to_model(model, field.name, field)
                    migrator()
        return missing_required

    @staticmethod
    def _declared_model_indexes(model: type[Model]) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
        declared: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
        for columns, unique in model._meta.indexes:
            if not unique and all(isinstance(column, str) for column in columns):
                normalized = tuple(
                    str(field.column_name) if (field := model._meta.fields.get(column)) else column for column in columns
                )
                declared.append((tuple(columns), normalized))
        declared.extend(
            ((field_name,), (str(field.column_name),))
            for field_name, field in model._meta.fields.items()
            if getattr(field, "index", False) and not getattr(field, "unique", False)
        )
        return declared

    def _sync_model_indexes(self, model: type[Model], database: Database, migrator: Migrator) -> None:
        table_name = str(model._meta.table_name)
        try:
            existing = database.get_indexes(table_name)
        except Exception:
            self.logger.exception("Failed to fetch indexes for table %s", table_name)
            return
        existing_columns = {tuple(getattr(index, "columns", [])) for index in existing}
        existing_names = {getattr(index, "name", None) for index in existing}
        for add_columns, compare_columns in self._declared_model_indexes(model):
            index_name = f"{table_name}_{'_'.join(compare_columns)}"
            if compare_columns in existing_columns or index_name in existing_names:
                continue
            try:
                with database.transaction():
                    migrator.add_index(model, *add_columns, unique=False)
                    migrator()
            except Exception:
                database.rollback()
                self.logger.exception("Failed to add index %s on table %s", add_columns, table_name)
                raise
