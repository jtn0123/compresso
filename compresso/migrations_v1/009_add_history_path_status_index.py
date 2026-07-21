"""Migration 009: Index per-path failed-history checks used by large scans."""

from compresso.migrations_v1._types import MigrationDatabase


def migrate(migrator: object, database: MigrationDatabase, fake: bool = False, **kwargs: object) -> None:
    del migrator
    if fake:
        return
    database.execute_sql(
        "CREATE INDEX IF NOT EXISTS completedtasks_abspath_task_success ON completedtasks (abspath, task_success)"
    )


def rollback(migrator: object, database: MigrationDatabase, fake: bool = False, **kwargs: object) -> None:
    del migrator
    if fake:
        return
    database.execute_sql("DROP INDEX IF EXISTS completedtasks_abspath_task_success")
