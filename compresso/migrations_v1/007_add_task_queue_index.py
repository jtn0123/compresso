"""Migration 007: Add the composite index used by pending-task scheduling."""

from compresso.migrations_v1._types import MigrationDatabase


def migrate(migrator: object, database: MigrationDatabase, fake: bool = False, **kwargs: object) -> None:
    if fake:
        return
    database.execute_sql("CREATE INDEX IF NOT EXISTS tasks_status_priority ON tasks (status, priority)")


def rollback(migrator: object, database: MigrationDatabase, fake: bool = False, **kwargs: object) -> None:
    if fake:
        return
    database.execute_sql("DROP INDEX IF EXISTS tasks_status_priority")
