#!/usr/bin/env python3
"""
compresso.installation_link.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     28 Oct 2021, (7:24 PM)

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

from __future__ import annotations

import hashlib
import json
import os.path
import re
import threading
import time
from collections.abc import Callable, Mapping
from typing import Literal, TypedDict, cast

import requests
from requests import Response
from requests_toolbelt import MultipartEncoder

from compresso import config
from compresso.libs import common, narrowing, session, task
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.resumable_transfer import file_sha256
from compresso.libs.singleton import SingletonType
from compresso.libs.worker_capabilities import WorkerCapabilities

_REMOTE_LIBRARIES_API = "/compresso/api/v2/settings/libraries"


class LinkStatus(TypedDict):
    status: str
    last_seen: float | None
    consecutive_failures: int
    next_retry: float


class LinkStatusPatch(TypedDict, total=False):
    status: str
    last_seen: float | None
    consecutive_failures: int
    next_retry: float


def _config_string(config_data: Mapping[str, object], key: str) -> str | None:
    return narrowing.strict_str_or_none(config_data.get(key))


class Links(metaclass=SingletonType):
    NETWORK_TRANSFER_LOCK_TTL_SECONDS = 30 * 60
    _network_transfer_lock: dict[str, dict[str, float]] = {}
    _transfer_lock = threading.RLock()

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.settings = config.Config()
        self.session = session.Session()
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)
        # {uuid: {'status': 'connected', 'last_seen': time.time(),
        #         'consecutive_failures': 0, 'next_retry': 0}}
        self._link_status: dict[str, LinkStatus] = {}

    def _log(self, message: object, message2: object = "", level: str = "info") -> None:
        message = common.format_message(message, message2)
        log_method = cast("Callable[[object], None]", getattr(self.logger, level))
        log_method(message)

    def get_link_status(self, uuid: str) -> LinkStatus:
        """Get status of a remote installation link."""
        status = self._link_status.get(uuid)
        if status is None:
            return {
                "status": "unknown",
                "last_seen": None,
                "consecutive_failures": 0,
                "next_retry": 0,
            }
        return cast("LinkStatus", dict(status))

    def set_link_status(self, uuid: str, status: LinkStatusPatch) -> None:
        """Update status of a remote installation link."""
        if uuid not in self._link_status:
            self._link_status[uuid] = {
                "status": "unknown",
                "last_seen": None,
                "consecutive_failures": 0,
                "next_retry": 0,
            }
        self._link_status[uuid].update(status)

    def get_all_link_statuses(self) -> dict[str, LinkStatus]:
        """Get all link statuses for WebSocket push."""
        return {k: cast("LinkStatus", dict(v)) for k, v in self._link_status.items()}

    def _record_link_success(self, uuid: str) -> None:
        """Record successful communication with a remote link."""
        current = self._link_status.get(uuid)
        was_reconnecting = current is not None and current["status"] == "reconnecting"
        self._link_status[uuid] = {
            "status": "connected",
            "last_seen": time.time(),
            "consecutive_failures": 0,
            "next_retry": 0,
        }
        if was_reconnecting:
            self._notify_link_status_change(uuid, "connected")

    def _record_link_failure(self, uuid: str) -> None:
        """Record failed communication with a remote link, apply exponential backoff."""
        current = self._link_status.get(uuid)
        failures = (current["consecutive_failures"] if current is not None else 0) + 1
        backoff = min(300, 10 * (2 ** min(failures, 5)))  # cap at 5 min

        new_status = "reconnecting" if failures <= 10 else "disconnected"
        was_connected = current is None or current["status"] in ("connected", "unknown")

        self._link_status[uuid] = {
            "status": new_status,
            "last_seen": current["last_seen"] if current is not None else None,
            "consecutive_failures": failures,
            "next_retry": time.time() + backoff,
        }

        if was_connected:
            self._notify_link_status_change(uuid, new_status)

    def _should_skip_link(self, uuid: str) -> bool:
        """Check if a link is in backoff period and should be skipped."""
        status = self._link_status.get(uuid)
        next_retry = status["next_retry"] if status is not None else 0
        return next_retry > 0 and time.time() < next_retry

    def _notify_link_status_change(self, uuid: str, new_status: str) -> None:
        """Push link status change to frontend."""
        try:
            from compresso.libs.frontend_push_messages import FrontendPushMessages

            msg_type = "warning" if new_status != "connected" else "success"
            label = f"Remote link {'reconnected' if new_status == 'connected' else 'disconnected'}"
            FrontendPushMessages().update(
                {
                    "id": f"link_status_{uuid}",
                    "type": msg_type,
                    "code": "linkStatusChanged",
                    "message": label,
                    "timeout": 10 if new_status == "connected" else 0,
                }
            )
        except Exception:  # noqa: S110 — best-effort UI notification; FrontendPushMessages may not be available
            pass

    def __format_address(self, address: str | None) -> str:
        if address is None:
            address = ""
        # Strip all whitespace
        address = address.strip()
        # Add http if it does not exist
        if not address.lower().startswith("http"):
            address = f"http://{address}"
        # Strip any trailing slashes
        address = address.rstrip("/")
        return address

    @staticmethod
    def _request_handler(remote_config: Mapping[str, object]) -> RequestHandler:
        return RequestHandler(
            auth=_config_string(remote_config, "auth") or "",
            username=_config_string(remote_config, "username"),
            password=_config_string(remote_config, "password"),
            api_token=_config_string(remote_config, "api_token"),
        )

    def __merge_config_dicts(self, config_dict: dict[str, object], compare_dict: Mapping[str, object]) -> None:
        for key in config_dict:
            if config_dict.get(key) != compare_dict.get(key) and compare_dict.get(key) is not None:
                # Apply the new value
                config_dict[key] = compare_dict.get(key)
                # Also flag the dict as updated
                config_dict["last_updated"] = time.time()

    def __generate_default_config(self, config_dict: Mapping[str, object]) -> dict[str, object]:
        return {
            "address": config_dict.get("address", "???"),
            "auth": config_dict.get("auth", "None"),
            "username": config_dict.get("username", ""),
            "password": config_dict.get("password", ""),
            "api_token": config_dict.get("api_token", ""),
            "enable_receiving_tasks": config_dict.get("enable_receiving_tasks", False),
            "enable_sending_tasks": config_dict.get("enable_sending_tasks", False),
            "enable_task_preloading": config_dict.get("enable_task_preloading", True),
            "preloading_count": config_dict.get("preloading_count", 2),
            "enable_checksum_validation": config_dict.get("enable_checksum_validation", False),
            "enable_config_missing_libraries": config_dict.get("enable_config_missing_libraries", False),
            "enable_distributed_worker_count": config_dict.get("enable_distributed_worker_count", False),
            "name": config_dict.get("name", "???"),
            "version": config_dict.get("version", "???"),
            "uuid": config_dict.get("uuid", "???"),
            "available": config_dict.get("available", False),
            "task_count": config_dict.get("runnable_task_count", config_dict.get("task_count", 0)),
            "runnable_task_count": config_dict.get("runnable_task_count", config_dict.get("task_count", 0)),
            "capabilities": config_dict.get("capabilities", {}),
            "last_updated": config_dict.get("last_updated", time.time()),
        }

    def acquire_network_transfer_lock(
        self, url: str, transfer_limit: int = 1, lock_type: str = "send"
    ) -> str | Literal[False]:
        """
        Limit transfers to each installation to 1 at a time

        :param url:
        :param transfer_limit:
        :param lock_type:
        :return:
        """
        time_now = time.time()
        lock = self._transfer_lock
        # Limit maximum transfer limit to 5
        if transfer_limit > 5:
            transfer_limit = 5
        # Acquire a lock if one is available
        with lock:
            for tx_lock in range(transfer_limit):
                lock_key = f"[{lock_type}-{tx_lock}]-{url}"
                if self._network_transfer_lock.get(lock_key, {}).get("expires", 0) < time_now:
                    # Bound leaked locks, but do not let one slow NAS chunk outlive
                    # an actively held transfer slot.
                    self._network_transfer_lock[lock_key] = {
                        "expires": (time_now + self.NETWORK_TRANSFER_LOCK_TTL_SECONDS),
                    }
                    # Return success
                    return lock_key
            # Failed to acquire network transfer lock
            return False

    def refresh_network_transfer_lock(self, lock_key: str | Literal[False] | None) -> bool:
        """Renew an actively progressing transfer lease without changing its slot."""
        if not lock_key:
            return False
        with self._transfer_lock:
            if not self._network_transfer_lock.get(lock_key):
                return False
            self._network_transfer_lock[lock_key]["expires"] = time.time() + self.NETWORK_TRANSFER_LOCK_TTL_SECONDS
            return True

    def release_network_transfer_lock(self, lock_key: str | Literal[False] | None) -> bool:
        """
        Expire the transfer lock for the given lock_key

        :param lock_key:
        :return:
        """
        if not lock_key:
            return False
        lock = self._transfer_lock
        with lock:
            # Expire the lock for this address
            self._network_transfer_lock[lock_key] = {}
            return True

    def remote_api_get(
        self, remote_config: Mapping[str, object], endpoint: str, timeout: int | float = 2
    ) -> dict[str, object]:
        """
        GET to remote installation API

        :param remote_config:
        :param endpoint:
        :param timeout:
        :return:
        """
        request_handler = self._request_handler(remote_config)
        address = self.__format_address(_config_string(remote_config, "address"))
        url = f"{address}{endpoint}"
        res = request_handler.get(url, timeout=timeout)
        if res.status_code == 200:
            return narrowing.string_keyed_dict(res.json())
        elif res.status_code in [400, 404, 405, 500]:
            json_data = narrowing.string_keyed_dict(res.json())
            self._log(
                "Error while executing GET on remote installation API - {}. Message: '{}'".format(
                    endpoint, json_data.get("error")
                ),
                message2=json_data.get("traceback", []),
                level="error",
            )
        return {}

    def remote_api_post(
        self,
        remote_config: Mapping[str, object],
        endpoint: str,
        data: Mapping[str, object],
        timeout: int | float = 2,
    ) -> dict[str, object]:
        """
        POST to remote installation API

        :param remote_config:
        :param endpoint:
        :param data:
        :param timeout:
        :return:
        """
        request_handler = self._request_handler(remote_config)
        address = self.__format_address(_config_string(remote_config, "address"))
        url = f"{address}{endpoint}"
        res = request_handler.post(url, json=data, timeout=timeout)
        if res.status_code == 200:
            return narrowing.string_keyed_dict(res.json())
        elif res.status_code in [400, 404, 405, 500]:
            json_data = narrowing.string_keyed_dict(res.json())
            self._log(
                "Error while executing POST on remote installation API - {}. Message: '{}'".format(
                    endpoint, json_data.get("error")
                ),
                message2=json_data.get("traceback", []),
                level="error",
            )
            return json_data
        return {}

    def remote_api_post_file(self, remote_config: Mapping[str, object], endpoint: str, path: str) -> dict[str, object]:
        """
        Send a file to the remote installation
        No timeout is set so the request will continue until closed

        :param remote_config:
        :param endpoint:
        :param path:
        :return:
        """
        request_handler = self._request_handler(remote_config)
        address = self.__format_address(_config_string(remote_config, "address"))
        url = f"{address}{endpoint}"
        # NOTE: If you remove a content type from the upload (text/plain) the file upload fails
        # NOTE2: The 'ith open(path, "rb") as f' method reads the file into memory before uploading.
        #   This is slow and not ideal for devices with small amounts of ram.
        #   ```
        #       with open(path, "rb") as f:
        #           files = {"fileName": (os.path.basename(path), f, 'text/plain')}
        #           res = requests.post(url, files=files)
        #   ```
        with open(path, "rb") as fh:
            m = MultipartEncoder(fields={"fileName": (os.path.basename(path), fh, "text/plain")})
            res = request_handler.post(url, data=m, headers={"Content-Type": m.content_type})
        if res.status_code == 200:
            return narrowing.string_keyed_dict(res.json())
        elif res.status_code in [400, 404, 405, 500]:
            json_data = narrowing.string_keyed_dict(res.json())
            self._log(
                "Error while uploading file to remote installation API - {}. Message: '{}'".format(
                    endpoint, json_data.get("error")
                ),
                message2=json_data.get("traceback", []),
                level="error",
            )
        return {}

    def remote_api_post_bytes(
        self, remote_config: Mapping[str, object], endpoint: str, data: bytes, headers: Mapping[str, str]
    ) -> dict[str, object]:
        request_handler = self._request_handler(remote_config)
        address = self.__format_address(_config_string(remote_config, "address"))
        response = request_handler.post(f"{address}{endpoint}", data=data, headers=headers, timeout=60)
        if response.status_code == 200:
            return narrowing.string_keyed_dict(response.json())
        return {}

    def remote_api_delete(
        self,
        remote_config: Mapping[str, object],
        endpoint: str,
        data: Mapping[str, object],
        timeout: int | float = 2,
    ) -> dict[str, object]:
        """
        DELETE to remote installation API

        :param remote_config:
        :param endpoint:
        :param data:
        :param timeout:
        :return:
        """
        request_handler = self._request_handler(remote_config)
        address = self.__format_address(_config_string(remote_config, "address"))
        url = f"{address}{endpoint}"
        res = request_handler.delete(url, json=data, timeout=timeout)
        if res.status_code == 200:
            return narrowing.string_keyed_dict(res.json())
        elif res.status_code in [400, 404, 405, 500]:
            json_data = narrowing.string_keyed_dict(res.json())
            self._log(
                "Error while executing DELETE on remote installation API - {}. Message: '{}'".format(
                    endpoint, json_data.get("error")
                ),
                message2=json_data.get("traceback", []),
                level="error",
            )
        return {}

    def remote_api_get_download(self, remote_config: Mapping[str, object], endpoint: str, path: str) -> bool:
        """
        Download a file from a remote installation

        :param remote_config:
        :param endpoint:
        :param path:
        :return:
        """
        request_handler = self._request_handler(remote_config)
        address = self.__format_address(_config_string(remote_config, "address"))
        url = f"{address}{endpoint}"
        with request_handler.get(url, stream=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=None):
                    if chunk:
                        f.write(chunk)
        return True

    def _remote_validation_data(self, response: Response, resource: str) -> tuple[bool, dict[str, object]]:
        """Return JSON from a successful remote validation request and log known failures."""
        if response.status_code == 200:
            return True, narrowing.string_keyed_dict(response.json())

        if response.status_code in {400, 404, 405, 500}:
            json_data = narrowing.string_keyed_dict(response.json())
            self._log(
                f"Error while fetching remote installation {resource}. Message: '{json_data.get('error')}'",
                message2=json_data.get("traceback", []),
                level="error",
            )
        return False, {}

    def validate_remote_installation(self, address: str, **kwargs: object) -> dict[str, object]:
        """
        Validate a remote Compresso installation by requesting
        its system info and version

        :param address:
        :param username:
        :param password:
        :return:
        """
        address = self.__format_address(address)

        auth = kwargs.get("auth")
        username = kwargs.get("username")
        password = kwargs.get("password")
        api_token = kwargs.get("api_token")
        request_handler = RequestHandler(
            auth=auth if isinstance(auth, str) else "",
            username=username if isinstance(username, str) else None,
            password=password if isinstance(password, str) else None,
            api_token=api_token if isinstance(api_token, str) else None,
        )

        # Fetch config
        url = f"{address}/compresso/api/v2/settings/configuration"
        res = request_handler.get(url, timeout=2)
        valid, system_configuration_data = self._remote_validation_data(res, "config")
        if not valid:
            return {}

        # Fetch settings
        url = f"{address}/compresso/api/v2/settings/read"
        res = request_handler.get(url, timeout=2)
        valid, settings_data = self._remote_validation_data(res, "settings")
        if not valid:
            return {}

        # Fetch version
        url = f"{address}/compresso/api/v2/version/read"
        res = request_handler.get(url, timeout=2)
        valid, version_data = self._remote_validation_data(res, "version")
        if not valid:
            return {}

        # Fetch session state
        url = f"{address}/compresso/api/v2/session/state"
        res = request_handler.get(url, timeout=2)
        valid, session_data = self._remote_validation_data(res, "session state")
        if not valid:
            return {}

        # Fetch task count data
        data = {"start": 0, "length": 1}
        url = f"{address}/compresso/api/v2/pending/tasks"
        res = request_handler.post(url, json=data, timeout=2)
        valid, tasks_data = self._remote_validation_data(res, "pending task list")
        if not valid:
            return {}

        # Capacity is advisory: an older peer can omit it and still remain linked.
        capabilities: dict[str, object] = {}
        url = f"{address}/compresso/api/v2/system/capabilities"
        res = request_handler.get(url, timeout=2)
        if res.status_code == 200:
            capabilities = narrowing.string_keyed_dict(res.json())

        runnable_task_count = narrowing.coerce_int(
            tasks_data.get(
                "runnableRecords",
                tasks_data.get("recordsFiltered", tasks_data.get("recordsTotal", 0)),
            )
        )

        return {
            "system_configuration": system_configuration_data.get("configuration"),
            "settings": settings_data.get("settings"),
            "version": version_data.get("version"),
            "session": {
                "level": session_data.get("level"),
                "picture_uri": session_data.get("picture_uri"),
                "name": session_data.get("name"),
                "email": session_data.get("email"),
                "uuid": session_data.get("uuid"),
            },
            "task_count": runnable_task_count,
            "runnable_task_count": runnable_task_count,
            "capabilities": capabilities,
        }

    def update_all_remote_installation_links(
        self,
    ) -> list[dict[str, object]]:
        """
        Updates the link status and configuration of linked remote installations

        :return:
        """
        save_settings = False
        installation_id_list: list[object] = []
        remote_installations: list[dict[str, object]] = []
        distributed_worker_count_target = self.settings.get_distributed_worker_count_target()
        for local_config in self.settings.get_remote_installations():
            if self._link_should_be_removed(local_config, installation_id_list):
                save_settings = True
                continue

            # Check if this link is in backoff period
            # Derive a stable per-link key even when uuid is not yet synced
            raw_uuid_value = local_config.get("uuid", "???")
            raw_uuid = raw_uuid_value if isinstance(raw_uuid_value, str) else "???"
            link_uuid = f"_addr_{local_config.get('address', 'unknown')}" if raw_uuid == "???" else raw_uuid
            if self._should_skip_link(link_uuid):
                # Still in backoff -- keep existing config but mark unavailable
                updated_config = self.__generate_default_config(local_config)
                updated_config["available"] = False
                remote_installations.append(updated_config)
                installation_id_list.append(updated_config.get("uuid", "???"))
                continue

            installation_data = self._validate_link(local_config, link_uuid)

            # Generate updated configured values
            updated_config = self.__generate_default_config(local_config)
            updated_config["available"] = False
            if installation_data:
                link_changed, distributed_worker_count_target = self._update_validated_link(
                    local_config,
                    updated_config,
                    installation_data,
                    link_uuid,
                    distributed_worker_count_target,
                )
                save_settings = save_settings or link_changed

            # Only save to file if the settings have been updated
            remote_installations.append(updated_config)

            # Add UUID to list for next loop
            installation_id_list.append(updated_config.get("uuid", "???"))

        # Update installation data. Only save the config to disk if it was modified
        settings_dict = {
            "remote_installations": remote_installations,
            "distributed_worker_count_target": distributed_worker_count_target,
        }
        self.settings.set_bulk_config_items(settings_dict, save_settings=save_settings)

        return remote_installations

    @staticmethod
    def _link_should_be_removed(local_config: Mapping[str, object], installation_ids: list[object]) -> bool:
        duplicate = local_config.get("uuid") in installation_ids and local_config.get("uuid", "???") != "???"
        missing_address = not local_config.get("address")
        unknown = local_config.get("address") == "???" and local_config.get("uuid") == "???"
        return duplicate or missing_address or unknown

    def _validate_link(self, local_config: Mapping[str, object], link_uuid: str) -> dict[str, object] | None:
        try:
            return self.validate_remote_installation(
                _config_string(local_config, "address") or "",
                auth=local_config.get("auth"),
                username=local_config.get("username"),
                password=local_config.get("password"),
                api_token=local_config.get("api_token"),
            )
        except Exception as error:
            self._record_link_failure(link_uuid)
            self.logger.warning("Failed to validate remote installation at %s: %s", local_config.get("address"), error)
            return None

    def _update_validated_link(
        self,
        local_config: Mapping[str, object],
        updated_config: dict[str, object],
        installation_data: Mapping[str, object],
        link_uuid: str,
        distributed_worker_count_target: int,
    ) -> tuple[bool, int]:
        self._merge_validated_link_status(updated_config, installation_data, link_uuid)
        remote_config = self._fetch_remote_link_config(local_config, updated_config)
        remote_link_config = narrowing.string_keyed_dict(remote_config.get("link_config"))
        link_changed, distributed_worker_count_target = self._sync_newer_remote_link_config(
            local_config,
            updated_config,
            remote_config,
            remote_link_config,
            distributed_worker_count_target,
        )
        self._push_link_config_if_needed(updated_config, remote_link_config)
        self._sync_missing_remote_libraries(local_config)
        return link_changed, distributed_worker_count_target

    def _merge_validated_link_status(
        self,
        updated_config: dict[str, object],
        installation_data: Mapping[str, object],
        link_uuid: str,
    ) -> None:
        installation_session = narrowing.string_keyed_dict(installation_data.get("session"))
        real_uuid_value = installation_session.get("uuid")
        real_uuid = real_uuid_value if isinstance(real_uuid_value, str) else None
        if real_uuid is not None and link_uuid != real_uuid:
            if link_uuid in self._link_status:
                self._link_status[real_uuid] = self._link_status.pop(link_uuid)
            link_uuid = real_uuid
        self._record_link_success(link_uuid)
        updated_config["available"] = True
        runnable_count = installation_data.get("runnable_task_count", installation_data.get("task_count", 0))
        updated_config["task_count"] = runnable_count
        updated_config["runnable_task_count"] = runnable_count
        updated_config["capabilities"] = installation_data.get("capabilities", {})
        installation_settings = narrowing.string_keyed_dict(installation_data.get("settings"))
        self.__merge_config_dicts(
            updated_config,
            {
                "name": installation_settings.get("installation_name"),
                "version": installation_data.get("version"),
                "uuid": installation_session.get("uuid"),
            },
        )

    def _fetch_remote_link_config(
        self, local_config: Mapping[str, object], updated_config: dict[str, object]
    ) -> dict[str, object]:
        try:
            return self.fetch_remote_installation_link_config_for_this(local_config)
        except requests.exceptions.Timeout:
            self._log("Request to fetch remote installation config timed out", level="warning")
        except requests.exceptions.RequestException as error:
            self._log("Request to fetch remote installation config failed", message2=str(error), level="warning")
        except Exception as error:
            self._log("Failed to fetch remote installation config", message2=str(error), level="error")
        updated_config["available"] = False
        return {}

    @staticmethod
    def _remote_link_is_newer(local_config: Mapping[str, object], remote_link_config: Mapping[str, object]) -> bool:
        local_updated = local_config.get("last_updated", 1)
        remote_updated = remote_link_config.get("last_updated", 1)
        return (
            isinstance(local_updated, (int, float))
            and isinstance(remote_updated, (int, float))
            and local_updated < remote_updated
        )

    def _sync_newer_remote_link_config(
        self,
        local_config: Mapping[str, object],
        updated_config: dict[str, object],
        remote_config: Mapping[str, object],
        remote_link_config: Mapping[str, object],
        distributed_worker_count_target: int,
    ) -> tuple[bool, int]:
        if not self._remote_link_is_newer(local_config, remote_link_config):
            return False, distributed_worker_count_target
        link_changed = self._copy_remote_link_flags(updated_config, remote_link_config)
        target = narrowing.coerce_int(remote_config.get("distributed_worker_count_target"))
        updated_config["last_updated"] = remote_link_config.get("last_updated")
        return link_changed, target

    @staticmethod
    def _copy_remote_link_flags(updated_config: dict[str, object], remote_link_config: Mapping[str, object]) -> bool:
        changed = False
        flag_pairs = (
            ("enable_receiving_tasks", "enable_sending_tasks"),
            ("enable_sending_tasks", "enable_receiving_tasks"),
        )
        for local_key, remote_key in flag_pairs:
            remote_value = remote_link_config.get(remote_key)
            if updated_config[local_key] != remote_value:
                updated_config[local_key] = remote_value
                changed = True
        return changed

    def _push_link_config_if_needed(self, updated_config: dict[str, object], remote_link_config: Mapping[str, object]) -> None:
        if remote_link_config.get("available"):
            return
        try:
            self.push_remote_installation_link_config(updated_config)
        except requests.exceptions.Timeout:
            self._log("Request to push link config to remote installation timed out", level="warning")
            updated_config["available"] = False
        except requests.exceptions.RequestException as error:
            self._log("Request to push link config to remote installation failed", message2=str(error), level="warning")
            updated_config["available"] = False
        except Exception as error:
            self._log("Failed to push link config to remote installation", message2=str(error), level="error")
            updated_config["available"] = False

    def _sync_missing_remote_libraries(self, local_config: Mapping[str, object]) -> None:
        if not local_config.get("enable_sending_tasks") or not local_config.get("enable_config_missing_libraries"):
            return
        results = self.remote_api_get(local_config, _REMOTE_LIBRARIES_API)
        existing_names = {library.get("name") for library in narrowing.string_keyed_dicts(results.get("libraries"))}
        for library_config in Library.get_all_libraries():
            if library_config["enable_remote_only"] or library_config["name"] in existing_names:
                continue
            self._import_remote_library(local_config, library_config)

    def _import_remote_library(self, local_config: Mapping[str, object], library_config: Mapping[str, object]) -> None:
        import_data = Library.export(narrowing.coerce_int(library_config.get("id")))
        import_data["library_id"] = 0
        imported_config = narrowing.string_keyed_dict(import_data.get("library_config"))
        imported_config.update({"enable_remote_only": True, "enable_scanner": False, "enable_inotify": False})
        import_data["library_config"] = imported_config
        library_name = library_config.get("name")
        self._log(f"Importing remote library config '{library_name}'", message2=import_data, level="debug")
        result = self.import_remote_library_config(local_config, import_data)
        if result is None:
            return
        if result.get("success"):
            self._log(f"Successfully imported library '{library_name}'", level="debug")
            return
        self._log(f"Failed to import library config '{library_name}'", message2=result.get("error"), level="error")

    def read_remote_installation_link_config(self, uuid: str) -> dict[str, object]:
        """
        Returns the configuration of the remote installation

        :param uuid:
        :return:
        """
        for remote_installation in self.settings.get_remote_installations():
            if remote_installation.get("uuid") == uuid:
                # If not yet configured, set default values before returning
                return self.__generate_default_config(remote_installation)

        # Ensure we have settings data from the remote installation
        raise Exception("Unable to read installation link configuration.")

    def update_single_remote_installation_link_config(
        self, configuration: dict[str, object], distributed_worker_count_target: int = 0
    ) -> None:
        """
        Returns the configuration of the remote installation after updating it

        :param configuration:
        :param distributed_worker_count_target:
        :return:
        """
        uuid = configuration.get("uuid")
        if not uuid:
            raise Exception("Updating a single installation link configuration requires a UUID.")

        current_distributed_worker_count_target = self.settings.get_distributed_worker_count_target()
        force_update_flag = False
        if int(current_distributed_worker_count_target) != int(distributed_worker_count_target):
            force_update_flag = True

        config_exists = False
        remote_installations = []
        for local_config in self.settings.get_remote_installations():
            updated_config = self.__generate_default_config(local_config)

            # If this is the uuid in the config provided, then update our config with the provided values
            if local_config.get("uuid") == uuid:
                config_exists = True
                self.__merge_config_dicts(updated_config, configuration)

            # If this link is configured for distributed worker count, and that count was change,
            #   force the last update flag to be updated so this change is disseminated
            if force_update_flag and configuration.get("enable_distributed_worker_count"):
                updated_config["last_updated"] = time.time()

            remote_installations.append(updated_config)

        # If the config does not yet exist, the add it now
        if not config_exists:
            remote_installations.append(self.__generate_default_config(configuration))

        # Update installation data and save the config to disk
        settings_dict = {
            "remote_installations": remote_installations,
            "distributed_worker_count_target": distributed_worker_count_target,
        }
        self.settings.set_bulk_config_items(settings_dict, save_settings=True)

    def delete_remote_installation_link_config(self, uuid: str) -> bool:
        """
        Removes a link configuration for a remote installation given its uuid
        If no uuid match is found, returns False

        :param uuid:
        :return:
        """
        removed = False
        updated_list = []
        for remote_installation in self.settings.get_remote_installations():
            if remote_installation.get("uuid") == uuid:
                # Mark the task as having successfully remoted the installation
                removed = True
                continue
            # Only add remote installations that do not match
            updated_list.append(remote_installation)

        # Update installation data and save the config to disk
        settings_dict = {
            "remote_installations": updated_list,
        }
        self.settings.set_bulk_config_items(settings_dict, save_settings=True)
        return removed

    def fetch_remote_installation_link_config_for_this(self, remote_config: Mapping[str, object]) -> dict[str, object]:
        """
        Fetches and returns the corresponding link configuration from a remote installation

        :param remote_config:
        :return:
        """
        request_handler = self._request_handler(remote_config)
        address = self.__format_address(_config_string(remote_config, "address"))
        url = f"{address}/compresso/api/v2/settings/link/read"
        data = {"uuid": self.session.uuid}
        res = request_handler.post(url, json=data, timeout=2)
        if res.status_code == 200:
            return narrowing.string_keyed_dict(res.json())
        elif res.status_code in [400, 404, 405, 500]:
            json_data = narrowing.string_keyed_dict(res.json())
            self._log(
                f"Error while fetching remote installation link config. Message: '{json_data.get('error')}'",
                message2=json_data.get("traceback", []),
                level="error",
            )
        return {}

    def push_remote_installation_link_config(self, configuration: Mapping[str, object]) -> bool:
        """
        Pushes the given link config to the remote installation returns
        the corresponding link configuration from a remote installation

        :param configuration:
        :return:
        """
        request_handler = self._request_handler(configuration)
        address = self.__format_address(_config_string(configuration, "address"))
        url = f"{address}/compresso/api/v2/settings/link/write"

        # First generate an updated config
        updated_config = self.__generate_default_config(configuration)

        # Update the bits for the remote instance
        updated_config["uuid"] = self.session.uuid
        updated_config["name"] = self.settings.get_installation_name()
        updated_config["version"] = self.settings.read_version()

        # Configure settings
        updated_config["enable_receiving_tasks"] = configuration.get("enable_sending_tasks")
        updated_config["enable_sending_tasks"] = configuration.get("enable_receiving_tasks")

        # Current runnable demand and measured capacity
        task_handler = task.Task()
        runnable_task_count = int(task_handler.get_runnable_task_count())
        updated_config["task_count"] = runnable_task_count
        updated_config["runnable_task_count"] = runnable_task_count
        updated_config["capabilities"] = WorkerCapabilities().snapshot(self.settings)

        # Fetch local config for distributed_worker_count_target
        distributed_worker_count_target = self.settings.get_distributed_worker_count_target()

        # Remove some of the other fields. These will need to be adjusted on the remote instance manually
        del updated_config["address"]
        del updated_config["available"]
        # This token authenticates requests *to* the peer. It is local-only
        # credential state and must never be synchronized back to that peer.
        updated_config.pop("api_token", None)

        data = {"link_config": updated_config, "distributed_worker_count_target": distributed_worker_count_target}
        res = request_handler.post(url, json=data, timeout=2)
        if res.status_code == 200:
            return True
        elif res.status_code in [400, 404, 405, 500]:
            json_data = narrowing.string_keyed_dict(res.json())
            self._log(
                f"Error while pushing remote installation link config. Message: '{json_data.get('error')}'",
                message2=json_data.get("traceback", []),
                level="error",
            )
        return False

    def check_remote_installation_for_available_workers(self) -> dict[str, dict[str, object]]:
        """
        Return a list of installations with workers available for a remote task.
        This list is filtered by:
            - Only installations that are available
            - Only installations that are configured for sending tasks to
            - Only installations that have not pending tasks
            - Only installations that have at least one idle worker that is not paused

        :return:
        """
        installations_with_info: dict[str, dict[str, object]] = {}
        for lc in self.settings.get_remote_installations():
            local_config = self.__generate_default_config(lc)
            local_uuid = _config_string(local_config, "uuid") or ""
            if (
                not local_config.get("available")
                or not local_config.get("enable_sending_tasks")
                or len(local_uuid) < 20
                or self._should_skip_link(local_uuid)
            ):
                continue
            try:
                if info := self._remote_worker_availability(local_config):
                    installations_with_info[local_uuid] = info

            except Exception as e:
                self._log(
                    f"Failed to contact remote installation '{local_config.get('address')}'",
                    message2=str(e),
                    level="warning",
                )
                continue

        return installations_with_info

    def _remote_worker_availability(self, config: dict[str, object]) -> dict[str, object] | None:
        worker_results = self.remote_api_get(config, "/compresso/api/v2/workers/status")
        workers = narrowing.string_keyed_dicts(worker_results.get("workers_status"))
        preloading = bool(config.get("enable_task_preloading"))
        max_pending = narrowing.coerce_int(config.get("preloading_count")) if preloading else 0
        pending = self.remote_api_post(config, "/compresso/api/v2/pending/tasks", {"start": 0, "length": 1})
        if pending.get("error"):
            return None
        pending_count = narrowing.coerce_int(pending.get("recordsFiltered"))
        if preloading and pending_count >= max_pending:
            self._log(f"Remote installation has exceeded max pending count ({pending_count})", level="debug")
            return None
        libraries = self.remote_api_get(config, _REMOTE_LIBRARIES_API)
        library_names = [
            name
            for library in narrowing.string_keyed_dicts(libraries.get("libraries"))
            if isinstance((name := library.get("name")), str)
        ]
        try:
            capabilities = self.remote_api_get(config, "/compresso/api/v2/system/capabilities")
            capabilities = {} if capabilities.get("error") else capabilities
        except Exception:
            capabilities = {}
        idle_slots = sum(bool(worker.get("idle")) and not bool(worker.get("paused")) for worker in workers)
        active_workers = sum(not bool(worker.get("paused")) for worker in workers)
        preload_slots = max(0, max_pending - pending_count) if preloading and active_workers else 0
        available_slots = idle_slots + preload_slots
        if not available_slots:
            return None
        return {
            **{
                key: config.get(key)
                for key in (
                    "address",
                    "auth",
                    "username",
                    "password",
                    "api_token",
                    "enable_task_preloading",
                    "preloading_count",
                )
            },
            "library_names": library_names,
            "available_slots": available_slots,
            "queue_depth": pending_count,
            "capabilities": capabilities,
            "scheduling_score": WorkerCapabilities.scheduling_score(capabilities) or 0,
            "available_workers": bool(idle_slots),
        }

    def within_enabled_link_limits(self) -> bool:
        """
        All features unlocked — no link count limits.

        :return:
        """
        return True

    def new_pending_task_create_on_remote_installation(
        self,
        remote_config: Mapping[str, object],
        abspath: str,
        library_id: int,
        job_id: str | None = None,
        lease_token: str | None = None,
        origin_installation_uuid: str | None = None,
    ) -> dict[str, object] | None:
        """
        Create a new pending task on a remote installation.
        The remote installation will return the ID of a generated task.

        :param remote_config:
        :param abspath:
        :param library_id:
        :return:
        """
        try:
            request_handler = self._request_handler(remote_config)
            address = self.__format_address(_config_string(remote_config, "address"))
            url = f"{address}/compresso/api/v2/pending/create"
            data = {
                "path": abspath,
                "library_id": library_id,
                "type": "remote",
            }
            if job_id:
                data["job_id"] = job_id
            if lease_token:
                data["lease_token"] = lease_token
            if origin_installation_uuid:
                data["origin_installation_uuid"] = origin_installation_uuid
            res = request_handler.post(url, json=data, timeout=2)
            if res.status_code in [200, 400]:
                return narrowing.string_keyed_dict(res.json())
            elif res.status_code in [404, 405, 500]:
                json_data = narrowing.string_keyed_dict(res.json())
                self._log(
                    f"Error while creating new remote pending task. Message: '{json_data.get('error')}'",
                    message2=json_data.get("traceback", []),
                    level="error",
                )
            return {}
        except requests.exceptions.Timeout:
            self._log(f"Request to create remote pending task timed out '{abspath}'", level="warning")
            return None
        except requests.exceptions.RequestException as e:
            self._log(f"Request to create remote pending task failed '{abspath}'", message2=str(e), level="warning")
            return None
        except Exception as e:
            self._log(f"Failed to create remote pending task '{abspath}'", message2=str(e), level="error")
        return {}

    def send_file_to_remote_installation(
        self,
        remote_config: Mapping[str, object],
        path: str,
        job_id: str | None = None,
        lease_token: str | None = None,
        origin_installation_uuid: str | None = None,
        progress_callback: Callable[[], bool | None] | None = None,
    ) -> dict[str, object]:
        """
        Send a file to a remote installation.
        The remote installation will return the ID of a generated task.

        :param remote_config:
        :param path:
        :return:
        """
        try:
            if not job_id:
                self._log("Refusing distributed upload without a stable job ID", level="error")
                return {}
            if progress_callback is not None:
                return self._send_file_resumable(
                    remote_config,
                    path,
                    job_id,
                    lease_token=lease_token,
                    origin_installation_uuid=origin_installation_uuid,
                    progress_callback=progress_callback,
                )
            return self._send_file_resumable(
                remote_config,
                path,
                job_id,
                lease_token=lease_token,
                origin_installation_uuid=origin_installation_uuid,
            )
        except requests.exceptions.RequestException as e:
            self._log("Request to upload to remote installation failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to upload to remote installation", message2=str(e), level="error")
        return {}

    def _send_file_resumable(
        self,
        remote_config: Mapping[str, object],
        path: str,
        job_id: str,
        lease_token: str | None = None,
        origin_installation_uuid: str | None = None,
        chunk_size: int = 8 * 1024 * 1024,
        progress_callback: Callable[[], bool | None] | None = None,
    ) -> dict[str, object]:
        total_size = os.path.getsize(path)
        expected_checksum = file_sha256(path)
        session = self.remote_api_post(
            remote_config,
            "/compresso/api/v2/transfer/session",
            {
                "job_id": job_id,
                "filename": os.path.basename(path),
                "total_size": total_size,
                "expected_checksum": expected_checksum,
                "lease_token": lease_token,
                "origin_installation_uuid": origin_installation_uuid,
            },
            timeout=60,
        )
        if not session:
            return {}
        transfer_id_value = session.get("transfer_id")
        if not isinstance(transfer_id_value, str):
            return {}
        transfer_id = transfer_id_value
        offset = narrowing.coerce_int(session.get("offset"))
        with open(path, "rb") as source:
            source.seek(offset)
            while offset < total_size:
                chunk = source.read(chunk_size)
                if not chunk:
                    return {}
                chunk_checksum = f"sha256:{hashlib.sha256(chunk).hexdigest()}"
                status = self.remote_api_post_bytes(
                    remote_config,
                    f"/compresso/api/v2/transfer/chunk/{transfer_id}",
                    chunk,
                    {
                        "Content-Type": "application/octet-stream",
                        "X-Transfer-Offset": str(offset),
                        "X-Chunk-Checksum": chunk_checksum,
                    },
                )
                next_offset = narrowing.coerce_int(status.get("offset"), offset)
                if next_offset != offset + len(chunk):
                    return {}
                offset = next_offset
                if progress_callback and progress_callback() is False:
                    return {}
        return self.remote_api_post(
            remote_config,
            f"/compresso/api/v2/transfer/finalize/{transfer_id}",
            {},
            timeout=60,
        )

    def fetch_remote_task_completed_file_resumable(
        self,
        remote_config: Mapping[str, object],
        remote_task_id: int,
        path: str,
        chunk_size: int = 8 * 1024 * 1024,
        progress_callback: Callable[[], bool | None] | None = None,
    ) -> bool:
        manifest = self.remote_api_get(
            remote_config,
            f"/compresso/api/v2/transfer/source/{remote_task_id}/manifest",
            timeout=60,
        )
        if not manifest:
            return False
        safe_path = os.path.realpath(path)
        cache_root = os.path.realpath(self.settings.get_cache_path())
        try:
            destination_is_safe = safe_path != cache_root and os.path.commonpath((cache_root, safe_path)) == cache_root
        except ValueError:
            destination_is_safe = False
        if not destination_is_safe:
            raise ValueError("Remote transfer destination must be inside the Compresso cache")
        if not isinstance(manifest, dict):
            return False
        total_size = manifest.get("total_size")
        checksum = manifest.get("checksum")
        if (
            not isinstance(total_size, int)
            or isinstance(total_size, bool)
            or total_size < 0
            or not isinstance(checksum, str)
            or re.fullmatch(r"sha256:[a-f0-9]{64}", checksum) is None
        ):
            return False
        partial_path = f"{safe_path}.part"
        if os.path.commonpath((cache_root, os.path.realpath(partial_path))) != cache_root:
            raise ValueError("Remote transfer partial path must be inside the Compresso cache")
        offset = os.path.getsize(partial_path) if os.path.exists(partial_path) else 0
        if offset > total_size:
            os.remove(partial_path)  # NOSONAR - partial_path is constrained to cache_root above
            offset = 0

        request_handler = self._request_handler(remote_config)
        address = self.__format_address(_config_string(remote_config, "address"))
        with open(partial_path, "ab") as output:  # NOSONAR - partial_path is constrained to cache_root above
            while offset < total_size:
                response = request_handler.get(
                    f"{address}/compresso/api/v2/transfer/source/{remote_task_id}/chunk",
                    params={"offset": offset, "limit": chunk_size},
                    timeout=60,
                )
                if response.status_code != 200 or not response.content:
                    return False
                expected_chunk_checksum = response.headers.get("X-Chunk-Checksum")
                actual_chunk_checksum = f"sha256:{hashlib.sha256(response.content).hexdigest()}"
                if expected_chunk_checksum != actual_chunk_checksum:
                    return False
                if len(response.content) > min(chunk_size, total_size - offset):
                    return False
                output.write(response.content)
                output.flush()
                os.fsync(output.fileno())
                offset += len(response.content)
                if progress_callback and progress_callback() is False:
                    return False

        if os.path.getsize(partial_path) != total_size or file_sha256(partial_path) != checksum:
            os.remove(partial_path)  # NOSONAR - partial_path is constrained to cache_root above
            return False
        os.replace(partial_path, safe_path)  # NOSONAR - both paths are constrained to cache_root above
        return True

    def remove_task_from_remote_installation(
        self, remote_config: Mapping[str, object], remote_task_id: int
    ) -> dict[str, object] | None:
        """
        Remove a task from the pending queue

        :param remote_config:
        :param remote_task_id:
        :return:
        """
        try:
            data = {"id_list": [remote_task_id]}
            return self.remote_api_delete(remote_config, "/compresso/api/v2/pending/tasks", data, timeout=15)
        except requests.exceptions.Timeout:
            self._log("Request to remove remote task timed out", level="warning")
            return None
        except requests.exceptions.RequestException as e:
            self._log("Request to remove remote task failed", message2=str(e), level="warning")
            return None
        except Exception as e:
            self._log("Failed to remove remote pending task", message2=str(e), level="error")
        return {}

    def get_the_remote_library_config_by_name(
        self, remote_config: Mapping[str, object], library_name: str
    ) -> dict[str, object] | None:
        """
        Fetch a remote library's configuration by its name

        :param remote_config:
        :param library_name:
        :return:
        """
        try:
            # Fetch remote installation libraries
            results = self.remote_api_get(remote_config, _REMOTE_LIBRARIES_API, timeout=4)
            for library in narrowing.string_keyed_dicts(results.get("libraries")):
                if library.get("name") == library_name:
                    return library
        except requests.exceptions.Timeout:
            self._log("Request to set remote task library timed out", level="warning")
            return None
        except requests.exceptions.RequestException as e:
            self._log("Request to set remote task library failed", message2=str(e), level="warning")
            return None
        except Exception as e:
            self._log("Failed to set remote task library", message2=str(e), level="error")
        return {}

    def set_the_remote_task_library(
        self, remote_config: Mapping[str, object], remote_task_id: int, library_name: str
    ) -> dict[str, object] | None:
        """
        Set the library for the remote task
        Defaults to the remote installation's default library

        :param remote_config:
        :param remote_task_id:
        :param library_name:
        :return:
        """
        try:
            data = {
                "id_list": [remote_task_id],
                "library_name": library_name,
            }
            results = self.remote_api_post(remote_config, "/compresso/api/v2/pending/library/update", data, timeout=7)
            if results.get("error"):
                results = {}
            return results
        except requests.exceptions.Timeout:
            self._log("Request to set remote task library timed out", level="warning")
            return None
        except requests.exceptions.RequestException as e:
            self._log("Request to set remote task library failed", message2=str(e), level="warning")
            return None
        except Exception as e:
            self._log("Failed to set remote task library", message2=str(e), level="error")
        return {}

    def get_remote_pending_task_state(
        self, remote_config: Mapping[str, object], remote_task_id: int
    ) -> dict[str, object] | None:
        """
        Get the remote pending task status

        :param remote_config:
        :param remote_task_id:
        :return:
        """
        try:
            data = {"id_list": [remote_task_id]}
            results = self.remote_api_post(remote_config, "/compresso/api/v2/pending/status/get", data, timeout=7)
            return results
        except requests.exceptions.Timeout:
            self._log("Request to get status of remote task timed out", level="warning")
        except requests.exceptions.RequestException as e:
            self._log("Request to get status of remote task failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to get status of remote pending task", message2=str(e), level="error")
        return None

    def start_the_remote_task_by_id(
        self, remote_config: Mapping[str, object], remote_task_id: int
    ) -> dict[str, object] | None:
        """
        Start the remote pending task

        :param remote_config:
        :param remote_task_id:
        :return:
        """
        try:
            data = {"id_list": [remote_task_id]}
            results = self.remote_api_post(remote_config, "/compresso/api/v2/pending/status/set/ready", data, timeout=7)
            if results.get("error"):
                results = {}
            return results
        except requests.exceptions.Timeout:
            self._log("Request to start remote task timed out", level="warning")
            return None
        except requests.exceptions.RequestException as e:
            self._log("Request to start remote task failed", message2=str(e), level="warning")
            return None
        except Exception as e:
            self._log("Failed to start remote pending task", message2=str(e), level="error")
        return {}

    def get_all_worker_status(self, remote_config: Mapping[str, object]) -> list[dict[str, object]]:
        """
        Start the remote pending task

        :param remote_config:
        :return:
        """
        try:
            results = self.remote_api_get(remote_config, "/compresso/api/v2/workers/status")
            return narrowing.string_keyed_dicts(results.get("workers_status"))
        except requests.exceptions.Timeout:
            self._log("Request to get worker status timed out", level="warning")
        except requests.exceptions.RequestException as e:
            self._log("Request to get worker status failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to get worker status", message2=str(e), level="error")
        return []

    def get_single_worker_status(self, remote_config: Mapping[str, object], worker_id: str) -> dict[str, object]:
        """
        Start the remote pending task

        :param remote_config:
        :param worker_id:
        :return:
        """
        workers_status = self.get_all_worker_status(remote_config)
        for worker in workers_status:
            if worker.get("id") == worker_id:
                return worker
        return {}

    def terminate_remote_worker(self, remote_config: Mapping[str, object], worker_id: str) -> dict[str, object]:
        """
        Start the remote pending task

        :param remote_config:
        :param worker_id:
        :return:
        """
        try:
            data = {"worker_id": [worker_id]}
            return self.remote_api_delete(remote_config, "/compresso/api/v2/workers/worker/terminate", data)
        except requests.exceptions.Timeout:
            self._log("Request to terminate remote worker timed out", level="warning")
        except requests.exceptions.RequestException as e:
            self._log("Request to terminate remote worker failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to terminate remote worker", message2=str(e), level="error")
        return {}

    def fetch_remote_task_data(self, remote_config: Mapping[str, object], remote_task_id: int, path: str) -> dict[str, object]:
        """
        Fetch the completed remote task data

        :param remote_config:
        :param remote_task_id:
        :param path:
        :return:
        """
        task_data = {}
        # Resolve path to prevent directory traversal
        safe_path = os.path.realpath(path)
        try:
            # Request API generate a DL link
            link_info = self.remote_api_get(remote_config, f"/compresso/api/v2/pending/download/data/id/{remote_task_id}")
            if link_info.get("link_id"):
                # Download the data file
                dl_url = f"/compresso/downloads/{link_info.get('link_id')}"
                res = self.remote_api_get_download(remote_config, dl_url, safe_path)
                if res and os.path.exists(safe_path):
                    with open(safe_path) as f:  # noqa: ASYNC230 — called from synchronous thread context
                        task_data = narrowing.string_keyed_dict(json.load(f))
        except requests.exceptions.Timeout:
            self._log("Request to fetch remote task data timed out", level="warning")
        except requests.exceptions.RequestException as e:
            self._log("Request to fetch remote task data failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to fetch remote task data", message2=str(e), level="error")
        return task_data

    def fetch_remote_task_completed_file(self, remote_config: Mapping[str, object], remote_task_id: int, path: str) -> bool:
        """
        Fetch the completed remote task file

        :param remote_config:
        :param remote_task_id:
        :param path:
        :return:
        """
        # Resolve path to prevent directory traversal
        safe_path = os.path.realpath(path)
        try:
            # Request API generate a DL link
            link_info = self.remote_api_get(remote_config, f"/compresso/api/v2/pending/download/file/id/{remote_task_id}")
            if link_info.get("link_id"):
                # Download the file
                dl_url = f"/compresso/downloads/{link_info.get('link_id')}"
                res = self.remote_api_get_download(remote_config, dl_url, safe_path)
                if res and os.path.exists(safe_path):
                    return True
        except requests.exceptions.Timeout:
            self._log("Request to fetch remote task completed file timed out", level="warning")
        except requests.exceptions.RequestException as e:
            self._log("Request to fetch remote task completed file failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to fetch remote task completed file", message2=str(e), level="error")
        return False

    def import_remote_library_config(
        self, remote_config: Mapping[str, object], import_data: Mapping[str, object]
    ) -> dict[str, object] | None:
        """
        Import a library config on a remote installation

        :param remote_config:
        :param import_data:
        :return:
        """
        try:
            results = self.remote_api_post(remote_config, "/compresso/api/v2/settings/library/import", import_data, timeout=60)
            if results.get("error"):
                results = {}
            return results
        except requests.exceptions.Timeout:
            self._log("Request to import remote library timed out", level="warning")
            return None
        except requests.exceptions.RequestException as e:
            self._log("Request to import remote library failed", message2=str(e), level="warning")
            return None
        except Exception as e:
            self._log("Failed to import remote library", message2=str(e), level="error")
        return {}


# Backward-compatible imports
from compresso.libs.request_handler import RequestHandler  # noqa: E402, F401


def __getattr__(name: str) -> object:
    if name == "RemoteTaskManager":
        from compresso.libs.remote_task_manager import RemoteTaskManager

        return RemoteTaskManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
