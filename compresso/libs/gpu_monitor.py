#!/usr/bin/env python3

"""
compresso.libs.gpu_monitor

Singleton GPU monitor that polls NVIDIA, Intel, and AMD GPUs
for real-time utilization metrics and maintains a rolling history.
"""

import json
import shutil
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import TypedDict

from compresso.libs import narrowing
from compresso.libs.logs import CompressoLogging
from compresso.libs.singleton import SingletonType

HISTORY_MAX_SAMPLES = 120  # 10 minutes at 5-second intervals
_DRM_SYSFS_PATH = "/sys/class/drm"
INTEL_VENDOR_ID = "0x8086"
AMD_VENDOR_ID = "0x1002"


class GpuMetrics(TypedDict):
    index: int
    type: str
    name: str
    utilization_percent: float | None
    memory_used_mb: int
    memory_total_mb: int
    temperature_c: int | None


class GpuHistorySample(TypedDict):
    timestamp: float
    utilization_percent: float | None
    memory_used_mb: int
    memory_total_mb: int
    temperature_c: int | None


class GpuMonitor(metaclass=SingletonType):
    def __init__(self) -> None:
        self.logger = CompressoLogging.get_logger(name=self.__class__.__name__)
        self._history: dict[str, deque[GpuHistorySample]] = {}
        self._capabilities = self._probe_capabilities()
        self._macos_gpu_cache: list[GpuMetrics] = []

    def _probe_capabilities(self) -> dict[str, bool]:
        """Check which GPU monitoring backends are available on this system."""
        caps = {
            "nvidia": shutil.which("nvidia-smi") is not None,
            "intel": False,
            "amd": False,
            "videotoolbox": False,
        }

        if sys.platform == "linux":
            # Check for Intel GPU via sysfs vendor ID (0x8086)
            try:
                for vendor_path in Path(_DRM_SYSFS_PATH).glob("card*/device/vendor"):
                    vendor_id = vendor_path.read_text().strip()
                    if vendor_id == INTEL_VENDOR_ID:
                        caps["intel"] = True
                        break
            except Exception:  # noqa: S110 — optional GPU detection; missing sysfs is expected
                pass

            # Check for AMD GPU via sysfs vendor ID (0x1002)
            try:
                for vendor_path in Path(_DRM_SYSFS_PATH).glob("card*/device/vendor"):
                    vendor_id = vendor_path.read_text().strip()
                    if vendor_id == AMD_VENDOR_ID:
                        caps["amd"] = True
                        break
            except Exception:  # noqa: S110 — optional GPU detection; missing sysfs is expected
                pass

        elif sys.platform == "darwin":
            # VideoToolbox is always available on macOS
            caps["videotoolbox"] = True

        self.logger.debug("GPU capabilities: %s", caps)
        return caps

    def get_realtime_metrics(self) -> list[GpuMetrics]:
        """
        Poll all available GPU backends and return current metrics.

        Returns a list of dicts, each with keys:
            index, type, name, utilization_percent, memory_used_mb,
            memory_total_mb, temperature_c
        """
        gpus: list[GpuMetrics] = []
        gpus.extend(self._poll_nvidia())
        gpus.extend(self._poll_intel())
        gpus.extend(self._poll_amd())
        gpus.extend(self._poll_macos_gpu())
        self._record_history(gpus)
        return gpus

    def _poll_nvidia(self) -> list[GpuMetrics]:
        """Query NVIDIA GPUs via nvidia-smi."""
        if not self._capabilities.get("nvidia"):
            return []

        try:
            result = subprocess.run(
                [  # noqa: S607 - nvidia-smi resolved from PATH intentionally
                    "nvidia-smi",
                    "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                self.logger.debug("nvidia-smi returned non-zero exit code: %d", result.returncode)
                return []

            gpus: list[GpuMetrics] = []
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    gpus.append(
                        {
                            "index": int(parts[0]),
                            "type": "nvidia",
                            "name": parts[1],
                            "utilization_percent": float(parts[2]),
                            "memory_used_mb": int(float(parts[3])),
                            "memory_total_mb": int(float(parts[4])),
                            "temperature_c": int(float(parts[5])),
                        }
                    )
            return gpus

        except FileNotFoundError:
            self.logger.debug("nvidia-smi not found on PATH")
            self._capabilities["nvidia"] = False
        except subprocess.TimeoutExpired:
            self.logger.warning("nvidia-smi timed out after 5 seconds")
        except Exception as e:
            self.logger.warning("NVIDIA GPU polling failed: %s", e)
        return []

    def _poll_intel(self) -> list[GpuMetrics]:
        """Best-effort Intel GPU metrics via sysfs."""
        if not self._capabilities.get("intel"):
            return []

        gpus: list[GpuMetrics] = []
        try:
            drm_path = Path(_DRM_SYSFS_PATH)
            for card_dir in sorted(drm_path.glob("card[0-9]*")):
                vendor_path = card_dir / "device" / "vendor"
                if not vendor_path.exists():
                    continue
                try:
                    vendor_id = vendor_path.read_text().strip()
                except Exception:  # noqa: S112 — skip unreadable sysfs entries
                    continue
                if vendor_id != INTEL_VENDOR_ID:
                    continue

                card_name = card_dir.name
                index = int(card_name.replace("card", ""))

                utilization = self._intel_utilization(card_dir)
                temperature = self._sysfs_temperature(card_dir)

                gpus.append(
                    {
                        "index": index,
                        "type": "intel",
                        "name": f"Intel GPU ({card_name})",
                        "utilization_percent": utilization,
                        "memory_used_mb": 0,
                        "memory_total_mb": 0,
                        "temperature_c": temperature,
                    }
                )

        except Exception as e:
            self.logger.warning("Intel GPU polling failed: %s", e)
        return gpus

    @staticmethod
    def _intel_utilization(card_dir: Path) -> float:
        try:
            current = float((card_dir / "gt_cur_freq_mhz").read_text().strip())
            maximum = float((card_dir / "gt_max_freq_mhz").read_text().strip())
            return round((current / maximum) * 100, 1) if maximum > 0 else 0.0
        except Exception:  # noqa: S110 — freq sysfs files may be absent or unreadable
            return 0.0

    @staticmethod
    def _sysfs_temperature(card_dir: Path) -> int:
        try:
            for hwmon_dir in (card_dir / "device" / "hwmon").iterdir():
                temp_path = hwmon_dir / "temp1_input"
                if temp_path.exists():
                    return int(temp_path.read_text().strip()) // 1000
        except Exception:  # noqa: S110 — hwmon temp files may be absent
            pass
        return 0

    def _poll_amd(self) -> list[GpuMetrics]:
        """Best-effort AMD GPU metrics via sysfs."""
        if not self._capabilities.get("amd"):
            return []

        gpus: list[GpuMetrics] = []
        try:
            drm_path = Path(_DRM_SYSFS_PATH)
            for card_dir in sorted(drm_path.glob("card[0-9]*")):
                vendor_path = card_dir / "device" / "vendor"
                if not vendor_path.exists():
                    continue
                try:
                    vendor_id = vendor_path.read_text().strip()
                except Exception:  # noqa: S112 — skip unreadable sysfs entries
                    continue
                if vendor_id != AMD_VENDOR_ID:
                    continue

                card_name = card_dir.name
                index = int(card_name.replace("card", ""))

                utilization = self._read_sysfs_float(card_dir / "device" / "gpu_busy_percent")
                memory_used, memory_total = self._amd_vram(card_dir)
                temperature = self._sysfs_temperature(card_dir)

                gpus.append(
                    {
                        "index": index,
                        "type": "amd",
                        "name": f"AMD GPU ({card_name})",
                        "utilization_percent": utilization,
                        "memory_used_mb": memory_used,
                        "memory_total_mb": memory_total,
                        "temperature_c": temperature,
                    }
                )

        except Exception as e:
            self.logger.warning("AMD GPU polling failed: %s", e)
        return gpus

    @staticmethod
    def _read_sysfs_float(path: Path) -> float:
        try:
            return float(path.read_text().strip())
        except Exception:  # noqa: S110 — gpu_busy_percent sysfs may be absent
            return 0.0

    @staticmethod
    def _amd_vram(card_dir: Path) -> tuple[int, int]:
        try:
            used_path = card_dir / "device" / "mem_info_vram_used"
            total_path = card_dir / "device" / "mem_info_vram_total"
            used = int(used_path.read_text().strip()) // (1024 * 1024) if used_path.exists() else 0
            total = int(total_path.read_text().strip()) // (1024 * 1024) if total_path.exists() else 0
            return used, total
        except Exception:  # noqa: S110 — VRAM sysfs files may be absent
            return 0, 0

    def _poll_macos_gpu(self) -> list[GpuMetrics]:
        """Detect GPU info on macOS via system_profiler. Cached after first call
        since GPU identity/VRAM are static hardware info."""
        if not self._capabilities.get("videotoolbox"):
            return []

        if self._macos_gpu_cache:
            return self._macos_gpu_cache

        try:
            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType", "-json"],  # noqa: S607 - macOS system command resolved from PATH
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return []

            data = narrowing.string_keyed_dict_or_none(json.loads(result.stdout))
            if data is None:
                return []
            displays = data.get("SPDisplaysDataType")
            if not isinstance(displays, list):
                return []
            detected_gpus = [self._macos_gpu_metrics(index, info) for index, info in enumerate(displays)]
            valid_gpus: list[GpuMetrics] = [gpu for gpu in detected_gpus if gpu is not None]
            self._macos_gpu_cache = valid_gpus
            return valid_gpus

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.debug("macOS GPU detection failed: %s", e)
        except Exception as e:
            self.logger.warning("macOS GPU polling failed: %s", e)
        return []

    @staticmethod
    def _macos_gpu_metrics(index: int, raw_gpu_info: object) -> GpuMetrics | None:
        gpu_info = narrowing.string_keyed_dict_or_none(raw_gpu_info)
        if gpu_info is None:
            return None
        raw_name = gpu_info.get("sppci_model")
        name = raw_name if isinstance(raw_name, str) else "Apple GPU"
        vram = gpu_info.get("spdisplays_vram", gpu_info.get("sppci_vram", ""))
        memory_total_mb = 0
        if isinstance(vram, str):
            try:
                value, *units = vram.split()
                memory_total_mb = int(value) * 1024 if units and units[0].upper().startswith("G") else int(value)
            except (ValueError, IndexError):
                pass
        return {
            "index": index,
            "type": "apple",
            "name": name,
            "utilization_percent": None,
            "memory_used_mb": 0,
            "memory_total_mb": memory_total_mb,
            "temperature_c": None,
        }

    def _record_history(self, gpus: list[GpuMetrics]) -> None:
        """Append current metrics with timestamp to rolling history.

        Uses composite key 'type:index' to avoid collisions when multiple GPU
        vendors are present (e.g., NVIDIA index 0 and Intel card0).
        """
        now = time.time()
        for gpu in gpus:
            idx = f"{gpu.get('type', 'unknown')}:{gpu['index']}"
            if idx not in self._history:
                self._history[idx] = deque(maxlen=HISTORY_MAX_SAMPLES)
            self._history[idx].append(
                {
                    "timestamp": now,
                    "utilization_percent": gpu.get("utilization_percent", 0.0),
                    "memory_used_mb": gpu.get("memory_used_mb", 0),
                    "memory_total_mb": gpu.get("memory_total_mb", 0),
                    "temperature_c": gpu.get("temperature_c", 0),
                }
            )

    def get_history(self, gpu_index: str | None = None) -> dict[str, list[GpuHistorySample]]:
        """
        Return historical samples.

        If gpu_index is provided (composite key like 'nvidia:0'), return
        samples for that GPU only.  Otherwise return all history.
        """
        if gpu_index is not None:
            samples = self._history.get(gpu_index, deque())
            return {gpu_index: list(samples)}
        return {idx: list(samples) for idx, samples in self._history.items()}
