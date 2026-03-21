# Compresso Migrations v1

This directory contains Peewee database migrations for Compresso >= 0.1.0.

## How migrations run

On every startup, Compresso runs a two-step schema upgrade (see `compresso/libs/db_migrate.py`):

1. **Auto-sync**: Creates missing tables and adds missing columns based on model definitions.
   This handles simple additive changes without needing a migration file.

2. **Explicit migrations**: Runs the numbered scripts in this directory via peewee-migrate.
   These handle non-additive changes: column renames, drops, constraint changes, data backfills,
   and special indexes.

## Writing a new migration

Use the helper script from the project root:

```bash
devops/migrations.sh create "description of change"
```

This creates a numbered Python file in this directory. Migration scripts must be
written defensively (e.g., check column existence before renaming) because auto-sync
may have already created new columns before migrations run.

## Listing and running manually

```bash
devops/migrations.sh list
devops/migrations.sh migrate
devops/migrations.sh rollback
```
