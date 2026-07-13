import json
import os
import sqlite3
import stat
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from compresso.ops import state_backup
from compresso.ops.state_backup import BackupError, create_state_backup, verify_state_backup


def _settings(tmp_path):
    settings = MagicMock()
    settings.get_config_path.return_value = str(tmp_path / "config")
    settings.get_userdata_path.return_value = str(tmp_path / "userdata")
    return settings


def _seed_state(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    with sqlite3.connect(config / "compresso.db") as connection:
        connection.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, name TEXT)")
        connection.execute("INSERT INTO jobs(name) VALUES ('canary')")
    (config / "settings.json").write_text(json.dumps({"api_auth_token": "private-token"}))
    journal = config / "recovery" / "file_operations"
    journal.mkdir(parents=True)
    (journal / "task-7.json").write_text(json.dumps({"state": "committed", "task_id": 7}))
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
