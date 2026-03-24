"""
Migration 005: Add VMAF and SSIM quality score fields to Tasks table.

Adds vmaf_score and ssim_score nullable float fields for storing
perceptual quality metrics computed during the approval staging process.

Note: These columns are added automatically by the auto-sync in db_migrate.py
(since they have defaults of None / are nullable). This migration exists for
documentation and explicit ordering purposes.
"""


def migrate(migrator, database, fake=False, **kwargs):
    # Columns are auto-added by update_schema() since they are nullable with defaults.
    # This migration is a no-op marker for tracking purposes.
    pass


def rollback(migrator, database, fake=False, **kwargs):
    # Rollback would require removing columns, which SQLite doesn't support natively.
    pass
