#!/usr/bin/env python3

"""
tests.unit.test_api_deferred_coverage.py

Schema-validation rejection coverage for three endpoints whose
happy/internal-error paths are already covered elsewhere but whose
input-validation (400) path was not exercised:

  - POST /plugins/flow/save           (plugin_flow_mixin)
  - POST /settings/link/validate      (settings_link_mixin)
  - POST /settings/library/import     (settings_library_mixin)

Each test posts an empty / structurally-invalid payload and asserts
the handler returns 400 via read_json_request's schema check —
without ever reaching the helper layer.
"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v2.plugins_api import ApiPluginsHandler
from compresso.webserver.api_v2.settings_api import ApiSettingsHandler
from tests.unit.api_test_base import ApiTestBase


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_plugins_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


def _mock_settings_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}
    self.config = MagicMock()


PLUGINS_HELPERS = "compresso.webserver.helpers.plugins"
SETTINGS_HELPERS = "compresso.webserver.helpers.settings"
SETTINGS_LINK_MIXIN = "compresso.webserver.api_v2.settings_link_mixin"


# ------------------------------------------------------------------
# POST /plugins/flow/save — invalid payload
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiPluginsHandler, "initialize", _mock_plugins_initialize)
class TestPluginFlowSaveInvalidPayload(ApiTestBase):
    __test__ = True
    handler_class = ApiPluginsHandler

    @patch(PLUGINS_HELPERS + ".save_enabled_plugin_flows_for_plugin_type")
    def test_empty_body_returns_400(self, mock_save):
        """An empty JSON object is missing all required fields
        (plugin_type, library_id, plugin_flow) and must be rejected at
        the schema layer — the helper must never be called."""
        resp = self.post_json("/plugins/flow/save", {})
        assert resp.code == 400
        mock_save.assert_not_called()

    @patch(PLUGINS_HELPERS + ".save_enabled_plugin_flows_for_plugin_type")
    def test_malformed_json_returns_400(self, mock_save):
        """A POST body that isn't valid JSON at all must be rejected
        before reaching the schema or helper layer."""
        response = self.fetch(
            "/compresso/api/v2/plugins/flow/save",
            method="POST",
            body="{not valid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.code == 400
        mock_save.assert_not_called()


# ------------------------------------------------------------------
# POST /settings/link/validate — invalid payload
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_settings_initialize)
class TestSettingsLinkValidateInvalidPayload(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(f"{SETTINGS_LINK_MIXIN}.Links")
    def test_empty_body_returns_400(self, mock_links_cls):
        """An empty JSON object is missing the required `address`
        field; the schema layer must reject before the Links helper
        is touched."""
        resp = self.post_json("/settings/link/validate", {})
        assert resp.code == 400
        mock_links_cls.assert_not_called()

    @patch(f"{SETTINGS_LINK_MIXIN}.Links")
    def test_malformed_json_returns_400(self, mock_links_cls):
        """A POST body that isn't valid JSON at all must be rejected
        before reaching the schema or helper layer."""
        response = self.fetch(
            "/compresso/api/v2/settings/link/validate",
            method="POST",
            body="not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert response.code == 400
        mock_links_cls.assert_not_called()


# ------------------------------------------------------------------
# POST /settings/library/import — invalid payload
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiSettingsHandler, "initialize", _mock_settings_initialize)
class TestSettingsLibraryImportInvalidPayload(ApiTestBase):
    __test__ = True
    handler_class = ApiSettingsHandler

    @patch(SETTINGS_HELPERS + ".save_library_request")
    def test_empty_body_returns_400(self, mock_save):
        """An empty JSON object is missing required fields
        (library_id, library_config); the schema layer must reject
        before the library save helper is touched."""
        resp = self.post_json("/settings/library/import", {})
        assert resp.code == 400
        mock_save.assert_not_called()

    @patch(SETTINGS_HELPERS + ".save_library_request")
    def test_malformed_json_returns_400(self, mock_save):
        """A POST body that isn't valid JSON at all must be rejected
        before reaching the schema or save layer."""
        response = self.fetch(
            "/compresso/api/v2/settings/library/import",
            method="POST",
            body='{"library_id": 1, "library_config":',  # truncated
            headers={"Content-Type": "application/json"},
        )
        assert response.code == 400
        mock_save.assert_not_called()
