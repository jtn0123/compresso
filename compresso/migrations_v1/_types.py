"""Structural types for the peewee-migrate callback boundary."""

from collections.abc import Sequence
from typing import Protocol


class MigrationColumn(Protocol):
    name: str


class MigrationCursor(Protocol):
    def fetchall(self) -> Sequence[Sequence[object]]: ...


class MigrationDatabase(Protocol):
    def execute_sql(self, sql: str) -> MigrationCursor: ...

    def get_columns(self, table: str) -> Sequence[MigrationColumn]: ...


class SchemaMigrator(Protocol):
    def rename_column(self, table: str, old_name: str, new_name: str) -> object: ...


class MigrationOperations(Protocol):
    def append(self, operation: object) -> None: ...


class MigrationRunner(Protocol):
    ops: MigrationOperations
    migrator: SchemaMigrator
