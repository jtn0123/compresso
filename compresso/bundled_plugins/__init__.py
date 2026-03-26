#!/usr/bin/env python3

"""
Bundled plugins that ship with Compresso.

These are automatically installed to the user's plugin directory
on startup if not already present (or if the bundled version is newer).
"""

import json
import os
import shutil

from compresso.libs.logs import CompressoLogging

logger = CompressoLogging.get_logger("bundled_plugins")

BUNDLED_PLUGINS_DIR = os.path.dirname(os.path.abspath(__file__))


def install_bundled_plugins(plugins_path):
    """
    Copy bundled plugins to the user's plugin directory if they are
    missing or if the bundled version is newer.

    :param plugins_path: Path to ~/.compresso/plugins/
    """
    if not os.path.exists(plugins_path):
        os.makedirs(plugins_path)

    for entry in os.listdir(BUNDLED_PLUGINS_DIR):
        bundled_dir = os.path.join(BUNDLED_PLUGINS_DIR, entry)
        if not os.path.isdir(bundled_dir):
            continue

        info_file = os.path.join(bundled_dir, "info.json")
        if not os.path.exists(info_file):
            continue

        with open(info_file) as f:
            bundled_info = json.load(f)

        plugin_id = bundled_info.get("id", entry)
        target_dir = os.path.join(plugins_path, plugin_id)

        should_install = False

        if not os.path.exists(target_dir):
            should_install = True
        else:
            # Check version — install if bundled is newer
            target_info_file = os.path.join(target_dir, "info.json")
            if os.path.exists(target_info_file):
                with open(target_info_file) as f:
                    existing_info = json.load(f)
                existing_version = existing_info.get("version", "0.0.0")
                bundled_version = bundled_info.get("version", "0.0.0")
                if _version_newer(bundled_version, existing_version):
                    should_install = True
            else:
                should_install = True

        if should_install:
            logger.info("Installing bundled plugin '%s' v%s", plugin_id, bundled_info.get("version"))
            _copy_plugin(bundled_dir, target_dir)
            _register_plugin_in_db(bundled_info, target_dir)


def _version_newer(new_version, old_version):
    """Compare semver-like version strings."""

    def parse(v):
        try:
            return [int(x) for x in v.split(".")]
        except (ValueError, AttributeError):
            return [0]

    return parse(new_version) > parse(old_version)


def _copy_plugin(source_dir, target_dir):
    """Copy plugin files, preserving user settings if they exist."""
    # Preserve existing settings files
    preserved = {}
    if os.path.exists(target_dir):
        for f in os.listdir(target_dir):
            if f.startswith("settings") and f.endswith(".json"):
                filepath = os.path.join(target_dir, f)
                with open(filepath) as fh:
                    preserved[f] = fh.read()
        shutil.rmtree(target_dir)

    shutil.copytree(source_dir, target_dir)

    # Restore preserved settings
    for filename, content in preserved.items():
        with open(os.path.join(target_dir, filename), "w") as fh:
            fh.write(content)


def _register_plugin_in_db(plugin_info, plugin_directory):
    """Register the plugin in the database."""
    try:
        from compresso.libs.unmodels.plugins import Plugins

        plugin_id = plugin_info.get("id")
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
            (Plugins.update(plugin_data).where(Plugins.plugin_id == plugin_id).execute())
        else:
            Plugins.insert(plugin_data).execute()
    except Exception as e:
        logger.warning("Could not register bundled plugin '%s' in DB: %s", plugin_info.get("id"), str(e))
