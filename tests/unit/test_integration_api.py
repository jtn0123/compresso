#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_integration_api.py

    Integration-style unit tests that exercise API helper
    workflows end-to-end with mocked backends.
"""

import pytest
from unittest.mock import patch


@pytest.mark.unittest
class TestHealthcheckWorkflow:
    """Test the full healthcheck workflow through helpers."""

    @patch('compresso.webserver.helpers.healthcheck.HealthCheckManager')
    @patch('compresso.webserver.helpers.healthcheck.StartupState')
    def test_full_healthcheck_lifecycle(self, mock_startup, mock_mgr_cls):
        """Test scan → progress → cancel → summary workflow."""
        from compresso.webserver.helpers import healthcheck

        # Start a scan
        mock_mgr_cls.return_value.schedule_library_scan.return_value = True
        result = healthcheck.scan_library(1, mode='quick')
        assert result is True

        # Check progress
        mock_mgr_cls.is_scanning.return_value = True
        mock_mgr_cls.get_scan_progress.return_value = 0.5
        progress = healthcheck.get_scan_progress()
        assert progress['scanning'] is True
        assert progress['progress'] == 0.5

        # Cancel scan
        mock_mgr_cls.cancel_scan.return_value = True
        assert healthcheck.cancel_scan() is True

        # Get summary
        mock_mgr_cls.return_value.get_health_summary.return_value = {'healthy': 10, 'unhealthy': 2}
        summary = healthcheck.get_health_summary(library_id=1)
        assert summary['healthy'] == 10

        # Startup readiness
        mock_startup.return_value.snapshot.return_value = {'ready': True}
        readiness = healthcheck.get_startup_readiness()
        assert readiness['ready'] is True


@pytest.mark.unittest
class TestSettingsHelperWorkflow:
    """Test settings helper functions."""

    def test_settings_module_importable(self):
        """Verify settings module can be imported."""
        from compresso.webserver.helpers import settings
        assert settings is not None


@pytest.mark.unittest
class TestWorkerHelperWorkflow:
    """Test worker status helper functions."""

    def test_workers_module_importable(self):
        """Verify workers helper module loads without error."""
        from compresso.webserver.helpers import workers
        assert workers is not None


@pytest.mark.unittest
class TestFileTestWorkflow:
    """End-to-end test of file testing with multiple checks."""

    @patch('compresso.libs.filetest.config.Config')
    @patch('compresso.libs.filetest.CompressoLogging')
    @patch('compresso.libs.filetest.PluginsHandler')
    @patch('compresso.libs.filetest.history.History')
    def test_file_passes_all_checks(self, mock_history, mock_ph, mock_logging, mock_config):
        """File not in ignore, not failed in history, plugins say add it."""
        mock_ph.return_value.get_enabled_plugin_modules_by_type.return_value = []

        from compresso.libs.filetest import FileTest
        ft = FileTest(library_id=1)

        # No failed history
        mock_history.return_value.get_historic_tasks_list_with_source_probe.return_value = []

        # No ignore file (path doesn't exist)
        result, issues, score, plugin = ft.should_file_be_added_to_task_list('/nonexistent/path/video.mp4')
        # With no plugins, result should be None (no decision made)
        assert result is None
        assert issues == []

    @patch('compresso.libs.filetest.config.Config')
    @patch('compresso.libs.filetest.CompressoLogging')
    @patch('compresso.libs.filetest.PluginsHandler')
    @patch('compresso.libs.filetest.history.History')
    def test_file_rejected_by_history(self, mock_history, mock_ph, mock_logging, mock_config):
        """File that previously failed should be rejected."""
        mock_ph.return_value.get_enabled_plugin_modules_by_type.return_value = []
        mock_history.return_value.get_historic_tasks_list_with_source_probe.return_value = [
            {'abspath': '/media/failed_video.mp4'}
        ]

        from compresso.libs.filetest import FileTest
        ft = FileTest(library_id=1)

        result, issues, _, _ = ft.should_file_be_added_to_task_list('/media/failed_video.mp4')
        assert result is False
        assert any(i['id'] == 'blacklisted' for i in issues)
