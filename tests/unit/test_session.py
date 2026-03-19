#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_session.py

    Unit tests for the Session class (all features unlocked, no remote API).

"""

import os
import pytest
import tempfile

from compresso.libs.unmodels.lib import Database


class TestSession(object):
    """
    TestSession

    Test the Session class behaves as an all-features-unlocked stub.
    """

    db_connection = None

    def setup_class(self):
        """
        Setup the class state for pytest.

        Creates an in-memory SQLite database and initialises
        the required tables so that Session can fetch installation data.
        """
        config_path = tempfile.mkdtemp(prefix='compresso_tests_')

        app_dir = os.path.dirname(os.path.abspath(__file__))
        database_settings = {
            "TYPE": "SQLITE",
            "FILE": ':memory:',
            "MIGRATIONS_DIR": os.path.join(app_dir, '..', 'migrations'),
        }
        self.db_connection = Database.select_database(database_settings)

        # Create the Installation table (needed by Session.__fetch_installation_data)
        from compresso.libs.unmodels import Installation
        self.db_connection.create_tables([Installation])

        from compresso import config
        self.settings = config.Config(config_path=config_path)

        # Clear singleton cache so each test class gets a fresh Session
        from compresso.libs.singleton import SingletonType
        from compresso.libs.session import Session
        SingletonType._instances.pop(Session, None)

    def teardown_class(self):
        pass

    def _make_session(self):
        """Create a fresh Session instance (singleton-cleared in setup_class)."""
        from compresso.libs.session import Session
        return Session()

    # ------------------------------------------------------------------
    # Level / supporter tier
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_default_level_is_100(self):
        """Session.level should be 100 by default (all features unlocked)."""
        from compresso.libs.session import Session
        assert Session.level == 100

    @pytest.mark.unittest
    def test_get_supporter_level_returns_100(self):
        s = self._make_session()
        assert s.get_supporter_level() == 100

    # ------------------------------------------------------------------
    # Registration / auth (no-ops)
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_register_compresso_returns_true(self):
        s = self._make_session()
        assert s.register_compresso() is True

    @pytest.mark.unittest
    def test_register_compresso_with_force_returns_true(self):
        s = self._make_session()
        assert s.register_compresso(force=True) is True

    @pytest.mark.unittest
    def test_auth_user_account_returns_true(self):
        s = self._make_session()
        assert s.auth_user_account() is True

    @pytest.mark.unittest
    def test_sign_out_returns_true(self):
        s = self._make_session()
        assert s.sign_out() is True

    @pytest.mark.unittest
    def test_sign_out_with_remote_false_returns_true(self):
        s = self._make_session()
        assert s.sign_out(remote=False) is True

    # ------------------------------------------------------------------
    # URL methods return empty strings
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_get_site_url_returns_empty_string(self):
        s = self._make_session()
        assert s.get_site_url() == ""

    @pytest.mark.unittest
    def test_get_sign_out_url_returns_empty_string(self):
        s = self._make_session()
        assert s.get_sign_out_url() == ""

    @pytest.mark.unittest
    def test_get_patreon_login_url_returns_empty_string(self):
        s = self._make_session()
        assert s.get_patreon_login_url() == ""

    @pytest.mark.unittest
    def test_get_github_login_url_returns_empty_string(self):
        s = self._make_session()
        assert s.get_github_login_url() == ""

    @pytest.mark.unittest
    def test_get_discord_login_url_returns_empty_string(self):
        s = self._make_session()
        assert s.get_discord_login_url() == ""

    # ------------------------------------------------------------------
    # Other no-op methods
    # ------------------------------------------------------------------

    @pytest.mark.unittest
    def test_auth_trial_account_returns_true(self):
        s = self._make_session()
        assert s.auth_trial_account() is True

    @pytest.mark.unittest
    def test_verify_token_returns_true(self):
        s = self._make_session()
        assert s.verify_token() is True

    @pytest.mark.unittest
    def test_get_access_token_returns_true(self):
        s = self._make_session()
        assert s.get_access_token() is True

    @pytest.mark.unittest
    def test_get_patreon_sponsor_page_returns_false(self):
        s = self._make_session()
        assert s.get_patreon_sponsor_page() is False

    @pytest.mark.unittest
    def test_init_device_auth_flow_returns_false(self):
        s = self._make_session()
        assert s.init_device_auth_flow() is False


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
