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

import json
import os.path
import threading
import time

import requests
from requests_toolbelt import MultipartEncoder

from compresso import config
from compresso.libs import common, session, task
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.singleton import SingletonType


class Links(metaclass=SingletonType):
    _network_transfer_lock: dict = {}
    _transfer_lock = threading.RLock()

    def __init__(self, *args, **kwargs):
        self.settings = config.Config()
        self.session = session.Session()
        self.logger = CompressoLogging.get_logger(name=__class__.__name__)
        # {uuid: {'status': 'connected', 'last_seen': time.time(),
        #         'consecutive_failures': 0, 'next_retry': 0}}
        self._link_status = {}

    def _log(self, message, message2="", level="info"):
        message = common.format_message(message, message2)
        getattr(self.logger, level)(message)

    def get_link_status(self, uuid):
        """Get status of a remote installation link."""
        status = self._link_status.get(uuid)
        if status is None:
            return {
                "status": "unknown",
                "last_seen": None,
                "consecutive_failures": 0,
                "next_retry": 0,
            }
        return dict(status)

    def set_link_status(self, uuid, status):
        """Update status of a remote installation link."""
        if uuid not in self._link_status:
            self._link_status[uuid] = {
                "status": "unknown",
                "last_seen": None,
                "consecutive_failures": 0,
                "next_retry": 0,
            }
        self._link_status[uuid].update(status)

    def get_all_link_statuses(self):
        """Get all link statuses for WebSocket push."""
        return {k: dict(v) for k, v in self._link_status.items()}

    def _record_link_success(self, uuid):
        """Record successful communication with a remote link."""
        was_reconnecting = self._link_status.get(uuid, {}).get("status") == "reconnecting"
        self._link_status[uuid] = {
            "status": "connected",
            "last_seen": time.time(),
            "consecutive_failures": 0,
            "next_retry": 0,
        }
        if was_reconnecting:
            self._notify_link_status_change(uuid, "connected")

    def _record_link_failure(self, uuid):
        """Record failed communication with a remote link, apply exponential backoff."""
        current = self._link_status.get(uuid, {"consecutive_failures": 0})
        failures = current.get("consecutive_failures", 0) + 1
        backoff = min(300, 10 * (2 ** min(failures, 5)))  # cap at 5 min

        new_status = "reconnecting" if failures <= 10 else "disconnected"
        was_connected = current.get("status") in ("connected", "unknown", None)

        self._link_status[uuid] = {
            "status": new_status,
            "last_seen": current.get("last_seen"),
            "consecutive_failures": failures,
            "next_retry": time.time() + backoff,
        }

        if was_connected:
            self._notify_link_status_change(uuid, new_status)

    def _should_skip_link(self, uuid):
        """Check if a link is in backoff period and should be skipped."""
        status = self._link_status.get(uuid, {})
        next_retry = status.get("next_retry", 0)
        return next_retry > 0 and time.time() < next_retry

    def _notify_link_status_change(self, uuid, new_status):
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

    def __format_address(self, address: str | None):
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

    def __merge_config_dicts(self, config_dict, compare_dict):
        for key in config_dict:
            if config_dict.get(key) != compare_dict.get(key) and compare_dict.get(key) is not None:
                # Apply the new value
                config_dict[key] = compare_dict.get(key)
                # Also flag the dict as updated
                config_dict["last_updated"] = time.time()

    def __generate_default_config(self, config_dict: dict):
        return {
            "address": config_dict.get("address", "???"),
            "auth": config_dict.get("auth", "None"),
            "username": config_dict.get("username", ""),
            "password": config_dict.get("password", ""),
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
            "task_count": config_dict.get("task_count", 0),
            "last_updated": config_dict.get("last_updated", time.time()),
        }

    def acquire_network_transfer_lock(self, url, transfer_limit=1, lock_type="send"):
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
                    # Create new upload lock that will expire in 1 minute
                    self._network_transfer_lock[lock_key] = {
                        "expires": (time_now + 60),
                    }
                    # Return success
                    return lock_key
            # Failed to acquire network transfer lock
            return False

    def release_network_transfer_lock(self, lock_key):
        """
        Expire the transfer lock for the given lock_key

        :param lock_key:
        :return:
        """
        lock = self._transfer_lock
        with lock:
            # Expire the lock for this address
            self._network_transfer_lock[lock_key] = {}
            return True

    def remote_api_get(self, remote_config: dict, endpoint: str, timeout=2):
        """
        GET to remote installation API

        :param remote_config:
        :param endpoint:
        :param timeout:
        :return:
        """
        request_handler = RequestHandler(
            auth=remote_config.get("auth"),
            username=remote_config.get("username"),
            password=remote_config.get("password"),
        )
        address = self.__format_address(remote_config.get("address"))
        url = f"{address}{endpoint}"
        res = request_handler.get(url, timeout=timeout)
        if res.status_code == 200:
            return res.json()
        elif res.status_code in [400, 404, 405, 500]:
            json_data = res.json()
            self._log(
                "Error while executing GET on remote installation API - {}. Message: '{}'".format(
                    endpoint, json_data.get("error")
                ),
                message2=json_data.get("traceback", []),
                level="error",
            )
        return {}

    def remote_api_post(self, remote_config: dict, endpoint: str, data: dict, timeout=2):
        """
        POST to remote installation API

        :param remote_config:
        :param endpoint:
        :param data:
        :param timeout:
        :return:
        """
        request_handler = RequestHandler(
            auth=remote_config.get("auth"),
            username=remote_config.get("username"),
            password=remote_config.get("password"),
        )
        address = self.__format_address(remote_config.get("address"))
        url = f"{address}{endpoint}"
        res = request_handler.post(url, json=data, timeout=timeout)
        if res.status_code == 200:
            return res.json()
        elif res.status_code in [400, 404, 405, 500]:
            json_data = res.json()
            self._log(
                "Error while executing POST on remote installation API - {}. Message: '{}'".format(
                    endpoint, json_data.get("error")
                ),
                message2=json_data.get("traceback", []),
                level="error",
            )
            return json_data
        return {}

    def remote_api_post_file(self, remote_config: dict, endpoint: str, path: str):
        """
        Send a file to the remote installation
        No timeout is set so the request will continue until closed

        :param remote_config:
        :param endpoint:
        :param path:
        :return:
        """
        request_handler = RequestHandler(
            auth=remote_config.get("auth"),
            username=remote_config.get("username"),
            password=remote_config.get("password"),
        )
        address = self.__format_address(remote_config.get("address"))
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
            return res.json()
        elif res.status_code in [400, 404, 405, 500]:
            json_data = res.json()
            self._log(
                "Error while uploading file to remote installation API - {}. Message: '{}'".format(
                    endpoint, json_data.get("error")
                ),
                message2=json_data.get("traceback", []),
                level="error",
            )
        return {}

    def remote_api_delete(self, remote_config: dict, endpoint: str, data: dict, timeout=2):
        """
        DELETE to remote installation API

        :param remote_config:
        :param endpoint:
        :param data:
        :param timeout:
        :return:
        """
        request_handler = RequestHandler(
            auth=remote_config.get("auth"),
            username=remote_config.get("username"),
            password=remote_config.get("password"),
        )
        address = self.__format_address(remote_config.get("address"))
        url = f"{address}{endpoint}"
        res = request_handler.delete(url, json=data, timeout=timeout)
        if res.status_code == 200:
            return res.json()
        elif res.status_code in [400, 404, 405, 500]:
            json_data = res.json()
            self._log(
                "Error while executing DELETE on remote installation API - {}. Message: '{}'".format(
                    endpoint, json_data.get("error")
                ),
                message2=json_data.get("traceback", []),
                level="error",
            )
        return {}

    def remote_api_get_download(self, remote_config: dict, endpoint: str, path: str):
        """
        Download a file from a remote installation

        :param remote_config:
        :param endpoint:
        :param path:
        :return:
        """
        request_handler = RequestHandler(
            auth=remote_config.get("auth"),
            username=remote_config.get("username"),
            password=remote_config.get("password"),
        )
        address = self.__format_address(remote_config.get("address"))
        url = f"{address}{endpoint}"
        with request_handler.get(url, stream=True) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(chunk_size=None):
                    if chunk:
                        f.write(chunk)
        return True

    def validate_remote_installation(self, address: str, **kwargs):
        """
        Validate a remote Compresso installation by requesting
        its system info and version

        :param address:
        :param username:
        :param password:
        :return:
        """
        address = self.__format_address(address)

        request_handler = RequestHandler(
            auth=kwargs.get("auth"),
            username=kwargs.get("username"),
            password=kwargs.get("password"),
        )

        # Fetch config
        url = f"{address}/compresso/api/v2/settings/configuration"
        res = request_handler.get(url, timeout=2)
        if res.status_code != 200:
            if res.status_code in [400, 404, 405, 500]:
                json_data = res.json()
                self._log(
                    f"Error while fetching remote installation config. Message: '{json_data.get('error')}'",
                    message2=json_data.get("traceback", []),
                    level="error",
                )
            return {}
        system_configuration_data = res.json()

        # Fetch settings
        url = f"{address}/compresso/api/v2/settings/read"
        res = request_handler.get(url, timeout=2)
        if res.status_code != 200:
            if res.status_code in [400, 404, 405, 500]:
                json_data = res.json()
                self._log(
                    f"Error while fetching remote installation settings. Message: '{json_data.get('error')}'",
                    message2=json_data.get("traceback", []),
                    level="error",
                )
            return {}
        settings_data = res.json()

        # Fetch version
        url = f"{address}/compresso/api/v2/version/read"
        res = request_handler.get(url, timeout=2)
        if res.status_code != 200:
            if res.status_code in [400, 404, 405, 500]:
                json_data = res.json()
                self._log(
                    f"Error while fetching remote installation version. Message: '{json_data.get('error')}'",
                    message2=json_data.get("traceback", []),
                    level="error",
                )
            return {}
        version_data = res.json()

        # Fetch version
        url = f"{address}/compresso/api/v2/session/state"
        res = request_handler.get(url, timeout=2)
        if res.status_code != 200:
            if res.status_code in [400, 404, 405, 500]:
                json_data = res.json()
                self._log(
                    f"Error while fetching remote installation session state. Message: '{json_data.get('error')}'",
                    message2=json_data.get("traceback", []),
                    level="error",
                )
            return {}
        session_data = res.json()

        # Fetch task count data
        data = {"start": 0, "length": 1}
        url = f"{address}/compresso/api/v2/pending/tasks"
        res = request_handler.post(url, json=data, timeout=2)
        if res.status_code != 200:
            if res.status_code in [400, 404, 405, 500]:
                json_data = res.json()
                self._log(
                    f"Error while fetching remote installation pending task list. Message: '{json_data.get('error')}'",
                    message2=json_data.get("traceback", []),
                    level="error",
                )
            return {}
        tasks_data = res.json()

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
            "task_count": int(tasks_data.get("recordsTotal", 0)),
        }

    def update_all_remote_installation_links(self):  # noqa: C901 — multi-step remote link sync with error recovery
        """
        Updates the link status and configuration of linked remote installations

        :return:
        """
        save_settings = False
        installation_id_list = []
        remote_installations = []
        distributed_worker_count_target = self.settings.get_distributed_worker_count_target()
        for local_config in self.settings.get_remote_installations():
            # Ensure address is not added twice by comparing installation IDs
            # Items matching these checks will be skipped over and will not be added to the installation list
            #   that will be re-saved
            if local_config.get("uuid") in installation_id_list and local_config.get("uuid", "???") != "???":
                # Do not update this installation. By doing this it will be removed from the list
                save_settings = True
                continue

            # Ensure the address is something valid
            if not local_config.get("address"):
                save_settings = True
                continue

            # Remove any entries that have an unknown address and uuid
            if local_config.get("address") == "???" and local_config.get("uuid") == "???":
                save_settings = True
                continue

            # Check if this link is in backoff period
            # Derive a stable per-link key even when uuid is not yet synced
            raw_uuid = local_config.get("uuid", "???")
            link_uuid = f"_addr_{local_config.get('address', 'unknown')}" if raw_uuid == "???" else raw_uuid
            if self._should_skip_link(link_uuid):
                # Still in backoff -- keep existing config but mark unavailable
                updated_config = self.__generate_default_config(local_config)
                updated_config["available"] = False
                remote_installations.append(updated_config)
                installation_id_list.append(updated_config.get("uuid", "???"))
                continue

            # Fetch updated data
            installation_data = None
            try:
                installation_data = self.validate_remote_installation(
                    local_config.get("address"),
                    auth=local_config.get("auth"),
                    username=local_config.get("username"),
                    password=local_config.get("password"),
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, OSError) as e:
                self._record_link_failure(link_uuid)
                self.logger.warning(
                    "Link %s unreachable: %s (retry in %ds)",
                    link_uuid,
                    e,
                    int(self._link_status.get(link_uuid, {}).get("next_retry", 0) - time.time()),
                )
            except Exception as e:
                self._record_link_failure(link_uuid)
                self.logger.warning("Failed to validate remote installation at %s: %s", local_config.get("address"), e)

            # Generate updated configured values
            updated_config = self.__generate_default_config(local_config)
            updated_config["available"] = False
            if installation_data:
                # If we used a temp address-based key, migrate status to the real UUID
                real_uuid = installation_data.get("session", {}).get("uuid")
                if real_uuid and link_uuid != real_uuid:
                    if link_uuid in self._link_status:
                        self._link_status[real_uuid] = self._link_status.pop(link_uuid)
                    link_uuid = real_uuid
                # Record successful contact
                self._record_link_success(link_uuid)
                # Mark the installation as available
                updated_config["available"] = True

                # Append the current task count
                updated_config["task_count"] = installation_data.get("task_count", 0)

                merge_dict = {
                    "name": installation_data.get("settings", {}).get("installation_name"),
                    "version": installation_data.get("version"),
                    "uuid": installation_data.get("session", {}).get("uuid"),
                }
                self.__merge_config_dicts(updated_config, merge_dict)

                # Fetch the corresponding remote configuration for this local installation
                remote_config = {}
                try:
                    remote_config = self.fetch_remote_installation_link_config_for_this(local_config)
                except requests.exceptions.Timeout:
                    self._log("Request to fetch remote installation config timed out", level="warning")
                    updated_config["available"] = False
                except requests.exceptions.RequestException as e:
                    self._log("Request to fetch remote installation config failed", message2=str(e), level="warning")
                    updated_config["available"] = False
                except Exception as e:
                    self._log("Failed to fetch remote installation config", message2=str(e), level="error")
                    updated_config["available"] = False

                # If the remote configuration is newer than this one, use those values
                # The remote installation will do the same and this will synchronise
                remote_link_config = remote_config.get("link_config", {})
                if local_config.get("last_updated", 1) < remote_link_config.get("last_updated", 1):
                    # Note that the configuration options are reversed when reading from the remote installation config
                    # These items are not synced here:
                    #   - enable_task_preloading
                    #   - enable_checksum_validation
                    #   - enable_config_missing_libraries
                    if updated_config["enable_receiving_tasks"] != remote_link_config.get("enable_sending_tasks"):
                        updated_config["enable_receiving_tasks"] = remote_link_config.get("enable_sending_tasks")
                        save_settings = True
                    if updated_config["enable_sending_tasks"] != remote_link_config.get("enable_receiving_tasks"):
                        updated_config["enable_sending_tasks"] = remote_link_config.get("enable_receiving_tasks")
                        save_settings = True
                    # Update the distributed_worker_count_target
                    distributed_worker_count_target = remote_config.get("distributed_worker_count_target", 0)
                    # Also sync the last_updated flag
                    updated_config["last_updated"] = remote_link_config.get("last_updated")

                # If the remote config is unable to contact this installation (or it does not have a corresponding config yet)
                #   then also push the configuration
                if not remote_link_config.get("available"):
                    try:
                        self.push_remote_installation_link_config(updated_config)
                    except requests.exceptions.Timeout:
                        self._log("Request to push link config to remote installation timed out", level="warning")
                        updated_config["available"] = False
                    except requests.exceptions.RequestException as e:
                        self._log(
                            "Request to push link config to remote installation failed", message2=str(e), level="warning"
                        )
                        updated_config["available"] = False
                    except Exception as e:
                        self._log("Failed to push link config to remote installation", message2=str(e), level="error")
                        updated_config["available"] = False

                # Push library configurations for missing remote libraries (if configured to do so)
                if local_config.get("enable_sending_tasks") and local_config.get("enable_config_missing_libraries"):
                    # Fetch remote installation library name list
                    results = self.remote_api_get(local_config, "/compresso/api/v2/settings/libraries")
                    existing_library_names = []
                    for library in results.get("libraries", []):
                        existing_library_names.append(library.get("name"))
                    # Loop over local libraries and create an import object for each one that is missing
                    for library in Library.get_all_libraries():
                        # Ignore local libraries that are configured for remote only
                        if library.get("enable_remote_only"):
                            continue
                        # For each of the missing libraries, create a new remote library with that config.
                        if library.get("name") not in existing_library_names:
                            # Export library config
                            import_data = Library.export(library.get("id"))
                            # Set library ID to 0 to generate new library from this import
                            import_data["library_id"] = 0
                            # Configure remote library to be fore remote files only
                            import_data["library_config"]["enable_remote_only"] = True
                            import_data["library_config"]["enable_scanner"] = False
                            import_data["library_config"]["enable_inotify"] = False
                            # Import library on remote installation
                            self._log(
                                f"Importing remote library config '{library.get('name')}'",
                                message2=import_data,
                                level="debug",
                            )
                            result = self.import_remote_library_config(local_config, import_data)
                            if result is None:
                                # There was a connection issue of some kind. This was already logged.
                                continue
                            if result.get("success"):
                                self._log(f"Successfully imported library '{library.get('name')}'", level="debug")
                                continue
                            self._log(
                                f"Failed to import library config '{library.get('name')}'",
                                message2=result.get("error"),
                                level="error",
                            )

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

    def read_remote_installation_link_config(self, uuid: str):
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

    def update_single_remote_installation_link_config(self, configuration: dict, distributed_worker_count_target=0):
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

    def delete_remote_installation_link_config(self, uuid: str):
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

    def fetch_remote_installation_link_config_for_this(self, remote_config: dict):
        """
        Fetches and returns the corresponding link configuration from a remote installation

        :param remote_config:
        :return:
        """
        request_handler = RequestHandler(
            auth=remote_config.get("auth"),
            username=remote_config.get("username"),
            password=remote_config.get("password"),
        )
        address = self.__format_address(remote_config.get("address"))
        url = f"{address}/compresso/api/v2/settings/link/read"
        data = {"uuid": self.session.uuid}
        res = request_handler.post(url, json=data, timeout=2)
        if res.status_code == 200:
            return res.json()
        elif res.status_code in [400, 404, 405, 500]:
            json_data = res.json()
            self._log(
                f"Error while fetching remote installation link config. Message: '{json_data.get('error')}'",
                message2=json_data.get("traceback", []),
                level="error",
            )
        return {}

    def push_remote_installation_link_config(self, configuration: dict):
        """
        Pushes the given link config to the remote installation returns
        the corresponding link configuration from a remote installation

        :param configuration:
        :return:
        """
        request_handler = RequestHandler(
            auth=configuration.get("auth"),
            username=configuration.get("username"),
            password=configuration.get("password"),
        )
        address = self.__format_address(configuration.get("address"))
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

        # Current task count
        task_handler = task.Task()
        updated_config["task_count"] = int(task_handler.get_total_task_list_count())

        # Fetch local config for distributed_worker_count_target
        distributed_worker_count_target = self.settings.get_distributed_worker_count_target()

        # Remove some of the other fields. These will need to be adjusted on the remote instance manually
        del updated_config["address"]
        del updated_config["available"]

        data = {"link_config": updated_config, "distributed_worker_count_target": distributed_worker_count_target}
        res = request_handler.post(url, json=data, timeout=2)
        if res.status_code == 200:
            return True
        elif res.status_code in [400, 404, 405, 500]:
            json_data = res.json()
            self._log(
                f"Error while pushing remote installation link config. Message: '{json_data.get('error')}'",
                message2=json_data.get("traceback", []),
                level="error",
            )
        return False

    def check_remote_installation_for_available_workers(self):
        """
        Return a list of installations with workers available for a remote task.
        This list is filtered by:
            - Only installations that are available
            - Only installations that are configured for sending tasks to
            - Only installations that have not pending tasks
            - Only installations that have at least one idle worker that is not paused

        :return:
        """
        installations_with_info = {}
        for lc in self.settings.get_remote_installations():
            local_config = self.__generate_default_config(lc)

            # Only installations that are available
            if not local_config.get("available"):
                continue

            # Only installations that are configured for sending tasks to
            if not local_config.get("enable_sending_tasks"):
                continue

            # No valid UUID, no valid connection. This link may still be syncing
            if len(local_config.get("uuid", "")) < 20:
                continue

            # Skip links in backoff period
            if self._should_skip_link(local_config.get("uuid")):
                continue

            try:
                # Define auth
                # Only installations that have at least one idle worker that is not paused
                results = self.remote_api_get(local_config, "/compresso/api/v2/workers/status")
                worker_list = results.get("workers_status", [])

                # Only add installations that have not got pending tasks. This is unless we are configured to preload the queue
                max_pending_tasks = 0
                if local_config.get("enable_task_preloading"):
                    # Preload with the number of workers (regardless of the worker status) plus an additional one to account
                    # for delays in the downloads
                    max_pending_tasks = local_config.get("preloading_count")
                results = self.remote_api_post(local_config, "/compresso/api/v2/pending/tasks", {"start": 0, "length": 1})
                if results.get("error"):
                    continue
                current_pending_tasks = int(results.get("recordsFiltered", 0))
                if local_config.get("enable_task_preloading") and current_pending_tasks >= max_pending_tasks:
                    self._log(
                        f"Remote installation has exceeded the max remote pending task count ({current_pending_tasks})",
                        level="debug",
                    )
                    continue

                # Fetch remote installation library name list
                results = self.remote_api_get(local_config, "/compresso/api/v2/settings/libraries")
                library_names = []
                for library in results.get("libraries", []):
                    library_names.append(library.get("name"))

                # Ensure that worker count is more than 0
                if len(worker_list):
                    installations_with_info[local_config.get("uuid")] = {
                        "address": local_config.get("address"),
                        "auth": local_config.get("auth"),
                        "username": local_config.get("username"),
                        "password": local_config.get("password"),
                        "enable_task_preloading": local_config.get("enable_task_preloading"),
                        "preloading_count": local_config.get("preloading_count"),
                        "library_names": library_names,
                        "available_slots": 0,
                    }

                available_workers = False
                for worker in worker_list:
                    # Add a slot for each worker regardless of its status
                    installations_with_info[local_config.get("uuid")]["available_slots"] += 1
                    if worker.get("idle") and not worker.get("paused"):
                        # If any workers are idle and not paused then we have an available worker slot
                        available_workers = True
                        installations_with_info[local_config.get("uuid")]["available_workers"] = True
                    elif not worker.get("idle"):
                        # If any workers are busy with a task then also mark that as an an available worker slot
                        available_workers = True
                        installations_with_info[local_config.get("uuid")]["available_workers"] = True

                # Check if this installation is configured for preloading
                if available_workers and local_config.get("enable_task_preloading"):
                    # Add more slots to fill up the pending task queue
                    while not current_pending_tasks > max_pending_tasks:
                        installations_with_info[local_config.get("uuid")]["available_slots"] += 1
                        current_pending_tasks += 1

            except Exception as e:
                self._log(
                    f"Failed to contact remote installation '{local_config.get('address')}'",
                    message2=str(e),
                    level="warning",
                )
                continue

        return installations_with_info

    def within_enabled_link_limits(self):
        """
        All features unlocked — no link count limits.

        :return:
        """
        return True

    def new_pending_task_create_on_remote_installation(self, remote_config: dict, abspath: str, library_id: int):
        """
        Create a new pending task on a remote installation.
        The remote installation will return the ID of a generated task.

        :param remote_config:
        :param abspath:
        :param library_id:
        :return:
        """
        try:
            request_handler = RequestHandler(
                auth=remote_config.get("auth"),
                username=remote_config.get("username"),
                password=remote_config.get("password"),
            )
            address = self.__format_address(remote_config.get("address"))
            url = f"{address}/compresso/api/v2/pending/create"
            data = {
                "path": abspath,
                "library_id": library_id,
                "type": "remote",
            }
            res = request_handler.post(url, json=data, timeout=2)
            if res.status_code in [200, 400]:
                return res.json()
            elif res.status_code in [404, 405, 500]:
                json_data = res.json()
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

    def send_file_to_remote_installation(self, remote_config: dict, path: str):
        """
        Send a file to a remote installation.
        The remote installation will return the ID of a generated task.

        :param remote_config:
        :param path:
        :return:
        """
        try:
            results = self.remote_api_post_file(remote_config, "/compresso/api/v2/upload/pending/file", path)
            if results.get("error"):
                results = {}
            return results
        except requests.exceptions.RequestException as e:
            self._log("Request to upload to remote installation failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to upload to remote installation", message2=str(e), level="error")
        return {}

    def remove_task_from_remote_installation(self, remote_config: dict, remote_task_id: int):
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

    def get_the_remote_library_config_by_name(self, remote_config: dict, library_name: str):
        """
        Fetch a remote library's configuration by its name

        :param remote_config:
        :param library_name:
        :return:
        """
        try:
            # Fetch remote installation libraries
            results = self.remote_api_get(remote_config, "/compresso/api/v2/settings/libraries", timeout=4)
            for library in results.get("libraries", []):
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

    def set_the_remote_task_library(self, remote_config: dict, remote_task_id: int, library_name: str):
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

    def get_remote_pending_task_state(self, remote_config: dict, remote_task_id: int):
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

    def start_the_remote_task_by_id(self, remote_config: dict, remote_task_id: int):
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

    def get_all_worker_status(self, remote_config: dict):
        """
        Start the remote pending task

        :param remote_config:
        :return:
        """
        try:
            results = self.remote_api_get(remote_config, "/compresso/api/v2/workers/status")
            return results.get("workers_status", [])
        except requests.exceptions.Timeout:
            self._log("Request to get worker status timed out", level="warning")
        except requests.exceptions.RequestException as e:
            self._log("Request to get worker status failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to get worker status", message2=str(e), level="error")
        return []

    def get_single_worker_status(self, remote_config: dict, worker_id: str):
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

    def terminate_remote_worker(self, remote_config: dict, worker_id: str):
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

    def fetch_remote_task_data(self, remote_config: dict, remote_task_id: int, path: str):
        """
        Fetch the completed remote task data

        :param remote_config:
        :param remote_task_id:
        :param path:
        :return:
        """
        task_data = {}
        try:
            # Request API generate a DL link
            link_info = self.remote_api_get(remote_config, f"/compresso/api/v2/pending/download/data/id/{remote_task_id}")
            if link_info.get("link_id"):
                # Download the data file
                res = self.remote_api_get_download(remote_config, f"/compresso/downloads/{link_info.get('link_id')}", path)
                if res and os.path.exists(path):
                    with open(path) as f:
                        task_data = json.load(f)
        except requests.exceptions.Timeout:
            self._log("Request to fetch remote task data timed out", level="warning")
        except requests.exceptions.RequestException as e:
            self._log("Request to fetch remote task data failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to fetch remote task data", message2=str(e), level="error")
        return task_data

    def fetch_remote_task_completed_file(self, remote_config: dict, remote_task_id: int, path: str):
        """
        Fetch the completed remote task file

        :param remote_config:
        :param remote_task_id:
        :param path:
        :return:
        """
        try:
            # Request API generate a DL link
            link_info = self.remote_api_get(remote_config, f"/compresso/api/v2/pending/download/file/id/{remote_task_id}")
            if link_info.get("link_id"):
                # Download the file
                res = self.remote_api_get_download(remote_config, f"/compresso/downloads/{link_info.get('link_id')}", path)
                if res and os.path.exists(path):
                    return True
        except requests.exceptions.Timeout:
            self._log("Request to fetch remote task completed file timed out", level="warning")
        except requests.exceptions.RequestException as e:
            self._log("Request to fetch remote task completed file failed", message2=str(e), level="warning")
        except Exception as e:
            self._log("Failed to fetch remote task completed file", message2=str(e), level="error")
        return False

    def import_remote_library_config(self, remote_config: dict, import_data: dict):
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


def __getattr__(name):
    if name == "RemoteTaskManager":
        from compresso.libs.remote_task_manager import RemoteTaskManager

        return RemoteTaskManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
