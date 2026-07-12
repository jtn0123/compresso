#!/usr/bin/env python3

"""Worker hardware discovery and heterogeneous scheduling scores."""

import math
import os
import platform
import shutil
import threading
from collections import defaultdict

import psutil

from compresso.libs.unffmpeg.info import Info
from compresso.libs.unmodels.completedtasks import CompletedTasks
from compresso.libs.unmodels.compressionstats import CompressionStats


class WorkerCapabilities:
    def __init__(self, ffmpeg_info=None):
        self.ffmpeg_info = ffmpeg_info or Info()
        self._static_capabilities = None
        self._lock = threading.Lock()

    @staticmethod
    def _existing_path(path):
        candidate = os.path.abspath(path)
        while not os.path.exists(candidate):
            parent = os.path.dirname(candidate)
            if parent == candidate:
                break
            candidate = parent
        return candidate

    def _static_snapshot(self):
        with self._lock:
            if self._static_capabilities is None:
                try:
                    encoders = sorted(self.ffmpeg_info.get_ffmpeg_video_encoders())
                except (OSError, RuntimeError, TypeError, ValueError):
                    encoders = []
                try:
                    hardware_accelerators = sorted(self.ffmpeg_info.get_available_ffmpeg_hw_acceleration_methods())
                except (OSError, RuntimeError, TypeError, ValueError):
                    hardware_accelerators = []
                self._static_capabilities = {
                    "platform": {
                        "system": platform.system(),
                        "machine": platform.machine(),
                    },
                    "video_encoders": encoders,
                    "hardware_accelerators": hardware_accelerators,
                }
            return dict(self._static_capabilities)

    def snapshot(self, settings):
        capabilities = self._static_snapshot()
        memory = psutil.virtual_memory()
        cache_path = self._existing_path(settings.get_cache_path())
        disk = shutil.disk_usage(cache_path)
        capabilities.update(
            {
                "cpu": {
                    "count": psutil.cpu_count() or 1,
                    "percent": float(psutil.cpu_percent(interval=0)),
                },
                "memory": {
                    "total_bytes": int(memory.total),
                    "available_bytes": int(memory.available),
                    "percent": float(memory.percent),
                },
                "cache_disk": {
                    "path": cache_path,
                    "total_bytes": int(disk.total),
                    "free_bytes": int(disk.free),
                },
                "thermal": self._thermal_snapshot(),
                "performance": self._performance_snapshot(),
            }
        )
        return capabilities

    @staticmethod
    def _thermal_snapshot():
        try:
            sensors = psutil.sensors_temperatures()
        except (AttributeError, OSError, RuntimeError):
            sensors = {}
        temperatures = [
            float(entry.current)
            for entries in sensors.values()
            for entry in entries
            if getattr(entry, "current", None) is not None
        ]
        max_celsius = max(temperatures, default=None)
        if max_celsius is None:
            state = "unknown"
        elif max_celsius >= 95:
            state = "critical"
        elif max_celsius >= 85:
            state = "hot"
        elif max_celsius >= 75:
            state = "warm"
        else:
            state = "nominal"
        return {"state": state, "max_celsius": max_celsius}

    @staticmethod
    def _performance_snapshot(limit=100):
        """Summarize persisted recent encode throughput overall and by output codec."""
        try:
            rows = (
                CompressionStats.select(CompressionStats, CompletedTasks)
                .join(CompletedTasks)
                .where(CompletedTasks.task_success == True)  # noqa: E712 - Peewee expression
                .order_by(CompletedTasks.finish_time.desc())
                .limit(limit)
            )
            buckets = defaultdict(list)
            all_samples = []
            for row in rows:
                duration = float(row.encoding_duration_seconds or 0)
                if duration <= 0:
                    continue
                sample = {
                    "tasks_per_hour": 3600 / duration,
                    "media_speed_ratio": max(0.0, float(row.source_duration_seconds or 0)) / duration,
                }
                all_samples.append(sample)
                buckets[row.destination_codec or "unknown"].append(sample)
        except Exception:
            return {"sample_count": 0, "tasks_per_hour": 0.0, "media_speed_ratio": 0.0, "by_codec": {}}

        def summarize(samples):
            count = len(samples)
            if not count:
                return {"sample_count": 0, "tasks_per_hour": 0.0, "media_speed_ratio": 0.0}
            return {
                "sample_count": count,
                "tasks_per_hour": round(sum(sample["tasks_per_hour"] for sample in samples) / count, 3),
                "media_speed_ratio": round(sum(sample["media_speed_ratio"] for sample in samples) / count, 3),
            }

        result = summarize(all_samples)
        result["by_codec"] = {codec: summarize(samples) for codec, samples in sorted(buckets.items())}
        return result

    @staticmethod
    def scheduling_score(capabilities, required_encoder=None):
        if not isinstance(capabilities, dict):
            return None if required_encoder else 0.0
        encoders = capabilities.get("video_encoders", [])
        if not isinstance(encoders, (list, tuple, set)):
            encoders = []
        if required_encoder and required_encoder not in encoders:
            return None
        cpu = capabilities.get("cpu") if isinstance(capabilities.get("cpu"), dict) else {}
        memory = capabilities.get("memory") if isinstance(capabilities.get("memory"), dict) else {}
        cache_disk = capabilities.get("cache_disk") if isinstance(capabilities.get("cache_disk"), dict) else {}
        thermal = capabilities.get("thermal") if isinstance(capabilities.get("thermal"), dict) else {}
        performance = capabilities.get("performance") if isinstance(capabilities.get("performance"), dict) else {}

        def finite_number(value, default):
            try:
                number = float(value)
            except (TypeError, ValueError):
                return default
            return number if math.isfinite(number) else default

        cpu_percent = min(100.0, max(0.0, finite_number(cpu.get("percent"), 100.0)))
        memory_percent = min(100.0, max(0.0, finite_number(memory.get("percent"), 100.0)))
        free_disk_bytes = max(0.0, finite_number(cache_disk.get("free_bytes"), 0.0))
        cpu_headroom = 100 - cpu_percent
        memory_headroom = 100 - memory_percent
        free_disk_gb = free_disk_bytes / (1024**3)
        base_score = (cpu_headroom * 0.5) + (memory_headroom * 0.3) + (min(free_disk_gb, 500) * 0.04)
        tasks_per_hour = max(0.0, finite_number(performance.get("tasks_per_hour"), 0.0))
        throughput_bonus = min(30.0, math.log1p(tasks_per_hour) * 6)
        thermal_factor = {"critical": 0.05, "hot": 0.35, "warm": 0.75}.get(thermal.get("state"), 1.0)
        return round((base_score + throughput_bonus) * thermal_factor, 3)
