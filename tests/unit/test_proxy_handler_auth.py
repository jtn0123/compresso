#!/usr/bin/env python3

"""Security-boundary tests for proxied API requests."""

from unittest.mock import patch

import pytest
import tornado.testing
import tornado.web

from compresso.webserver.proxy import ProxyHandler


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


@pytest.mark.unittest
class TestProxyHandlerAuth(tornado.testing.AsyncHTTPTestCase):
    def runTest(self):
        pass

    def get_app(self):
        return tornado.web.Application([(r"/compresso/api/v2/.*", ProxyHandler)])

    @patch("compresso.webserver.proxy.resolve_proxy_target", return_value=None)
    @patch(
        "compresso.config.Config",
        return_value=_Settings(api_auth_enabled=True, api_auth_token="secret"),  # noqa: S106
    )
    def test_mutation_rejects_missing_api_token_before_proxy_resolution(self, _mock_config, mock_resolve):
        response = self.fetch(
            "/compresso/api/v2/approval/approve",
            method="POST",
            body="{}",
            headers={"Content-Type": "application/json", "X-Compresso-Target-Installation": "remote"},
        )

        assert response.code == 401
        mock_resolve.assert_not_called()

    @patch("compresso.webserver.proxy.resolve_proxy_target", return_value=None)
    @patch("compresso.config.Config", return_value=_Settings(csrf_protection_enabled=True))
    def test_mutation_rejects_missing_csrf_header_before_proxy_resolution(self, _mock_config, mock_resolve):
        response = self.fetch(
            "/compresso/api/v2/approval/reject",
            method="POST",
            body="{}",
            headers={"Content-Type": "application/json", "X-Compresso-Target-Installation": "remote"},
        )

        assert response.code == 403
        mock_resolve.assert_not_called()

    @patch("compresso.webserver.proxy.resolve_proxy_target", return_value=None)
    @patch(
        "compresso.config.Config",
        return_value=_Settings(api_auth_enabled=True, api_auth_token="secret"),  # noqa: S106
    )
    def test_valid_api_token_reaches_proxy_resolution(self, _mock_config, mock_resolve):
        response = self.fetch(
            "/compresso/api/v2/approval/approve",
            method="POST",
            body="{}",
            headers={
                "Content-Type": "application/json",
                "X-Compresso-Api-Token": "secret",
                "X-Compresso-Target-Installation": "remote",
            },
        )

        assert response.code == 400
        mock_resolve.assert_called_once_with("remote")

    @patch("compresso.webserver.proxy.resolve_proxy_target", return_value=None)
    @patch("compresso.webserver.api_v2.rate_limiter.get_rate_limiter")
    @patch("compresso.config.Config", return_value=_Settings())
    def test_rate_limit_runs_before_proxy_resolution(self, _mock_config, mock_limiter, mock_resolve):
        mock_limiter.return_value.check_rate_limit.return_value = (False, 0, 30)

        response = self.fetch(
            "/compresso/api/v2/system/status",
            headers={"X-Compresso-Target-Installation": "remote"},
        )

        assert response.code == 429
        mock_resolve.assert_not_called()
