#!/usr/bin/env python3

"""Before/after media accounting for canaries and production batches."""

import hashlib
import json
import math
import ntpath
import os
import posixpath
import random
import subprocess
import time
from collections import Counter
from dataclasses import dataclass

from compresso.libs.json_state import atomic_json_write

MEDIA_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".ts",
    ".webm",
    ".wmv",
}
STREAM_TYPES = ("video", "audio", "subtitle", "data", "attachment")
HDR_FIELDS = ("color_primaries", "color_transfer", "color_space")


@dataclass(frozen=True)
class ManifestEntryPathTransition:
    path: str | None
    issues: tuple[str, ...]
    include_expected: bool


def _is_absolute_manifest_path(path):
    """Reject absolute paths using either supported host path syntax."""
    windows_drive, _ = ntpath.splitdrive(path)
    return bool(windows_drive) or ntpath.isabs(path) or posixpath.isabs(path)


def _manifest_entry_path_transition(root, relative_path, seen_relative_paths):
    """Validate and resolve one manifest path while tracking duplicates."""
    if not isinstance(relative_path, str) or not relative_path or _is_absolute_manifest_path(relative_path):
        return ManifestEntryPathTransition(None, ("manifest relative_path is invalid",), False)
    normalized_path = os.path.normpath(relative_path)
    if normalized_path in seen_relative_paths:
        return ManifestEntryPathTransition(None, ("manifest relative_path is duplicated",), False)
    seen_relative_paths.add(normalized_path)
    path = os.path.realpath(os.path.join(root, normalized_path))
    try:
        common_root = os.path.commonpath((root, path))
    except ValueError:
        common_root = None
    if common_root != root:
        return ManifestEntryPathTransition(path, ("manifest path escapes verification root",), True)
    return ManifestEntryPathTransition(path, (), True)


def _manifest_before_size(expected):
    try:
        return int(expected.get("size_bytes", 0))
    except (TypeError, ValueError):
        return 0


def _verify_manifest_entry(root, expected, seen_relative_paths):
    """Verify one manifest entry and return its stable report row and totals."""
    if not isinstance(expected, dict):
        expected = {}
    relative_path = expected.get("relative_path")
    before_size = _manifest_before_size(expected)
    transition = _manifest_entry_path_transition(root, relative_path, seen_relative_paths)
    issues = list(transition.issues)
    current_size = 0
    current_checksum = None
    path = transition.path
    if path is not None and not issues:
        if not os.path.isfile(path):
            issues.append("output file is missing")
        else:
            try:
                current_size = os.path.getsize(path)
                if current_size <= 0:
                    issues.append("output file is empty")
                current_media = probe_media(path)
                issues.extend(compare_media_summaries(expected.get("media", {}), current_media))
                current_checksum = _sha256(path)
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as error:
                issues.append(f"output probe failed: {error}")
    result = {
        "relative_path": relative_path,
        "passed": not issues,
        "issues": issues,
        "before_size_bytes": before_size,
        "after_size_bytes": current_size,
        "before_checksum": expected.get("checksum"),
        "after_checksum": current_checksum,
    }
    return result, before_size, current_size, transition.include_expected


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:  # NOSONAR - caller constrains paths to the selected media root
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _atomic_json_write(path, data):
    atomic_json_write(path, data, mode=0o600)


def probe_media(path):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_chapters",
        "-show_format",
        "-of",
        "json",
        "-i",
        path,
    ]
    result = subprocess.run(  # noqa: S603  # NOSONAR - fixed executable, argv list, and explicit input operand
        command, capture_output=True, text=True, check=True, timeout=120
    )
    probe = json.loads(result.stdout)
    streams = probe.get("streams", [])
    counts = Counter(stream.get("codec_type") for stream in streams)
    primary_video = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    try:
        duration = float(probe.get("format", {}).get("duration", 0) or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "streams": {stream_type: int(counts.get(stream_type, 0)) for stream_type in STREAM_TYPES},
        "chapters": len(probe.get("chapters", [])),
        "duration_seconds": duration,
        "video": {field: primary_video.get(field) for field in HDR_FIELDS},
    }


def compare_media_summaries(before, after):
    issues = []
    if not isinstance(before, dict):
        return ["manifest media summary is invalid"]
    if not isinstance(after, dict):
        return ["output media summary is invalid"]
    before_streams = before.get("streams", {})
    after_streams = after.get("streams", {})
    if not isinstance(before_streams, dict):
        return ["manifest stream summary is invalid"]
    if not isinstance(after_streams, dict):
        return ["output stream summary is invalid"]
    for stream_type in STREAM_TYPES:
        try:
            expected = int(before_streams.get(stream_type, 0))
            actual = int(after_streams.get(stream_type, 0))
        except (TypeError, ValueError, OverflowError):
            issues.append(f"{stream_type} stream count is invalid")
            continue
        if actual < expected:
            issues.append(f"{stream_type} streams decreased from {expected} to {actual}")
    try:
        expected_chapters = int(before.get("chapters", 0))
        actual_chapters = int(after.get("chapters", 0))
    except (TypeError, ValueError, OverflowError):
        issues.append("chapter count is invalid")
        expected_chapters = actual_chapters = 0
    if actual_chapters < expected_chapters:
        issues.append(f"chapters decreased from {expected_chapters} to {actual_chapters}")
    before_video = before.get("video", {})
    after_video = after.get("video", {})
    if not isinstance(before_video, dict) or not isinstance(after_video, dict):
        issues.append("video metadata summary is invalid")
        before_video = after_video = {}
    for field in HDR_FIELDS:
        expected = before_video.get(field)
        if expected and after_video.get(field) != expected:
            issues.append(f"{field} changed from {expected} to {after_video.get(field)}")
    try:
        before_duration = float(before.get("duration_seconds", 0) or 0)
        after_duration = float(after.get("duration_seconds", 0) or 0)
    except (TypeError, ValueError, OverflowError):
        issues.append("duration is invalid")
    else:
        if not math.isfinite(before_duration) or not math.isfinite(after_duration):
            issues.append("duration is not finite")
        else:
            tolerance = max(1.0, before_duration * 0.01)
            if before_duration and abs(before_duration - after_duration) > tolerance:
                issues.append(f"duration changed from {before_duration:.3f}s to {after_duration:.3f}s")
    return issues


def _media_files(root):
    paths = []
    walk_errors = []
    for directory, subdirectories, filenames in os.walk(root, onerror=walk_errors.append):
        for subdirectory in subdirectories:
            path = os.path.join(directory, subdirectory)
            if os.path.islink(path):
                raise ValueError(f"media manifest refuses symbolic-link directory: {path}")
        subdirectories.sort()
        for filename in sorted(filenames):
            if os.path.splitext(filename)[1].lower() in MEDIA_EXTENSIONS:
                path = os.path.join(directory, filename)
                if os.path.islink(path):
                    raise ValueError(f"media manifest refuses symbolic-link input: {path}")
                paths.append(path)
    if walk_errors:
        raise OSError(f"media manifest could not read {len(walk_errors)} director{'y' if len(walk_errors) == 1 else 'ies'}")
    return paths


def create_manifest(root, output_path, sample_size=None, seed=20):
    root = os.path.abspath(root)
    if os.path.islink(root):
        raise ValueError("media root must not be a symbolic link")
    if not os.path.isdir(root):
        raise ValueError("media root must be an existing directory")
    if sample_size is not None and int(sample_size) <= 0:
        raise ValueError("sample size must be greater than zero")
    paths = _media_files(root)
    if not paths:
        raise ValueError("media root contains no supported media files")
    if sample_size is not None and int(sample_size) < len(paths):
        paths = sorted(
            random.Random(seed).sample(paths, max(0, int(sample_size)))  # noqa: S311  # NOSONAR
        )  # deterministic sampling, not a security decision
    files = []
    for path in paths:
        files.append(
            {
                "relative_path": os.path.relpath(path, root),
                "size_bytes": os.path.getsize(path),
                "checksum": _sha256(path),
                "media": probe_media(path),
            }
        )
    manifest = {"version": 1, "created_at": time.time(), "root": root, "files": files}
    _atomic_json_write(output_path, manifest)
    return manifest


def verify_manifest(manifest_path, current_root=None, report_path=None):
    with open(manifest_path, encoding="utf-8") as source:
        manifest = json.load(source)
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    root_value = current_root or manifest.get("root")
    if not isinstance(root_value, (str, os.PathLike)) or not os.fspath(root_value):
        raise ValueError("manifest root is invalid")
    root = os.path.realpath(root_value)
    if not os.path.isdir(root):
        raise ValueError("verification root must be an existing directory")
    results = []
    total_before = 0
    total_after = 0
    manifest_files = manifest.get("files")
    if manifest.get("version") != 1:
        results.append(
            {
                "relative_path": None,
                "passed": False,
                "issues": ["manifest version is unsupported"],
                "before_size_bytes": 0,
                "after_size_bytes": 0,
                "before_checksum": None,
                "after_checksum": None,
            }
        )
    if not isinstance(manifest_files, list) or not manifest_files:
        manifest_files = []
        results.append(
            {
                "relative_path": None,
                "passed": False,
                "issues": ["manifest contains no files"],
                "before_size_bytes": 0,
                "after_size_bytes": 0,
                "before_checksum": None,
                "after_checksum": None,
            }
        )
    seen_relative_paths = set()
    expected_relative_paths = set()
    for expected in manifest_files:
        result, before_size, current_size, include_expected = _verify_manifest_entry(
            root,
            expected,
            seen_relative_paths,
        )
        total_before += before_size
        total_after += current_size
        if include_expected:
            expected_relative_paths.add(os.path.normpath(result["relative_path"]))
        results.append(result)
    try:
        current_relative_paths = {os.path.relpath(path, root) for path in _media_files(root)}
    except (OSError, ValueError) as error:
        results.append(
            {
                "relative_path": None,
                "passed": False,
                "issues": [f"output inventory failed: {error}"],
                "before_size_bytes": 0,
                "after_size_bytes": 0,
                "before_checksum": None,
                "after_checksum": None,
            }
        )
    else:
        for unexpected in sorted(current_relative_paths - expected_relative_paths):
            results.append(
                {
                    "relative_path": unexpected,
                    "passed": False,
                    "issues": ["unexpected output file is not present in the manifest"],
                    "before_size_bytes": 0,
                    "after_size_bytes": os.path.getsize(os.path.join(root, unexpected)),
                    "before_checksum": None,
                    "after_checksum": None,
                }
            )
    failed = sum(not result["passed"] for result in results)
    report = {
        "version": 1,
        "verified_at": time.time(),
        "manifest": os.path.abspath(manifest_path),
        "root": root,
        "total": len(results),
        "passed": len(results) - failed,
        "failed": failed,
        "before_size_bytes": total_before,
        "after_size_bytes": total_after,
        "saved_bytes": total_before - total_after,
        "files": results,
    }
    if report_path:
        _atomic_json_write(report_path, report)
    return report
