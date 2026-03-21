#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json

import pytest
from unittest.mock import MagicMock, patch

from tests.unit.api_test_base import ApiTestBase
from compresso.webserver.api_v2.base_api_handler import BaseApiError
from compresso.webserver.api_v2.filebrowser_api import ApiFilebrowserHandler
from compresso.webserver.api_v2.fileinfo_api import ApiFileinfoHandler
from compresso.webserver.api_v2.notifications_api import ApiNotificationsHandler


def _mock_filebrowser_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}


def _mock_notifications_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    self.compresso_data_queues = {}
    self.config = MagicMock()


@pytest.mark.unittest
@patch.object(ApiFilebrowserHandler, 'initialize', _mock_filebrowser_initialize)
class TestFilebrowserApiCoverage(ApiTestBase):
    __test__ = True
    handler_class = ApiFilebrowserHandler

    @patch('compresso.webserver.api_v2.filebrowser_api.DirectoryListing')
    def test_fetch_directory_listing_success(self, mock_listing_cls):
        mock_listing_cls.return_value.fetch_path_data.return_value = {
            'directories': [{'name': 'dir'}],
            'files': [{'name': 'file'}],
        }

        resp = self.post_json('/filebrowser/list', {'current_path': '/tmp', 'list_type': 'all'})

        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['directories'][0]['name'] == 'dir'
        assert data['files'][0]['name'] == 'file'

    def test_fetch_directory_listing_invalid_json(self):
        resp = self.fetch(
            '/compresso/api/v2/filebrowser/list',
            method='POST',
            body='not json',
            headers={'Content-Type': 'application/json'},
        )

        assert resp.code == 400

    @patch('compresso.webserver.api_v2.filebrowser_api.DirectoryListing')
    def test_fetch_directory_listing_internal_error(self, mock_listing_cls):
        mock_listing_cls.return_value.fetch_path_data.side_effect = Exception('boom')

        resp = self.post_json('/filebrowser/list', {'current_path': '/tmp'})

        assert resp.code == 500


@pytest.mark.unittest
class TestFileinfoApiCoverage(ApiTestBase):
    __test__ = True
    handler_class = ApiFileinfoHandler

    @staticmethod
    def _make_direct_handler(call_method):
        handler = object.__new__(ApiFileinfoHandler)
        handler.route = {'call_method': call_method}
        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.write_success = MagicMock()
        handler.build_response = MagicMock(return_value={})
        return handler

    @patch('compresso.webserver.api_v2.fileinfo_api.fileinfo.probe_and_format')
    @patch('compresso.webserver.api_v2.fileinfo_api.os.path.exists', return_value=True)
    def test_probe_file_success(self, _mock_exists, mock_probe):
        mock_probe.return_value = {
            'video_streams': [{'codec': 'h264'}],
            'audio_streams': [{'codec': 'aac'}],
            'subtitle_streams': [],
            'format': {'duration': '10.0'},
        }

        resp = self.post_json('/fileinfo/probe', {'file_path': '/tmp/video.mkv'})

        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['format']['duration'] == '10.0'

    @patch('compresso.webserver.api_v2.fileinfo_api.os.path.exists', return_value=False)
    def test_probe_file_missing_file(self, _mock_exists):
        resp = self.post_json('/fileinfo/probe', {'file_path': '/tmp/missing.mkv'})

        assert resp.code == 400

    @patch('compresso.webserver.api_v2.fileinfo_api.fileinfo.probe_and_format', return_value=None)
    @patch('compresso.webserver.api_v2.fileinfo_api.os.path.exists', return_value=True)
    def test_probe_file_ffprobe_failure(self, _mock_exists, _mock_probe):
        resp = self.post_json('/fileinfo/probe', {'file_path': '/tmp/video.mkv'})

        assert resp.code == 500

    @patch('compresso.webserver.api_v2.fileinfo_api.fileinfo.probe_and_format')
    @patch('compresso.webserver.api_v2.fileinfo_api.os.path.exists', return_value=True)
    def test_probe_task_file_success(self, _mock_exists, mock_probe):
        from compresso.libs.unmodels import CompletedTasks

        mock_probe.return_value = {
            'video_streams': [],
            'audio_streams': [],
            'subtitle_streams': [],
            'format': {'duration': '22.0'},
        }
        task = MagicMock()
        task.abspath = '/tmp/video.mkv'

        with patch.object(CompletedTasks, 'get_by_id', return_value=task):
            resp = self.post_json('/fileinfo/task', {'task_id': 1})

        assert resp.code == 200
        assert self.parse_response(resp)['format']['duration'] == '22.0'

    def test_probe_task_file_not_found(self):
        from compresso.libs.unmodels import CompletedTasks

        with patch.object(CompletedTasks, 'get_by_id', side_effect=CompletedTasks.DoesNotExist):
            resp = self.post_json('/fileinfo/task', {'task_id': 1})

        assert resp.code == 400

    def test_probe_task_file_missing_path(self):
        from compresso.libs.unmodels import CompletedTasks

        task = MagicMock()
        task.abspath = '/tmp/missing.mkv'
        with patch.object(CompletedTasks, 'get_by_id', return_value=task), \
             patch('compresso.webserver.api_v2.fileinfo_api.os.path.exists', return_value=False):
            resp = self.post_json('/fileinfo/task', {'task_id': 1})

        assert resp.code == 400

    def test_probe_file_handles_base_api_error(self):
        handler = self._make_direct_handler('probe_file')
        handler.read_json_request = MagicMock(side_effect=BaseApiError('bad request'))

        asyncio.run(ApiFileinfoHandler.probe_file(handler))

        handler.set_status.assert_called_once()
        handler.write_error.assert_called_once()

    def test_probe_file_handles_generic_exception(self):
        handler = self._make_direct_handler('probe_file')
        handler.read_json_request = MagicMock(return_value={'file_path': '/tmp/video.mkv'})

        with patch('compresso.webserver.api_v2.fileinfo_api.os.path.exists', return_value=True), \
             patch('compresso.webserver.api_v2.fileinfo_api.fileinfo.probe_and_format', side_effect=Exception('boom')):
            asyncio.run(ApiFileinfoHandler.probe_file(handler))

        handler.set_status.assert_called_once()
        handler.write_error.assert_called_once()

    def test_probe_task_file_ffprobe_failure_sets_error(self):
        from compresso.libs.unmodels import CompletedTasks

        task = MagicMock()
        task.abspath = '/tmp/video.mkv'
        with patch.object(CompletedTasks, 'get_by_id', return_value=task), \
             patch('compresso.webserver.api_v2.fileinfo_api.os.path.exists', return_value=True), \
             patch('compresso.webserver.api_v2.fileinfo_api.fileinfo.probe_and_format', return_value=None):
            resp = self.post_json('/fileinfo/task', {'task_id': 1})

        assert resp.code == 500

    def test_probe_task_file_handles_base_api_error(self):
        handler = self._make_direct_handler('probe_task_file')
        handler.read_json_request = MagicMock(side_effect=BaseApiError('bad request'))

        asyncio.run(ApiFileinfoHandler.probe_task_file(handler))

        handler.set_status.assert_called_once()
        handler.write_error.assert_called_once()

    def test_probe_task_file_handles_generic_exception(self):
        handler = self._make_direct_handler('probe_task_file')
        handler.read_json_request = MagicMock(return_value={'task_id': 1})

        with patch('compresso.libs.unmodels.CompletedTasks.get_by_id', side_effect=Exception('boom')):
            asyncio.run(ApiFileinfoHandler.probe_task_file(handler))

        handler.set_status.assert_called_once()
        handler.write_error.assert_called_once()


@pytest.mark.unittest
@patch.object(ApiNotificationsHandler, 'initialize', _mock_notifications_initialize)
class TestNotificationsApiCoverage(ApiTestBase):
    __test__ = True
    handler_class = ApiNotificationsHandler

    @staticmethod
    def _make_direct_handler(call_method):
        handler = object.__new__(ApiNotificationsHandler)
        handler.route = {'call_method': call_method}
        handler.set_status = MagicMock()
        handler.write_error = MagicMock()
        handler.write_success = MagicMock()
        handler.build_response = MagicMock(return_value={})
        return handler

    @patch('compresso.webserver.api_v2.notifications_api.Notifications')
    def test_get_notifications_success(self, mock_notifications_cls):
        mock_notifications_cls.return_value.read_all_items.return_value = [
            {
                'uuid': 'older',
                'type': 'info',
                'icon': 'info',
                'label': 'older_label',
                'message': 'older_message',
                'navigation': {},
            },
            {
                'uuid': 'newer',
                'type': 'info',
                'icon': 'info',
                'label': 'newer_label',
                'message': 'newer_message',
                'navigation': {},
            },
        ]

        resp = self.get_json('/notifications/read')

        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['notifications'][0]['uuid'] == 'newer'

    @patch('compresso.webserver.api_v2.notifications_api.Notifications')
    def test_get_notifications_internal_error(self, mock_notifications_cls):
        mock_notifications_cls.return_value.read_all_items.side_effect = Exception('boom')

        resp = self.get_json('/notifications/read')

        assert resp.code == 500

    @patch('compresso.webserver.api_v2.notifications_api.Notifications')
    def test_remove_notifications_success(self, mock_notifications_cls):
        mock_notifications_cls.return_value.remove.return_value = True

        resp = self.fetch(
            '/compresso/api/v2/notifications/remove',
            method='DELETE',
            body=json.dumps({'uuid_list': ['a', 'b']}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )

        assert resp.code == 200

    @patch('compresso.webserver.api_v2.notifications_api.Notifications')
    def test_remove_notifications_failure(self, mock_notifications_cls):
        mock_notifications_cls.return_value.remove.return_value = False

        resp = self.fetch(
            '/compresso/api/v2/notifications/remove',
            method='DELETE',
            body=json.dumps({'uuid_list': ['a']}),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )

        assert resp.code == 400

    def test_remove_notifications_invalid_json(self):
        resp = self.fetch(
            '/compresso/api/v2/notifications/remove',
            method='DELETE',
            body='not json',
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )

        assert resp.code == 400

    def test_get_notifications_handles_base_api_error(self):
        handler = self._make_direct_handler('get_notifications')
        handler.build_response.side_effect = BaseApiError('bad request')

        with patch('compresso.webserver.api_v2.notifications_api.Notifications') as mock_notifications:
            mock_notifications.return_value.read_all_items.return_value = []
            asyncio.run(ApiNotificationsHandler.get_notifications(handler))

        handler.set_status.assert_called_once()

    def test_remove_notifications_handles_generic_exception(self):
        handler = self._make_direct_handler('remove_notifications')
        handler.read_json_request = MagicMock(return_value={'uuid_list': ['uuid-1']})

        with patch('compresso.webserver.api_v2.notifications_api.Notifications', side_effect=Exception('boom')):
            asyncio.run(ApiNotificationsHandler.remove_notifications(handler))

        handler.set_status.assert_called_once()
        handler.write_error.assert_called_once()
