#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    unmanic.fileinfo_api.py

    API handler for file info endpoints.

"""

import os

import tornado.log

from unmanic.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from unmanic.webserver.api_v2.schema.fileinfo_schemas import (
    RequestFileInfoProbeSchema,
    RequestFileInfoTaskSchema,
    FileInfoResponseSchema,
)
from unmanic.webserver.helpers import fileinfo


class ApiFileinfoHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern":      r"/fileinfo/probe",
            "supported_methods": ["POST"],
            "call_method":       "probe_file",
        },
        {
            "path_pattern":      r"/fileinfo/task",
            "supported_methods": ["POST"],
            "call_method":       "probe_task_file",
        },
    ]

    async def probe_file(self):
        """
        FileInfo - probe file
        ---
        description: Probe an arbitrary file path and return stream/format info.
        requestBody:
            description: File path to probe.
            required: True
            content:
                application/json:
                    schema:
                        RequestFileInfoProbeSchema
        responses:
            200:
                description: 'Returns file info.'
                content:
                    application/json:
                        schema:
                            FileInfoResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestFileInfoProbeSchema())
            file_path = json_request.get('file_path', '')

            if not os.path.exists(file_path):
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="File not found: {}".format(file_path))
                self.write_error()
                return

            info = fileinfo.probe_and_format(file_path)
            if info is None:
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="ffprobe failed for file")
                self.write_error()
                return

            response = self.build_response(
                FileInfoResponseSchema(),
                {
                    "success":           True,
                    "video_streams":     info.get('video_streams', []),
                    "audio_streams":     info.get('audio_streams', []),
                    "subtitle_streams":  info.get('subtitle_streams', []),
                    "format":            info.get('format', {}),
                }
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def probe_task_file(self):
        """
        FileInfo - probe task file
        ---
        description: Probe the file from a completed task by task ID.
        requestBody:
            description: Task ID.
            required: True
            content:
                application/json:
                    schema:
                        RequestFileInfoTaskSchema
        responses:
            200:
                description: 'Returns file info.'
                content:
                    application/json:
                        schema:
                            FileInfoResponseSchema
        """
        try:
            json_request = self.read_json_request(RequestFileInfoTaskSchema())
            task_id = json_request.get('task_id')

            from unmanic.libs.unmodels import CompletedTasks
            try:
                task = CompletedTasks.get_by_id(task_id)
            except CompletedTasks.DoesNotExist:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Task not found: {}".format(task_id))
                self.write_error()
                return

            file_path = task.abspath
            if not file_path or not os.path.exists(file_path):
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="File not found: {}".format(file_path))
                self.write_error()
                return

            info = fileinfo.probe_and_format(file_path)
            if info is None:
                self.set_status(self.STATUS_ERROR_INTERNAL, reason="ffprobe failed for file")
                self.write_error()
                return

            response = self.build_response(
                FileInfoResponseSchema(),
                {
                    "success":           True,
                    "video_streams":     info.get('video_streams', []),
                    "audio_streams":     info.get('audio_streams', []),
                    "subtitle_streams":  info.get('subtitle_streams', []),
                    "format":            info.get('format', {}),
                }
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
