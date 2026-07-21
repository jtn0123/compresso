#!/usr/bin/env python3

"""
compresso.library.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     06 Feb 2022, (12:11 PM)

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

import json
import random
from collections.abc import Iterable, Mapping, Sequence
from typing import NotRequired, TypedDict, cast

from compresso.config import Config
from compresso.libs import common
from compresso.libs.frontend_push_messages import FrontendPushMessages
from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_count, execute_write
from compresso.libs.unmodels import EnabledPlugins, Libraries, LibraryPluginFlow, Plugins, Tags, Tasks

logger = CompressoLogging.get_logger(name=__name__)


class LibraryLookupError(ValueError):
    """Raised when a requested library identifier is invalid or missing."""


class LibraryConfig(TypedDict):
    id: int
    name: str
    path: str
    locked: bool
    enable_remote_only: bool
    enable_scanner: bool
    enable_inotify: bool
    tags: list[str]
    target_codecs: NotRequired[str]
    skip_codecs: NotRequired[str]
    size_guardrail_enabled: NotRequired[bool]
    size_guardrail_min_pct: NotRequired[int]
    size_guardrail_max_pct: NotRequired[int]
    replacement_policy: NotRequired[str]


def generate_random_library_name() -> str:
    names = [
        "Willes",
        "Here",
        "Helry",
        "Vyncent",
        "Burgwy",
        "Homas Yournet",
        "Roguy Eldys",
        "George Ewes",
        "Hearda",
        "Mathye Gedde",
        "Wynfre",
        "Gauwill",
        "Aldhert",
        "Ryany",
        "Reward",
        "Atwulf",
        "Amer",
        "Alten Yourner",
        "Reda",
        "Oled",
        "Anthohn Dene",
        "Rarder",
        "Artin Borne",
        "Eadwean",
        "Freyny Loray",
        "Breda",
        "Gauwalt Nynsell",
        "Lodwy",
        "Exam",
        "Alters Corby",
        "Wilhye",
        "Gery",
        "Raffin",
        "Ceolbehrt",
        "Jamath",
        "George Sone",
        "Geoffrey Nette",
        "Eadund",
        "Dunne",
        "Gilda",
        "Aered",
        "Lafa",
        "Eadulf",
        "Eanmaed",
        "Cyni",
        "Draffin",
        "Nichye",
        "Reder",
        "Aldwid",
        "Conbad",
        "Munda",
        "Willex",
        "Ichohn",
        "Orkold",
        "Gyleon",
        "Ealard",
        "Helmund",
        "Nother",
        "Bertio",
        "Phamund Erett",
        "Cuthre",
        "Aewald",
        "Aehehrt",
        "Folke",
        "Ales",
        "Chury Kypwe",
        "Liamund",
        "Rewalt Wyne",
        "Arryn",
        "Charlip",
        "Georguy",
        "Lare",
        "Aenward",
        "Eanwald",
        "Ashwid",
        "Britheard",
        "Cholas",
        "Eolhed",
        "Anwulf",
        "Eorcorht",
        "Piersym",
        "Godre",
        "Edward",
        "Dreder",
        "Geoffry",
        "Wyny",
        "Hardwy",
        "Witio",
        "Grewis",
        "Chilew",
        "Gare",
        "Arnwulf",
        "Masym Arren",
        "Iged",
        "Uwan",
        "Coenwy",
        "Saefa",
        "Thiles",
        "Cyne",
        "Exard",
        "Ichas Horne",
        "Rewilh Morley",
        "Edmur Ferry",
        "Wine",
        "Ered",
        "Lacio",
        "Elres",
        "Gaenbyrtf",
        "Stomund",
        "Riffin Maley",
        "Thiliam Save",
        "Walda",
        "Giles Drighte",
        "Robern Finchey",
        "Wulfa",
        "James",
        "Stiny Fane",
        "Driffin",
        "Andrers",
        "Beorhtio",
        "Balda",
        "Warder",
        "Bealdu",
        "Dene",
        "Andren",
        "Stephye",
        "Ealcar",
        "Richye Corby",
        "Ament Anes",
        "Tharry",
        "Germund",
        "Ralphye Payney",
    ]
    adjectives = [
        "awesome",
        "adorable",
        "abounding",
        "aspiring",
        "beloved",
        "blue",
        "blissful",
        "creamy",
        "cavernous",
        "content",
        "droopy",
        "excited",
        "enchanted",
        "enormous",
        "extroverted",
        "exciting",
        "gullible",
        "gaseous",
        "grumpy",
        "giant",
        "handsome",
        "hefty",
        "harmless",
        "happy",
        "hairy",
        "humdrum",
        "invincible",
        "illiterate",
        "inexperienced",
        "impolite",
        "illustrious",
        "impartial",
        "innocent",
        "jovial",
        "juvenile",
        "joyful",
        "jumpy",
        "jagged",
        "joyous",
        "kooky",
        "large",
        "likeable",
        "mountainous",
        "momentous",
        "minty",
        "nocturnal",
        "nautical",
        "organic",
        "overcooked",
        "productive",
        "plush",
        "polished",
        "queasy",
        "quirky",
        "quintessential",
        "reminiscent",
        "remarkable",
        "ragged",
        "rowdy",
        "soggy",
        "sudden",
        "scandalous",
        "secretive",
        "spry",
        "squiggly",
        "smooth",
        "sulky",
        "scented",
        "spicy",
        "sticky",
        "slushy",
        "symptomatic",
        "tart",
        "turbulent",
        "tiresome",
        "typical",
        "xyloid",
        "xanthic",
        "zealous",
        "zany",
    ]
    return f"{random.choice(names)}, the {random.choice(adjectives)} library"  # noqa: S311 — not used for security/crypto


class Library:
    """
    Library

    Contains all data pertaining to a library

    """

    def __init__(self, library_id: int) -> None:
        # Ensure library ID is not 0
        if library_id < 1:
            raise LibraryLookupError("Library ID cannot be less than 1")
        model = Libraries.get_or_none(id=library_id)
        if model is None:
            raise LibraryLookupError(f"Unable to fetch library with ID {library_id}")
        self.model = model

    @staticmethod
    def get_all_libraries() -> list[LibraryConfig]:
        """
        Return a list of all libraries

        :return:
        """
        # Fetch default library path from
        from compresso.config import Config

        default_library_path = Config().get_library_path()
        if not default_library_path:
            default_library_path = common.get_default_library_path()

        # Fetch all libraries from DB
        configured_libraries = Libraries.select()

        # Ensure that at least the default path was added.
        # If the libraries path is empty, then we should add the default path
        if not configured_libraries:
            seeded_default: LibraryConfig = {
                "id": 1,
                "name": generate_random_library_name(),
                "path": default_library_path,
                "locked": False,
                "enable_remote_only": False,
                "enable_scanner": False,
                "enable_inotify": False,
                "tags": [],
            }
            Libraries.create(**seeded_default)
            return [seeded_default]

        # Loop over results
        default_libraries: list[LibraryConfig] = []
        libraries: list[LibraryConfig] = []
        for lib in configured_libraries:
            # Always update the default library path
            if lib.id == 1 and lib.path != default_library_path:
                lib.path = default_library_path
                lib.save()
            # Create library config dictionary
            library_config: LibraryConfig = {
                "id": lib.id,
                "name": lib.name,
                "path": lib.path,
                "locked": lib.locked,
                "enable_remote_only": lib.enable_remote_only,
                "enable_scanner": lib.enable_scanner,
                "enable_inotify": lib.enable_inotify,
                "target_codecs": lib.target_codecs or "",
                "skip_codecs": lib.skip_codecs or "",
                "size_guardrail_enabled": bool(lib.size_guardrail_enabled),
                "size_guardrail_min_pct": lib.size_guardrail_min_pct,
                "size_guardrail_max_pct": lib.size_guardrail_max_pct,
                "replacement_policy": lib.replacement_policy or "",
                "tags": [],
            }
            # Append tags
            for tag in lib.tags.order_by(Tags.name):
                library_config["tags"].append(tag.name)

            # Keep the default library separate
            if lib.id == 1:
                default_libraries.append(library_config)
                continue
            libraries.append(library_config)

        # Return the list of libraries sorted by name
        return default_libraries + sorted(libraries, key=lambda d: d["name"])

    @staticmethod
    def within_library_count_limits() -> bool:
        # All features unlocked — no library count limits
        frontend_messages = FrontendPushMessages()
        frontend_messages.remove_item("libraryEnabledLimits")
        return True

    @staticmethod
    def create(data: dict[str, object]) -> "Library":
        """
        Create a new library

        :param data:
        :return:
        """
        # Ensure ID is removed from data for a create
        if "id" in data:
            del data["id"]
        new_library = Libraries.create(**data)
        return Library(new_library.id)

    @staticmethod
    def export(library_id: int) -> dict[str, object]:
        from compresso.libs.plugins import PluginsHandler

        # Read the library
        library_config = Library(library_id)

        # Get list of enabled plugins with their settings
        enabled_plugins: list[dict[str, object]] = []
        for enabled_plugin in library_config.get_enabled_plugins(include_settings=True):
            enabled_plugins.append(
                {
                    "plugin_id": enabled_plugin.get("plugin_id"),
                    "has_config": enabled_plugin.get("has_config"),
                    "settings": enabled_plugin.get("settings"),
                }
            )

        # Create plugin flow
        plugin_flow: dict[str, list[object]] = {}

        plugin_handler = PluginsHandler()
        for plugin_type in plugin_handler.get_plugin_types_with_flows():
            plugin_flow[plugin_type] = []
            flow = plugin_handler.get_enabled_plugin_flows_for_plugin_type(plugin_type, library_id)
            for f in flow:
                plugin_flow[plugin_type].append(f.get("plugin_id"))

        return {
            "plugins": {
                "enabled_plugins": enabled_plugins,
                "plugin_flow": plugin_flow,
            },
            "library_config": {
                "name": library_config.get_name(),
                "path": library_config.get_path(),
                "enable_remote_only": library_config.get_enable_remote_only(),
                "enable_scanner": library_config.get_enable_scanner(),
                "enable_inotify": library_config.get_enable_inotify(),
                "tags": library_config.get_tags(),
            },
        }

    def __remove_enabled_plugins(self) -> int:
        """
        Remove all enabled plugins

        :return:
        """
        query = EnabledPlugins.delete()
        query = query.where(EnabledPlugins.library_id == self.model.id)
        return execute_count(query)

    def __trim_plugin_flow(self, plugin_ids: Sequence[int]) -> int:
        """
        Trim the plugin flow removing entries not in the given plugin ids list

        :param plugin_ids:
        :return:
        """
        query = LibraryPluginFlow.delete()
        query = query.where((LibraryPluginFlow.library_id == self.model.id) & (LibraryPluginFlow.plugin_id.not_in(plugin_ids)))
        return execute_count(query)

    def __remove_associated_tasks(self) -> None:
        """
        Remove all tasks associated with a library

        :return:
        """
        from compresso.libs import task as task_module

        select_query = Tasks.select(Tasks.id).where(Tasks.library_id == self.model.id)
        task_ids = [task_row.id for task_row in select_query]
        for task_id in task_ids:
            task_module.TaskDataStore.clear_task(task_id)

        execute_write(Tasks.delete().where(Tasks.library_id == self.model.id))

    def get_id(self) -> int:
        return int(self.model.id)

    def get_name(self) -> str:
        return str(self.model.name)

    def set_name(self, value: str) -> None:
        self.model.name = value

    def get_path(self) -> str:
        return str(self.model.path)

    def set_path(self, value: str) -> None:
        self.model.path = value

    def get_locked(self) -> bool:
        return bool(self.model.locked)

    def set_locked(self, value: bool) -> None:
        self.model.locked = value

    def get_enable_remote_only(self) -> bool:
        return bool(self.model.enable_remote_only)

    def set_enable_remote_only(self, value: bool) -> None:
        self.model.enable_remote_only = value

    def get_enable_scanner(self) -> bool:
        return bool(self.model.enable_scanner)

    def set_enable_scanner(self, value: bool) -> None:
        self.model.enable_scanner = value

    def get_enable_inotify(self) -> bool:
        return bool(self.model.enable_inotify)

    def set_enable_inotify(self, value: bool) -> None:
        self.model.enable_inotify = value

    def get_priority_score(self) -> int:
        return int(self.model.priority_score)

    def set_priority_score(self, value: int) -> None:
        self.model.priority_score = value

    def get_tags(self) -> list[str]:
        return_tags: list[str] = []
        for tag in self.model.tags.order_by(Tags.name):
            return_tags.append(tag.name)
        return return_tags

    def set_tags(self, value: Sequence[str]) -> None:
        # Create any missing tags
        for tag_name in value:
            # Do not update any current tags with on_conflict_replace() as this will also change their IDs
            # Instead, just ignore them
            execute_write(Tags.insert(name=tag_name).on_conflict_ignore())
        # Create a SELECT query for all tags with the listed names
        tags_select_query = Tags.select().where(Tags.name.in_(value))
        # Clear out the current linking table of tags linked to this library
        # Add new links for each tag that was fetched matching the provided names
        self.model.tags.add(tags_select_query, clear_existing=True)

    # --- Flow settings: Codec filtering ---

    def get_target_codecs(self) -> list[str]:
        raw = self.model.target_codecs or ""
        if not raw:
            return []
        try:
            parsed: object = json.loads(raw)
            if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                return cast("list[str]", parsed)
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    def set_target_codecs(self, value: Sequence[str] | str | None) -> None:
        if not isinstance(value, str) and value is not None:
            self.model.target_codecs = json.dumps(list(value))
        else:
            self.model.target_codecs = value or ""

    def get_skip_codecs(self) -> list[str]:
        raw = self.model.skip_codecs or ""
        if not raw:
            return []
        try:
            parsed: object = json.loads(raw)
            if isinstance(parsed, list) and all(isinstance(item, str) for item in parsed):
                return cast("list[str]", parsed)
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    def set_skip_codecs(self, value: Sequence[str] | str | None) -> None:
        if not isinstance(value, str) and value is not None:
            self.model.skip_codecs = json.dumps(list(value))
        else:
            self.model.skip_codecs = value or ""

    # --- Flow settings: Size guardrails ---

    def get_size_guardrail_enabled(self) -> bool:
        return bool(self.model.size_guardrail_enabled)

    def set_size_guardrail_enabled(self, value: object) -> None:
        self.model.size_guardrail_enabled = bool(value)

    def get_size_guardrail_min_pct(self) -> int:
        return int(self.model.size_guardrail_min_pct)

    def set_size_guardrail_min_pct(self, value: int | str) -> None:
        val = max(5, min(95, int(value)))
        self.model.size_guardrail_min_pct = val

    def get_size_guardrail_max_pct(self) -> int:
        return int(self.model.size_guardrail_max_pct)

    def set_size_guardrail_max_pct(self, value: int | str) -> None:
        val = max(50, min(100, int(value)))
        self.model.size_guardrail_max_pct = val

    # --- Flow settings: Replacement policy ---

    def get_replacement_policy(self) -> str:
        return self.model.replacement_policy or ""

    def set_replacement_policy(self, value: str | None) -> None:
        valid_policies = ("", "replace", "approval_required", "keep_both")
        policy = value or ""
        if policy not in valid_policies:
            policy = ""
        self.model.replacement_policy = policy

    def get_enabled_plugins(self, include_settings: bool = False) -> list[dict[str, object]]:
        """
        Get all enabled plugins for this library

        :return:
        """
        # Fetch enabled plugins for this library
        query = EnabledPlugins.select(Plugins, EnabledPlugins.library_id)
        query = query.where(EnabledPlugins.library_id == self.model.id)
        query = query.join(Plugins, join_type="LEFT OUTER JOIN", on=(EnabledPlugins.plugin_id == Plugins.id))
        query = query.order_by(Plugins.name)

        from compresso.libs.unplugins import PluginExecutor

        plugin_executor = PluginExecutor()

        # Extract required data
        enabled_plugins: list[dict[str, object]] = []
        enabled_plugin_rows = cast("Iterable[dict[str, object]]", query.dicts())
        for enabled_plugin in enabled_plugin_rows:
            # A dangling EnabledPlugins row (plugin deleted) yields NULL plugin
            # columns via the LEFT OUTER JOIN; skip it rather than surfacing a
            # half-empty entry that downstream consumers cannot use.
            if enabled_plugin.get("name") is None and enabled_plugin.get("plugin_id") is None:
                logger.warning("Ignoring orphaned enabled-plugin row for library %s", self.model.id)
                continue
            # Check if plugin is able to be configured
            has_config = False
            plugin_id = enabled_plugin.get("plugin_id")
            plugin_settings, plugin_settings_meta = plugin_executor.get_plugin_settings(
                plugin_id if isinstance(plugin_id, str) else "", library_id=self.model.id
            )
            if plugin_settings:
                has_config = True
            # Add plugin to list of enabled plugins
            item = {
                "plugin_id": enabled_plugin.get("plugin_id"),
                "name": enabled_plugin.get("name"),
                "description": enabled_plugin.get("description"),
                "icon": enabled_plugin.get("icon"),
                "has_config": has_config,
            }
            if include_settings:
                item["settings"] = plugin_settings
            enabled_plugins.append(item)

        return enabled_plugins

    def get_plugin_flow(self) -> dict[str, list[dict[str, object]]]:
        """
        Fetch the plugin flow for a library

        :return:
        """
        plugin_flow: dict[str, list[dict[str, object]]] = {}
        from compresso.libs.plugins import PluginsHandler

        plugin_handler = PluginsHandler()
        from compresso.libs.unplugins import PluginExecutor

        plugin_ex = PluginExecutor()
        for plugin_type in plugin_ex.get_all_plugin_types():
            # Ignore types without flows
            if not plugin_type.get("has_flow"):
                continue

            plugin_type_id = plugin_type.get("id")
            if not isinstance(plugin_type_id, str):
                continue
            # Create list of plugins in this plugin type
            plugin_flow[plugin_type_id] = []
            plugin_modules = plugin_handler.get_enabled_plugin_modules_by_type(plugin_type_id, library_id=self.model.id)
            for plugin_module in plugin_modules:
                plugin_flow[plugin_type_id].append(
                    {
                        "plugin_id": plugin_module.get("plugin_id"),
                        "name": plugin_module.get("name", ""),
                        "author": plugin_module.get("author", ""),
                        "description": plugin_module.get("description", ""),
                        "version": plugin_module.get("version", ""),
                        "icon": plugin_module.get("icon", ""),
                    }
                )

        return plugin_flow

    def __set_default_plugin_flow_priority(self, plugin_list: Sequence[Mapping[str, object]]) -> None:
        from compresso.libs.unplugins import PluginExecutor

        plugin_executor = PluginExecutor()
        from compresso.libs.plugins import PluginsHandler

        plugin_handler = PluginsHandler()

        # Fetch current items
        configured_plugin_ids: list[str] = []
        query = LibraryPluginFlow.select().where(LibraryPluginFlow.library_id == self.model.id)
        for flow_item in query:
            configured_plugin_ids.append(flow_item.plugin_id.plugin_id)

        for plugin in plugin_list:
            plugin_id = plugin.get("plugin_id")
            if not isinstance(plugin_id, str):
                continue
            # Ignore already configured plugins
            if plugin_id in configured_plugin_ids:
                continue
            plugin_info = plugin_handler.get_plugin_info(plugin_id)
            if not isinstance(plugin_info, Mapping):
                continue
            plugin_priorities = plugin_info.get("priorities")
            if isinstance(plugin_priorities, Mapping):
                # Fetch the plugin info back from the DB
                plugin_model = Plugins.select().where(Plugins.plugin_id == plugin_id).first()
                if plugin_model is None:
                    continue
                # Fetch all plugin types in this plugin
                plugin_types_in_plugin = plugin_executor.get_all_plugin_types_in_plugin(plugin_id)
                # Loop over the plugin types in this plugin
                for plugin_type in plugin_types_in_plugin:
                    # get the plugin runner function name for this runner
                    plugin_type_meta = plugin_executor.get_plugin_type_meta(plugin_type)
                    runner_string = plugin_type_meta.plugin_runner()
                    priority = plugin_priorities.get(runner_string)
                    if isinstance(priority, (int, str)) and int(priority) > 0:
                        # If the runner has a priority set and that value is greater than 0 (default that wont set anything),
                        # Save the priority
                        PluginsHandler.set_plugin_flow_position_for_single_plugin(
                            plugin_model, plugin_type, self.model.id, int(priority)
                        )

    def set_enabled_plugins(self, plugin_list: Sequence[Mapping[str, object]]) -> None:
        """
        Update the list of enabled plugins

        :param plugin_list:
        :return:
        """
        # Remove all enabled plugins
        self.__remove_enabled_plugins()

        # Add new repos
        data: list[dict[str, object]] = []
        plugin_ids: list[int] = []
        for plugin_info in plugin_list:
            plugin_id = plugin_info.get("plugin_id")
            if not isinstance(plugin_id, str):
                continue
            plugin = Plugins.get(plugin_id=plugin_id)
            plugin_ids.append(plugin.id)
            if plugin:
                data.append(
                    {
                        "library_id": self.model.id,
                        "plugin_id": plugin,
                        "plugin_name": plugin.name,
                    }
                )

        # Delete all plugin flows for plugins not to be enabled for this library
        self.__trim_plugin_flow(plugin_ids)

        # Insert plugins
        execute_write(EnabledPlugins.insert_many(data))

        # Add default flow for newly added plugins
        self.__set_default_plugin_flow_priority(plugin_list)

    def save(self) -> int:
        """
        Save the data for this library

        :return:
        """
        # Save changes made to model
        save_result = self.model.save()

        # If this is the default library path, save to config.library_path object also
        if self.get_id() == 1:
            config = Config()
            config.set_config_item("library_path", self.get_path())

        return int(save_result)

    def delete(self) -> int:
        """
        Delete the current library

        :return:
        """
        # Ensure we can never delete library ID 1 (the default library)
        if self.get_id() == 1:
            raise Exception("Unable to remove the default library")

        # Ensure we are not trying to delete a locked library
        if self.get_locked():
            raise Exception("Unable to remove a locked library")

        # Remove all enabled plugins
        self.__remove_enabled_plugins()

        # Remove all plugin flows
        self.__trim_plugin_flow([])

        # Delete all tasks with matching library_id
        self.__remove_associated_tasks()

        # Remove the library entry
        return int(self.model.delete_instance(recursive=True))
