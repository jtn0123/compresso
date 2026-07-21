#!/usr/bin/env python3

"""
compresso.startup.py

Deployment-oriented startup validation and readiness state helpers.

"""

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import TypedDict

from compresso.config import Config
from compresso.libs.singleton import SingletonType

logger = logging.getLogger("compresso.startup")


class FFmpegInfo(TypedDict):
    ffmpeg: str | None
    ffprobe: str | None
    version: str | None


class StartupState(metaclass=SingletonType):
    REQUIRED_STAGES = (
        "config_loaded",
        "startup_validation",
        "db_ready",
        "threads_ready",
        "ui_server_ready",
    )

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._stages: dict[str, bool] = dict.fromkeys(self.REQUIRED_STAGES, False)
            self._details: dict[str, object] = {}
            self._errors: list[dict[str, str]] = []

    def mark_ready(self, stage: str, detail: object = None) -> None:
        with self._lock:
            self._stages[stage] = True
            if detail is not None:
                self._details[stage] = detail

    def mark_error(self, stage: str, message: object) -> None:
        with self._lock:
            self._stages[stage] = False
            self._details[stage] = message
            self._errors.append(
                {
                    "stage": stage,
                    "message": str(message),
                }
            )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            stages = dict(self._stages)
            details = dict(self._details)
            errors = list(self._errors)
        return {
            "ready": all(stages.get(stage, False) for stage in self.REQUIRED_STAGES),
            "stages": stages,
            "details": details,
            "errors": errors,
        }


def _ensure_writable_dir(path: str | None, label: str, create: bool = False) -> None:
    if not path:
        raise RuntimeError(f"{label} is not configured")

    if create:
        os.makedirs(path, exist_ok=True)

    if not os.path.isdir(path):
        raise RuntimeError(f"{label} '{path}' is not a directory")

    if not os.access(path, os.W_OK):
        raise RuntimeError(f"{label} '{path}' is not writable")

    fd, tmp_path = tempfile.mkstemp(prefix="compresso-startup-", dir=path)
    os.close(fd)
    os.unlink(tmp_path)


def _ensure_readable_dir(path: str | None, label: str) -> None:
    if not path:
        raise RuntimeError(f"{label} is not configured")
    if not os.path.isdir(path):
        raise RuntimeError(f"{label} '{path}' does not exist")
    if not os.access(path, os.R_OK | os.X_OK):
        raise RuntimeError(f"{label} '{path}' is not readable")


def _validate_cache_path(cache_path: str | None, config_path: str, library_path: str) -> None:
    if not cache_path:
        raise RuntimeError("cache path is not configured")

    normalized = os.path.abspath(cache_path)
    invalid_roots = {os.path.abspath(os.sep)}
    if os.name == "nt":
        invalid_roots.add(os.path.abspath(os.path.splitdrive(normalized)[0] + os.sep))
    if normalized in invalid_roots:
        raise RuntimeError(f"cache path '{cache_path}' is invalid")

    if normalized == os.path.abspath(config_path):
        raise RuntimeError(f"cache path '{cache_path}' must not equal config path")
    if normalized == os.path.abspath(library_path):
        raise RuntimeError(f"cache path '{cache_path}' must not equal library path")


def _validate_ffmpeg() -> FFmpegInfo:
    """
    Check that ffmpeg and ffprobe are available on PATH.
    Returns a dict with paths and version info. Logs warnings if missing.
    """
    result = FFmpegInfo(ffmpeg=None, ffprobe=None, version=None)

    result["ffmpeg"] = shutil.which("ffmpeg")
    result["ffprobe"] = shutil.which("ffprobe")

    if not result["ffmpeg"] or not result["ffprobe"]:
        missing = [k for k in ("ffmpeg", "ffprobe") if not result[k]]
        if sys.platform == "darwin":
            hint = "Install with: brew install ffmpeg"
        elif os.name == "nt":
            hint = "Install with: winget install ffmpeg  (or choco install ffmpeg)"
        else:
            hint = "Install with: apt install ffmpeg  (or dnf install ffmpeg)"
        logger.warning("Missing required tools: %s. %s", ", ".join(missing), hint)
        return result

    try:
        proc = subprocess.run(
            ["ffmpeg", "-version"],  # noqa: S607 - ffmpeg resolved from PATH
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0 and proc.stdout:
            first_line = proc.stdout.strip().split("\n")[0]
            result["version"] = first_line
            logger.info("FFmpeg found: %s", first_line)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.warning("FFmpeg found on PATH but version check failed: %s", e)

    return result


def validate_startup_environment(settings: Config) -> None:
    config_path = settings.get_config_path()
    library_path = settings.get_library_path()
    cache_path = settings.get_cache_path()

    _ensure_writable_dir(config_path, "config path", create=True)
    _ensure_readable_dir(library_path, "library path")
    _validate_cache_path(cache_path, config_path, library_path)
    _ensure_writable_dir(cache_path, "cache path", create=True)


def _sum_worker_groups_count() -> int:
    """Sum ``number_of_workers`` across all configured worker groups.

    Imported lazily so this module stays import-free of peewee for
    callers that only need the readiness helpers above. The body is
    wrapped in a broad try so the startup summary still renders if
    the worker-group DB isn't queryable yet (e.g. mid-migration or
    transient lock).
    """
    try:
        from compresso.libs.worker_group import WorkerGroup

        total = 0
        for wg in WorkerGroup.get_all_worker_groups():
            total += int(wg.get("number_of_workers", 0) or 0)
        return total
    except Exception:
        return 0


def build_startup_summary(settings: Config, event_monitor_module: object) -> dict[str, object]:
    ffmpeg_info = _validate_ffmpeg()
    return {
        "library_path": settings.get_library_path(),
        "cache_path": settings.get_cache_path(),
        "config_path": settings.get_config_path(),
        "enable_library_scanner": settings.get_enable_library_scanner(),
        "run_full_scan_on_start": settings.get_run_full_scan_on_start(),
        "concurrent_file_testers": settings.get_concurrent_file_testers(),
        # v2.0: workers are per-group, not a top-level setting. Sum across
        # configured worker groups for the startup-summary metric.
        "worker_count": _sum_worker_groups_count(),
        "event_monitor_active": bool(event_monitor_module),
        "safe_defaults": settings.get_large_library_safe_defaults(),
        "ffmpeg_version": ffmpeg_info.get("version"),
    }
