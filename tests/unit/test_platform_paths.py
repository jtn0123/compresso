#!/usr/bin/env python3

"""
Tests for platform-specific default path functions in compresso.libs.common.
"""

import os
from unittest.mock import patch

import pytest


@pytest.mark.unittest
class TestGetDefaultLibraryPath:
    def test_macos_returns_movies(self):
        with patch("compresso.libs.common.sys") as mock_sys, patch("compresso.libs.common.os.name", "posix"):
            mock_sys.platform = "darwin"
            from compresso.libs.common import get_default_library_path

            result = get_default_library_path()
            assert result.endswith(os.path.join("Movies"))
            assert os.path.expanduser("~") in result

    def test_windows_returns_documents(self):
        with (
            patch("compresso.libs.common.sys") as mock_sys,
            patch("compresso.libs.common.os.name", "nt"),
            patch("compresso.libs.common.os.path.expandvars", return_value=r"C:\Users\test"),
        ):
            mock_sys.platform = "win32"
            from compresso.libs.common import get_default_library_path

            result = get_default_library_path()
            assert result.endswith("Documents")

    def test_linux_returns_library(self):
        with patch("compresso.libs.common.sys") as mock_sys, patch("compresso.libs.common.os.name", "posix"):
            mock_sys.platform = "linux"
            from compresso.libs.common import get_default_library_path

            result = get_default_library_path()
            assert result.endswith("library")


@pytest.mark.unittest
class TestGetDefaultCachePath:
    def test_macos_returns_library_caches(self):
        with patch("compresso.libs.common.sys") as mock_sys, patch("compresso.libs.common.os.name", "posix"):
            mock_sys.platform = "darwin"
            from compresso.libs.common import get_default_cache_path

            result = get_default_cache_path()
            assert "Library" in result
            assert "Caches" in result
            assert "Compresso" in result

    def test_windows_returns_localappdata(self):
        with (
            patch("compresso.libs.common.sys") as mock_sys,
            patch("compresso.libs.common.os.name", "nt"),
            patch("compresso.libs.common.os.path.expandvars", return_value=r"C:\Users\test\AppData\Local\Temp"),
        ):
            mock_sys.platform = "win32"
            from compresso.libs.common import get_default_cache_path

            result = get_default_cache_path()
            assert "Compresso" in result

    def test_linux_returns_tmp(self):
        with patch("compresso.libs.common.sys") as mock_sys, patch("compresso.libs.common.os.name", "posix"):
            mock_sys.platform = "linux"
            from compresso.libs.common import get_default_cache_path

            result = get_default_cache_path()
            assert "tmp" in result
            assert "compresso" in result
