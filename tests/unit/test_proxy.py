#!/usr/bin/env python3

"""
tests.unit.test_proxy.py

Unit tests for compresso/webserver/proxy.py:
- resolve_proxy_target address/uuid/name matching
- URL normalization
- Auth header generation

"""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType

REMOTES = [
    {
        "address": "http://192.168.1.10:8888",
        "uuid": "abc-123",
        "name": "server-one",
        "auth": "basic",
        "username": "admin",
        "password": "secret",
        "api_token": "worker-one-token",
    },
    {
        "address": "http://10.0.0.5:8888",
        "uuid": "def-456",
        "name": "server-two",
        "auth": "",
        "username": "",
        "password": "",
    },
]


class TestResolveProxyTarget:
    def setup_method(self):
        SingletonType._instances = {}

    def teardown_method(self):
        SingletonType._instances = {}

    def _patch_and_resolve(self, target_id):
        mock_settings = MagicMock()
        mock_settings.get_remote_installations.return_value = REMOTES
        mock_settings.reload = MagicMock()

        mock_links = MagicMock()
        mock_links.settings = mock_settings

        with patch("compresso.webserver.proxy.Links", return_value=mock_links):
            from compresso.webserver.proxy import resolve_proxy_target

            return resolve_proxy_target(target_id)

    @pytest.mark.unittest
    def test_resolve_by_address(self):
        result = self._patch_and_resolve("http://192.168.1.10:8888")
        assert result is not None
        assert "url_base" in result

    @pytest.mark.unittest
    def test_resolve_by_uuid(self):
        result = self._patch_and_resolve("abc-123")
        assert result is not None

    @pytest.mark.unittest
    def test_resolve_by_name(self):
        result = self._patch_and_resolve("server-one")
        assert result is not None

    @pytest.mark.unittest
    def test_resolve_no_match(self):
        result = self._patch_and_resolve("nonexistent")
        assert result is None

    @pytest.mark.unittest
    def test_resolve_normalizes_url(self):
        result = self._patch_and_resolve("192.168.1.10:8888")
        assert result is not None

    @pytest.mark.unittest
    def test_auth_header_basic(self):
        result = self._patch_and_resolve("http://192.168.1.10:8888")
        assert result is not None
        assert "Authorization" in result["headers"]
        assert result["headers"]["Authorization"].startswith("Basic")
        assert result["headers"]["X-Compresso-Api-Token"] == "worker-one-token"

    @pytest.mark.unittest
    def test_auth_header_none(self):
        result = self._patch_and_resolve("http://10.0.0.5:8888")
        assert result is not None
        assert result["headers"] == {}


@pytest.mark.unittest
class TestProxyHeaderBoundary:
    def test_only_actual_redirect_statuses_are_blocked(self):
        from compresso.webserver.proxy import is_blocked_proxy_redirect

        assert not is_blocked_proxy_redirect(304)
        assert all(is_blocked_proxy_redirect(status) for status in (301, 302, 303, 307, 308))

    def test_request_headers_allow_only_transfer_metadata_and_worker_credentials(self):
        from compresso.webserver.proxy import build_proxy_request_headers

        inbound = {
            "Accept": "application/json",
            "Content-Type": "application/octet-stream",
            "Cache-Control": "no-cache",
            "Range": "bytes=0-99",
            "If-None-Match": '"etag"',
            "X-Transfer-Offset": "0",
            "X-Chunk-Checksum": "sha256:abc",
            "Authorization": "Bearer master-token",
            "X-Compresso-Api-Token": "master-token",
            "Cookie": "session=master-cookie",
            "X-Compresso-CSRF-Token": "master-csrf",
            "Origin": "https://master.example",
            "Referer": "https://master.example/ui",
            "X-Compresso-Target-Installation": "worker-one",
        }
        target_credentials = {
            "Authorization": "Basic d29ya2VyOnNlY3JldA==",
            "X-Compresso-Api-Token": "worker-token",
        }

        result = build_proxy_request_headers(inbound, target_credentials)

        assert result["Accept"] == "application/json"
        assert result["Range"] == "bytes=0-99"
        assert result["X-Transfer-Offset"] == "0"
        assert result["Authorization"] == target_credentials["Authorization"]
        assert result["X-Compresso-Api-Token"] == "worker-token"
        assert "Cookie" not in result
        assert "X-Compresso-CSRF-Token" not in result
        assert "Origin" not in result
        assert "Referer" not in result
        assert "X-Compresso-Target-Installation" not in result
        assert "master-token" not in repr(result)

    def test_response_headers_drop_worker_state_and_security_policy(self):
        from compresso.webserver.proxy import build_proxy_response_headers

        upstream = {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": 'attachment; filename="result.mkv"',
            "Cache-Control": "private",
            "ETag": '"result"',
            "Content-Range": "bytes 0-99/1000",
            "X-Chunk-Checksum": "sha256:abc",
            "Set-Cookie": "worker_session=secret",
            "Location": "https://worker.example/login",
            "WWW-Authenticate": 'Basic realm="worker"',
            "Access-Control-Allow-Origin": "*",
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "default-src *",
        }

        result = build_proxy_response_headers(upstream)

        assert result["Content-Type"] == "application/octet-stream"
        assert result["Content-Range"] == "bytes 0-99/1000"
        assert result["X-Chunk-Checksum"] == "sha256:abc"
        assert "Set-Cookie" not in result
        assert "Location" not in result
        assert "WWW-Authenticate" not in result
        assert "Access-Control-Allow-Origin" not in result
        assert "X-Frame-Options" not in result
        assert "Content-Security-Policy" not in result


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
