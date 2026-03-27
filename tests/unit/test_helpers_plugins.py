#!/usr/bin/env python3

"""
tests.unit.test_helpers_plugins.py

Unit tests for compresso.webserver.helpers.plugins module.
Covers plugin helper functions for settings, listing, flows, and installation.
"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.mark.unittest
class TestPrepareFilteredPlugins:
    def test_returns_expected_structure(self):
        mock_plugins = MagicMock()
        mock_plugins.get_total_plugin_list_count.return_value = 2
        mock_query = MagicMock()
        mock_query.count.return_value = 2
        mock_plugins.get_plugin_list_filtered_and_sorted.return_value = mock_query

        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (None, None)

        with (
            patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_plugins),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import prepare_filtered_plugins

            result = prepare_filtered_plugins({"start": 0, "length": 10})
        assert "recordsTotal" in result
        assert "recordsFiltered" in result
        assert "results" in result

    def test_plugin_with_settings_has_config(self):
        mock_plugins = MagicMock()
        mock_plugins.get_total_plugin_list_count.return_value = 1
        plugin_data = iter(
            [
                {
                    "id": 1,
                    "plugin_id": "test_plugin",
                    "icon": "",
                    "name": "Test",
                    "description": "A test plugin",
                    "tags": "test",
                    "author": "Author",
                    "version": "1.0",
                    "update_available": False,
                }
            ]
        )
        mock_query = MagicMock()
        mock_query.count.return_value = 1
        mock_query.__iter__ = lambda self: plugin_data
        mock_plugins.get_plugin_list_filtered_and_sorted.return_value = mock_query

        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = ({"setting1": "value1"}, {})

        with (
            patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_plugins),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import prepare_filtered_plugins

            result = prepare_filtered_plugins({"start": 0, "length": 10})
        assert result["results"][0]["has_config"] is True


@pytest.mark.unittest
class TestGetPluginTypesWithFlows:
    def test_delegates_to_handler(self):
        with patch("compresso.webserver.helpers.plugins.PluginsHandler") as mock_cls:
            mock_cls.get_plugin_types_with_flows.return_value = ["library_management.file_test"]
            from compresso.webserver.helpers.plugins import get_plugin_types_with_flows

            result = get_plugin_types_with_flows()
        assert result == ["library_management.file_test"]


@pytest.mark.unittest
class TestGetEnabledPluginFlows:
    def test_returns_flow_list(self):
        mock_handler = MagicMock()
        mock_handler.get_enabled_plugin_flows_for_plugin_type.return_value = [{"plugin_id": "p1", "name": "P1"}]
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import get_enabled_plugin_flows_for_plugin_type

            result = get_enabled_plugin_flows_for_plugin_type("worker.process", 1)
        assert len(result) == 1


@pytest.mark.unittest
class TestGetEnabledPluginDataPanels:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.get_enabled_plugin_modules_by_type.return_value = []
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import get_enabled_plugin_data_panels

            get_enabled_plugin_data_panels()
        mock_handler.get_enabled_plugin_modules_by_type.assert_called_with("frontend.panel")


@pytest.mark.unittest
class TestExecDataPanelsRunner:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.exec_plugin_runner.return_value = True
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import exec_data_panels_plugin_runner

            exec_data_panels_plugin_runner({}, "p1")
        mock_handler.exec_plugin_runner.assert_called_with({}, "p1", "frontend.panel")


@pytest.mark.unittest
class TestGetEnabledPluginApis:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.get_enabled_plugin_modules_by_type.return_value = []
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import get_enabled_plugin_plugin_apis

            get_enabled_plugin_plugin_apis()
        mock_handler.get_enabled_plugin_modules_by_type.assert_called_with("frontend.plugin_api")


@pytest.mark.unittest
class TestExecPluginApiRunner:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.exec_plugin_runner.return_value = True
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import exec_plugin_api_plugin_runner

            exec_plugin_api_plugin_runner({}, "p1")
        mock_handler.exec_plugin_runner.assert_called_with({}, "p1", "frontend.plugin_api")


@pytest.mark.unittest
class TestSaveEnabledPluginFlows:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.set_plugin_flow.return_value = True
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import save_enabled_plugin_flows_for_plugin_type

            result = save_enabled_plugin_flows_for_plugin_type("worker.process", 1, [])
        assert result is True


@pytest.mark.unittest
class TestRemovePlugins:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.uninstall_plugins_by_db_table_id.return_value = True
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import remove_plugins

            result = remove_plugins([1, 2])
        assert result is True


@pytest.mark.unittest
class TestUpdatePlugins:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.update_plugins_by_db_table_id.return_value = True
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import update_plugins

            result = update_plugins([1])
        assert result is True


@pytest.mark.unittest
class TestGetPluginSettings:
    def test_text_input_default(self):
        mock_session = MagicMock()
        mock_session.level = 0
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (
            {"option1": "value1"},
            {"option1": {"input_type": None, "label": "Option 1", "description": "Desc"}},
        )
        with (
            patch("compresso.libs.session.Session", return_value=mock_session),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import get_plugin_settings

            result = get_plugin_settings("test_plugin")
        assert len(result) == 1
        assert result[0]["input_type"] == "text"

    def test_checkbox_for_bool_value(self):
        mock_session = MagicMock()
        mock_session.level = 0
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (
            {"enabled": True},
            {"enabled": {}},
        )
        with (
            patch("compresso.libs.session.Session", return_value=mock_session),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import get_plugin_settings

            result = get_plugin_settings("test_plugin")
        assert result[0]["input_type"] == "checkbox"

    def test_select_reverts_to_text_without_options(self):
        mock_session = MagicMock()
        mock_session.level = 0
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (
            {"choice": "a"},
            {"choice": {"input_type": "select", "select_options": []}},
        )
        with (
            patch("compresso.libs.session.Session", return_value=mock_session),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import get_plugin_settings

            result = get_plugin_settings("test_plugin")
        assert result[0]["input_type"] == "text"

    def test_slider_reverts_to_text_without_options(self):
        mock_session = MagicMock()
        mock_session.level = 0
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (
            {"quality": 50},
            {"quality": {"input_type": "slider"}},
        )
        with (
            patch("compresso.libs.session.Session", return_value=mock_session),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import get_plugin_settings

            result = get_plugin_settings("test_plugin")
        assert result[0]["input_type"] == "text"

    def test_slider_with_options(self):
        mock_session = MagicMock()
        mock_session.level = 0
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (
            {"quality": 50},
            {"quality": {"input_type": "slider", "slider_options": {"min": "0", "max": "100", "step": "5"}}},
        )
        with (
            patch("compresso.libs.session.Session", return_value=mock_session),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import get_plugin_settings

            result = get_plugin_settings("test_plugin")
        assert result[0]["input_type"] == "slider"
        assert result[0]["slider_options"]["min"] == "0"

    def test_unsupported_input_type_falls_back(self):
        mock_session = MagicMock()
        mock_session.level = 0
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (
            {"field": "val"},
            {"field": {"input_type": "color_picker"}},
        )
        with (
            patch("compresso.libs.session.Session", return_value=mock_session),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import get_plugin_settings

            result = get_plugin_settings("test_plugin")
        assert result[0]["input_type"] == "text"

    def test_req_lev_disables_setting(self):
        mock_session = MagicMock()
        mock_session.level = 0
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (
            {"premium": "val"},
            {"premium": {"input_type": "text", "req_lev": 5, "description": "Premium option"}},
        )
        with (
            patch("compresso.libs.session.Session", return_value=mock_session),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import get_plugin_settings

            result = get_plugin_settings("test_plugin")
        assert result[0]["display"] == "disabled"

    def test_empty_settings(self):
        mock_session = MagicMock()
        mock_session.level = 0
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (None, None)
        with (
            patch("compresso.libs.session.Session", return_value=mock_session),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import get_plugin_settings

            result = get_plugin_settings("test_plugin")
        assert result == []


@pytest.mark.unittest
class TestUpdatePluginSettings:
    def test_returns_false_no_plugin_data(self):
        with patch("compresso.webserver.helpers.plugins.prepare_plugin_info_and_settings", return_value={}):
            from compresso.webserver.helpers.plugins import update_plugin_settings

            result = update_plugin_settings("test_plugin", [])
        assert result is False

    def test_skips_section_headers(self):
        plugin_data = {"plugin_id": "test_plugin", "settings": []}
        mock_pe = MagicMock()
        mock_pe.save_plugin_settings.return_value = True
        with (
            patch("compresso.webserver.helpers.plugins.prepare_plugin_info_and_settings", return_value=plugin_data),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import update_plugin_settings

            result = update_plugin_settings(
                "test_plugin",
                [
                    {"key": "header", "input_type": "section_header", "value": "Header"},
                    {"key": "opt", "input_type": "text", "value": "hello"},
                ],
            )
        assert result is True

    def test_converts_checkbox_string_to_bool(self):
        plugin_data = {"plugin_id": "test_plugin"}
        mock_pe = MagicMock()
        mock_pe.save_plugin_settings.return_value = True
        with (
            patch("compresso.webserver.helpers.plugins.prepare_plugin_info_and_settings", return_value=plugin_data),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
        ):
            from compresso.webserver.helpers.plugins import update_plugin_settings

            update_plugin_settings(
                "test_plugin",
                [
                    {"key": "enabled", "input_type": "checkbox", "value": "true"},
                ],
            )
        saved = mock_pe.save_plugin_settings.call_args[0][1]
        assert saved["enabled"] is True


@pytest.mark.unittest
class TestResetPluginSettings:
    def test_returns_false_no_plugin(self):
        with patch("compresso.webserver.helpers.plugins.prepare_plugin_info_and_settings", return_value={}):
            from compresso.webserver.helpers.plugins import reset_plugin_settings

            result = reset_plugin_settings("nonexistent")
        assert result is False


@pytest.mark.unittest
class TestCheckIfPluginInstalled:
    def test_installed_returns_true(self):
        mock_handler = MagicMock()
        mock_handler.get_plugin_list_filtered_and_sorted.return_value = [{"id": 1}]
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import check_if_plugin_is_installed

            assert check_if_plugin_is_installed("test") is True

    def test_not_installed_returns_false(self):
        mock_handler = MagicMock()
        mock_handler.get_plugin_list_filtered_and_sorted.return_value = []
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import check_if_plugin_is_installed

            assert check_if_plugin_is_installed("missing") is False


@pytest.mark.unittest
class TestPreparePluginReposList:
    def test_excludes_default_repo(self):
        mock_handler = MagicMock()
        mock_handler.get_plugin_repos.return_value = [
            {"path": "default"},
            {"path": "https://custom.repo"},
        ]
        mock_handler.get_default_repo.return_value = "default"
        mock_handler.get_plugin_repo_id.return_value = 1
        mock_handler.read_repo_data.return_value = {"repo": {"name": "Custom"}}
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import prepare_plugin_repos_list

            result = prepare_plugin_repos_list()
        assert len(result) == 1
        assert result[0]["name"] == "Custom"


@pytest.mark.unittest
class TestReloadPluginReposData:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.update_plugin_repos.return_value = True
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import reload_plugin_repos_data

            result = reload_plugin_repos_data()
        assert result is True


@pytest.mark.unittest
class TestInstallPluginById:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.install_plugin_by_id.return_value = True
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import install_plugin_by_id

            result = install_plugin_by_id("my_plugin", repo_id=1)
        assert result is True


@pytest.mark.unittest
class TestSavePluginReposList:
    def test_delegates_to_handler(self):
        mock_handler = MagicMock()
        mock_handler.set_plugin_repos.return_value = True
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import save_plugin_repos_list

            result = save_plugin_repos_list(["https://repo.com"])
        assert result is True


@pytest.mark.unittest
class TestPreparePluginInfoAndSettings:
    def test_installed_plugin(self):
        mock_handler = MagicMock()
        mock_handler.get_plugin_list_filtered_and_sorted.return_value = [
            {
                "id": 1,
                "plugin_id": "p1",
                "icon": "",
                "name": "P1",
                "description": "Desc",
                "tags": "",
                "author": "A",
                "version": "1.0",
                "update_available": False,
            }
        ]
        mock_pe = MagicMock()
        mock_pe.get_plugin_settings.return_value = (None, None)
        mock_pe.get_plugin_changelog.return_value = ["# v1.0"]
        mock_pe.get_plugin_long_description.return_value = ["Long desc"]
        with (
            patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler),
            patch("compresso.webserver.helpers.plugins.PluginExecutor", return_value=mock_pe),
            patch("compresso.libs.session.Session") as mock_session_cls,
        ):
            mock_session_cls.return_value.level = 0
            mock_session_cls.return_value.register_compresso = MagicMock()
            from compresso.webserver.helpers.plugins import prepare_plugin_info_and_settings

            result = prepare_plugin_info_and_settings("p1")
        assert result["plugin_id"] == "p1"

    def test_not_installed_fetches_from_repo(self):
        mock_handler = MagicMock()
        mock_handler.get_plugin_list_filtered_and_sorted.return_value = []
        mock_handler.get_installable_plugins_list.return_value = [
            {
                "plugin_id": "p2",
                "icon": "",
                "name": "P2",
                "description": "Desc",
                "tags": "",
                "author": "B",
                "version": "2.0",
                "changelog_url": "http://example.com/cl.md",
            }
        ]
        mock_handler.read_remote_changelog_file.return_value = "# Changelog"
        with patch("compresso.webserver.helpers.plugins.PluginsHandler", return_value=mock_handler):
            from compresso.webserver.helpers.plugins import prepare_plugin_info_and_settings

            result = prepare_plugin_info_and_settings("p2")
        assert result["plugin_id"] == "p2"
