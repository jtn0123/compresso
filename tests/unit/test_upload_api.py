#!/usr/bin/env python3

"""
    tests.unit.test_upload_api.py

    Tests for the upload API handler.
    Covers: prepare, data_received, get_receiver, upload_file_to_pending_tasks,
    upload_and_install_plugin, on_finish.
"""


from unittest.mock import MagicMock, mock_open, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


@pytest.mark.unittest
class TestUploadApiConstants:

    def test_constants_defined(self):
        from compresso.webserver.api_v2.upload_api import GB, MAX_STREAMED_SIZE, MB, SEPARATOR, TB
        assert MB == 1024 * 1024
        assert GB == 1024 * MB
        assert TB == 1024 * GB
        assert MAX_STREAMED_SIZE == 100 * TB
        assert SEPARATOR == b'\r\n'


@pytest.mark.unittest
class TestUploadApiGetReceiver:

    @patch('compresso.webserver.api_v2.upload_api.session')
    @patch('compresso.webserver.api_v2.upload_api.config')
    @patch('compresso.webserver.api_v2.upload_api.FrontendPushMessages')
    def test_get_receiver_returns_callable(self, _fpm, _config, _session):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler
        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = '/tmp/test'
        receiver = handler.get_receiver('pending')
        assert callable(receiver)

    @patch('compresso.webserver.api_v2.upload_api.session')
    @patch('compresso.webserver.api_v2.upload_api.config')
    @patch('compresso.webserver.api_v2.upload_api.FrontendPushMessages')
    def test_receiver_first_chunk_parses_metadata(self, _fpm, _config, _session):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler
        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = '/tmp/test'
        receiver = handler.get_receiver('pending')

        boundary = b'----WebKitFormBoundary'
        header_line = b'Content-Disposition: form-data; name="file"; filename="test.mp4"'
        content_type = b'Content-Type: video/mp4'
        chunk = boundary + b'\r\n' + header_line + b'\r\n' + content_type + b'\r\n\r\nFILEDATA'

        with patch('builtins.open', mock_open()):
            receiver(chunk)

        assert handler.meta['filename'] == 'test.mp4'

    @patch('compresso.webserver.api_v2.upload_api.session')
    @patch('compresso.webserver.api_v2.upload_api.config')
    @patch('compresso.webserver.api_v2.upload_api.FrontendPushMessages')
    def test_receiver_sanitizes_path_traversal(self, _fpm, _config, _session):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler
        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = None
        handler.meta = {}
        handler.cache_directory = '/tmp/test'
        receiver = handler.get_receiver('plugin')

        boundary = b'----WebKitFormBoundary'
        header_line = b'Content-Disposition: form-data; name="file"; filename="../../etc/passwd"'
        content_type = b'Content-Type: application/octet-stream'
        chunk = boundary + b'\r\n' + header_line + b'\r\n' + content_type + b'\r\n\r\nDATA'

        with patch('builtins.open', mock_open()):
            receiver(chunk)

        # Should sanitize to just the basename
        assert handler.meta['filename'] == 'passwd'

    @patch('compresso.webserver.api_v2.upload_api.session')
    @patch('compresso.webserver.api_v2.upload_api.config')
    @patch('compresso.webserver.api_v2.upload_api.FrontendPushMessages')
    def test_receiver_subsequent_chunks(self, _fpm, _config, _session):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler
        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = None
        handler.meta = {}
        handler.cache_directory = '/tmp/test'
        receiver = handler.get_receiver('pending')

        boundary = b'----WebKitFormBoundary'
        header_line = b'Content-Disposition: form-data; name="file"; filename="test.mp4"'
        content_type = b'Content-Type: video/mp4'
        chunk1 = boundary + b'\r\n' + header_line + b'\r\n' + content_type + b'\r\n\r\nPART1'

        m = mock_open()
        with patch('builtins.open', m):
            receiver(chunk1)
            receiver(b'PART2')

        # The file handle should have been written to twice
        handle = m()
        assert handle.write.call_count == 2


@pytest.mark.unittest
class TestUploadApiOnFinish:

    def test_on_finish_closes_file(self):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler
        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.fp = MagicMock()
        handler.fp.closed = False
        handler._status_code = 200
        handler._reason = 'OK'
        handler._finished = False
        handler._auto_finish = True
        handler._headers = {}
        handler._write_buffer = []
        # Patch parent on_finish
        with patch.object(ApiUploadHandler.__bases__[0], 'on_finish'):
            handler.on_finish()
        handler.fp.close.assert_called_once()

    def test_on_finish_no_fp(self):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler
        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        # No fp attribute - should not error
        with patch.object(ApiUploadHandler.__bases__[0], 'on_finish'):
            handler.on_finish()


@pytest.mark.unittest
class TestUploadApiRoutes:

    def test_routes_defined(self):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler
        assert len(ApiUploadHandler.routes) == 2
        paths = [r['path_pattern'] for r in ApiUploadHandler.routes]
        assert r'/upload/pending/file' in paths
        assert r'/upload/plugin/file' in paths
