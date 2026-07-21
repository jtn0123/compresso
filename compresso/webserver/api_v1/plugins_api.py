#!/usr/bin/env python3

"""
compresso.plugins_api.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     03 Mar 2021, (12:10 PM)

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
from collections.abc import Mapping

import tornado.log

from compresso.libs.plugins import PluginsHandler
from compresso.libs.uiserver import CompressoDataQueues, DataQueues
from compresso.libs.unplugins import PluginExecutor
from compresso.webserver.api_v1.base_api_handler import BaseApiHandler


class ApiPluginsHandler(BaseApiHandler):
    name: str
    params: object
    compresso_data_queues: DataQueues

    routes = [
        {
            "supported_methods": ["GET"],
            "call_method": "get_plugin_list",
            "path_pattern": r"/api/v1/plugins/list",
        },
        {
            "supported_methods": ["POST"],
            "call_method": "install_plugin_by_id",
            "path_pattern": r"/api/v1/plugins/install",
        },
        {
            "supported_methods": ["GET"],
            "call_method": "get_repo_list",
            "path_pattern": r"/api/v1/plugins/repos/list",
        },
        {
            "supported_methods": ["POST"],
            "call_method": "update_repo_list",
            "path_pattern": r"/api/v1/plugins/repos/update",
        },
        {
            "supported_methods": ["GET"],
            "call_method": "update_repos",
            "path_pattern": r"/api/v1/plugins/repos/fetch",
        },
    ]

    def initialize(self, **kwargs: object) -> None:
        self.name = "plugins_api"
        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()

    def set_default_headers(self) -> None:
        """Set the default response header to be JSON."""
        super().set_default_headers()

    async def get(self, path: str) -> None:
        self.action_route()

    async def post(self, path: str) -> None:
        self.action_route()

    def prepare_filtered_plugins(self, request_dict: Mapping[str, object]) -> dict[str, object]:
        """
        Returns a object of records filtered and sorted
        according to the provided request.

        :param request_dict:
        :return:
        """

        # Generate filters for query
        start_value = request_dict.get("start")
        length_value = request_dict.get("length")
        start = start_value if isinstance(start_value, int) and not isinstance(start_value, bool) else 0
        length = length_value if isinstance(length_value, int) and not isinstance(length_value, bool) else 0

        search_value_raw = request_dict.get("search")
        search = search_value_raw if isinstance(search_value_raw, Mapping) else {}
        search_entry = search.get("value")
        search_value = search_entry if isinstance(search_entry, str) else ""

        # Force sort order always by ID desc
        order = [
            {
                "column": "name",
                "dir": "asc",
            }
        ]

        # Fetch Plugins
        plugins = PluginsHandler()
        # Get total count
        records_total_count = plugins.get_total_plugin_list_count()
        # Get quantity after filters (without pagination)
        filtered_plugins = plugins.get_plugin_list_filtered_and_sorted(
            order=order, start=0, length=0, search_value=search_value
        )
        records_filtered_count = filtered_plugins.count() if filtered_plugins is not None else 0
        # Get filtered/sorted results
        plugin_results = plugins.get_plugin_list_filtered_and_sorted(
            order=order, start=start, length=length, search_value=search_value
        )

        # Build return data
        data: list[dict[str, object]] = []
        return_data: dict[str, object] = {
            "draw": request_dict.get("draw"),
            "recordsTotal": records_total_count,
            "recordsFiltered": records_filtered_count,
            "successCount": 0,
            "failedCount": 0,
            "data": data,
        }

        # Iterate over plugins and append them to the plugin data
        for plugin_result in plugin_results or []:
            # Set plugin status
            plugin_status = {
                "enabled": plugin_result.get("enabled"),
                "update_available": plugin_result.get("update_available"),
            }
            # Set params as required in template
            item = {
                "id": plugin_result.get("id"),
                "plugin_id": plugin_result.get("plugin_id"),
                "icon": plugin_result.get("icon"),
                "name": plugin_result.get("name"),
                "description": plugin_result.get("description"),
                "tags": plugin_result.get("tags"),
                "author": plugin_result.get("author"),
                "version": plugin_result.get("version"),
                "status": plugin_status,
                "selected": False,
            }
            data.append(item)

        # Return results
        return return_data

    def update_repo_list(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        repos_text = self.get_argument("repos_list")

        repos_list = repos_text.splitlines() if repos_text else []

        try:
            plugins = PluginsHandler()
            plugins.set_plugin_repos(repos_list)
        except Exception as e:
            tornado.log.app_log.exception(f"Exception in updating repo list - {str(e)}", exc_info=True)

        self.get_repo_list()

    def get_repo_list(self) -> None:
        try:
            plugins = PluginsHandler()
            # Fetch the data again from the database
            current_repos = plugins.get_plugin_repos()

            # Remove the default plugin repo from the list
            return_repos: list[dict[str, object]] = []
            default_repo = plugins.get_default_repo()
            for repo in current_repos:
                repo_path = repo.get("path")
                if isinstance(repo_path, str) and not repo_path.startswith(default_repo):
                    return_repos.append(repo)

            # Return success
            self.write(json.dumps({"success": True, "repos": return_repos}))
        except Exception as e:
            tornado.log.app_log.exception(f"Exception in fetching the current repo list - {str(e)}", exc_info=True)

            # Return failure
            self.write(json.dumps({"success": False}))

    def update_repos(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        plugins = PluginsHandler()
        if plugins.update_plugin_repos():
            # Return success
            self.write(json.dumps({"success": True}))
        else:
            # Return failure
            self.write(json.dumps({"success": False}))

    def get_plugin_list(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        plugins = PluginsHandler()
        # Fetch a list of plugin data cached locally
        plugin_list = plugins.get_installable_plugins_list()
        self.write(json.dumps({"success": True, "plugins": plugin_list}))

    def install_plugin_by_id(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        plugin_id = self.get_argument("plugin_id")

        # Fetch a list of plugin data cached locally
        plugins = PluginsHandler()
        success = plugins.install_plugin_by_id(plugin_id)

        if success:
            # Return success
            self.write(json.dumps({"success": True}))
        else:
            # Return failure
            self.write(json.dumps({"success": False}))

    def __get_plugin_changelog(self, plugin_id: str) -> list[str]:
        """
        Given a plugin ID , return a list of lines read from the plugin's changelog

        :param plugin_id:
        :return:
        """
        # Fetch plugin changelog
        plugin_executor = PluginExecutor()
        return plugin_executor.get_plugin_changelog(plugin_id)

    def __get_plugin_long_description(self, plugin_id: str) -> list[str]:
        """
        Given a plugin ID , return a list of lines read from the plugin's changelog

        :param plugin_id:
        :return:
        """
        # Fetch plugin changelog
        plugin_executor = PluginExecutor()
        return plugin_executor.get_plugin_long_description(plugin_id)
