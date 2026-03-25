#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_gpu_monitor.py

    Unit tests for compresso.libs.gpu_monitor.GpuMonitor.
"""

import logging
import subprocess
import time

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from compresso.libs.singleton import SingletonType

GPU_MONITOR = 'compresso.libs.gpu_monitor'


@pytest.fixture(autouse=True)
def reset_singleton():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture(autouse=True)
def mock_logger():
    logger = logging.getLogger('compresso_test_gpu_monitor')
    with patch('compresso.libs.logs.CompressoLogging.get_logger', return_value=logger):
        yield logger


@pytest.fixture
def no_backends():
    """Patch shutil.which and sysfs so no GPU backends are detected."""
    with patch(GPU_MONITOR + '.shutil.which', return_value=None), \
         patch(GPU_MONITOR + '.Path') as mock_path_cls:
        mock_drm = MagicMock()
        mock_drm.glob.return_value = []
        mock_path_cls.return_value = mock_drm
        yield


@pytest.fixture
def nvidia_only():
    """Patch so only NVIDIA backend is detected."""
    with patch(GPU_MONITOR + '.shutil.which', side_effect=lambda cmd: '/usr/bin/nvidia-smi' if cmd == 'nvidia-smi' else None), \
         patch(GPU_MONITOR + '.Path') as mock_path_cls:
        mock_drm = MagicMock()
        mock_drm.glob.return_value = []
        mock_path_cls.return_value = mock_drm
        yield


def _make_nvidia_csv(*rows):
    """Build nvidia-smi CSV output from tuples of (index, name, util, mem_used, mem_total, temp)."""
    lines = []
    for row in rows:
        lines.append(', '.join(str(v) for v in row))
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------
@pytest.mark.unittest
class TestGpuMonitorSingleton:

    def test_returns_same_instance(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        m1 = GpuMonitor()
        m2 = GpuMonitor()
        assert m1 is m2

    def test_creates_instance(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        assert monitor is not None


# ---------------------------------------------------------------------------
# Capability probing
# ---------------------------------------------------------------------------
@pytest.mark.unittest
class TestProbeCapabilities:

    def test_no_backends_detected(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        assert monitor._capabilities['nvidia'] is False
        assert monitor._capabilities['intel'] is False
        assert monitor._capabilities['amd'] is False

    def test_nvidia_detected_when_on_path(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        assert monitor._capabilities['nvidia'] is True

    def test_intel_detected_via_sysfs(self):
        mock_vendor = MagicMock()
        mock_vendor.read_text.return_value = '0x8086'

        mock_card = MagicMock()
        mock_card.__truediv__ = MagicMock(side_effect=lambda part: mock_vendor if part == 'device' else mock_vendor)
        mock_vendor.__truediv__ = MagicMock(return_value=mock_vendor)

        with patch(GPU_MONITOR + '.shutil.which', return_value=None), \
             patch(GPU_MONITOR + '.Path') as mock_path_cls:
            mock_drm = MagicMock()

            def glob_side_effect(pattern):
                if 'vendor' in pattern:
                    return [mock_vendor]
                return []

            mock_drm.glob.side_effect = glob_side_effect
            mock_path_cls.return_value = mock_drm

            from compresso.libs.gpu_monitor import GpuMonitor
            monitor = GpuMonitor()
            assert monitor._capabilities['intel'] is True

    def test_amd_detected_via_sysfs(self):
        mock_vendor = MagicMock()
        mock_vendor.read_text.return_value = '0x1002'

        with patch(GPU_MONITOR + '.shutil.which', return_value=None), \
             patch(GPU_MONITOR + '.Path') as mock_path_cls:
            mock_drm = MagicMock()

            def glob_side_effect(pattern):
                if 'vendor' in pattern:
                    return [mock_vendor]
                return []

            mock_drm.glob.side_effect = glob_side_effect
            mock_path_cls.return_value = mock_drm

            from compresso.libs.gpu_monitor import GpuMonitor
            monitor = GpuMonitor()
            assert monitor._capabilities['amd'] is True


# ---------------------------------------------------------------------------
# NVIDIA polling
# ---------------------------------------------------------------------------
@pytest.mark.unittest
class TestPollNvidia:

    def test_returns_empty_when_not_available(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        assert monitor._poll_nvidia() == []

    def test_parses_single_gpu(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        csv_output = _make_nvidia_csv((0, 'NVIDIA GeForce RTX 3080', 45, 2048, 10240, 72))
        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=csv_output)
            result = monitor._poll_nvidia()

        assert len(result) == 1
        gpu = result[0]
        assert gpu['index'] == 0
        assert gpu['type'] == 'nvidia'
        assert gpu['name'] == 'NVIDIA GeForce RTX 3080'
        assert gpu['utilization_percent'] == 45.0
        assert gpu['memory_used_mb'] == 2048
        assert gpu['memory_total_mb'] == 10240
        assert gpu['temperature_c'] == 72

    def test_parses_multiple_gpus(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        csv_output = _make_nvidia_csv(
            (0, 'RTX 3090', 80, 4096, 24576, 85),
            (1, 'RTX 3080', 55, 2048, 10240, 70),
        )
        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=csv_output)
            result = monitor._poll_nvidia()

        assert len(result) == 2
        assert result[0]['index'] == 0
        assert result[1]['index'] == 1

    def test_handles_nonzero_returncode(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout='')
            result = monitor._poll_nvidia()

        assert result == []

    def test_handles_timeout(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd='nvidia-smi', timeout=5)
            result = monitor._poll_nvidia()

        assert result == []

    def test_handles_file_not_found(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.side_effect = FileNotFoundError("nvidia-smi not found")
            result = monitor._poll_nvidia()

        assert result == []
        # Should disable capability after FileNotFoundError
        assert monitor._capabilities['nvidia'] is False

    def test_handles_empty_output(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='')
            result = monitor._poll_nvidia()

        assert result == []

    def test_skips_malformed_lines(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        csv_output = "0, RTX 3080, 45\n1, RTX 3090, 80, 4096, 24576, 85"
        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=csv_output)
            result = monitor._poll_nvidia()

        # Only the second line has enough fields
        assert len(result) == 1
        assert result[0]['index'] == 1


# ---------------------------------------------------------------------------
# Intel polling
# ---------------------------------------------------------------------------
@pytest.mark.unittest
class TestPollIntel:

    def test_returns_empty_when_not_available(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        assert monitor._poll_intel() == []

    def test_reads_sysfs_metrics(self):
        from compresso.libs.gpu_monitor import GpuMonitor

        with patch(GPU_MONITOR + '.shutil.which', return_value=None), \
             patch(GPU_MONITOR + '.Path') as mock_path_cls:
            # Build mock sysfs tree
            mock_vendor_file = MagicMock()
            mock_vendor_file.exists.return_value = True
            mock_vendor_file.read_text.return_value = '0x8086'

            mock_cur_freq = MagicMock()
            mock_cur_freq.read_text.return_value = '750'

            mock_max_freq = MagicMock()
            mock_max_freq.read_text.return_value = '1500'

            mock_temp = MagicMock()
            mock_temp.exists.return_value = True
            mock_temp.read_text.return_value = '55000'

            mock_hwmon_inner = MagicMock()
            mock_hwmon_inner.__truediv__ = MagicMock(return_value=mock_temp)

            mock_hwmon_dir = MagicMock()
            mock_hwmon_dir.iterdir.return_value = [mock_hwmon_inner]

            mock_device_dir = MagicMock()

            mock_card = MagicMock()
            mock_card.name = 'card0'

            def card_div(part):
                if part == 'device':
                    return mock_device_dir
                if part == 'gt_cur_freq_mhz':
                    return mock_cur_freq
                if part == 'gt_max_freq_mhz':
                    return mock_max_freq
                return MagicMock()

            mock_card.__truediv__ = MagicMock(side_effect=card_div)

            def device_div(part):
                if part == 'vendor':
                    return mock_vendor_file
                if part == 'hwmon':
                    return mock_hwmon_dir
                return MagicMock()

            mock_device_dir.__truediv__ = MagicMock(side_effect=device_div)

            mock_drm = MagicMock()

            def drm_glob(pattern):
                if 'vendor' in pattern:
                    return [mock_vendor_file]
                elif 'card[0-9]' in pattern:
                    return [mock_card]
                return []

            mock_drm.glob.side_effect = drm_glob
            mock_path_cls.return_value = mock_drm

            monitor = GpuMonitor()
            # Force capability on since our mock is correctly wired
            monitor._capabilities['intel'] = True
            result = monitor._poll_intel()

        assert len(result) == 1
        gpu = result[0]
        assert gpu['type'] == 'intel'
        assert gpu['index'] == 0
        assert gpu['utilization_percent'] == 50.0
        assert gpu['temperature_c'] == 55


# ---------------------------------------------------------------------------
# AMD polling
# ---------------------------------------------------------------------------
@pytest.mark.unittest
class TestPollAmd:

    def test_returns_empty_when_not_available(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        assert monitor._poll_amd() == []

    def test_reads_sysfs_metrics(self):
        from compresso.libs.gpu_monitor import GpuMonitor

        with patch(GPU_MONITOR + '.shutil.which', return_value=None), \
             patch(GPU_MONITOR + '.Path') as mock_path_cls:
            mock_vendor_file = MagicMock()
            mock_vendor_file.exists.return_value = True
            mock_vendor_file.read_text.return_value = '0x1002'

            mock_busy = MagicMock()
            mock_busy.read_text.return_value = '67'

            mock_vram_used = MagicMock()
            mock_vram_used.exists.return_value = True
            mock_vram_used.read_text.return_value = str(4 * 1024 * 1024 * 1024)  # 4 GB

            mock_vram_total = MagicMock()
            mock_vram_total.exists.return_value = True
            mock_vram_total.read_text.return_value = str(8 * 1024 * 1024 * 1024)  # 8 GB

            mock_temp = MagicMock()
            mock_temp.exists.return_value = True
            mock_temp.read_text.return_value = '65000'

            mock_hwmon_inner = MagicMock()
            mock_hwmon_inner.__truediv__ = MagicMock(return_value=mock_temp)

            mock_hwmon_dir = MagicMock()
            mock_hwmon_dir.iterdir.return_value = [mock_hwmon_inner]

            mock_device_dir = MagicMock()

            mock_card = MagicMock()
            mock_card.name = 'card1'

            def card_div(part):
                if part == 'device':
                    return mock_device_dir
                return MagicMock()

            mock_card.__truediv__ = MagicMock(side_effect=card_div)

            def device_div(part):
                if part == 'vendor':
                    return mock_vendor_file
                if part == 'gpu_busy_percent':
                    return mock_busy
                if part == 'mem_info_vram_used':
                    return mock_vram_used
                if part == 'mem_info_vram_total':
                    return mock_vram_total
                if part == 'hwmon':
                    return mock_hwmon_dir
                return MagicMock()

            mock_device_dir.__truediv__ = MagicMock(side_effect=device_div)

            mock_drm = MagicMock()

            def drm_glob(pattern):
                if 'vendor' in pattern:
                    return [mock_vendor_file]
                elif 'card[0-9]' in pattern:
                    return [mock_card]
                return []

            mock_drm.glob.side_effect = drm_glob
            mock_path_cls.return_value = mock_drm

            monitor = GpuMonitor()
            monitor._capabilities['amd'] = True
            result = monitor._poll_amd()

        assert len(result) == 1
        gpu = result[0]
        assert gpu['type'] == 'amd'
        assert gpu['index'] == 1
        assert gpu['utilization_percent'] == 67.0
        assert gpu['memory_used_mb'] == 4096
        assert gpu['memory_total_mb'] == 8192
        assert gpu['temperature_c'] == 65


# ---------------------------------------------------------------------------
# get_realtime_metrics integration
# ---------------------------------------------------------------------------
@pytest.mark.unittest
class TestGetRealtimeMetrics:

    def test_aggregates_all_backends(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        monitor._capabilities = {'nvidia': True, 'intel': False, 'amd': False}

        csv_output = _make_nvidia_csv((0, 'RTX 3080', 55, 2048, 10240, 70))
        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=csv_output)
            result = monitor.get_realtime_metrics()

        assert len(result) == 1
        assert result[0]['type'] == 'nvidia'

    def test_returns_empty_when_no_gpus(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        result = monitor.get_realtime_metrics()
        assert result == []

    def test_records_history_after_poll(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        monitor._capabilities = {'nvidia': True, 'intel': False, 'amd': False}

        csv_output = _make_nvidia_csv((0, 'RTX 3080', 55, 2048, 10240, 70))
        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=csv_output)
            monitor.get_realtime_metrics()

        history = monitor.get_history(gpu_index=0)
        assert 0 in history
        assert len(history[0]) == 1
        assert history[0][0]['utilization_percent'] == 55.0


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
@pytest.mark.unittest
class TestHistory:

    def test_record_and_retrieve(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        gpus = [
            {'index': 0, 'utilization_percent': 50.0, 'memory_used_mb': 1024,
             'memory_total_mb': 8192, 'temperature_c': 60},
            {'index': 1, 'utilization_percent': 30.0, 'memory_used_mb': 512,
             'memory_total_mb': 4096, 'temperature_c': 45},
        ]
        monitor._record_history(gpus)

        all_history = monitor.get_history()
        assert 0 in all_history
        assert 1 in all_history
        assert len(all_history[0]) == 1
        assert all_history[0][0]['utilization_percent'] == 50.0
        assert all_history[1][0]['temperature_c'] == 45

    def test_get_history_single_gpu(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        gpus = [
            {'index': 0, 'utilization_percent': 50.0, 'memory_used_mb': 0,
             'memory_total_mb': 0, 'temperature_c': 0},
        ]
        monitor._record_history(gpus)
        history = monitor.get_history(gpu_index=0)
        assert 0 in history
        assert len(history) == 1

    def test_get_history_missing_gpu_returns_empty(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        history = monitor.get_history(gpu_index=99)
        assert history == {99: []}

    def test_history_respects_max_samples(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor, HISTORY_MAX_SAMPLES
        monitor = GpuMonitor()

        for i in range(HISTORY_MAX_SAMPLES + 20):
            monitor._record_history([{
                'index': 0, 'utilization_percent': float(i),
                'memory_used_mb': 0, 'memory_total_mb': 0, 'temperature_c': 0,
            }])

        history = monitor.get_history(gpu_index=0)
        assert len(history[0]) == HISTORY_MAX_SAMPLES
        # Oldest samples should have been evicted; newest is the last one recorded
        assert history[0][-1]['utilization_percent'] == float(HISTORY_MAX_SAMPLES + 19)

    def test_history_includes_timestamps(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        before = time.time()
        monitor._record_history([{
            'index': 0, 'utilization_percent': 10.0,
            'memory_used_mb': 0, 'memory_total_mb': 0, 'temperature_c': 0,
        }])
        after = time.time()

        history = monitor.get_history(gpu_index=0)
        ts = history[0][0]['timestamp']
        assert before <= ts <= after


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------
@pytest.mark.unittest
class TestErrorResilience:

    def test_nvidia_unexpected_exception(self, nvidia_only):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()

        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.side_effect = OSError("unexpected error")
            result = monitor._poll_nvidia()

        assert result == []

    def test_get_realtime_metrics_never_raises(self, no_backends):
        from compresso.libs.gpu_monitor import GpuMonitor
        monitor = GpuMonitor()
        # Force capability on, but make subprocess blow up
        monitor._capabilities = {'nvidia': True, 'intel': False, 'amd': False}

        with patch(GPU_MONITOR + '.subprocess.run') as mock_run:
            mock_run.side_effect = RuntimeError("catastrophic failure")
            # Should NOT raise
            result = monitor.get_realtime_metrics()

        assert result == []
