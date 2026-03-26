#!/usr/bin/env python3

"""
    tests.unit.test_installation_link.py

    Unit tests for compresso/libs/installation_link.py:
    - RequestHandler authentication
    - Links address formatting, config generation, network locks, remote API calls
    - validate_remote_installation

"""

import time
from unittest.mock import MagicMock, patch

import pytest
import requests
from requests.auth import HTTPBasicAuth

from compresso.libs.installation_link import Links, RequestHandler
from compresso.libs.singleton import SingletonType


class TestRequestHandler:

    @pytest.mark.unittest
    def test_basic_auth(self):
        handler = RequestHandler(auth='basic', username='user', password='pass')
        result = handler._RequestHandler__get_request_auth()
        assert isinstance(result, HTTPBasicAuth)

    @pytest.mark.unittest
    def test_no_auth(self):
        handler = RequestHandler(auth='')
        result = handler._RequestHandler__get_request_auth()
        assert result is None


class TestLinks:

    def setup_method(self):
        SingletonType._instances = {}

    def teardown_method(self):
        SingletonType._instances = {}

    def _create_links(self):
        with patch('compresso.libs.installation_link.config.Config'), \
             patch('compresso.libs.installation_link.session.Session'), \
             patch('compresso.libs.installation_link.CompressoLogging.get_logger'):
            return Links()

    @pytest.mark.unittest
    def test_format_address_adds_http(self):
        links = self._create_links()
        result = links._Links__format_address('192.168.1.5:8888')
        assert result.startswith('http://')

    @pytest.mark.unittest
    def test_format_address_strips_trailing_slash(self):
        links = self._create_links()
        result = links._Links__format_address('http://host:8888/')
        assert result == 'http://host:8888'

    @pytest.mark.unittest
    def test_generate_default_config_keys(self):
        links = self._create_links()
        result = links._Links__generate_default_config({})
        expected_keys = [
            'address', 'auth', 'username', 'password',
            'enable_receiving_tasks', 'enable_sending_tasks',
            'enable_task_preloading', 'preloading_count',
            'enable_checksum_validation', 'enable_config_missing_libraries',
            'enable_distributed_worker_count', 'name', 'version', 'uuid',
            'available', 'task_count', 'last_updated',
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"
        assert len(result) == 17

    @pytest.mark.unittest
    def test_network_transfer_lock_acquire_release(self):
        links = self._create_links()
        lock_key = links.acquire_network_transfer_lock('http://example.com', transfer_limit=1)
        assert isinstance(lock_key, str)
        result = links.release_network_transfer_lock(lock_key)
        assert result is True

    @pytest.mark.unittest
    def test_network_transfer_lock_max_limit(self):
        links = self._create_links()
        keys = []
        for _ in range(5):
            key = links.acquire_network_transfer_lock('http://example.com', transfer_limit=5)
            assert key is not False
            keys.append(key)
        sixth = links.acquire_network_transfer_lock('http://example.com', transfer_limit=5)
        assert sixth is False

    @pytest.mark.unittest
    def test_network_transfer_lock_expiry(self):
        links = self._create_links()
        links._network_transfer_lock = {}
        lock_key = links.acquire_network_transfer_lock('http://expiry.com', transfer_limit=1)
        assert lock_key is not False
        links._network_transfer_lock[lock_key]['expires'] = time.time() - 10
        new_key = links.acquire_network_transfer_lock('http://expiry.com', transfer_limit=1)
        assert new_key is not False

    @pytest.mark.unittest
    def test_remote_api_get_constructs_url(self):
        links = self._create_links()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': 'test'}

        with patch('compresso.libs.installation_link.requests.get', return_value=mock_response) as mock_get:
            config = {'address': '192.168.1.5:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_get(config, '/api/v2/test')
            called_url = mock_get.call_args[0][0]
            assert called_url == 'http://192.168.1.5:8888/api/v2/test'
            assert result == {'data': 'test'}

    @pytest.mark.unittest
    def test_remote_api_post_forwards_body(self):
        links = self._create_links()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch('compresso.libs.installation_link.requests.post', return_value=mock_response) as mock_post:
            config = {'address': '192.168.1.5:8888', 'auth': '', 'username': '', 'password': ''}
            data = {'key': 'value'}
            links.remote_api_post(config, '/api/v2/test', data)
            assert mock_post.call_args[1]['json'] == data

    @pytest.mark.unittest
    def test_validate_remote_installation_success(self):
        links = self._create_links()

        def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            if 'configuration' in url:
                resp.json.return_value = {'configuration': {'key': 'val'}}
            elif 'settings/read' in url:
                resp.json.return_value = {'settings': {'s': 1}}
            elif 'version/read' in url:
                resp.json.return_value = {'version': '1.0'}
            elif 'session/state' in url:
                resp.json.return_value = {'level': 0, 'picture_uri': '', 'name': '', 'email': '', 'uuid': 'u1'}
            return resp

        def mock_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {'recordsTotal': 5}
            return resp

        with patch.object(RequestHandler, 'get', side_effect=mock_get), \
             patch.object(RequestHandler, 'post', side_effect=mock_post):
            result = links.validate_remote_installation('192.168.1.5:8888')
            assert 'system_configuration' in result
            assert 'settings' in result
            assert 'version' in result
            assert 'session' in result
            assert 'task_count' in result

    @pytest.mark.unittest
    def test_validate_remote_installation_timeout(self):
        links = self._create_links()
        with patch.object(RequestHandler, 'get', side_effect=requests.exceptions.Timeout):
            with pytest.raises(requests.exceptions.Timeout):
                links.validate_remote_installation('192.168.1.5:8888')

    @pytest.mark.unittest
    def test_validate_remote_installation_offline(self):
        links = self._create_links()
        with patch.object(RequestHandler, 'get', side_effect=requests.exceptions.ConnectionError):
            with pytest.raises(requests.exceptions.ConnectionError):
                links.validate_remote_installation('192.168.1.5:8888')


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
