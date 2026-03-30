#!/usr/bin/env python3

"""
tests.unit.test_plugins_coverage.py

Focused unit tests covering ONLY the lines not already covered by
test_plugins_extended.py and test_plugins_handler.py.

Target lines: 72-73, 161, 172, 187-188, 192-210, 389-390, 426-429,
468-476, 487-511, 523, 555-556, 561-581, 584-585, 599-655, 658-672,
682-717, 720-732, 744-766, 795-817, 828-829, 838-891, 900-907,
917-929, 939-942
"""

import json
import os
import subprocess
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_handler(tmp_path):
    """Create a PluginsHandler with mocked settings pointing at tmp_path."""
    with patch("compresso.libs.plugins.config") as mock_config_mod:
        mock_settings = MagicMock()
        mock_settings.get_plugins_path.return_value = str(tmp_path / "plugins")
        mock_config_mod.Config.return_value = mock_settings
        with patch("compresso.libs.plugins.CompressoLogging"):
            from compresso.libs.plugins import PluginsHandler

            handler = PluginsHandler()
    return handler


# ---------------------------------------------------------------------------
# Lines 72-73: _log method
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestLogMethod:
    def test_log_calls_format_message_and_delegates_to_logger(self, tmp_path):
        """_log must format the message then call the named log level on self.logger."""
        handler = _make_handler(tmp_path)
        mock_logger = MagicMock()
        handler.logger = mock_logger

        with patch("compresso.libs.plugins.common") as mock_common:
            mock_common.format_message.return_value = "formatted: hello world"
            handler._log("hello", "world", level="info")

        mock_common.format_message.assert_called_once_with("hello", "world")
        mock_logger.info.assert_called_once_with("formatted: hello world")

    def test_log_uses_warning_level(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_logger = MagicMock()
        handler.logger = mock_logger

        with patch("compresso.libs.plugins.common") as mock_common:
            mock_common.format_message.return_value = "warn msg"
            handler._log("warn msg", level="warning")

        mock_logger.warning.assert_called_once_with("warn msg")

    def test_log_default_level_is_info(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_logger = MagicMock()
        handler.logger = mock_logger

        with patch("compresso.libs.plugins.common") as mock_common:
            mock_common.format_message.return_value = "default"
            handler._log("default")

        mock_logger.info.assert_called_once_with("default")


# ---------------------------------------------------------------------------
# Line 161: fetch_remote_repo_data — status_code >= 500
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFetchRemoteRepoData500:
    def test_logs_debug_on_500_response(self, tmp_path):
        """A 500+ response should call logger.debug and still return data (None)."""
        handler = _make_handler(tmp_path)
        mock_session = MagicMock()
        mock_session.get_installation_uuid.return_value = "uuid"
        mock_session.get_supporter_level.return_value = 0
        mock_session.api_get.return_value = (None, 503)

        with patch("compresso.libs.plugins.Session", return_value=mock_session):
            result = handler.fetch_remote_repo_data("default")

        # The method returns data (None in this case) and logs a debug message
        assert result is None
        handler.logger.debug.assert_called()


# ---------------------------------------------------------------------------
# Line 172: update_plugin_repos — plugins_directory creation branch
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUpdatePluginReposDirectoryCreation:
    def test_creates_plugins_directory_if_missing(self, tmp_path):
        """update_plugin_repos should create the plugins dir when it does not exist."""
        handler = _make_handler(tmp_path)
        plugins_dir = str(tmp_path / "new_plugins_dir")
        handler.settings.get_plugins_path.return_value = plugins_dir

        with (
            patch.object(handler, "get_plugin_repos", return_value=[]),
            patch("compresso.libs.plugins.os.path.exists", return_value=False),
            patch("compresso.libs.plugins.os.makedirs") as mock_makedirs,
        ):
            handler.update_plugin_repos()

        mock_makedirs.assert_called_once_with(plugins_dir)


# ---------------------------------------------------------------------------
# Lines 187-188: update_plugin_repos — JSONDecodeError branch
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUpdatePluginReposJsonDecodeError:
    def test_logs_error_on_json_decode_error(self, tmp_path):
        """A JSONDecodeError while writing the cache file should be caught and logged."""
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)

        with (
            patch.object(handler, "get_plugin_repos", return_value=[{"path": "default"}]),
            patch.object(handler, "fetch_remote_repo_data", return_value={"repo": {}}),
            patch.object(handler, "get_repo_cache_file", return_value=str(plugins_dir / "repo-0.json")),
            patch("compresso.libs.plugins.os.path.exists", return_value=True),
            patch("compresso.libs.plugins.json.dump", side_effect=json.JSONDecodeError("bad", "", 0)),
        ):
            result = handler.update_plugin_repos()

        assert result is True
        handler.logger.error.assert_called()


# ---------------------------------------------------------------------------
# Lines 192-210: get_settings_of_all_installed_plugins
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetSettingsOfAllInstalledPlugins:
    def test_returns_dict_of_plugin_settings(self, tmp_path):
        handler = _make_handler(tmp_path)
        fake_plugins = [
            {"plugin_id": "plugin_a"},
            {"plugin_id": "plugin_b"},
        ]
        mock_executor = MagicMock()
        mock_executor.get_plugin_settings.side_effect = [
            ({"setting1": "val1"}, {}),
            ({"setting2": "val2"}, {}),
        ]

        with (
            patch.object(handler, "get_plugin_list_filtered_and_sorted", return_value=fake_plugins),
            patch("compresso.libs.plugins.PluginExecutor", return_value=mock_executor),
        ):
            result = handler.get_settings_of_all_installed_plugins()

        assert result == {
            "plugin_a": {"setting1": "val1"},
            "plugin_b": {"setting2": "val2"},
        }

    def test_returns_empty_dict_when_no_plugins_installed(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_executor = MagicMock()

        with (
            patch.object(handler, "get_plugin_list_filtered_and_sorted", return_value=[]),
            patch("compresso.libs.plugins.PluginExecutor", return_value=mock_executor),
        ):
            result = handler.get_settings_of_all_installed_plugins()

        assert result == {}
        mock_executor.get_plugin_settings.assert_not_called()


# ---------------------------------------------------------------------------
# Lines 389-390: install_plugin_by_id — exception during DB write
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestInstallPluginByIdException:
    def test_returns_false_on_exception_during_db_write(self, tmp_path):
        """If write_plugin_data_to_db raises, the exception is logged and False is returned."""
        handler = _make_handler(tmp_path)
        plugin = {"plugin_id": "test_plugin", "name": "Test", "version": "1.0"}

        with (
            patch.object(handler, "get_installable_plugins_list", return_value=[plugin]),
            patch.object(handler, "download_and_install_plugin", return_value=True),
            patch.object(handler, "get_plugin_path", return_value=str(tmp_path / "plugins" / "test_plugin")),
            patch.object(handler, "write_plugin_data_to_db", side_effect=RuntimeError("db failure")),
            patch("compresso.libs.plugins.PluginExecutor"),
        ):
            result = handler.install_plugin_by_id("test_plugin")

        assert result is False
        handler.logger.exception.assert_called()


# ---------------------------------------------------------------------------
# Lines 426-429: install_plugin_from_path_on_disk — exception branch
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestInstallPluginFromPathException:
    def test_returns_false_on_exception_during_install(self, tmp_path):
        """If install_plugin raises, the exception is caught, logged, and False returned."""
        zip_path = tmp_path / "plugin.zip"
        info = {"id": "my_plugin", "name": "My Plugin", "version": "1.0"}
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("info.json", json.dumps(info))

        handler = _make_handler(tmp_path)

        with patch.object(handler, "install_plugin", side_effect=Exception("extraction failed")):
            result = handler.install_plugin_from_path_on_disk(str(zip_path))

        assert result is False
        handler.logger.exception.assert_called()


# ---------------------------------------------------------------------------
# Lines 468-476: download_plugin
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestDownloadPlugin:
    def test_downloads_file_to_cache_path(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin = {"plugin_id": "my_plugin", "version": "1.0", "package_url": "http://example.com/plugin.zip"}
        expected_dest = str(plugins_dir / "my_plugin-1.0.zip")

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_content.return_value = [b"data_chunk"]

        mock_session = MagicMock()
        mock_session.requests_session.get.return_value = mock_response

        with patch("compresso.libs.plugins.Session", return_value=mock_session):
            dest = handler.download_plugin(plugin)

        assert dest == expected_dest
        assert os.path.exists(expected_dest)


# ---------------------------------------------------------------------------
# Lines 487-511: install_plugin — with and without plugin_id
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestInstallPlugin:
    def test_install_plugin_reads_id_from_zip_when_no_plugin_id(self, tmp_path):
        """When no plugin_id is provided, the id must be read from info.json inside the zip."""
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin_id = "auto_detected_plugin"
        info = {"id": plugin_id, "name": "Auto Plugin", "version": "1.0", "compatibility": [2]}
        zip_path = tmp_path / "auto_plugin.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("info.json", json.dumps(info))

        plugin_dir = plugins_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "info.json").write_text(json.dumps(info))

        with patch("subprocess.call"):
            result = handler.install_plugin(str(zip_path))

        assert result.get("id") == plugin_id

    def test_install_plugin_uses_provided_plugin_id(self, tmp_path):
        """When plugin_id is provided, it must be used without reading from the zip."""
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin_id = "explicit_plugin"
        info = {"id": plugin_id, "name": "Explicit Plugin", "version": "1.0", "compatibility": [2]}
        zip_path = tmp_path / "explicit_plugin.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("info.json", json.dumps(info))

        plugin_dir = plugins_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "info.json").write_text(json.dumps(info))

        with patch("subprocess.call"):
            result = handler.install_plugin(str(zip_path), plugin_id=plugin_id)

        assert result.get("id") == plugin_id

    def test_install_plugin_raises_when_git_repo_present(self, tmp_path):
        """install_plugin must raise if the target directory contains a .git folder."""
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin_id = "dev_plugin"
        info = {"id": plugin_id, "name": "Dev Plugin", "version": "1.0"}
        zip_path = tmp_path / "dev_plugin.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("info.json", json.dumps(info))

        # Simulate a git repository in the plugin directory
        plugin_dir = plugins_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / ".git").mkdir()

        with pytest.raises(Exception, match="git repository"):
            handler.install_plugin(str(zip_path), plugin_id=plugin_id)

    def test_install_plugin_with_defer_dependency_install(self, tmp_path):
        """If defer_dependency_install is True, requirements and npm are installed."""
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin_id = "deferred_plugin"
        info = {"id": plugin_id, "name": "Deferred", "version": "1.0", "defer_dependency_install": True}
        zip_path = tmp_path / "deferred_plugin.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("info.json", json.dumps(info))

        plugin_dir = plugins_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "info.json").write_text(json.dumps(info))

        with (
            patch.object(handler, "install_plugin_requirements") as mock_req,
            patch.object(handler, "install_npm_modules") as mock_npm,
        ):
            handler.install_plugin(str(zip_path), plugin_id=plugin_id)

        mock_req.assert_called()
        mock_npm.assert_called_once()

    def test_install_plugin_with_post_install_requirements(self, tmp_path):
        """If requirements.post-install.txt exists, it should be processed."""
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin_id = "post_req_plugin"
        info = {"id": plugin_id, "name": "PostReq", "version": "1.0"}
        zip_path = tmp_path / "post_req_plugin.zip"
        with zipfile.ZipFile(str(zip_path), "w") as zf:
            zf.writestr("info.json", json.dumps(info))
            zf.writestr("requirements.post-install.txt", "some-package>=1.0")

        plugin_dir = plugins_dir / plugin_id
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "info.json").write_text(json.dumps(info))
        (plugin_dir / "requirements.post-install.txt").write_text("some-package>=1.0")

        with patch.object(handler, "install_plugin_requirements") as mock_req:
            handler.install_plugin(str(zip_path), plugin_id=plugin_id)

        # install_plugin_requirements should be called with the post-install requirements_file kwarg
        all_kwargs = [c.kwargs for c in mock_req.call_args_list]
        assert any("post-install" in str(kw.get("requirements_file", "")) for kw in all_kwargs)


# ---------------------------------------------------------------------------
# Line 523: install_plugin_requirements — cleanup of existing site-packages
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestInstallPluginRequirementsCleanup:
    def test_removes_existing_site_packages_before_install(self, tmp_path):
        """install_plugin_requirements must rmtree existing site-packages before reinstalling."""
        from compresso.libs.plugins import PluginsHandler

        plugin_dir = tmp_path / "my_plugin"
        plugin_dir.mkdir()
        req_file = plugin_dir / "requirements.txt"
        req_file.write_text("requests>=2.0")
        site_pkgs = plugin_dir / "site-packages"
        site_pkgs.mkdir()  # existing installation

        with patch("subprocess.call"):
            PluginsHandler.install_plugin_requirements(str(plugin_dir))

        # After the call the site-packages should have been recreated (rmtree + makedirs)
        assert (plugin_dir / "site-packages").exists()


# ---------------------------------------------------------------------------
# Lines 555-556: install_npm_modules — npm build timeout
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestInstallNpmModulesBuildTimeout:
    def test_npm_build_timeout_is_caught_and_logged(self, tmp_path):
        """A TimeoutExpired during npm build must be caught without re-raising."""
        from compresso.libs.plugins import PluginsHandler

        plugin_dir = tmp_path / "npm_plugin"
        plugin_dir.mkdir()
        (plugin_dir / "package.json").write_text('{"name": "test"}')

        def fake_call(cmd, *args, **kwargs):
            if cmd[0] == "npm" and len(cmd) > 1 and cmd[1] == "run":
                raise subprocess.TimeoutExpired(cmd, 300)

        with patch("subprocess.call", side_effect=fake_call):
            # Must not raise
            PluginsHandler.install_npm_modules(str(plugin_dir))


# ---------------------------------------------------------------------------
# Lines 561-581: write_plugin_data_to_db — update vs insert
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestWritePluginDataToDb:
    def test_inserts_new_plugin_when_not_found(self, tmp_path):
        """write_plugin_data_to_db should INSERT when no existing entry exists."""
        from compresso.libs.plugins import PluginsHandler

        plugin = {
            "plugin_id": "new_plugin",
            "name": "New Plugin",
            "author": "Author",
            "version": "1.0",
            "tags": "tag1",
            "description": "desc",
            "icon": "",
        }

        with patch("compresso.libs.plugins.Plugins") as mock_plugins:
            mock_plugins.get_or_none.return_value = None
            mock_insert = MagicMock()
            mock_plugins.insert.return_value = mock_insert

            result = PluginsHandler.write_plugin_data_to_db(plugin, "/fake/path")

        assert result is True
        mock_plugins.insert.assert_called_once()
        mock_insert.execute.assert_called_once()

    def test_updates_existing_plugin_when_found(self, tmp_path):
        """write_plugin_data_to_db should UPDATE when an existing entry is found."""
        from compresso.libs.plugins import PluginsHandler

        plugin = {
            "plugin_id": "existing_plugin",
            "name": "Existing",
            "author": "Author",
            "version": "2.0",
            "tags": "tag",
            "description": "desc",
            "icon": "",
        }

        with patch("compresso.libs.plugins.Plugins") as mock_plugins:
            mock_plugins.get_or_none.return_value = MagicMock()  # existing entry
            mock_update = MagicMock()
            mock_update.where.return_value.execute = MagicMock()
            mock_plugins.update.return_value = mock_update

            result = PluginsHandler.write_plugin_data_to_db(plugin, "/fake/path")

        assert result is True
        mock_plugins.update.assert_called_once()


# ---------------------------------------------------------------------------
# Lines 599-655: get_plugin_list_filtered_and_sorted — various filter branches
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetPluginListFilteredAndSorted:
    def _setup_mock_plugins(self, mock_plugins, fake_records=None):
        """Configure the Plugins mock to return fake_records from .dicts()."""
        if fake_records is None:
            fake_records = []
        mock_query = MagicMock()
        mock_query.join.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.order_by_extend.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.dicts.return_value = fake_records
        mock_plugins.select.return_value = mock_query
        mock_plugins.DoesNotExist = Exception
        return mock_query

    def test_filter_by_plugin_type_without_library_id(self, tmp_path):
        """plugin_type without library_id uses the simpler join condition."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow") as mock_lpf,
            patch("compresso.libs.plugins.EnabledPlugins"),
        ):
            self._setup_mock_plugins(mock_plugins, [{"plugin_id": "p1"}])
            mock_lpf.plugin_id = MagicMock()
            mock_lpf.plugin_type = MagicMock()

            result = handler.get_plugin_list_filtered_and_sorted(plugin_type="worker")

        assert result is not None

    def test_filter_by_plugin_type_with_library_id(self, tmp_path):
        """plugin_type + library_id uses the three-way join condition."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow") as mock_lpf,
            patch("compresso.libs.plugins.EnabledPlugins"),
        ):
            self._setup_mock_plugins(mock_plugins, [])
            mock_lpf.plugin_id = MagicMock()
            mock_lpf.plugin_type = MagicMock()
            mock_lpf.library_id = MagicMock()

            result = handler.get_plugin_list_filtered_and_sorted(plugin_type="worker", library_id=1)

        assert result is not None

    def test_filter_by_search_value(self, tmp_path):
        """search_value applies a WHERE clause using name, author, and tags."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow"),
            patch("compresso.libs.plugins.EnabledPlugins"),
        ):
            self._setup_mock_plugins(mock_plugins, [{"plugin_id": "p1", "name": "Test"}])

            result = handler.get_plugin_list_filtered_and_sorted(search_value="Test")

        assert result is not None

    def test_filter_by_id_list(self, tmp_path):
        """id_list applies a WHERE Plugins.id.in_() clause."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow"),
            patch("compresso.libs.plugins.EnabledPlugins"),
        ):
            self._setup_mock_plugins(mock_plugins, [{"plugin_id": "p1"}])

            result = handler.get_plugin_list_filtered_and_sorted(id_list=[1, 2, 3])

        assert result is not None

    def test_filter_by_library_id_only(self, tmp_path):
        """library_id without plugin_type joins EnabledPlugins."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow"),
            patch("compresso.libs.plugins.EnabledPlugins") as mock_ep,
        ):
            self._setup_mock_plugins(mock_plugins, [])
            mock_ep.plugin_id = MagicMock()
            mock_ep.library_id = MagicMock()

            result = handler.get_plugin_list_filtered_and_sorted(library_id=5)

        assert result is not None

    def test_enabled_flag_raises_deprecation_exception(self, tmp_path):
        """Passing enabled= must raise an Exception (deprecated)."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow"),
            patch("compresso.libs.plugins.EnabledPlugins"),
        ):
            self._setup_mock_plugins(mock_plugins, [])
            mock_plugins.DoesNotExist = Exception

            # The deprecated path raises Exception, which is caught internally
            result = handler.get_plugin_list_filtered_and_sorted(enabled=True)

        assert result is None

    def test_order_with_custom_model(self, tmp_path):
        """Order entries with an explicit model= use attrgetter on that model."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow") as mock_lpf,
            patch("compresso.libs.plugins.EnabledPlugins"),
        ):
            self._setup_mock_plugins(mock_plugins, [])
            mock_lpf.position = MagicMock()
            mock_lpf.position.asc = MagicMock(return_value="asc_order")

            order = [{"model": mock_lpf, "column": "position", "dir": "asc"}]
            result = handler.get_plugin_list_filtered_and_sorted(order=order)

        assert result is not None

    def test_length_and_start_apply_limit_offset(self, tmp_path):
        """length and start should produce a .limit().offset() call chain."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow"),
            patch("compresso.libs.plugins.EnabledPlugins"),
        ):
            mock_query = self._setup_mock_plugins(mock_plugins, [])

            handler.get_plugin_list_filtered_and_sorted(start=10, length=20)

        mock_query.limit.assert_called_once_with(20)

    def test_does_not_exist_exception_returns_none(self, tmp_path):
        """A Plugins.DoesNotExist during query should return None (warning logged)."""
        handler = _make_handler(tmp_path)
        with (
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.LibraryPluginFlow"),
            patch("compresso.libs.plugins.EnabledPlugins"),
        ):
            mock_plugins.DoesNotExist = RuntimeError
            mock_plugins.select.side_effect = RuntimeError("no plugins")

            result = handler.get_plugin_list_filtered_and_sorted()

        assert result is None


# ---------------------------------------------------------------------------
# Lines 658-672: flag_plugin_for_update_by_id
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestFlagPluginForUpdateById:
    def test_returns_true_when_all_records_flagged(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugin_id = "my_plugin"

        with patch("compresso.libs.plugins.Plugins") as mock_plugins:
            mock_plugins.update.return_value.where.return_value.execute = MagicMock()
            with patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": plugin_id, "update_available": True}],
            ):
                result = handler.flag_plugin_for_update_by_id(plugin_id)

        assert result is True

    def test_returns_false_when_record_not_flagged(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugin_id = "unflagged_plugin"

        with patch("compresso.libs.plugins.Plugins") as mock_plugins:
            mock_plugins.update.return_value.where.return_value.execute = MagicMock()
            with patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": plugin_id, "update_available": False}],
            ):
                result = handler.flag_plugin_for_update_by_id(plugin_id)

        assert result is False

    def test_returns_true_for_empty_records(self, tmp_path):
        """If no records are returned after update, the loop exits without returning False."""
        handler = _make_handler(tmp_path)

        with patch("compresso.libs.plugins.Plugins") as mock_plugins:
            mock_plugins.update.return_value.where.return_value.execute = MagicMock()
            with patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[],
            ):
                result = handler.flag_plugin_for_update_by_id("ghost_plugin")

        assert result is True


# ---------------------------------------------------------------------------
# Lines 682-717: uninstall_plugins_by_db_table_id
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUninstallPluginsByDbTableId:
    def test_removes_plugin_files_and_db_entries(self, tmp_path):
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin_dir = plugins_dir / "p1"
        plugin_dir.mkdir()
        info_file = plugin_dir / "info.json"
        info_file.write_text('{"id": "p1"}')

        with (
            patch("compresso.libs.plugins.PluginExecutor") as mock_pe,
            patch("compresso.libs.plugins.EnabledPlugins") as mock_ep,
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "p1"}],
            ),
        ):
            mock_pe.unload_plugin_module = MagicMock()
            mock_ep.delete.return_value.where.return_value.execute = MagicMock()
            mock_plugins.delete.return_value.where.return_value.execute.return_value = 1

            handler.uninstall_plugins_by_db_table_id([1])

        # Plugin directory should be gone
        assert not plugin_dir.exists()

    def test_handles_exception_during_unload(self, tmp_path):
        """If PluginExecutor.unload_plugin_module raises, it should be caught and logged."""
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin_dir = plugins_dir / "p1"
        plugin_dir.mkdir()

        with (
            patch("compresso.libs.plugins.PluginExecutor") as mock_pe,
            patch("compresso.libs.plugins.EnabledPlugins") as mock_ep,
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "p1"}],
            ),
        ):
            mock_pe.unload_plugin_module.side_effect = RuntimeError("unload error")
            mock_ep.delete.return_value.where.return_value.execute = MagicMock()
            mock_plugins.delete.return_value.where.return_value.execute.return_value = 1

            # Should not raise
            handler.uninstall_plugins_by_db_table_id([1])

    def test_handles_exception_during_directory_removal(self, tmp_path):
        """If shutil.rmtree raises, the exception should be caught and logged."""
        handler = _make_handler(tmp_path)
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir(parents=True, exist_ok=True)
        handler.settings.get_plugins_path.return_value = str(plugins_dir)

        plugin_dir = plugins_dir / "p1"
        plugin_dir.mkdir()

        with (
            patch("compresso.libs.plugins.PluginExecutor") as mock_pe,
            patch("compresso.libs.plugins.EnabledPlugins") as mock_ep,
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch("compresso.libs.plugins.shutil.rmtree", side_effect=OSError("locked")),
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "p1"}],
            ),
        ):
            mock_pe.unload_plugin_module = MagicMock()
            mock_ep.delete.return_value.where.return_value.execute = MagicMock()
            mock_plugins.delete.return_value.where.return_value.execute.return_value = 1

            # Should not raise
            handler.uninstall_plugins_by_db_table_id([1])


# ---------------------------------------------------------------------------
# Lines 720-732: update_plugins_by_db_table_id
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUpdatePluginsByDbTableId:
    def test_returns_true_when_all_plugins_updated(self, tmp_path):
        handler = _make_handler(tmp_path)
        with (
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "p1"}, {"plugin_id": "p2"}],
            ),
            patch.object(handler, "install_plugin_by_id", return_value=True),
        ):
            result = handler.update_plugins_by_db_table_id([1, 2])

        assert result is True

    def test_returns_false_when_one_update_fails(self, tmp_path):
        handler = _make_handler(tmp_path)
        with (
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "p1"}, {"plugin_id": "p2"}],
            ),
            patch.object(handler, "install_plugin_by_id", side_effect=[True, False]),
        ):
            result = handler.update_plugins_by_db_table_id([1, 2])

        assert result is False


# ---------------------------------------------------------------------------
# Lines 744-766: set_plugin_flow
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestSetPluginFlow:
    def test_set_plugin_flow_with_valid_plugins(self, tmp_path):
        handler = _make_handler(tmp_path)
        flow = [{"plugin_id": "p1"}, {"plugin_id": "p2"}]

        mock_p1 = MagicMock()
        mock_p2 = MagicMock()

        def fake_first_call(plugin_id):
            return {"p1": mock_p1, "p2": mock_p2}.get(plugin_id)

        with (
            patch("compresso.libs.plugins.LibraryPluginFlow") as mock_lpf,
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch.object(handler, "set_plugin_flow_position_for_single_plugin", return_value=True) as mock_set_pos,
        ):
            mock_lpf.delete.return_value.where.return_value.execute = MagicMock()
            mock_plugins.select.return_value.where.return_value.first.side_effect = [mock_p1, mock_p2]

            result = handler.set_plugin_flow("worker", 1, flow)

        assert result is True
        assert mock_set_pos.call_count == 2

    def test_set_plugin_flow_skips_missing_plugins(self, tmp_path):
        handler = _make_handler(tmp_path)
        flow = [{"plugin_id": "missing"}]

        with (
            patch("compresso.libs.plugins.LibraryPluginFlow") as mock_lpf,
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch.object(handler, "set_plugin_flow_position_for_single_plugin") as mock_set_pos,
        ):
            mock_lpf.delete.return_value.where.return_value.execute = MagicMock()
            mock_plugins.select.return_value.where.return_value.first.return_value = None

            result = handler.set_plugin_flow("worker", 1, flow)

        assert result is True
        mock_set_pos.assert_not_called()

    def test_set_plugin_flow_returns_false_when_position_fails(self, tmp_path):
        handler = _make_handler(tmp_path)
        flow = [{"plugin_id": "p1"}]
        mock_p1 = MagicMock()

        with (
            patch("compresso.libs.plugins.LibraryPluginFlow") as mock_lpf,
            patch("compresso.libs.plugins.Plugins") as mock_plugins,
            patch.object(handler, "set_plugin_flow_position_for_single_plugin", return_value=False),
        ):
            mock_lpf.delete.return_value.where.return_value.execute = MagicMock()
            mock_plugins.select.return_value.where.return_value.first.return_value = mock_p1

            result = handler.set_plugin_flow("worker", 1, flow)

        assert result is False


# ---------------------------------------------------------------------------
# Lines 795-817: get_enabled_plugin_modules_by_type
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetEnabledPluginModulesByType:
    def test_returns_plugin_data_from_executor(self, tmp_path):
        handler = _make_handler(tmp_path)
        fake_plugin_data = [{"plugin_id": "p1", "runner": MagicMock()}]
        mock_session = MagicMock()
        mock_executor = MagicMock()
        mock_executor.get_plugin_data_by_type.return_value = fake_plugin_data

        with (
            patch("compresso.libs.plugins.Session", return_value=mock_session),
            patch("compresso.libs.plugins.PluginExecutor", return_value=mock_executor),
            patch.object(handler, "get_plugin_list_filtered_and_sorted", return_value=[{"plugin_id": "p1"}]),
        ):
            result = handler.get_enabled_plugin_modules_by_type("worker", library_id=1)

        assert result == fake_plugin_data
        mock_session.register_compresso.assert_called_once()

    def test_calls_register_compresso_to_refresh_session(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_session = MagicMock()
        mock_executor = MagicMock()
        mock_executor.get_plugin_data_by_type.return_value = []

        with (
            patch("compresso.libs.plugins.Session", return_value=mock_session),
            patch("compresso.libs.plugins.PluginExecutor", return_value=mock_executor),
            patch.object(handler, "get_plugin_list_filtered_and_sorted", return_value=[]),
        ):
            handler.get_enabled_plugin_modules_by_type("on_library_file_matched")

        mock_session.register_compresso.assert_called_once()


# ---------------------------------------------------------------------------
# Lines 828-829: exec_plugin_runner
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestExecPluginRunner:
    def test_delegates_to_plugin_executor(self, tmp_path):
        handler = _make_handler(tmp_path)
        mock_executor = MagicMock()
        mock_executor.execute_plugin_runner.return_value = {"result": "ok"}

        with patch("compresso.libs.plugins.PluginExecutor", return_value=mock_executor):
            result = handler.exec_plugin_runner({"data": 1}, "my_plugin", "worker")

        mock_executor.execute_plugin_runner.assert_called_once_with({"data": 1}, "my_plugin", "worker")
        assert result == {"result": "ok"}


# ---------------------------------------------------------------------------
# Lines 838-891: get_incompatible_enabled_plugins
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetIncompatibleEnabledPlugins:
    def test_returns_empty_list_when_all_compatible(self, tmp_path):
        handler = _make_handler(tmp_path)
        compatible_plugin_info = {"compatibility": [2]}

        with (
            patch("compresso.libs.plugins.Library") as mock_library,
            patch("compresso.libs.plugins.FrontendPushMessages"),
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "p1", "name": "Plugin One"}],
            ),
            patch.object(handler, "get_plugin_info", return_value=compatible_plugin_info),
        ):
            mock_library.get_all_libraries.return_value = [{"id": 1}]
            result = handler.get_incompatible_enabled_plugins()

        assert result == []

    def test_returns_incompatible_plugins(self, tmp_path):
        handler = _make_handler(tmp_path)
        incompatible_plugin_info = {"compatibility": [1]}  # version 2 not listed

        with (
            patch("compresso.libs.plugins.Library") as mock_library,
            patch("compresso.libs.plugins.FrontendPushMessages"),
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "bad_plugin", "name": "Bad Plugin"}],
            ),
            patch.object(handler, "get_plugin_info", return_value=incompatible_plugin_info),
        ):
            mock_library.get_all_libraries.return_value = [{"id": 1}]
            result = handler.get_incompatible_enabled_plugins()

        assert len(result) == 1
        assert result[0]["plugin_id"] == "bad_plugin"

    def test_adds_frontend_message_for_incompatible_plugin(self, tmp_path):
        handler = _make_handler(tmp_path)

        mock_frontend_messages = MagicMock()

        with (
            patch("compresso.libs.plugins.Library") as mock_library,
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "bad_plugin", "name": "Bad Plugin"}],
            ),
            patch.object(handler, "get_plugin_info", return_value={"compatibility": [99]}),
        ):
            mock_library.get_all_libraries.return_value = [{"id": 1}]
            handler.get_incompatible_enabled_plugins(frontend_messages=mock_frontend_messages)

        mock_frontend_messages.add.assert_called_once()
        added_msg = mock_frontend_messages.add.call_args[0][0]
        assert added_msg["code"] == "incompatiblePlugin"
        assert added_msg["timeout"] == 0

    def test_handles_exception_fetching_plugin_info(self, tmp_path):
        """If get_plugin_info raises, the plugin is treated as incompatible."""
        handler = _make_handler(tmp_path)

        with (
            patch("compresso.libs.plugins.Library") as mock_library,
            patch("compresso.libs.plugins.FrontendPushMessages"),
            patch.object(
                handler,
                "get_plugin_list_filtered_and_sorted",
                return_value=[{"plugin_id": "broken", "name": "Broken Plugin"}],
            ),
            patch.object(handler, "get_plugin_info", side_effect=Exception("read error")),
        ):
            mock_library.get_all_libraries.return_value = [{"id": 1}]
            result = handler.get_incompatible_enabled_plugins()

        assert any(p["plugin_id"] == "broken" for p in result)

    def test_uses_default_frontend_messages_when_none_provided(self, tmp_path):
        """When frontend_messages=None, a FrontendPushMessages instance is created."""
        handler = _make_handler(tmp_path)
        mock_fpm = MagicMock()

        with (
            patch("compresso.libs.plugins.Library") as mock_library,
            patch("compresso.libs.plugins.FrontendPushMessages", return_value=mock_fpm),
            patch.object(handler, "get_plugin_list_filtered_and_sorted", return_value=[]),
        ):
            mock_library.get_all_libraries.return_value = []
            result = handler.get_incompatible_enabled_plugins(frontend_messages=None)

        assert result == []


# ---------------------------------------------------------------------------
# Lines 900-907: get_plugin_types_with_flows
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetPluginTypesWithFlows:
    def test_returns_only_types_with_flows(self, tmp_path):
        from compresso.libs.plugins import PluginsHandler

        all_types = [
            {"id": "worker", "has_flow": True},
            {"id": "on_library_file_matched", "has_flow": False},
            {"id": "on_postprocessor_task_results", "has_flow": True},
        ]
        mock_executor = MagicMock()
        mock_executor.get_all_plugin_types.return_value = all_types

        with patch("compresso.libs.plugins.PluginExecutor", return_value=mock_executor):
            result = PluginsHandler.get_plugin_types_with_flows()

        assert "worker" in result
        assert "on_postprocessor_task_results" in result
        assert "on_library_file_matched" not in result

    def test_returns_empty_list_when_no_types_have_flows(self, tmp_path):
        from compresso.libs.plugins import PluginsHandler

        mock_executor = MagicMock()
        mock_executor.get_all_plugin_types.return_value = [
            {"id": "event_type", "has_flow": False},
        ]

        with patch("compresso.libs.plugins.PluginExecutor", return_value=mock_executor):
            result = PluginsHandler.get_plugin_types_with_flows()

        assert result == []


# ---------------------------------------------------------------------------
# Lines 917-929: get_enabled_plugin_flows_for_plugin_type
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestGetEnabledPluginFlowsForPluginType:
    def test_returns_flow_list_for_plugin_type(self, tmp_path):
        handler = _make_handler(tmp_path)
        fake_modules = [
            {
                "plugin_id": "p1",
                "name": "Plugin One",
                "author": "Auth",
                "description": "desc",
                "version": "1.0",
                "icon": "icon.png",
            }
        ]

        with patch.object(handler, "get_enabled_plugin_modules_by_type", return_value=fake_modules):
            result = handler.get_enabled_plugin_flows_for_plugin_type("worker", library_id=1)

        assert len(result) == 1
        assert result[0]["plugin_id"] == "p1"
        assert result[0]["name"] == "Plugin One"
        assert result[0]["author"] == "Auth"

    def test_returns_empty_list_when_no_modules(self, tmp_path):
        handler = _make_handler(tmp_path)

        with patch.object(handler, "get_enabled_plugin_modules_by_type", return_value=[]):
            result = handler.get_enabled_plugin_flows_for_plugin_type("worker", library_id=1)

        assert result == []

    def test_result_includes_all_required_keys(self, tmp_path):
        handler = _make_handler(tmp_path)
        fake_modules = [{"plugin_id": "p1", "name": "N", "author": "A", "description": "D", "version": "V", "icon": "I"}]

        with patch.object(handler, "get_enabled_plugin_modules_by_type", return_value=fake_modules):
            result = handler.get_enabled_plugin_flows_for_plugin_type("worker", library_id=2)

        assert set(result[0].keys()) == {"plugin_id", "name", "author", "description", "version", "icon"}


# ---------------------------------------------------------------------------
# Lines 939-942: run_event_plugins_for_plugin_type
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestRunEventPluginsForPluginType:
    def test_runs_exec_for_each_module(self, tmp_path):
        handler = _make_handler(tmp_path)
        fake_modules = [
            {"plugin_id": "p1"},
            {"plugin_id": "p2"},
        ]
        data = {"key": "value"}

        with (
            patch.object(handler, "get_enabled_plugin_modules_by_type", return_value=fake_modules),
            patch.object(handler, "exec_plugin_runner", return_value=True) as mock_exec,
        ):
            handler.run_event_plugins_for_plugin_type("on_library_file_matched", data)

        assert mock_exec.call_count == 2
        mock_exec.assert_any_call(data, "p1", "on_library_file_matched")
        mock_exec.assert_any_call(data, "p2", "on_library_file_matched")

    def test_continues_when_exec_returns_falsy(self, tmp_path):
        """If exec_plugin_runner returns a falsy value, iteration should continue."""
        handler = _make_handler(tmp_path)
        fake_modules = [{"plugin_id": "p1"}, {"plugin_id": "p2"}]

        with (
            patch.object(handler, "get_enabled_plugin_modules_by_type", return_value=fake_modules),
            patch.object(handler, "exec_plugin_runner", return_value=None) as mock_exec,
        ):
            # Should complete without error
            handler.run_event_plugins_for_plugin_type("on_library_file_matched", {})

        assert mock_exec.call_count == 2
