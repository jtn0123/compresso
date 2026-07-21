#!/usr/bin/env python3

"""
Bundled plugins that ship with Compresso.

These are automatically installed to the user's plugin directory
on startup if not already present (or if the bundled version is newer).
"""

import json
import os
import re
import shutil
from collections.abc import Mapping

from compresso.libs.logs import CompressoLogging
from compresso.libs.peewee_types import execute_write

logger = CompressoLogging.get_logger("bundled_plugins")

BUNDLED_PLUGINS_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_SETTINGS_FILENAME_PATTERN = re.compile(r"settings[A-Za-z0-9_.-]*\.json\Z")


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _validated_plugin_name(value: object, fallback: str | None = None) -> str:
    """Return a path-safe plugin name or reject malformed metadata."""
    candidate = value if isinstance(value, str) else fallback
    if candidate is None or candidate in {".", ".."} or _PLUGIN_NAME_PATTERN.fullmatch(candidate) is None:
        raise ValueError("Bundled plugin names may contain only letters, numbers, dots, dashes, and underscores")
    return candidate


def _safe_child_path(root: str | os.PathLike[str], name: str) -> str:
    """Build a direct child path and prove that it cannot escape its root."""
    safe_name = _validated_plugin_name(name)
    root_path = os.path.abspath(os.fspath(root))
    child_path = os.path.abspath(os.path.join(root_path, safe_name))
    if os.path.commonpath((root_path, child_path)) != root_path:
        raise ValueError("Bundled plugin path escapes its configured root")
    return child_path


def install_bundled_plugins(plugins_path: str | os.PathLike[str]) -> None:
    """
    Copy bundled plugins to the user's plugin directory if they are
    missing or if the bundled version is newer.

    :param plugins_path: Path to ~/.compresso/plugins/
    """
    if not os.path.exists(plugins_path):
        os.makedirs(plugins_path)

    for entry in os.listdir(BUNDLED_PLUGINS_DIR):
        try:
            bundled_dir = _safe_child_path(BUNDLED_PLUGINS_DIR, entry)
        except ValueError:
            logger.warning("Skipping bundled plugin with an invalid directory name")
            continue
        if os.path.islink(bundled_dir) or not os.path.isdir(bundled_dir):
            continue

        info_file = os.path.join(bundled_dir, "info.json")
        if not os.path.exists(info_file):
            continue

        with open(info_file) as f:
            bundled_info = _mapping(json.load(f))

        try:
            plugin_id = _validated_plugin_name(bundled_info.get("id"), entry)
            target_dir = _safe_child_path(plugins_path, plugin_id)
        except ValueError:
            logger.warning("Skipping bundled plugin with an invalid identifier")
            continue

        should_install = False

        if not os.path.exists(target_dir):
            should_install = True
        else:
            # Check version — install if bundled is newer
            target_info_file = os.path.join(target_dir, "info.json")
            if os.path.exists(target_info_file):
                with open(target_info_file) as f:
                    existing_info = _mapping(json.load(f))
                existing_version = existing_info.get("version", "0.0.0")
                bundled_version = bundled_info.get("version", "0.0.0")
                if _version_newer(bundled_version, existing_version):
                    should_install = True
            else:
                should_install = True

        if should_install:
            logger.info("Installing validated bundled plugin")
            _copy_plugin(bundled_dir, target_dir)
            normalized_info = dict(bundled_info)
            normalized_info["id"] = plugin_id
            _register_plugin_in_db(normalized_info, target_dir)


def _version_newer(new_version: object, old_version: object) -> bool:
    """Compare semver-like version strings."""

    def parse(value: object) -> list[int]:
        if not isinstance(value, str):
            return [0]
        try:
            return [int(part) for part in value.split(".")]
        except ValueError:
            return [0]

    return parse(new_version) > parse(old_version)


def _copy_plugin(source_dir: str, target_dir: str) -> None:
    """Copy plugin files, preserving user settings if they exist."""
    if os.path.islink(source_dir) or os.path.islink(target_dir):
        raise ValueError("Bundled plugin directories must not be symbolic links")

    # Preserve existing settings files
    preserved: dict[str, str] = {}
    if os.path.exists(target_dir):
        for filename in os.listdir(target_dir):
            if _SETTINGS_FILENAME_PATTERN.fullmatch(filename) is None:
                continue
            filepath = _safe_child_path(target_dir, filename)
            if os.path.islink(filepath) or not os.path.isfile(filepath):
                continue
            with open(filepath) as fh:
                preserved[filename] = fh.read()
        shutil.rmtree(target_dir)

    shutil.copytree(source_dir, target_dir)

    # Restore preserved settings
    for filename, content in preserved.items():
        with open(_safe_child_path(target_dir, filename), "w") as fh:
            fh.write(content)


def _register_plugin_in_db(plugin_info: Mapping[str, object], plugin_directory: str) -> None:
    """Register the plugin in the database."""
    try:
        from compresso.libs.unmodels.plugins import Plugins

        plugin_id = _validated_plugin_name(plugin_info.get("id"))
        plugin_data = {
            Plugins.plugin_id: plugin_id,
            Plugins.name: plugin_info.get("name", ""),
            Plugins.author: plugin_info.get("author", ""),
            Plugins.version: plugin_info.get("version", ""),
            Plugins.tags: plugin_info.get("tags", ""),
            Plugins.description: plugin_info.get("description", ""),
            Plugins.icon: plugin_info.get("icon", ""),
            Plugins.local_path: plugin_directory,
            Plugins.update_available: False,
        }

        existing = Plugins.get_or_none(plugin_id=plugin_id)
        if existing is not None:
            execute_write(Plugins.update(plugin_data).where(Plugins.plugin_id == plugin_id))
        else:
            execute_write(Plugins.insert(plugin_data))
    except Exception:
        logger.warning("Could not register bundled plugin in DB", exc_info=True)
