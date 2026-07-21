#!/usr/bin/env python3

"""
compresso.plugins.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     25 Aug 2021, (3:49 PM)

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

import os

import tornado.escape
import tornado.log
import tornado.web

from compresso.webserver.helpers import plugins
from compresso.webserver.request_auth import authorize_request
from compresso.webserver.security_headers import SecurityHeadersMixin


def _string(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def get_plugin_by_path(path: str) -> dict[str, object] | None:
    # Get the plugin ID from the url
    split_path = path.split("/")
    if len(split_path) < 4:
        return None
    plugin_type = split_path[2]
    plugin_id = split_path[3]
    if plugin_type == "plugin_api":
        # Fetch all api plugins
        results = plugins.get_enabled_plugin_plugin_apis()
    else:
        # Fetch all frontend plugins
        results = plugins.get_enabled_plugin_data_panels()
    # Check if their path matches
    plugin_module = None
    for result in results:
        if plugin_id == result.get("plugin_id"):
            plugin_module = result
            break
    return plugin_module


class DataPanelRequestHandler(SecurityHeadersMixin, tornado.web.RequestHandler):
    name: str

    def initialize(self) -> None:
        self.name = "DataPanel"

    def get(self, path: str) -> None:
        self.handle_panel_request()

    def handle_panel_request(self) -> None:
        # Get the remainder of the path after the plugin ID. This will be passed as path
        path = list(filter(None, self.request.path.split("/")[4:]))

        # Escape user-provided values to prevent reflected XSS
        safe_path = "/" + "/".join(tornado.escape.xhtml_escape(p) for p in path)
        safe_uri = tornado.escape.xhtml_escape(self.request.uri or "")
        safe_query = tornado.escape.xhtml_escape(self.request.query or "")
        safe_arguments = {
            k: [tornado.escape.xhtml_escape(v.decode("utf-8", errors="replace")) for v in vals]
            for k, vals in self.request.arguments.items()
        }

        # Generate default data
        data: dict[str, object] = {
            "content_type": "text/html",
            "content": "<!doctype html><html><head></head><body></body></html>",
            "path": safe_path,
            "uri": safe_uri,
            "query": safe_query,
            "arguments": safe_arguments,
        }
        plugin_module = get_plugin_by_path(self.request.path)
        if not plugin_module:
            self.set_status(404)
            self.write("404 Not Found")
            return

        # Run plugin and fetch return data
        plugin_id = _string(plugin_module.get("plugin_id"))
        if not plugins.exec_data_panels_plugin_runner(data, plugin_id):
            tornado.log.app_log.error("Failed to execute plugin runner on DataPanel '%s'", plugin_module.get("plugin_id"))
            self.set_status(500)
            self.write("Plugin execution failed")
            return

        self.render_data(data)
        return

    def render_data(self, data: dict[str, object]) -> None:
        # Always serve DataPanel content as escaped HTML to prevent reflected XSS.
        # Plugin runners receive sanitized inputs and generate the content, but we
        # escape on output as defense-in-depth since the data dict is mutable.
        self.set_header("Content-Type", "text/html")
        self.set_security_headers()
        content = data.get("content", "")
        self.write(tornado.escape.xhtml_escape(str(content)))


class PluginAPIRequestHandler(SecurityHeadersMixin, tornado.web.RequestHandler):
    name: str

    def initialize(self) -> None:
        self.name = "PluginAPI"

    def prepare(self) -> None:
        if not authorize_request(self):
            return

    def get(self, path: str) -> None:
        self.handle_panel_request()

    def post(self, path: str) -> None:
        self.handle_panel_request()

    def delete(self, path: str) -> None:
        self.handle_panel_request()

    def put(self, path: str) -> None:
        self.handle_panel_request()

    def handle_panel_request(self) -> None:
        path = list(filter(None, self.request.path.split("/")[4:]))

        # Sanitize user-provided values to break taint flow from request to output.
        # Even though output is JSON-serialized, sanitizing inputs prevents any
        # plugin runner from inadvertently reflecting raw user input.
        safe_path = "/" + "/".join(tornado.escape.xhtml_escape(p) for p in path)
        safe_uri = tornado.escape.xhtml_escape(self.request.uri or "")
        safe_query = tornado.escape.xhtml_escape(self.request.query or "")
        safe_arguments = {
            k: [tornado.escape.xhtml_escape(v.decode("utf-8", errors="replace")) for v in vals]
            for k, vals in self.request.arguments.items()
        }
        data: dict[str, object] = {
            "content_type": "application/json",
            "content": {},
            "status": 200,
            "method": self.request.method,
            "path": safe_path,
            "uri": safe_uri,
            "query": safe_query,
            "arguments": safe_arguments,
            "body": self.request.body,
        }
        plugin_module = get_plugin_by_path(self.request.path)
        if not plugin_module:
            self.set_status(404, reason="404 Not Found")
            status_code = self.get_status()
            self.write(
                {
                    "error": f"{status_code:d}: {self._reason}",
                    "messages": {},
                }
            )
            return

        # Run plugin and fetch return data
        plugin_id = _string(plugin_module.get("plugin_id"))
        try:
            if not plugins.exec_plugin_api_plugin_runner(data, plugin_id):
                tornado.log.app_log.exception(
                    f"Exception while carrying out plugin runner on PluginAPI '{plugin_module.get('plugin_id')}'"
                )
        except Exception:
            tornado.log.app_log.exception(
                f"Exception while carrying out plugin runner on PluginAPI '{plugin_module.get('plugin_id')}'"
            )
            self.set_status(500, reason="Internal server error")
            status_code = self.get_status()
            self.write(
                {
                    "error": f"{status_code:d}: {self._reason}",
                    "messages": {},
                }
            )
            return

        self.render_data(data)

    def render_data(self, data: dict[str, object]) -> None:
        # Always force JSON content type for API responses to prevent XSS
        self.set_header("Content-Type", "application/json")
        self.set_security_headers()
        status_value = data.get("status")
        self.set_status(status_value if isinstance(status_value, int) else 200)
        content = data.get("content", {})
        # Use Tornado's json_encode which escapes '</' sequences to prevent
        # script injection when JSON is embedded in HTML contexts
        self.write(tornado.escape.json_encode(content))


class PluginStaticFileHandler(tornado.web.StaticFileHandler):
    """
    A static file handler which serves static content from a plugin '/static/' directory.
    """

    def initialize(self, path: str, default_filename: str | None = None) -> None:
        plugin_module = get_plugin_by_path(self.request.path)
        if plugin_module:
            path = os.path.join(_string(plugin_module.get("plugin_path")), "static")
        super().initialize(path, default_filename)
