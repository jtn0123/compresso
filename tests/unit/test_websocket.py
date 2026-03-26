#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_websocket.py

    Unit tests for compresso.webserver.websocket.CompressoWebsocketHandler.
"""

import json
import time

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


WS_MOD = 'compresso.webserver.websocket'


def _make_handler():
    """Create a CompressoWebsocketHandler with mocked dependencies."""
    with patch(f'{WS_MOD}.config.Config') as mock_config_cls, \
         patch(f'{WS_MOD}.CompressoDataQueues') as mock_udq_cls, \
         patch(f'{WS_MOD}.CompressoRunningThreads') as mock_urt_cls, \
         patch(f'{WS_MOD}.session.Session'):

        mock_config = MagicMock()
        mock_config_cls.return_value = mock_config
        mock_udq = MagicMock()
        mock_udq.get_compresso_data_queues.return_value = {}
        mock_udq_cls.return_value = mock_udq
        mock_urt = MagicMock()
        mock_foreman = MagicMock()
        mock_urt.get_compresso_running_thread.return_value = mock_foreman
        mock_urt_cls.return_value = mock_urt

        # Create handler with mocked tornado internals
        app = MagicMock()
        app.ui_methods = {}
        app.ui_modules = {}
        request = MagicMock()
        request.connection = MagicMock()

        from compresso.webserver.websocket import CompressoWebsocketHandler
        handler = CompressoWebsocketHandler(app, request)
        handler.config = mock_config
        handler.foreman = mock_foreman
        return handler


# ------------------------------------------------------------------
# TestOnMessage
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestOnMessage:
    """Tests for CompressoWebsocketHandler.on_message()."""

    def test_valid_json_command_dispatches_to_method(self):
        handler = _make_handler()
        handler.start_frontend_messages = MagicMock()
        message = json.dumps({'command': 'start_frontend_messages', 'params': {}})
        handler.on_message(message)
        handler.start_frontend_messages.assert_called_once_with(params={})

    def test_valid_json_command_with_params(self):
        handler = _make_handler()
        handler.dismiss_message = MagicMock()
        message = json.dumps({'command': 'dismiss_message', 'params': {'message_id': 'abc'}})
        handler.on_message(message)
        handler.dismiss_message.assert_called_once_with(params={'message_id': 'abc'})

    def test_invalid_json_does_not_raise(self):
        handler = _make_handler()
        # Should log error but not raise
        handler.on_message('not valid json')

    def test_missing_command_key_does_nothing(self):
        handler = _make_handler()
        handler.default_failure_response = MagicMock()
        message = json.dumps({'data': 'value'})
        # When 'command' is missing, get returns None, which triggers default_failure_response
        handler.on_message(message)

    def test_proxy_mode_forwards_message(self):
        handler = _make_handler()
        handler.is_proxy = True
        handler.remote_ws = MagicMock()
        message = json.dumps({'command': 'test'})
        handler.on_message(message)
        handler.remote_ws.write_message.assert_called_once_with(message)

    def test_proxy_mode_no_remote_ws_does_not_crash(self):
        handler = _make_handler()
        handler.is_proxy = True
        handler.remote_ws = None
        message = json.dumps({'command': 'test'})
        # Should not raise
        handler.on_message(message)


# ------------------------------------------------------------------
# TestOnClose
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestOnClose:
    """Tests for CompressoWebsocketHandler.on_close()."""

    def test_on_close_sets_close_event(self):
        handler = _make_handler()
        import tornado.locks
        handler.close_event = tornado.locks.Event()
        handler.on_close()
        assert handler.close_event.is_set()

    def test_on_close_stops_all_senders(self):
        handler = _make_handler()
        import tornado.locks
        handler.close_event = tornado.locks.Event()
        handler.sending_frontend_message = True
        handler.sending_system_logs = True
        handler.sending_worker_info = True
        handler.sending_pending_tasks_info = True
        handler.sending_completed_tasks_info = True
        handler.sending_system_status = True
        handler.on_close()
        assert handler.sending_frontend_message is False
        assert handler.sending_system_logs is False
        assert handler.sending_worker_info is False
        assert handler.sending_pending_tasks_info is False
        assert handler.sending_completed_tasks_info is False
        assert handler.sending_system_status is False

    def test_on_close_proxy_mode_closes_remote(self):
        handler = _make_handler()
        import tornado.locks
        handler.close_event = tornado.locks.Event()
        handler.is_proxy = True
        handler.remote_ws = MagicMock()
        handler.on_close()
        handler.remote_ws.close.assert_called_once()


# ------------------------------------------------------------------
# TestOnRemoteMessage
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestOnRemoteMessage:
    """Tests for CompressoWebsocketHandler.on_remote_message()."""

    def test_none_message_closes_handler(self):
        handler = _make_handler()
        handler.close = MagicMock()
        handler.on_remote_message(None)
        handler.close.assert_called_once()

    def test_forwards_message(self):
        handler = _make_handler()
        handler.write_message = MagicMock()
        handler.on_remote_message('{"data": "test"}')
        handler.write_message.assert_called_once_with('{"data": "test"}')


# ------------------------------------------------------------------
# TestDefaultFailureResponse
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestDefaultFailureResponse:
    """Tests for CompressoWebsocketHandler.default_failure_response()."""

    def test_writes_failure_response(self):
        handler = _make_handler()
        handler.write_message = MagicMock()
        handler.default_failure_response()
        handler.write_message.assert_called_once_with({'success': False})


# ------------------------------------------------------------------
# TestStartStopMethods
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestStartStopMethods:
    """Tests for start/stop toggle methods."""

    @patch(f'{WS_MOD}.tornado.ioloop.IOLoop')
    def test_start_frontend_messages_sets_flag(self, mock_ioloop):
        handler = _make_handler()
        mock_ioloop.current.return_value = MagicMock()
        handler.start_frontend_messages()
        assert handler.sending_frontend_message is True

    @patch(f'{WS_MOD}.tornado.ioloop.IOLoop')
    def test_start_frontend_messages_idempotent(self, mock_ioloop):
        handler = _make_handler()
        mock_loop = MagicMock()
        mock_ioloop.current.return_value = mock_loop
        handler.start_frontend_messages()
        handler.start_frontend_messages()
        # spawn_callback should only be called once
        assert mock_loop.spawn_callback.call_count == 1

    def test_stop_frontend_messages_clears_flag(self):
        handler = _make_handler()
        handler.sending_frontend_message = True
        handler.stop_frontend_messages()
        assert handler.sending_frontend_message is False

    @patch(f'{WS_MOD}.tornado.ioloop.IOLoop')
    def test_start_system_logs_sets_flag(self, mock_ioloop):
        handler = _make_handler()
        mock_ioloop.current.return_value = MagicMock()
        handler.start_system_logs()
        assert handler.sending_system_logs is True

    def test_stop_system_logs_clears_flag(self):
        handler = _make_handler()
        handler.sending_system_logs = True
        handler.stop_system_logs()
        assert handler.sending_system_logs is False

    @patch(f'{WS_MOD}.tornado.ioloop.IOLoop')
    def test_start_workers_info_sets_flag(self, mock_ioloop):
        handler = _make_handler()
        mock_ioloop.current.return_value = MagicMock()
        handler.start_workers_info()
        assert handler.sending_worker_info is True

    def test_stop_workers_info_clears_flag(self):
        handler = _make_handler()
        handler.sending_worker_info = True
        handler.stop_workers_info()
        assert handler.sending_worker_info is False

    @patch(f'{WS_MOD}.tornado.ioloop.IOLoop')
    def test_start_pending_tasks_info_sets_flag(self, mock_ioloop):
        handler = _make_handler()
        mock_ioloop.current.return_value = MagicMock()
        handler.start_pending_tasks_info()
        assert handler.sending_pending_tasks_info is True

    def test_stop_pending_tasks_info_clears_flag(self):
        handler = _make_handler()
        handler.sending_pending_tasks_info = True
        handler.stop_pending_tasks_info()
        assert handler.sending_pending_tasks_info is False

    @patch(f'{WS_MOD}.tornado.ioloop.IOLoop')
    def test_start_completed_tasks_info_sets_flag(self, mock_ioloop):
        handler = _make_handler()
        mock_ioloop.current.return_value = MagicMock()
        handler.start_completed_tasks_info()
        assert handler.sending_completed_tasks_info is True

    def test_stop_completed_tasks_info_clears_flag(self):
        handler = _make_handler()
        handler.sending_completed_tasks_info = True
        handler.stop_completed_tasks_info()
        assert handler.sending_completed_tasks_info is False

    @patch(f'{WS_MOD}.tornado.ioloop.IOLoop')
    def test_start_system_status_sets_flag(self, mock_ioloop):
        handler = _make_handler()
        mock_ioloop.current.return_value = MagicMock()
        handler.start_system_status()
        assert handler.sending_system_status is True

    def test_stop_system_status_clears_flag(self):
        handler = _make_handler()
        handler.sending_system_status = True
        handler.stop_system_status()
        assert handler.sending_system_status is False


# ------------------------------------------------------------------
# TestDismissMessage
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestDismissMessage:
    """Tests for CompressoWebsocketHandler.dismiss_message()."""

    @patch(f'{WS_MOD}.FrontendPushMessages')
    def test_dismiss_removes_message(self, mock_fpm_cls):
        handler = _make_handler()
        mock_fpm = MagicMock()
        mock_fpm_cls.return_value = mock_fpm
        handler.dismiss_message(params={'message_id': 'msg-123'})
        mock_fpm.remove_item.assert_called_once_with('msg-123')

    @patch(f'{WS_MOD}.FrontendPushMessages')
    def test_dismiss_with_no_message_id(self, mock_fpm_cls):
        handler = _make_handler()
        mock_fpm = MagicMock()
        mock_fpm_cls.return_value = mock_fpm
        handler.dismiss_message(params={})
        mock_fpm.remove_item.assert_called_once_with('')


# ------------------------------------------------------------------
# TestSend
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestSend:
    """Tests for CompressoWebsocketHandler.send()."""

    @pytest.mark.asyncio
    async def test_send_writes_when_connected(self):
        handler = _make_handler()
        handler.ws_connection = MagicMock()
        handler.write_message = AsyncMock()
        await handler.send({'test': True})
        handler.write_message.assert_called_once_with({'test': True})

    @pytest.mark.asyncio
    async def test_send_does_nothing_when_disconnected(self):
        handler = _make_handler()
        handler.ws_connection = None
        handler.write_message = AsyncMock()
        await handler.send({'test': True})
        handler.write_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_stops_senders_when_socket_closes_mid_write(self):
        handler = _make_handler()
        handler.ws_connection = MagicMock()
        handler.write_message = AsyncMock(side_effect=Exception())
        handler.stop_frontend_messages = MagicMock()
        handler.stop_workers_info = MagicMock()
        handler.stop_pending_tasks_info = MagicMock()
        handler.stop_completed_tasks_info = MagicMock()
        handler.stop_system_logs = MagicMock()
        handler.stop_system_status = MagicMock()

        with patch(f'{WS_MOD}.tornado.websocket.WebSocketClosedError', Exception):
            await handler.send({'test': True})

        handler.stop_frontend_messages.assert_called_once()
        handler.stop_workers_info.assert_called_once()


# ------------------------------------------------------------------
# TestGetGpuUtilization
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestGetGpuUtilization:
    """Tests for CompressoWebsocketHandler._get_gpu_utilization() (now delegates to GpuMonitor)."""

    @patch(f'{WS_MOD}.GpuMonitor')
    def test_delegates_to_gpu_monitor(self, mock_gpu_monitor_cls):
        handler = _make_handler()
        mock_monitor = MagicMock()
        mock_monitor.get_realtime_metrics.return_value = [
            {'index': 0, 'type': 'nvidia', 'name': 'GPU-0',
             'utilization_percent': 45.0, 'memory_used_mb': 2048,
             'memory_total_mb': 8192, 'temperature_c': 65},
            {'index': 1, 'type': 'nvidia', 'name': 'GPU-1',
             'utilization_percent': 30.0, 'memory_used_mb': 1024,
             'memory_total_mb': 4096, 'temperature_c': 55},
        ]
        mock_gpu_monitor_cls.return_value = mock_monitor

        gpus = handler._get_gpu_utilization()
        assert len(gpus) == 2
        assert gpus[0]['index'] == 0
        assert gpus[0]['utilization_percent'] == 45.0
        assert gpus[0]['memory_used_mb'] == 2048
        assert gpus[0]['memory_total_mb'] == 8192
        assert gpus[0]['temperature_c'] == 65
        assert gpus[1]['index'] == 1
        mock_monitor.get_realtime_metrics.assert_called_once()

    @patch(f'{WS_MOD}.GpuMonitor')
    def test_returns_empty_when_no_gpus(self, mock_gpu_monitor_cls):
        handler = _make_handler()
        mock_monitor = MagicMock()
        mock_monitor.get_realtime_metrics.return_value = []
        mock_gpu_monitor_cls.return_value = mock_monitor

        gpus = handler._get_gpu_utilization()
        assert gpus == []


# ------------------------------------------------------------------
# TestAsyncLoops
# ------------------------------------------------------------------

@pytest.mark.unittest
class TestAsyncLoops:
    """Tests for the async loop methods (single iteration)."""

    @pytest.mark.asyncio
    async def test_async_frontend_message_sends_data(self):
        handler = _make_handler()
        handler.sending_frontend_message = True
        handler.send = AsyncMock()

        with patch(f'{WS_MOD}.FrontendPushMessages') as mock_fpm_cls, \
             patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            mock_fpm = MagicMock()
            mock_fpm.read_all_items.return_value = [{'id': 1, 'msg': 'test'}]
            mock_fpm_cls.return_value = mock_fpm

            # Stop after first iteration
            async def stop_after_first(*args):
                handler.sending_frontend_message = False

            mock_sleep.side_effect = stop_after_first

            await handler.async_frontend_message()

            handler.send.assert_called_once()
            call_data = handler.send.call_args[0][0]
            assert call_data['type'] == 'frontend_message'
            assert call_data['success'] is True

    @pytest.mark.asyncio
    async def test_async_system_logs_sends_data(self):
        handler = _make_handler()
        handler.sending_system_logs = True
        handler.send = AsyncMock()
        handler.config.read_system_logs.return_value = ['log line 1']
        handler.config.get_log_path.return_value = '/var/log/compresso'

        with patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            async def stop_after_first(*args):
                handler.sending_system_logs = False
            mock_sleep.side_effect = stop_after_first

            await handler.async_system_logs()

            handler.send.assert_called_once()
            call_data = handler.send.call_args[0][0]
            assert call_data['type'] == 'system_logs'
            assert call_data['data']['system_logs'] == ['log line 1']

    @pytest.mark.asyncio
    async def test_async_workers_info_sends_data(self):
        handler = _make_handler()
        handler.sending_worker_info = True
        handler.send = AsyncMock()
        handler.foreman.get_all_worker_status.return_value = [{'id': 'w1'}]

        with patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            async def stop_after_first(*args):
                handler.sending_worker_info = False
            mock_sleep.side_effect = stop_after_first

            await handler.async_workers_info()

            handler.send.assert_called_once()
            call_data = handler.send.call_args[0][0]
            assert call_data['type'] == 'workers_info'

    @pytest.mark.asyncio
    async def test_async_workers_info_skips_duplicate_payloads(self):
        handler = _make_handler()
        handler.sending_worker_info = True
        handler.send = AsyncMock()
        handler.foreman.get_all_worker_status.return_value = [{'id': 'w1', 'name': 'CPU-Worker-1'}]

        sleep_calls = {'count': 0}

        with patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            async def stop_after_second(*args):
                sleep_calls['count'] += 1
                if sleep_calls['count'] >= 2:
                    handler.sending_worker_info = False

            mock_sleep.side_effect = stop_after_second

            await handler.async_workers_info()

            handler.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_workers_info_refreshes_on_changed_payload(self):
        handler = _make_handler()
        handler.sending_worker_info = True
        handler.send = AsyncMock()
        handler.foreman.get_all_worker_status.side_effect = [
            [{'id': 'w1', 'name': 'CPU-Worker-1', 'idle': True}],
            [{'id': 'w1', 'name': 'CPU-Worker-1', 'idle': False}],
        ]

        sleep_calls = {'count': 0}

        with patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            async def stop_after_second(*args):
                sleep_calls['count'] += 1
                if sleep_calls['count'] >= 2:
                    handler.sending_worker_info = False

            mock_sleep.side_effect = stop_after_second

            await handler.async_workers_info()

            assert handler.send.call_count == 2

    @pytest.mark.asyncio
    async def test_async_pending_tasks_info_sends_data(self):
        handler = _make_handler()
        handler.sending_pending_tasks_info = True
        handler.send = AsyncMock()

        with patch(f'{WS_MOD}.pending_tasks.prepare_filtered_pending_tasks') as mock_pending, \
             patch(f'{WS_MOD}.estimate_queue_eta', return_value={'total_queue_eta_seconds': 120}), \
             patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            mock_pending.return_value = {
                'results': [
                    {'id': 1, 'abspath': '/test.mkv', 'priority': 100, 'status': 'pending'}
                ]
            }
            async def stop_after_first(*args):
                handler.sending_pending_tasks_info = False
            mock_sleep.side_effect = stop_after_first

            await handler.async_pending_tasks_info()

            handler.send.assert_called_once()
            call_data = handler.send.call_args[0][0]
            assert call_data['type'] == 'pending_tasks'
            assert len(call_data['data']['results']) == 1
            assert call_data['data']['results'][0]['id'] == 1
            assert call_data['data']['queue_eta'] == {'total_queue_eta_seconds': 120}

    @pytest.mark.asyncio
    async def test_async_completed_tasks_info_sends_data(self):
        handler = _make_handler()
        handler.sending_completed_tasks_info = True
        handler.send = AsyncMock()

        with patch(f'{WS_MOD}.completed_tasks.prepare_filtered_completed_tasks') as mock_completed, \
             patch(f'{WS_MOD}.common.make_timestamp_human_readable', return_value='5 mins ago'), \
             patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            mock_completed.return_value = {
                'results': [
                    {'id': 1, 'task_label': 'test.mkv', 'task_success': True,
                     'finish_time': str(int(time.time()) - 120)}
                ]
            }
            async def stop_after_first(*args):
                handler.sending_completed_tasks_info = False
            mock_sleep.side_effect = stop_after_first

            await handler.async_completed_tasks_info()

            handler.send.assert_called_once()
            call_data = handler.send.call_args[0][0]
            assert call_data['type'] == 'completed_tasks'
            assert len(call_data['data']['results']) == 1

    @pytest.mark.asyncio
    async def test_async_completed_tasks_just_now(self):
        handler = _make_handler()
        handler.sending_completed_tasks_info = True
        handler.send = AsyncMock()

        with patch(f'{WS_MOD}.completed_tasks.prepare_filtered_completed_tasks') as mock_completed, \
             patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            # finish_time within 60 seconds => "Just Now"
            mock_completed.return_value = {
                'results': [
                    {'id': 1, 'task_label': 'recent.mkv', 'task_success': True,
                     'finish_time': str(int(time.time()))}
                ]
            }
            async def stop_after_first(*args):
                handler.sending_completed_tasks_info = False
            mock_sleep.side_effect = stop_after_first

            await handler.async_completed_tasks_info()

            call_data = handler.send.call_args[0][0]
            assert call_data['data']['results'][0]['human_readable_time'] == 'Just Now'

    @pytest.mark.asyncio
    async def test_async_system_status_sends_data(self):
        handler = _make_handler()
        handler.sending_system_status = True
        handler.send = AsyncMock()

        with patch(f'{WS_MOD}.psutil') as mock_psutil, \
             patch(f'{WS_MOD}.GpuMonitor') as mock_gpu_cls, \
             patch(f'{WS_MOD}.gen.sleep', new_callable=AsyncMock) as mock_sleep:
            mock_gpu = MagicMock()
            mock_gpu.get_realtime_metrics.return_value = []
            mock_gpu.get_history.return_value = {}
            mock_gpu_cls.return_value = mock_gpu
            mock_mem = MagicMock()
            mock_mem.percent = 55.0
            mock_mem.used = 8 * (1024 ** 3)
            mock_psutil.virtual_memory.return_value = mock_mem
            mock_disk = MagicMock()
            mock_disk.percent = 40.0
            mock_disk.used = 200 * (1024 ** 3)
            mock_psutil.disk_usage.return_value = mock_disk
            mock_psutil.cpu_percent.return_value = 25.0

            async def stop_after_first(*args):
                handler.sending_system_status = False
            mock_sleep.side_effect = stop_after_first

            await handler.async_system_status()

            handler.send.assert_called_once()
            call_data = handler.send.call_args[0][0]
            assert call_data['type'] == 'system_status'
            assert call_data['data']['cpu_percent'] == 25.0
            assert call_data['data']['memory_percent'] == 55.0
            assert 'gpus' in call_data['data']
            assert 'gpu_history' in call_data['data']


if __name__ == '__main__':
    pytest.main(['-s', '--log-cli-level=INFO', __file__])
