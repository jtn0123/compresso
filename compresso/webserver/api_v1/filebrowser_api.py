#!/usr/bin/env python3

"""
compresso.file_browser_api.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     11 Apr 2021, (7:06 PM)

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

from compresso.libs.uiserver import CompressoDataQueues
from compresso.webserver.api_v1.base_api_handler import BaseApiHandler


def _validate_browsable_path(user_path):
    """Resolve and validate a user-provided filesystem path for browsing.

    Returns a canonical absolute path with traversal sequences resolved.
    Rejects null bytes and paths outside a valid filesystem root.
    """
    if not user_path or "\x00" in str(user_path):
        return os.sep
    resolved = os.path.realpath(user_path)
    # Build the filesystem root for this path (handles drive letters on Windows)
    drive, _ = os.path.splitdrive(resolved)
    fs_root = drive + os.sep if drive else os.sep
    if not resolved.startswith(fs_root):
        return os.sep
    return resolved


class ApiFilebrowserHandler(BaseApiHandler):
    name = None
    params = None
    compresso_data_queues = None

    routes = [
        {
            "supported_methods": ["POST"],
            "call_method": "fetch_directory_listing",
            "path_pattern": r"/api/v1/filebrowser/list",
        },
    ]

    def initialize(self, **kwargs):
        self.name = "file_browser_api"
        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()

    def set_default_headers(self):
        """Set the default response header to be JSON."""
        self.set_header("Content-Type", 'application/json; charset="utf-8"')

    def get(self, path):
        self.action_route()

    def post(self, path):
        self.action_route()

    def fetch_directory_listing(self, *args, **kwargs):
        current_path = _validate_browsable_path(self.get_argument("current_path", "/"))
        list_type = self.get_argument("list_type", "all")

        path_data = self.fetch_path_data(current_path, list_type)

        self.finish(tornado.escape.json_encode(path_data))

    def fetch_path_data(self, current_path, list_type="directories"):
        """
        Returns an object filled with data pertaining to a particular path

        :param current_path:
        :param list_type:
        :return:
        """
        directories = []
        files = []
        if list_type == "directories" or list_type == "all":
            directories = self.fetch_directories(current_path)
        if list_type == "files" or list_type == "all":
            files = self.fetch_files(current_path)
        path_data = {
            "current_path": current_path,
            "list_type": list_type,
            "directories": directories,
            "files": files,
            "success": True,
        }
        return path_data

    def fetch_directories(self, path):
        """
        Fetch a list of directory objects based on a given path

        :param path:
        :return:
        """
        safe_path = _validate_browsable_path(path)
        results = []
        if os.path.exists(safe_path):
            # check if this is a root path or if it has a parent
            parent_path = _validate_browsable_path(os.path.join(safe_path, ".."))
            if parent_path != safe_path:
                # Path has a parent, Add the double dots
                results.append(
                    {
                        "name": "..",
                        "full_path": parent_path,
                    }
                )
            try:
                for item in sorted(os.listdir(safe_path)):
                    abspath = _validate_browsable_path(os.path.join(safe_path, item))
                    if os.path.isdir(abspath):
                        results.append(
                            {
                                "name": item,
                                "full_path": abspath,
                            }
                        )
            except OSError:
                pass
        else:
            # Path doesn't exist!
            # Just return the root dir as the first directory option
            results.append(
                {
                    "name": "/",
                    "full_path": "/",
                }
            )
        return results

    def fetch_files(self, path):
        """
        Fetch a list of file objects based on a given path

        :param path:
        :return:
        """
        safe_path = _validate_browsable_path(path)
        results = []
        if os.path.exists(safe_path):
            try:
                for item in sorted(os.listdir(safe_path)):
                    abspath = _validate_browsable_path(os.path.join(safe_path, item))
                    if os.path.isfile(abspath):
                        results.append(
                            {
                                "name": item,
                                "full_path": abspath,
                            }
                        )
            except OSError:
                pass
        return results
