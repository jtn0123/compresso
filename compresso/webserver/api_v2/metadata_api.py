#!/usr/bin/env python3

"""
compresso.metadata_api.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     03 Feb 2026

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

from datetime import datetime

from peewee import DoesNotExist, fn

from compresso.libs.metadata import CompressoFileMetadata
from compresso.libs.unmodels import CompletedTasks, FileMetadata, FileMetadataPaths
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler, integer_value, string_value
from compresso.webserver.api_v2.schema.history_schemas import (
    MetadataSearchResultsSchema,
    RequestMetadataByFingerprintSchema,
    RequestMetadataByTaskSchema,
    RequestMetadataDeleteSchema,
    RequestMetadataSearchSchema,
    RequestMetadataUpdateSchema,
)
from compresso.webserver.api_v2.schema.schemas import BaseSuccessSchema


class ApiMetadataHandler(BaseApiHandler):
    params: object
    routes = [
        {
            "path_pattern": r"/metadata/search",
            "supported_methods": ["GET", "POST"],
            "call_method": "search_metadata",
        },
        {
            "path_pattern": r"/metadata/by-task",
            "supported_methods": ["POST"],
            "call_method": "get_metadata_by_task",
        },
        {
            "path_pattern": r"/metadata/by-fingerprint",
            "supported_methods": ["POST"],
            "call_method": "get_metadata_by_fingerprint",
        },
        {
            "path_pattern": r"/metadata/by-task/(?P<task_id>[0-9]+)",
            "supported_methods": ["GET"],
            "call_method": "get_metadata_by_task_id",
        },
        {
            "path_pattern": r"/metadata/update",
            "supported_methods": ["POST"],
            "call_method": "update_metadata",
        },
        {
            "path_pattern": r"/metadata",
            "supported_methods": ["DELETE"],
            "call_method": "delete_metadata",
        },
    ]

    def initialize(self, **kwargs: object) -> None:
        self.params = kwargs.get("params")

    async def search_metadata(self) -> None:
        """
        Metadata - search
        ---
        description: Search file metadata by path, with pagination.
        requestBody:
            required: false
            content:
                application/json:
                    schema:
                        RequestMetadataSearchSchema
        responses:
            200:
                description: Matching metadata records.
                content:
                    application/json:
                        schema:
                            MetadataSearchResultsSchema
        """
        try:
            if self.request.method == "GET":
                path_value: object = self.get_argument("path", None)
                offset_value: object = self.get_argument("offset", None)
                limit_value: object = self.get_argument("limit", None)
            else:
                json_request = self.read_json_request(RequestMetadataSearchSchema())
                path_value = json_request.get("path")
                offset_value = json_request.get("offset")
                limit_value = json_request.get("limit")

            try:
                offset = int(offset_value) if isinstance(offset_value, (int, str)) else 0
            except ValueError:
                offset = 0
            try:
                limit = int(limit_value) if isinstance(limit_value, (int, str)) else 50
            except ValueError:
                limit = 50
            path = string_value(path_value)

            if limit < 1:
                limit = 1
            # Cap the page size so a single request cannot trigger an unbounded query.
            if limit > 500:
                limit = 500
            if offset < 0:
                offset = 0

            results: list[dict[str, object]] = []
            total_count = 0

            if not path:
                base = FileMetadata.select(FileMetadata.id)
                total_count = base.count()
                page_ids = [row.id for row in base.order_by(FileMetadata.updated_at.desc()).limit(limit).offset(offset)]
            else:
                search_value = path.strip().lower()
                base = (
                    FileMetadata.select(FileMetadata.id)
                    .join(FileMetadataPaths)
                    .where(fn.LOWER(FileMetadataPaths.path).contains(search_value))
                    .distinct()
                )
                total_count = base.count()
                page_ids = [row.id for row in base.order_by(FileMetadata.updated_at.desc()).limit(limit).offset(offset)]

            if page_ids:
                path_map: dict[int, list[dict[str, object]]] = {}
                for path_row in FileMetadataPaths.select().where(FileMetadataPaths.file_metadata.in_(page_ids)):
                    path_map.setdefault(path_row.file_metadata.id, []).append(
                        {
                            "path": path_row.path,
                            "path_type": path_row.path_type,
                        }
                    )

                for metadata_row in (
                    FileMetadata.select().where(FileMetadata.id.in_(page_ids)).order_by(FileMetadata.updated_at.desc())
                ):
                    results.append(
                        {
                            "fingerprint": metadata_row.fingerprint,
                            "fingerprint_algo": metadata_row.fingerprint_algo,
                            "metadata_json": CompressoFileMetadata._load_json_dict(metadata_row.metadata_json),
                            "last_task_id": metadata_row.last_task_id,
                            "paths": path_map.get(metadata_row.id, []),
                        }
                    )
            response = self.build_response(
                MetadataSearchResultsSchema(),
                {
                    "results": results,
                    "total_count": total_count,
                },
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_metadata_by_task(self) -> None:
        """
        Metadata - by task
        ---
        description: Return metadata associated with a completed task.
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        RequestMetadataByTaskSchema
        responses:
            200:
                description: Metadata associated with the task.
                content:
                    application/json:
                        schema:
                            MetadataSearchResultsSchema
        """
        try:
            json_request = self.read_json_request(RequestMetadataByTaskSchema())
            task_id = integer_value(json_request.get("task_id"))
            await self._get_metadata_by_task_id(task_id)
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_metadata_by_task_id(self, task_id: str) -> None:
        """
        Metadata - by task ID
        ---
        description: Return metadata associated with the task ID in the path.
        responses:
            200:
                description: Metadata associated with the task.
                content:
                    application/json:
                        schema:
                            MetadataSearchResultsSchema
        """
        try:
            await self._get_metadata_by_task_id(int(task_id))
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def _get_metadata_by_task_id(self, task_id: int) -> None:
        try:
            completed_task = CompletedTasks.get_by_id(task_id)
        except DoesNotExist:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Completed task not found")
            self.write_error()
            return

        path = completed_task.abspath
        metadata_ids: set[int] = set()

        for metadata_row in FileMetadata.select(FileMetadata.id).where(FileMetadata.last_task_id == task_id):
            metadata_ids.add(metadata_row.id)

        for path_row in FileMetadataPaths.select(FileMetadataPaths.file_metadata).where(FileMetadataPaths.path == path):
            metadata_ids.add(path_row.file_metadata.id)

        results: list[dict[str, object]] = []
        if metadata_ids:
            path_map: dict[int, list[dict[str, object]]] = {}
            for path_row in FileMetadataPaths.select().where(FileMetadataPaths.file_metadata.in_(metadata_ids)):
                path_map.setdefault(path_row.file_metadata.id, []).append(
                    {
                        "path": path_row.path,
                        "path_type": path_row.path_type,
                    }
                )

            for metadata_row in FileMetadata.select().where(FileMetadata.id.in_(metadata_ids)):
                results.append(
                    {
                        "fingerprint": metadata_row.fingerprint,
                        "fingerprint_algo": metadata_row.fingerprint_algo,
                        "metadata_json": CompressoFileMetadata._load_json_dict(metadata_row.metadata_json),
                        "last_task_id": metadata_row.last_task_id,
                        "paths": path_map.get(metadata_row.id, []),
                    }
                )

        response = self.build_response(
            MetadataSearchResultsSchema(),
            {
                "results": results,
                "total_count": len(results),
            },
        )
        self.write_success(response)

    async def update_metadata(self) -> None:
        """
        Metadata - update
        ---
        description: Replace one plugin's metadata for a fingerprint.
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        RequestMetadataUpdateSchema
        responses:
            200:
                description: Metadata was updated.
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
        """
        try:
            json_request = self.read_json_request(RequestMetadataUpdateSchema())
            fingerprint = string_value(json_request.get("fingerprint"))
            plugin_id = string_value(json_request.get("plugin_id"))
            json_blob = json_request.get("json_blob")

            if not isinstance(json_blob, dict) or not all(isinstance(key, str) for key in json_blob):
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Metadata update requires a dict payload")
                self.write_error()
                return

            try:
                CompressoFileMetadata._enforce_plugin_size_limit(json_blob)
            except ValueError as error:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(error))
                self.write_error()
                return

            row = FileMetadata.get_or_none(FileMetadata.fingerprint == fingerprint)
            if not row:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Fingerprint not found")
                self.write_error()
                return

            data = CompressoFileMetadata._load_json_dict(row.metadata_json)
            data[plugin_id] = {str(key): value for key, value in json_blob.items()}
            row.metadata_json = CompressoFileMetadata._dump_json_dict(data)
            row.updated_at = datetime.now()
            row.save()

            response = self.build_response(BaseSuccessSchema(), {"success": True})
            self.write_success(response)
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def delete_metadata(self) -> None:
        """
        Metadata - delete
        ---
        description: Delete all metadata or one plugin's metadata for a fingerprint.
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        RequestMetadataDeleteSchema
        responses:
            200:
                description: Metadata was deleted.
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
        """
        try:
            json_request = self.read_json_request(RequestMetadataDeleteSchema())
            fingerprint_value = json_request.get("fingerprint")
            plugin_id_value = json_request.get("plugin_id")
            fingerprint = fingerprint_value if isinstance(fingerprint_value, str) else None
            plugin_id = plugin_id_value if isinstance(plugin_id_value, str) else None

            result = CompressoFileMetadata.delete_for_plugin(fingerprint, plugin_id=plugin_id)
            if not result:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Fingerprint not found")
                self.write_error()
                return

            response = self.build_response(BaseSuccessSchema(), {"success": True})
            self.write_success(response)
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)

    async def get_metadata_by_fingerprint(self) -> None:
        """
        Metadata - by fingerprint
        ---
        description: Return metadata associated with a file fingerprint.
        requestBody:
            required: true
            content:
                application/json:
                    schema:
                        RequestMetadataByFingerprintSchema
        responses:
            200:
                description: Metadata associated with the fingerprint.
                content:
                    application/json:
                        schema:
                            MetadataSearchResultsSchema
        """
        try:
            json_request = self.read_json_request(RequestMetadataByFingerprintSchema())
            fingerprint = string_value(json_request.get("fingerprint"))
            if not fingerprint:
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="Fingerprint not provided")
                self.write_error()
                return

            row = FileMetadata.get_or_none(FileMetadata.fingerprint == fingerprint)
            results: list[dict[str, object]] = []
            if row:
                path_map: list[dict[str, object]] = []
                for path_row in FileMetadataPaths.select().where(FileMetadataPaths.file_metadata == row.id):
                    path_map.append(
                        {
                            "path": path_row.path,
                            "path_type": path_row.path_type,
                        }
                    )

                results.append(
                    {
                        "fingerprint": row.fingerprint,
                        "fingerprint_algo": row.fingerprint_algo,
                        "metadata_json": CompressoFileMetadata._load_json_dict(row.metadata_json),
                        "last_task_id": row.last_task_id,
                        "paths": path_map,
                    }
                )

            response = self.build_response(
                MetadataSearchResultsSchema(),
                {
                    "results": results,
                    "total_count": len(results),
                },
            )
            self.write_success(response)
        except BaseApiError as bae:
            self.handle_base_api_error(bae)
            return
        except Exception as e:
            self.handle_unhandled_error(e)
