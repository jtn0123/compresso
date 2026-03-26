#!/usr/bin/env python3

"""
tests.unit.test_session_api.py

Tests for the session API handler endpoints.
Covers: get_session_state, session_reload, session_logout,
get_app_auth_code, get_funding_proposals.
"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v2.session_api import ApiSessionHandler
from tests.unit.api_test_base import ApiTestBase


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_initialize(self, **kwargs):
    self.session = MagicMock()
    self.session.created = 1700000000.0
    self.session.level = 1
    self.session.picture_uri = "https://example.com/pic.png"
    self.session.name = "TestUser"
    self.session.email = "test@example.com"
    self.session.uuid = "uuid-1234"
    self.session.token_poll_task = None
    self.logger = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _mock_initialize)
class TestSessionApiState(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_get_session_state_success(self):
        resp = self.get_json("/session/state")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["name"] == "TestUser"
        assert data["email"] == "test@example.com"
        assert data["uuid"] == "uuid-1234"

    def test_get_session_state_not_created(self):
        def _mock_init_no_session(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.created = 0

        with patch.object(ApiSessionHandler, "initialize", _mock_init_no_session):
            resp = self.get_json("/session/state")
            assert resp.code == 500

    def test_get_session_state_exception(self):
        def _mock_init_error(self, **kwargs):
            class BrokenSession:
                created = 1700000000.0
                picture_uri = "https://example.com/pic.png"
                name = "TestUser"
                email = "test@example.com"
                uuid = "uuid-1234"
                token_poll_task = None

                @property
                def level(self):
                    raise Exception("error")

            self.session = BrokenSession()
            self.logger = MagicMock()
            self.params = kwargs.get("params")
            self.compresso_data_queues = {}

        with patch.object(ApiSessionHandler, "initialize", _mock_init_error):
            resp = self.get_json("/session/state")
            assert resp.code == 500


# ------------------------------------------------------------------
# Session reload
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _mock_initialize)
class TestSessionApiReload(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_session_reload_success(self):
        resp = self.post_json("/session/reload", {})
        assert resp.code == 200

    def test_session_reload_failure(self):
        def _mock_init_fail(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.register_compresso.return_value = False

        with patch.object(ApiSessionHandler, "initialize", _mock_init_fail):
            resp = self.post_json("/session/reload", {})
            assert resp.code == 500

    def test_session_reload_exception(self):
        def _mock_init_error(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.register_compresso.side_effect = Exception("error")

        with patch.object(ApiSessionHandler, "initialize", _mock_init_error):
            resp = self.post_json("/session/reload", {})
            assert resp.code == 500


# ------------------------------------------------------------------
# Session logout
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _mock_initialize)
class TestSessionApiLogout(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_session_logout_success(self):
        resp = self.get_json("/session/logout")
        assert resp.code == 200

    def test_session_logout_failure(self):
        def _mock_init_fail(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.sign_out.return_value = False

        with patch.object(ApiSessionHandler, "initialize", _mock_init_fail):
            resp = self.get_json("/session/logout")
            assert resp.code == 500

    def test_session_logout_exception(self):
        def _mock_init_error(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.sign_out.side_effect = Exception("error")

        with patch.object(ApiSessionHandler, "initialize", _mock_init_error):
            resp = self.get_json("/session/logout")
            assert resp.code == 500


# ------------------------------------------------------------------
# Get funding proposals
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSessionHandler, "initialize", _mock_initialize)
class TestSessionApiFunding(ApiTestBase):
    __test__ = True
    handler_class = ApiSessionHandler

    def test_get_funding_proposals_success(self):
        def _mock_init_funding(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.get_credit_portal_funding_proposals.return_value = ({"proposals": []}, 200)

        with patch.object(ApiSessionHandler, "initialize", _mock_init_funding):
            resp = self.get_json("/session/funding_proposals")
            assert resp.code == 200

    def test_get_funding_proposals_401(self):
        def _mock_init_401(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.get_credit_portal_funding_proposals.return_value = (None, 401)

        with patch.object(ApiSessionHandler, "initialize", _mock_init_401):
            resp = self.get_json("/session/funding_proposals")
            assert resp.code == 400

    def test_get_funding_proposals_server_error(self):
        def _mock_init_500(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.get_credit_portal_funding_proposals.return_value = ({"messages": ["Service unavailable"]}, 503)

        with patch.object(ApiSessionHandler, "initialize", _mock_init_500):
            resp = self.get_json("/session/funding_proposals")
            assert resp.code == 500

    def test_get_funding_proposals_exception(self):
        def _mock_init_error(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.get_credit_portal_funding_proposals.side_effect = Exception("error")

        with patch.object(ApiSessionHandler, "initialize", _mock_init_error):
            resp = self.get_json("/session/funding_proposals")
            assert resp.code == 500

    def test_get_funding_proposals_empty_response(self):
        def _mock_init_empty(self, **kwargs):
            _mock_initialize(self, **kwargs)
            self.session.get_credit_portal_funding_proposals.return_value = (None, 500)

        with patch.object(ApiSessionHandler, "initialize", _mock_init_empty):
            resp = self.get_json("/session/funding_proposals")
            assert resp.code == 500
