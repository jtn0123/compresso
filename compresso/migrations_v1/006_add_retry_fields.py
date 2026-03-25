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
    # This migration is a no-op marker for tracking purposes.
    pass


def rollback(migrator, database, fake=False, **kwargs):
    # Rollback would require removing columns, which SQLite doesn't support natively.
    pass
