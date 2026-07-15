#!/usr/bin/env python3

"""
compresso.upload_api.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     01 Oct 2021, (12:55 AM)

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

import asyncio
import os
import tempfile
import threading
from pathlib import Path

import tornado.web

from compresso import config
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler

MB = 1024 * 1024
MAX_PLUGIN_UPLOAD_SIZE = 64 * MB
TRANSFER_SUCCESSORS = {
    "create": "/compresso/api/v2/transfer/session",
    "chunk": "/compresso/api/v2/transfer/chunk/{transfer_id}",
    "finalize": "/compresso/api/v2/transfer/finalize/{transfer_id}",
}
_PLUGIN_INSTALL_LOCK = threading.Lock()


def _persist_plugin_upload(upload_root, body):
    """Write a framework-parsed upload outside the async request loop."""
    upload_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_path = tempfile.mkstemp(prefix="plugin-", suffix=".zip", dir=upload_root)
    upload_path = Path(temporary_path)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(body)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        upload_path.unlink(missing_ok=True)
        raise
    return upload_path


def _install_plugin_serialized(plugins_handler, upload_path):
    """Prevent overlapping legacy installers until PR 5 adds per-plugin transactions."""
    with _PLUGIN_INSTALL_LOCK:
        return plugins_handler.install_plugin_from_path_on_disk(upload_path)


@tornado.web.stream_request_body
class ApiUploadHandler(BaseApiHandler):
    """Compatibility endpoint that rejects retired media-file uploads early."""

    routes = [
        {
            "path_pattern": r"/upload/pending/file",
            "supported_methods": ["POST"],
            "call_method": "retire_pending_upload",
        }
    ]

    def prepare(self):
        super().prepare()
        if not self._finished:
            self._write_retirement_response()

    def data_received(self, chunk):
        """Discard bytes if a client races the early 410 response."""

    def _write_retirement_response(self):
        self.set_status(410)
        self.finish(
            {
                "error": "410: Legacy media upload retired",
                "successor": dict(TRANSFER_SUCCESSORS),
            }
        )

    async def retire_pending_upload(self):
        """Return the resumable-transfer successor contract.
        ---
        description: This legacy media-ingress route is retired; use resumable transfer endpoints.
        deprecated: true
        responses:
          410:
            description: Legacy media upload is gone and successor endpoint templates are returned.
        """
        if not self._finished:
            self._write_retirement_response()


class ApiPluginUploadHandler(BaseApiHandler):
    """Bounded framework-parsed upload endpoint for plugin ZIP archives."""

    routes = [
        {
            "path_pattern": r"/upload/plugin/file",
            "supported_methods": ["POST"],
            "call_method": "upload_and_install_plugin",
        }
    ]

    def initialize(self, **kwargs):
        super().initialize(**kwargs)
        self.config = config.Config()

    def _plugin_upload(self):
        content_length = self.request.headers.get("Content-Length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_PLUGIN_UPLOAD_SIZE:
                    raise BaseApiError("Plugin archive exceeds 64 MiB", status_code=413)
            except ValueError as exc:
                raise BaseApiError("Invalid plugin upload length", status_code=400) from exc

        for uploads in self.request.files.values():
            if uploads:
                upload = uploads[0]
                if len(upload.body) > MAX_PLUGIN_UPLOAD_SIZE:
                    raise BaseApiError("Plugin archive exceeds 64 MiB", status_code=413)
                return upload
        raise BaseApiError("A plugin ZIP file is required", status_code=400)

    async def upload_and_install_plugin(self):
        """Install one ordinary multipart plugin upload and remove its temp copy.
        ---
        description: Upload a plugin ZIP archive limited to 64 MiB compressed.
        requestBody:
          required: true
          content:
            multipart/form-data:
              schema:
                type: object
                properties:
                  file:
                    type: string
                    format: binary
        responses:
          200:
            description: Plugin installed.
          400:
            description: Missing or invalid plugin archive.
          413:
            description: Compressed plugin archive exceeds 64 MiB.
        """
        upload_path = None
        try:
            upload = self._plugin_upload()
            upload_root = Path(self.config.get_cache_path()).resolve() / "plugin_uploads"
            upload_path = await asyncio.to_thread(_persist_plugin_upload, upload_root, upload.body)

            from compresso.libs.plugins import PluginsHandler

            installed = await asyncio.to_thread(_install_plugin_serialized, PluginsHandler(), upload_path)
            if not installed:
                raise BaseApiError("Plugin package could not be installed", status_code=400)
            self.write_success()
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except Exception as exc:
            self.handle_unhandled_error(exc)
        finally:
            if upload_path is not None:
                upload_path.unlink(missing_ok=True)
