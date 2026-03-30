#!/usr/bin/env python3

"""
tests.unit.test_upload_api_coverage.py

Focused coverage tests for uncovered lines in upload_api.py.

Uncovered lines targeted:
  80-83     - initialize: session, params, config, frontend_messages setup
  86-101    - prepare: bytes_read, meta, receiver, cache_directory setup
  104       - data_received: delegates to self.receiver
  123       - get_receiver: invalid filename raises ValueError
  199-254   - upload_file_to_pending_tasks: success, BaseApiError, Exception paths
  304-339   - upload_and_install_plugin: success, failure, BaseApiError, Exception paths
"""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handler(upload_type="pending", cache_dir=None):
    """Create a partially-initialised ApiUploadHandler for unit tests."""
    from compresso.webserver.api_v2.upload_api import ApiUploadHandler

    handler = ApiUploadHandler.__new__(ApiUploadHandler)
    handler.frontend_messages = MagicMock()
    handler.meta = {}
    handler.cache_directory = cache_dir or "/tmp/compresso_test_upload"
    # Provide a real-ish route dict so route.get('call_method') doesn't blow up
    handler.route = {"call_method": "upload_file_to_pending_tasks"}
    handler.routes = ApiUploadHandler.routes

    # Fake Tornado request/response plumbing so set_status/write_error/write_success work
    handler._status_code = 200
    handler._reason = "OK"
    handler._finished = False
    handler._headers = MagicMock()
    handler._write_buffer = []
    handler.error_messages = {}

    return handler


def _make_chunk(filename="test.mp4", data=b"FILEDATA"):
    """Build a minimal multipart chunk for the receiver."""
    boundary = b"----WebKitFormBoundary"
    header_line = f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode()
    content_type = b"Content-Type: video/mp4"
    return boundary + b"\r\n" + header_line + b"\r\n" + content_type + b"\r\n\r\n" + data


# ---------------------------------------------------------------------------
# initialize (lines 80-83)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUploadApiInitialize:
    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_initialize_sets_session_and_config(self, mock_session, mock_config, mock_fpm):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.initialize(params=["p1"])

        assert handler.session is mock_session.return_value
        assert handler.config is mock_config.return_value
        assert handler.frontend_messages is mock_fpm.return_value
        assert handler.params == ["p1"]

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_initialize_without_params(self, mock_session, mock_config, mock_fpm):
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.initialize()
        assert handler.params is None


# ---------------------------------------------------------------------------
# prepare (lines 86-101)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUploadApiPrepare:
    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_prepare_creates_cache_directory(self, mock_session, mock_config, mock_fpm):
        """prepare() should create the cache directory and set up meta/receiver."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.session = mock_session.return_value
        handler.config = mock_config.return_value
        handler.frontend_messages = mock_fpm.return_value
        handler.cache_directory = None  # force creation

        mock_config.return_value.get_cache_path.return_value = "/tmp/compresso_test"

        fake_conn = MagicMock()
        handler.request = MagicMock()
        handler.request.uri = "/compresso/api/v2/upload/pending/file"
        handler.request.connection = fake_conn

        with patch("os.makedirs") as mock_makedirs, patch("os.path.exists", return_value=False):
            handler.prepare()

        assert handler.bytes_read == 0
        assert isinstance(handler.meta, dict)
        assert callable(handler.receiver)
        mock_makedirs.assert_called_once()

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_prepare_detects_plugin_upload_type(self, mock_session, mock_config, mock_fpm):
        """prepare() should detect 'plugin' upload type from the URI."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.session = mock_session.return_value
        handler.config = mock_config.return_value
        handler.frontend_messages = mock_fpm.return_value
        handler.cache_directory = "/tmp/already_exists"

        handler.request = MagicMock()
        handler.request.uri = "/compresso/api/v2/upload/plugin/file"
        handler.request.connection = MagicMock()

        with patch("os.path.exists", return_value=True):
            handler.prepare()

        assert handler.bytes_read == 0
        assert callable(handler.receiver)

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_prepare_skips_makedirs_if_cache_exists(self, mock_session, mock_config, mock_fpm):
        """prepare() should not call makedirs if cache_directory already set."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.session = mock_session.return_value
        handler.config = mock_config.return_value
        handler.frontend_messages = mock_fpm.return_value
        handler.cache_directory = "/tmp/existing_cache"

        handler.request = MagicMock()
        handler.request.uri = "/compresso/api/v2/upload/pending/file"
        handler.request.connection = MagicMock()

        with patch("os.makedirs") as mock_makedirs:
            handler.prepare()

        mock_makedirs.assert_not_called()


# ---------------------------------------------------------------------------
# data_received (line 104)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUploadApiDataReceived:
    def test_data_received_delegates_to_receiver(self):
        """data_received() calls self.receiver with the chunk."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.receiver = MagicMock()

        handler.data_received(b"some chunk data")
        handler.receiver.assert_called_once_with(b"some chunk data")


# ---------------------------------------------------------------------------
# get_receiver – invalid filename (line 123)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUploadApiReceiverInvalidFilename:
    def test_receiver_raises_on_empty_filename(self):
        """Receiver should raise ValueError when filename is empty after sanitization."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = None
        handler.meta = {}
        handler.cache_directory = "/tmp/test_upload"

        receiver = handler.get_receiver("pending")

        # Build a chunk where the filename field is empty
        boundary = b"----WebKitFormBoundary"
        header_line = b'Content-Disposition: form-data; name="file"; filename=""'
        content_type = b"Content-Type: video/mp4"
        chunk = boundary + b"\r\n" + header_line + b"\r\n" + content_type + b"\r\n\r\nDATA"

        with pytest.raises(ValueError, match="Invalid filename"):
            receiver(chunk)

    def test_receiver_raises_on_dot_filename(self):
        """Receiver should raise ValueError when filename sanitizes to '.'."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = None
        handler.meta = {}
        handler.cache_directory = "/tmp/test_upload"

        receiver = handler.get_receiver("pending")

        boundary = b"----WebKitFormBoundary"
        # A filename of just '.' should be rejected
        header_line = b'Content-Disposition: form-data; name="file"; filename="."'
        content_type = b"Content-Type: video/mp4"
        chunk = boundary + b"\r\n" + header_line + b"\r\n" + content_type + b"\r\n\r\nDATA"

        with pytest.raises(ValueError, match="Invalid filename"):
            receiver(chunk)

    def test_receiver_no_frontend_messages_for_plugin_type(self):
        """Receiver for plugin type does not call frontend_messages even if set."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test_upload"

        receiver = handler.get_receiver("plugin")  # not "pending"

        boundary = b"----WebKitFormBoundary"
        header_line = b'Content-Disposition: form-data; name="file"; filename="plugin.zip"'
        content_type = b"Content-Type: application/zip"
        chunk = boundary + b"\r\n" + header_line + b"\r\n" + content_type + b"\r\n\r\nZIPDATA"

        with patch("builtins.open", mock_open()):
            receiver(chunk)

        # frontend_messages.update should NOT have been called for plugin type
        handler.frontend_messages.update.assert_not_called()


# ---------------------------------------------------------------------------
# upload_file_to_pending_tasks (lines 199-254)
# ---------------------------------------------------------------------------


def _setup_upload_handler_for_post(handler, content_length=100):
    """Configure handler state to simulate having received a file upload."""
    header = b"\r\n----boundary\r\nContent-Disposition: form-data\r\n\r\n"
    boundary = b"\r\n----boundary--\r\n"
    handler.meta = {
        "filename": "test.mp4",
        "header": header,
        "boundary": boundary,
        "content_length": content_length,
    }
    handler.fp = MagicMock()
    handler.fp.closed = False
    handler.request = MagicMock()
    handler.request.headers.get.return_value = str(len(header) + len(boundary) + content_length)


@pytest.mark.unittest
class TestUploadFileToPendingTasks:
    @patch("compresso.webserver.api_v2.upload_api.common.get_file_checksum", return_value="abc123")
    @patch("compresso.webserver.api_v2.upload_api.pending_tasks.add_remote_tasks")
    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_pending_success(self, _sess, _cfg, _fpm, mock_add, mock_checksum):
        """upload_file_to_pending_tasks success path returns 200 (lines 199-241)."""

        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        mock_add.return_value = {
            "id": 1,
            "abspath": "/cache/test.mp4",
            "priority": 0,
            "type": "remote",
            "status": "queued",
        }

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_file_to_pending_tasks"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        wrote = {}

        def fake_write_success(response=None):
            wrote["code"] = 200
            wrote["response"] = response

        def fake_write_error(status_code=None, **kwargs):
            wrote["code"] = status_code or 500

        def fake_set_status(code, reason=None):
            wrote["set_status"] = code

        handler.write_success = fake_write_success
        handler.write_error = fake_write_error
        handler.set_status = fake_set_status
        handler.get_status = MagicMock(return_value=200)
        handler._reason = "OK"
        handler.finish = MagicMock()

        # Run via asyncio since the method is async
        import asyncio

        asyncio.new_event_loop().run_until_complete(handler.upload_file_to_pending_tasks())

        assert wrote.get("code") == 200

    @patch("compresso.webserver.api_v2.upload_api.pending_tasks.add_remote_tasks", return_value=None)
    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_pending_add_remote_returns_none(self, _sess, _cfg, _fpm, mock_add):
        """When add_remote_tasks returns None, write_error is called."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_file_to_pending_tasks"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        wrote = {}

        def fake_write_error(status_code=None, **kwargs):
            wrote["called"] = True

        handler.write_success = MagicMock()
        handler.write_error = fake_write_error
        handler.set_status = MagicMock()
        handler.get_status = MagicMock(return_value=200)
        handler._reason = "OK"
        handler.finish = MagicMock()

        import asyncio

        asyncio.new_event_loop().run_until_complete(handler.upload_file_to_pending_tasks())
        assert wrote.get("called") is True

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_pending_base_api_error(self, _sess, _cfg, _fpm):
        """BaseApiError in upload_file_to_pending_tasks returns 400 (lines 242-248)."""
        from compresso.webserver.api_v2.base_api_handler import BaseApiError
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_file_to_pending_tasks"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        # Make fp.seek raise a BaseApiError
        handler.fp.seek.side_effect = BaseApiError("Bad data")

        wrote = {}

        def fake_set_status(code, reason=None):
            wrote["code"] = code

        def fake_write_error(status_code=None, **kwargs):
            pass

        handler.set_status = fake_set_status
        handler.write_error = fake_write_error
        handler.write_success = MagicMock()
        handler.get_status = MagicMock(return_value=400)
        handler._reason = "Bad data"
        handler.finish = MagicMock()

        import asyncio

        asyncio.new_event_loop().run_until_complete(handler.upload_file_to_pending_tasks())
        assert wrote.get("code") == 400

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_pending_generic_exception(self, _sess, _cfg, _fpm):
        """Generic Exception in upload_file_to_pending_tasks returns 500 (lines 249-254)."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_file_to_pending_tasks"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        handler.fp.seek.side_effect = RuntimeError("disk full")

        wrote = {}

        def fake_set_status(code, reason=None):
            wrote["code"] = code

        handler.set_status = fake_set_status
        handler.write_error = MagicMock()
        handler.write_success = MagicMock()
        handler.get_status = MagicMock(return_value=500)
        handler._reason = "error"
        handler.finish = MagicMock()

        import asyncio

        asyncio.new_event_loop().run_until_complete(handler.upload_file_to_pending_tasks())
        assert wrote.get("code") == 500

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_pending_removes_frontend_msg_on_error(self, _sess, _cfg, _fpm):
        """On error, frontend_messages.remove_item('receivingRemoteFile') is called."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_file_to_pending_tasks"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        handler.fp.seek.side_effect = Exception("boom")

        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.write_success = MagicMock()
        handler.get_status = MagicMock(return_value=500)
        handler._reason = "error"
        handler.finish = MagicMock()

        import asyncio

        asyncio.new_event_loop().run_until_complete(handler.upload_file_to_pending_tasks())
        handler.frontend_messages.remove_item.assert_called_with("receivingRemoteFile")


# ---------------------------------------------------------------------------
# upload_and_install_plugin (lines 304-339)
# ---------------------------------------------------------------------------


@pytest.mark.unittest
class TestUploadAndInstallPlugin:
    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_plugin_success(self, _sess, _cfg, _fpm):
        """upload_and_install_plugin success path returns 200 (lines 304-326)."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_and_install_plugin"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        wrote = {}

        def fake_write_success(response=None):
            wrote["code"] = 200

        handler.write_success = fake_write_success
        handler.write_error = MagicMock()
        handler.set_status = MagicMock()
        handler.get_status = MagicMock(return_value=200)
        handler._reason = "OK"
        handler.finish = MagicMock()

        mock_plugins = MagicMock()
        mock_plugins.install_plugin_from_path_on_disk.return_value = True

        with patch("compresso.webserver.api_v2.upload_api.ApiUploadHandler.upload_and_install_plugin.__module__"):
            pass

        # Patch the PluginsHandler import inside the method
        with patch("compresso.libs.plugins.PluginsHandler", return_value=mock_plugins):
            import asyncio

            asyncio.new_event_loop().run_until_complete(handler.upload_and_install_plugin())

        assert wrote.get("code") == 200

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_plugin_install_failure(self, _sess, _cfg, _fpm):
        """When install_plugin_from_path_on_disk returns False, returns 500 (lines 320-323)."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_and_install_plugin"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        wrote = {}

        def fake_set_status(code, reason=None):
            wrote["code"] = code

        handler.write_success = MagicMock()
        handler.write_error = MagicMock()
        handler.set_status = fake_set_status
        handler.get_status = MagicMock(return_value=500)
        handler._reason = "error"
        handler.finish = MagicMock()

        mock_plugins = MagicMock()
        mock_plugins.install_plugin_from_path_on_disk.return_value = False

        with patch("compresso.libs.plugins.PluginsHandler", return_value=mock_plugins):
            import asyncio

            asyncio.new_event_loop().run_until_complete(handler.upload_and_install_plugin())

        assert wrote.get("code") == 500

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_plugin_base_api_error(self, _sess, _cfg, _fpm):
        """BaseApiError in upload_and_install_plugin returns 400 (lines 327-333)."""
        from compresso.webserver.api_v2.base_api_handler import BaseApiError
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_and_install_plugin"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        # Raise BaseApiError from fp.seek
        handler.fp.seek.side_effect = BaseApiError("Bad upload")

        wrote = {}

        def fake_set_status(code, reason=None):
            wrote["code"] = code

        handler.set_status = fake_set_status
        handler.write_error = MagicMock()
        handler.write_success = MagicMock()
        handler.get_status = MagicMock(return_value=400)
        handler._reason = "error"
        handler.finish = MagicMock()

        import asyncio

        asyncio.new_event_loop().run_until_complete(handler.upload_and_install_plugin())
        assert wrote.get("code") == 400

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_plugin_generic_exception(self, _sess, _cfg, _fpm):
        """Generic Exception in upload_and_install_plugin returns 500 (lines 334-339)."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_and_install_plugin"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        handler.fp.seek.side_effect = OSError("I/O error")

        wrote = {}

        def fake_set_status(code, reason=None):
            wrote["code"] = code

        handler.set_status = fake_set_status
        handler.write_error = MagicMock()
        handler.write_success = MagicMock()
        handler.get_status = MagicMock(return_value=500)
        handler._reason = "error"
        handler.finish = MagicMock()

        import asyncio

        asyncio.new_event_loop().run_until_complete(handler.upload_and_install_plugin())
        assert wrote.get("code") == 500

    @patch("compresso.webserver.api_v2.upload_api.FrontendPushMessages")
    @patch("compresso.webserver.api_v2.upload_api.config.Config")
    @patch("compresso.webserver.api_v2.upload_api.session.Session")
    def test_upload_plugin_removes_frontend_msg_on_exception(self, _sess, _cfg, _fpm):
        """On exception, frontend_messages.remove_item is called (lines 336-337)."""
        from compresso.webserver.api_v2.upload_api import ApiUploadHandler

        handler = ApiUploadHandler.__new__(ApiUploadHandler)
        handler.frontend_messages = MagicMock()
        handler.meta = {}
        handler.cache_directory = "/tmp/test"
        handler.route = {"call_method": "upload_and_install_plugin"}
        handler.routes = ApiUploadHandler.routes
        handler.error_messages = {}
        _setup_upload_handler_for_post(handler)

        handler.fp.seek.side_effect = Exception("crash")

        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.write_success = MagicMock()
        handler.get_status = MagicMock(return_value=500)
        handler._reason = "error"
        handler.finish = MagicMock()

        import asyncio

        asyncio.new_event_loop().run_until_complete(handler.upload_and_install_plugin())
        handler.frontend_messages.remove_item.assert_called_with("receivingRemoteFile")
