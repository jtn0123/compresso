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
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from compresso.config import Config

SCHEMA_VERSION = 1
ARCHIVE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.zip")
REPORT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.json")
MAX_ARCHIVE_ENTRIES = 2_000
MAX_UNCOMPRESSED_BYTES = 32 * 1024**3
MAX_MANIFEST_BYTES = 4 * 1024**2


class BackupError(RuntimeError):
    """A state backup or rehearsal failed a safety invariant."""


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


def _private_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _database_integrity(path: Path) -> str:
    uri = f"file:{quote(path.as_posix(), safe='/')}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=10) as connection:
            rows = connection.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.Error as error:
        raise BackupError(f"SQLite integrity check failed: {type(error).__name__}") from error
    if rows != [("ok",)]:
        raise BackupError("SQLite integrity check did not return ok")
    return "ok"


def _snapshot_database(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BackupError("Compresso database is missing")
    source_uri = f"file:{quote(source.as_posix(), safe='/')}?mode=ro"
    try:
        with (
            sqlite3.connect(source_uri, uri=True, timeout=10) as source_connection,
            sqlite3.connect(destination) as destination_connection,
        ):
            source_connection.backup(destination_connection)
        _database_integrity(destination)
    except (sqlite3.Error, BackupError) as error:
        destination.unlink(missing_ok=True)
        if isinstance(error, BackupError) and str(error).startswith("SQLite integrity"):
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


def _write_archive(destination: Path, files: list[tuple[str, Path]], generated_at: str) -> dict[str, Any]:
    manifest_files = {
        logical_name: {"sha256": _sha256(source), "size_bytes": source.stat().st_size} for logical_name, source in files
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "compresso-control-plane-backup",
        "generated_at": generated_at,
        "files": manifest_files,
    }
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = destination.with_suffix(f".{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w+b") as archive_file:
            with zipfile.ZipFile(archive_file, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
                for logical_name, source in files:
                    bundle.write(source, logical_name)
                bundle.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            archive_file.flush()
            os.fsync(archive_file.fileno())
        os.replace(temporary, destination)
        if os.name != "nt":
            os.chmod(destination, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest


def create_state_backup(settings: Any, output_name: str) -> dict[str, Any]:
    """Create an online SQLite snapshot plus small recovery evidence files."""
    config_root = Path(settings.get_config_path()).expanduser().resolve()
    userdata_root = Path(settings.get_userdata_path()).expanduser().resolve()
    destination = _safe_owned_path(_owned_directory(userdata_root, "backups"), output_name, ARCHIVE_NAME_PATTERN, "--output")
    if destination.exists():
        raise BackupError("Refusing to overwrite an existing state backup")
    with tempfile.TemporaryDirectory(prefix=".state-backup-", dir=destination.parent) as temporary:
        snapshot = Path(temporary) / "compresso.db"
        _snapshot_database(config_root / "compresso.db", snapshot)
        files: list[tuple[str, Path]] = [("config/compresso.db", snapshot)]
        settings_file = config_root / "settings.json"
        if settings_file.is_symlink():
            raise BackupError("Refusing to back up a symbolic-link settings file")
        if settings_file.is_file() and not settings_file.is_symlink():
            files.append(("config/settings.json", settings_file))
        files.extend(_journal_files(config_root))
        files.extend(_evidence_files(userdata_root))
        if len(files) > MAX_ARCHIVE_ENTRIES:
            raise BackupError("Control-plane backup contains too many files")
        manifest = _write_archive(destination, files, _timestamp())
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
        info.filename == "manifest.json"
        or info.filename in {"config/compresso.db", "config/settings.json"}
        or (len(path.parts) == 4 and path.parts[:3] == ("config", "recovery", "file_operations"))
        or (len(path.parts) == 3 and path.parts[0] == "userdata" and path.parts[1] in {"safety", "readiness", "planning"})
    )
    if not allowed or (info.filename != "config/compresso.db" and not info.filename.endswith(".json")):
        raise BackupError(f"unexpected archive entry: {info.filename}")


def _copy_and_hash(source, destination: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as output:
        while chunk := source.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest(), size


def verify_state_backup(settings: Any, archive_name: str, *, output_name: str | None = None) -> dict[str, Any]:
    """Extract into an isolated temporary directory and prove recovery invariants."""
    userdata_root = Path(settings.get_userdata_path()).expanduser().resolve()
    archive = _safe_owned_path(_owned_directory(userdata_root, "backups"), archive_name, ARCHIVE_NAME_PATTERN, "--archive")
    if not archive.is_file() or archive.is_symlink():
        raise BackupError("State backup archive is missing or is not a regular file")
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise BackupError("duplicate archive entry detected")
            if len(infos) > MAX_ARCHIVE_ENTRIES + 1:
                raise BackupError("archive contains too many entries")
            uncompressed_bytes = sum(info.file_size for info in infos)
            if uncompressed_bytes > MAX_UNCOMPRESSED_BYTES:
                raise BackupError("archive expands beyond the rehearsal safety limit")
            temporary_root = Path(tempfile.gettempdir()).resolve()
            if shutil.disk_usage(temporary_root).free < uncompressed_bytes + 512 * 1024**2:
                raise BackupError("Insufficient temporary disk space for recovery rehearsal")
            for info in infos:
                _validate_entry(info)
            if "manifest.json" not in names:
                raise BackupError("archive manifest is missing")
            manifest_info = bundle.getinfo("manifest.json")
            if manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise BackupError("archive manifest is too large")
            manifest = json.loads(bundle.read("manifest.json"))
            if (
                not isinstance(manifest, dict)
                or manifest.get("schema_version") != SCHEMA_VERSION
                or manifest.get("kind") != "compresso-control-plane-backup"
                or not isinstance(manifest.get("files"), dict)
            ):
                raise BackupError("archive manifest is invalid")
            expected_files = manifest["files"]
            if set(expected_files) != set(names) - {"manifest.json"}:
                raise BackupError("archive entries do not match the manifest")
            for logical_name, metadata in expected_files.items():
                if (
                    not isinstance(logical_name, str)
                    or not isinstance(metadata, dict)
                    or re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("sha256", ""))) is None
                    or not isinstance(metadata.get("size_bytes"), int)
                    or metadata["size_bytes"] < 0
                ):
                    raise BackupError("archive manifest contains invalid file metadata")
            with tempfile.TemporaryDirectory(prefix="compresso-recovery-rehearsal-", dir=temporary_root) as temporary:
                rehearsal_root = Path(temporary)
                for info in infos:
                    if info.filename == "manifest.json":
                        continue
                    destination = rehearsal_root.joinpath(*PurePosixPath(info.filename).parts).resolve()
                    if not destination.is_relative_to(rehearsal_root):
                        raise BackupError(f"unsafe archive destination: {info.filename}")
                    with bundle.open(info) as source:
                        digest, size = _copy_and_hash(source, destination)
                    expected = expected_files[info.filename]
                    if digest != expected.get("sha256") or size != expected.get("size_bytes"):
                        raise BackupError(f"checksum mismatch for {info.filename}")
                    if info.filename.endswith(".json"):
                        json.loads(destination.read_text(encoding="utf-8"))
                database_integrity = _database_integrity(rehearsal_root / "config" / "compresso.db")
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise BackupError(f"Recovery rehearsal failed: {type(error).__name__}") from error

    report_name = output_name or f"state-rehearsal-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
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
    _private_atomic_json(report_path, report)
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
