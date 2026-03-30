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

from compresso.libs.logs import CompressoLogging
from compresso.libs.singleton import SingletonType

HISTORY_MAX_SAMPLES = 120  # 10 minutes at 5-second intervals
_DRM_SYSFS_PATH = "/sys/class/drm"
INTEL_VENDOR_ID = "0x8086"
AMD_VENDOR_ID = "0x1002"


class GpuMonitor(metaclass=SingletonType):
    def __init__(self):
        self.logger = CompressoLogging.get_logger(name=self.__class__.__name__)
        self._history: dict[str, deque] = {}
        self._capabilities = self._probe_capabilities()
        self._macos_gpu_cache: list[dict] = []

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

    def get_realtime_metrics(self) -> list[dict]:
        """
        Poll all available GPU backends and return current metrics.

        Returns a list of dicts, each with keys:
            index, type, name, utilization_percent, memory_used_mb,
            memory_total_mb, temperature_c
        """
        gpus = []
        gpus.extend(self._poll_nvidia())
        gpus.extend(self._poll_intel())
        gpus.extend(self._poll_amd())
        gpus.extend(self._poll_macos_gpu())
        self._record_history(gpus)
        return gpus

    def _poll_nvidia(self) -> list[dict]:
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

            gpus = []
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

    def _poll_intel(self) -> list[dict]:
        """Best-effort Intel GPU metrics via sysfs."""
        if not self._capabilities.get("intel"):
            return []

        gpus = []
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

                # Approximate utilization from current vs max frequency
                utilization = 0.0
                cur_freq_path = card_dir / "gt_cur_freq_mhz"
                max_freq_path = card_dir / "gt_max_freq_mhz"
                try:
                    cur_freq = float(cur_freq_path.read_text().strip())
                    max_freq = float(max_freq_path.read_text().strip())
                    if max_freq > 0:
                        utilization = round((cur_freq / max_freq) * 100, 1)
                except Exception:  # noqa: S110 — freq sysfs files may be absent or unreadable
                    pass

                # Read temperature from hwmon if available
                temperature = 0
                try:
                    hwmon_dirs = list((card_dir / "device" / "hwmon").iterdir())
                    for hwmon_dir in hwmon_dirs:
                        temp_path = hwmon_dir / "temp1_input"
                        if temp_path.exists():
                            # sysfs reports millidegrees Celsius
                            temperature = int(temp_path.read_text().strip()) // 1000
                            break
                except Exception:  # noqa: S110 — hwmon temp files may be absent
                    pass

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

    def _poll_amd(self) -> list[dict]:
        """Best-effort AMD GPU metrics via sysfs."""
        if not self._capabilities.get("amd"):
            return []

        gpus = []
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

                # Read GPU busy percent
                utilization = 0.0
                busy_path = card_dir / "device" / "gpu_busy_percent"
                try:  # noqa: SIM105 — gpu_busy_percent may be absent or unreadable
                    utilization = float(busy_path.read_text().strip())
                except Exception:  # noqa: S110 — gpu_busy_percent sysfs may be absent
                    pass

                # Read VRAM usage if available
                memory_used = 0
                memory_total = 0
                try:
                    vram_used_path = card_dir / "device" / "mem_info_vram_used"
                    vram_total_path = card_dir / "device" / "mem_info_vram_total"
                    if vram_used_path.exists():
                        memory_used = int(vram_used_path.read_text().strip()) // (1024 * 1024)
                    if vram_total_path.exists():
                        memory_total = int(vram_total_path.read_text().strip()) // (1024 * 1024)
                except Exception:  # noqa: S110 — VRAM sysfs files may be absent
                    pass

                # Read temperature from hwmon if available
                temperature = 0
                try:
                    hwmon_dirs = list((card_dir / "device" / "hwmon").iterdir())
                    for hwmon_dir in hwmon_dirs:
                        temp_path = hwmon_dir / "temp1_input"
                        if temp_path.exists():
                            temperature = int(temp_path.read_text().strip()) // 1000
                            break
                except Exception:  # noqa: S110 — hwmon temp files may be absent
                    pass

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

    def _poll_macos_gpu(self) -> list[dict]:
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

            data = json.loads(result.stdout)
            displays = data.get("SPDisplaysDataType", [])
            gpus = []
            for i, gpu_info in enumerate(displays):
                name = gpu_info.get("sppci_model", "Apple GPU")
                # VRAM may be reported as a string like "8 GB" or missing entirely
                vram_str = gpu_info.get("spdisplays_vram", gpu_info.get("sppci_vram", ""))
                memory_total_mb = 0
                if isinstance(vram_str, str):
                    parts = vram_str.split()
                    try:
                        val = int(parts[0])
                        memory_total_mb = val * 1024 if len(parts) > 1 and parts[1].upper().startswith("G") else val
                    except (ValueError, IndexError):
                        pass

                gpus.append(
                    {
                        "index": i,
                        "type": "apple",
                        "name": name,
                        "utilization_percent": None,
                        "memory_used_mb": 0,
                        "memory_total_mb": memory_total_mb,
                        "temperature_c": None,
                    }
                )
            self._macos_gpu_cache = gpus
            return gpus

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            self.logger.debug("macOS GPU detection failed: %s", e)
        except Exception as e:
            self.logger.warning("macOS GPU polling failed: %s", e)
        return []

    def _record_history(self, gpus: list[dict]) -> None:
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

    def get_history(self, gpu_index=None) -> dict:
        """
        Return historical samples.

        If gpu_index is provided (composite key like 'nvidia:0'), return
        samples for that GPU only.  Otherwise return all history.
        """
        if gpu_index is not None:
            samples = self._history.get(gpu_index, deque())
            return {gpu_index: list(samples)}
        return {idx: list(samples) for idx, samples in self._history.items()}
