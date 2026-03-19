"""
Migration 003: Add flow settings fields to Libraries table.

Adds codec filtering, size guardrails, and replacement policy fields.

Note: These columns are added automatically by the auto-sync in db_migrate.py
(since they have defaults). This migration exists for documentation and
explicit ordering purposes. The actual column creation is handled by
update_schema()'s auto-add logic.
"""


def migrate(migrator, database, fake=False, **kwargs):
    # Columns are auto-added by update_schema() since they have defaults.
    # This migration is a no-op marker for tracking purposes.
    pass


def rollback(migrator, database, fake=False, **kwargs):
    # Rollback would require removing columns, which SQLite doesn't support natively.
    # Use a table rebuild migration if removal is ever needed.
    pass
