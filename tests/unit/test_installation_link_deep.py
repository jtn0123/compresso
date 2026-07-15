#!/usr/bin/env python3

"""
tests.unit.test_installation_link_deep.py

Deep unit tests for compresso/libs/installation_link.py
covering RemoteTaskManager, Links config management,
transfer methods, and remote worker management.
"""

import hashlib
import json
import queue
from unittest.mock import MagicMock, mock_open, patch

import pytest
import requests

from compresso.libs.installation_link import Links, RemoteTaskManager
from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _create_links():
    with (
        patch("compresso.libs.installation_link.config.Config"),
        patch("compresso.libs.installation_link.session.Session"),
        patch("compresso.libs.installation_link.CompressoLogging.get_logger"),
    ):
        return Links()


# ==================================================================
# Links.__merge_config_dicts
# ==================================================================


@pytest.mark.unittest
class TestMergeConfigDicts:
    def test_updates_changed_values(self):
        links = _create_links()
        config = {"a": 1, "b": 2, "last_updated": 0}
        compare = {"a": 3, "b": 2}
        links._Links__merge_config_dicts(config, compare)
        assert config["a"] == 3
        assert config["last_updated"] != 0

    def test_does_not_update_same_values(self):
        links = _create_links()
        config = {"a": 1, "b": 2, "last_updated": 0}
        compare = {"a": 1, "b": 2}
        links._Links__merge_config_dicts(config, compare)
        assert config["last_updated"] == 0

    def test_ignores_none_in_compare(self):
        links = _create_links()
        config = {"a": 1, "last_updated": 0}
        compare = {"a": None}
        links._Links__merge_config_dicts(config, compare)
        assert config["a"] == 1

    def test_updates_multiple_keys(self):
        links = _create_links()
        config = {"x": "old", "y": "old", "last_updated": 0}
        compare = {"x": "new", "y": "new"}
        links._Links__merge_config_dicts(config, compare)
        assert config["x"] == "new"
        assert config["y"] == "new"

    def test_compare_missing_key_ignored(self):
        links = _create_links()
        config = {"a": 1, "b": 2, "last_updated": 0}
        compare = {"a": 1}
        links._Links__merge_config_dicts(config, compare)
        assert config["b"] == 2


# ==================================================================
# Links._log
# ==================================================================


@pytest.mark.unittest
class TestLinksLog:
    def test_log_calls_logger(self):
        links = _create_links()
        links.logger = MagicMock()
        with patch("compresso.libs.installation_link.common.format_message", return_value="formatted"):
            links._log("test message", level="warning")
        links.logger.warning.assert_called_once_with("formatted")

    def test_log_defaults_to_info(self):
        links = _create_links()
        links.logger = MagicMock()
        with patch("compresso.libs.installation_link.common.format_message", return_value="msg"):
            links._log("test")
        links.logger.info.assert_called_once()


# ==================================================================
# Links.read_remote_installation_link_config
# ==================================================================


@pytest.mark.unittest
class TestReadRemoteInstallationLinkConfig:
    def test_returns_config_for_matching_uuid(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [{"uuid": "uuid-1", "address": "10.0.0.1", "name": "Server1"}]
        result = links.read_remote_installation_link_config("uuid-1")
        assert result["address"] == "10.0.0.1"

    def test_raises_when_uuid_not_found(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = []
        with pytest.raises(Exception, match="Unable to read"):
            links.read_remote_installation_link_config("nonexistent")


# ==================================================================
# Links.update_single_remote_installation_link_config
# ==================================================================


@pytest.mark.unittest
class TestUpdateSingleRemoteInstallationLinkConfig:
    def test_raises_without_uuid(self):
        links = _create_links()
        with pytest.raises(Exception, match="requires a UUID"):
            links.update_single_remote_installation_link_config({})

    def test_updates_existing_config(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [{"uuid": "uuid-1", "address": "10.0.0.1", "name": "Old"}]
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.update_single_remote_installation_link_config(
            {"uuid": "uuid-1", "name": "New"}, distributed_worker_count_target=0
        )
        links.settings.set_bulk_config_items.assert_called_once()

    def test_adds_new_config_when_uuid_not_found(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = []
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.update_single_remote_installation_link_config(
            {"uuid": "new-uuid", "address": "10.0.0.2"}, distributed_worker_count_target=0
        )
        call_args = links.settings.set_bulk_config_items.call_args
        remote_list = call_args[0][0]["remote_installations"]
        assert len(remote_list) == 1

    def test_force_update_flag_when_worker_count_changes(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [
            {"uuid": "uuid-1", "address": "10.0.0.1", "enable_distributed_worker_count": True}
        ]
        links.settings.get_distributed_worker_count_target.return_value = 2
        links.update_single_remote_installation_link_config(
            {"uuid": "uuid-1", "enable_distributed_worker_count": True}, distributed_worker_count_target=5
        )
        links.settings.set_bulk_config_items.assert_called_once()


# ==================================================================
# Links.delete_remote_installation_link_config
# ==================================================================


@pytest.mark.unittest
class TestDeleteRemoteInstallationLinkConfig:
    def test_removes_matching_uuid(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [
            {"uuid": "uuid-1", "address": "10.0.0.1"},
            {"uuid": "uuid-2", "address": "10.0.0.2"},
        ]
        result = links.delete_remote_installation_link_config("uuid-1")
        assert result is True
        call_args = links.settings.set_bulk_config_items.call_args
        remaining = call_args[0][0]["remote_installations"]
        assert len(remaining) == 1
        assert remaining[0]["uuid"] == "uuid-2"

    def test_returns_false_when_uuid_not_found(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = []
        result = links.delete_remote_installation_link_config("nonexistent")
        assert result is False


# ==================================================================
# Links.fetch_remote_installation_link_config_for_this
# ==================================================================


@pytest.mark.unittest
class TestFetchRemoteInstallationLinkConfigForThis:
    def test_returns_json_on_200(self):
        links = _create_links()
        links.session = MagicMock()
        links.session.uuid = "local-uuid"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"link_config": {"uuid": "local-uuid"}}
        with patch("compresso.libs.installation_link.requests.post", return_value=mock_resp):
            config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
            result = links.fetch_remote_installation_link_config_for_this(config)
            assert result == {"link_config": {"uuid": "local-uuid"}}

    def test_returns_empty_on_error(self):
        links = _create_links()
        links.session = MagicMock()
        links.session.uuid = "local-uuid"
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": "fail", "traceback": []}
        with patch("compresso.libs.installation_link.requests.post", return_value=mock_resp):
            config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
            result = links.fetch_remote_installation_link_config_for_this(config)
            assert result == {}


# ==================================================================
# Links.push_remote_installation_link_config
# ==================================================================


@pytest.mark.unittest
class TestPushRemoteInstallationLinkConfig:
    def test_returns_true_on_200(self):
        links = _create_links()
        links.session = MagicMock()
        links.session.uuid = "local-uuid"
        links.settings = MagicMock()
        links.settings.get_installation_name.return_value = "TestInstall"
        links.settings.read_version.return_value = "1.0"
        links.settings.get_distributed_worker_count_target.return_value = 0
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with (
            patch("compresso.libs.installation_link.requests.post", return_value=mock_resp),
            patch("compresso.libs.installation_link.task.Task") as mock_task_cls,
        ):
            mock_task_cls.return_value.get_total_task_list_count.return_value = 5
            config = {
                "address": "host:8888",
                "auth": "",
                "username": "",
                "password": "",
                "enable_sending_tasks": True,
                "enable_receiving_tasks": False,
            }
            result = links.push_remote_installation_link_config(config)
            assert result is True

    def test_returns_false_on_error(self):
        links = _create_links()
        links.session = MagicMock()
        links.session.uuid = "local-uuid"
        links.settings = MagicMock()
        links.settings.get_installation_name.return_value = "X"
        links.settings.read_version.return_value = "1.0"
        links.settings.get_distributed_worker_count_target.return_value = 0
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": "fail", "traceback": []}
        with (
            patch("compresso.libs.installation_link.requests.post", return_value=mock_resp),
            patch("compresso.libs.installation_link.task.Task") as mock_task_cls,
        ):
            mock_task_cls.return_value.get_total_task_list_count.return_value = 0
            config = {
                "address": "host:8888",
                "auth": "",
                "username": "",
                "password": "",
                "enable_sending_tasks": False,
                "enable_receiving_tasks": False,
            }
            result = links.push_remote_installation_link_config(config)
            assert result is False


# ==================================================================
# Links.new_pending_task_create_on_remote_installation
# ==================================================================


@pytest.mark.unittest
class TestNewPendingTaskCreate:
    def test_includes_stable_job_and_lease_identity(self):
        links = _create_links()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"id": 42}
        with patch("compresso.libs.installation_link.requests.post", return_value=mock_resp) as post:
            config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
            links.new_pending_task_create_on_remote_installation(
                config,
                "/path/to/file",
                1,
                job_id="job-1",
                lease_token="lease-1",  # noqa: S106 - synthetic lease fixture
                origin_installation_uuid="master-1",
            )

        assert post.call_args.kwargs["json"]["job_id"] == "job-1"
        assert post.call_args.kwargs["json"]["lease_token"] == "lease-1"  # noqa: S105 - synthetic fixture
        assert post.call_args.kwargs["json"]["origin_installation_uuid"] == "master-1"

    def test_returns_json_on_success(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 42}
        with patch("compresso.libs.installation_link.requests.post", return_value=mock_resp):
            config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
            result = links.new_pending_task_create_on_remote_installation(config, "/path/to/file", 1)
            assert result == {"id": 42}

    def test_returns_empty_dict_on_404(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"error": "not found", "traceback": []}
        with patch("compresso.libs.installation_link.requests.post", return_value=mock_resp):
            config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
            result = links.new_pending_task_create_on_remote_installation(config, "/path", 1)
            assert result == {}

    def test_returns_none_on_timeout(self):
        links = _create_links()
        with patch("compresso.libs.installation_link.requests.post", side_effect=requests.exceptions.Timeout):
            config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
            result = links.new_pending_task_create_on_remote_installation(config, "/path", 1)
            assert result is None

    def test_returns_none_on_request_exception(self):
        links = _create_links()
        with patch("compresso.libs.installation_link.requests.post", side_effect=requests.exceptions.ConnectionError):
            config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
            result = links.new_pending_task_create_on_remote_installation(config, "/path", 1)
            assert result is None

    def test_returns_json_on_400(self):
        links = _create_links()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {"error": "task already exists"}
        with patch("compresso.libs.installation_link.requests.post", return_value=mock_resp):
            config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
            result = links.new_pending_task_create_on_remote_installation(config, "/path", 1)
            assert result == {"error": "task already exists"}


# ==================================================================
# Links.send_file_to_remote_installation
# ==================================================================


@pytest.mark.unittest
class TestSendFileToRemoteInstallation:
    def test_resumable_upload_continues_from_remote_offset(self, tmp_path):
        payload = b"abcdefghij"
        source = tmp_path / "movie.mkv"
        source.write_bytes(payload)
        links = _create_links()
        transfer_id = "a" * 32
        links.remote_api_post = MagicMock(
            side_effect=[
                {"transfer_id": transfer_id, "offset": 4, "complete": False},
                {"id": 7, "status": "creating", "checksum": "verified"},
            ]
        )
        offsets = []

        def append_chunk(_config, _endpoint, data, headers):
            offsets.append((int(headers["X-Transfer-Offset"]), data))
            return {"offset": int(headers["X-Transfer-Offset"]) + len(data)}

        links.remote_api_post_bytes = MagicMock(side_effect=append_chunk)

        result = links._send_file_resumable({}, str(source), "job-1", chunk_size=3)

        assert result["id"] == 7
        assert offsets == [(4, b"efg"), (7, b"hij")]

    def test_resumable_upload_stops_when_lease_heartbeat_fails(self, tmp_path):
        source = tmp_path / "movie.mkv"
        source.write_bytes(b"abcdefghij")
        links = _create_links()
        links.remote_api_post = MagicMock(return_value={"transfer_id": "a" * 32, "offset": 0, "complete": False})
        links.remote_api_post_bytes = MagicMock(return_value={"offset": 3})

        result = links._send_file_resumable({}, str(source), "job-1", chunk_size=3, progress_callback=lambda: False)

        assert result == {}
        links.remote_api_post.assert_called_once()

    def test_resumable_download_continues_existing_partial_file(self, tmp_path):
        payload = b"abcdefghij"
        destination = tmp_path / "movie.mkv"
        (tmp_path / "movie.mkv.part").write_bytes(payload[:4])
        links = _create_links()
        links.settings.get_cache_path.return_value = str(tmp_path)
        links.remote_api_get = MagicMock(
            return_value={
                "total_size": len(payload),
                "checksum": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            }
        )
        responses = []
        for chunk in (payload[4:7], payload[7:]):
            response = MagicMock(status_code=200, content=chunk)
            response.headers = {"X-Chunk-Checksum": f"sha256:{hashlib.sha256(chunk).hexdigest()}"}
            responses.append(response)
        request_handler = MagicMock()
        request_handler.get.side_effect = responses

        with patch("compresso.libs.installation_link.RequestHandler", return_value=request_handler):
            success = links.fetch_remote_task_completed_file_resumable({}, 7, str(destination), chunk_size=3)

        assert success is True
        assert destination.read_bytes() == payload
        assert not (tmp_path / "movie.mkv.part").exists()

    def test_resumable_download_stops_when_lease_heartbeat_fails(self, tmp_path):
        payload = b"abcdefghij"
        destination = tmp_path / "movie.mkv"
        links = _create_links()
        links.settings.get_cache_path.return_value = str(tmp_path)
        links.remote_api_get = MagicMock(
            return_value={
                "total_size": len(payload),
                "checksum": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            }
        )
        response = MagicMock(status_code=200, content=payload[:3])
        response.headers = {"X-Chunk-Checksum": f"sha256:{hashlib.sha256(payload[:3]).hexdigest()}"}
        request_handler = MagicMock()
        request_handler.get.return_value = response

        with patch("compresso.libs.installation_link.RequestHandler", return_value=request_handler):
            success = links.fetch_remote_task_completed_file_resumable(
                {}, 7, str(destination), chunk_size=3, progress_callback=lambda: False
            )

        assert success is False
        assert (tmp_path / "movie.mkv.part").read_bytes() == payload[:3]

    def test_resumable_download_discards_full_corrupt_partial_for_next_retry(self, tmp_path):
        payload = b"good"
        destination = tmp_path / "movie.mkv"
        partial = tmp_path / "movie.mkv.part"
        partial.write_bytes(b"bad!")
        links = _create_links()
        links.settings.get_cache_path.return_value = str(tmp_path)
        links.remote_api_get = MagicMock(
            return_value={
                "total_size": len(payload),
                "checksum": f"sha256:{hashlib.sha256(payload).hexdigest()}",
            }
        )

        assert links.fetch_remote_task_completed_file_resumable({}, 7, str(destination)) is False
        assert not partial.exists()

    def test_resumable_download_rejects_destination_outside_cache(self, tmp_path):
        links = _create_links()
        links.settings.get_cache_path.return_value = str(tmp_path / "cache")
        links.remote_api_get = MagicMock(return_value={"total_size": 0, "checksum": "sha256:empty"})

        with pytest.raises(ValueError, match="inside the Compresso cache"):
            links.fetch_remote_task_completed_file_resumable({}, 7, str(tmp_path / "outside.mkv"))

    def test_resumable_download_rejects_malformed_manifest_size(self, tmp_path):
        destination = tmp_path / "movie.mkv"
        links = _create_links()
        links.settings.get_cache_path.return_value = str(tmp_path)
        links.remote_api_get = MagicMock(
            return_value={
                "total_size": -1,
                "checksum": f"sha256:{hashlib.sha256(b'').hexdigest()}",
            }
        )

        assert links.fetch_remote_task_completed_file_resumable({}, 7, str(destination)) is False
        assert not destination.exists()

    def test_resumable_download_rejects_chunk_beyond_declared_size(self, tmp_path):
        declared = b"data"
        oversized = b"data!"
        destination = tmp_path / "movie.mkv"
        links = _create_links()
        links.settings.get_cache_path.return_value = str(tmp_path)
        links.remote_api_get = MagicMock(
            return_value={
                "total_size": len(declared),
                "checksum": f"sha256:{hashlib.sha256(oversized).hexdigest()}",
            }
        )
        response = MagicMock(status_code=200, content=oversized)
        response.headers = {"X-Chunk-Checksum": f"sha256:{hashlib.sha256(oversized).hexdigest()}"}
        request_handler = MagicMock()
        request_handler.get.return_value = response

        with patch("compresso.libs.installation_link.RequestHandler", return_value=request_handler):
            assert links.fetch_remote_task_completed_file_resumable({}, 7, str(destination)) is False

        assert not destination.exists()

    def test_resumable_download_rejects_cache_root_as_file_destination(self, tmp_path):
        cache_root = tmp_path / "cache"
        cache_root.mkdir()
        sibling_partial = tmp_path / "cache.part"
        links = _create_links()
        links.settings.get_cache_path.return_value = str(cache_root)
        links.remote_api_get = MagicMock(
            return_value={
                "total_size": 0,
                "checksum": f"sha256:{hashlib.sha256(b'').hexdigest()}",
            }
        )

        with pytest.raises(ValueError, match="inside the Compresso cache"):
            links.fetch_remote_task_completed_file_resumable({}, 7, str(cache_root))

        assert not sibling_partial.exists()

    def test_uses_resumable_protocol_for_stable_remote_job(self):
        links = _create_links()
        links._send_file_resumable = MagicMock(return_value={"id": 5, "checksum": "abc"})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}

        links.send_file_to_remote_installation(
            config,
            "/path/to/file",
            job_id="job-1",
            lease_token="lease-1",  # noqa: S106 - synthetic lease fixture
            origin_installation_uuid="master-1",
        )

        links._send_file_resumable.assert_called_once_with(
            config,
            "/path/to/file",
            "job-1",
            lease_token="lease-1",  # noqa: S106 - synthetic lease fixture
            origin_installation_uuid="master-1",
        )

    def test_rejects_distributed_upload_without_stable_job_id(self):
        links = _create_links()
        links.remote_api_post_file = MagicMock()
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}

        result = links.send_file_to_remote_installation(config, "/path/to/file")

        assert result == {}
        links.remote_api_post_file.assert_not_called()

    def test_returns_results_on_success(self):
        links = _create_links()
        links._send_file_resumable = MagicMock(return_value={"id": 5, "checksum": "abc"})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.send_file_to_remote_installation(config, "/path/to/file", job_id="job-1")
        assert result == {"id": 5, "checksum": "abc"}

    def test_returns_empty_when_resumable_transfer_is_interrupted(self):
        links = _create_links()
        links._send_file_resumable = MagicMock(return_value={})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.send_file_to_remote_installation(config, "/path/to/file", job_id="job-1")
        assert result == {}

    def test_returns_empty_on_request_exception(self):
        links = _create_links()
        links._send_file_resumable = MagicMock(side_effect=requests.exceptions.ConnectionError)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.send_file_to_remote_installation(config, "/path/to/file", job_id="job-1")
        assert result == {}


# ==================================================================
# Links.remove_task_from_remote_installation
# ==================================================================


@pytest.mark.unittest
class TestRemoveTaskFromRemote:
    def test_calls_api_delete(self):
        links = _create_links()
        links.remote_api_delete = MagicMock(return_value={"success": True})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.remove_task_from_remote_installation(config, 42)
        links.remote_api_delete.assert_called_once()
        assert result == {"success": True}

    def test_returns_none_on_timeout(self):
        links = _create_links()
        links.remote_api_delete = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.remove_task_from_remote_installation(config, 42)
        assert result is None

    def test_returns_none_on_request_exception(self):
        links = _create_links()
        links.remote_api_delete = MagicMock(side_effect=requests.exceptions.ConnectionError)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.remove_task_from_remote_installation(config, 42)
        assert result is None

    def test_returns_empty_on_generic_exception(self):
        links = _create_links()
        links.remote_api_delete = MagicMock(side_effect=Exception("oops"))
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.remove_task_from_remote_installation(config, 42)
        assert result == {}


# ==================================================================
# Links.get_the_remote_library_config_by_name
# ==================================================================


@pytest.mark.unittest
class TestGetRemoteLibraryConfigByName:
    def test_returns_matching_library(self):
        links = _create_links()
        links.remote_api_get = MagicMock(return_value={"libraries": [{"name": "Movies", "id": 1}, {"name": "TV", "id": 2}]})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_the_remote_library_config_by_name(config, "TV")
        assert result == {"name": "TV", "id": 2}

    def test_returns_empty_when_not_found(self):
        links = _create_links()
        links.remote_api_get = MagicMock(return_value={"libraries": [{"name": "Movies", "id": 1}]})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_the_remote_library_config_by_name(config, "Music")
        assert result == {}

    def test_returns_none_on_timeout(self):
        links = _create_links()
        links.remote_api_get = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_the_remote_library_config_by_name(config, "Movies")
        assert result is None


# ==================================================================
# Links.set_the_remote_task_library
# ==================================================================


@pytest.mark.unittest
class TestSetRemoteTaskLibrary:
    def test_returns_results_on_success(self):
        links = _create_links()
        links.remote_api_post = MagicMock(return_value={"success": True})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.set_the_remote_task_library(config, 42, "Movies")
        assert result == {"success": True}

    def test_returns_empty_on_error_in_result(self):
        links = _create_links()
        links.remote_api_post = MagicMock(return_value={"error": "bad"})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.set_the_remote_task_library(config, 42, "Movies")
        assert result == {}

    def test_returns_none_on_timeout(self):
        links = _create_links()
        links.remote_api_post = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.set_the_remote_task_library(config, 42, "Movies")
        assert result is None


# ==================================================================
# Links.get_remote_pending_task_state
# ==================================================================


@pytest.mark.unittest
class TestGetRemotePendingTaskState:
    def test_returns_results_on_success(self):
        links = _create_links()
        links.remote_api_post = MagicMock(return_value={"results": [{"id": 1, "status": "pending"}]})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_remote_pending_task_state(config, 1)
        assert result == {"results": [{"id": 1, "status": "pending"}]}

    def test_returns_none_on_timeout(self):
        links = _create_links()
        links.remote_api_post = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_remote_pending_task_state(config, 1)
        assert result is None


# ==================================================================
# Links.start_the_remote_task_by_id
# ==================================================================


@pytest.mark.unittest
class TestStartRemoteTaskById:
    def test_returns_results_on_success(self):
        links = _create_links()
        links.remote_api_post = MagicMock(return_value={"success": True})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.start_the_remote_task_by_id(config, 42)
        assert result == {"success": True}

    def test_returns_empty_on_error_in_result(self):
        links = _create_links()
        links.remote_api_post = MagicMock(return_value={"error": "fail"})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.start_the_remote_task_by_id(config, 42)
        assert result == {}

    def test_returns_none_on_timeout(self):
        links = _create_links()
        links.remote_api_post = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.start_the_remote_task_by_id(config, 42)
        assert result is None


# ==================================================================
# Links.get_all_worker_status
# ==================================================================


@pytest.mark.unittest
class TestGetAllWorkerStatus:
    def test_returns_worker_list(self):
        links = _create_links()
        links.remote_api_get = MagicMock(return_value={"workers_status": [{"id": "w1", "idle": True}]})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_all_worker_status(config)
        assert result == [{"id": "w1", "idle": True}]

    def test_returns_empty_list_on_timeout(self):
        links = _create_links()
        links.remote_api_get = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_all_worker_status(config)
        assert result == []


# ==================================================================
# Links.get_single_worker_status
# ==================================================================


@pytest.mark.unittest
class TestGetSingleWorkerStatus:
    def test_returns_matching_worker(self):
        links = _create_links()
        links.get_all_worker_status = MagicMock(return_value=[{"id": "w1", "idle": True}, {"id": "w2", "idle": False}])
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_single_worker_status(config, "w2")
        assert result == {"id": "w2", "idle": False}

    def test_returns_empty_when_not_found(self):
        links = _create_links()
        links.get_all_worker_status = MagicMock(return_value=[{"id": "w1"}])
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.get_single_worker_status(config, "w99")
        assert result == {}


# ==================================================================
# Links.terminate_remote_worker
# ==================================================================


@pytest.mark.unittest
class TestTerminateRemoteWorker:
    def test_calls_api_delete(self):
        links = _create_links()
        links.remote_api_delete = MagicMock(return_value={"success": True})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.terminate_remote_worker(config, "w1")
        assert result == {"success": True}

    def test_returns_empty_on_timeout(self):
        links = _create_links()
        links.remote_api_delete = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.terminate_remote_worker(config, "w1")
        assert result == {}


# ==================================================================
# Links.fetch_remote_task_data
# ==================================================================


@pytest.mark.unittest
class TestFetchRemoteTaskData:
    def test_returns_task_data_on_success(self):
        links = _create_links()
        links.remote_api_get = MagicMock(return_value={"link_id": "dl-123"})
        links.remote_api_get_download = MagicMock(return_value=True)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        task_data = {"log": "test log", "task_success": True}
        with patch("os.path.exists", return_value=True), patch("builtins.open", mock_open(read_data=json.dumps(task_data))):
            result = links.fetch_remote_task_data(config, 42, "/tmp/data.json")
            assert result == task_data

    def test_returns_empty_when_no_link_id(self):
        links = _create_links()
        links.remote_api_get = MagicMock(return_value={})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.fetch_remote_task_data(config, 42, "/tmp/data.json")
        assert result == {}

    def test_returns_empty_on_timeout(self):
        links = _create_links()
        links.remote_api_get = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.fetch_remote_task_data(config, 42, "/tmp/data.json")
        assert result == {}


# ==================================================================
# Links.fetch_remote_task_completed_file
# ==================================================================


@pytest.mark.unittest
class TestFetchRemoteTaskCompletedFile:
    def test_returns_true_on_success(self):
        links = _create_links()
        links.remote_api_get = MagicMock(return_value={"link_id": "dl-456"})
        links.remote_api_get_download = MagicMock(return_value=True)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        with patch("os.path.exists", return_value=True):
            result = links.fetch_remote_task_completed_file(config, 42, "/tmp/output.mkv")
            assert result is True

    def test_returns_false_when_no_link_id(self):
        links = _create_links()
        links.remote_api_get = MagicMock(return_value={})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.fetch_remote_task_completed_file(config, 42, "/tmp/out.mkv")
        assert result is False

    def test_returns_false_on_timeout(self):
        links = _create_links()
        links.remote_api_get = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.fetch_remote_task_completed_file(config, 42, "/tmp/out.mkv")
        assert result is False


# ==================================================================
# Links.import_remote_library_config
# ==================================================================


@pytest.mark.unittest
class TestImportRemoteLibraryConfig:
    def test_returns_results_on_success(self):
        links = _create_links()
        links.remote_api_post = MagicMock(return_value={"success": True})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.import_remote_library_config(config, {"library_id": 0})
        assert result == {"success": True}

    def test_returns_empty_when_error_in_result(self):
        links = _create_links()
        links.remote_api_post = MagicMock(return_value={"error": "bad"})
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.import_remote_library_config(config, {"library_id": 0})
        assert result == {}

    def test_returns_none_on_timeout(self):
        links = _create_links()
        links.remote_api_post = MagicMock(side_effect=requests.exceptions.Timeout)
        config = {"address": "host:8888", "auth": "", "username": "", "password": ""}
        result = links.import_remote_library_config(config, {})
        assert result is None


# ==================================================================
# Links.check_remote_installation_for_available_workers
# ==================================================================


@pytest.mark.unittest
class TestCheckRemoteInstallationForAvailableWorkers:
    def test_returns_empty_when_not_available(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [
            {"available": False, "enable_sending_tasks": True, "uuid": "a" * 21, "address": "10.0.0.1"}
        ]
        result = links.check_remote_installation_for_available_workers()
        assert result == {}

    def test_returns_empty_when_sending_disabled(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [
            {"available": True, "enable_sending_tasks": False, "uuid": "a" * 21, "address": "10.0.0.1"}
        ]
        result = links.check_remote_installation_for_available_workers()
        assert result == {}

    def test_returns_empty_when_uuid_too_short(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_remote_installations.return_value = [
            {"available": True, "enable_sending_tasks": True, "uuid": "short", "address": "10.0.0.1"}
        ]
        result = links.check_remote_installation_for_available_workers()
        assert result == {}

    def test_includes_remote_capabilities_and_scheduling_score(self):
        links = _create_links()
        links.settings = MagicMock()
        remote_uuid = "a" * 21
        links.settings.get_remote_installations.return_value = [
            {
                "available": True,
                "enable_sending_tasks": True,
                "uuid": remote_uuid,
                "address": "10.0.0.1",
            }
        ]
        links.remote_api_get = MagicMock(
            side_effect=[
                {"workers_status": [{"idle": True, "paused": False}]},
                {"libraries": [{"name": "Movies"}]},
                {
                    "video_encoders": ["hevc_videotoolbox"],
                    "cpu": {"percent": 10},
                    "memory": {"percent": 20},
                    "cache_disk": {"free_bytes": 100 * 1024**3},
                },
            ]
        )
        links.remote_api_post = MagicMock(return_value={"recordsFiltered": 0})

        result = links.check_remote_installation_for_available_workers()

        assert result[remote_uuid]["capabilities"]["video_encoders"] == ["hevc_videotoolbox"]
        assert result[remote_uuid]["scheduling_score"] > 0


# ==================================================================
# RemoteTaskManager.__init__
# ==================================================================


@pytest.mark.unittest
class TestRemoteTaskManagerInit:
    def test_init_sets_attributes(self):
        pending_q = queue.Queue(maxsize=1)
        complete_q = queue.Queue()
        event = MagicMock()
        info = {"address": "10.0.0.1", "uuid": "uuid-1"}
        with (
            patch("compresso.libs.remote_task_manager.Links"),
            patch("compresso.libs.remote_task_manager.CompressoLogging.get_logger"),
        ):
            mgr = RemoteTaskManager("thread-1", "RTM-1", info, pending_q, complete_q, event)
        assert mgr.thread_id == "thread-1"
        assert mgr.name == "RTM-1"
        assert mgr.installation_info == info
        assert not mgr.redundant_flag.is_set()
        assert not mgr.paused_flag.is_set()

    def test_get_info(self):
        pending_q = queue.Queue(maxsize=1)
        complete_q = queue.Queue()
        event = MagicMock()
        info = {"address": "10.0.0.1", "uuid": "uuid-1"}
        with (
            patch("compresso.libs.remote_task_manager.Links"),
            patch("compresso.libs.remote_task_manager.CompressoLogging.get_logger"),
        ):
            mgr = RemoteTaskManager("thread-1", "RTM-1", info, pending_q, complete_q, event)
        result = mgr.get_info()
        assert result["name"] == "RTM-1"
        assert result["installation_info"] == info


# ==================================================================
# RemoteTaskManager.run - empty queue
# ==================================================================


@pytest.mark.unittest
class TestRemoteTaskManagerRun:
    def test_run_with_empty_queue_logs_warning(self):
        pending_q = queue.Queue(maxsize=1)
        complete_q = queue.Queue()
        event = MagicMock()
        info = {"address": "10.0.0.1", "uuid": "uuid-1"}
        with (
            patch("compresso.libs.remote_task_manager.Links"),
            patch("compresso.libs.remote_task_manager.CompressoLogging.get_logger"),
        ):
            mgr = RemoteTaskManager("t-1", "RTM-1", info, pending_q, complete_q, event)
            mgr._log = MagicMock()
            mgr.run()
            # Should log the empty queue warning
            calls = [c[0][0] for c in mgr._log.call_args_list]
            assert any("empty" in c.lower() for c in calls)


# ==================================================================
# RemoteTaskManager.__set_current_task / __unset_current_task
# ==================================================================


@pytest.mark.unittest
class TestRemoteTaskManagerTaskManagement:
    def _make_rtm(self):
        pending_q = queue.Queue(maxsize=1)
        complete_q = queue.Queue()
        event = MagicMock()
        info = {"address": "10.0.0.1", "uuid": "uuid-1"}
        with (
            patch("compresso.libs.remote_task_manager.Links"),
            patch("compresso.libs.remote_task_manager.CompressoLogging.get_logger"),
            patch("compresso.libs.remote_task_manager.PluginsHandler"),
        ):
            mgr = RemoteTaskManager("t-1", "RTM-1", info, pending_q, complete_q, event)
        return mgr

    def test_set_current_task(self):
        mgr = self._make_rtm()
        mock_task = MagicMock()
        mock_task.get_task_library_id.return_value = 1
        mock_task.get_task_id.return_value = 42
        mock_task.get_task_type.return_value = "local"
        mock_task.get_source_data.return_value = {}
        with patch("compresso.libs.remote_task_manager.PluginsHandler"):
            mgr._RemoteTaskManager__set_current_task(mock_task)
        assert mgr.current_task is mock_task
        assert len(mgr.worker_log) == 0

    def test_unset_current_task(self):
        mgr = self._make_rtm()
        mgr.current_task = MagicMock()
        mgr.worker_runners_info = {"a": 1}
        mgr.worker_log = ["line1"]
        mgr._RemoteTaskManager__unset_current_task()
        assert mgr.current_task is None
        assert mgr.worker_runners_info == {}
        assert len(mgr.worker_log) == 0


# ==================================================================
# RemoteTaskManager.__set_start_task_stats / __set_finish_task_stats
# ==================================================================


@pytest.mark.unittest
class TestRemoteTaskManagerStats:
    def _make_rtm(self):
        pending_q = queue.Queue(maxsize=1)
        complete_q = queue.Queue()
        event = MagicMock()
        info = {"address": "10.0.0.1"}
        with (
            patch("compresso.libs.remote_task_manager.Links"),
            patch("compresso.libs.remote_task_manager.CompressoLogging.get_logger"),
        ):
            mgr = RemoteTaskManager("t-1", "RTM-1", info, pending_q, complete_q, event)
        return mgr

    def test_set_start_task_stats(self):
        mgr = self._make_rtm()
        mgr.current_task = MagicMock()
        mgr._RemoteTaskManager__set_start_task_stats()
        assert mgr.start_time is not None
        assert mgr.finish_time is None
        assert mgr.current_task.task.processed_by_worker == "RTM-1"

    def test_set_finish_task_stats(self):
        mgr = self._make_rtm()
        mgr.current_task = MagicMock()
        mgr._RemoteTaskManager__set_finish_task_stats()
        assert mgr.finish_time is not None


# ==================================================================
# RemoteTaskManager.__write_failure_to_worker_log
# ==================================================================


@pytest.mark.unittest
class TestRemoteTaskManagerWriteFailure:
    def test_appends_failure_log_lines(self):
        pending_q = queue.Queue(maxsize=1)
        complete_q = queue.Queue()
        event = MagicMock()
        info = {"address": "10.0.0.1"}
        with (
            patch("compresso.libs.remote_task_manager.Links"),
            patch("compresso.libs.remote_task_manager.CompressoLogging.get_logger"),
        ):
            mgr = RemoteTaskManager("t-1", "RTM-1", info, pending_q, complete_q, event)
        mgr.worker_log = []
        mgr.current_task = MagicMock()
        mgr._RemoteTaskManager__write_failure_to_worker_log()
        assert len(mgr.worker_log) > 0
        assert any("FAILED" in line for line in mgr.worker_log)
        mgr.current_task.save_command_log.assert_called_once()


# ==================================================================
# Links.update_all_remote_installation_links
# ==================================================================


@pytest.mark.unittest
class TestUpdateAllRemoteInstallationLinks:
    def test_skips_duplicate_uuids(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "uuid-1", "address": "10.0.0.1"},
            {"uuid": "uuid-1", "address": "10.0.0.2"},
        ]
        links.validate_remote_installation = MagicMock(return_value=None)
        result = links.update_all_remote_installation_links()
        # Only one should remain
        assert len(result) == 1

    def test_skips_empty_address(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "uuid-1", "address": ""},
        ]
        result = links.update_all_remote_installation_links()
        assert len(result) == 0

    def test_skips_unknown_address_and_uuid(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "???", "address": "???"},
        ]
        result = links.update_all_remote_installation_links()
        assert len(result) == 0

    def test_marks_unavailable_on_exception(self):
        links = _create_links()
        links.settings = MagicMock()
        links.settings.get_distributed_worker_count_target.return_value = 0
        links.settings.get_remote_installations.return_value = [
            {"uuid": "uuid-1", "address": "10.0.0.1"},
        ]
        links.validate_remote_installation = MagicMock(side_effect=Exception("connection failed"))
        result = links.update_all_remote_installation_links()
        assert len(result) == 1
        assert result[0]["available"] is False


# ==================================================================
# Links.remote_api_post_file — file handle leak fix
# ==================================================================


@pytest.mark.unittest
class TestRemoteApiPostFileHandleLeak:
    def test_file_handle_closed_on_success(self, tmp_path):
        links = _create_links()
        test_file = tmp_path / "test.mkv"
        test_file.write_bytes(b"fake video data")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1}
        mock_fh = MagicMock()

        with (
            patch("compresso.libs.installation_link.RequestHandler") as MockRH,
            patch("compresso.libs.installation_link.MultipartEncoder"),
            patch("builtins.open", return_value=mock_fh),
        ):
            MockRH.return_value.post.return_value = mock_response
            links.remote_api_post_file(
                {"address": "http://host:8888", "auth": "", "username": "", "password": ""}, "/api/upload", str(test_file)
            )
            mock_fh.__exit__.assert_called_once()

    def test_file_handle_closed_on_post_exception(self, tmp_path):
        links = _create_links()
        test_file = tmp_path / "test.mkv"
        test_file.write_bytes(b"fake video data")
        mock_fh = MagicMock()

        with (
            patch("compresso.libs.installation_link.RequestHandler") as MockRH,
            patch("compresso.libs.installation_link.MultipartEncoder"),
            patch("builtins.open", return_value=mock_fh),
        ):
            MockRH.return_value.post.side_effect = Exception("connection error")
            with pytest.raises(Exception, match="connection error"):
                links.remote_api_post_file(
                    {"address": "http://host:8888", "auth": "", "username": "", "password": ""}, "/api/upload", str(test_file)
                )
            mock_fh.__exit__.assert_called_once()


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
