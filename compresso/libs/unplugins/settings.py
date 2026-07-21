#!/usr/bin/env python3

"""
compresso.settings.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     16 Mar 2021, (7:14 PM)

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

import contextlib
import json
import os
import sys
from typing import cast

from compresso import config
from compresso.libs.json_state import atomic_json_write

_SETTINGS_FILENAME = "settings.json"


class PluginSettings:
    """
    A dictionary of settings accessible to the Plugin class and able
    to be configured by users from within the Compresso WebUI.

    """

    settings: dict[str, object] = {}

    """
    A dictionary of form settings used by Compresso's WebUI to configure
    the plugin's settings form.

    """
    form_settings: dict[str, object] = {}

    """
    A cached copy of settings as they are stored on disk.

    """
    settings_configured: dict[str, object] = {}

    """
    The library ID that we are fetching settings for.

    """
    library_id: int | None = None

    def __init__(self, *args: object, **kwargs: object) -> None:
        library_id = kwargs.get("library_id")
        self.library_id = None
        # If the given library is not None, ensure that it is a number
        if library_id:
            try:
                if not isinstance(library_id, (str, bytes, bytearray, int, float)):
                    raise ValueError
                self.library_id = int(library_id)
            except (TypeError, ValueError):
                raise ValueError(f"Library ID needs to be an integer. You have provided '{library_id}'") from None
        self.settings_configured = {}

    def __get_plugin_settings_file(self, force_library_settings: bool = False) -> str:
        profile_directory = self.get_profile_directory()
        # The legacy migration that moved settings.json from the plugin
        # directory to the profile directory has been removed in
        # v2.0-prep. Anyone still running a pre-migration build needs to
        # move plugin settings.json manually before upgrading.
        plugin_settings_file = os.path.join(profile_directory, _SETTINGS_FILENAME)
        if self.library_id:
            plugin_settings_file = os.path.join(profile_directory, f"settings.{self.library_id}.json")
            if not os.path.exists(plugin_settings_file) and not force_library_settings:
                # If the library file does not yet exist, then resort to using the default settings file
                plugin_settings_file = os.path.join(profile_directory, _SETTINGS_FILENAME)
        return plugin_settings_file

    def __export_configured_settings(self) -> None:
        """
        Write settings to settings file

        :return:
        """
        plugin_settings_file = self.__get_plugin_settings_file(force_library_settings=True)

        atomic_json_write(plugin_settings_file, self.settings_configured, mode=0o600)

    def __import_configured_settings(self) -> None:
        """
        Read settings from settings file

        :return:
        """
        plugin_settings_file = self.__get_plugin_settings_file()

        # Default the configured settings to the plugin defaults
        # Loop over the self.settings object to clone the keys/values
        self.settings_configured = {}
        for key in self.settings:
            self.settings_configured[key] = self.settings[key]

        # if the file does not yet exist, create it
        if not os.path.exists(plugin_settings_file):
            self.__export_configured_settings()

        # Read plugin settings from file
        with open(plugin_settings_file) as infile:
            raw_settings = json.load(infile)
            plugin_settings = cast("dict[str, object]", raw_settings) if isinstance(raw_settings, dict) else {}

        # Loop over settings
        for key in self.settings:
            if key in plugin_settings:
                value = plugin_settings.get(key)
                if value is None:
                    # Restore default value
                    value = self.settings.get(key)
                self.settings_configured[key] = value

    def reset_settings_to_defaults(self) -> bool:
        """
        Remove all currently configured settings by deleting the settings.json file

        :return:
        """
        plugin_settings_file = self.__get_plugin_settings_file()

        # If the settings file returned is the global settings file and this was called on a library config,
        # do not reset the config.
        if self.library_id is not None and os.path.basename(plugin_settings_file) == _SETTINGS_FILENAME:
            return False

        # if the file does not yet exist, create it
        if os.path.exists(plugin_settings_file):
            os.remove(plugin_settings_file)

        return bool(not os.path.exists(plugin_settings_file))

    def get_plugin_directory(self) -> str:
        """
        Return the absolute path to the Plugin's directory.
        This is where the Plugin is currently installed.

        :return:
        """
        module_file = getattr(sys.modules[self.__class__.__module__], "__file__", None)
        if not isinstance(module_file, str):
            raise RuntimeError("Plugin module does not have a filesystem path")
        return os.path.dirname(os.path.abspath(module_file))

    def get_profile_directory(self) -> str:
        """
        Return the absolute path to the Plugin's profile directory.
        This is where Plugin settings are saved and where all mutable data for the
        Plugin should be stored.

        :return:
        """
        settings = config.Config()
        userdata_path = settings.get_userdata_path()
        plugin_directory = self.get_plugin_directory()
        plugin_id = os.path.basename(plugin_directory)
        profile_directory = os.path.join(userdata_path, plugin_id)
        if not os.path.exists(profile_directory):
            os.makedirs(profile_directory)
        return profile_directory

    def get_form_settings(self) -> dict[str, object]:
        """
        Return the current form settings.

        :return:
        """
        return self.form_settings

    def get_setting(self, key: str | None = None) -> object:
        """
        Fetch a single configuration value, or, when passed "all" as the key argument,
        return the full configuration dictionary.

        :param key:
        :return:
        """
        # First import settings
        try:
            self.__import_configured_settings()
        except json.decoder.JSONDecodeError:
            # If the import fails, then it will resort to defaults.
            # That is fine. Better than breaking the rest of the process
            pass
        except FileNotFoundError:
            # If the settings file did not exist, then also resort to defaults.
            pass

        if key is None:
            return self.settings_configured
        return self.settings_configured.get(key)

    def set_setting(self, key: str, value: object) -> bool:
        """
        Set a singe configuration value.
        Used by the Compresso WebUI to save user settings.
        Settings are stored on disk in order to be persistent.

        :param key:
        :param value:
        :return:
        """
        # First import settings
        # If the import fails, it will resort to defaults. Better than breaking the rest of the process.
        with contextlib.suppress(json.decoder.JSONDecodeError):
            self.__import_configured_settings()

        # Ensure plugin has this setting
        if key not in self.settings:
            return False

        # Set the configured value
        self.settings_configured[key] = value

        # Export the settings again
        self.__export_configured_settings()

        return True

    def get_default_setting(self, key: str | None = None) -> object:
        """
        Fetch a single configuration value, or, when passed "all" as the key argument,
        return the full configuration dictionary.

        :param key:
        :return:
        """
        if key is None:
            return self.settings
        return self.settings.get(key)
