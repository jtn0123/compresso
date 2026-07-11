#!/usr/bin/env python3

"""Fail closed when a release candidate's source and package versions disagree."""

import argparse
import email.parser
import re
import sys
import tarfile
import zipfile
from pathlib import Path

VERSION_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}(?:-[0-9A-Za-z.-]+)?$")


def read_wheel_version(wheel_path):
    with zipfile.ZipFile(wheel_path) as wheel:
        metadata_paths = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise ValueError(f"Expected one wheel METADATA file, found {len(metadata_paths)}")
        metadata = email.parser.Parser().parsestr(wheel.read(metadata_paths[0]).decode("utf-8"))
    return metadata.get("Version")


def read_sdist_version(sdist_path):
    with tarfile.open(sdist_path, "r:gz") as archive:
        metadata_members = [
            member for member in archive.getmembers() if member.name.count("/") == 1 and member.name.endswith("/PKG-INFO")
        ]
        if len(metadata_members) != 1:
            raise ValueError(f"Expected one top-level sdist PKG-INFO, found {len(metadata_members)}")
        source = archive.extractfile(metadata_members[0])
        if source is None:
            raise ValueError("Unable to read sdist PKG-INFO")
        metadata = email.parser.Parser().parsestr(source.read().decode("utf-8"))
    return metadata.get("Version")


def verify_release(repo_root, expected_version, expected_sha, actual_sha, dist_dir=None, notes_file=None):
    if not VERSION_PATTERN.fullmatch(expected_version):
        raise ValueError(f"Invalid expected version: {expected_version}")

    repo_root = Path(repo_root).resolve()
    if actual_sha != expected_sha:
        raise ValueError(f"Release SHA mismatch: expected {expected_sha}, got {actual_sha}")

    source_version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    if source_version != expected_version:
        raise ValueError(f"VERSION mismatch: expected {expected_version}, got {source_version}")

    if notes_file is not None and not Path(notes_file).read_text(encoding="utf-8").strip():
        raise ValueError("Release notes are empty")

    if dist_dir is not None:
        dist_dir = Path(dist_dir)
        wheels = sorted(dist_dir.glob("*.whl"))
        sdists = sorted(dist_dir.glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise ValueError(f"Expected one wheel and one sdist, found {len(wheels)} wheel(s) and {len(sdists)} sdist(s)")
        artifact_versions = {
            "wheel": read_wheel_version(wheels[0]),
            "sdist": read_sdist_version(sdists[0]),
        }
        mismatches = {kind: version for kind, version in artifact_versions.items() if version != expected_version}
        if mismatches:
            raise ValueError(f"Artifact version mismatch: expected {expected_version}, got {mismatches}")

    return {"version": expected_version, "sha": actual_sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--actual-sha", required=True)
    parser.add_argument("--dist-dir")
    parser.add_argument("--notes-file")
    args = parser.parse_args()
    result = verify_release(
        args.repo_root,
        args.expected_version,
        args.expected_sha,
        args.actual_sha,
        dist_dir=args.dist_dir,
        notes_file=args.notes_file,
    )
    sys.stdout.write(f"release integrity verified: version={result['version']} sha={result['sha']}\n")


if __name__ == "__main__":
    main()
