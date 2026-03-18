#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_paywall_removal.py

    Unit tests verifying that paywall / feature-gating has been removed:
    - Library.within_library_count_limits() always returns True
    - Links.within_enabled_link_limits() always returns True
    - Session level is always 100

"""

import os
import pytest
import tempfile

from unmanic.libs.unmodels.lib import Database


class TestPaywallRemoval(object):
    """
    TestPaywallRemoval

    Verify that feature-gating checks always return True / unrestricted.
    """

    db_connection = None

    def setup_class(self):
        """
        Setup the class state for pytest.

        Creates an in-memory SQLite database and the tables required
        by the classes under test.
        """
        config_path = tempfile.mkdtemp(prefix='unmanic_tests_')

        app_dir = os.path.dirname(os.path.abspath(__file__))
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": ':memory:',
            "MIGRATIONS_DIR": os.path.join(app_dir, '..', 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        from unmanic.libs.unmodels import (
            CompletedTasks, Installation, Libraries, Tags,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        )
        self.db_connection.create_tables([
            CompletedTasks, Installation, Libraries, Tags,
            Plugins, EnabledPlugins, LibraryPluginFlow,
        ])

        from unmanic import config
        self.settings = config.Config(config_path=config_path)

        # Clear Session singleton so it picks up our in-memory DB
        from unmanic.libs.singleton import SingletonType
        from unmanic.libs.session import Session
        SingletonType._instances.pop(Session, None)

    def teardown_class(self):
        pass

    # ------------------------------------------------------------------
    # Library.within_library_count_limits
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_library_within_library_count_limits_returns_true(self):
        """Library.within_library_count_limits() must always return True."""
        from unmanic.libs.library import Library
        assert Library.within_library_count_limits() is True

    # ------------------------------------------------------------------
    # Links.within_enabled_link_limits
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_links_within_enabled_link_limits_returns_true(self):
        """Links.within_enabled_link_limits() must always return True."""
        from unmanic.libs.installation_link import Links
        # Clear any singleton cache so we get a fresh Links instance
        from unmanic.libs.singleton import SingletonType
        SingletonType._instances.pop(Links, None)

        links = Links()
        assert links.within_enabled_link_limits() is True

    # ------------------------------------------------------------------
    # Session level (cross-check from paywall perspective)
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_session_level_is_100(self):
        """Session.level should be 100, meaning all features unlocked."""
        from unmanic.libs.session import Session
        assert Session.level == 100

    @pytest.mark.unittest
    def test_session_instance_supporter_level_is_100(self):
        """An instantiated Session should report supporter level 100."""
        from unmanic.libs.session import Session
        s = Session()
        assert s.get_supporter_level() == 100

    @pytest.mark.unittest
    def test_session_library_count_is_high(self):
        """Session.library_count should be effectively unlimited."""
        from unmanic.libs.session import Session
        s = Session()
        assert s.library_count >= 999

    @pytest.mark.unittest
    def test_session_link_count_is_high(self):
        """Session.link_count should be effectively unlimited."""
        from unmanic.libs.session import Session
        s = Session()
        assert s.link_count >= 999

    # ------------------------------------------------------------------
    # Plugin executor save_plugin_settings (code path verification)
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_save_plugin_settings_has_no_req_lev_gate(self):
        """
        Verify that the PluginExecutor.save_plugin_settings method source
        does not enforce a supporter-level gate via get_supporter_level().

        This is a static analysis check: we inspect the source code of the
        method to confirm the paywall check was removed.  A comment
        mentioning 'req_lev' is fine; what matters is that
        get_supporter_level() is not called to block settings.
        """
        import inspect
        from unmanic.libs.unplugins.executor import PluginExecutor

        source = inspect.getsource(PluginExecutor.save_plugin_settings)
        # The old paywall code called get_supporter_level() and compared
        # against a required level before allowing settings to be saved.
        assert 'get_supporter_level' not in source, (
            "save_plugin_settings still calls get_supporter_level — paywall not removed"
        )


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
