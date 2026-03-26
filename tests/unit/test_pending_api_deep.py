#!/usr/bin/env python3

"""
    tests.unit.test_pending_api_deep.py

    Deep coverage tests for pending API routes not covered by test_pending_api.py.
    Covers: create_task_from_path, test_task_from_path, download links,
    all_filtered selection mode, and set_pending_library_by_name.
"""

import json
import queue
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v2.pending_api import ApiPendingHandler
from tests.unit.api_test_base import ApiTestBase

PENDING_HELPERS = 'compresso.webserver.helpers.pending_tasks'


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _mock_initialize(self, **kwargs):
    self.session = MagicMock()
    self.params = kwargs.get("params")
    q = queue.Queue(maxsize=1)
    self.compresso_data_queues = {
        'library_scanner_triggers': q,
    }


# ------------------------------------------------------------------
# Create task from path
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiCreateTask(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.create_task')
    @patch(PENDING_HELPERS + '.check_if_task_exists_matching_path', return_value=False)
    @patch('os.path.exists', return_value=True)
    def test_create_task_success(self, _exists, _check, mock_create):
        mock_create.return_value = {
            'id': 1, 'abspath': '/media/video.mp4',
            'priority': 100, 'type': 'local', 'status': 'pending',
        }
        resp = self.post_json('/pending/create', {
            'path': '/media/video.mp4',
            'library_id': 1,
            'type': 'local',
            'priority_score': 50,
        })
        assert resp.code == 200

    @patch('os.path.exists', return_value=False)
    def test_create_task_path_not_exists(self, _exists):
        resp = self.post_json('/pending/create', {
            'path': '/nonexistent/file.mp4',
        })
        assert resp.code == 400

    @patch(PENDING_HELPERS + '.check_if_task_exists_matching_path', return_value=True)
    @patch('os.path.exists', return_value=True)
    def test_create_task_already_exists(self, _exists, _check):
        resp = self.post_json('/pending/create', {
            'path': '/media/video.mp4',
        })
        assert resp.code == 400

    @patch(PENDING_HELPERS + '.create_task', return_value=None)
    @patch(PENDING_HELPERS + '.check_if_task_exists_matching_path', return_value=False)
    @patch('os.path.exists', return_value=True)
    def test_create_task_save_failure(self, _exists, _check, _create):
        resp = self.post_json('/pending/create', {
            'path': '/media/video.mp4',
        })
        assert resp.code == 400

    @patch(PENDING_HELPERS + '.create_task')
    @patch(PENDING_HELPERS + '.check_if_task_exists_matching_path', return_value=False)
    @patch('os.path.exists', return_value=True)
    def test_create_task_exception(self, _exists, _check, mock_create):
        mock_create.side_effect = Exception("DB error")
        resp = self.post_json('/pending/create', {
            'path': '/media/video.mp4',
        })
        assert resp.code == 500


# ------------------------------------------------------------------
# Delete with all_filtered selection mode
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiDeleteFiltered(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.remove_pending_tasks', return_value=True)
    @patch(PENDING_HELPERS + '.get_filtered_pending_task_ids', return_value=[1, 2, 3])
    def test_delete_all_filtered_success(self, _mock_filter, _mock_remove):
        resp = self.fetch(
            '/compresso/api/v2/pending/tasks',
            method='DELETE',
            body=json.dumps({
                'selection_mode': 'all_filtered',
                'search_value': '',
                'library_ids': [],
                'exclude_ids': [],
            }),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 200

    @patch(PENDING_HELPERS + '.get_filtered_pending_task_ids', return_value=[])
    def test_delete_all_filtered_empty_result(self, _mock_filter):
        resp = self.fetch(
            '/compresso/api/v2/pending/tasks',
            method='DELETE',
            body=json.dumps({
                'selection_mode': 'all_filtered',
                'search_value': '',
                'library_ids': [],
            }),
            headers={'Content-Type': 'application/json'},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 400


# ------------------------------------------------------------------
# Reorder with all_filtered selection mode
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiReorderFiltered(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.reorder_pending_tasks', return_value=True)
    @patch(PENDING_HELPERS + '.get_filtered_pending_task_ids', return_value=[1, 2])
    def test_reorder_all_filtered_success(self, _mock_filter, _mock_reorder):
        resp = self.post_json('/pending/reorder', {
            'selection_mode': 'all_filtered',
            'search_value': '',
            'library_ids': [],
            'position': 'top',
        })
        assert resp.code == 200

    @patch(PENDING_HELPERS + '.get_filtered_pending_task_ids', return_value=[])
    def test_reorder_all_filtered_empty(self, _mock_filter):
        resp = self.post_json('/pending/reorder', {
            'selection_mode': 'all_filtered',
            'search_value': '',
            'library_ids': [],
            'position': 'top',
        })
        assert resp.code == 400


# ------------------------------------------------------------------
# Download link - pending task file
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiDownloadFile(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch('compresso.webserver.api_v2.pending_api.DownloadsLinks')
    @patch(PENDING_HELPERS + '.fetch_tasks_status')
    def test_gen_download_link_file_success(self, mock_status, mock_dl):
        mock_status.return_value = [{'abspath': '/media/video.mp4', 'status': 'pending'}]
        mock_dl.return_value.generate_download_link.return_value = 'abc-123'
        resp = self.get_json('/pending/download/file/id/1')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['link_id'] == 'abc-123'

    @patch(PENDING_HELPERS + '.fetch_tasks_status', return_value=None)
    def test_gen_download_link_file_no_status(self, _mock_status):
        resp = self.get_json('/pending/download/file/id/1')
        assert resp.code == 500

    @patch(PENDING_HELPERS + '.fetch_tasks_status')
    def test_gen_download_link_file_error(self, mock_status):
        mock_status.side_effect = Exception("DB error")
        resp = self.get_json('/pending/download/file/id/1')
        assert resp.code == 500


# ------------------------------------------------------------------
# Download link - pending task data
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiDownloadData(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch('compresso.webserver.api_v2.pending_api.DownloadsLinks')
    @patch(PENDING_HELPERS + '.fetch_tasks_status')
    def test_gen_download_link_data_success(self, mock_status, mock_dl):
        mock_status.return_value = [{'abspath': '/media/video.mp4', 'status': 'complete'}]
        mock_dl.return_value.generate_download_link.return_value = 'xyz-789'
        resp = self.get_json('/pending/download/data/id/1')
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data['link_id'] == 'xyz-789'

    @patch(PENDING_HELPERS + '.fetch_tasks_status', return_value=None)
    def test_gen_download_link_data_no_status(self, _mock_status):
        resp = self.get_json('/pending/download/data/id/1')
        assert resp.code == 500

    @patch(PENDING_HELPERS + '.fetch_tasks_status')
    def test_gen_download_link_data_not_complete(self, mock_status):
        mock_status.return_value = [{'abspath': '/media/video.mp4', 'status': 'pending'}]
        resp = self.get_json('/pending/download/data/id/1')
        assert resp.code == 500


# ------------------------------------------------------------------
# Set pending library by name
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiSetLibrary(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.update_pending_tasks_library', return_value=True)
    def test_set_library_success(self, _mock_update):
        resp = self.post_json('/pending/library/update', {
            'id_list': [1, 2],
            'library_name': 'TV Shows',
        })
        assert resp.code == 200

    @patch(PENDING_HELPERS + '.update_pending_tasks_library', return_value=False)
    def test_set_library_failure(self, _mock_update):
        resp = self.post_json('/pending/library/update', {
            'id_list': [1],
            'library_name': 'TV Shows',
        })
        assert resp.code == 500

    @patch(PENDING_HELPERS + '.update_pending_tasks_library')
    def test_set_library_exception(self, mock_update):
        mock_update.side_effect = Exception("error")
        resp = self.post_json('/pending/library/update', {
            'id_list': [1],
            'library_name': 'TV Shows',
        })
        assert resp.code == 500


# ------------------------------------------------------------------
# Test task from path
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiTestTask(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.test_path_for_pending_task')
    @patch('os.path.exists', return_value=True)
    @patch('os.path.isabs', return_value=True)
    @patch('compresso.webserver.api_v2.pending_api.Library')
    def test_test_task_success(self, mock_lib_cls, _isabs, _exists, mock_test):
        mock_lib = MagicMock()
        mock_lib.get_id.return_value = 1
        mock_lib.get_name.return_value = 'Movies'
        mock_lib.get_path.return_value = '/movies'
        mock_lib_cls.return_value = mock_lib
        mock_test.return_value = {
            'add_file_to_pending_tasks': True,
            'issues': [],
            'decision_plugin': None,
        }
        resp = self.post_json('/pending/test', {
            'path': '/media/video.mp4',
            'library_id': 1,
        })
        assert resp.code == 200

    def test_test_task_no_library(self):
        resp = self.post_json('/pending/test', {
            'path': '/media/video.mp4',
        })
        assert resp.code == 400

    @patch('compresso.webserver.api_v2.pending_api.Library')
    def test_test_task_library_not_found_by_name(self, mock_lib_cls):
        mock_lib_cls.get_all_libraries.return_value = [
            {'id': 1, 'name': 'Movies'},
        ]
        resp = self.post_json('/pending/test', {
            'path': '/media/video.mp4',
            'library_name': 'NonExistent',
        })
        assert resp.code == 400

    @patch('os.path.exists', return_value=False)
    @patch('os.path.isabs', return_value=True)
    @patch('compresso.webserver.api_v2.pending_api.Library')
    def test_test_task_path_not_exists(self, mock_lib_cls, _isabs, _exists):
        mock_lib = MagicMock()
        mock_lib.get_id.return_value = 1
        mock_lib.get_name.return_value = 'Movies'
        mock_lib.get_path.return_value = '/movies'
        mock_lib_cls.return_value = mock_lib
        resp = self.post_json('/pending/test', {
            'path': '/nonexistent.mp4',
            'library_id': 1,
        })
        assert resp.code == 400

    @patch('compresso.webserver.api_v2.pending_api.Library')
    def test_test_task_library_exception(self, mock_lib_cls):
        mock_lib_cls.return_value = None
        mock_lib_cls.side_effect = Exception("Library not found")
        resp = self.post_json('/pending/test', {
            'path': '/media/video.mp4',
            'library_id': 999,
        })
        assert resp.code == 400


# ------------------------------------------------------------------
# Get pending status
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiGetStatus(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.fetch_tasks_status')
    def test_get_status_exception(self, mock_status):
        mock_status.side_effect = Exception("DB error")
        resp = self.post_json('/pending/status/get', {'id_list': [1]})
        assert resp.code == 500


# ------------------------------------------------------------------
# Set status as ready
# ------------------------------------------------------------------

@pytest.mark.unittest
@patch.object(ApiPendingHandler, 'initialize', _mock_initialize)
class TestPendingApiSetReadyExtended(ApiTestBase):
    __test__ = True
    handler_class = ApiPendingHandler

    @patch(PENDING_HELPERS + '.update_pending_tasks_status')
    def test_set_ready_exception(self, mock_update):
        mock_update.side_effect = Exception("DB error")
        resp = self.post_json('/pending/status/set/ready', {'id_list': [1]})
        assert resp.code == 500
