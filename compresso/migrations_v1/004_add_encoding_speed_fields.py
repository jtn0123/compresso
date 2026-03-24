"""
Migration 004: Add encoding speed tracking fields to CompressionStats table.

Adds encoding_duration_seconds, avg_encoding_fps, source_duration_seconds,
and encoding_speed_ratio fields for tracking FFmpeg encoding performance.

Note: These columns are added automatically by the auto-sync in db_migrate.py
(since they have defaults). This migration exists for documentation and
explicit ordering purposes.
"""


def migrate(migrator, database, fake=False, **kwargs):
    # Columns are auto-added by update_schema() since they have defaults.
    # This migration is a no-op marker for tracking purposes.
    pass


def rollback(migrator, database, fake=False, **kwargs):
    # Rollback would require removing columns, which SQLite doesn't support natively.
    pass
