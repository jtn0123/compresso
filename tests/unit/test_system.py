#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_system.py

    Unit tests for compresso.libs.system.System.
"""

import logging
import subprocess
import sys

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singleton():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.fixture(autouse=True)
def mock_logger():
    logger = logging.getLogger('compresso_test_system')
    with patch('compresso.libs.logs.CompressoLogging.get_logger', return_value=logger):
        yield logger


@pytest.mark.unittest
class TestSystemInit:

    def test_creates_instance(self):
        from compresso.libs.system import System
        system = System()
        assert system is not None

    def test_singleton_returns_same_instance(self):
        from compresso.libs.system import System
        s1 = System()
        s2 = System()
        assert s1 is s2


@pytest.mark.unittest
class TestSystemInfo:

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'Test CPU', 'count': 4})
    @patch('compresso.libs.system.subprocess.run')
    @patch('compresso.libs.system.glob.glob', return_value=[])
    def test_info_returns_required_keys(self, mock_glob, mock_run, mock_cpuinfo):
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")
        from compresso.libs.system import System
        system = System()
        info = system.info()
        assert 'devices' in info
        assert 'platform' in info
        assert 'python' in info

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'Test CPU', 'count': 4})
    @patch('compresso.libs.system.subprocess.run')
    @patch('compresso.libs.system.glob.glob', return_value=[])
    def test_info_devices_has_cpu_and_gpu(self, mock_glob, mock_run, mock_cpuinfo):
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")
        from compresso.libs.system import System
        system = System()
        info = system.info()
        assert 'cpu_info' in info['devices']
        assert 'gpu_info' in info['devices']

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'Test CPU'})
    @patch('compresso.libs.system.subprocess.run')
    @patch('compresso.libs.system.glob.glob', return_value=[])
    def test_platform_is_uname(self, mock_glob, mock_run, mock_cpuinfo):
        mock_run.side_effect = FileNotFoundError
        from compresso.libs.system import System
        system = System()
        info = system.info()
        assert hasattr(info['platform'], 'system')
        assert hasattr(info['platform'], 'node')


@pytest.mark.unittest
class TestSystemGetPythonInfo:

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.subprocess.run', side_effect=FileNotFoundError)
    @patch('compresso.libs.system.glob.glob', return_value=[])
    def test_python_version_format(self, mock_glob, mock_run, mock_cpuinfo):
        from compresso.libs.system import System
        system = System()
        info = system.info()
        python_ver = info['python']
        # Should contain version info like "3.x.y.final.0"
        parts = python_ver.split('.')
        assert len(parts) == 5
        assert parts[0] == str(sys.version_info.major)
        assert parts[1] == str(sys.version_info.minor)


@pytest.mark.unittest
class TestSystemDetectGpus:

    @pytest.fixture(autouse=True)
    def force_linux_platform(self):
        with patch('compresso.libs.system.sys') as mock_sys, \
             patch('compresso.libs.system.os.name', 'posix'):
            mock_sys.platform = 'linux'
            yield

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.glob.glob', return_value=[])
    @patch('compresso.libs.system.subprocess.run')
    def test_nvidia_gpu_detected(self, mock_run, mock_glob, mock_cpuinfo):
        nvidia_output = "0, NVIDIA GeForce RTX 3080, 10240, 525.60.11"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=nvidia_output
        )
        from compresso.libs.system import System
        system = System()
        info = system.info()
        gpus = info['devices']['gpu_info']
        nvidia_gpus = [g for g in gpus if g['type'] == 'nvidia']
        assert len(nvidia_gpus) == 1
        assert nvidia_gpus[0]['name'] == 'NVIDIA GeForce RTX 3080'
        assert nvidia_gpus[0]['hwaccel'] == 'nvenc'
        assert nvidia_gpus[0]['index'] == 0
        assert nvidia_gpus[0]['memory_total_mb'] == 10240
        assert nvidia_gpus[0]['driver_version'] == '525.60.11'

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.glob.glob', return_value=['/dev/dri/renderD128', '/dev/dri/renderD129'])
    @patch('compresso.libs.system.subprocess.run')
    def test_vaapi_devices_detected(self, mock_run, mock_glob, mock_cpuinfo):
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")
        from compresso.libs.system import System
        system = System()
        info = system.info()
        gpus = info['devices']['gpu_info']
        vaapi_gpus = [g for g in gpus if g['type'] == 'vaapi']
        assert len(vaapi_gpus) == 2
        assert vaapi_gpus[0]['name'] == '/dev/dri/renderD128'
        assert vaapi_gpus[0]['hwaccel'] == 'vaapi'
        assert vaapi_gpus[1]['index'] == 1

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.glob.glob', return_value=[])
    @patch('compresso.libs.system.subprocess.run')
    def test_no_gpus_returns_empty(self, mock_run, mock_glob, mock_cpuinfo):
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")
        from compresso.libs.system import System
        system = System()
        info = system.info()
        assert info['devices']['gpu_info'] == []

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.glob.glob', return_value=[])
    @patch('compresso.libs.system.subprocess.run')
    def test_nvidia_smi_timeout(self, mock_run, mock_glob, mock_cpuinfo):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='nvidia-smi', timeout=10)
        from compresso.libs.system import System
        system = System()
        info = system.info()
        assert info['devices']['gpu_info'] == []

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.glob.glob', return_value=['/dev/dri/renderD128'])
    @patch('compresso.libs.system.subprocess.run')
    def test_nvidia_and_vaapi_both_detected(self, mock_run, mock_glob, mock_cpuinfo):
        nvidia_output = "0, GTX 1080, 8192, 470.82"
        mock_run.return_value = MagicMock(returncode=0, stdout=nvidia_output)
        from compresso.libs.system import System
        system = System()
        info = system.info()
        gpus = info['devices']['gpu_info']
        types = {g['type'] for g in gpus}
        assert types == {'nvidia', 'vaapi'}

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.glob.glob', return_value=[])
    @patch('compresso.libs.system.subprocess.run')
    def test_nvidia_smi_nonzero_returncode(self, mock_run, mock_glob, mock_cpuinfo):
        mock_run.return_value = MagicMock(returncode=1, stdout='')
        from compresso.libs.system import System
        system = System()
        info = system.info()
        assert info['devices']['gpu_info'] == []

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.glob.glob', return_value=[])
    @patch('compresso.libs.system.subprocess.run')
    def test_nvidia_multiple_gpus(self, mock_run, mock_glob, mock_cpuinfo):
        nvidia_output = "0, RTX 3090, 24576, 525.60\n1, RTX 3080, 10240, 525.60"
        mock_run.return_value = MagicMock(returncode=0, stdout=nvidia_output)
        from compresso.libs.system import System
        system = System()
        info = system.info()
        nvidia_gpus = [g for g in info['devices']['gpu_info'] if g['type'] == 'nvidia']
        assert len(nvidia_gpus) == 2
        assert nvidia_gpus[0]['index'] == 0
        assert nvidia_gpus[1]['index'] == 1


@pytest.mark.unittest
class TestSystemCaching:

    @patch('cpuinfo.get_cpu_info', return_value={'brand_raw': 'CPU'})
    @patch('compresso.libs.system.subprocess.run', side_effect=FileNotFoundError)
    @patch('compresso.libs.system.glob.glob', return_value=[])
    def test_devices_cached_after_first_call(self, mock_glob, mock_run, mock_cpuinfo):
        from compresso.libs.system import System
        system = System()
        info1 = system.info()
        info2 = system.info()
        # cpuinfo should only be called once due to caching
        assert mock_cpuinfo.call_count == 1
        assert info1['devices'] is info2['devices']
