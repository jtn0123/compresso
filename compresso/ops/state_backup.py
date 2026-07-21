# SPDX-License-Identifier: GPL-3.0-only

"""Private control-plane backups and non-destructive recovery rehearsals."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import uuid
import zipfile
from collections.abc import Iterable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import IO, TypedDict, cast
from urllib.parse import quote

from compresso.config import Config
from compresso.libs.json_state import atomic_json_write

SCHEMA_VERSION = 1
ARCHIVE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.zip")
REPORT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json")
MAX_ARCHIVE_ENTRIES = 2_000
MAX_UNCOMPRESSED_BYTES = 32 * 1024**3
MAX_MANIFEST_BYTES = 4 * 1024**2
TEMPORARY_SPACE_RESERVE_BYTES = 512 * 1024**2
MANIFEST_ARCHIVE_PATH = "manifest.json"
DATABASE_FILENAME = "compresso.db"
DATABASE_ARCHIVE_PATH = f"config/{DATABASE_FILENAME}"
SETTINGS_ARCHIVE_PATH = "config/settings.json"
BACKUP_KIND = "compresso-control-plane-backup"
REQUIRED_DATABASE_COLUMNS = {
    "libraries": {"id", "name", "path"},
    "tasks": {"id", "abspath", "library_id", "status"},
}
REQUIRED_DATABASE_TABLES = set(REQUIRED_DATABASE_COLUMNS)
JOURNAL_STATES = {
    "active",
    "rolling_back",
    "rollback_failed",
    "committing",
    "commit_cleanup_pending",
    "committed",
}
JOURNAL_FINALIZATION_PHASES = {None, "file_committed", "history_committed", "metadata_committed", "task_deleted"}


class BackupError(RuntimeError):
    """A state backup or rehearsal failed a safety invariant."""


class ManifestFile(TypedDict):
    sha256: str
    size_bytes: int


class BackupManifest(TypedDict):
    schema_version: int
    kind: str
    generated_at: str
    files: dict[str, ManifestFile]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _safe_owned_path(root: Path, name: str, pattern: re.Pattern[str], label: str) -> Path:
    if Path(name).name != name or pattern.fullmatch(name) is None:
        file_type = "ZIP" if pattern is ARCHIVE_NAME_PATTERN else "JSON"
        raise BackupError(f"{label} must be a safe {file_type} filename")
    root = root.expanduser().resolve()
    destination = (root / name).resolve()
    if destination.parent != root:
        raise BackupError(f"{label} escapes its installation-owned directory")
    return destination


def _owned_directory(userdata_root: Path, name: str) -> Path:
    candidate = userdata_root / name
    if candidate.is_symlink():
        raise BackupError(f"Refusing symbolic-link user-data directory: {name}")
    destination = candidate.resolve()
    if destination.parent != userdata_root:
        raise BackupError(f"User-data directory escapes the configured root: {name}")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(destination, 0o700)
    return destination


def _private_exclusive_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        reservation = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise BackupError("Refusing to overwrite an existing recovery rehearsal report") from error
    os.close(reservation)
    try:
        atomic_json_write(path, payload, mode=0o600)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _database_integrity(path: Path) -> str:
    uri = f"file:{quote(path.as_posix(), safe='/')}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
            tables = {
                str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
            columns = {
                table: {
                    str(row[0]) for row in connection.execute("SELECT name FROM pragma_table_info(?)", (table,)).fetchall()
                }
                for table in REQUIRED_DATABASE_TABLES & tables
            }
    except sqlite3.Error as error:
        raise BackupError(f"SQLite integrity check failed: {type(error).__name__}") from error
    if rows != [("ok",)]:
        raise BackupError("SQLite integrity check did not return ok")
    missing_tables = sorted(REQUIRED_DATABASE_TABLES - tables)
    if missing_tables:
        raise BackupError(f"SQLite backup is missing required Compresso tables: {', '.join(missing_tables)}")
    missing_columns = {
        table: sorted(required - columns[table])
        for table, required in REQUIRED_DATABASE_COLUMNS.items()
        if required - columns[table]
    }
    if missing_columns:
        detail = "; ".join(f"{table}: {', '.join(names)}" for table, names in sorted(missing_columns.items()))
        raise BackupError(f"SQLite backup is missing required Compresso columns: {detail}")
    return "ok"


def _snapshot_database(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BackupError("Compresso database is missing")
    source_uri = f"file:{quote(source.as_posix(), safe='/')}?mode=ro"
    try:
        with (
            closing(sqlite3.connect(source_uri, uri=True, timeout=10)) as source_connection,
            closing(sqlite3.connect(destination)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
            destination_connection.commit()
        _database_integrity(destination)
    except (sqlite3.Error, BackupError) as error:
        destination.unlink(missing_ok=True)
        if isinstance(error, BackupError):
            raise BackupError(f"SQLite backup failed: {error}") from error
        raise BackupError(f"SQLite backup failed: {type(error).__name__}") from error


def _evidence_files(root: Path) -> Iterable[tuple[str, Path]]:
    for category in ("safety", "readiness", "planning"):
        category_root = root / category
        if not category_root.is_dir():
            continue
        for source in sorted(category_root.glob("*.json")):
            if source.is_file() and not source.is_symlink():
                yield f"userdata/{category}/{source.name}", source


def _journal_files(config_root: Path) -> Iterable[tuple[str, Path]]:
    journal_root = config_root / "recovery" / "file_operations"
    if not journal_root.is_dir():
        return
    for source in sorted(journal_root.glob("*.json")):
        if source.is_file() and not source.is_symlink():
            yield f"config/recovery/file_operations/{source.name}", source


def _write_archive(destination: Path, files: list[tuple[str, Path]], generated_at: str) -> BackupManifest:
    manifest_files: dict[str, ManifestFile] = {
        logical_name: {"sha256": _sha256(source), "size_bytes": source.stat().st_size} for logical_name, source in files
    }
    manifest = BackupManifest(
        schema_version=SCHEMA_VERSION,
        kind=BACKUP_KIND,
        generated_at=generated_at,
        files=manifest_files,
    )
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
    reserved_destination = False
    try:
        try:
            reservation = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise BackupError("Refusing to overwrite an existing state backup") from error
        os.close(reservation)
        reserved_destination = True
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w+b") as archive_file:
            with zipfile.ZipFile(archive_file, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
                for logical_name, source in files:
                    bundle.write(source, logical_name)
                bundle.writestr(MANIFEST_ARCHIVE_PATH, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            archive_file.flush()
            os.fsync(archive_file.fileno())
        os.replace(temporary, destination)
        reserved_destination = False
        if os.name != "nt":
            os.chmod(destination, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
        if reserved_destination:
            destination.unlink(missing_ok=True)
    return manifest


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupError(f"{label} is not valid JSON") from error
    if not isinstance(payload, dict):
        raise BackupError(f"{label} must contain a JSON object")
    return payload


def _stage_backup_files(files: list[tuple[str, Path]], staging_root: Path) -> list[tuple[str, Path]]:
    staged = []
    total_bytes = 0
    for logical_name, source in files:
        destination = staging_root.joinpath(*PurePosixPath(logical_name).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with source.open("rb") as input_file, destination.open("xb") as output_file:
                shutil.copyfileobj(input_file, output_file, length=1024 * 1024)
        except OSError as error:
            raise BackupError(f"Could not snapshot control-plane file: {logical_name}") from error
        total_bytes += destination.stat().st_size
        if total_bytes > MAX_UNCOMPRESSED_BYTES:
            raise BackupError("Control-plane backup exceeds its safety size limit")
        if logical_name.endswith(".json"):
            try:
                payload = json.loads(destination.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise BackupError(f"Control-plane JSON changed or is invalid: {logical_name}") from error
            if logical_name == SETTINGS_ARCHIVE_PATH and not isinstance(payload, dict):
                raise BackupError("Compresso settings.json must contain a JSON object")
            if logical_name.startswith("config/recovery/file_operations/"):
                _validate_journal_payload(logical_name, payload)
        staged.append((logical_name, destination))
    return staged


def create_state_backup(settings: Config, output_name: str) -> dict[str, object]:
    """Create an online SQLite snapshot plus small recovery evidence files."""
    config_root = Path(settings.get_config_path()).expanduser().resolve()
    userdata_root = Path(settings.get_userdata_path()).expanduser().resolve()
    destination = _safe_owned_path(_owned_directory(userdata_root, "backups"), output_name, ARCHIVE_NAME_PATTERN, "--output")
    if destination.exists():
        raise BackupError("Refusing to overwrite an existing state backup")
    with tempfile.TemporaryDirectory(prefix=".state-backup-", dir=destination.parent) as temporary:
        snapshot = Path(temporary) / DATABASE_FILENAME
        _snapshot_database(config_root / DATABASE_FILENAME, snapshot)
        files: list[tuple[str, Path]] = [(DATABASE_ARCHIVE_PATH, snapshot)]
        settings_file = config_root / "settings.json"
        if settings_file.is_symlink():
            raise BackupError("Refusing to back up a symbolic-link settings file")
        if not settings_file.is_file():
            raise BackupError("Compresso settings.json is missing")
        _read_json_object(settings_file, "Compresso settings.json")
        files.append((SETTINGS_ARCHIVE_PATH, settings_file))
        files.extend(_journal_files(config_root))
        files.extend(_evidence_files(userdata_root))
        if len(files) > MAX_ARCHIVE_ENTRIES:
            raise BackupError("Control-plane backup contains too many files")
        staging_root = Path(temporary) / "payload"
        staged_files = _stage_backup_files(files, staging_root)
        _validate_recovery_semantics(staging_root, settings)
        manifest = _write_archive(destination, staged_files, _timestamp())
    return {
        "archive_path": str(destination),
        "archive_sha256": _sha256(destination),
        "database_integrity": "ok",
        "files_archived": len(manifest["files"]),
        "generated_at": manifest["generated_at"],
    }


def _validate_entry(info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(info.filename)
    if path.is_absolute() or ".." in path.parts or not path.parts or info.filename.endswith("/"):
        raise BackupError(f"unsafe archive entry: {info.filename}")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise BackupError(f"archive entry is a symbolic link: {info.filename}")
    allowed = (
        info.filename == MANIFEST_ARCHIVE_PATH
        or info.filename in {DATABASE_ARCHIVE_PATH, SETTINGS_ARCHIVE_PATH}
        or (len(path.parts) == 4 and path.parts[:3] == ("config", "recovery", "file_operations"))
        or (len(path.parts) == 3 and path.parts[0] == "userdata" and path.parts[1] in {"safety", "readiness", "planning"})
    )
    if not allowed or (info.filename != DATABASE_ARCHIVE_PATH and not info.filename.endswith(".json")):
        raise BackupError(f"unexpected archive entry: {info.filename}")


def _copy_and_hash(source: IO[bytes], destination: Path, *, maximum_bytes: int, logical_name: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            if size > maximum_bytes:
                raise BackupError(f"archive entry exceeds its declared size: {logical_name}")
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest(), size


def _validate_archive_inventory(
    bundle: zipfile.ZipFile,
) -> tuple[list[zipfile.ZipInfo], list[str], dict[str, int], Path]:
    infos = bundle.infolist()
    names = [info.filename for info in infos]
    declared_sizes = {info.filename: info.file_size for info in infos}
    if len(names) != len(set(names)):
        raise BackupError("duplicate archive entry detected")
    if len(infos) > MAX_ARCHIVE_ENTRIES + 1:
        raise BackupError("archive contains too many entries")
    uncompressed_bytes = sum(declared_sizes.values())
    if uncompressed_bytes > MAX_UNCOMPRESSED_BYTES:
        raise BackupError("archive expands beyond the rehearsal safety limit")
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if shutil.disk_usage(temporary_root).free < uncompressed_bytes + TEMPORARY_SPACE_RESERVE_BYTES:
        raise BackupError("Insufficient temporary disk space for recovery rehearsal")
    for info in infos:
        _validate_entry(info)
    if MANIFEST_ARCHIVE_PATH not in names:
        raise BackupError("archive manifest is missing")
    return infos, names, declared_sizes, temporary_root


def _read_manifest(bundle: zipfile.ZipFile) -> BackupManifest:
    manifest_info = bundle.getinfo(MANIFEST_ARCHIVE_PATH)
    if manifest_info.file_size > MAX_MANIFEST_BYTES:
        raise BackupError("archive manifest is too large")
    try:
        manifest = json.loads(bundle.read(MANIFEST_ARCHIVE_PATH))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupError("archive manifest is invalid") from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != SCHEMA_VERSION
        or manifest.get("kind") != BACKUP_KIND
        or not isinstance(manifest.get("files"), dict)
    ):
        raise BackupError("archive manifest is invalid")
    return cast("BackupManifest", manifest)


def _valid_manifest_metadata(logical_name: object, metadata: object) -> bool:
    return (
        isinstance(logical_name, str)
        and isinstance(metadata, dict)
        and re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("sha256", ""))) is not None
        and isinstance(metadata.get("size_bytes"), int)
        and metadata["size_bytes"] >= 0
    )


def _validate_manifest_files(
    manifest: BackupManifest, names: list[str], declared_sizes: dict[str, int]
) -> dict[str, dict[str, object]]:
    expected_files = manifest["files"]
    if set(expected_files) != set(names) - {MANIFEST_ARCHIVE_PATH}:
        raise BackupError("archive entries do not match the manifest")
    for logical_name, metadata in expected_files.items():
        if not _valid_manifest_metadata(logical_name, metadata):
            raise BackupError("archive manifest contains invalid file metadata")
        if declared_sizes[logical_name] != metadata["size_bytes"]:
            raise BackupError(f"declared size mismatch for {logical_name}")
    return cast("dict[str, dict[str, object]]", expected_files)


def _extract_entry(
    bundle: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    rehearsal_root: Path,
    expected: dict[str, object],
    declared_size: int,
) -> None:
    destination = rehearsal_root.joinpath(*PurePosixPath(info.filename).parts).resolve()
    if not destination.is_relative_to(rehearsal_root):
        raise BackupError(f"unsafe archive destination: {info.filename}")
    with bundle.open(info) as source:
        digest, size = _copy_and_hash(
            source,
            destination,
            maximum_bytes=declared_size,
            logical_name=info.filename,
        )
    if digest != expected["sha256"] or size != expected["size_bytes"]:
        raise BackupError(f"checksum mismatch for {info.filename}")
    if info.filename.endswith(".json"):
        json.loads(destination.read_text(encoding="utf-8"))


def _validate_journal_payload(logical_name: str, payload: object) -> list[str]:
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise BackupError(f"file-operation journal is invalid: {logical_name}")
    operation_id = payload.get("operation_id")
    if not isinstance(operation_id, str) or f"{operation_id}.json" != PurePosixPath(logical_name).name:
        raise BackupError(f"file-operation journal identity is invalid: {logical_name}")
    _validate_journal_state(logical_name, payload)
    task_id = payload.get("task_id")
    if task_id is not None and (not isinstance(task_id, int) or isinstance(task_id, bool)):
        raise BackupError(f"file-operation journal task ID is invalid: {logical_name}")
    backups = payload.get("backups")
    created_paths = payload.get("created_paths")
    if not isinstance(backups, list) or not isinstance(created_paths, list):
        raise BackupError(f"file-operation journal paths are invalid: {logical_name}")
    paths = _validated_backup_paths(logical_name, backups)
    if not all(isinstance(item, str) and item for item in created_paths):
        raise BackupError(f"file-operation journal created paths are invalid: {logical_name}")
    paths.extend(created_paths)
    return paths


def _validate_journal_state(logical_name: str, payload: dict[object, object]) -> None:
    if payload.get("state") not in JOURNAL_STATES:
        raise BackupError(f"file-operation journal state is invalid: {logical_name}")
    if payload.get("finalization_phase") not in JOURNAL_FINALIZATION_PHASES:
        raise BackupError(f"file-operation journal finalization phase is invalid: {logical_name}")


def _validated_backup_paths(logical_name: str, backups: list[object]) -> list[str]:
    paths: list[str] = []
    for pair in backups:
        if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(item, str) and item for item in pair):
            raise BackupError(f"file-operation journal backup is invalid: {logical_name}")
        paths.extend(pair)
    return paths


def _validate_recovery_semantics(rehearsal_root: Path, settings: Config) -> None:
    _read_json_object(rehearsal_root / SETTINGS_ARCHIVE_PATH, "archived settings.json")
    allowed_roots = _configured_recovery_roots(settings)
    allowed_roots.extend(_archived_library_roots(rehearsal_root))
    for journal in sorted((rehearsal_root / "config" / "recovery" / "file_operations").glob("*.json")):
        _validate_recovery_journal(rehearsal_root, journal, allowed_roots)


def _configured_recovery_roots(settings: Config) -> list[Path]:
    allowed_roots: list[Path] = []
    for getter_name in ("get_config_path", "get_cache_path", "get_library_path", "get_userdata_path"):
        getter = getattr(settings, getter_name, None)
        value = getter() if callable(getter) else None
        if isinstance(value, (str, os.PathLike)) and os.fspath(value):
            allowed_roots.append(Path(value).expanduser().resolve())
    return allowed_roots


def _archived_library_roots(rehearsal_root: Path) -> list[Path]:
    database = rehearsal_root / DATABASE_ARCHIVE_PATH
    uri = f"file:{quote(database.as_posix(), safe='/')}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
            library_paths = connection.execute("SELECT path FROM libraries WHERE path IS NOT NULL").fetchall()
    except sqlite3.Error as error:
        raise BackupError("Archived library paths could not be read") from error
    return [
        Path(value).expanduser().resolve()
        for (value,) in library_paths
        if isinstance(value, str) and value and Path(value).expanduser().is_absolute()
    ]


def _validate_recovery_journal(rehearsal_root: Path, journal: Path, allowed_roots: list[Path]) -> None:
    payload = json.loads(journal.read_text(encoding="utf-8"))
    logical_name = journal.relative_to(rehearsal_root).as_posix()
    for raw_path in _validate_journal_payload(logical_name, payload):
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise BackupError(f"file-operation journal path is not absolute: {logical_name}")
        candidate = candidate.resolve()
        if not any(candidate == root or candidate.is_relative_to(root) for root in allowed_roots):
            raise BackupError(f"file-operation journal path is outside configured roots: {logical_name}")


def _extract_and_verify_database(
    bundle: zipfile.ZipFile,
    infos: list[zipfile.ZipInfo],
    rehearsal_root: Path,
    expected_files: dict[str, dict[str, object]],
    declared_sizes: dict[str, int],
) -> str:
    for info in infos:
        if info.filename != MANIFEST_ARCHIVE_PATH:
            _extract_entry(bundle, info, rehearsal_root, expected_files[info.filename], declared_sizes[info.filename])
    return _database_integrity(rehearsal_root / DATABASE_ARCHIVE_PATH)


def verify_state_backup(settings: Config, archive_name: str, *, output_name: str | None = None) -> dict[str, object]:
    """Extract into an isolated temporary directory and prove recovery invariants."""
    userdata_root = Path(settings.get_userdata_path()).expanduser().resolve()
    archive = _safe_owned_path(_owned_directory(userdata_root, "backups"), archive_name, ARCHIVE_NAME_PATTERN, "--archive")
    if not archive.is_file() or archive.is_symlink():
        raise BackupError("State backup archive is missing or is not a regular file")
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos, names, declared_sizes, temporary_root = _validate_archive_inventory(bundle)
            manifest = _read_manifest(bundle)
            expected_files = _validate_manifest_files(manifest, names, declared_sizes)
            with tempfile.TemporaryDirectory(prefix="compresso-recovery-rehearsal-", dir=temporary_root) as temporary:
                rehearsal_root = Path(temporary)
                database_integrity = _extract_and_verify_database(
                    bundle, infos, rehearsal_root, expected_files, declared_sizes
                )
                _validate_recovery_semantics(rehearsal_root, settings)
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise BackupError(f"Recovery rehearsal failed: {type(error).__name__}") from error

    report_name = output_name or f"state-rehearsal-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex}.json"
    report_path = _safe_owned_path(
        _owned_directory(userdata_root, "recovery-rehearsals"), report_name, REPORT_NAME_PATTERN, "--output"
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "overall_status": "pass",
        "verified_at": _timestamp(),
        "archive_name": archive.name,
        "archive_sha256": _sha256(archive),
        "files_verified": len(expected_files),
        "database_integrity": database_integrity,
    }
    _private_exclusive_json(report_path, report)
    report["report_path"] = str(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compresso state", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("backup", help="Create a private online control-plane backup")
    create_parser.add_argument("--output", required=True)
    rehearse_parser = subparsers.add_parser("rehearse", help="Verify a backup in an isolated temporary directory")
    rehearse_parser.add_argument("--archive", required=True)
    rehearse_parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        settings = Config()
        if args.command == "backup":
            result = create_state_backup(settings, args.output)
        else:
            result = verify_state_backup(settings, args.archive, output_name=args.output)
        sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return 0
    except BackupError as error:
        sys.stderr.write(json.dumps({"error": str(error), "type": "state-backup"}, sort_keys=True) + "\n")
        return 1
