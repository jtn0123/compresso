#!/usr/bin/env python3

"""
compresso.common.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     06 Dec 2018, (7:21 AM)

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
       EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
       MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
       IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
       DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
       OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
       OR OTHER DEALINGS IN THE SOFTWARE.

"""

import copy
import datetime
import hashlib
import os
import random
import shutil
import string
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import BinaryIO, TypedDict

import xxhash

from compresso.libs.json_state import atomic_json_write
from compresso.libs.logs import CompressoLogging

logger = CompressoLogging.get_logger("common")

type PathLike = str | os.PathLike[str]


class JsonWriteResult(TypedDict):
    errors: list[str]
    success: bool


@dataclass(frozen=True)
class _FingerprintAlgorithm:
    sample_size: int | None
    sample_count: int | None
    full_hash_limit: int
    fallback_algo: str | None = None


def get_home_dir() -> str:
    # Attempt to get the HOME_DIR environment variable
    home_dir = os.environ.get("HOME_DIR")
    # If HOME_DIR is unset/empty, expand ~; otherwise resolve tilde and relative paths to absolute.
    home_dir = os.path.expanduser("~") if not home_dir else os.path.abspath(os.path.expanduser(home_dir))
    return home_dir


def get_default_root_path() -> str:
    root = os.path.join(os.sep)
    if os.name == "nt":
        root = os.path.join("c:", os.sep)
    return root


def get_default_library_path() -> str:
    library_path = os.path.join(get_default_root_path(), "library")
    if sys.platform == "darwin":
        library_path = os.path.join(os.path.expanduser("~"), "Movies")
    elif os.name == "nt":
        library_path = os.path.join(os.path.expandvars(r"%USERPROFILE%"), "Documents")
    return library_path


def get_default_cache_path() -> str:
    cache_path = os.path.join(get_default_root_path(), "tmp", "compresso")
    if sys.platform == "darwin":
        cache_path = os.path.join(os.path.expanduser("~"), "Library", "Caches", "Compresso")
    elif os.name == "nt":
        cache_path = os.path.join(os.path.expandvars(r"%LOCALAPPDATA%\Temp"), "Compresso")
    return cache_path


def format_message(message: object, message2: object = "") -> str:
    message = str(message)
    if message2:
        # Message2 can support other objects:
        if isinstance(message2, str):
            message = f"{message} - {str(message2)}"
        elif isinstance(message2, (dict, list)):
            import pprint

            message2 = pprint.pformat(message2, indent=1)
            message = f"{message} \n{str(message2)}"
        else:
            message = f"{message} - {str(message2)}"
    message = f"[FORMATTED] - {message}"
    return message


def make_timestamp_human_readable(ts: float) -> str:
    """
    Accept a unix timestamp, return a human readable timedelta string.

    :param ts: a datetime, timedelta, or timestamp (integer / float) object
    :returns: Human readable timedelta string (Str)
    """
    units = ("year", "day", "hour", "minute", "second", "millisecond", "microsecond")
    precision = 1
    past_tense = "{} ago"
    future_tense = "in {}"

    # Get datetime from ts string
    dt = datetime.datetime.fromtimestamp(ts)
    delta = datetime.datetime.now(tz=dt.tzinfo) - dt

    # Determine if this is past or future tense
    the_tense = future_tense if delta < datetime.timedelta(0) else past_tense

    # Create a dictionary of units
    delta = abs(delta)
    d = {
        "year": int(delta.days / 365),
        "day": int(delta.days % 365),
        "hour": int(delta.seconds / 3600),
        "minute": int(delta.seconds / 60) % 60,
        "second": delta.seconds % 60,
        "millisecond": delta.microseconds / 1000,
        "microsecond": delta.microseconds % 1000,
    }

    human_readable_list = []
    count = 0

    # Start building up the output in the human readable list.
    for unit in units:
        if count >= precision:
            break  # met precision
        if d[unit] == 0:
            continue  # skip 0's
        else:
            s = "" if d[unit] == 1 else "s"  # handle plurals
            human_readable_list.append(f"{d[unit]} {unit}{s}")
        count += 1

    return the_tense.format(", ".join(human_readable_list))


def ensure_dir(file_path: PathLike) -> None:
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)


def time_string_to_seconds(time_string: str) -> int:
    pt = datetime.datetime.strptime(time_string, "%H:%M:%S.%f")
    return pt.second + pt.minute * 60 + pt.hour * 3600


def tail(f: BinaryIO, n: int, offset: int = 0) -> list[bytes]:
    """Reads a n lines from f with an offset of offset lines."""
    avg_line_length = 153
    to_read = n + offset
    while 1:
        try:
            f.seek(-(avg_line_length * to_read), 2)
            while f.read(1) != b"\n":
                f.seek(-2, os.SEEK_CUR)
        except OSError:
            f.seek(0)
        pos = f.tell()
        lines = f.read().splitlines()
        if len(lines) >= to_read or pos == 0:
            return lines
        avg_line_length = int(avg_line_length * 1.3)


def touch(
    fname: PathLike,
    mode: int = 0o666,
    dir_fd: int | None = None,
    *,
    times: tuple[float, float] | None = None,
    ns: tuple[int, int] | None = None,
    follow_symlinks: bool = True,
) -> None:
    """Touch a file. If it does not exist, create it."""
    flags = os.O_CREAT | os.O_APPEND
    with os.fdopen(os.open(fname, flags=flags, mode=mode, dir_fd=dir_fd)) as f:
        target = f.fileno() if os.utime in os.supports_fd else fname
        target_dir_fd = None if os.utime in os.supports_fd else dir_fd
        if ns is not None:
            os.utime(target, ns=ns, dir_fd=target_dir_fd, follow_symlinks=follow_symlinks)
        else:
            os.utime(target, times=times, dir_fd=target_dir_fd, follow_symlinks=follow_symlinks)


def clean_files_in_cache_dir(cache_directory: PathLike, protected_paths: Sequence[PathLike] | None = None) -> None:
    """Remove abandoned task cache directories while retaining active files."""
    protected_paths = [os.path.realpath(path) for path in (protected_paths or []) if path]

    if not os.path.exists(cache_directory):
        return
    for root, _subfolders, _files in os.walk(cache_directory):
        root_name = os.path.basename(root)
        if root_name.startswith("compresso_file_conversion-"):
            _clean_cache_path(root, protected_paths, "active cache", "cache")
        elif root_name.startswith("compresso_remote_pending_library-"):
            _clean_cache_path(root, protected_paths, "active remote cache", "remote library cache")


def _clean_cache_path(root: str, protected_paths: Sequence[PathLike], preserve_label: str, clear_label: str) -> None:
    if _contains_protected_path(root, protected_paths):
        logger.info("Preserving %s path - %s", preserve_label, root)
        return
    try:
        logger.info("Clearing %s path - %s", clear_label, root)
        shutil.rmtree(root)
    except Exception:
        logger.exception("Exception while clearing %s path - %s", clear_label, root)


def _contains_protected_path(directory: PathLike, protected_paths: Sequence[PathLike]) -> bool:
    directory = os.path.realpath(directory)
    for path in protected_paths:
        try:
            if os.path.commonpath([directory, path]) == directory:
                return True
        except ValueError:
            continue
    return False


def random_string(string_length: int = 5) -> str:
    """Generate a random string of fixed length"""
    letters = string.ascii_lowercase
    return "".join(random.choice(letters) for i in range(string_length))  # noqa: S311 — not used for security/crypto


def json_dump_to_file(
    json_data: object,
    out_file: PathLike,
    check: bool = True,
    file_mode: int | None = None,
) -> JsonWriteResult:
    """Compatibility wrapper for atomically writing a JSON document.

    Atomic replacement ensures a failed write cannot leave a partial document.
    """
    import json

    result = JsonWriteResult(errors=[], success=False)
    try:
        atomic_json_write(out_file, json_data, mode=file_mode)
        if check:
            with open(out_file, encoding="utf-8") as infile:
                json.load(infile)
    except Exception as e:
        result["errors"].append(f"Exception in writing to file: {str(e)}")
        return result

    result["success"] = True
    return result


def extract_video_codecs_from_file_properties(file_properties: dict[str, object]) -> list[str]:
    """
    Read a dictionary of file properties
    Extract a list of video codecs from the video streams

    :param file_properties:
    :return:
    """
    codecs: list[str] = []
    streams = file_properties.get("streams")
    if not isinstance(streams, list):
        return codecs
    for stream in streams:
        if not isinstance(stream, dict) or stream.get("codec_type") != "video":
            continue
        codec_name = stream.get("codec_name")
        if isinstance(codec_name, str):
            codecs.append(codec_name)
    return codecs


def get_file_checksum(path: PathLike) -> str:
    """
    Read a checksum of a file.

    Rather than opening the whole file in memory, open it in chunks.
    This is slightly slower, but allows working on systems with limited memory.

    :param path:
    :return:
    """
    file_hash = hashlib.md5()  # noqa: S324 — used for file fingerprinting, not security
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            file_hash.update(chunk)
    return copy.copy(file_hash.hexdigest())


def get_file_fingerprint(path: PathLike, algo: str = "sampled_xxhash_v1") -> tuple[str, str]:
    """
    Create a content-based fingerprint for a file.

    Returns a tuple: (fingerprint, algo_used)

    Supported algos:
        - "sampled_sha256_v1"
        - "full_sha256_v1"
        - "sampled_xxhash_v1"
        - "full_xxhash_v1"

    :param path:
    :param algo:
    :return:
    """
    algos: dict[str, _FingerprintAlgorithm] = {
        "sampled_sha256_v1": _FingerprintAlgorithm(
            sample_size=8 * 1024 * 1024,
            sample_count=10,
            full_hash_limit=100 * 1024 * 1024,
            fallback_algo="full_sha256_v1",
        ),
        "full_sha256_v1": _FingerprintAlgorithm(sample_size=None, sample_count=None, full_hash_limit=0),
        "sampled_xxhash_v1": _FingerprintAlgorithm(
            sample_size=8 * 1024 * 1024,
            sample_count=10,
            full_hash_limit=100 * 1024 * 1024,
            fallback_algo="full_xxhash_v1",
        ),
        "full_xxhash_v1": _FingerprintAlgorithm(sample_size=None, sample_count=None, full_hash_limit=0),
    }

    if algo not in algos:
        algo = "sampled_xxhash_v1"

    file_size = os.path.getsize(path)

    actual_algo_to_use = algo

    algorithm = algos[algo]
    if algo in ["sampled_sha256_v1", "sampled_xxhash_v1"] and file_size <= algorithm.full_hash_limit:
        actual_algo_to_use = algorithm.fallback_algo or algo

    file_hash_obj = xxhash.xxh64() if actual_algo_to_use in ["full_xxhash_v1", "sampled_xxhash_v1"] else hashlib.sha256()

    file_hash_obj.update(str(file_size).encode("utf-8"))

    perform_full_hash = False
    if actual_algo_to_use in ["full_sha256_v1", "full_xxhash_v1"]:
        perform_full_hash = True

    if perform_full_hash:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                file_hash_obj.update(chunk)
        return file_hash_obj.hexdigest(), actual_algo_to_use

    selected_algorithm = algos[actual_algo_to_use]
    sample_size = selected_algorithm.sample_size
    sample_count = selected_algorithm.sample_count
    if sample_size is None or sample_count is None:
        raise RuntimeError(f"Sampled fingerprint algorithm {actual_algo_to_use!r} is incomplete")
    max_offset = max(0, file_size - sample_size)
    if sample_count < 2:
        sample_count = 2

    # Generate evenly spaced offsets including first and last positions.
    offsets = []
    for i in range(sample_count):
        offset = int((max_offset * i) / (sample_count - 1))
        offsets.append(offset)

    # De-duplicate offsets for small-ish files and read samples.
    offsets = sorted(set(offsets))
    with open(path, "rb") as f:
        for offset in offsets:
            f.seek(offset)
            file_hash_obj.update(f.read(sample_size))

    return file_hash_obj.hexdigest(), actual_algo_to_use
