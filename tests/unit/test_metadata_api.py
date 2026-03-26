#!/usr/bin/env python3

"""
tests.unit.test_metadata_api.py

Unit tests for compresso.webserver.api_v2.metadata_api.ApiMetadataHandler.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType
from compresso.webserver.api_v2.metadata_api import ApiMetadataHandler
from tests.unit.api_test_base import ApiTestBase


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


META_API = "compresso.webserver.api_v2.metadata_api"


def _mock_initialize(self, **kwargs):
    """Stub out initialize."""
    self.params = kwargs.get("params")


# ------------------------------------------------------------------
# TestSearchMetadata
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _mock_initialize)
class TestSearchMetadata(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{META_API}.FileMetadataPaths")
    @patch(f"{META_API}.FileMetadata")
    def test_search_metadata_get_no_path(self, mock_fm, mock_fmp):
        """GET /metadata/search without path returns all results."""
        # Mock the query chain
        mock_base = MagicMock()
        mock_base.count.return_value = 0
        mock_base.order_by.return_value.limit.return_value.offset.return_value = []
        mock_fm.select.return_value = mock_base
        mock_fm.id = MagicMock()

        resp = self.get_json("/metadata/search")
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "results" in data
        assert "total_count" in data

    @patch(f"{META_API}.FileMetadataPaths")
    @patch(f"{META_API}.FileMetadata")
    def test_search_metadata_get_with_path(self, mock_fm, mock_fmp):
        """GET /metadata/search?path=/media returns filtered results."""
        mock_base = MagicMock()
        mock_base.count.return_value = 0
        mock_base.order_by.return_value.limit.return_value.offset.return_value = []
        mock_fm.select.return_value.join.return_value.where.return_value.distinct.return_value = mock_base

        resp = self.get_json("/metadata/search?path=/media")
        assert resp.code == 200

    @patch(f"{META_API}.FileMetadataPaths")
    @patch(f"{META_API}.FileMetadata")
    def test_search_metadata_post(self, mock_fm, mock_fmp):
        """POST /metadata/search with body returns results."""
        mock_base = MagicMock()
        mock_base.count.return_value = 0
        mock_base.order_by.return_value.limit.return_value.offset.return_value = []
        mock_fm.select.return_value.join.return_value.where.return_value.distinct.return_value = mock_base

        resp = self.post_json("/metadata/search", {"path": "/media"})
        assert resp.code == 200

    @patch(f"{META_API}.FileMetadataPaths")
    @patch(f"{META_API}.FileMetadata")
    def test_search_metadata_with_results(self, mock_fm, mock_fmp):
        """GET /metadata/search returns populated results when data exists."""
        mock_row_id = MagicMock()
        mock_row_id.id = 1
        mock_base = MagicMock()
        mock_base.count.return_value = 1
        mock_base.order_by.return_value.limit.return_value.offset.return_value = [mock_row_id]
        mock_fm.select.return_value = mock_base

        # Mock path map
        mock_path_row = MagicMock()
        mock_path_row.file_metadata.id = 1
        mock_path_row.path = "/media/test.mkv"
        mock_path_row.path_type = "source"
        mock_fmp.select.return_value.where.return_value = [mock_path_row]

        # Mock file metadata row
        mock_meta_row = MagicMock()
        mock_meta_row.id = 1
        mock_meta_row.fingerprint = "abc123"
        mock_meta_row.fingerprint_algo = "xxhash"
        mock_meta_row.metadata_json = "{}"
        mock_meta_row.last_task_id = 42

        with patch(f"{META_API}.CompressoFileMetadata._load_json_dict", return_value={}):
            mock_fm.select.return_value.where.return_value.order_by.return_value = [mock_meta_row]
            resp = self.get_json("/metadata/search")
            assert resp.code == 200

    @patch(f"{META_API}.FileMetadata")
    def test_search_metadata_bad_offset(self, mock_fm):
        """GET /metadata/search?offset=bad uses default offset."""
        mock_base = MagicMock()
        mock_base.count.return_value = 0
        mock_base.order_by.return_value.limit.return_value.offset.return_value = []
        mock_fm.select.return_value = mock_base

        resp = self.get_json("/metadata/search?offset=bad&limit=-1")
        assert resp.code == 200


# ------------------------------------------------------------------
# TestGetMetadataByTask
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _mock_initialize)
class TestGetMetadataByTask(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{META_API}.FileMetadataPaths")
    @patch(f"{META_API}.FileMetadata")
    @patch(f"{META_API}.CompletedTasks")
    def test_get_metadata_by_task_success(self, mock_ct, mock_fm, mock_fmp):
        """POST /metadata/by-task returns metadata for a task."""
        mock_task = MagicMock()
        mock_task.abspath = "/media/test.mkv"
        mock_ct.get_by_id.return_value = mock_task

        # No metadata found
        mock_fm.select.return_value.where.return_value = []
        mock_fmp.select.return_value.where.return_value = []

        resp = self.post_json("/metadata/by-task", {"task_id": 1})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert "results" in data

    @patch(f"{META_API}.CompletedTasks")
    def test_get_metadata_by_task_not_found(self, mock_ct):
        """POST /metadata/by-task returns 400 if task not found."""

        # Create a real exception class for DoesNotExist
        class DoesNotExist(Exception):
            pass

        mock_ct.DoesNotExist = DoesNotExist
        mock_ct.get_by_id.side_effect = DoesNotExist
        resp = self.post_json("/metadata/by-task", {"task_id": 999})
        assert resp.code == 400

    @patch(f"{META_API}.FileMetadataPaths")
    @patch(f"{META_API}.FileMetadata")
    @patch(f"{META_API}.CompletedTasks")
    def test_get_metadata_by_task_id_url_param(self, mock_ct, mock_fm, mock_fmp):
        """GET /metadata/by-task/42 returns metadata for task 42."""
        mock_task = MagicMock()
        mock_task.abspath = "/media/test.mkv"
        mock_ct.get_by_id.return_value = mock_task

        mock_fm.select.return_value.where.return_value = []
        mock_fmp.select.return_value.where.return_value = []

        resp = self.get_json("/metadata/by-task/42")
        assert resp.code == 200


# ------------------------------------------------------------------
# TestUpdateMetadata
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _mock_initialize)
class TestUpdateMetadata(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{META_API}.CompressoFileMetadata")
    @patch(f"{META_API}.FileMetadata")
    def test_update_metadata_success(self, mock_fm, mock_cfm):
        """POST /metadata/update returns 200 on success."""
        mock_row = MagicMock()
        mock_row.metadata_json = "{}"
        mock_fm.get_or_none.return_value = mock_row
        mock_cfm._load_json_dict.return_value = {}
        mock_cfm._dump_json_dict.return_value = '{"plugin1": {"key": "val"}}'
        mock_cfm._enforce_plugin_size_limit.return_value = None

        resp = self.post_json(
            "/metadata/update",
            {
                "fingerprint": "abc123",
                "plugin_id": "plugin1",
                "json_blob": {"key": "val"},
            },
        )
        assert resp.code == 200

    @patch(f"{META_API}.FileMetadata")
    def test_update_metadata_not_found(self, mock_fm):
        """POST /metadata/update returns 400 if fingerprint not found."""
        mock_fm.get_or_none.return_value = None

        with patch(f"{META_API}.CompressoFileMetadata._enforce_plugin_size_limit"):
            resp = self.post_json(
                "/metadata/update",
                {
                    "fingerprint": "missing",
                    "plugin_id": "plugin1",
                    "json_blob": {"key": "val"},
                },
            )
        assert resp.code == 400

    def test_update_metadata_invalid_json_blob(self):
        """POST /metadata/update returns 400 if json_blob is not dict."""
        resp = self.post_json(
            "/metadata/update",
            {
                "fingerprint": "abc123",
                "plugin_id": "plugin1",
                "json_blob": "not a dict",
            },
        )
        assert resp.code == 400

    @patch(f"{META_API}.CompressoFileMetadata")
    def test_update_metadata_size_limit_exceeded(self, mock_cfm):
        """POST /metadata/update returns 400 if size limit exceeded."""
        mock_cfm._enforce_plugin_size_limit.side_effect = ValueError("Too large")

        resp = self.post_json(
            "/metadata/update",
            {
                "fingerprint": "abc123",
                "plugin_id": "plugin1",
                "json_blob": {"key": "val"},
            },
        )
        assert resp.code == 400


# ------------------------------------------------------------------
# TestDeleteMetadata
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _mock_initialize)
class TestDeleteMetadata(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{META_API}.CompressoFileMetadata")
    def test_delete_metadata_success(self, mock_cfm):
        """DELETE /metadata returns 200."""
        mock_cfm.delete_for_plugin.return_value = True

        resp = self.fetch(
            "/compresso/api/v2/metadata",
            method="DELETE",
            body=json.dumps({"fingerprint": "abc123", "plugin_id": "plugin1"}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 200

    @patch(f"{META_API}.CompressoFileMetadata")
    def test_delete_metadata_not_found(self, mock_cfm):
        """DELETE /metadata returns 400 if fingerprint not found."""
        mock_cfm.delete_for_plugin.return_value = False

        resp = self.fetch(
            "/compresso/api/v2/metadata",
            method="DELETE",
            body=json.dumps({"fingerprint": "missing", "plugin_id": "plugin1"}),
            headers={"Content-Type": "application/json"},
            allow_nonstandard_methods=True,
        )
        assert resp.code == 400


# ------------------------------------------------------------------
# TestGetMetadataByFingerprint
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _mock_initialize)
class TestGetMetadataByFingerprint(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    @patch(f"{META_API}.CompressoFileMetadata._load_json_dict", return_value={})
    @patch(f"{META_API}.FileMetadataPaths")
    @patch(f"{META_API}.FileMetadata")
    def test_get_by_fingerprint_found(self, mock_fm, mock_fmp, mock_load):
        """POST /metadata/by-fingerprint returns results when found."""
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.fingerprint = "abc123"
        mock_row.fingerprint_algo = "xxhash"
        mock_row.metadata_json = "{}"
        mock_row.last_task_id = 42
        mock_fm.get_or_none.return_value = mock_row

        mock_path_row = MagicMock()
        mock_path_row.path = "/media/test.mkv"
        mock_path_row.path_type = "source"
        mock_fmp.select.return_value.where.return_value = [mock_path_row]

        resp = self.post_json("/metadata/by-fingerprint", {"fingerprint": "abc123"})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["total_count"] == 1

    @patch(f"{META_API}.FileMetadata")
    def test_get_by_fingerprint_not_found(self, mock_fm):
        """POST /metadata/by-fingerprint returns empty when not found."""
        mock_fm.get_or_none.return_value = None

        resp = self.post_json("/metadata/by-fingerprint", {"fingerprint": "missing"})
        assert resp.code == 200
        data = self.parse_response(resp)
        assert data["total_count"] == 0

    def test_get_by_fingerprint_empty_string(self):
        """POST /metadata/by-fingerprint with empty fingerprint returns 400."""
        resp = self.post_json("/metadata/by-fingerprint", {"fingerprint": ""})
        assert resp.code == 400


# ------------------------------------------------------------------
# TestMetadataApiEndpointNotFound
# ------------------------------------------------------------------


@pytest.mark.unittest
@patch.object(ApiMetadataHandler, "initialize", _mock_initialize)
class TestMetadataApiEndpointNotFound(ApiTestBase):
    __test__ = True
    handler_class = ApiMetadataHandler

    def test_unknown_endpoint_returns_404(self):
        resp = self.get_json("/metadata/nonexistent")
        assert resp.code == 404


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
