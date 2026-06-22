#!/usr/bin/env python3

"""
tests.unit.test_plugin_flow_position.py

Unit tests for PluginsHandler.set_plugin_flow_position_for_single_plugin, which
persists a single plugin's flow position into the LibraryPluginFlow table.

Regression coverage: the method was previously an empty stub that returned None,
so per-plugin flow positions were silently never saved.
"""

import os

import pytest

from compresso.libs.plugins import PluginsHandler
from compresso.libs.unmodels import Libraries
from compresso.libs.unmodels.lib import Database
from compresso.libs.unmodels.librarypluginflow import LibraryPluginFlow
from compresso.libs.unmodels.plugins import Plugins


@pytest.fixture
def flow_db(tmp_path):
    """Temporary SQLite DB with the tables needed for plugin-flow tests."""
    db_file = os.path.join(str(tmp_path), "flow_test.db")
    database_settings = {
        "TYPE": "SQLITE",
        "FILE": db_file,
        "MIGRATIONS_DIR": os.path.join(str(tmp_path), "migrations"),
    }
    db_connection = Database.select_database(database_settings)
    db_connection.create_tables([Plugins, Libraries, LibraryPluginFlow])
    yield db_connection
    db_connection.close()


def _make_plugin(plugin_id="encoder", name="Encoder"):
    return Plugins.create(
        plugin_id=plugin_id,
        name=name,
        author="tester",
        version="1.0.0",
        tags="video",
        description="desc",
        icon="",
        local_path="/tmp/plugin",
    )


@pytest.mark.unittest
class TestSetPluginFlowPositionForSinglePlugin:
    def test_creates_flow_row(self, flow_db):
        library = Libraries.create(name="Movies", path="/library/movies")
        plugin = _make_plugin()

        result = PluginsHandler.set_plugin_flow_position_for_single_plugin(plugin, "video.encoder", library.id, 3)

        assert result is not None
        rows = list(LibraryPluginFlow.select())
        assert len(rows) == 1
        row = rows[0]
        assert row.plugin_id.id == plugin.id
        assert row.library_id.id == library.id
        assert row.plugin_name == "Encoder"
        assert row.plugin_type == "video.encoder"
        assert row.position == 3

    def test_replaces_existing_position(self, flow_db):
        library = Libraries.create(name="Movies", path="/library/movies")
        plugin = _make_plugin()

        PluginsHandler.set_plugin_flow_position_for_single_plugin(plugin, "video.encoder", library.id, 1)
        PluginsHandler.set_plugin_flow_position_for_single_plugin(plugin, "video.encoder", library.id, 5)

        rows = list(LibraryPluginFlow.select().where(LibraryPluginFlow.plugin_type == "video.encoder"))
        assert len(rows) == 1
        assert rows[0].position == 5

    def test_returns_none_on_failure(self, flow_db):
        # A plugin instance that was never saved has no id, so the write fails and
        # the method returns None rather than raising.
        unsaved = Plugins(
            plugin_id="ghost",
            name="Ghost",
            author="t",
            version="1",
            tags="x",
            description="d",
            icon="",
            local_path="/tmp/x",
        )
        result = PluginsHandler.set_plugin_flow_position_for_single_plugin(unsaved, "video.encoder", 999999, 1)
        assert result is None
