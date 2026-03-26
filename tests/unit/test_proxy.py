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
        'address': 'http://192.168.1.10:8888',
        'uuid': 'abc-123',
        'name': 'server-one',
        'auth': 'basic',
        'username': 'admin',
        'password': 'secret',
    },
    {
        'address': 'http://10.0.0.5:8888',
        'uuid': 'def-456',
        'name': 'server-two',
        'auth': '',
        'username': '',
        'password': '',
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

        with patch('compresso.webserver.proxy.Links', return_value=mock_links):
            from compresso.webserver.proxy import resolve_proxy_target
            return resolve_proxy_target(target_id)

    @pytest.mark.unittest
    def test_resolve_by_address(self):
        result = self._patch_and_resolve('http://192.168.1.10:8888')
        assert result is not None
        assert 'url_base' in result

    @pytest.mark.unittest
    def test_resolve_by_uuid(self):
        result = self._patch_and_resolve('abc-123')
        assert result is not None

    @pytest.mark.unittest
    def test_resolve_by_name(self):
        result = self._patch_and_resolve('server-one')
        assert result is not None

    @pytest.mark.unittest
    def test_resolve_no_match(self):
        result = self._patch_and_resolve('nonexistent')
        assert result is None

    @pytest.mark.unittest
    def test_resolve_normalizes_url(self):
        result = self._patch_and_resolve('192.168.1.10:8888')
        assert result is not None

    @pytest.mark.unittest
    def test_auth_header_basic(self):
        result = self._patch_and_resolve('http://192.168.1.10:8888')
        assert result is not None
        assert 'Authorization' in result['headers']
        assert result['headers']['Authorization'].startswith('Basic')

    @pytest.mark.unittest
    def test_auth_header_none(self):
        result = self._patch_and_resolve('http://10.0.0.5:8888')
        assert result is not None
        assert result['headers'] == {}


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
