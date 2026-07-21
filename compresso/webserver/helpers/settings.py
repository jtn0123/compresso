#!/usr/bin/env python3

"""
compresso.settings.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     21 Feb 2022, (5:22 PM)

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

from collections.abc import Mapping

from compresso.libs import narrowing
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.unplugins import PluginExecutor
from compresso.webserver.helpers import plugins

logger = CompressoLogging.get_logger(name="SettingsHelper")


def save_library_config(  # noqa: C901 — complex validation logic; refactor tracked in JTN-7
    library_id: int,
    library_config: Mapping[str, object] | None = None,
    plugin_config: Mapping[str, object] | None = None,
) -> int:
    """
    Save a complete library configuration

    :param library_id:
    :param library_config:
    :param plugin_config:
    :return:
    """
    # Parse library config
    if plugin_config is None:
        plugin_config = {}
    if library_config is None:
        library_config = {}

    # Check if this save requires a new library entry
    if library_id > 0:
        # Fetch existing library by ID
        new_library = False
        library = Library(library_id)
    else:
        # Create a new library with required data
        new_library = True
        library = Library.create(
            {
                "name": narrowing.strict_str(library_config.get("name")),
                "path": narrowing.strict_str(library_config.get("path")),
            }
        )
        library_id = library.get_id()

    # Update library config (if the data was given)
    if library_config:
        library.set_name(narrowing.strict_str(library_config.get("name"), library.get_name()))
        library.set_path(narrowing.strict_str(library_config.get("path"), library.get_path()))
        library.set_locked(narrowing.strict_bool(library_config.get("locked"), library.get_locked()))
        library.set_enable_remote_only(
            narrowing.strict_bool(library_config.get("enable_remote_only"), library.get_enable_remote_only())
        )
        library.set_enable_scanner(narrowing.strict_bool(library_config.get("enable_scanner"), library.get_enable_scanner()))
        library.set_enable_inotify(narrowing.strict_bool(library_config.get("enable_inotify"), library.get_enable_inotify()))
        library.set_priority_score(narrowing.strict_int(library_config.get("priority_score"), library.get_priority_score()))
        library.set_tags(narrowing.string_list(library_config.get("tags"), library.get_tags()))
        # Flow settings
        if "target_codecs" in library_config:
            library.set_target_codecs(narrowing.string_list(library_config.get("target_codecs")))
        if "skip_codecs" in library_config:
            library.set_skip_codecs(narrowing.string_list(library_config.get("skip_codecs")))
        if "size_guardrail_enabled" in library_config:
            library.set_size_guardrail_enabled(library_config.get("size_guardrail_enabled"))
        if "size_guardrail_min_pct" in library_config:
            library.set_size_guardrail_min_pct(narrowing.strict_int(library_config.get("size_guardrail_min_pct")))
        if "size_guardrail_max_pct" in library_config:
            library.set_size_guardrail_max_pct(narrowing.strict_int(library_config.get("size_guardrail_max_pct")))
        if "replacement_policy" in library_config:
            replacement_policy = library_config.get("replacement_policy")
            library.set_replacement_policy(replacement_policy if isinstance(replacement_policy, str) else None)

    # Update enabled plugins (if the data was given)
    enabled_plugins_value = plugin_config.get("enabled_plugins")
    if enabled_plugins_value is not None:
        enabled_plugins = narrowing.mapping_list(enabled_plugins_value)
        # Narrow each entry exactly once so the install and settings-import
        # phases below cannot read the same field two different ways.
        parsed_plugins = [
            (
                narrowing.strict_str(ep.get("plugin_id")),
                bool(ep.get("has_config")),
                narrowing.mapping_value(ep.get("settings")),
            )
            for ep in enabled_plugins
        ]
        enable_scanner = bool(library_config.get("enable_scanner", library.get_enable_scanner()))
        enable_inotify = bool(library_config.get("enable_inotify", library.get_enable_inotify()))
        if enabled_plugins and (enable_scanner or enable_inotify):
            logger.warning(
                "PLUGIN_AUTOMATION_REVIEW_RECOMMENDED library_id=%s enable_scanner=%s enable_inotify=%s plugin_count=%s",
                library_id,
                enable_scanner,
                enable_inotify,
                len(enabled_plugins),
            )
        # Ensure plugins are installed (install them if they are not). This
        # phase stays separate from the settings import: an install failure
        # must abort before any plugin settings have been written.
        repo_refreshed = False
        for plugin_id, _, _ in parsed_plugins:
            if not plugins.check_if_plugin_is_installed(plugin_id):
                # Trigger plugin repo refresh if this is the first install
                if not repo_refreshed:
                    plugins.reload_plugin_repos_data()
                    repo_refreshed = True
                # Install the plugin
                if not plugins.install_plugin_by_id(plugin_id):
                    if new_library:
                        library.delete()
                    raise RuntimeError(f"Failed to install plugin by plugin ID '{plugin_id}'")
        # Enable the plugins against this library
        library.set_enabled_plugins(enabled_plugins)
        # Import settings
        plugin_executor = PluginExecutor()
        for plugin_id, has_config, plugin_settings in parsed_plugins:
            if has_config:
                plugin_executor.save_plugin_settings(plugin_id, plugin_settings, library_id=library_id)

    # Update plugin flow (if the data was given)
    plugin_flow_value = plugin_config.get("plugin_flow")
    if isinstance(plugin_flow_value, Mapping):
        for plugin_type in plugins.get_plugin_types_with_flows():
            flow: list[dict[str, object]] = []
            plugin_ids = plugin_flow_value.get(plugin_type, [])
            if not isinstance(plugin_ids, list):
                continue
            for plugin_id in plugin_ids:
                if not isinstance(plugin_id, str):
                    continue
                flow.append({"plugin_id": plugin_id})
            plugins.save_enabled_plugin_flows_for_plugin_type(plugin_type, library_id, flow)

    # Save config
    return library.save()


def save_worker_group_config(data: Mapping[str, object]) -> int | None:
    """
    Save a complete worker group configuration

    NOTE:
        If the worker group is updated in the future with new options, then be sure to apply the save logic to
        both the create and update methods

    :param data:
    :return:
    """
    from compresso.libs.worker_group import WorkerGroup

    # Create new worker group
    if not data.get("id"):
        WorkerGroup.create(data)
        return None

    # Update existing worker group
    # NOTE: If this is updated in the future with new options, then be sure to apply the same save logic to the create method
    worker_group = WorkerGroup(narrowing.strict_int(data.get("id")))
    # Store locked status
    worker_group.set_locked(narrowing.strict_bool(data.get("locked"), worker_group.get_locked()))
    # Store name
    worker_group.set_name(narrowing.strict_str(data.get("name"), worker_group.get_name()))
    # Store the number of workers
    worker_group.set_number_of_workers(
        narrowing.strict_int(data.get("number_of_workers"), worker_group.get_number_of_workers())
    )
    # Store the worker type
    worker_group.set_worker_type(narrowing.strict_str(data.get("worker_type"), worker_group.get_worker_type()))

    # Set lists
    worker_group.set_tags(narrowing.string_list(data.get("tags"), worker_group.get_tags()))
    worker_group.set_worker_event_schedules(
        narrowing.mapping_list(data.get("worker_event_schedules", worker_group.get_worker_event_schedules()))
    )

    # Save config
    return worker_group.save()
