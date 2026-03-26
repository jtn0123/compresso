"""
Migration 006: Add retry and deferred scheduling fields to Tasks table.

Adds retry_count, max_retries, and deferred_until nullable fields to support
automatic task retry with exponential backoff on transient failures.

Note: These columns are added automatically by the auto-sync in db_migrate.py
(since they are nullable with defaults). This migration exists for
documentation and explicit ordering purposes.
"""


def migrate(migrator, database, fake=False, **kwargs):
    # Columns are auto-added by update_schema() since they are nullable with defaults.
    # Backfill existing rows with ORM default values
    if not fake:
        database.execute_sql("UPDATE tasks SET retry_count = 0 WHERE retry_count IS NULL")
        database.execute_sql("UPDATE tasks SET max_retries = 3 WHERE max_retries IS NULL")
        # deferred_until default is NULL, so no backfill needed


def rollback(migrator, database, fake=False, **kwargs):
    # Rollback would require removing columns, which SQLite doesn't support natively.
    pass
