"""
Migration: Allow 'awaiting_approval' as a valid task status.

The Tasks.status column is a free-form TextField, so no DDL change is needed.
This migration exists as documentation and to ensure the migration sequence
is consistent if future migrations reference it.
"""


def migrate(migrator, database, fake=False, **kwargs):
    """No schema change required — status is a free-form TextField."""
    pass


def rollback(migrator, database, fake=False, **kwargs):
    """No schema change to reverse."""
    pass
