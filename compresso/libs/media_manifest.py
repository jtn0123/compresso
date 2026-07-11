#!/usr/bin/env python3

"""Before/after media accounting for canaries and production batches."""

import hashlib
import json
import ntpath
import os
import posixpath
import random
import subprocess
import tempfile
import time
from collections import Counter

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


def _is_absolute_manifest_path(path):
    """Reject absolute paths using either supported host path syntax."""
    windows_drive, _ = ntpath.splitdrive(path)
    return bool(windows_drive) or ntpath.isabs(path) or posixpath.isabs(path)


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:  # NOSONAR - caller constrains paths to the selected media root
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _atomic_json_write(path, data):
    destination = os.path.abspath(path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=os.path.dirname(destination))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, indent=2, sort_keys=True)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


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
    before_streams = before.get("streams", {})
    after_streams = after.get("streams", {})
    for stream_type in STREAM_TYPES:
        expected = int(before_streams.get(stream_type, 0))
        actual = int(after_streams.get(stream_type, 0))
        if actual < expected:
            issues.append(f"{stream_type} streams decreased from {expected} to {actual}")
    expected_chapters = int(before.get("chapters", 0))
    actual_chapters = int(after.get("chapters", 0))
    if actual_chapters < expected_chapters:
        issues.append(f"chapters decreased from {expected_chapters} to {actual_chapters}")
    before_video = before.get("video", {})
    after_video = after.get("video", {})
    for field in HDR_FIELDS:
        expected = before_video.get(field)
        if expected and after_video.get(field) != expected:
            issues.append(f"{field} changed from {expected} to {after_video.get(field)}")
    before_duration = float(before.get("duration_seconds", 0) or 0)
    after_duration = float(after.get("duration_seconds", 0) or 0)
    tolerance = max(1.0, before_duration * 0.01)
    if before_duration and abs(before_duration - after_duration) > tolerance:
        issues.append(f"duration changed from {before_duration:.3f}s to {after_duration:.3f}s")
    return issues


def _media_files(root):
    paths = []
    for directory, subdirectories, filenames in os.walk(root):
        subdirectories.sort()
        for filename in sorted(filenames):
            if os.path.splitext(filename)[1].lower() in MEDIA_EXTENSIONS:
                paths.append(os.path.join(directory, filename))
    return paths


def create_manifest(root, output_path, sample_size=None, seed=20):
    root = os.path.abspath(root)
    if sample_size is not None and int(sample_size) <= 0:
        raise ValueError("sample size must be greater than zero")
    paths = _media_files(root)
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
    root = os.path.realpath(current_root or manifest["root"])
    results = []
    total_before = 0
    total_after = 0
    manifest_files = manifest.get("files")
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
    for expected in manifest_files:
        if not isinstance(expected, dict):
            expected = {}
        relative_path = expected.get("relative_path")
        try:
            before_size = int(expected.get("size_bytes", 0))
        except (TypeError, ValueError):
            before_size = 0
        total_before += before_size
        issues = []
        current_size = 0
        current_checksum = None
        if not isinstance(relative_path, str) or not relative_path or _is_absolute_manifest_path(relative_path):
            path = None
            issues.append("manifest relative_path is invalid")
        else:
            path = os.path.realpath(os.path.join(root, relative_path))
        if path is not None and os.path.commonpath((root, path)) != root:
            issues.append("manifest path escapes verification root")
        elif path is not None and not os.path.isfile(path):
            issues.append("output file is missing")
        elif path is not None:
            current_size = os.path.getsize(path)
            total_after += current_size
            if current_size <= 0:
                issues.append("output file is empty")
            try:
                current_media = probe_media(path)
                issues.extend(compare_media_summaries(expected.get("media", {}), current_media))
                current_checksum = _sha256(path)
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError) as error:
                issues.append(f"output probe failed: {error}")
        results.append(
            {
                "relative_path": relative_path,
                "passed": not issues,
                "issues": issues,
                "before_size_bytes": before_size,
                "after_size_bytes": current_size,
                "before_checksum": expected.get("checksum"),
                "after_checksum": current_checksum,
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
