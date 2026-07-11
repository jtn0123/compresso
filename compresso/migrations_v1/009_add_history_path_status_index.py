"""Migration 009: Index per-path failed-history checks used by large scans."""


def migrate(migrator, database, fake=False, **kwargs):
    if fake:
        return
    database.execute_sql(
        "CREATE INDEX IF NOT EXISTS completedtasks_abspath_task_success ON completedtasks (abspath, task_success)"
    )


def rollback(migrator, database, fake=False, **kwargs):
    if fake:
        return
    database.execute_sql("DROP INDEX IF EXISTS completedtasks_abspath_task_success")
