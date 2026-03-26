#!/usr/bin/env python3

"""
    tests.unit.test_notifications_api.py

    Unit tests for the notification API endpoints:
    - GET /notifications/channels returns channels with masked URLs
    - POST /notifications/channels/save persists channels
    - POST /notifications/channels/test calls test_channel
    - URL masking logic
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


NOTIF_MOD = 'compresso.webserver.api_v2.notifications_api'


# ------------------------------------------------------------------
# TestMaskUrl
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestMaskUrl:
    """Tests for ApiNotificationsHandler._mask_url() static method."""

    def test_masks_long_https_url(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler
        result = ApiNotificationsHandler._mask_url('https://discord.com/api/webhooks/123456789/abcdefghij')
        assert result.startswith('https://')
        assert result.endswith('***')
        assert len(result) < len('https://discord.com/api/webhooks/123456789/abcdefghij')

    def test_masks_long_http_url(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler
        result = ApiNotificationsHandler._mask_url('http://hooks.slack.com/services/T000/B000/xxxxxxxxxxxxxx')
        assert result.startswith('http://')
        assert result.endswith('***')

    def test_short_url_not_masked(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler
        result = ApiNotificationsHandler._mask_url('https://a.co')
        # URL rest is <= 12 chars, returned as-is
        assert result == 'https://a.co'

    def test_empty_url_returns_empty(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler
        result = ApiNotificationsHandler._mask_url('')
        assert result == ''

    def test_none_url_returns_empty(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler
        result = ApiNotificationsHandler._mask_url(None)
        assert result == ''

    def test_url_without_protocol_masked(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler
        result = ApiNotificationsHandler._mask_url('hooks.slack.com/services/T000/B000/xxx')
        assert result.endswith('***')

    def test_url_without_protocol_short_not_masked(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler
        result = ApiNotificationsHandler._mask_url('short.co')
        assert result == 'short.co'

    def test_preserves_protocol_prefix(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler
        result = ApiNotificationsHandler._mask_url('https://discord.com/api/webhooks/123456789/abcdef')
        assert result.startswith('https://discord.com/')
        # The first 12 chars of "discord.com/..." are shown
        rest_shown = result[len('https://'):]
        # Should show exactly 12 chars + '***'
        assert rest_shown == 'discord.com/***'


# ------------------------------------------------------------------
# TestGetNotificationChannels
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetNotificationChannelsEndpoint:
    """Tests for the GET /notifications/channels handler logic."""

    @pytest.mark.asyncio
    async def test_returns_channels_with_masked_urls(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler

        handler = object.__new__(ApiNotificationsHandler)
        handler.config = MagicMock()
        handler.config.get_notification_channels.return_value = [
            {
                'type': 'discord',
                'name': 'test-discord',
                'url': 'https://discord.com/api/webhooks/123456789/very-long-token-here',
                'triggers': ['task_completed'],
                'enabled': True,
            },
        ]

        written_data = {}

        def mock_write_success(data=None):
            written_data.update(data or {})

        handler.write_success = mock_write_success

        await handler.get_notification_channels()

        assert 'channels' in written_data
        assert len(written_data['channels']) == 1
        ch = written_data['channels'][0]
        assert ch['name'] == 'test-discord'
        assert ch['url'].endswith('***')
        # Original URL should not be in the response
        assert 'very-long-token-here' not in ch['url']

    @pytest.mark.asyncio
    async def test_returns_empty_channels(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler

        handler = object.__new__(ApiNotificationsHandler)
        handler.config = MagicMock()
        handler.config.get_notification_channels.return_value = []

        written_data = {}

        def mock_write_success(data=None):
            written_data.update(data or {})

        handler.write_success = mock_write_success

        await handler.get_notification_channels()

        assert written_data['channels'] == []


# ------------------------------------------------------------------
# TestSaveNotificationChannels
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestSaveNotificationChannelsEndpoint:
    """Tests for the POST /notifications/channels/save handler logic."""

    @pytest.mark.asyncio
    async def test_saves_valid_channels(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler

        handler = object.__new__(ApiNotificationsHandler)
        handler.config = MagicMock()

        channels_payload = [
            {'type': 'discord', 'name': 'ch1', 'url': 'https://discord.com/hook', 'triggers': [], 'enabled': True},
        ]
        handler.request = MagicMock()
        handler.request.body = json.dumps({'channels': channels_payload}).encode()

        handler.write_success = MagicMock()
        handler.set_status = MagicMock()
        handler.write_error = MagicMock()

        await handler.save_notification_channels()

        handler.config.set_config_item.assert_called_once_with('notification_channels', channels_payload)
        handler.write_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_non_list_channels(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler

        handler = object.__new__(ApiNotificationsHandler)
        handler.config = MagicMock()
        handler.request = MagicMock()
        handler.request.body = json.dumps({'channels': 'not_a_list'}).encode()

        handler.write_success = MagicMock()
        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.STATUS_ERROR_EXTERNAL = 400

        await handler.save_notification_channels()

        handler.write_error.assert_called_once()
        handler.write_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler

        handler = object.__new__(ApiNotificationsHandler)
        handler.config = MagicMock()
        handler.request = MagicMock()
        handler.request.body = b'not json'

        handler.write_success = MagicMock()
        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.STATUS_ERROR_EXTERNAL = 400

        await handler.save_notification_channels()

        handler.write_error.assert_called_once()


# ------------------------------------------------------------------
# TestTestNotificationChannel
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestTestNotificationChannelEndpoint:
    """Tests for the POST /notifications/channels/test handler logic."""

    @pytest.mark.asyncio
    async def test_calls_test_channel(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler

        handler = object.__new__(ApiNotificationsHandler)
        channel_config = {'type': 'discord', 'name': 'test', 'url': 'https://discord.com/hook'}
        handler.request = MagicMock()
        handler.request.body = json.dumps({'channel': channel_config}).encode()

        handler.write_success = MagicMock()
        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.STATUS_ERROR_EXTERNAL = 400

        with patch(f'{NOTIF_MOD}.ExternalNotificationDispatcher') as mock_disp_cls:
            mock_dispatcher = MagicMock()
            mock_dispatcher.test_channel.return_value = {'success': True}
            mock_disp_cls.return_value = mock_dispatcher

            await handler.test_notification_channel()

        mock_dispatcher.test_channel.assert_called_once_with(channel_config)
        handler.write_success.assert_called_once_with({'success': True})

    @pytest.mark.asyncio
    async def test_rejects_non_dict_channel(self):
        from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler

        handler = object.__new__(ApiNotificationsHandler)
        handler.request = MagicMock()
        handler.request.body = json.dumps({'channel': 'not_a_dict'}).encode()

        handler.write_success = MagicMock()
        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.STATUS_ERROR_EXTERNAL = 400

        await handler.test_notification_channel()

        handler.write_error.assert_called_once()
        handler.write_success.assert_not_called()


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
