"""Migration 008: Durable job identity, remote leases, and idempotent results."""


def migrate(migrator, database, fake=False, **kwargs):
    if fake:
        return

    cursor = database.execute_sql("PRAGMA table_info(tasks)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    columns = {
        "job_id": "TEXT",
        "remote_task_id": "INTEGER",
        "remote_installation_uuid": "TEXT",
        "lease_token": "TEXT",
        "lease_expires_at": "DATETIME",
        "heartbeat_at": "DATETIME",
        "remote_result_checksum": "TEXT",
        "remote_completed_at": "DATETIME",
    }
    for column, data_type in columns.items():
        if column not in existing_columns:
            database.execute_sql(f"ALTER TABLE tasks ADD COLUMN {column} {data_type}")

    database.execute_sql("UPDATE tasks SET job_id = 'legacy-' || id WHERE job_id IS NULL")
    database.execute_sql("CREATE UNIQUE INDEX IF NOT EXISTS tasks_job_id ON tasks (job_id)")
    database.execute_sql("CREATE INDEX IF NOT EXISTS tasks_remote_installation_uuid ON tasks (remote_installation_uuid)")
    database.execute_sql("CREATE INDEX IF NOT EXISTS tasks_lease_expires_at ON tasks (lease_expires_at)")


def rollback(migrator, database, fake=False, **kwargs):
    if fake:
        return
    database.execute_sql("DROP INDEX IF EXISTS tasks_job_id")
    database.execute_sql("DROP INDEX IF EXISTS tasks_remote_installation_uuid")
    database.execute_sql("DROP INDEX IF EXISTS tasks_lease_expires_at")
