"""Migration 007: Add the composite index used by pending-task scheduling."""


def migrate(migrator, database, fake=False, **kwargs):
    if fake:
        return
    database.execute_sql("CREATE INDEX IF NOT EXISTS tasks_status_priority ON tasks (status, priority)")


def rollback(migrator, database, fake=False, **kwargs):
    if fake:
        return
    database.execute_sql("DROP INDEX IF EXISTS tasks_status_priority")
