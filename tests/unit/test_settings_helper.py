#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pytest
from unittest.mock import MagicMock, patch

from unmanic.webserver.helpers import settings


@pytest.mark.unittest
@patch('unmanic.webserver.helpers.settings.PluginExecutor')
@patch('unmanic.webserver.helpers.settings.plugins')
@patch('unmanic.webserver.helpers.settings.Library')
@patch('unmanic.webserver.helpers.settings.logger')
def test_save_library_config_warns_when_plugins_and_library_automation_are_enabled(
        mock_logger,
        mock_library_class,
        mock_plugins,
        mock_plugin_executor,
):
    mock_library = MagicMock()
    mock_library.get_enable_scanner.return_value = False
    mock_library.get_enable_inotify.return_value = False
    mock_library.get_name.return_value = 'Library'
    mock_library.get_path.return_value = '/library'
    mock_library.get_locked.return_value = False
    mock_library.get_enable_remote_only.return_value = False
    mock_library.get_priority_score.return_value = 0
    mock_library.get_tags.return_value = []
    mock_library.save.return_value = True
    mock_library_class.return_value = mock_library
    mock_plugins.check_if_plugin_is_installed.return_value = True
    mock_plugins.get_plugin_types_with_flows.return_value = []

    result = settings.save_library_config(
        1,
        library_config={
            'enable_scanner': True,
            'enable_inotify': False,
        },
        plugin_config={
            'enabled_plugins': [
                {'plugin_id': 'example_plugin', 'has_config': False},
            ],
        },
    )

    assert result is True
    mock_logger.warning.assert_called_once()
    assert 'PLUGIN_AUTOMATION_REVIEW_RECOMMENDED' in mock_logger.warning.call_args[0][0]
