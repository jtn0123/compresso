#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Tests for FFmpeg startup validation in compresso.libs.startup.
"""

from unittest.mock import patch, MagicMock

import pytest

from compresso.libs.startup import _validate_ffmpeg


@pytest.mark.unittest
class TestValidateFfmpeg:

    def test_returns_paths_when_found(self):
        with patch('compresso.libs.startup.shutil.which') as mock_which, \
             patch('compresso.libs.startup.subprocess.run') as mock_run:
            mock_which.side_effect = lambda cmd: '/usr/bin/' + cmd
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='ffmpeg version 7.0.1 Copyright (c) 2000-2024\n'
            )
            result = _validate_ffmpeg()
            assert result['ffmpeg'] == '/usr/bin/ffmpeg'
            assert result['ffprobe'] == '/usr/bin/ffprobe'
            assert 'ffmpeg version 7.0.1' in result['version']

    def test_returns_none_when_missing(self):
        with patch('compresso.libs.startup.shutil.which', return_value=None), \
             patch('compresso.libs.startup.logger') as mock_logger:
            result = _validate_ffmpeg()
            assert result['ffmpeg'] is None
            assert result['ffprobe'] is None
            assert result['version'] is None
            mock_logger.warning.assert_called_once()

    def test_warns_with_macos_hint(self):
        with patch('compresso.libs.startup.shutil.which', return_value=None), \
             patch('compresso.libs.startup.sys') as mock_sys, \
             patch('compresso.libs.startup.os.name', 'posix'), \
             patch('compresso.libs.startup.logger') as mock_logger:
            mock_sys.platform = 'darwin'
            _validate_ffmpeg()
            warning_msg = mock_logger.warning.call_args[0][2]
            assert 'brew' in warning_msg

    def test_warns_with_windows_hint(self):
        with patch('compresso.libs.startup.shutil.which', return_value=None), \
             patch('compresso.libs.startup.sys') as mock_sys, \
             patch('compresso.libs.startup.os.name', 'nt'), \
             patch('compresso.libs.startup.logger') as mock_logger:
            mock_sys.platform = 'win32'
            _validate_ffmpeg()
            warning_msg = mock_logger.warning.call_args[0][2]
            assert 'winget' in warning_msg

    def test_warns_with_linux_hint(self):
        with patch('compresso.libs.startup.shutil.which', return_value=None), \
             patch('compresso.libs.startup.sys') as mock_sys, \
             patch('compresso.libs.startup.os.name', 'posix'), \
             patch('compresso.libs.startup.logger') as mock_logger:
            mock_sys.platform = 'linux'
            _validate_ffmpeg()
            warning_msg = mock_logger.warning.call_args[0][2]
            assert 'apt' in warning_msg

    def test_handles_version_check_failure(self):
        with patch('compresso.libs.startup.shutil.which') as mock_which, \
             patch('compresso.libs.startup.subprocess.run', side_effect=FileNotFoundError), \
             patch('compresso.libs.startup.logger') as mock_logger:
            mock_which.side_effect = lambda cmd: '/usr/bin/' + cmd
            result = _validate_ffmpeg()
            assert result['ffmpeg'] == '/usr/bin/ffmpeg'
            assert result['version'] is None
            mock_logger.warning.assert_called_once()

    def test_handles_partial_missing(self):
        """Test when ffmpeg is found but ffprobe is not."""
        def which_side_effect(cmd):
            return '/usr/bin/ffmpeg' if cmd == 'ffmpeg' else None

        with patch('compresso.libs.startup.shutil.which', side_effect=which_side_effect), \
             patch('compresso.libs.startup.logger') as mock_logger:
            result = _validate_ffmpeg()
            assert result['ffmpeg'] == '/usr/bin/ffmpeg'
            assert result['ffprobe'] is None
            mock_logger.warning.assert_called_once()
            warning_args = mock_logger.warning.call_args[0][1]
            assert 'ffprobe' in warning_args
