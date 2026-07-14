import json
import os
import sqlite3
import stat
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from compresso.ops import state_backup
from compresso.ops.state_backup import BackupError, create_state_backup, verify_state_backup


def _settings(tmp_path):
    settings = MagicMock()
    settings.get_config_path.return_value = str(tmp_path / "config")
    settings.get_userdata_path.return_value = str(tmp_path / "userdata")
    settings.get_cache_path.return_value = str(tmp_path / "cache")
    settings.get_library_path.return_value = str(tmp_path / "library")
    return settings


def _seed_state(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (tmp_path / "cache").mkdir()
    (tmp_path / "library").mkdir()
    with sqlite3.connect(config / "compresso.db") as connection:
        connection.execute("CREATE TABLE libraries (id INTEGER PRIMARY KEY, name TEXT, path TEXT NOT NULL)")
        connection.execute("INSERT INTO libraries(name, path) VALUES ('Media', ?)", (str(tmp_path / "library"),))
        connection.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, abspath TEXT, library_id INTEGER, status TEXT)")
    (config / "settings.json").write_text(json.dumps({"api_auth_token": "private-token"}))
    journal = config / "recovery" / "file_operations"
    journal.mkdir(parents=True)
    (journal / "task-7.json").write_text(
        json.dumps(
            {
                "version": 1,
                "operation_id": "task-7",
                "state": "committed",
                "task_id": 7,
                "finalization_phase": None,
                "backups": [],
                "created_paths": [],
            }
        )
    )
    safety = tmp_path / "userdata" / "safety"
    safety.mkdir(parents=True)
    (safety / "state.json").write_text(json.dumps({"schema_version": 1, "pause_required": False, "events": []}))


@pytest.mark.unittest
def test_create_and_rehearse_private_state_backup(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)

    created = create_state_backup(settings, "pre-nas.zip")
    verified = verify_state_backup(settings, "pre-nas.zip", output_name="pre-nas-rehearsal.json")

    archive = Path(created["archive_path"])
    assert archive == tmp_path / "userdata" / "backups" / "pre-nas.zip"
    assert created["database_integrity"] == "ok"
    assert verified["overall_status"] == "pass"
    assert verified["database_integrity"] == "ok"
    assert verified["files_verified"] == 4
    assert Path(verified["report_path"]).is_file()
    if os.name != "nt":
        assert archive.stat().st_mode & 0o777 == 0o600
        assert Path(verified["report_path"]).stat().st_mode & 0o777 == 0o600
    with zipfile.ZipFile(archive) as bundle:
        assert sorted(bundle.namelist()) == [
            "config/compresso.db",
            "config/recovery/file_operations/task-7.json",
            "config/settings.json",
            "manifest.json",
            "userdata/safety/state.json",
        ]
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["schema_version"] == 1
        assert manifest["files"]["config/settings.json"]["sha256"]


@pytest.mark.unittest
def test_backup_and_rehearsal_close_every_database_connection(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    real_connect = sqlite3.connect
    connections = []

    def tracked_connect(*args, **kwargs):
        connection = real_connect(*args, **kwargs)
        connections.append(connection)
        return connection

    with patch("compresso.ops.state_backup.sqlite3.connect", side_effect=tracked_connect):
        create_state_backup(settings, "state.zip")
        verify_state_backup(settings, "state.zip")

    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")


@pytest.mark.unittest
def test_rehearsal_rejects_tampered_payload(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    created = create_state_backup(settings, "state.zip")
    archive = Path(created["archive_path"])

    with pytest.warns(UserWarning, match="Duplicate name"), zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("config/settings.json", b"tampered")

    with pytest.raises(BackupError, match="duplicate archive entry|checksum mismatch"):
        verify_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_rehearsal_rejects_path_traversal_and_symlinks(tmp_path):
    settings = _settings(tmp_path)
    backup_root = tmp_path / "userdata" / "backups"
    backup_root.mkdir(parents=True)

    traversal = backup_root / "traversal.zip"
    with zipfile.ZipFile(traversal, "w") as bundle:
        bundle.writestr("../escape", b"bad")
        bundle.writestr("manifest.json", json.dumps({"schema_version": 1, "files": {}}))
    with pytest.raises(BackupError, match="unsafe archive entry"):
        verify_state_backup(settings, traversal.name)

    symlink = backup_root / "symlink.zip"
    link = zipfile.ZipInfo("config/settings.json")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(symlink, "w") as bundle:
        bundle.writestr(link, "target")
        bundle.writestr("manifest.json", json.dumps({"schema_version": 1, "files": {}}))
    with pytest.raises(BackupError, match="symbolic link"):
        verify_state_backup(settings, symlink.name)


@pytest.mark.unittest
@pytest.mark.parametrize("name", ["../state.zip", "/tmp/state.zip", "state.tar", "bad name.zip"])
def test_backup_names_are_confined_to_owned_directories(tmp_path, name):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)

    with pytest.raises(BackupError, match="safe ZIP filename"):
        create_state_backup(settings, name)


@pytest.mark.unittest
def test_create_rejects_corrupt_database_without_publishing_archive(tmp_path):
    settings = _settings(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "compresso.db").write_bytes(b"not sqlite")

    with pytest.raises(BackupError, match="SQLite backup failed"):
        create_state_backup(settings, "broken.zip")

    assert not (tmp_path / "userdata" / "backups" / "broken.zip").exists()


@pytest.mark.unittest
def test_create_refuses_to_overwrite_existing_backup(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    create_state_backup(settings, "state.zip")

    with pytest.raises(BackupError, match="Refusing to overwrite"):
        create_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_rehearsal_checks_temporary_disk_capacity_before_extracting(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    create_state_backup(settings, "state.zip")

    with (
        patch("compresso.ops.state_backup.shutil.disk_usage", return_value=MagicMock(free=0)),
        pytest.raises(BackupError, match="temporary disk space"),
    ):
        verify_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_rehearsal_rejects_content_larger_than_its_declared_zip_size(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    create_state_backup(settings, "state.zip")
    original_infolist = zipfile.ZipFile.infolist
    original_open = zipfile.ZipFile.open
    actual_sizes = {}

    def forged_infolist(bundle):
        infos = original_infolist(bundle)
        for info in infos:
            if info.filename == "config/settings.json":
                actual_sizes[id(info)] = info.file_size
                info.file_size = 1
        return infos

    def open_with_actual_size(bundle, member, *args, **kwargs):
        if isinstance(member, zipfile.ZipInfo) and id(member) in actual_sizes:
            member.file_size = actual_sizes[id(member)]
        return original_open(bundle, member, *args, **kwargs)

    with (
        patch.object(zipfile.ZipFile, "infolist", forged_infolist),
        patch.object(zipfile.ZipFile, "open", open_with_actual_size),
        pytest.raises(BackupError, match="declared size"),
    ):
        verify_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_rehearsal_refuses_to_overwrite_existing_report(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    create_state_backup(settings, "state.zip")
    verify_state_backup(settings, "state.zip", output_name="rehearsal.json")
    report = tmp_path / "userdata" / "recovery-rehearsals" / "rehearsal.json"
    original = report.read_bytes()

    with pytest.raises(BackupError, match="Refusing to overwrite"):
        verify_state_backup(settings, "state.zip", output_name="rehearsal.json")

    assert report.read_bytes() == original


@pytest.mark.unittest
def test_cli_creates_and_rehearses_backup(tmp_path, monkeypatch, capsys):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    monkeypatch.setattr(state_backup, "Config", lambda: settings)

    assert state_backup.main(["backup", "--output", "state.zip"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["database_integrity"] == "ok"

    assert state_backup.main(["rehearse", "--archive", "state.zip", "--output", "rehearsal.json"]) == 0
    rehearsed = json.loads(capsys.readouterr().out)
    assert rehearsed["overall_status"] == "pass"


@pytest.mark.unittest
def test_cli_returns_structured_error_for_unsafe_name(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(state_backup, "Config", lambda: _settings(tmp_path))

    assert state_backup.main(["backup", "--output", "../escape.zip"]) == 1
    error = json.loads(capsys.readouterr().err)
    assert error["type"] == "state-backup"


@pytest.mark.unittest
@pytest.mark.skipif(os.name == "nt", reason="Creating directory symlinks requires elevated Windows privileges")
def test_backup_rejects_symlinked_owned_directory(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    backups = tmp_path / "userdata" / "backups"
    backups.symlink_to(external, target_is_directory=True)

    with pytest.raises(BackupError, match="symbolic-link user-data directory"):
        create_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_create_requires_object_settings_file(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    (tmp_path / "config" / "settings.json").write_text("[]")

    with pytest.raises(BackupError, match="JSON object"):
        create_state_backup(settings, "state.zip")

    assert not (tmp_path / "userdata" / "backups" / "state.zip").exists()


@pytest.mark.unittest
def test_create_rejects_invalid_recovery_journal(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    journal = tmp_path / "config" / "recovery" / "file_operations" / "task-7.json"
    journal.write_text(json.dumps({"state": "committed", "task_id": 7}))

    with pytest.raises(BackupError, match="journal is invalid"):
        create_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_create_rejects_invalid_journal_finalization_phase(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    journal = tmp_path / "config" / "recovery" / "file_operations" / "task-7.json"
    payload = json.loads(journal.read_text())
    payload["finalization_phase"] = "skip-safety"
    journal.write_text(json.dumps(payload))

    with pytest.raises(BackupError, match="finalization phase"):
        create_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_create_rejects_journal_paths_outside_configured_roots(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    journal = tmp_path / "config" / "recovery" / "file_operations" / "task-7.json"
    payload = json.loads(journal.read_text())
    payload["created_paths"] = [str(tmp_path.parent / "unowned-media.mkv")]
    journal.write_text(json.dumps(payload))

    with pytest.raises(BackupError, match="outside configured roots"):
        create_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_create_requires_settings_file(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    (tmp_path / "config" / "settings.json").unlink()

    with pytest.raises(BackupError, match="settings.json is missing"):
        create_state_backup(settings, "state.zip")


@pytest.mark.unittest
def test_concurrent_creates_cannot_both_publish_same_backup_name(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(create_state_backup, settings, "state.zip") for _ in range(2)]
    results = []
    for future in futures:
        try:
            results.append(future.result())
        except BackupError as error:
            results.append(error)

    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, BackupError) for result in results) == 1
    assert (tmp_path / "userdata" / "backups" / "state.zip").is_file()


@pytest.mark.unittest
def test_archive_uses_staged_settings_snapshot_when_live_file_changes(tmp_path):
    settings = _settings(tmp_path)
    _seed_state(tmp_path)
    settings_file = tmp_path / "config" / "settings.json"
    original = settings_file.read_bytes()
    real_write_archive = state_backup._write_archive

    def mutate_live_settings(destination, files, generated_at):
        settings_file.write_text(json.dumps({"api_auth_token": "changed"}))
        return real_write_archive(destination, files, generated_at)

    with patch("compresso.ops.state_backup._write_archive", side_effect=mutate_live_settings):
        created = create_state_backup(settings, "state.zip")

    with zipfile.ZipFile(created["archive_path"]) as bundle:
        assert bundle.read("config/settings.json") == original


@pytest.mark.unittest
def test_integrity_check_rejects_non_compresso_sqlite_database(tmp_path):
    database = tmp_path / "placeholder.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")

    with pytest.raises(BackupError, match="required Compresso tables"):
        state_backup._database_integrity(database)


@pytest.mark.unittest
def test_integrity_check_rejects_tables_without_compresso_schema(tmp_path):
    database = tmp_path / "placeholder.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE libraries (id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")

    with pytest.raises(BackupError, match="required Compresso columns"):
        state_backup._database_integrity(database)
