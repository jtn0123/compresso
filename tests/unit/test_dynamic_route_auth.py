from unittest.mock import MagicMock, patch

import pytest
import tornado.httpclient
import tornado.testing
import tornado.web
import tornado.websocket

from compresso.webserver.plugins import PluginAPIRequestHandler
from compresso.webserver.proxy import ProxyHandler
from compresso.webserver.request_auth import WEBSOCKET_AUTH_PROTOCOL_PREFIX, encode_websocket_token
from compresso.webserver.websocket import CompressoWebsocketHandler


class _AuthSettings:
    def get_api_auth_enabled(self):
        return True

    def get_api_auth_token(self):
        return "secret"


@pytest.mark.unittest
class TestDynamicRouteAuth(tornado.testing.AsyncHTTPTestCase):
    def runTest(self):
        pass

    def setUp(self):
        self.config_patch = patch("compresso.webserver.request_auth.config.Config", return_value=_AuthSettings())
        self.config_patch.start()
        super().setUp()

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            self.config_patch.stop()

    def get_app(self):
        return tornado.web.Application(
            [
                (r"/proxy/.*", ProxyHandler),
                (r"/compresso/plugin_api/[^/]+(/.*)?", PluginAPIRequestHandler),
            ]
        )

    def test_proxy_rejects_missing_token_before_resolving_target(self):
        with patch("compresso.webserver.proxy.resolve_proxy_target") as resolve:
            response = self.fetch("/proxy/test")

        assert response.code == 401
        resolve.assert_not_called()

    def test_proxy_accepts_configured_token(self):
        with patch("compresso.webserver.proxy.resolve_proxy_target", return_value=None) as resolve:
            response = self.fetch(
                "/proxy/test",
                headers={"X-Compresso-Api-Token": "secret"},
            )

        assert response.code == 400
        resolve.assert_called_once_with(None)

    def test_plugin_api_rejects_missing_token_before_loading_plugin(self):
        with patch("compresso.webserver.plugins.get_plugin_by_path") as get_plugin:
            response = self.fetch("/compresso/plugin_api/example/path")

        assert response.code == 401
        get_plugin.assert_not_called()

    def test_plugin_api_accepts_configured_token(self):
        with patch("compresso.webserver.plugins.get_plugin_by_path", return_value=None):
            response = self.fetch(
                "/compresso/plugin_api/missing/path",
                headers={"X-Compresso-Api-Token": "secret"},
            )

        assert response.code == 404


@pytest.mark.unittest
class TestWebsocketRouteAuth(tornado.testing.AsyncHTTPTestCase):
    def runTest(self):
        pass

    def setUp(self):
        settings = MagicMock()
        settings.get_api_auth_enabled.return_value = True
        settings.get_api_auth_token.return_value = "secret"
        self.config_patch = patch("compresso.config.Config", return_value=settings)
        self.config_patch.start()
        self.queue_patch = patch("compresso.webserver.websocket.CompressoDataQueues")
        queues = self.queue_patch.start()
        queues.return_value.get_compresso_data_queues.return_value = {}
        self.thread_patch = patch("compresso.webserver.websocket.CompressoRunningThreads")
        self.thread_patch.start()
        self.session_patch = patch("compresso.webserver.websocket.session.Session")
        self.session_patch.start()
        super().setUp()

    def tearDown(self):
        try:
            super().tearDown()
        finally:
            self.session_patch.stop()
            self.thread_patch.stop()
            self.queue_patch.stop()
            self.config_patch.stop()

    def get_app(self):
        return tornado.web.Application([(r"/compresso/websocket", CompressoWebsocketHandler)])

    @tornado.testing.gen_test
    async def test_websocket_rejects_missing_token_during_handshake(self):
        request = tornado.httpclient.HTTPRequest(self.get_url("/compresso/websocket").replace("http", "ws", 1))

        with pytest.raises(tornado.httpclient.HTTPClientError) as exc:
            await tornado.websocket.websocket_connect(request)

        assert exc.value.code == 401

    @tornado.testing.gen_test
    async def test_websocket_accepts_encoded_token_protocol(self):
        token_protocol = f"{WEBSOCKET_AUTH_PROTOCOL_PREFIX}{encode_websocket_token('secret')}"
        request = tornado.httpclient.HTTPRequest(
            self.get_url("/compresso/websocket").replace("http", "ws", 1),
            headers={"Sec-WebSocket-Protocol": f"compresso, {token_protocol}"},
        )

        socket = await tornado.websocket.websocket_connect(request)

        assert socket.selected_subprotocol == "compresso"
        socket.close()
