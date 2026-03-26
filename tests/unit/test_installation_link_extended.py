#!/usr/bin/env python3

"""
    tests.unit.test_installation_link_extended.py

    Extended unit tests for compresso/libs/installation_link.py.
    Does NOT duplicate tests in test_installation_link.py.

    Covers:
    - RequestHandler: __init__ with auth types, get/post/delete delegation, __get_request_auth
    - Links: __format_address edge cases, __generate_default_config defaults,
      acquire/release_network_transfer_lock mechanics,
      remote_api_get/post/delete error handling,
      remote_api_post_file, remote_api_get_download,
      validate_remote_installation flow
"""

import time
from unittest.mock import MagicMock, mock_open, patch

import pytest
from requests.auth import HTTPBasicAuth

from compresso.libs.installation_link import Links, RequestHandler
from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _create_links():
    with patch('compresso.libs.installation_link.config.Config'), \
         patch('compresso.libs.installation_link.session.Session'), \
         patch('compresso.libs.installation_link.CompressoLogging.get_logger'):
        return Links()


# ==================================================================
# RequestHandler
# ==================================================================

@pytest.mark.unittest
class TestRequestHandlerInit:

    def test_defaults_to_empty_strings(self):
        handler = RequestHandler()
        assert handler.auth == ''
        assert handler.username == ''
        assert handler.password == ''

    def test_basic_auth_type(self):
        handler = RequestHandler(auth='basic', username='admin', password='secret')  # noqa: S106 — test fixture
        assert handler.auth == 'basic'
        assert handler.username == 'admin'
        assert handler.password == 'secret'  # noqa: S105 — test fixture

    def test_none_username_defaults_to_empty(self):
        handler = RequestHandler(auth='basic', username=None, password='pw')  # noqa: S106 — test fixture
        assert handler.username == ''

    def test_none_password_defaults_to_empty(self):
        handler = RequestHandler(auth='basic', username='u', password=None)
        assert handler.password == ''


@pytest.mark.unittest
class TestRequestHandlerAuth:

    def test_basic_auth_returns_httpbasicauth(self):
        handler = RequestHandler(auth='basic', username='u', password='p')  # noqa: S106 — test fixture
        auth = handler._RequestHandler__get_request_auth()
        assert isinstance(auth, HTTPBasicAuth)
        assert auth.username == 'u'
        assert auth.password == 'p'  # noqa: S105 — test fixture

    def test_no_auth_returns_none(self):
        handler = RequestHandler(auth='')
        assert handler._RequestHandler__get_request_auth() is None

    def test_none_auth_returns_none(self):
        handler = RequestHandler()
        assert handler._RequestHandler__get_request_auth() is None

    def test_case_insensitive_basic(self):
        handler = RequestHandler(auth='Basic', username='u', password='p')  # noqa: S106 — test fixture
        auth = handler._RequestHandler__get_request_auth()
        assert isinstance(auth, HTTPBasicAuth)


@pytest.mark.unittest
class TestRequestHandlerMethods:

    @patch('compresso.libs.installation_link.requests.get')
    def test_get_passes_auth_and_kwargs(self, mock_get):
        handler = RequestHandler(auth='basic', username='u', password='p')  # noqa: S106 — test fixture
        handler.get('http://example.com', timeout=5)
        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        assert args[0] == 'http://example.com'
        assert isinstance(kwargs['auth'], HTTPBasicAuth)
        assert kwargs['timeout'] == 5

    @patch('compresso.libs.installation_link.requests.post')
    def test_post_passes_auth(self, mock_post):
        handler = RequestHandler(auth='')
        handler.post('http://example.com', json={'key': 'val'})
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs['auth'] is None
        assert kwargs['json'] == {'key': 'val'}

    @patch('compresso.libs.installation_link.requests.delete')
    def test_delete_passes_auth(self, mock_delete):
        handler = RequestHandler(auth='basic', username='a', password='b')  # noqa: S106 — test fixture
        handler.delete('http://example.com/item')
        mock_delete.assert_called_once()
        args, kwargs = mock_delete.call_args
        assert isinstance(kwargs['auth'], HTTPBasicAuth)


# ==================================================================
# Links.__format_address edge cases
# ==================================================================

@pytest.mark.unittest
class TestFormatAddressExtended:

    def test_strips_whitespace(self):
        links = _create_links()
        result = links._Links__format_address('  192.168.1.1:8888  ')
        assert result == 'http://192.168.1.1:8888'

    def test_preserves_https(self):
        links = _create_links()
        result = links._Links__format_address('https://secure.host:443/')
        assert result == 'https://secure.host:443'

    def test_strips_multiple_trailing_slashes(self):
        links = _create_links()
        result = links._Links__format_address('http://host:8888///')
        assert result == 'http://host:8888'

    def test_case_insensitive_http_check(self):
        links = _create_links()
        result = links._Links__format_address('HTTP://HOST:8888')
        assert result == 'HTTP://HOST:8888'


# ==================================================================
# Links.__generate_default_config
# ==================================================================

@pytest.mark.unittest
class TestGenerateDefaultConfigExtended:

    def test_uses_provided_values(self):
        links = _create_links()
        config = links._Links__generate_default_config({
            'address': '10.0.0.1:8888',
            'auth': 'basic',
            'username': 'admin',
            'name': 'MyServer',
        })
        assert config['address'] == '10.0.0.1:8888'
        assert config['auth'] == 'basic'
        assert config['username'] == 'admin'
        assert config['name'] == 'MyServer'

    def test_defaults_for_missing_keys(self):
        links = _create_links()
        config = links._Links__generate_default_config({})
        assert config['address'] == '???'
        assert config['auth'] == 'None'
        assert config['username'] == ''
        assert config['password'] == ''
        assert config['enable_receiving_tasks'] is False
        assert config['enable_sending_tasks'] is False
        assert config['enable_task_preloading'] is True
        assert config['preloading_count'] == 2
        assert config['name'] == '???'
        assert config['version'] == '???'
        assert config['uuid'] == '???'
        assert config['available'] is False
        assert config['task_count'] == 0

    def test_last_updated_is_set(self):
        links = _create_links()
        before = time.time()
        config = links._Links__generate_default_config({})
        after = time.time()
        assert before <= config['last_updated'] <= after


# ==================================================================
# Links.acquire_network_transfer_lock / release_network_transfer_lock
# ==================================================================

@pytest.mark.unittest
class TestNetworkTransferLockExtended:

    def test_lock_key_includes_type_and_url(self):
        links = _create_links()
        key = links.acquire_network_transfer_lock('http://host', transfer_limit=1, lock_type='download')
        assert key is not False
        assert 'download' in key
        assert 'http://host' in key

    def test_transfer_limit_capped_at_5(self):
        links = _create_links()
        links._network_transfer_lock = {}
        keys = []
        for _ in range(10):
            key = links.acquire_network_transfer_lock('http://host', transfer_limit=10, lock_type='send')
            if key is not False:
                keys.append(key)
        # Should be capped at 5
        assert len(keys) == 5

    def test_release_clears_lock(self):
        links = _create_links()
        links._network_transfer_lock = {}
        key = links.acquire_network_transfer_lock('http://host', transfer_limit=1)
        assert key is not False
        # Lock is held, next acquire should fail
        assert links.acquire_network_transfer_lock('http://host', transfer_limit=1) is False
        # Release it
        links.release_network_transfer_lock(key)
        # Now should succeed
        new_key = links.acquire_network_transfer_lock('http://host', transfer_limit=1)
        assert new_key is not False

    def test_expired_locks_are_reused(self):
        links = _create_links()
        links._network_transfer_lock = {}
        key = links.acquire_network_transfer_lock('http://host', transfer_limit=1)
        # Manually expire the lock
        links._network_transfer_lock[key]['expires'] = time.time() - 10
        # Should be able to acquire again
        new_key = links.acquire_network_transfer_lock('http://host', transfer_limit=1)
        assert new_key is not False


# ==================================================================
# Links.remote_api_get / remote_api_post / remote_api_delete
# ==================================================================

@pytest.mark.unittest
class TestRemoteApiGetExtended:

    def test_returns_empty_dict_on_non_200_non_error_status(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 302
        with patch('compresso.libs.installation_link.requests.get', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_get(config, '/api/test')
            assert result == {}

    def test_logs_error_on_400_status(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {'error': 'bad request', 'traceback': []}
        with patch('compresso.libs.installation_link.requests.get', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_get(config, '/api/test')
            assert result == {}

    def test_returns_json_on_200(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'result': 'ok'}
        with patch('compresso.libs.installation_link.requests.get', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_get(config, '/api/test')
            assert result == {'result': 'ok'}


@pytest.mark.unittest
class TestRemoteApiPostExtended:

    def test_returns_json_on_200(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'created': True}
        with patch('compresso.libs.installation_link.requests.post', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_post(config, '/api/create', {'name': 'test'})
            assert result == {'created': True}

    def test_returns_error_json_on_500(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {'error': 'internal', 'traceback': []}
        with patch('compresso.libs.installation_link.requests.post', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_post(config, '/api/create', {})
            assert result == {'error': 'internal', 'traceback': []}

    def test_returns_empty_dict_on_non_error_non_200(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 301
        with patch('compresso.libs.installation_link.requests.post', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_post(config, '/api/test', {})
            assert result == {}


@pytest.mark.unittest
class TestRemoteApiDeleteExtended:

    def test_returns_json_on_200(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'deleted': True}
        with patch('compresso.libs.installation_link.requests.delete', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_delete(config, '/api/item', {'id': 1})
            assert result == {'deleted': True}

    def test_returns_empty_dict_on_404(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {'error': 'not found', 'traceback': []}
        with patch('compresso.libs.installation_link.requests.delete', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_delete(config, '/api/item', {'id': 1})
            assert result == {}


# ==================================================================
# Links.remote_api_post_file
# ==================================================================

@pytest.mark.unittest
class TestRemoteApiPostFile:

    @patch('compresso.libs.installation_link.MultipartEncoder')
    @patch('compresso.libs.installation_link.requests.post')
    @patch('builtins.open', mock_open(read_data=b'filedata'))
    def test_returns_json_on_success(self, mock_post, mock_encoder):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {'uploaded': True}
        mock_post.return_value = mock_resp
        mock_enc_instance = MagicMock()
        mock_enc_instance.content_type = 'multipart/form-data'
        mock_encoder.return_value = mock_enc_instance
        config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
        result = links.remote_api_post_file(config, '/api/upload', '/tmp/file.dat')
        assert result == {'uploaded': True}

    @patch('compresso.libs.installation_link.MultipartEncoder')
    @patch('compresso.libs.installation_link.requests.post')
    @patch('builtins.open', mock_open(read_data=b'filedata'))
    def test_returns_empty_dict_on_failure(self, mock_post, mock_encoder):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {'error': 'fail', 'traceback': []}
        mock_post.return_value = mock_resp
        mock_enc_instance = MagicMock()
        mock_enc_instance.content_type = 'multipart/form-data'
        mock_encoder.return_value = mock_enc_instance
        config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
        result = links.remote_api_post_file(config, '/api/upload', '/tmp/file.dat')
        assert result == {}


# ==================================================================
# Links.remote_api_get_download
# ==================================================================

@pytest.mark.unittest
class TestRemoteApiGetDownload:

    @patch('builtins.open', mock_open())
    @patch('compresso.libs.installation_link.requests.get')
    def test_downloads_file_to_path(self, mock_get):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.raise_for_status = MagicMock()
        mock_resp.iter_content.return_value = [b'chunk1', b'chunk2']

        # Use RequestHandler.get instead of requests.get directly
        with patch.object(RequestHandler, 'get', return_value=mock_resp):
            config = {'address': 'host:8888', 'auth': '', 'username': '', 'password': ''}
            result = links.remote_api_get_download(config, '/api/download/file', '/tmp/output.dat')
            assert result is True


# ==================================================================
# Links.validate_remote_installation - extended scenarios
# ==================================================================

@pytest.mark.unittest
class TestValidateRemoteInstallationExtended:

    def test_returns_empty_dict_on_config_non_200(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch.object(RequestHandler, 'get', return_value=mock_resp):
            result = links.validate_remote_installation('192.168.1.5:8888')
            assert result == {}

    def test_returns_empty_dict_on_settings_non_200(self):
        links = _create_links()
        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] == 1:
                # configuration - success
                resp.status_code = 200
                resp.json.return_value = {'configuration': {}}
            else:
                # settings - fail
                resp.status_code = 503
            return resp

        with patch.object(RequestHandler, 'get', side_effect=mock_get):
            result = links.validate_remote_installation('192.168.1.5:8888')
            assert result == {}

    def test_returns_empty_dict_on_version_non_200(self):
        links = _create_links()
        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] <= 2:
                resp.status_code = 200
                if call_count[0] == 1:
                    resp.json.return_value = {'configuration': {}}
                else:
                    resp.json.return_value = {'settings': {}}
            else:
                resp.status_code = 500
                resp.json.return_value = {'error': 'err', 'traceback': []}
            return resp

        with patch.object(RequestHandler, 'get', side_effect=mock_get):
            result = links.validate_remote_installation('192.168.1.5:8888')
            assert result == {}

    def test_returns_empty_dict_on_session_non_200(self):
        links = _create_links()
        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if call_count[0] <= 3:
                resp.status_code = 200
                if call_count[0] == 1:
                    resp.json.return_value = {'configuration': {}}
                elif call_count[0] == 2:
                    resp.json.return_value = {'settings': {}}
                else:
                    resp.json.return_value = {'version': '2.0'}
            else:
                resp.status_code = 403
            return resp

        with patch.object(RequestHandler, 'get', side_effect=mock_get):
            result = links.validate_remote_installation('192.168.1.5:8888')
            assert result == {}

    def test_returns_empty_dict_on_tasks_post_non_200(self):
        links = _create_links()
        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.status_code = 200
            if call_count[0] == 1:
                resp.json.return_value = {'configuration': {}}
            elif call_count[0] == 2:
                resp.json.return_value = {'settings': {}}
            elif call_count[0] == 3:
                resp.json.return_value = {'version': '2.0'}
            else:
                resp.json.return_value = {'level': 0, 'picture_uri': '', 'name': '', 'email': '', 'uuid': 'u1'}
            return resp

        def mock_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 500
            resp.json.return_value = {'error': 'err', 'traceback': []}
            return resp

        with patch.object(RequestHandler, 'get', side_effect=mock_get), \
             patch.object(RequestHandler, 'post', side_effect=mock_post):
            result = links.validate_remote_installation('192.168.1.5:8888')
            assert result == {}

    def test_returns_full_result_on_all_success(self):
        links = _create_links()
        call_count = [0]

        def mock_get(url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            resp.status_code = 200
            if call_count[0] == 1:
                resp.json.return_value = {'configuration': {'key': 'val'}}
            elif call_count[0] == 2:
                resp.json.return_value = {'settings': {'s1': 1}}
            elif call_count[0] == 3:
                resp.json.return_value = {'version': '2.0.0'}
            else:
                resp.json.return_value = {'level': 1, 'picture_uri': '/img', 'name': 'Admin', 'email': 'a@b.c', 'uuid': 'u-1'}
            return resp

        def mock_post(url, **kwargs):
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {'recordsTotal': 42}
            return resp

        with patch.object(RequestHandler, 'get', side_effect=mock_get), \
             patch.object(RequestHandler, 'post', side_effect=mock_post):
            result = links.validate_remote_installation('192.168.1.5:8888')
            assert result['system_configuration'] == {'key': 'val'}
            assert result['settings'] == {'s1': 1}
            assert result['version'] == '2.0.0'
            assert result['session']['name'] == 'Admin'
            assert result['session']['uuid'] == 'u-1'
            assert result['task_count'] == 42

    def test_formats_address_in_requests(self):
        links = _create_links()
        urls_called = []

        def mock_get(url, **kwargs):
            urls_called.append(url)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {
                'configuration': {}, 'settings': {}, 'version': '',
                'level': 0, 'picture_uri': '', 'name': '', 'email': '', 'uuid': '',
            }
            return resp

        def mock_post(url, **kwargs):
            urls_called.append(url)
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {'recordsTotal': 0}
            return resp

        with patch.object(RequestHandler, 'get', side_effect=mock_get), \
             patch.object(RequestHandler, 'post', side_effect=mock_post):
            links.validate_remote_installation('192.168.1.5:8888/')
            # All URLs should have http:// prefix and no trailing slash on the base
            for url in urls_called:
                assert url.startswith('http://192.168.1.5:8888/compresso/')


# ==================================================================
# Links.within_enabled_link_limits
# ==================================================================

@pytest.mark.unittest
class TestWithinEnabledLinkLimits:

    def test_always_returns_true(self):
        links = _create_links()
        assert links.within_enabled_link_limits() is True


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
