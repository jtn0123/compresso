#!/usr/bin/env python3

"""Contracts for retired media ingress and bounded ordinary plugin uploads."""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unittest
def test_upload_routes_are_split_between_retired_media_and_plugin_handlers():
    from compresso.webserver.api_v2.upload_api import ApiPluginUploadHandler, ApiUploadHandler

    assert [route["path_pattern"] for route in ApiUploadHandler.routes] == [r"/upload/pending/file"]
    assert [route["path_pattern"] for route in ApiPluginUploadHandler.routes] == [r"/upload/plugin/file"]


@pytest.mark.unittest
def test_pending_file_upload_returns_410_with_resumable_successors():
    from compresso.webserver.api_v2.upload_api import ApiUploadHandler

    handler = ApiUploadHandler.__new__(ApiUploadHandler)
    handler._finished = False
    handler.set_status = MagicMock()
    handler.finish = MagicMock()

    asyncio.run(handler.retire_pending_upload())

    handler.set_status.assert_called_once_with(410)
    response = handler.finish.call_args.args[0]
    assert response["successor"]["create"] == "/compresso/api/v2/transfer/session"
    assert response["successor"]["chunk"].startswith("/compresso/api/v2/transfer/chunk/")


@pytest.mark.unittest
def test_plugin_upload_requires_one_framework_parsed_file(tmp_path):
    from compresso.webserver.api_v2.upload_api import ApiPluginUploadHandler

    handler = ApiPluginUploadHandler.__new__(ApiPluginUploadHandler)
    handler.request = SimpleNamespace(files={}, headers={})
    handler.config = MagicMock()
    handler.config.get_cache_path.return_value = str(tmp_path)
    handler.handle_base_api_error = MagicMock()

    asyncio.run(handler.upload_and_install_plugin())

    assert handler.handle_base_api_error.call_args.args[0].status_code == 400


@pytest.mark.unittest
def test_plugin_upload_rejects_payload_above_64_mib_before_install(tmp_path):
    from compresso.webserver.api_v2.upload_api import MAX_PLUGIN_UPLOAD_SIZE, ApiPluginUploadHandler

    handler = ApiPluginUploadHandler.__new__(ApiPluginUploadHandler)
    handler.request = SimpleNamespace(
        files={"file": [SimpleNamespace(filename="plugin.zip", body=b"x", content_type="application/zip")]},
        headers={"Content-Length": str(MAX_PLUGIN_UPLOAD_SIZE + 1)},
    )
    handler.config = MagicMock()
    handler.config.get_cache_path.return_value = str(tmp_path)
    handler.handle_base_api_error = MagicMock()

    with patch("compresso.libs.plugins.PluginsHandler.install_plugin_from_path_on_disk") as install:
        asyncio.run(handler.upload_and_install_plugin())

    install.assert_not_called()
    assert handler.handle_base_api_error.call_args.args[0].status_code == 413


@pytest.mark.unittest
def test_plugin_upload_uses_framework_parsed_file_and_cleans_temporary_copy(tmp_path):
    from compresso.webserver.api_v2.upload_api import ApiPluginUploadHandler

    handler = ApiPluginUploadHandler.__new__(ApiPluginUploadHandler)
    handler.request = SimpleNamespace(
        files={"file": [SimpleNamespace(filename="plugin.zip", body=b"zip-data", content_type="application/zip")]},
        headers={"Content-Length": "8"},
    )
    handler.config = MagicMock()
    handler.config.get_cache_path.return_value = str(tmp_path)
    handler.write_success = MagicMock()
    handler.handle_base_api_error = MagicMock()
    observed_paths = []

    def install(path):
        observed_paths.append(path)
        assert path.read_bytes() == b"zip-data"
        return True

    with patch("compresso.libs.plugins.PluginsHandler.install_plugin_from_path_on_disk", side_effect=install):
        asyncio.run(handler.upload_and_install_plugin())

    handler.write_success.assert_called_once()
    assert observed_paths
    assert not observed_paths[0].exists()


@pytest.mark.unittest
def test_plugin_upload_install_failure_is_structured_and_cleans_temporary_copy(tmp_path):
    from compresso.webserver.api_v2.upload_api import ApiPluginUploadHandler

    handler = ApiPluginUploadHandler.__new__(ApiPluginUploadHandler)
    handler.request = SimpleNamespace(
        files={"file": [SimpleNamespace(filename="plugin.zip", body=b"bad-zip", content_type="application/zip")]},
        headers={"Content-Length": "7"},
    )
    handler.config = MagicMock()
    handler.config.get_cache_path.return_value = str(tmp_path)
    handler.handle_base_api_error = MagicMock()

    with patch("compresso.libs.plugins.PluginsHandler.install_plugin_from_path_on_disk", return_value=False):
        asyncio.run(handler.upload_and_install_plugin())

    assert handler.handle_base_api_error.call_args.args[0].status_code == 400
    assert list((tmp_path / "plugin_uploads").iterdir()) == []


@pytest.mark.unittest
def test_plugin_install_calls_are_serialized(tmp_path):
    from compresso.webserver.api_v2.upload_api import _install_plugin_serialized

    state_lock = threading.Lock()
    state = {"active": 0, "maximum": 0}

    def install(_path):
        with state_lock:
            state["active"] += 1
            state["maximum"] = max(state["maximum"], state["active"])
        time.sleep(0.02)
        with state_lock:
            state["active"] -= 1
        return True

    plugins = SimpleNamespace(install_plugin_from_path_on_disk=install)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: _install_plugin_serialized(plugins, tmp_path), range(2)))

    assert results == [True, True]
    assert state["maximum"] == 1
