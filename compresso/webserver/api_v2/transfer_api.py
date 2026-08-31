#!/usr/bin/env python3

"""Resumable, checksummed remote-media transfer endpoints."""

import asyncio
import hashlib
import os
from collections.abc import Mapping

from tornado.log import app_log

from compresso import config
from compresso.libs.resumable_transfer import ResumableTransferStore, TransferStorageError, file_sha256
from compresso.libs.safety_state import record_safety_event
from compresso.libs.unmodels.tasks import Tasks
from compresso.webserver.api_v2.base_api_handler import (
    BaseApiError,
    BaseApiHandler,
    integer_value,
    string_value,
)
from compresso.webserver.api_v2.schema.transfer_schemas import RequestTransferSessionSchema
from compresso.webserver.helpers import pending_tasks

MAX_CHUNK_SIZE = 8 * 1024 * 1024


def _decode_path_parameter(value: str | bytes | None) -> str:
    """Tornado's PathMatches may supply captured route values as bytes."""
    if isinstance(value, bytes):
        return value.decode("ascii")
    if isinstance(value, str):
        return value
    raise ValueError("Missing route parameter")


def _read_file_chunk(path: str, offset: int, limit: int) -> bytes:
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
            "path_pattern": r"/transfer/session/(?P<transfer_id>[a-f0-9]{32})",
            "supported_methods": ["DELETE"],
            "call_method": "abandon_transfer",
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

    def _store(self) -> ResumableTransferStore:
        settings = config.Config()
        root = os.path.join(settings.get_cache_path(), "remote_transfers")
        minimum_free_bytes = 0
        if settings.get_disk_space_guard_enabled():
            minimum_free_bytes = int(settings.get_minimum_free_space_gb() * 1024**3)
        maximum_file_size_bytes = int(settings.get_maximum_transfer_file_size_gb() * 1024**3)
        return ResumableTransferStore(
            root,
            maximum_file_size_bytes=maximum_file_size_bytes,
            minimum_free_bytes=minimum_free_bytes,
        )

    def _handle_transfer_error(self, error: Exception) -> None:
        """Map transfer failures to structured client-facing API errors."""
        if isinstance(error, TransferStorageError):
            settings = config.Config()
            try:
                record_safety_event(
                    settings,
                    None,
                    "disk-reserve",
                    "Remote transfer paused because the cache reserve would be breached",
                    phase="transfer",
                    path=settings.get_cache_path(),
                    free_bytes=error.free_bytes,
                    required_bytes=error.required_bytes,
                    reserved_bytes=error.reserved_bytes,
                )
            except Exception:
                # Preserve the storage response even if the secondary safety recorder
                # cannot be reached, while recording the secondary failure.
                app_log.exception("Failed to persist the transfer disk-reserve safety latch")
            status_code = 507
            public_message = "Transfer storage reserve exhausted"
        else:
            status_code = 404 if isinstance(error, KeyError) else 400
            public_message = "Transfer request could not be completed"
        self.handle_base_api_error(
            BaseApiError(
                public_message,
                status_code=status_code,
                private_detail=f"{type(error).__name__}: {error}",
            )
        )

    async def begin_transfer(self) -> None:
        """Create or resume a bounded checksummed media transfer.
        ---
        description: Create or resume a media transfer using a stable job ID.
        requestBody:
          required: true
          content:
            application/json:
              schema:
                RequestTransferSessionSchema
        responses:
          200:
            description: Transfer session created or resumed.
          400:
            description: Invalid transfer metadata or configured file-size limit exceeded.
          507:
            description: Cache capacity or disk reserve is exhausted.
        """
        try:
            request = self.read_json_request(RequestTransferSessionSchema())
            metadata = {
                "lease_token": request.get("lease_token"),
                "origin_installation_uuid": request.get("origin_installation_uuid"),
            }
            store = self._store()
            status = await asyncio.to_thread(
                store.begin,
                string_value(request["job_id"]),
                string_value(request["filename"]),
                integer_value(request["total_size"]),
                string_value(request["expected_checksum"]),
                metadata=metadata,
            )
            self.write_success(status)
        except BaseApiError as exc:
            self.handle_base_api_error(exc)
        except (OSError, TypeError, ValueError) as error:
            self._handle_transfer_error(error)

    async def get_transfer_status(self, transfer_id: str | bytes | None = None) -> None:
        """Read the durable offset for a resumable transfer.
        ---
        description: Return the current offset and completion state for a transfer.
        responses:
          200:
            description: Current transfer state.
          404:
            description: Unknown transfer ID.
        """
        try:
            transfer_id = _decode_path_parameter(transfer_id)
            store = self._store()
            self.write_success(await asyncio.to_thread(store.status, transfer_id))
        except (KeyError, OSError, ValueError) as error:
            self._handle_transfer_error(error)

    async def abandon_transfer(self, transfer_id: str | bytes | None = None) -> None:
        """Delete an intentionally abandoned incomplete transfer session.
        ---
        description: Delete an incomplete transfer manifest, partial file, and owned completed directory.
        responses:
          200:
            description: Transfer session abandoned.
          400:
            description: Completed transfers cannot be abandoned.
          404:
            description: Unknown transfer ID.
        """
        try:
            transfer_id = _decode_path_parameter(transfer_id)
            store = self._store()
            self.write_success(await asyncio.to_thread(store.abandon, transfer_id))
        except (KeyError, OSError, ValueError) as error:
            self._handle_transfer_error(error)

    async def append_transfer_chunk(self, transfer_id: str | bytes | None = None) -> None:
        """Append one checksummed chunk at the declared offset.
        ---
        description: Append at most 8 MiB after validating offset, chunk checksum, and disk reserve.
        requestBody:
          required: true
          content:
            application/octet-stream:
              schema:
                type: string
                format: binary
        responses:
          200:
            description: Chunk accepted and durable offset advanced.
          400:
            description: Invalid offset, size, or checksum.
          507:
            description: Cache disk reserve would be breached.
        """
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
            self._handle_transfer_error(error)

    async def finalize_transfer(self, transfer_id: str | bytes | None = None) -> None:
        """Verify and publish a complete transferred file.
        ---
        description: Verify the complete SHA-256 checksum and create the worker task exactly once.
        responses:
          200:
            description: Transfer verified and finalized.
          400:
            description: Transfer is incomplete or failed checksum validation.
          404:
            description: Unknown transfer ID.
        """
        try:
            transfer_id = _decode_path_parameter(transfer_id)
            response = await asyncio.to_thread(self._finalize_transfer_sync, transfer_id)
            self.write_success(response)
        except (KeyError, OSError, TypeError, ValueError) as error:
            self._handle_transfer_error(error)

    def _finalize_transfer_sync(self, transfer_id: str) -> dict[str, object]:
        store = self._store()
        completed_path = store.finalize(transfer_id)
        manifest = store.get_manifest(transfer_id)
        task_info = pending_tasks.add_remote_tasks(str(completed_path), job_id=string_value(manifest["job_id"]) or None)
        if not isinstance(task_info, dict):
            raise ValueError("Transferred task could not be created")
        task_id = integer_value(task_info.get("id"))
        task_status = string_value(task_info.get("status"))
        metadata_value = manifest.get("metadata", {})
        metadata = metadata_value if isinstance(metadata_value, Mapping) else {}
        if not pending_tasks.bind_remote_task_identity(
            task_id,
            lease_token=string_value(metadata.get("lease_token")) or None,
            origin_installation_uuid=string_value(metadata.get("origin_installation_uuid")) or None,
        ):
            raise ValueError("Remote task identity conflicts with the existing job")
        response: dict[str, object] = dict(store.status(transfer_id))
        response.update({"id": task_id, "status": task_status, "checksum": manifest["expected_checksum"]})
        return response

    @staticmethod
    def _completed_source(task_id: str) -> Tasks:
        task = Tasks.get_or_none(Tasks.id == int(task_id))
        if task is None or task.status != "complete" or not os.path.isfile(task.abspath):
            raise ValueError("Completed task output is unavailable")
        return task

    async def get_source_manifest(self, task_id: str | bytes | None = None) -> None:
        """Return metadata for resumable result download.
        ---
        description: Return size and SHA-256 metadata for a completed worker task.
        responses:
          200:
            description: Completed task transfer manifest.
          400:
            description: Completed output is unavailable.
        """
        try:
            task_id = _decode_path_parameter(task_id)
            self.write_success(await asyncio.to_thread(self._source_manifest_sync, task_id))
        except (OSError, TypeError, ValueError) as error:
            self._handle_transfer_error(error)

    def _source_manifest_sync(self, task_id: str) -> dict[str, object]:
        task = self._completed_source(task_id)
        return {
            "task_id": task.id,
            "job_id": task.job_id,
            "filename": os.path.basename(task.abspath),
            "total_size": os.path.getsize(task.abspath),
            "checksum": file_sha256(task.abspath),
        }

    async def get_source_chunk(self, task_id: str | bytes | None = None) -> None:
        """Download one checksummed result chunk.
        ---
        description: Return at most 8 MiB from a completed worker task with offset and checksum headers.
        responses:
          200:
            description: Binary result chunk.
          400:
            description: Completed output or requested range is unavailable.
        """
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
            self._handle_transfer_error(error)
