#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.system.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     05 Mar 2021, (11:00 PM)

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

           THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
           EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
           MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
           IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
           DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
           OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
           OR OTHER DEALINGS IN THE SOFTWARE.

"""
import glob
import subprocess

from compresso.libs.logs import CompressoLogging
from compresso.libs.singleton import SingletonType


class System(object, metaclass=SingletonType):
    devices = {}
    ffmpeg = {}
    platform = {}
    python_version = {}

    def __init__(self, *args, **kwargs):
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)

    def __get_python_info(self):
        """
        Return a string of the python version

        :return:
        """
        import sys
        if not self.python_version:
            self.python_version = "{0}.{1}.{2}.{3}.{4}".format(*sys.version_info)
        return self.python_version

    def __detect_gpus(self):
        """
        Detect available GPUs on the system.
        Returns a list of GPU info dicts.

        :return:
        """
        gpus = []

        # NVIDIA detection via nvidia-smi
        try:
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=index,name,memory.total,driver_version', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if not line.strip():
                        continue
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 4:
                        gpus.append({
                            'type': 'nvidia',
                            'hwaccel': 'nvenc',
                            'index': int(parts[0]),
                            'name': parts[1],
                            'memory_total_mb': int(float(parts[2])),
                            'driver_version': parts[3],
                        })
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
            self.logger.debug('NVIDIA GPU detection skipped: %s', str(e))

        # VAAPI detection via /dev/dri/render* devices
        try:
            render_devices = sorted(glob.glob('/dev/dri/render*'))
            for i, device_path in enumerate(render_devices):
                gpus.append({
                    'type': 'vaapi',
                    'hwaccel': 'vaapi',
                    'index': i,
                    'name': device_path,
                    'memory_total_mb': 0,
                    'driver_version': '',
                })
        except Exception as e:
            self.logger.debug('VAAPI GPU detection skipped: %s', str(e))

        return gpus

    def __get_devices_info(self):
        """
        Return a dictionary of device information

        :return:
        """
        import cpuinfo
        if not self.devices:
            self.devices = {
                "cpu_info": cpuinfo.get_cpu_info(),
                "gpu_info": self.__detect_gpus(),
            }
        return self.devices

    def __get_platform_info(self):
        """
        Return a dictionary of device information

        :return:
        """
        import platform
        if not self.platform:
            self.platform = platform.uname()
        return self.platform

    def info(self):
        """
        Returns a dictionary of system information

        :return:
        """
        info = {
            "devices":  self.__get_devices_info(),
            "platform": self.__get_platform_info(),
            "python":   self.__get_python_info(),
        }
        return info


if __name__ == "__main__":
    import json
    import sys
    import os

    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(project_dir)
    sys.path.append(project_dir)
    system = System()
    print(json.dumps(system.info(), indent=2))
