#!/usr/bin/env python3

"""
compresso.plugins.py

Written by:               Josh.5 <jsunnex@gmail.com>
Date:                     03 Mar 2021, (3:52 PM)

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

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import zipfile
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Protocol, cast
from urllib.parse import urlparse

import requests
from filelock import FileLock
from peewee import DoesNotExist

from compresso import config
from compresso.libs import common
from compresso.libs.frontend_push_messages import FrontendPushMessages
from compresso.libs.json_state import atomic_json_write
from compresso.libs.library import Library
from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_count, execute_write
from compresso.libs.session import Session
from compresso.libs.singleton import SingletonType
from compresso.libs.unmodels import EnabledPlugins, LibraryPluginFlow, PluginRepos, Plugins
from compresso.libs.unplugins import PluginExecutor

_PLUGIN_INFO_FILENAME = "info.json"
_LOGGER_NAME = "Compresso.PluginsHandler"
_SHA256_HEX_LENGTH = 64
MAX_PLUGIN_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_PLUGIN_ARCHIVE_ENTRIES = 1_000
MAX_PLUGIN_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_PLUGIN_ENTRY_BYTES = 128 * 1024 * 1024
MAX_PLUGIN_INFO_BYTES = 1 * 1024 * 1024
MAX_PLUGIN_COMPRESSION_RATIO = 100
_PLUGIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_PLUGIN_REQUIRED_TEXT_FIELDS = ("id", "name", "author", "version", "tags", "description", "icon")
_PLUGIN_SORT_FIELDS = frozenset({"name", "author", "version", "plugin_id", "position", "update_available"})

type PluginRecord = dict[str, object]
type NormalizedArchiveMember = tuple[zipfile.ZipInfo, PurePosixPath]


class PluginRows(Protocol):
    def __iter__(self) -> Iterator[PluginRecord]: ...

    def count(self) -> int: ...


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return {}
    return cast("dict[str, object]", value)


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _object_list(value: object) -> list[PluginRecord]:
    if not isinstance(value, list):
        return []
    return [_object_dict(item) for item in value if isinstance(item, dict)]


class PluginsHandler(metaclass=SingletonType):
    """
    Set plugin version.
    Plugins must be compatible with this version to be installed.
    """

    version: int = 2
    _install_locks_guard = threading.Lock()
    _install_locks: dict[str, threading.RLock] = {}

    def __init__(self, *args: object, **kwargs: object) -> None:
        self.settings = config.Config()
        self.logger = CompressoLogging.get_logger(name=type(self).__name__)

    def _log(self, message: object, message2: object = "", level: str = "info") -> None:
        message = common.format_message(message, message2)
        getattr(self.logger, level)(message)

    @staticmethod
    def get_plugin_repo_id(repo_path: str) -> int:
        return int(hashlib.md5(repo_path.encode("utf8")).hexdigest(), 16)  # noqa: S324 — used for deterministic ID generation, not security

    def get_repo_cache_file(self, repo_id: int) -> str:
        plugins_directory = self.settings.get_plugins_path()
        if not os.path.exists(plugins_directory):
            os.makedirs(plugins_directory)
        return os.path.join(plugins_directory, f"repo-{repo_id}.json")

    def get_plugin_path(self, plugin_id: str) -> str:
        plugin_directory = self._get_plugin_path_without_create(plugin_id)
        if not os.path.exists(plugin_directory):
            os.makedirs(plugin_directory)
        return plugin_directory

    def _get_plugin_path_without_create(self, plugin_id: str) -> str:
        if not isinstance(plugin_id, str) or not _PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            raise ValueError(f"Invalid plugin_id: path traversal detected in '{plugin_id}'")
        base_path = os.path.realpath(self.settings.get_plugins_path())
        plugin_directory = os.path.realpath(os.path.join(base_path, plugin_id))
        if os.path.commonpath((base_path, plugin_directory)) != base_path or plugin_directory == base_path:
            raise ValueError(f"Invalid plugin_id: path traversal detected in '{plugin_id}'")
        return plugin_directory

    @classmethod
    def _plugin_install_lock(cls, plugin_id: str) -> threading.RLock:
        """Return the process-local lock for one validated plugin ID."""
        with cls._install_locks_guard:
            return cls._install_locks.setdefault(plugin_id, threading.RLock())

    @contextmanager
    def _plugin_install_guard(self, plugin_id: str) -> Iterator[None]:
        """Serialize one plugin ID across threads and server processes."""
        plugins_root = Path(self.settings.get_plugins_path()).resolve()
        plugins_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock_path = plugins_root / f".{plugin_id}.install.lock"
        with self._plugin_install_lock(plugin_id), FileLock(lock_path, mode=0o600):
            yield

    def get_plugin_download_cache_path(self, plugin_id: str, plugin_version: str) -> str:
        """Return a cache path contained under the configured plugin directory."""
        if not plugin_id or not plugin_version:
            raise ValueError("Remote plugin metadata must include a plugin_id and version")
        plugin_directory = os.path.realpath(self.settings.get_plugins_path())
        cache_path = os.path.realpath(os.path.join(plugin_directory, f"{plugin_id}-{plugin_version}.zip"))
        if os.path.commonpath((plugin_directory, cache_path)) != plugin_directory or cache_path == plugin_directory:
            raise ValueError("Invalid remote plugin metadata: cache path traversal detected")
        return cache_path

    @staticmethod
    def get_default_repo() -> str:
        return "default"

    def get_plugin_repos(self) -> list[PluginRecord]:
        """
        Returns a list of plugin repos

        :return:
        """
        default_repo = self.get_default_repo()
        repo_list: list[PluginRecord] = [{"path": default_repo}]

        repos = PluginRepos.select().order_by(PluginRepos.id.asc())
        for repo in repos:
            repo_dict = repo.model_to_dict()
            if repo_dict.get("path") == default_repo:
                continue
            repo_list.append(repo_dict)

        return repo_list

    def set_plugin_repos(self, repo_list: Sequence[str]) -> bool:
        # Ensure list of repo URLs is valid
        for repo_path in repo_list:
            repo_data = self.fetch_remote_repo_data(repo_path)
            if not repo_data:
                return False

        # Remove all existing repos
        execute_write(PluginRepos.delete())

        # Add new repos
        data = []
        for repo_path in repo_list:
            data.append({"path": repo_path})

        execute_write(PluginRepos.insert_many(data))

        return True

    def fetch_remote_repo_data(self, repo_path: str) -> dict[str, object] | None:
        # Fetch remote JSON file
        session = Session()
        uuid = session.get_installation_uuid()
        level = session.get_supporter_level()
        repo = base64.b64encode(repo_path.encode("utf-8")).decode("utf-8")
        api_path = f"plugin_repos/repo_data/uuid/{uuid}/level/{level}/repo/{repo}"
        data, status_code = session.api_get(
            "compresso-api",
            2,
            api_path,
        )
        if status_code == 401:
            # Something is wrong with registration. Let's resend it and try again.
            self.logger.debug("Plugin repo returned a request to register. Code:%s", status_code)
            session.register_compresso()
            data, status_code = session.api_get(
                "compresso-api",
                2,
                api_path,
            )
        if status_code >= 500:
            self.logger.debug("Failed to fetch plugin repo from '%s'. Code:%s", api_path, status_code)
        return _object_dict(data) if isinstance(data, dict) else None

    def update_plugin_repos(self) -> bool:
        """
        Updates the local cached data of plugin repos

        :return:
        """
        plugins_directory = self.settings.get_plugins_path()
        if not os.path.exists(plugins_directory):
            os.makedirs(plugins_directory)
        current_repos_list = self.get_plugin_repos()
        for repo in current_repos_list:
            repo_path = repo.get("path")
            if not isinstance(repo_path, str):
                continue
            repo_id = self.get_plugin_repo_id(repo_path)

            # Fetch remote JSON file
            repo_data = self.fetch_remote_repo_data(repo_path)

            # Dumb object to local JSON file
            repo_cache = self.get_repo_cache_file(repo_id)
            self.logger.info("Repo cache file '%s'.", repo_cache)
            try:
                atomic_json_write(repo_cache, repo_data, mode=0o600)
            except json.JSONDecodeError as e:
                self.logger.error("Unable to update plugin repo '%s'. %s", repo_path, str(e))
        return True

    def get_settings_of_all_installed_plugins(self) -> dict[str, dict[str, object]]:
        all_settings: dict[str, dict[str, object]] = {}

        # First fetch all enabled plugins
        order: list[dict[str, object]] = [
            {
                "column": "name",
                "dir": "asc",
            },
        ]
        installed_plugins: Iterable[PluginRecord] = self.get_plugin_list_filtered_and_sorted(order=order) or []

        # Fetch settings for each plugin
        plugin_executor = PluginExecutor()
        for plugin in installed_plugins:
            plugin_id = _string(plugin.get("plugin_id"))
            if plugin_id is None:
                continue
            plugin_settings, plugin_settings_meta = plugin_executor.get_plugin_settings(plugin_id)
            all_settings[plugin_id] = plugin_settings

        # Return modules
        return all_settings

    def read_repo_data(self, repo_id: int) -> dict[str, object]:
        repo_cache = self.get_repo_cache_file(repo_id)
        if os.path.exists(repo_cache):
            with open(repo_cache) as f:
                repo_data = json.load(f)
            return _object_dict(repo_data)
        return {}

    def get_plugin_info(self, plugin_id: str) -> dict[str, object]:
        plugin_info: dict[str, object] = {}
        plugin_directory = os.path.join(self.settings.get_plugins_path(), plugin_id)
        info_file = os.path.join(plugin_directory, _PLUGIN_INFO_FILENAME)
        if os.path.exists(info_file):
            # Read plugin info.json
            with open(info_file) as json_file:
                plugin_info = _object_dict(json.load(json_file))
        return plugin_info

    def get_plugins_in_repo_data(self, repo_data: Mapping[str, object]) -> list[PluginRecord]:
        return_list: list[PluginRecord] = []
        if "repo" in repo_data and "plugins" in repo_data:
            # Get URLs for plugin downloads
            repo_meta = _object_dict(repo_data.get("repo"))
            repo_data_directory = repo_meta.get("repo_data_directory")
            repo_name = repo_meta.get("name") or repo_meta.get("repo_name")

            # Loop over
            for plugin in _object_list(repo_data.get("plugins")):
                # Only show plugins that are compatible with this version
                # Plugins will require a 'compatibility' entry in their info.json file.
                #   This must list the plugin handler versions that it is compatible with
                compatibility = plugin.get("compatibility", plugin.get("compresso_compatibility", []))
                if not isinstance(compatibility, list) or self.version not in compatibility:
                    continue

                if isinstance(repo_data_directory, str) and repo_data_directory:
                    repo_data_directory = repo_data_directory.rstrip("/")
                    plugin_package_url = "{0}/{1}/{1}-{2}.zip".format(
                        repo_data_directory,
                        plugin.get("id"),
                        plugin.get("version"),
                    )
                    plugin_changelog_url = "{}/{}/changelog.md".format(
                        repo_data_directory,
                        plugin.get("id"),
                    )
                else:
                    plugin_package_url = _string(plugin.get("plugin_download_url")) or ""
                    plugin_changelog_url = ""

                # Check if plugin is already installed:
                plugin_status = {
                    "installed": False,
                }
                plugin_id = _string(plugin.get("id", plugin.get("plugin_id")))
                if plugin_id is None:
                    continue
                plugin_info = self.get_plugin_info(plugin_id)
                if plugin_info:
                    local_version = plugin_info.get("version")
                    # Parse the currently installed version number and check if it matches
                    remote_version = plugin.get("version", plugin.get("plugin_version"))
                    if local_version == remote_version:
                        plugin_status = {
                            "installed": True,
                            "update_available": False,
                        }
                    else:
                        # There is an update available
                        self.flag_plugin_for_update_by_id(plugin_id)
                        plugin_status = {
                            "installed": True,
                            "update_available": True,
                        }

                return_list.append(
                    {
                        "plugin_id": plugin_id,
                        "name": plugin.get("name", plugin.get("plugin_name")),
                        "author": plugin.get("author", plugin.get("plugin_author")),
                        "description": plugin.get("description", plugin.get("plugin_description")),
                        "version": plugin.get("version", plugin.get("plugin_version")),
                        "icon": plugin.get("icon", plugin.get("plugin_icon_url", "")),
                        "tags": plugin.get("tags"),
                        "status": plugin_status,
                        "package_url": plugin_package_url,
                        "package_sha256": plugin.get("package_sha256", plugin.get("sha256")),
                        "changelog_url": plugin_changelog_url,
                        "repo_name": repo_name,
                    }
                )
        return return_list

    def get_installable_plugins_list(self, filter_repo_id: int | str | None = None) -> list[PluginRecord]:
        """
        Return a list of plugins that can be installed
        Optionally filter by repo

        :param filter_repo_id:
        :return:
        """
        return_list: list[PluginRecord] = []

        # First fetch a list of available repos
        current_repos_list = self.get_plugin_repos()
        for repo in current_repos_list:
            repo_path = repo.get("path")
            if not isinstance(repo_path, str):
                continue
            repo_id = self.get_plugin_repo_id(repo_path)
            if filter_repo_id and repo_id != int(filter_repo_id):
                # Filtering by repo ID and this one does not match
                continue
            repo_data = self.read_repo_data(repo_id)
            plugins_in_repo = self.get_plugins_in_repo_data(repo_data)
            for plugin_data in plugins_in_repo:
                plugin_data["repo_id"] = str(repo_id)
            return_list += plugins_in_repo

        return return_list

    def read_remote_changelog_file(self, changelog_url: str) -> str:
        # A 1s timeout is aggressive enough that transient network blips
        # would otherwise crash the caller (changelog fetches are
        # best-effort UI metadata). Treat any RequestException the same
        # as a non-200 response.
        try:
            r = requests.get(changelog_url, timeout=1)
        except requests.exceptions.RequestException as e:
            self.logger.debug("Failed to fetch remote changelog from %s: %s", changelog_url, e)
            return ""
        if r.status_code == 200:
            return str(r.text)
        return ""

    def notify_site_of_plugin_install(self, plugin: Mapping[str, object]) -> bool:
        """
        Notify the compresso API API of the installation.
        This is used for metric stats so that we can get a count of plugin downloads.

        :param plugin:
        :return:
        """
        # Post
        session = Session()
        uuid = session.get_installation_uuid()
        level = session.get_supporter_level()
        post_data = {
            "uuid": uuid,
            "level": level,
            "plugin_id": plugin.get("plugin_id"),
            "author": plugin.get("author"),
            "version": plugin.get("version"),
        }
        try:
            repo_data, status_code = session.api_post("compresso-api", 1, "plugin_repos/record_install", post_data)
            if not repo_data.get("success"):
                session.register_compresso()
        except Exception as e:
            self.logger.debug("Exception while logging plugin install. %s", str(e))
            return False
        return True

    def install_plugin_by_id(self, plugin_id: str, repo_id: int | str | None = None) -> bool:
        """
        Find the matching plugin info for the given plugin ID.
        Download the plugin if it is found and return the result.
        If it is not found, return False.

        :param plugin_id:
        :param repo_id:
        :return:
        """
        plugin_list = self.get_installable_plugins_list(filter_repo_id=repo_id)
        for plugin in plugin_list:
            if plugin.get("plugin_id") == plugin_id:
                return self.download_and_install_plugin(plugin)

        return False

    def install_plugin_from_path_on_disk(self, abspath: str | os.PathLike[str]) -> bool:
        """
        Install a plugin from a ZIP file on disk

        :param abspath:
        :return:
        """
        if not zipfile.is_zipfile(abspath):
            self.logger.error("Plugin install failed - not a valid zip file: %s", abspath)
            return False
        try:
            plugin_info = self.install_plugin(abspath)
            self.logger.info("Installed plugin '%s'", plugin_info["plugin_id"])
            return True
        except Exception as e:
            self.logger.exception("Exception while installing plugin from zip '%s'. %s", abspath, str(e))
            return False
        finally:
            if os.path.isfile(abspath):
                os.remove(abspath)

    def download_and_install_plugin(self, plugin: Mapping[str, object]) -> bool:
        """
        Download and install a given plugin

        :param plugin:
        :return:
        """
        self.logger.debug("Installing plugin '%s'", plugin.get("name"))
        # Try to fetch URL
        try:
            # Fetch remote zip file
            destination = self.download_plugin(plugin)
            try:
                installed_info = self.install_plugin(destination, _string(plugin.get("plugin_id")))
            finally:
                if os.path.isfile(destination):
                    os.remove(destination)
            self.notify_site_of_plugin_install(installed_info)
            return True

        except Exception as e:
            self.logger.exception("Exception while installing plugin '%s'. %s", plugin, str(e))

        return False

    def download_plugin(self, plugin: Mapping[str, object]) -> str:
        """
        Download a given plugin to a temp directory

        :param plugin:
        :return:
        """
        package_url = _string(plugin.get("package_url")) or ""
        expected_digest = str(plugin.get("package_sha256") or "").lower()
        if urlparse(package_url).scheme != "https":
            raise ValueError("Remote plugins must be downloaded over HTTPS")
        if len(expected_digest) != _SHA256_HEX_LENGTH or any(char not in "0123456789abcdef" for char in expected_digest):
            raise ValueError("Remote plugin metadata must include a valid package_sha256 digest")

        # Fetch the package and authenticate its bytes before extraction. The
        # digest is supplied by the trusted repository metadata channel.
        plugin_id = _string(plugin.get("plugin_id"))
        plugin_version = _string(plugin.get("version"))
        if plugin_id is None or plugin_version is None:
            raise ValueError("Remote plugin metadata must include string plugin_id and version values")
        destination = self.get_plugin_download_cache_path(plugin_id, plugin_version)
        self.logger.debug("Downloading plugin '%s' to '%s'", package_url, destination)
        session = Session()
        digest = hashlib.sha256()
        bytes_downloaded = 0
        try:
            with session.requests_session.get(package_url, stream=True, allow_redirects=True, timeout=60) as r:
                r.raise_for_status()
                with open(destination, "wb") as f:
                    for chunk in r.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        bytes_downloaded += len(chunk)
                        if bytes_downloaded > MAX_PLUGIN_ARCHIVE_BYTES:
                            raise ValueError("Plugin archive exceeds the maximum compressed size of 64 MiB")
                        digest.update(chunk)
                        f.write(chunk)
            if digest.hexdigest() != expected_digest:
                raise ValueError("Downloaded plugin package does not match its repository SHA-256 digest")
        except Exception:
            if os.path.isfile(destination):
                os.remove(destination)
            raise
        return destination

    @staticmethod
    def _normalized_archive_path(member: zipfile.ZipInfo) -> PurePosixPath:
        raw_name = member.filename.replace("\\", "/").rstrip("/")
        if not raw_name or raw_name.startswith("/") or re.match(r"^[A-Za-z]:/", raw_name):
            raise ValueError(f"Plugin archive contains an unsafe path: {member.filename}")
        parts = PurePosixPath(raw_name).parts
        if any(part in {"", ".", ".."} for part in parts):
            raise ValueError(f"Plugin archive contains an unsafe path: {member.filename}")
        return PurePosixPath(*parts)

    @classmethod
    def _validate_archive_member(cls, member: zipfile.ZipInfo, seen_paths: set[str]) -> PurePosixPath:
        member_path = cls._normalized_archive_path(member)
        duplicate_key = member_path.as_posix().casefold()
        if duplicate_key in seen_paths:
            raise ValueError(f"Plugin archive contains a duplicate path: {member.filename}")
        seen_paths.add(duplicate_key)

        if member.flag_bits & 0x1:
            raise ValueError(f"Plugin archive contains an encrypted member: {member.filename}")
        if member.create_system == 3:
            file_type = stat.S_IFMT(member.external_attr >> 16)
            if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ValueError(f"Plugin archive contains a forbidden file type: {member.filename}")
        if member.file_size > MAX_PLUGIN_ENTRY_BYTES:
            raise ValueError(f"Plugin archive entry is too large: {member.filename}")
        if member.file_size and (
            member.compress_size == 0 or member.file_size / member.compress_size > MAX_PLUGIN_COMPRESSION_RATIO
        ):
            raise ValueError(f"Plugin archive exceeds the maximum compression ratio: {member.filename}")
        return member_path

    @classmethod
    def _validate_archive_members(cls, members: Sequence[zipfile.ZipInfo]) -> list[NormalizedArchiveMember]:
        if len(members) > MAX_PLUGIN_ARCHIVE_ENTRIES:
            raise ValueError(f"Plugin archive contains too many entries (maximum {MAX_PLUGIN_ARCHIVE_ENTRIES})")

        seen_paths: set[str] = set()
        expanded_size = 0
        compressed_size = 0
        normalized_members: list[NormalizedArchiveMember] = []
        for member in members:
            member_path = cls._validate_archive_member(member, seen_paths)
            expanded_size += member.file_size
            compressed_size += member.compress_size
            if expanded_size > MAX_PLUGIN_EXPANDED_BYTES:
                raise ValueError("Plugin archive exceeds the maximum total expanded size")
            normalized_members.append((member, member_path))

        if expanded_size and (compressed_size == 0 or expanded_size / compressed_size > MAX_PLUGIN_COMPRESSION_RATIO):
            raise ValueError("Plugin archive exceeds the maximum total compression ratio")
        return normalized_members

    def _validate_plugin_archive(
        self, zip_ref: zipfile.ZipFile, requested_plugin_id: str | None = None
    ) -> tuple[PluginRecord, list[NormalizedArchiveMember]]:
        normalized_members = self._validate_archive_members(zip_ref.infolist())
        info_members = [item for item in normalized_members if item[1].as_posix() == _PLUGIN_INFO_FILENAME]
        if len(info_members) != 1:
            raise ValueError("Plugin archive must contain exactly one root info.json")
        info_member = info_members[0][0]
        if info_member.file_size > MAX_PLUGIN_INFO_BYTES:
            raise ValueError("Plugin archive info.json is too large")
        try:
            plugin_info = _object_dict(json.loads(zip_ref.read(info_member).decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError, RuntimeError, zipfile.BadZipFile) as exc:
            raise ValueError("Plugin archive contains an invalid info.json") from exc
        if not plugin_info:
            raise ValueError("Plugin archive info.json must be a JSON object")

        for field in _PLUGIN_REQUIRED_TEXT_FIELDS:
            value = plugin_info.get(field)
            if not isinstance(value, str) or (field != "icon" and not value.strip()):
                raise ValueError(f"Plugin archive info.json has an invalid or missing '{field}'")
        plugin_id = _string(plugin_info["id"])
        if plugin_id is None:
            raise ValueError("Plugin archive info.json has an invalid plugin ID")
        if not _PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            raise ValueError(f"Plugin archive info.json has an invalid plugin ID: {plugin_id}")
        if requested_plugin_id is not None and plugin_id != requested_plugin_id:
            raise ValueError("Plugin archive info.json ID does not match the requested plugin ID")
        compatibility = plugin_info.get("compatibility", plugin_info.get("compresso_compatibility"))
        if not isinstance(compatibility, list) or self.version not in compatibility:
            raise ValueError(f"Plugin archive is not compatible with plugin API version {self.version}")
        return plugin_info, normalized_members

    @staticmethod
    def _extract_validated_plugin_archive(
        zip_ref: zipfile.ZipFile,
        plugin_directory: str | os.PathLike[str],
        normalized_members: Sequence[NormalizedArchiveMember],
    ) -> None:
        destination = Path(plugin_directory).resolve()
        for member, normalized_path in normalized_members:
            member_path = destination.joinpath(*normalized_path.parts)
            if member.is_dir():
                member_path.mkdir(parents=True, exist_ok=True, mode=0o700)
                continue
            member_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with zip_ref.open(member, "r") as source, open(member_path, "wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
            archive_mode = member.external_attr >> 16 if member.create_system == 3 else 0
            os.chmod(member_path, 0o700 if archive_mode & 0o111 else 0o600)

    @classmethod
    def _safe_extract_plugin_archive(cls, zip_ref: zipfile.ZipFile, plugin_directory: str | os.PathLike[str]) -> None:
        """Compatibility helper for callers that only need safe extraction."""
        normalized_members = cls._validate_archive_members(zip_ref.infolist())
        cls._extract_validated_plugin_archive(zip_ref, plugin_directory, normalized_members)

    def install_plugin(self, zip_file: str | os.PathLike[str], plugin_id: str | None = None) -> PluginRecord:
        """
        Install a given plugin from a zip file

        :param zip_file:
        :param plugin_id:
        :return:
        """
        archive_path = Path(zip_file)
        if archive_path.stat().st_size > MAX_PLUGIN_ARCHIVE_BYTES:
            raise ValueError("Plugin archive exceeds the maximum compressed size of 64 MiB")

        with zipfile.ZipFile(archive_path, "r") as zip_ref:
            plugin_info, normalized_members = self._validate_plugin_archive(zip_ref, plugin_id)
            validated_plugin_id = _string(plugin_info.get("id"))
            if validated_plugin_id is None:
                raise ValueError("Plugin archive info.json has an invalid plugin ID")
            plugin_id = validated_plugin_id
            with self._plugin_install_guard(plugin_id):
                return self._install_validated_plugin(zip_ref, plugin_info, normalized_members)

    def _install_validated_plugin(
        self,
        zip_ref: zipfile.ZipFile,
        plugin_info: PluginRecord,
        normalized_members: Sequence[NormalizedArchiveMember],
    ) -> PluginRecord:
        plugin_id = _string(plugin_info.get("id"))
        if plugin_id is None:
            raise ValueError("Plugin archive info.json has an invalid plugin ID")
        plugins_root = Path(self.settings.get_plugins_path()).resolve()
        plugins_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        plugin_directory = Path(self._get_plugin_path_without_create(plugin_id))
        if (plugin_directory / ".git").exists():
            raise RuntimeError("Plugin directory contains a git repository. Uninstall this source version before installing.")

        staging = Path(tempfile.mkdtemp(prefix=f".{plugin_id}.staging-", dir=plugins_root))
        rollback = None
        promoted = False
        snapshot = None
        executor = PluginExecutor()
        try:
            plugin_info = self._prepare_plugin_staging(zip_ref, plugin_info, normalized_members, staging)
            snapshot = self._snapshot_plugin_record(plugin_id)
            rollback = self._promote_plugin_staging(plugin_id, staging, plugin_directory, plugins_root)
            promoted = True
            installed_info = dict(plugin_info, plugin_id=plugin_id)
            if not self.write_plugin_data_to_db(installed_info, str(plugin_directory)):
                raise RuntimeError(f"Failed to persist database metadata for plugin '{plugin_id}'")
            executor.reload_plugin_module(plugin_id)
            if rollback is not None:
                shutil.rmtree(rollback, ignore_errors=True)
            return installed_info
        except Exception:
            if promoted:
                self._rollback_plugin_install(plugin_id, plugin_directory, rollback, snapshot, executor)
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if rollback is not None and rollback.exists():
                shutil.rmtree(rollback, ignore_errors=True)

    def _prepare_plugin_staging(
        self,
        zip_ref: zipfile.ZipFile,
        plugin_info: PluginRecord,
        normalized_members: Sequence[NormalizedArchiveMember],
        staging: Path,
    ) -> PluginRecord:
        self._extract_validated_plugin_archive(zip_ref, staging, normalized_members)
        if plugin_info.get("bundled") is True:
            plugin_info = dict(plugin_info, bundled=False)
            atomic_json_write(staging / _PLUGIN_INFO_FILENAME, plugin_info, mode=0o600)

        post_install_requirements = staging / "requirements.post-install.lock"
        if post_install_requirements.exists():
            self.install_plugin_requirements(staging, requirements_file=post_install_requirements)
        if plugin_info.get("defer_dependency_install", False):
            self.install_plugin_requirements(staging, clean=not post_install_requirements.exists())
            self.install_npm_modules(staging)
        return plugin_info

    @staticmethod
    def _promote_plugin_staging(plugin_id: str, staging: Path, plugin_directory: Path, plugins_root: Path) -> Path | None:
        rollback = None
        if plugin_directory.exists():
            rollback = Path(tempfile.mkdtemp(prefix=f".{plugin_id}.rollback-", dir=plugins_root))
            rollback.rmdir()
            os.replace(plugin_directory, rollback)
        try:
            os.replace(staging, plugin_directory)
        except Exception:
            if rollback is not None and rollback.exists():
                os.replace(rollback, plugin_directory)
            raise
        return rollback

    def _rollback_plugin_install(
        self,
        plugin_id: str,
        plugin_directory: Path,
        rollback: Path | None,
        snapshot: PluginRecord | None,
        executor: PluginExecutor,
    ) -> None:
        if plugin_directory.exists():
            shutil.rmtree(plugin_directory)
        if rollback is not None and rollback.exists():
            os.replace(rollback, plugin_directory)
        try:
            self._restore_plugin_record(plugin_id, snapshot)
        except Exception:
            self.logger.exception("Failed to restore database metadata for plugin '%s'", plugin_id)
        try:
            executor.reload_plugin_module(plugin_id)
        except Exception:
            self.logger.exception("Failed to restore loaded module for plugin '%s'", plugin_id)

    @staticmethod
    def install_plugin_requirements(
        plugin_path: str | os.PathLike[str],
        requirements_file: str | os.PathLike[str] | None = None,
        clean: bool = True,
    ) -> None:
        """Install a plugin's hash-locked wheel dependencies into its private target."""
        if requirements_file is None:
            requirements_file = os.path.join(plugin_path, "requirements.lock")
        install_target = os.path.join(plugin_path, "site-packages")
        # Check if the requirements file exists
        if not os.path.exists(requirements_file):
            return
        # First, remove the existing site-packages directory if it exists to ensure a clean installation
        if clean and os.path.exists(install_target):
            shutil.rmtree(install_target)
        # Recreate the site-packages directory
        os.makedirs(install_target, exist_ok=True)
        try:
            return_code = subprocess.call(  # noqa: S603 - trusted pip install for plugin dependencies
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--require-hashes",
                    "--only-binary=:all:",
                    "-r",
                    requirements_file,
                    f"--target={install_target}",
                ],
                timeout=300,
            )
            if isinstance(return_code, int) and return_code != 0:
                raise subprocess.CalledProcessError(return_code, "pip install")
        except subprocess.TimeoutExpired:
            logging.getLogger(_LOGGER_NAME).error("Timed out installing pip requirements for plugin at %s", requirements_file)
            raise

    @staticmethod
    def install_npm_modules(plugin_path: str | os.PathLike[str]) -> None:
        package_file = os.path.join(plugin_path, "package.json")
        if not os.path.exists(package_file):
            return
        lock_file = os.path.join(plugin_path, "package-lock.json")
        if not os.path.exists(lock_file):
            raise ValueError("Plugin package.json requires a package-lock.json")
        npm_binary = shutil.which("npm")
        if npm_binary is None:
            raise RuntimeError("npm is required to install plugin dependencies")
        # The executable is resolved through PATH and lifecycle scripts are disabled.
        return_code = subprocess.call(  # noqa: S603
            [npm_binary, "ci", "--ignore-scripts", "--omit=dev"],
            cwd=str(plugin_path),
            timeout=300,
        )
        if return_code != 0:
            raise subprocess.CalledProcessError(return_code, "npm ci")

    @staticmethod
    def _snapshot_plugin_record(plugin_id: str) -> PluginRecord | None:
        plugin_entry = Plugins.get_or_none(plugin_id=plugin_id)
        if plugin_entry is None:
            return None
        return {field.name: getattr(plugin_entry, field.name) for field in Plugins._meta.sorted_fields}

    @staticmethod
    def _restore_plugin_record(plugin_id: str, snapshot: PluginRecord | None) -> None:
        with Plugins._meta.database.atomic():
            if snapshot is None:
                execute_write(Plugins.delete().where(Plugins.plugin_id == plugin_id))
                return
            restored = execute_count(Plugins.update(snapshot).where(Plugins.plugin_id == plugin_id))
            if restored == 0:
                execute_write(Plugins.insert(snapshot))

    @staticmethod
    def write_plugin_data_to_db(plugin: Mapping[str, object], plugin_directory: str) -> bool:
        # Add installed plugin to database
        plugin_data = {
            Plugins.plugin_id: plugin.get("plugin_id"),
            Plugins.name: plugin.get("name"),
            Plugins.author: plugin.get("author"),
            Plugins.version: plugin.get("version"),
            Plugins.tags: plugin.get("tags"),
            Plugins.description: plugin.get("description"),
            Plugins.icon: plugin.get("icon"),
            Plugins.local_path: plugin_directory,
            Plugins.update_available: False,
        }
        plugin_entry = Plugins.get_or_none(plugin_id=plugin.get("plugin_id"))
        if plugin_entry is not None:
            # Update the existing entry
            update_query = Plugins.update(plugin_data).where(Plugins.plugin_id == plugin.get("plugin_id"))
            execute_write(update_query)
        else:
            # Insert a new entry
            execute_write(Plugins.insert(plugin_data))

        return True

    def get_total_plugin_list_count(self) -> int:
        task_query = Plugins.select().order_by(Plugins.id.desc())
        return int(task_query.count())

    def get_plugin_list_filtered_and_sorted(
        self,
        order: Sequence[Mapping[str, object]] | None = None,
        start: int = 0,
        length: int | None = None,
        search_value: str | None = None,
        id_list: Sequence[int] | None = None,
        enabled: bool | None = None,
        plugin_id: str | None = None,
        plugin_type: str | None = None,
        library_id: int | None = None,
    ) -> PluginRows | None:
        if order:
            invalid_fields = [item.get("column") for item in order if item.get("column") not in _PLUGIN_SORT_FIELDS]
            if invalid_fields:
                raise ValueError(f"Unsupported plugin sort field: {invalid_fields[0]}")
        model_does_not_exist = cast("type[Exception]", getattr(Plugins, "DoesNotExist", DoesNotExist))
        try:
            query = Plugins.select()

            if plugin_type:
                if library_id is not None:
                    join_condition = (
                        (LibraryPluginFlow.plugin_id == Plugins.id)
                        & (LibraryPluginFlow.plugin_type == plugin_type)
                        & (LibraryPluginFlow.library_id == library_id)
                    )
                else:
                    join_condition = (LibraryPluginFlow.plugin_id == Plugins.id) & (
                        LibraryPluginFlow.plugin_type == plugin_type
                    )
                query = query.join(LibraryPluginFlow, join_type="LEFT OUTER JOIN", on=join_condition)

            if id_list:
                query = query.where(Plugins.id.in_(id_list))

            if search_value:
                query = query.where(
                    (Plugins.name.contains(search_value))
                    | (Plugins.author.contains(search_value))
                    | (Plugins.tags.contains(search_value))
                )

            if plugin_id is not None:
                query = query.where(Plugins.plugin_id.in_([plugin_id]))

            # Deprecate this "enabled" status as plugins are now enabled when the are assigned to a library
            if enabled is not None:
                raise Exception("Fetching plugins by 'enabled' status is deprecated")

            if library_id is not None:
                join_condition = (EnabledPlugins.plugin_id == Plugins.id) & (EnabledPlugins.library_id == library_id)
                query = query.join(EnabledPlugins, join_type="LEFT OUTER JOIN", on=join_condition)
                query = query.where(EnabledPlugins.plugin_id.is_null(False))

            # Get order by
            if order:
                for o in order:
                    model_value = o.get("model") if o.get("model") else Plugins
                    column = o.get("column")
                    if not isinstance(column, str):
                        raise ValueError("Plugin sort column must be a string")
                    model = cast("type[Plugins] | type[LibraryPluginFlow]", model_value)
                    unsupported_flow_sort = model is LibraryPluginFlow and o.get("column") != "position"
                    if model not in {Plugins, LibraryPluginFlow} or unsupported_flow_sort:
                        raise ValueError("Unsupported plugin sort model")
                    order_by = getattr(model, column).asc() if o.get("dir") == "asc" else getattr(model, column).desc()

                    query = query.order_by_extend(order_by)

            if length:
                query = query.limit(length).offset(start)

            return cast("PluginRows", query.dicts())

        except model_does_not_exist:
            # No plugin entries exist yet
            self.logger.warning("No plugins exist yet.")
            return None

    def flag_plugin_for_update_by_id(self, plugin_id: str) -> bool:
        self.logger.debug("Flagging update available for installed plugin '%s'", plugin_id)
        # Disable the matching entries in the table
        execute_write(Plugins.update(update_available=True).where(Plugins.plugin_id == plugin_id))

        # Fetch records
        records: Iterable[PluginRecord] = self.get_plugin_list_filtered_and_sorted(plugin_id=plugin_id) or []

        # Ensure they are now disabled
        for record in records:
            if record.get("update_available"):
                continue
            self.logger.debug("Failed to flag plugin for update '%s'", record.get("plugin_id"))
            return False

        return True

    def uninstall_plugins_by_db_table_id(self, plugin_table_ids: Sequence[int]) -> int:
        """
        Remove a Plugin by it's DB table ID column.
        This will also remove the Plugin directory and all it's contents.

        :param plugin_table_ids:
        :return:
        """
        self.logger.debug("Uninstall plugins '%s'", plugin_table_ids)

        # Fetch records
        records_by_id: Iterable[PluginRecord] = self.get_plugin_list_filtered_and_sorted(id_list=plugin_table_ids) or []

        # Remove each plugin from disk
        for record in records_by_id:
            plugin_id = _string(record.get("plugin_id"))
            if plugin_id is None:
                continue
            # Unload plugin modules
            try:
                PluginExecutor.unload_plugin_module(plugin_id)
            except Exception as e:
                self._log(
                    f"Exception while unloading python module {record.get('plugin_id')}:",
                    message2=str(e),
                    level="exception",
                )

            # Remove from disk
            plugin_directory = self.get_plugin_path(plugin_id)
            self._log(f"Removing plugin files from disk '{plugin_directory}'", level="debug")
            try:
                # Delete the info file first to prevent any other process trying to read the plugin.
                # Without the info file, the plugin is effectivly uninstalled
                info_file = os.path.join(plugin_directory, _PLUGIN_INFO_FILENAME)
                if os.path.exists(info_file):
                    os.remove(info_file)
                # Cleanup the rest of the plugin directory
                shutil.rmtree(plugin_directory)
            except Exception as e:
                self._log(f"Exception while removing directory {plugin_directory}:", message2=str(e), level="exception")

        # Unlink from library by ID in DB
        execute_write(EnabledPlugins.delete().where(EnabledPlugins.plugin_id.in_(plugin_table_ids)))

        # Delete by ID in DB
        return execute_count(Plugins.delete().where(Plugins.id.in_(plugin_table_ids)))

    def update_plugins_by_db_table_id(self, plugin_table_ids: Sequence[int]) -> bool:
        self.logger.debug("Update plugins '%s'", plugin_table_ids)

        # Fetch records
        records_by_id: Iterable[PluginRecord] = self.get_plugin_list_filtered_and_sorted(id_list=plugin_table_ids) or []

        # Update each plugin in turn
        for record in records_by_id:
            plugin_id = _string(record.get("plugin_id"))
            if plugin_id is not None and self.install_plugin_by_id(plugin_id):
                continue
            self.logger.debug("Failed to update plugin '%s'", record.get("plugin_id"))
            return False

        return True

    def set_plugin_flow(self, plugin_type: str, library_id: int, flow: Sequence[Mapping[str, object]]) -> bool:
        """
        Update the plugin flow for all plugins in a given plugin type

        :param plugin_type:
        :param library_id:
        :param flow:
        :return:
        """
        # Delete all current flow data for this plugin type
        delete_query = LibraryPluginFlow.delete().where(
            (LibraryPluginFlow.plugin_type == plugin_type) & (LibraryPluginFlow.library_id == library_id)
        )
        execute_write(delete_query)

        success = True
        priority = 1
        for plugin in flow:
            plugin_id = plugin.get("plugin_id")

            # Fetch the plugin info
            plugin_info = Plugins.select().where(Plugins.plugin_id == plugin_id).first()
            if not plugin_info:
                continue

            # Save the plugin flow
            plugin_flow = self.set_plugin_flow_position_for_single_plugin(plugin_info, plugin_type, library_id, priority)
            priority += 1

            if not plugin_flow:
                success = False

        return success

    @staticmethod
    def set_plugin_flow_position_for_single_plugin(
        plugin_info: Plugins, plugin_type: str, library_id: int, priority: int
    ) -> LibraryPluginFlow | None:
        """
        Persist the flow position for a single plugin and type with the provided priority.

        Writes (or replaces) the matching ``LibraryPluginFlow`` row so the plugin's
        configured order of execution is honoured for the given library.

        :param plugin_info: The ``Plugins`` model instance for this plugin.
        :param plugin_type: The plugin runner type this position applies to.
        :param library_id: The library this flow position belongs to.
        :param priority: The 1-based position within the flow.
        :return: The created ``LibraryPluginFlow`` row on success, otherwise ``None``.
        """
        try:
            # Remove any existing position for this exact plugin/type/library tuple so
            # repeated saves do not accumulate duplicate flow rows.
            execute_write(
                LibraryPluginFlow.delete().where(
                    (LibraryPluginFlow.plugin_id == plugin_info.id)
                    & (LibraryPluginFlow.plugin_type == plugin_type)
                    & (LibraryPluginFlow.library_id == library_id)
                )
            )
            return LibraryPluginFlow.create(
                plugin_id=plugin_info,
                library_id=library_id,
                plugin_name=plugin_info.name,
                plugin_type=plugin_type,
                position=priority,
            )
        except Exception:
            logging.getLogger(_LOGGER_NAME).exception(
                "Failed to persist plugin flow position for plugin '%s' (type=%s, library=%s)",
                getattr(plugin_info, "plugin_id", plugin_info),
                plugin_type,
                library_id,
            )
            return None

    def get_enabled_plugin_modules_by_type(self, plugin_type: str, library_id: int | None = None) -> list[PluginRecord]:
        """
        Return a list of enabled plugin modules when given a plugin type

        Runners are filtered by the given 'plugin_type' and sorted by
        configured order of execution.

        If no library ID is provided, this will return all installed plugins for that type.
        This case should only be used for plugin runner types that are not associated with a library.

        :param plugin_type:
        :param library_id:
        :return:
        """
        # Refresh session
        s = Session()
        s.register_compresso()

        # First fetch all enabled plugins
        order: list[dict[str, object]] = [
            {
                "model": LibraryPluginFlow,
                "column": "position",
                "dir": "asc",
            },
            {
                "column": "name",
                "dir": "asc",
            },
        ]
        enabled_plugins: Iterable[PluginRecord] = (
            self.get_plugin_list_filtered_and_sorted(order=order, plugin_type=plugin_type, library_id=library_id) or []
        )

        # Fetch all plugin modules from the given list of enabled plugins
        plugin_executor = PluginExecutor()
        plugin_data = plugin_executor.get_plugin_data_by_type(enabled_plugins, plugin_type)

        # Return modules
        return plugin_data

    def exec_plugin_runner(self, data: dict[str, object], plugin_id: str, plugin_type: str) -> bool:
        """
        Execute a plugin runner

        :param data:
        :param plugin_id:
        :param plugin_type:
        :return:
        """
        plugin_executor = PluginExecutor()
        return plugin_executor.execute_plugin_runner(data, plugin_id, plugin_type)

    def get_incompatible_enabled_plugins(self, frontend_messages: FrontendPushMessages | None = None) -> list[PluginRecord]:
        """
        Ensure that the currently installed plugins are compatible with this PluginsHandler version

        :return:
        :rtype:
        """
        if frontend_messages is None:
            frontend_messages = FrontendPushMessages()
        # Fetch all libraries
        all_libraries = Library.get_all_libraries()

        def add_frontend_message(plugin_id: str, name: str) -> None:
            # If the frontend messages queue was included in request, append a message
            if frontend_messages:
                frontend_messages.add(
                    {
                        "id": f"incompatiblePlugin_{plugin_id}",
                        "type": "error",
                        "code": "incompatiblePlugin",
                        "message": name,
                        "timeout": 0,
                    }
                )

        # Fetch all enabled plugins
        incompatible_list: list[PluginRecord] = []
        for library in all_libraries:
            library_id = library.get("id")
            if not isinstance(library_id, int) or isinstance(library_id, bool):
                continue
            enabled_plugins: Iterable[PluginRecord] = self.get_plugin_list_filtered_and_sorted(library_id=library_id) or []

            # Ensure only compatible plugins are enabled
            # If all enabled plugins are compatible, then return true
            for record in enabled_plugins:
                try:
                    # Ensure plugin is compatible
                    plugin_id = _string(record.get("plugin_id"))
                    if plugin_id is None:
                        continue
                    plugin_info = self.get_plugin_info(plugin_id)
                except Exception as e:
                    plugin_info = None
                    self._log(
                        f"Exception while fetching plugin info for {record.get('plugin_id')}:",
                        message2=str(e),
                        level="exception",
                    )
                # Plugins will require a 'compatibility' entry in their info.json file.
                #   This must list the plugin handler versions that it is compatible with
                compatibility = plugin_info.get("compatibility", []) if plugin_info else []
                if isinstance(compatibility, list) and self.version in compatibility:
                    continue

                self._log(
                    f"Incompatible plugin detected: {record.get('name')} ({record.get('plugin_id')})",
                    level="warning",
                )
                incompatible_list.append(
                    {
                        "plugin_id": record.get("plugin_id"),
                        "name": record.get("name"),
                    }
                )
                plugin_id = _string(record.get("plugin_id")) or "unknown"
                plugin_name = _string(record.get("name")) or "Unknown plugin"
                add_frontend_message(plugin_id, plugin_name)

        return incompatible_list

    @staticmethod
    def get_plugin_types_with_flows() -> list[str]:
        """
        Returns a list of all available plugin types

        :return:
        """
        return_plugin_types: list[str] = []
        plugin_ex = PluginExecutor()
        types_list = plugin_ex.get_all_plugin_types()
        # Filter out the types without flows
        for plugin_type in types_list:
            if plugin_type.get("has_flow"):
                plugin_type_id = _string(plugin_type.get("id"))
                if plugin_type_id is not None:
                    return_plugin_types.append(plugin_type_id)
        return return_plugin_types

    def get_enabled_plugin_flows_for_plugin_type(self, plugin_type: str, library_id: int) -> list[PluginRecord]:
        """
        Fetch all enabled plugin flows for a plugin type

        :param plugin_type:
        :param library_id:
        :return:
        """
        return_plugin_flow: list[PluginRecord] = []
        for plugin_module in self.get_enabled_plugin_modules_by_type(plugin_type, library_id=library_id):
            return_plugin_flow.append(
                {
                    "plugin_id": plugin_module.get("plugin_id"),
                    "name": plugin_module.get("name", ""),
                    "author": plugin_module.get("author", ""),
                    "description": plugin_module.get("description", ""),
                    "version": plugin_module.get("version", ""),
                    "icon": plugin_module.get("icon", ""),
                }
            )
        return return_plugin_flow

    def run_event_plugins_for_plugin_type(self, plugin_type: str, data: dict[str, object]) -> None:
        """
        Run all enabled plugins for an event plugin type

        :param plugin_type:
        :param data:
        :return:
        """
        plugin_modules = self.get_enabled_plugin_modules_by_type(plugin_type)
        for plugin_module in plugin_modules:
            plugin_id = _string(plugin_module.get("plugin_id"))
            if plugin_id is None or not self.exec_plugin_runner(data, plugin_id, plugin_type):
                continue
