#!/usr/bin/env python3

"""Shared crash-safe JSON persistence for installation-owned state."""

from __future__ import annotations

import errno
import json
import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path

_UNSUPPORTED_DIRECTORY_SYNC_ERRORS = {
    errno.EACCES,
    errno.EBADF,
    errno.EINVAL,
    getattr(errno, "ENOTSUP", errno.EINVAL),
}


def _fsync_parent_directory(parent: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(parent, flags)
    except OSError as exc:
        if os.name == "nt" or exc.errno in _UNSUPPORTED_DIRECTORY_SYNC_ERRORS:
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as exc:
            if exc.errno not in _UNSUPPORTED_DIRECTORY_SYNC_ERRORS:
                raise
    finally:
        os.close(descriptor)


def atomic_json_write(path: str | os.PathLike[str], payload: object, mode: int | None = None) -> None:
    """Durably replace one JSON document without exposing a partial write."""
    destination = Path(os.path.abspath(os.path.expanduser(os.fspath(path))))
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing_mode = None
    if mode is None and not destination.is_symlink():
        with suppress(OSError):
            existing_mode = stat.S_IMODE(destination.stat().st_mode)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}-",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        requested_mode = mode if mode is not None else existing_mode
        if requested_mode is not None:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, requested_mode)
            else:
                os.chmod(temporary, requested_mode)
        output = os.fdopen(descriptor, "w", encoding="utf-8")
        descriptor = -1
        with output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
        _fsync_parent_directory(destination.parent)
    finally:
        if descriptor >= 0:
            with suppress(OSError):
                os.close(descriptor)
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
