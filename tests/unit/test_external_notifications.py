#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_external_notifications.py

    Unit tests for compresso.libs.external_notifications.ExternalNotificationDispatcher.
"""

import pytest
from unittest.mock import patch, MagicMock

from compresso.libs.singleton import SingletonType


def _fresh_dispatcher():
    """Get a fresh ExternalNotificationDispatcher by clearing its singleton cache entry."""
    from compresso.libs.external_notifications import ExternalNotificationDispatcher
    SingletonType._instances.pop(ExternalNotificationDispatcher, None)
    return ExternalNotificationDispatcher()


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_channel(channel_type='discord', name='test-channel', url='https://discord.com/api/webhooks/123/abc',
                  triggers=None, enabled=True, headers=None):
    ch = {
        'type': channel_type,
        'name': name,
        'url': url,
        'triggers': triggers or ['task_completed', 'task_failed'],
        'enabled': enabled,
    }
    if headers:
        ch['headers'] = headers
    return ch


def _task_completed_context():
    return {
        'file_name': 'movie.mp4',
        'codec': 'hevc',
        'size_saved': '200 MB (35%)',
        'quality_scores': {'vmaf': 92.5, 'ssim': 0.97},
        'message': 'Encoding completed successfully.',
    }


# ------------------------------------------------------------------
# Discord embed format
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestDiscordEmbed:

    @patch('compresso.libs.external_notifications.requests.post')
    def test_discord_embed_has_correct_structure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='discord')
        context = _task_completed_context()

        dispatcher._send_discord(channel, 'task_completed', context)

        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        payload = kwargs.get('json') or _args[1] if len(_args) > 1 else kwargs['json']
        assert 'embeds' in payload
        embed = payload['embeds'][0]
        assert embed['title'] == 'Task Completed'
        assert embed['color'] == 0x1A6B4A
        assert 'timestamp' in embed
        assert 'fields' in embed

    @patch('compresso.libs.external_notifications.requests.post')
    def test_discord_embed_fields_contain_context(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='discord')
        context = _task_completed_context()

        dispatcher._send_discord(channel, 'task_completed', context)

        payload = mock_post.call_args[1]['json']
        embed = payload['embeds'][0]
        field_names = [f['name'] for f in embed['fields']]
        assert 'File' in field_names
        assert 'Codec' in field_names
        assert 'Size Saved' in field_names
        assert 'Quality' in field_names

    @patch('compresso.libs.external_notifications.requests.post')
    def test_discord_embed_color_for_failed(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='discord')

        dispatcher._send_discord(channel, 'task_failed', {'message': 'error occurred'})

        payload = mock_post.call_args[1]['json']
        assert payload['embeds'][0]['color'] == 0xFF4444

    @patch('compresso.libs.external_notifications.requests.post')
    def test_discord_timeout_is_ten_seconds(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='discord')

        dispatcher._send_discord(channel, 'task_completed', {})

        assert mock_post.call_args[1]['timeout'] == 10


# ------------------------------------------------------------------
# Slack blocks format
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestSlackBlocks:

    @patch('compresso.libs.external_notifications.requests.post')
    def test_slack_payload_has_blocks(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='slack', url='https://hooks.slack.com/services/T00/B00/xxx')
        context = _task_completed_context()

        dispatcher._send_slack(channel, 'task_completed', context)

        mock_post.assert_called_once()
        payload = mock_post.call_args[1]['json']
        assert 'blocks' in payload
        blocks = payload['blocks']
        # First block is header
        assert blocks[0]['type'] == 'header'
        assert blocks[0]['text']['text'] == 'Task Completed'

    @patch('compresso.libs.external_notifications.requests.post')
    def test_slack_blocks_contain_section_with_details(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='slack', url='https://hooks.slack.com/services/T00/B00/xxx')
        context = _task_completed_context()

        dispatcher._send_slack(channel, 'task_completed', context)

        payload = mock_post.call_args[1]['json']
        blocks = payload['blocks']
        section_blocks = [b for b in blocks if b['type'] == 'section']
        assert len(section_blocks) >= 1
        text = section_blocks[0]['text']['text']
        assert '*File:* movie.mp4' in text
        assert '*Codec:* hevc' in text

    @patch('compresso.libs.external_notifications.requests.post')
    def test_slack_blocks_have_context_footer(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='slack', url='https://hooks.slack.com/services/T00/B00/xxx')

        dispatcher._send_slack(channel, 'queue_empty', {})

        payload = mock_post.call_args[1]['json']
        blocks = payload['blocks']
        context_blocks = [b for b in blocks if b['type'] == 'context']
        assert len(context_blocks) == 1
        assert 'Compresso' in context_blocks[0]['elements'][0]['text']

    @patch('compresso.libs.external_notifications.requests.post')
    def test_slack_timeout_is_ten_seconds(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='slack', url='https://hooks.slack.com/services/T00/B00/xxx')

        dispatcher._send_slack(channel, 'task_completed', {})

        assert mock_post.call_args[1]['timeout'] == 10


# ------------------------------------------------------------------
# Webhook generic payload
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestWebhookGeneric:

    @patch('compresso.libs.external_notifications.requests.post')
    def test_webhook_payload_structure(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='webhook', url='https://example.com/hook')
        context = _task_completed_context()

        dispatcher._send_webhook(channel, 'task_completed', context)

        mock_post.assert_called_once()
        payload = mock_post.call_args[1]['json']
        assert payload['event'] == 'task_completed'
        assert payload['title'] == 'Task Completed'
        assert 'timestamp' in payload
        assert payload['context'] == context

    @patch('compresso.libs.external_notifications.requests.post')
    def test_webhook_sends_custom_headers(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        custom_headers = {'X-Api-Key': 'secret123', 'X-Custom': 'value'}
        channel = _make_channel(channel_type='webhook', url='https://example.com/hook',
                                headers=custom_headers)

        dispatcher._send_webhook(channel, 'task_completed', {})

        sent_headers = mock_post.call_args[1]['headers']
        assert sent_headers['X-Api-Key'] == 'secret123'
        assert sent_headers['X-Custom'] == 'value'
        assert sent_headers['Content-Type'] == 'application/json'

    @patch('compresso.libs.external_notifications.requests.post')
    def test_webhook_timeout_is_ten_seconds(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='webhook', url='https://example.com/hook')

        dispatcher._send_webhook(channel, 'task_completed', {})

        assert mock_post.call_args[1]['timeout'] == 10


# ------------------------------------------------------------------
# Trigger filtering
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestTriggerFiltering:

    @patch('compresso.libs.external_notifications.requests.post')
    @patch('compresso.libs.external_notifications.ExternalNotificationDispatcher._get_channels_for_event')
    def test_dispatch_only_sends_to_matching_channels(self, mock_get_channels, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        discord_ch = _make_channel(channel_type='discord', name='discord-ch',
                                   triggers=['task_completed'])
        _make_channel(channel_type='slack', name='slack-ch',
                      url='https://hooks.slack.com/services/T00/B00/xxx',
                      triggers=['task_failed'])
        mock_get_channels.return_value = [discord_ch]

        dispatcher = _fresh_dispatcher()
        dispatcher.dispatch('task_completed', {'file_name': 'test.mp4'})

        # Wait for thread pool to finish
        dispatcher._executor.shutdown(wait=True)
        # Only discord should have been sent
        assert mock_post.call_count == 1
        sent_url = mock_post.call_args[0][0]
        assert 'discord.com' in sent_url

    def test_get_channels_for_event_filters_by_trigger(self):
        dispatcher = _fresh_dispatcher()
        channels = [
            _make_channel(name='a', triggers=['task_completed', 'task_failed']),
            _make_channel(name='b', triggers=['queue_empty']),
            _make_channel(name='c', triggers=['task_completed']),
        ]
        with patch('compresso.libs.external_notifications.ExternalNotificationDispatcher._get_channels_for_event',
                   wraps=dispatcher._get_channels_for_event):
            with patch('compresso.config.Config') as MockConfig:
                instance = MockConfig.return_value
                instance.get_notification_channels.return_value = channels
                result = dispatcher._get_channels_for_event('task_completed')

        assert len(result) == 2
        names = [ch['name'] for ch in result]
        assert 'a' in names
        assert 'c' in names
        assert 'b' not in names

    def test_get_channels_for_event_skips_disabled(self):
        dispatcher = _fresh_dispatcher()
        channels = [
            _make_channel(name='enabled', triggers=['task_completed'], enabled=True),
            _make_channel(name='disabled', triggers=['task_completed'], enabled=False),
        ]
        with patch('compresso.config.Config') as MockConfig:
            instance = MockConfig.return_value
            instance.get_notification_channels.return_value = channels
            result = dispatcher._get_channels_for_event('task_completed')

        assert len(result) == 1
        assert result[0]['name'] == 'enabled'

    @patch('compresso.libs.external_notifications.requests.post')
    def test_dispatch_ignores_unknown_event_type(self, mock_post):
        dispatcher = _fresh_dispatcher()
        dispatcher.dispatch('nonexistent_event', {})
        dispatcher._executor.shutdown(wait=True)
        mock_post.assert_not_called()


# ------------------------------------------------------------------
# Error handling
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestErrorHandling:

    @patch('compresso.libs.external_notifications.requests.post')
    def test_failed_send_does_not_raise(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='discord')

        # This should not raise
        dispatcher._send_to_channel(channel, 'task_completed', {})

    @patch('compresso.libs.external_notifications.requests.post')
    def test_http_error_status_logs_warning_but_no_raise(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='discord')

        # Should not raise despite 500 status
        dispatcher._send_discord(channel, 'task_completed', {})

    @patch('compresso.libs.external_notifications.requests.post')
    def test_unknown_channel_type_does_not_raise(self, mock_post):
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='unknown_type')

        # Should log warning but not raise
        dispatcher._send_to_channel(channel, 'task_completed', {})
        mock_post.assert_not_called()

    @patch('compresso.libs.external_notifications.requests.post')
    @patch('compresso.libs.external_notifications.ExternalNotificationDispatcher._get_channels_for_event')
    def test_dispatch_continues_after_channel_failure(self, mock_get_channels, mock_post):
        """If one channel fails, the other should still be attempted."""
        call_count = {'value': 0}

        def side_effect(*args, **kwargs):
            call_count['value'] += 1
            if call_count['value'] == 1:
                raise Exception("First channel failed")
            return MagicMock(status_code=200)

        mock_post.side_effect = side_effect

        discord_ch = _make_channel(channel_type='discord', name='ch1')
        webhook_ch = _make_channel(channel_type='webhook', name='ch2', url='https://example.com/hook')
        mock_get_channels.return_value = [discord_ch, webhook_ch]

        dispatcher = _fresh_dispatcher()
        dispatcher.dispatch('task_completed', {})
        dispatcher._executor.shutdown(wait=True)

        assert mock_post.call_count == 2


# ------------------------------------------------------------------
# test_channel
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestTestChannel:

    @patch('compresso.libs.external_notifications.requests.post')
    def test_test_channel_returns_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='discord')

        result = dispatcher.test_channel(channel)

        assert result['success'] is True
        mock_post.assert_called_once()

    @patch('compresso.libs.external_notifications.requests.post')
    def test_test_channel_sends_test_context(self, mock_post):
        mock_post.return_value = MagicMock(status_code=204)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='discord')

        dispatcher.test_channel(channel)

        payload = mock_post.call_args[1]['json']
        embed = payload['embeds'][0]
        field_values = [f['value'] for f in embed['fields']]
        assert 'test_video.mp4' in field_values

    @patch('compresso.libs.external_notifications.requests.post')
    def test_test_channel_returns_error_on_exception(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout")
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='webhook', url='https://example.com/hook')

        result = dispatcher.test_channel(channel)

        assert result['success'] is False
        assert 'error' in result

    @patch('compresso.libs.external_notifications.requests.post')
    def test_test_channel_uses_task_completed_event(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        dispatcher = _fresh_dispatcher()
        channel = _make_channel(channel_type='webhook', url='https://example.com/hook')

        dispatcher.test_channel(channel)

        payload = mock_post.call_args[1]['json']
        assert payload['event'] == 'task_completed'
