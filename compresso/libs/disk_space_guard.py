#!/usr/bin/env python3

"""Disk-capacity checks for encoding, approval staging, and final replacement."""

import math
import os
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Protocol

from compresso.config import Config


class DiskUsageResult(Protocol):
    @property
    def free(self) -> int: ...


Pathish = str | os.PathLike[str]


@dataclass(frozen=True)
class DiskSpaceCheck:
    ok: bool
    phase: str
    path: str
    free_bytes: int
    required_bytes: int

    def to_dict(self) -> dict[str, bool | str | int]:
        return asdict(self)


class DiskSpaceGuard:
    """Calculate conservative free-space requirements before file operations."""

    def __init__(
        self,
        settings: Config,
        disk_usage: Callable[[str], DiskUsageResult] = shutil.disk_usage,
    ) -> None:
        self.settings = settings
        self._disk_usage = disk_usage

    def _enabled(self) -> bool:
        try:
            value = self.settings.get_disk_space_guard_enabled()
        except (AttributeError, TypeError):
            return True
        if isinstance(value, str):
            return value.lower() in {"true", "1", "yes", "on"}
        return value if isinstance(value, bool) else True

    def _reserve_bytes(self) -> int:
        try:
            reserve_gb = float(self.settings.get_minimum_free_space_gb())
        except (AttributeError, TypeError, ValueError):
            reserve_gb = 5.0
        if not math.isfinite(reserve_gb) or reserve_gb > 1_000_000:
            reserve_gb = 5.0
        return math.ceil(max(0.0, reserve_gb) * (1024**3))

    def _output_multiplier(self) -> float:
        try:
            multiplier = float(self.settings.get_disk_space_output_multiplier())
        except (AttributeError, TypeError, ValueError):
            multiplier = 1.25
        if not math.isfinite(multiplier) or multiplier > 1_000:
            multiplier = 1.25
        return max(1.0, multiplier)

    @staticmethod
    def _file_size(path: Pathish) -> int:
        try:
            return os.path.getsize(path)
        except (OSError, TypeError, ValueError):
            return 0

    @staticmethod
    def _usage_path(target: Pathish) -> str:
        candidate = os.path.abspath(os.fspath(target))
        if not os.path.isdir(candidate):
            candidate = os.path.dirname(candidate)
        while not os.path.exists(candidate):
            parent = os.path.dirname(candidate)
            if parent == candidate:
                break
            candidate = parent
        return candidate

    def _check(self, phase: str, target: Pathish, workload_bytes: int | float) -> DiskSpaceCheck:
        if not self._enabled():
            return DiskSpaceCheck(True, "disabled", os.fspath(target), 0, 0)
        usage_path = self._usage_path(target)
        free_bytes = int(self._disk_usage(usage_path).free)
        required_bytes = self._reserve_bytes() + max(0, math.ceil(workload_bytes))
        return DiskSpaceCheck(free_bytes >= required_bytes, phase, usage_path, free_bytes, required_bytes)

    def check_cache_capacity(self, source_path: Pathish, cache_path: Pathish) -> DiskSpaceCheck:
        estimated_output = self._file_size(source_path) * self._output_multiplier()
        return self._check("encode_cache", cache_path, estimated_output)

    def check_staging_capacity(self, encoded_path: Pathish, staging_path: Pathish) -> DiskSpaceCheck:
        return self._check("approval_staging", staging_path, self._file_size(encoded_path))

    def check_finalization_capacity(
        self,
        source_path: Pathish,
        encoded_path: Pathish,
        destination_path: Pathish,
    ) -> DiskSpaceCheck:
        # Final replacement may temporarily hold an original backup and a new
        # destination copy on the library volume at the same time.
        workload = self._file_size(source_path) + self._file_size(encoded_path)
        return self._check("final_replacement", destination_path, workload)
