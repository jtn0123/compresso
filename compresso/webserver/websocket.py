#!/usr/bin/env python3

"""
    compresso.websocket.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     23 Jul 2021, (6:08 PM)

    Copyright:
           Copyright (C) Josh Sunnex - All Rights Reserved

           Permission is hereby granted, free of charge, to any person obtaining a copy
           of this software and associated documentation files (the "Software"), to deal
           in the Software without restriction, including without limitation the rights
           to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
           copies of the Software, and to permit persons to whom the Software is
           furnished to do so, subject to the following conditions:

           The above copyright notice and this permission notice shall be included in all
           copies or substantial portions of the Software.

           THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
           EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
           MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
           IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
           DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
           OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE
           OR OTHER DEALINGS IN THE SOFTWARE.

"""
import json
import time
import uuid
from typing import Any

import psutil
import tornado.ioloop
import tornado.locks
import tornado.web
import tornado.websocket
from tornado import gen

from compresso import config
from compresso.libs import common, session
from compresso.libs.frontend_push_messages import FrontendPushMessages
from compresso.libs.gpu_monitor import GpuMonitor
from compresso.libs.installation_link import Links
from compresso.libs.uiserver import CompressoDataQueues, CompressoRunningThreads
from compresso.webserver.helpers import completed_tasks, pending_tasks
from compresso.webserver.helpers.queue_eta import estimate_queue_eta
from compresso.webserver.proxy import resolve_proxy_target


class CompressoWebsocketHandler(tornado.websocket.WebSocketHandler):
    STREAM_POLL_INTERVALS = {
        'frontend_message': 0.5,
        'system_logs': 1,
        'workers_info': 0.5,
        'pending_tasks': 3,
        'completed_tasks': 3,
        'system_status': 5,
    }
    STREAM_FORCE_REFRESH_INTERVALS = {
        'frontend_message': 3,
        'system_logs': 5,
        'workers_info': 2,
        'pending_tasks': 10,
        'completed_tasks': 10,
        'system_status': 15,
    }

    name = None
    config = None
    sending_frontend_message = False
    sending_system_logs = False
    sending_worker_info = False
    sending_pending_tasks_info = False
    sending_completed_tasks_info = False
    sending_system_status = False
    close_event = None

    def __init__(self, *args, **kwargs):
        self.name = 'CompressoWebsocketHandler'
        self.config = config.Config()
        self.server_id = str(uuid.uuid4())
        udq = CompressoDataQueues()
        urt = CompressoRunningThreads()
        self.data_queues = udq.get_compresso_data_queues()
        self.foreman = urt.get_compresso_running_thread('foreman')
        self.session = session.Session()
        self._stream_state: dict[str, dict[str, Any]] = {}
        self._gpu_history_tick = 0
        super().__init__(*args, **kwargs)

    async def open(self):
        tornado.log.app_log.warning('WS Opened', exc_info=True)
        self.close_event = tornado.locks.Event()

        # Check if we are proxying to a remote installation
        target_id = self.get_argument("target_id", None)

        if target_id:
            target_info = resolve_proxy_target(target_id)
            if target_info:
                self.is_proxy = True
                # WS URL: http -> ws, https -> wss
                url_base = target_info['url_base']
                if url_base.startswith("https"):
                    ws_url = url_base.replace("https", "wss", 1)
                else:
                    ws_url = url_base.replace("http", "ws", 1)

                ws_url = f"{ws_url}/compresso/websocket"

                headers = target_info['headers']
                try:
                    request = tornado.httpclient.HTTPRequest(url=ws_url, headers=headers)
                    self.remote_ws = await tornado.websocket.websocket_connect(
                        request,
                        on_message_callback=self.on_remote_message,
                    )
                except Exception as e:
                    tornado.log.app_log.error(f"Failed to connect to remote WS: {e}")
                    self.close()

    def on_message(self, message):
        if getattr(self, 'is_proxy', False):
            if hasattr(self, 'remote_ws') and self.remote_ws:
                self.remote_ws.write_message(message)
            return

        try:
            message_data = json.loads(message)
            if message_data.get('command'):
                # Execute the function
                getattr(self, message_data.get('command', 'default_failure_response'))(
                    params=message_data.get('params', {}))
        except json.decoder.JSONDecodeError:
            tornado.log.app_log.error(f'Received incorrectly formatted message - {message}', exc_info=False)

    def on_close(self):
        tornado.log.app_log.warning('WS Closed', exc_info=True)
        self.close_event.set()

        if getattr(self, 'is_proxy', False):
            if hasattr(self, 'remote_ws') and self.remote_ws:
                self.remote_ws.close()
            return

        self._stop_all_senders()

    def on_remote_message(self, message):
        if message is None:
            # Remote closed
            self.close()
            return
        self.write_message(message)

    def default_failure_response(self, params=None):
        """
        WS Command - default_failure_response
        Returns a failure response

        :param params:
        :type params:
        :return:
        :rtype:
        """
        self.write_message({'success': False})

    def start_frontend_messages(self, params=None):
        """
        WS Command - start_frontend_messages
        Start sending messages from the application to the frontend.

        :param params:
        :type params:
        :return:
        :rtype:
        """
        if not self.sending_frontend_message:
            self.sending_frontend_message = True
            tornado.ioloop.IOLoop.current().spawn_callback(self.async_frontend_message)

    def stop_frontend_messages(self, params=None):
        """
        WS Command - stop_frontend_messages
        Stop sending messages from the application to the frontend.

        :param params:
        :type params:
        :return:
        :rtype:
        """
        self.sending_frontend_message = False

    def start_system_logs(self, params=None):
        """
        WS Command - start_system_logs
        Start sending system logs from the application to the frontend.

        :param params:
        :type params:
        :return:
        :rtype:
        """
        if not self.sending_system_logs:
            self.sending_system_logs = True
            tornado.ioloop.IOLoop.current().spawn_callback(self.async_system_logs)

    def stop_system_logs(self, params=None):
        """
        WS Command - stop_system_logs
        Stop sending system logs from the application to the frontend.

        :param params:
        :type params:
        :return:
        :rtype:
        """
        self.sending_system_logs = False

    def start_workers_info(self, params=None):
        """
        WS Command - start_workers_info
        Start sending information pertaining to the workers

        :param params:
        :type params:
        :return:
        :rtype:
        """
        if not self.sending_worker_info:
            self.sending_worker_info = True
            tornado.ioloop.IOLoop.current().spawn_callback(self.async_workers_info)

    def stop_workers_info(self, params=None):
        """
        WS Command - stop_workers_info
        Stop sending information pertaining to the workers

        :param params:
        :type params:
        :return:
        :rtype:
        """
        self.sending_worker_info = False

    def start_pending_tasks_info(self, params=None):
        """
        WS Command - start_pending_tasks_info
        Start sending information pertaining to the pending tasks list

        :param params:
        :type params:
        :return:
        :rtype:
        """
        if not self.sending_pending_tasks_info:
            self.sending_pending_tasks_info = True
            tornado.ioloop.IOLoop.current().spawn_callback(self.async_pending_tasks_info)

    def stop_pending_tasks_info(self, params=None):
        """
        WS Command - stop_pending_tasks_info
        Stop sending information pertaining to the pending tasks list

        :param params:
        :type params:
        :return:
        :rtype:
        """
        self.sending_pending_tasks_info = False

    def start_completed_tasks_info(self, params=None):
        """
        WS Command - start_completed_tasks_info
        Start sending information pertaining to the completed tasks list

        :param params:
        :type params:
        :return:
        :rtype:
        """
        if not self.sending_completed_tasks_info:
            self.sending_completed_tasks_info = True
            tornado.ioloop.IOLoop.current().spawn_callback(self.async_completed_tasks_info)

    def stop_completed_tasks_info(self, params=None):
        """
        WS Command - stop_completed_tasks_info
        Stop sending information pertaining to the completed tasks list

        :param params:
        :type params:
        :return:
        :rtype:
        """
        self.sending_completed_tasks_info = False

    def start_system_status(self, params=None):
        """
        WS Command - start_system_status
        Start sending system resource metrics (CPU, RAM, disk) to the frontend.

        :param params:
        :type params:
        :return:
        :rtype:
        """
        if not self.sending_system_status:
            self.sending_system_status = True
            tornado.ioloop.IOLoop.current().spawn_callback(self.async_system_status)

    def stop_system_status(self, params=None):
        """
        WS Command - stop_system_status
        Stop sending system resource metrics to the frontend.

        :param params:
        :type params:
        :return:
        :rtype:
        """
        self.sending_system_status = False

    def dismiss_message(self, params=None):
        """
        WS Command - dismiss_message
        Dismiss a specified message by id.

        params:
            - message_id    - The ID of the message to be dismissed

        :param params:
        :type params:
        :return:
        :rtype:
        """
        frontend_messages = FrontendPushMessages()
        frontend_messages.remove_item(params.get('message_id', ''))

    async def send(self, message):
        if self.ws_connection:
            try:
                await self.write_message(message)
                return True
            except tornado.websocket.WebSocketClosedError:
                self._stop_all_senders()
        return False

    def _stop_all_senders(self):
        self.stop_frontend_messages()
        self.stop_workers_info()
        self.stop_pending_tasks_info()
        self.stop_completed_tasks_info()
        self.stop_system_logs()
        self.stop_system_status()

    def _stream_is_active(self, enabled: bool) -> bool:
        return enabled and not (self.close_event and self.close_event.is_set())

    @staticmethod
    def _normalize_stream_data(stream_name: str, data: Any) -> Any:
        if stream_name == 'frontend_message' and isinstance(data, list):
            return sorted(data, key=lambda item: str(item.get('id', '')))
        if stream_name == 'workers_info' and isinstance(data, list):
            return sorted(data, key=lambda item: (str(item.get('name', '')), str(item.get('id', ''))))
        return data

    def _should_send_stream(self, stream_name: str, payload: Any) -> dict[str, Any]:
        normalized_payload = self._normalize_stream_data(stream_name, payload)
        serialized_payload = json.dumps(normalized_payload, sort_keys=True, default=str)
        payload_bytes = len(serialized_payload.encode('utf-8'))
        now = time.time()
        state = self._stream_state.setdefault(
            stream_name,
            {
                'last_payload': None,
                'last_sent_at': 0.0,
                'sequence': 0,
                'skipped_duplicates': 0,
            },
        )

        should_send = (
            state['last_payload'] is None
            or state['last_payload'] != serialized_payload
            or (now - state['last_sent_at']) >= self.STREAM_FORCE_REFRESH_INTERVALS.get(stream_name, 5)
        )

        if not should_send:
            state['skipped_duplicates'] += 1
            return {
                'should_send': False,
                'normalized_payload': normalized_payload,
                'payload_bytes': payload_bytes,
            }

        state['last_payload'] = serialized_payload
        state['last_sent_at'] = now
        state['sequence'] += 1
        return {
            'should_send': True,
            'normalized_payload': normalized_payload,
            'payload_bytes': payload_bytes,
            'sequence': state['sequence'],
            'sent_at': now,
            'skipped_duplicates': state['skipped_duplicates'],
        }

    async def _send_stream_message(self, stream_name: str, payload: Any):
        stream_state = self._should_send_stream(stream_name, payload)
        if not stream_state['should_send']:
            return False

        await self.send(
            {
                'success': True,
                'server_id': self.server_id,
                'type': stream_name,
                'data': stream_state['normalized_payload'],
                'meta': {
                    'sequence': stream_state['sequence'],
                    'sent_at': stream_state['sent_at'],
                    'payload_bytes': stream_state['payload_bytes'],
                    'skipped_duplicates': stream_state['skipped_duplicates'],
                },
            }
        )
        return True

    async def async_frontend_message(self):
        while self._stream_is_active(self.sending_frontend_message):
            frontend_messages = FrontendPushMessages()
            frontend_message_items = frontend_messages.read_all_items()
            await self._send_stream_message('frontend_message', frontend_message_items)

            await gen.sleep(self.STREAM_POLL_INTERVALS['frontend_message'])

    async def async_system_logs(self):
        while self._stream_is_active(self.sending_system_logs):
            system_logs = self.config.read_system_logs(lines=1000)

            await self._send_stream_message(
                'system_logs',
                {
                    "logs_path": self.config.get_log_path(),
                    'system_logs': system_logs,
                },
            )

            await gen.sleep(self.STREAM_POLL_INTERVALS['system_logs'])

    async def async_workers_info(self):
        while self._stream_is_active(self.sending_worker_info):
            workers_info = self.foreman.get_all_worker_status()
            await self._send_stream_message('workers_info', workers_info)
            await gen.sleep(self.STREAM_POLL_INTERVALS['workers_info'])

    async def async_pending_tasks_info(self):
        while self._stream_is_active(self.sending_pending_tasks_info):
            results = []
            params = {
                'start':        '0',
                'length':       '10',
                'search_value': '',
                'order':        {
                    "column": 'priority',
                    "dir":    'desc',
                }
            }
            task_list = pending_tasks.prepare_filtered_pending_tasks(params)

            for task_result in task_list.get('results', []):
                # Append the task to the results list
                item = {
                    'id':       task_result['id'],
                    'label':    task_result['abspath'],
                    'priority': task_result['priority'],
                    'status':   task_result['status'],
                }
                # Include retry info when present
                if task_result.get('retry_count'):
                    item['retry_count'] = task_result['retry_count']
                if task_result.get('deferred_until'):
                    item['deferred_until'] = str(task_result['deferred_until'])
                results.append(item)

            # Estimate queue ETA and include in payload
            try:
                queue_eta = estimate_queue_eta(self.foreman)
            except Exception:
                queue_eta = None

            await self._send_stream_message(
                'pending_tasks',
                {
                    'results': results,
                    'queue_eta': queue_eta,
                },
            )

            await gen.sleep(self.STREAM_POLL_INTERVALS['pending_tasks'])

    async def async_completed_tasks_info(self):
        while self._stream_is_active(self.sending_completed_tasks_info):
            results = []
            params = {
                'start':        '0',
                'length':       '10',
                'search_value': '',
                'order':        {
                    "column": 'finish_time',
                    "dir":    'desc',
                }
            }
            task_list = completed_tasks.prepare_filtered_completed_tasks(params)

            for task_result in task_list.get('results', []):
                # Set human-readable time
                if (int(task_result['finish_time']) + 60) > int(time.time()):
                    human_readable_time = 'Just Now'
                else:
                    human_readable_time = common.make_timestamp_human_readable(int(task_result['finish_time']))

                # Append the task to the results list
                results.append(
                    {
                        'id':                  task_result['id'],
                        'label':               task_result['task_label'],
                        'success':             task_result['task_success'],
                        'finish_time':         task_result['finish_time'],
                        'human_readable_time': human_readable_time,
                    }
                )

            await self._send_stream_message(
                'completed_tasks',
                {
                    'results': results
                },
            )

            await gen.sleep(self.STREAM_POLL_INTERVALS['completed_tasks'])

    def _get_gpu_utilization(self):
        """Deprecated: Use GpuMonitor().get_realtime_metrics() instead."""
        return GpuMonitor().get_realtime_metrics()

    async def async_system_status(self):
        while self._stream_is_active(self.sending_system_status):
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage('/')

            self._gpu_history_tick += 1
            gpu_monitor = GpuMonitor()

            # Include remote installation link statuses
            try:
                links = Links()
                link_statuses = links.get_all_link_statuses()
            except Exception:
                link_statuses = {}

            payload = {
                'cpu_percent':    psutil.cpu_percent(interval=0),
                'memory_percent': mem.percent,
                'memory_used_gb': round(mem.used / (1024 ** 3), 1),
                'disk_percent':   disk.percent,
                'disk_used_gb':   round(disk.used / (1024 ** 3), 1),
                'gpus':           gpu_monitor.get_realtime_metrics(),
                'gpu_history':    gpu_monitor.get_history() if self._gpu_history_tick % 6 == 0 else None,
                'link_statuses':  link_statuses,
            }

            await self._send_stream_message('system_status', payload)

            await gen.sleep(self.STREAM_POLL_INTERVALS['system_status'])
