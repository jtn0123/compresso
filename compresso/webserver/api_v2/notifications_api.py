#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    compresso.notifications_api.py

    Written by:               Josh.5 <jsunnex@gmail.com>
    Date:                     20 Apr 2022, (1:07 AM)

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
import re

import tornado.log
from compresso import config
from compresso.libs import session
from compresso.libs.external_notifications import ExternalNotificationDispatcher
from compresso.libs.notifications import Notifications
from compresso.libs.uiserver import CompressoDataQueues
from compresso.webserver.api_v2.base_api_handler import BaseApiError, BaseApiHandler
from compresso.webserver.api_v2.schema.schemas import RequestNotificationsDataSchema, RequestTableUpdateByUuidList


class ApiNotificationsHandler(BaseApiHandler):
    session = None
    config = None
    params = None
    compresso_data_queues = None

    routes = [
        {
            "path_pattern":      r"/notifications/read",
            "supported_methods": ["GET"],
            "call_method":       "get_notifications",
        },
        {
            "path_pattern":      r"/notifications/remove",
            "supported_methods": ["DELETE"],
            "call_method":       "remove_notifications",
        },
        {
            "path_pattern":      r"/notifications/channels",
            "supported_methods": ["GET"],
            "call_method":       "get_notification_channels",
        },
        {
            "path_pattern":      r"/notifications/channels/save",
            "supported_methods": ["POST"],
            "call_method":       "save_notification_channels",
        },
        {
            "path_pattern":      r"/notifications/channels/test",
            "supported_methods": ["POST"],
            "call_method":       "test_notification_channel",
        },
    ]

    def initialize(self, **kwargs):
        self.session = session.Session()
        self.params = kwargs.get("params")
        udq = CompressoDataQueues()
        self.compresso_data_queues = udq.get_compresso_data_queues()
        self.config = config.Config()

    async def get_notifications(self):
        """
        Notifications - read
        ---
        description: Returns a list of notifications in reverse chronological order.
        responses:
            200:
                description: 'Sample response: A list of notifications in reverse chronological order.'
                content:
                    application/json:
                        schema:
                            RequestNotificationsDataSchema
            400:
                description: Bad request; Check `messages` for any validation errors
                content:
                    application/json:
                        schema:
                            BadRequestSchema
            404:
                description: Bad request; Requested endpoint not found
                content:
                    application/json:
                        schema:
                            BadEndpointSchema
            405:
                description: Bad request; Requested method is not allowed
                content:
                    application/json:
                        schema:
                            BadMethodSchema
            500:
                description: Internal error; Check `error` for exception
                content:
                    application/json:
                        schema:
                            InternalErrorSchema
        """
        try:
            notifications = Notifications()
            notifications_list = notifications.read_all_items()
            notifications_list_reversed = list(reversed(notifications_list))

            response = self.build_response(
                RequestNotificationsDataSchema(),
                {
                    "notifications": notifications_list_reversed,
                }
            )
            self.write_success(response)
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def remove_notifications(self):
        """
        Notifications - delete
        ---
        description: Delete one or all notifications.
        requestBody:
            description: Requested list of items to delete.
            required: True
            content:
                application/json:
                    schema:
                        RequestTableUpdateByUuidList
        responses:
            200:
                description: 'Successful request; Returns success status'
                content:
                    application/json:
                        schema:
                            BaseSuccessSchema
            400:
                description: Bad request; Check `messages` for any validation errors
                content:
                    application/json:
                        schema:
                            BadRequestSchema
            404:
                description: Bad request; Requested endpoint not found
                content:
                    application/json:
                        schema:
                            BadEndpointSchema
            405:
                description: Bad request; Requested method is not allowed
                content:
                    application/json:
                        schema:
                            BadMethodSchema
            500:
                description: Internal error; Check `error` for exception
                content:
                    application/json:
                        schema:
                            InternalErrorSchema
        """
        try:
            json_request = self.read_json_request(RequestTableUpdateByUuidList())

            notifications = Notifications()
            for notification_uuid in json_request.get('uuid_list', []):
                if not notifications.remove(notification_uuid):
                    self.set_status(self.STATUS_ERROR_EXTERNAL,
                                    reason="Failed to delete the notification with UUID '{}'".format(notification_uuid))
                    self.write_error()
                    return

            self.write_success()
            return
        except BaseApiError as bae:
            tornado.log.app_log.error("BaseApiError.{}: {}".format(self.route.get('call_method'), str(bae)))
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(bae))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    @staticmethod
    def _mask_url(url):
        """
        Partially mask a webhook URL for display security.
        Shows the protocol + first 12 chars of the rest, then '***'.
        """
        if not url:
            return ''
        match = re.match(r'^(https?://)', url)
        if match:
            prefix = match.group(1)
            rest = url[len(prefix):]
            if len(rest) > 12:
                return prefix + rest[:12] + '***'
            return url
        if len(url) > 12:
            return url[:12] + '***'
        return url

    async def get_notification_channels(self):
        """
        Notification Channels - read
        ---
        description: Returns the list of configured external notification channels
                     with webhook URLs partially masked.
        responses:
            200:
                description: 'List of configured notification channels.'
            500:
                description: Internal error
        """
        try:
            channels = self.config.get_notification_channels()
            # Mask URLs for display security
            masked = []
            for ch in channels:
                masked_ch = dict(ch)
                masked_ch['url'] = self._mask_url(ch.get('url', ''))
                masked.append(masked_ch)
            self.write_success({'channels': masked})
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def save_notification_channels(self):
        """
        Notification Channels - save
        ---
        description: Save the full list of notification channels to config.
        requestBody:
            required: True
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            channels:
                                type: array
        responses:
            200:
                description: 'Channels saved successfully.'
            400:
                description: Bad request
            500:
                description: Internal error
        """
        try:
            body = json.loads(self.request.body)
            channels = body.get('channels')
            if not isinstance(channels, list):
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="'channels' must be a list")
                self.write_error()
                return
            self.config.set_config_item('notification_channels', channels)
            self.write_success()
            return
        except (json.JSONDecodeError, TypeError) as e:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(e))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()

    async def test_notification_channel(self):
        """
        Notification Channels - test
        ---
        description: Send a test notification to a single channel.
        requestBody:
            required: True
            content:
                application/json:
                    schema:
                        type: object
                        properties:
                            channel:
                                type: object
        responses:
            200:
                description: 'Test result with success boolean.'
            400:
                description: Bad request
            500:
                description: Internal error
        """
        try:
            body = json.loads(self.request.body)
            channel_config = body.get('channel')
            if not isinstance(channel_config, dict):
                self.set_status(self.STATUS_ERROR_EXTERNAL, reason="'channel' must be an object")
                self.write_error()
                return
            dispatcher = ExternalNotificationDispatcher()
            result = dispatcher.test_channel(channel_config)
            self.write_success(result)
            return
        except (json.JSONDecodeError, TypeError) as e:
            self.set_status(self.STATUS_ERROR_EXTERNAL, reason=str(e))
            self.write_error()
            return
        except Exception as e:
            self.set_status(self.STATUS_ERROR_INTERNAL, reason=str(e))
            self.write_error()
