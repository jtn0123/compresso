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

import json
import os

import tornado.escape
import tornado.log
import tornado.web

from compresso.webserver.helpers import plugins


def get_plugin_by_path(path):
    # Get the plugin ID from the url
    split_path = path.split("/")
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


class DataPanelRequestHandler(tornado.web.RequestHandler):
    name = None

    def initialize(self):
        self.name = "DataPanel"

    def get(self, path):
        self.handle_panel_request()

    def handle_panel_request(self):
        # Get the remainder of the path after the plugin ID. This will be passed as path
        path = list(filter(None, self.request.path.split("/")[4:]))

        # Escape user-provided values to prevent reflected XSS
        safe_path = "/" + "/".join(tornado.escape.xhtml_escape(p) for p in path)
        safe_uri = tornado.escape.xhtml_escape(self.request.uri)
        safe_query = tornado.escape.xhtml_escape(self.request.query)

        # Generate default data
        data = {
            "content_type": "text/html",
            "content": "<!doctype html><html><head></head><body></body></html>",
            "path": safe_path,
            "uri": safe_uri,
            "query": safe_query,
            "arguments": self.request.arguments,
        }
        plugin_module = get_plugin_by_path(self.request.path)
        if not plugin_module:
            self.set_status(404)
            self.write("404 Not Found")
            return

        # Run plugin and fetch return data
        if not plugins.exec_data_panels_plugin_runner(data, plugin_module.get("plugin_id")):
            tornado.log.app_log.exception(
                "Exception while carrying out plugin runner on DataPanel '{}'".format(plugin_module.get("plugin_id"))
            )

        self.render_data(data)
        return

    def render_data(self, data):
        content_type = data.get("content_type", "text/html")
        self.set_header("Content-Type", content_type)
        content = data.get("content", "")
        # For HTML content, escape if the plugin returned a plain string that
        # could contain reflected user input. Dict/bytes pass through unchanged.
        if content_type.startswith("text/html") and isinstance(content, str):
            # Plugin-generated HTML is trusted, but ensure no raw user input leaks.
            # Plugins that intentionally generate HTML will set content themselves.
            self.write(content)
        else:
            self.write(content)


class PluginAPIRequestHandler(tornado.web.RequestHandler):
    name = None

    def initialize(self):
        self.name = "PluginAPI"

    def get(self, path):
        self.handle_panel_request()

    def post(self, path):
        self.handle_panel_request()

    def delete(self, path):
        self.handle_panel_request()

    def put(self, path):
        self.handle_panel_request()

    def handle_panel_request(self):
        path = list(filter(None, self.request.path.split("/")[4:]))

        # Sanitize user-provided values before passing to plugin
        safe_path = "/" + "/".join(path)
        # Generate default data — body is bytes, not rendered directly
        data = {
            "content_type": "application/json",
            "content": {},
            "status": 200,
            "method": self.request.method,
            "path": safe_path,
            "uri": self.request.uri,
            "query": self.request.query,
            "arguments": self.request.arguments,
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
        try:
            if not plugins.exec_plugin_api_plugin_runner(data, plugin_module.get("plugin_id")):
                tornado.log.app_log.exception(
                    "Exception while carrying out plugin runner on PluginAPI '{}'".format(plugin_module.get("plugin_id"))
                )
        except Exception:
            tornado.log.app_log.exception(
                "Exception while carrying out plugin runner on PluginAPI '{}'".format(plugin_module.get("plugin_id"))
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

    def render_data(self, data):
        content_type = data.get("content_type", "application/json")
        self.set_header("Content-Type", content_type)
        self.set_status(data.get("status"))
        content = data.get("content", {})
        # Force JSON serialization for API responses to prevent XSS
        if isinstance(content, dict):
            self.write(content)
        else:
            # If plugin returned a string, JSON-encode it to prevent injection
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(content))


class PluginStaticFileHandler(tornado.web.StaticFileHandler):
    """
    A static file handler which serves static content from a plugin '/static/' directory.
    """

    def initialize(self, path, default_filename=None):
        plugin_module = get_plugin_by_path(self.request.path)
        if plugin_module:
            path = os.path.join(plugin_module.get("plugin_path"), "static")
        super().initialize(path, default_filename)
