"""Migration 006: Add retry and deferred scheduling fields to Tasks table.

Adds retry_count, max_retries, and deferred_until nullable fields to support
automatic task retry with exponential backoff on transient failures.
"""

from compresso.migrations_v1._types import MigrationDatabase


def migrate(migrator: object, database: MigrationDatabase, fake: bool = False, **kwargs: object) -> None:
    if fake:
        return

    # Check which columns already exist
    cursor = database.execute_sql("PRAGMA table_info(tasks)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "retry_count" not in existing_columns:
        database.execute_sql("ALTER TABLE tasks ADD COLUMN retry_count INTEGER DEFAULT 0")

    if "max_retries" not in existing_columns:
        database.execute_sql("ALTER TABLE tasks ADD COLUMN max_retries INTEGER DEFAULT 3")

    if "deferred_until" not in existing_columns:
        database.execute_sql("ALTER TABLE tasks ADD COLUMN deferred_until REAL")

    # Backfill existing rows
    database.execute_sql("UPDATE tasks SET retry_count = 0 WHERE retry_count IS NULL")
    database.execute_sql("UPDATE tasks SET max_retries = 3 WHERE max_retries IS NULL")


def rollback(migrator: object, database: MigrationDatabase, fake: bool = False, **kwargs: object) -> None:
    """Rollback not required — added columns with defaults can remain unused."""
