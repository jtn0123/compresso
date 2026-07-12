#!/usr/bin/env python3

"""Resumable, checksummed remote-media transfer endpoints."""

import asyncio
import hashlib
import os

from compresso import config
from compresso.libs.resumable_transfer import ResumableTransferStore, file_sha256
from compresso.libs.unmodels.tasks import Tasks
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.transfer_schemas import RequestTransferSessionSchema
from compresso.webserver.helpers import pending_tasks

MAX_CHUNK_SIZE = 8 * 1024 * 1024


def _decode_path_parameter(value):
    """Tornado's PathMatches may supply captured route values as bytes."""
    return value.decode("ascii") if isinstance(value, bytes) else value


def _read_file_chunk(path, offset, limit):
    with open(path, "rb") as source:
        source.seek(offset)
        return source.read(limit)


class ApiTransferHandler(BaseApiHandler):
    routes = [
        {
            "path_pattern": r"/transfer/session",
            "supported_methods": ["POST"],
            "call_method": "begin_transfer",
        },
        {
            "path_pattern": r"/transfer/session/(?P<transfer_id>[a-f0-9]{32})",
            "supported_methods": ["GET"],
            "call_method": "get_transfer_status",
        },
        {
            "path_pattern": r"/transfer/chunk/(?P<transfer_id>[a-f0-9]{32})",
            "supported_methods": ["POST"],
            "call_method": "append_transfer_chunk",
        },
        {
            "path_pattern": r"/transfer/finalize/(?P<transfer_id>[a-f0-9]{32})",
            "supported_methods": ["POST"],
            "call_method": "finalize_transfer",
        },
        {
            "path_pattern": r"/transfer/source/(?P<task_id>[0-9]+)/manifest",
            "supported_methods": ["GET"],
            "call_method": "get_source_manifest",
        },
        {
            "path_pattern": r"/transfer/source/(?P<task_id>[0-9]+)/chunk",
            "supported_methods": ["GET"],
            "call_method": "get_source_chunk",
        },
    ]

    def _store(self):
        root = os.path.join(config.Config().get_cache_path(), "remote_transfers")
        return ResumableTransferStore(root)

    async def begin_transfer(self):
        try:
            request = self.read_json_request(RequestTransferSessionSchema())
            metadata = {
                "lease_token": request.get("lease_token"),
                "origin_installation_uuid": request.get("origin_installation_uuid"),
            }
            store = self._store()
            status = await asyncio.to_thread(
                store.begin,
                request["job_id"],
                request["filename"],
                request["total_size"],
                request["expected_checksum"],
                metadata=metadata,
            )
            self.write_success(status)
        except BaseApiError:
            return
        except (OSError, TypeError, ValueError) as error:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(error))
            self.write_error()

    async def get_transfer_status(self, transfer_id=None):
        try:
            transfer_id = _decode_path_parameter(transfer_id)
            store = self._store()
            self.write_success(await asyncio.to_thread(store.status, transfer_id))
        except (KeyError, OSError, ValueError) as error:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(error))
            self.write_error()

    async def append_transfer_chunk(self, transfer_id=None):
        try:
            transfer_id = _decode_path_parameter(transfer_id)
            if len(self.request.body) > MAX_CHUNK_SIZE:
                raise ValueError("Transfer chunk exceeds maximum size")
            offset = int(self.request.headers.get("X-Transfer-Offset", "-1"))
            chunk_checksum = self.request.headers.get("X-Chunk-Checksum", "")
            store = self._store()
            status = await asyncio.to_thread(store.append, transfer_id, offset, self.request.body, chunk_checksum)
            self.write_success(status)
        except (KeyError, OSError, TypeError, ValueError) as error:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(error))
            self.write_error()

    async def finalize_transfer(self, transfer_id=None):
        try:
            transfer_id = _decode_path_parameter(transfer_id)
            response = await asyncio.to_thread(self._finalize_transfer_sync, transfer_id)
            self.write_success(response)
        except (KeyError, OSError, TypeError, ValueError) as error:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(error))
            self.write_error()

    def _finalize_transfer_sync(self, transfer_id):
        store = self._store()
        completed_path = store.finalize(transfer_id)
        manifest = store.get_manifest(transfer_id)
        task_info = pending_tasks.add_remote_tasks(str(completed_path), job_id=manifest["job_id"])
        metadata = manifest.get("metadata", {})
        if not pending_tasks.bind_remote_task_identity(
            task_info["id"],
            lease_token=metadata.get("lease_token"),
            origin_installation_uuid=metadata.get("origin_installation_uuid"),
        ):
            raise ValueError("Remote task identity conflicts with the existing job")
        response = store.status(transfer_id)
        response.update({"id": task_info["id"], "status": task_info["status"], "checksum": manifest["expected_checksum"]})
        return response

    @staticmethod
    def _completed_source(task_id):
        task = Tasks.get_or_none(Tasks.id == int(task_id))
        if task is None or task.status != "complete" or not os.path.isfile(task.abspath):
            raise ValueError("Completed task output is unavailable")
        return task

    async def get_source_manifest(self, task_id=None):
        try:
            task_id = _decode_path_parameter(task_id)
            self.write_success(await asyncio.to_thread(self._source_manifest_sync, task_id))
        except (OSError, TypeError, ValueError) as error:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(error))
            self.write_error()

    def _source_manifest_sync(self, task_id):
        task = self._completed_source(task_id)
        return {
            "task_id": task.id,
            "job_id": task.job_id,
            "filename": os.path.basename(task.abspath),
            "total_size": os.path.getsize(task.abspath),
            "checksum": file_sha256(task.abspath),
        }

    async def get_source_chunk(self, task_id=None):
        try:
            task_id = _decode_path_parameter(task_id)
            task = await asyncio.to_thread(self._completed_source, task_id)
            offset = max(0, int(self.get_query_argument("offset", "0")))
            limit = min(MAX_CHUNK_SIZE, max(1, int(self.get_query_argument("limit", str(MAX_CHUNK_SIZE)))))
            chunk = await asyncio.to_thread(_read_file_chunk, task.abspath, offset, limit)
            self.set_header("Content-Type", "application/octet-stream")
            self.set_header("X-Transfer-Offset", str(offset))
            self.set_header("X-Chunk-Checksum", f"sha256:{hashlib.sha256(chunk).hexdigest()}")
            self.set_status(self.STATUS_SUCCESS)
            self.finish(chunk)
        except (OSError, TypeError, ValueError) as error:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(error))
            self.write_error()
