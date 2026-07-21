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
from dataclasses import dataclass

from compresso.libs import narrowing
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.unplugins import PluginExecutor
from compresso.webserver.helpers import plugins

logger = CompressoLogging.get_logger(name="SettingsHelper")


@dataclass(frozen=True, slots=True)
class LibrarySaveRequest:
    """Validated top-level input for one library configuration save."""

    library_id: int
    library_config: dict[str, object]
    plugin_config: dict[str, object]


@dataclass(frozen=True, slots=True)
class _EnabledPlugin:
    plugin_id: str
    has_config: bool
    settings: Mapping[str, object]


def parse_library_save_request(
    library_id: object,
    library_config: object,
    plugin_config: object,
) -> LibrarySaveRequest:
    """Turn schema-validated JSON sections into one typed save request."""
    if not isinstance(library_config, Mapping) or not isinstance(plugin_config, Mapping):
        raise ValueError("Library configuration must contain objects")
    normalized_library = narrowing.mapping_dict(library_config)
    normalized_plugins = narrowing.mapping_dict(plugin_config)
    if len(normalized_library) != len(library_config) or len(normalized_plugins) != len(plugin_config):
        raise ValueError("Library configuration objects must use string keys")
    return LibrarySaveRequest(
        library_id=narrowing.coerce_int(library_id),
        library_config=normalized_library,
        plugin_config=normalized_plugins,
    )


def _load_or_create_library(request: LibrarySaveRequest) -> tuple[Library, int, bool]:
    if request.library_id > 0:
        return Library(request.library_id), request.library_id, False
    library = Library.create(
        {
            "name": narrowing.strict_str(request.library_config.get("name")),
            "path": narrowing.strict_str(request.library_config.get("path")),
        }
    )
    return library, library.get_id(), True


def _apply_library_fields(library: Library, config: Mapping[str, object]) -> None:
    if not config:
        return
    library.set_name(narrowing.strict_str(config.get("name"), library.get_name()))
    library.set_path(narrowing.strict_str(config.get("path"), library.get_path()))
    library.set_locked(narrowing.strict_bool(config.get("locked"), library.get_locked()))
    library.set_enable_remote_only(narrowing.strict_bool(config.get("enable_remote_only"), library.get_enable_remote_only()))
    library.set_enable_scanner(narrowing.strict_bool(config.get("enable_scanner"), library.get_enable_scanner()))
    library.set_enable_inotify(narrowing.strict_bool(config.get("enable_inotify"), library.get_enable_inotify()))
    library.set_priority_score(narrowing.strict_int(config.get("priority_score"), library.get_priority_score()))
    library.set_tags(narrowing.string_list(config.get("tags"), library.get_tags()))
    if "target_codecs" in config:
        library.set_target_codecs(narrowing.string_list(config.get("target_codecs")))
    if "skip_codecs" in config:
        library.set_skip_codecs(narrowing.string_list(config.get("skip_codecs")))
    if "size_guardrail_enabled" in config:
        library.set_size_guardrail_enabled(config.get("size_guardrail_enabled"))
    if "size_guardrail_min_pct" in config:
        library.set_size_guardrail_min_pct(narrowing.strict_int(config.get("size_guardrail_min_pct")))
    if "size_guardrail_max_pct" in config:
        library.set_size_guardrail_max_pct(narrowing.strict_int(config.get("size_guardrail_max_pct")))
    if "replacement_policy" in config:
        replacement_policy = config.get("replacement_policy")
        library.set_replacement_policy(replacement_policy if isinstance(replacement_policy, str) else None)


def _parse_enabled_plugins(value: object) -> tuple[list[Mapping[str, object]], list[_EnabledPlugin]]:
    sources = narrowing.mapping_list(value)
    parsed = [
        _EnabledPlugin(
            plugin_id=narrowing.strict_str(plugin.get("plugin_id")),
            has_config=narrowing.strict_bool(plugin.get("has_config")),
            settings=narrowing.mapping_value(plugin.get("settings")),
        )
        for plugin in sources
    ]
    return sources, parsed


def _install_and_enable_plugins(
    library: Library,
    library_id: int,
    library_config: Mapping[str, object],
    enabled_plugins_value: object,
    *,
    new_library: bool,
) -> None:
    enabled_plugins, parsed_plugins = _parse_enabled_plugins(enabled_plugins_value)
    enable_scanner = narrowing.strict_bool(library_config.get("enable_scanner"), library.get_enable_scanner())
    enable_inotify = narrowing.strict_bool(library_config.get("enable_inotify"), library.get_enable_inotify())
    if enabled_plugins and (enable_scanner or enable_inotify):
        logger.warning(
            "PLUGIN_AUTOMATION_REVIEW_RECOMMENDED library_id=%s enable_scanner=%s enable_inotify=%s plugin_count=%s",
            library_id,
            enable_scanner,
            enable_inotify,
            len(enabled_plugins),
        )

    repo_refreshed = False
    for plugin in parsed_plugins:
        if plugins.check_if_plugin_is_installed(plugin.plugin_id):
            continue
        if not repo_refreshed:
            plugins.reload_plugin_repos_data()
            repo_refreshed = True
        if not plugins.install_plugin_by_id(plugin.plugin_id):
            if new_library:
                library.delete()
            raise RuntimeError(f"Failed to install plugin by plugin ID '{plugin.plugin_id}'")

    library.set_enabled_plugins(enabled_plugins)
    plugin_executor = PluginExecutor()
    for plugin in parsed_plugins:
        if plugin.has_config:
            plugin_executor.save_plugin_settings(plugin.plugin_id, plugin.settings, library_id=library_id)


def _save_plugin_flows(library_id: int, plugin_flow_value: object) -> None:
    if not isinstance(plugin_flow_value, Mapping):
        return
    for plugin_type in plugins.get_plugin_types_with_flows():
        plugin_ids = plugin_flow_value.get(plugin_type, [])
        if not isinstance(plugin_ids, list):
            continue
        flow = [{"plugin_id": plugin_id} for plugin_id in plugin_ids if isinstance(plugin_id, str)]
        plugins.save_enabled_plugin_flows_for_plugin_type(plugin_type, library_id, flow)


def save_library_request(request: LibrarySaveRequest) -> int:
    """Save one already-validated library request."""
    library, saved_library_id, new_library = _load_or_create_library(request)
    _apply_library_fields(library, request.library_config)

    enabled_plugins_value = request.plugin_config.get("enabled_plugins")
    if enabled_plugins_value is not None:
        _install_and_enable_plugins(
            library,
            saved_library_id,
            request.library_config,
            enabled_plugins_value,
            new_library=new_library,
        )
    _save_plugin_flows(saved_library_id, request.plugin_config.get("plugin_flow"))
    return library.save()


def save_library_config(
    library_id: int,
    library_config: Mapping[str, object] | None = None,
    plugin_config: Mapping[str, object] | None = None,
) -> int:
    """Compatibility entry point for callers that do not have a typed request."""
    request = parse_library_save_request(
        library_id,
        {} if library_config is None else library_config,
        {} if plugin_config is None else plugin_config,
    )
    return save_library_request(request)


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
