#!/usr/bin/env python3

"""
compresso.executor.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     05 Mar 2021, (6:55 PM)

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

import copy
import importlib
import importlib.util
import inspect
import json
import os
import sys
from collections.abc import Callable, Iterable, Mapping
from types import ModuleType
from typing import Protocol, cast

from compresso.libs import common
from compresso.libs.metadata import CompressoFileMetadata

from ..logs import CompressoLogging
from ..task import TaskDataStore
from . import plugin_types
from .plugin_types.plugin_type_base import PluginType


class _PluginSettings(Protocol):
    def get_form_settings(self) -> object: ...

    def get_setting(self, key: str | None = None) -> object: ...

    def set_setting(self, key: str, value: object) -> bool: ...

    def reset_settings_to_defaults(self) -> bool: ...


class _PluginSettingsFactory(Protocol):
    def __call__(self, *, library_id: int | None = None) -> _PluginSettings: ...


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return {}
    return cast("dict[str, object]", value)


class PluginExecutor:
    def __init__(self, plugins_directory: str | None = None) -> None:
        # Set plugins directory
        if not plugins_directory:
            home_directory = common.get_home_dir()
            plugins_directory = os.path.join(home_directory, ".compresso", "plugins")
        self.plugins_directory = plugins_directory
        # NOTE: List plugin types in order that they are run against a library
        #       This is listing them in order helps the frontend. Don't order alphabetically
        self.plugin_types: list[dict[str, object]] = [
            {
                "id": "frontend.panel",
                "has_flow": False,
            },
            {
                "id": "frontend.plugin_api",
                "has_flow": False,
            },
            {
                "id": "library_management.file_test",
                "has_flow": True,
            },
            {
                "id": "events.file_queued",
                "has_flow": False,
            },
            {
                "id": "events.task_queued",
                "has_flow": False,
            },
            {
                "id": "events.scan_complete",
                "has_flow": False,
            },
            {
                "id": "events.task_scheduled",
                "has_flow": False,
            },
            {
                "id": "events.worker_process_started",
                "has_flow": False,
            },
            {
                "id": "worker.process",
                "has_flow": True,
            },
            {
                "id": "events.worker_process_complete",
                "has_flow": False,
            },
            {
                "id": "events.postprocessor_started",
                "has_flow": False,
            },
            {
                "id": "postprocessor.file_move",
                "has_flow": True,
            },
            {
                "id": "postprocessor.task_result",
                "has_flow": True,
            },
            {
                "id": "events.postprocessor_complete",
                "has_flow": False,
            },
        ]
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)

    def __get_plugin_directory(self, plugin_id: str) -> str | None:
        """
        Return a contained plugin path for a plugin ID, or ``None`` when unsafe.

        :param plugin_id:
        :return:
        """
        plugins_directory = os.path.realpath(self.plugins_directory)
        plugin_directory = os.path.realpath(os.path.join(plugins_directory, plugin_id))
        try:
            contained = os.path.commonpath((plugins_directory, plugin_directory)) == plugins_directory
        except ValueError:
            contained = False
        if not contained or plugin_directory == plugins_directory:
            self.logger.error("Refusing plugin path outside the configured plugin directory: %s", plugin_id)
            return None
        return plugin_directory

    @staticmethod
    def __include_plugin_site_packages(path: str) -> None:
        plugin_site_packages_dir = os.path.join(path, "site-packages")
        if os.path.exists(plugin_site_packages_dir) and plugin_site_packages_dir not in sys.path:
            sys.path.append(plugin_site_packages_dir)

    @staticmethod
    def __include_plugin_directory(path: str) -> None:
        if os.path.exists(path) and path not in sys.path:
            sys.path.append(path)

    def __load_plugin_module(self, plugin_id: str, path: str) -> ModuleType | None:
        """
        Loads and returns the python module from a given plugin path.
            All plugins should have a file called "plugin.py".

        :param plugin_id:
        :param path:
        :return:
        """
        if not self.__is_plugin_trusted(plugin_id, path):
            self.logger.error(
                "Refusing to load untrusted plugin '%s'. Bundled plugins are trusted; "
                "explicitly allow external IDs with COMPRESSO_TRUSTED_PLUGIN_IDS.",
                plugin_id,
            )
            return None

        # Set the module name
        module_name = f"{plugin_id}.plugin"

        # Get main module file
        plugin_module_path = os.path.join(path, "plugin.py")

        # Ensure the Compresso plugins directory to sys path prior to loading it
        self.__include_plugin_directory(self.plugins_directory)

        # Add site-packages directory to sys path prior to loading the module
        self.__include_plugin_site_packages(path)

        # Don't re-import the module if it is already loaded.
        if module_name in sys.modules:
            return sys.modules[module_name]

        try:
            # First import the module namespace
            # Without this we are unable to reload the plugin in reload_plugin_module()
            importlib.import_module(plugin_id)

            # Import the module for this plugin
            module_spec = importlib.util.spec_from_file_location(module_name, plugin_module_path)
            if module_spec is None or module_spec.loader is None:
                self.logger.error("Unable to build an import specification for plugin '%s'", plugin_id)
                return None
            plugin_import = importlib.util.module_from_spec(module_spec)

            # Adding the module to sys.modules is optional but it gives us visibility if we need it elsewhere.
            sys.modules[module_name] = plugin_import

            module_spec.loader.exec_module(plugin_import)

            return plugin_import
        except Exception as e:
            self.logger.exception("Exception encountered while importing module '%s'. %s", plugin_id, e)
            return None

    @staticmethod
    def __is_plugin_trusted(plugin_id: str, path: str) -> bool:
        info_path = os.path.join(path, "info.json")
        try:
            with open(info_path, encoding="utf-8") as info_file:
                plugin_info = _object_dict(json.load(info_file))
        except (OSError, ValueError, TypeError):
            return False

        if plugin_info.get("bundled") is True:
            return True

        trusted_ids = {item.strip() for item in os.environ.get("COMPRESSO_TRUSTED_PLUGIN_IDS", "").split(",") if item.strip()}
        return plugin_id in trusted_ids

    def reload_plugin_module(self, plugin_id: str) -> None:
        """
        Reload a plugin module

        :param plugin_id:
        :return:
        """
        # Set the module name
        module_name = f"{plugin_id}.plugin"
        # self.logger.debug("Reloading module '{}'".format(module_name))

        if module_name in sys.modules:
            # Get all submodules
            module_names = [module_name]
            for m in sys.modules:
                if plugin_id in m and m not in [plugin_id, module_name]:
                    # Add to removal list
                    module_names.append(m)
            # Reload all imported modules or remove them if that fails
            for mn in module_names:
                try:
                    importlib.reload(sys.modules[mn])
                except ImportError:
                    # The module's parent was probably not imported.
                    # Delete it from sys.modules and carry on.
                    # This will force it to be reloaded again
                    self.logger.exception("Exception encountered while trying to reload module '%s'", module_name)
                    del sys.modules[module_name]

    @staticmethod
    def unload_plugin_module(plugin_id: str) -> None:
        """
        Remove plugin module from sys.modules

        This does not really clean up memory. Things are still getting really messy behind the scenes.
        This just makes it remove the module so that it will need to be re-imported above.

        :param plugin_id:
        :return:
        """
        # Set the module name
        module_name = f"{plugin_id}.plugin"

        if module_name in sys.modules:
            del sys.modules[module_name]

    @staticmethod
    def get_plugin_type_meta(plugin_type: str) -> PluginType:
        return plugin_types.grab_module(plugin_type)

    def get_all_plugin_types(self) -> list[dict[str, object]]:
        return self.plugin_types

    def get_all_plugin_types_in_plugin(self, plugin_id: str) -> list[str]:
        return_plugin_types: list[str] = []

        # Get the path for this plugin
        plugin_path = self.__get_plugin_directory(plugin_id)
        if plugin_path is None:
            return return_plugin_types

        # Load this plugin module
        plugin_module = self.__load_plugin_module(plugin_id, plugin_path)

        for plugin_type in self.get_all_plugin_types():
            # Get the called runner function for the given plugin type
            plugin_type_id = plugin_type.get("id")
            if not isinstance(plugin_type_id, str):
                continue
            plugin_type_meta = self.get_plugin_type_meta(plugin_type_id)
            plugin_runner = plugin_type_meta.plugin_runner()

            # Check if this module contains the given plugin type runner function
            if plugin_module is not None and hasattr(plugin_module, plugin_runner):
                # If it does, add it to the plugin_modules list
                return_plugin_types.append(plugin_type_id)

        return return_plugin_types

    def execute_plugin_runner(self, data: dict[str, object], plugin_id: str, plugin_type: str) -> bool:
        """
        Given a data, a plugin ID, and a plugin type
        Load that plugin module and execute the runner
        Return the modified data

        :param data:
        :param plugin_id:
        :param plugin_type:
        :return:
        """
        # Get the path for this plugin
        plugin_path = self.__get_plugin_directory(plugin_id)
        if plugin_path is None:
            return False

        # Load this plugin module
        plugin_module = self.__load_plugin_module(plugin_id, plugin_path)
        if not plugin_module:
            self.logger.error("No module found with plugin_id '%s' and plugin_path '%s'", plugin_id, plugin_path)
            return False

        # Get the called runner function for the given plugin type
        plugin_type_meta = self.get_plugin_type_meta(plugin_type)
        plugin_runner = plugin_type_meta.plugin_runner()

        # Check if this module contains the given plugin type runner
        runner_value = getattr(plugin_module, plugin_runner, None)
        if not callable(runner_value):
            # Plugin does not contain this runner, return false
            return False

        runner = cast("Callable[..., object]", runner_value)
        run_successfully = False
        task_id = data.get("task_id")
        typed_task_id = task_id if isinstance(task_id, int) and not isinstance(task_id, bool) else None
        try:
            # if we have a task_id, bind context for store-based calls
            if typed_task_id is not None:
                TaskDataStore.bind_runner_context(
                    task_id=typed_task_id,
                    plugin_id=plugin_id,
                    runner=plugin_runner,
                )

            metadata_path = data.get("path") or data.get("file_path")
            CompressoFileMetadata.bind_runner_context(
                plugin_id=plugin_id,
                task_id=typed_task_id,
                path=metadata_path if isinstance(metadata_path, str) else None,
            )

            sig = inspect.signature(runner)
            params = sig.parameters

            def supports_kwarg(name: str) -> bool:
                if name in params:
                    return True
                return any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params.values())

            # v2.0: kwargs-only plugin runner contract. Plugins must accept
            # `task_data_store` and/or `file_metadata` as keyword arguments
            # (or **kwargs). The legacy positional-args fallback was
            # removed; any plugin still using positional helpers will now
            # raise TypeError, which surfaces as a clean run failure via
            # the broad except below.
            kwargs: dict[str, object] = {}
            if supports_kwarg("task_data_store"):
                kwargs["task_data_store"] = TaskDataStore
            if supports_kwarg("file_metadata"):
                kwargs["file_metadata"] = CompressoFileMetadata
            runner(data, **kwargs)

            run_successfully = True
        except Exception:
            self.logger.exception("Exception while carrying out '%s' plugin runner '%s'", plugin_type, plugin_id)
        finally:
            TaskDataStore.clear_context()
            CompressoFileMetadata.clear_context()

        return run_successfully

    def build_plugin_data_from_plugin_list_filtered_by_plugin_type(
        self, plugins_list: Iterable[Mapping[str, object]], plugin_type: str
    ) -> list[dict[str, object]]:
        """
        Given a list of plugins and a plugin type,
        Return a filtered list of dictionaries containing:
            - the plugin module
            - the runner function to execute
            - the metadata for that plugin

        :param plugins_list:
        :param plugin_type:
        :return:
        """
        plugin_modules: list[dict[str, object]] = []

        # Ensure called runner type exists
        if plugin_type not in plugin_types.get_all_plugin_types():
            self.logger.error("Provided plugin type does not exist! %s", plugin_type)
            return plugin_modules

        # Get the called runner function for the given plugin type
        plugin_type_meta = self.get_plugin_type_meta(plugin_type)
        plugin_runner = plugin_type_meta.plugin_runner()

        for plugin_data in plugins_list:
            # Get plugin ID
            plugin_id = plugin_data.get("plugin_id")
            if not isinstance(plugin_id, str):
                continue

            # Get plugin metadata
            plugin_name = plugin_data.get("name")
            plugin_author = plugin_data.get("author")
            plugin_version = plugin_data.get("version")
            plugin_icon = plugin_data.get("icon")
            plugin_description = plugin_data.get("description")

            # Get the path for this plugin
            plugin_path = self.__get_plugin_directory(plugin_id)
            if plugin_path is None:
                continue

            # Load this plugin module
            plugin_module = self.__load_plugin_module(plugin_id, plugin_path)

            # Check if this module contains the given plugin type runner function
            if plugin_module is not None and hasattr(plugin_module, plugin_runner):
                # If it does, add it to the plugin_modules list
                plugin_runner_data = {
                    "plugin_id": plugin_id,
                    "name": plugin_name,
                    "author": plugin_author,
                    "version": plugin_version,
                    "icon": plugin_icon,
                    "description": plugin_description,
                    "plugin_module": plugin_module,
                    "plugin_path": plugin_path,
                }
                plugin_modules.append(plugin_runner_data)

        return plugin_modules

    def get_plugin_data_by_type(
        self, enabled_plugins: Iterable[Mapping[str, object]], plugin_type: str
    ) -> list[dict[str, object]]:
        """
        Given a list of enabled plugins and a plugin type
        Returns a list of dictionaries containing plugin data including
            - the plugin module
            - the runner function to execute
            - the metadata for that plugin

        :param enabled_plugins:
        :param plugin_type:
        :return:
        """
        # Filter out only plugins that have runners of this type
        plugin_data = self.build_plugin_data_from_plugin_list_filtered_by_plugin_type(enabled_plugins, plugin_type)

        # Return runners
        return plugin_data

    def get_plugin_settings(
        self, plugin_id: str, library_id: int | None = None
    ) -> tuple[dict[str, object], dict[str, object]]:
        """
        Returns a dictionary of a given plugin's settings

        :param plugin_id:
        :param library_id:
        :return:
        """
        # Get the path for this plugin
        plugin_path = self.__get_plugin_directory(plugin_id)
        if plugin_path is None:
            return {}, {}

        # Load this plugin module
        plugin_module = self.__load_plugin_module(plugin_id, plugin_path)

        if plugin_module is None or not hasattr(plugin_module, "Settings"):
            # This plugin does not have a settings class
            return {}, {}

        try:
            # Settings plugin_settings
            settings_factory = cast("_PluginSettingsFactory", plugin_module.Settings)
            plugin_settings = settings_factory(library_id=library_id)

            # Build form first so any in-memory defaults are applied without persisting
            plugin_form_settings = _object_dict(copy.deepcopy(plugin_settings.get_form_settings()))
            all_plugin_settings = _object_dict(copy.deepcopy(plugin_settings.get_setting()))
        except Exception as e:
            self.logger.exception("Exception while fetching settings for plugin '%s' %s", plugin_id, e)
            all_plugin_settings = {}
            plugin_form_settings = {}

        return all_plugin_settings, plugin_form_settings

    def save_plugin_settings(self, plugin_id: str, settings: Mapping[str, object], library_id: int | None = None) -> bool:
        """
        Saves a collection of a given plugin's settings.
        Returns a boolean result for the overall success
        of saving all values.

        :param plugin_id:
        :param settings:
        :param library_id:
        :return:
        """
        # Get the path for this plugin
        plugin_path = self.__get_plugin_directory(plugin_id)
        if plugin_path is None:
            return False

        # Load this plugin module
        plugin_module = self.__load_plugin_module(plugin_id, plugin_path)

        try:
            if plugin_module is None:
                return False
            settings_factory = cast("_PluginSettingsFactory", plugin_module.Settings)
            plugin_settings = settings_factory(library_id=library_id)
            save_result = True
            for key in settings:
                value = settings.get(key)
                # All plugin settings are available — no req_lev gating
                if not plugin_settings.set_setting(key, value):
                    save_result = False

            del plugin_settings, plugin_module

            if save_result:
                self.reload_plugin_module(plugin_id)

            return save_result
        except Exception as e:
            self.logger.exception("Exception while saving settings for plugin '%s' %s", plugin_id, e)
            return False

    def reset_plugin_settings(self, plugin_id: str, library_id: int | None = None) -> bool:
        """
        Reset a plugin settings by removing the config file

        :param plugin_id:
        :param library_id:
        :return:
        """
        # Get the path for this plugin
        plugin_path = self.__get_plugin_directory(plugin_id)
        if plugin_path is None:
            return False

        # Load this plugin module
        plugin_module = self.__load_plugin_module(plugin_id, plugin_path)

        try:
            if plugin_module is None:
                return False
            settings_factory = cast("_PluginSettingsFactory", plugin_module.Settings)
            plugin_settings = settings_factory(library_id=library_id)
            return plugin_settings.reset_settings_to_defaults()
        except Exception as e:
            self.logger.exception("Exception while resetting settings for plugin '%s' %s", plugin_id, e)
            return False

    def get_plugin_changelog(self, plugin_id: str) -> list[str]:
        """
        Returns a list of lines from the plugin's changelog

        :param plugin_id:
        :return:
        """
        changelog: list[str] = []
        # Get the path for this plugin
        plugin_path = self.__get_plugin_directory(plugin_id)
        if plugin_path is None:
            return changelog
        plugin_changelog = os.path.join(plugin_path, "changelog.md")
        if os.path.exists(plugin_changelog):
            with open(plugin_changelog) as f:
                changelog = f.readlines()

        return changelog

    def get_plugin_long_description(self, plugin_id: str) -> list[str]:
        """
        Returns a list of lines from the plugin's additional description file

        :param plugin_id:
        :return:
        """
        description: list[str] = []
        # Get the path for this plugin
        plugin_path = self.__get_plugin_directory(plugin_id)
        if plugin_path is None:
            return description
        plugin_description = os.path.join(plugin_path, "description.md")
        if os.path.exists(plugin_description):
            with open(plugin_description) as f:
                description = f.readlines()

        return description

    def test_plugin_runner(
        self,
        plugin_id: str,
        plugin_type: str,
        test_data: Mapping[str, object] | None = None,
        test_data_modifiers: Mapping[str, str] | None = None,
    ) -> list[str]:
        if test_data is None:
            test_data = {}
        if test_data_modifiers is None:
            test_data_modifiers = {}
        try:
            # Get the path for this plugin
            plugin_path = self.__get_plugin_directory(plugin_id)
            if plugin_path is None:
                return [f"Plugin '{plugin_id}' has an unsafe path."]

            # Load this plugin module
            plugin_module = self.__load_plugin_module(plugin_id, plugin_path)
            if plugin_module is None:
                return [f"Plugin '{plugin_id}' could not be loaded."]

            # Get the called runner function for the given plugin type
            plugin_type_meta = self.get_plugin_type_meta(plugin_type)
            if not test_data:
                test_data = plugin_type_meta.get_test_data()
                test_data = plugin_type_meta.modify_test_data(test_data, test_data_modifiers)
            errors = plugin_type_meta.run_data_schema_tests(plugin_id, plugin_module, test_data=test_data)
        except Exception as e:
            self.logger.exception("Exception while testing plugin runner for plugin '%s' %s", plugin_id, e)
            errors = [f"Exception encountered while testing runner - {str(e)}"]

        return errors

    def test_plugin_settings(self, plugin_id: str) -> tuple[list[str], dict[str, object]]:
        errors: list[str] = []

        # Get the called runner function for the given plugin type
        plugin_settings: dict[str, object] = {}
        try:
            plugin_settings, plugin_settings_meta = self.get_plugin_settings(plugin_id, library_id=1)
        except Exception as e:
            errors.append(str(e))

        return errors, plugin_settings
