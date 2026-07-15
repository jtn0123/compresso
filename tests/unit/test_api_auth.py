#!/usr/bin/env python3

"""
tests.unit.test_api_auth.py

Tests for optional API auth and CSRF protection in BaseApiHandler.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import tornado.web

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v1.base_api_handler import BaseApiHandler as V1BaseApiHandler
from compresso.webserver.api_v2.approval_api import ApiApprovalHandler
from tests.unit.api_test_base import ApiTestBase


def _test_token(label):
    return f"test-{label}"


TEST_SERVICE_TOKEN = _test_token("service")
TEST_V1_TOKEN = _test_token("v1")
TEST_WORKER_TOKEN = _test_token("worker")


class _Settings:
    def __init__(self, *, api_auth_enabled=False, api_auth_token="", csrf_protection_enabled=False):
        self.api_auth_enabled = api_auth_enabled
        self.api_auth_token = api_auth_token
        self.csrf_protection_enabled = csrf_protection_enabled

    def get_api_auth_enabled(self):
        return self.api_auth_enabled

    def get_api_auth_token(self):
        return self.api_auth_token

    def get_csrf_protection_enabled(self):
        return self.csrf_protection_enabled


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


@pytest.mark.unittest
@patch.object(ApiApprovalHandler, "initialize", _mock_initialize)
class TestApiMutationProtection(ApiTestBase):
    __test__ = True
    handler_class = ApiApprovalHandler

    @patch("compresso.webserver.helpers.approval.approve_tasks")
    @patch("compresso.config.Config", return_value=_Settings())
    def test_auth_disabled_preserves_mutating_requests(self, _mock_config, mock_approve):
        resp = self.post_json("/approval/approve", {"id_list": [1]})
        assert resp.code == 200
        mock_approve.assert_called_once_with([1])

    @patch("compresso.webserver.helpers.approval.approve_tasks")
    @patch("compresso.config.Config", return_value=_Settings(api_auth_enabled=True, api_auth_token="secret"))  # noqa: S106
    def test_auth_enabled_rejects_missing_token(self, _mock_config, mock_approve):
        resp = self.post_json("/approval/approve", {"id_list": [1]})
        assert resp.code == 401
        mock_approve.assert_not_called()

    @patch("compresso.webserver.helpers.approval.approve_tasks")
    @patch("compresso.config.Config", return_value=_Settings(api_auth_enabled=True, api_auth_token="secret"))  # noqa: S106
    def test_auth_enabled_accepts_bearer_token(self, _mock_config, mock_approve):
        resp = self.fetch(
            "/compresso/api/v2/approval/approve",
            method="POST",
            body=json.dumps({"id_list": [1]}),
            headers={"Content-Type": "application/json", "Authorization": "Bearer secret"},
        )
        assert resp.code == 200
        mock_approve.assert_called_once_with([1])

    @patch("compresso.webserver.helpers.approval.approve_tasks")
    @patch("compresso.config.Config", return_value=_Settings(api_auth_enabled=True, api_auth_token="secret"))  # noqa: S106
    def test_auth_enabled_accepts_compresso_token_header(self, _mock_config, mock_approve):
        resp = self.fetch(
            "/compresso/api/v2/approval/approve",
            method="POST",
            body=json.dumps({"id_list": [1]}),
            headers={"Content-Type": "application/json", "X-Compresso-Api-Token": "secret"},
        )
        assert resp.code == 200
        mock_approve.assert_called_once_with([1])

    @patch("compresso.webserver.helpers.approval.prepare_approval_summary")
    @patch("compresso.config.Config", return_value=_Settings(api_auth_enabled=True, api_auth_token="secret"))  # noqa: S106
    def test_auth_enabled_rejects_missing_token_on_read_endpoint(self, _mock_config, mock_summary):
        mock_summary.return_value = {
            "total_count": 0,
            "total_source_size": 0,
            "total_staged_size": 0,
            "total_space_saved": 0,
            "average_savings_percent": 0,
            "largest_savings_file": "",
            "largest_savings_bytes": 0,
            "average_vmaf": None,
            "codec_options": [],
        }
        resp = self.post_json("/approval/summary", {})
        assert resp.code == 401
        mock_summary.assert_not_called()

    @patch("compresso.webserver.helpers.approval.prepare_approval_summary")
    @patch("compresso.config.Config", return_value=_Settings(api_auth_enabled=True, api_auth_token="secret"))  # noqa: S106
    def test_auth_enabled_accepts_token_on_read_endpoint(self, _mock_config, mock_summary):
        mock_summary.return_value = {
            "total_count": 0,
            "total_source_size": 0,
            "total_staged_size": 0,
            "total_space_saved": 0,
            "average_savings_percent": 0,
            "largest_savings_file": "",
            "largest_savings_bytes": 0,
            "average_vmaf": None,
            "codec_options": [],
        }
        resp = self.fetch(
            "/compresso/api/v2/approval/summary",
            method="POST",
            body="{}",
            headers={"Content-Type": "application/json", "X-Compresso-Api-Token": "secret"},
        )
        assert resp.code == 200
        mock_summary.assert_called_once()

    @patch("compresso.webserver.helpers.approval.approve_tasks")
    @patch("compresso.config.Config", return_value=_Settings(csrf_protection_enabled=True))
    def test_csrf_enabled_rejects_missing_header_on_mutation(self, _mock_config, mock_approve):
        resp = self.post_json("/approval/approve", {"id_list": [1]})
        assert resp.code == 403
        mock_approve.assert_not_called()

    @patch("compresso.webserver.helpers.approval.approve_tasks")
    @patch("compresso.config.Config", return_value=_Settings(csrf_protection_enabled=True))
    def test_csrf_enabled_accepts_cookie_header_pair(self, _mock_config, mock_approve):
        resp = self.fetch(
            "/compresso/api/v2/approval/approve",
            method="POST",
            body=json.dumps({"id_list": [1]}),
            headers={
                "Content-Type": "application/json",
                "Cookie": "compresso_csrf_token=test-token",
                "X-Compresso-CSRF-Token": "test-token",
            },
        )
        assert resp.code == 200
        mock_approve.assert_called_once_with([1])

    @patch("compresso.webserver.helpers.approval.approve_tasks")
    @patch(
        "compresso.config.Config",
        return_value=_Settings(
            api_auth_enabled=True,
            api_auth_token=TEST_SERVICE_TOKEN,
            csrf_protection_enabled=True,
        ),
    )
    def test_valid_service_token_does_not_require_browser_csrf(self, _mock_config, mock_approve):
        resp = self.fetch(
            "/compresso/api/v2/approval/approve",
            method="POST",
            body=json.dumps({"id_list": [1]}),
            headers={"Content-Type": "application/json", "X-Compresso-Api-Token": TEST_SERVICE_TOKEN},
        )

        assert resp.code == 200
        mock_approve.assert_called_once_with([1])


class _V1ProbeHandler(V1BaseApiHandler):
    def initialize(self, **kwargs):
        super().initialize(**kwargs)
        self.params = kwargs.get("params", [])

    def get(self, path):
        self.finish({"success": True})


@pytest.mark.unittest
class TestV1ApiGuards(ApiTestBase):
    __test__ = True
    handler_class = _V1ProbeHandler

    def get_app(self):
        return tornado.web.Application([(r"/compresso/api/v1/(.*)", _V1ProbeHandler)])

    @patch(
        "compresso.config.Config",
        return_value=_Settings(api_auth_enabled=True, api_auth_token=TEST_V1_TOKEN),
    )
    def test_v1_rejects_missing_api_token_and_marks_deprecation(self, _mock_config):
        resp = self.fetch("/compresso/api/v1/read")

        assert resp.code == 401
        assert resp.headers["Deprecation"] == "true"
        assert "deprecated" in resp.headers["Warning"].lower()
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    @patch("compresso.config.Config", return_value=_Settings(csrf_protection_enabled=True))
    def test_v1_legacy_mutating_get_requires_csrf_for_browser_auth(self, _mock_config):
        resp = self.fetch("/compresso/api/v1/pending/rescan")

        assert resp.code == 403

    @patch(
        "compresso.config.Config",
        return_value=_Settings(api_auth_enabled=True, api_auth_token=TEST_WORKER_TOKEN, csrf_protection_enabled=True),
    )
    def test_v1_legacy_mutating_get_accepts_explicit_service_token(self, _mock_config):
        resp = self.fetch(
            "/compresso/api/v1/pending/rescan",
            headers={"X-Compresso-Api-Token": TEST_WORKER_TOKEN},
        )

        assert resp.code == 200
        assert resp.headers.get("X-RateLimit-Remaining") is not None
