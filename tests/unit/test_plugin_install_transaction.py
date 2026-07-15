#!/usr/bin/env python3

"""Adversarial contracts for transactional plugin installation."""

import json
import stat
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.singleton import SingletonType


@pytest.fixture(autouse=True)
def reset_singletons():
    SingletonType._instances = {}
    yield
    SingletonType._instances = {}


def _make_handler(tmp_path):
    with patch("compresso.libs.plugins.config") as mock_config_mod:
        settings = MagicMock()
        settings.get_plugins_path.return_value = str(tmp_path / "plugins")
        mock_config_mod.Config.return_value = settings
        with patch("compresso.libs.plugins.CompressoLogging"):
            from compresso.libs.plugins import PluginsHandler

            return PluginsHandler()


def _info(plugin_id="safe_plugin", **overrides):
    info = {
        "id": plugin_id,
        "name": "Safe Plugin",
        "author": "Compresso",
        "version": "1.0.0",
        "tags": "worker,test",
        "description": "A test plugin",
        "icon": "",
        "compatibility": [2],
    }
    info.update(overrides)
    return info


def _archive(path, info=None, members=None, compression=zipfile.ZIP_STORED):
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        archive.writestr("info.json", json.dumps(info or _info()))
        for name, payload in members or [("plugin.py", "")]:
            archive.writestr(name, payload)
    return path


def _install_with_fake_db(handler, archive, **patches):
    snapshot = patches.pop("snapshot", None)
    executor = MagicMock()
    contexts = [
        patch.object(handler, "_snapshot_plugin_record", return_value=snapshot),
        patch.object(handler, "write_plugin_data_to_db", return_value=True),
        patch("compresso.libs.plugins.PluginExecutor", return_value=executor),
    ]
    with contexts[0] as snapshot_mock, contexts[1] as write_mock, contexts[2]:
        result = handler.install_plugin(str(archive))
    return result, snapshot_mock, write_mock, executor


@pytest.mark.unittest
class TestPluginArchiveValidation:
    @pytest.mark.parametrize(
        ("member", "message"),
        [
            ("../escape", "unsafe path"),
            ("/absolute", "unsafe path"),
            (r"..\escape", "unsafe path"),
        ],
    )
    def test_rejects_unsafe_paths_before_touching_live_plugin(self, tmp_path, member, message):
        handler = _make_handler(tmp_path)
        live = tmp_path / "plugins" / "safe_plugin"
        live.mkdir(parents=True)
        (live / "marker").write_text("old")
        archive = _archive(tmp_path / "unsafe.zip", members=[(member, "bad")])

        with pytest.raises(ValueError, match=message):
            handler.install_plugin(str(archive))

        assert (live / "marker").read_text() == "old"

    def test_rejects_duplicate_normalized_paths(self, tmp_path):
        handler = _make_handler(tmp_path)
        archive = _archive(tmp_path / "duplicate.zip", members=[("Plugin.py", "one"), ("plugin.py", "two")])

        with pytest.raises(ValueError, match="duplicate path"):
            handler.install_plugin(str(archive))

    @pytest.mark.parametrize("file_type", [stat.S_IFLNK, stat.S_IFIFO, stat.S_IFCHR])
    def test_rejects_links_and_special_files(self, tmp_path, file_type):
        handler = _make_handler(tmp_path)
        archive_path = tmp_path / "special.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("info.json", json.dumps(_info()))
            member = zipfile.ZipInfo("special")
            member.create_system = 3
            member.external_attr = (file_type | 0o600) << 16
            archive.writestr(member, "target")

        with pytest.raises(ValueError, match="forbidden file type"):
            handler.install_plugin(str(archive_path))

    def test_rejects_encrypted_member_flag(self, tmp_path):
        handler = _make_handler(tmp_path)
        archive_path = _archive(tmp_path / "encrypted.zip")
        payload = bytearray(archive_path.read_bytes())
        local = payload.index(b"PK\x03\x04")
        central = payload.index(b"PK\x01\x02")
        payload[local + 6 : local + 8] = (1).to_bytes(2, "little")
        payload[central + 8 : central + 10] = (1).to_bytes(2, "little")
        archive_path.write_bytes(payload)

        with pytest.raises(ValueError, match="encrypted"):
            handler.install_plugin(str(archive_path))

    @pytest.mark.parametrize(
        "info",
        [
            [],
            {"id": "../bad", "compatibility": [2]},
            _info(compatibility=[1]),
            _info(compatibility="2"),
            {"id": "safe_plugin", "compatibility": [2]},
        ],
    )
    def test_rejects_invalid_or_incompatible_metadata(self, tmp_path, info):
        handler = _make_handler(tmp_path)
        archive_path = tmp_path / "bad-info.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("info.json", json.dumps(info))

        with pytest.raises(ValueError):
            handler.install_plugin(str(archive_path))

    def test_rejects_malformed_or_missing_metadata(self, tmp_path):
        handler = _make_handler(tmp_path)
        malformed = tmp_path / "malformed.zip"
        missing = tmp_path / "missing.zip"
        with zipfile.ZipFile(malformed, "w") as archive:
            archive.writestr("info.json", "{")
        with zipfile.ZipFile(missing, "w") as archive:
            archive.writestr("plugin.py", "")

        with pytest.raises(ValueError, match="info.json"):
            handler.install_plugin(str(malformed))
        with pytest.raises(ValueError, match="info.json"):
            handler.install_plugin(str(missing))

    def test_rejects_requested_id_mismatch(self, tmp_path):
        handler = _make_handler(tmp_path)
        archive = _archive(tmp_path / "mismatch.zip")

        with pytest.raises(ValueError, match="does not match"):
            handler.install_plugin(str(archive), "another_plugin")

    @pytest.mark.parametrize(
        ("constant", "value", "message"),
        [
            ("MAX_PLUGIN_ARCHIVE_BYTES", 1, "compressed size"),
            ("MAX_PLUGIN_ARCHIVE_ENTRIES", 1, "too many entries"),
            ("MAX_PLUGIN_EXPANDED_BYTES", 1, "expanded size"),
            ("MAX_PLUGIN_ENTRY_BYTES", 1, "entry is too large"),
            ("MAX_PLUGIN_INFO_BYTES", 1, "info.json is too large"),
        ],
    )
    def test_enforces_archive_size_and_entry_bounds(self, tmp_path, constant, value, message):
        handler = _make_handler(tmp_path)
        archive = _archive(tmp_path / f"{constant}.zip")

        with patch(f"compresso.libs.plugins.{constant}", value), pytest.raises(ValueError, match=message):
            handler.install_plugin(str(archive))

    def test_rejects_high_compression_ratio(self, tmp_path):
        handler = _make_handler(tmp_path)
        archive = _archive(
            tmp_path / "ratio.zip",
            members=[("payload.bin", b"0" * 100_000)],
            compression=zipfile.ZIP_DEFLATED,
        )

        with pytest.raises(ValueError, match="compression ratio"):
            handler.install_plugin(str(archive))


@pytest.mark.unittest
class TestTransactionalPluginInstall:
    def test_dependencies_run_in_staging_before_atomic_promotion(self, tmp_path):
        handler = _make_handler(tmp_path)
        archive = _archive(
            tmp_path / "plugin.zip",
            _info(defer_dependency_install=True, bundled=True),
            [("requirements.lock", ""), ("package-lock.json", "{}"), ("package.json", "{}")],
        )
        dependency_paths = []

        with (
            patch.object(handler, "install_plugin_requirements", side_effect=lambda path, **_: dependency_paths.append(path)),
            patch.object(handler, "install_npm_modules", side_effect=lambda path: dependency_paths.append(path)),
        ):
            result, _snapshot, write, executor = _install_with_fake_db(handler, archive)

        live = tmp_path / "plugins" / "safe_plugin"
        assert result["bundled"] is False
        assert dependency_paths
        assert all(Path(path).name.startswith(".safe_plugin.staging-") for path in dependency_paths)
        assert json.loads((live / "info.json").read_text())["bundled"] is False
        assert write.call_args.args[1] == str(live)
        executor.reload_plugin_module.assert_called_once_with("safe_plugin")
        assert not list((tmp_path / "plugins").glob(".safe_plugin.*-*"))

    def test_dependency_failure_leaves_live_plugin_and_database_untouched(self, tmp_path):
        handler = _make_handler(tmp_path)
        live = tmp_path / "plugins" / "safe_plugin"
        live.mkdir(parents=True)
        (live / "marker").write_text("old")
        archive = _archive(tmp_path / "plugin.zip", _info(defer_dependency_install=True))

        with (
            patch.object(handler, "install_plugin_requirements", side_effect=RuntimeError("pip failed")),
            patch.object(handler, "_snapshot_plugin_record") as snapshot,
            patch.object(handler, "write_plugin_data_to_db") as write,
            pytest.raises(RuntimeError, match="pip failed"),
        ):
            handler.install_plugin(str(archive))

        assert (live / "marker").read_text() == "old"
        snapshot.assert_not_called()
        write.assert_not_called()

    @pytest.mark.parametrize("failure", ["database", "reload"])
    def test_post_swap_failure_restores_directory_database_and_module(self, tmp_path, failure):
        handler = _make_handler(tmp_path)
        live = tmp_path / "plugins" / "safe_plugin"
        live.mkdir(parents=True)
        (live / "marker").write_text("old")
        archive = _archive(tmp_path / "plugin.zip", members=[("marker", "new")])
        snapshot = {"plugin_id": "safe_plugin", "name": "Old"}
        executor = MagicMock()
        if failure == "reload":
            executor.reload_plugin_module.side_effect = [RuntimeError("reload failed"), None]

        with (
            patch.object(handler, "_snapshot_plugin_record", return_value=snapshot),
            patch.object(handler, "_restore_plugin_record") as restore,
            patch.object(
                handler,
                "write_plugin_data_to_db",
                side_effect=RuntimeError("database failed") if failure == "database" else None,
            ),
            patch("compresso.libs.plugins.PluginExecutor", return_value=executor),
            pytest.raises(RuntimeError, match=f"{failure} failed"),
        ):
            handler.install_plugin(str(archive))

        assert (live / "marker").read_text() == "old"
        restore.assert_called_once_with("safe_plugin", snapshot)
        executor.reload_plugin_module.assert_called_with("safe_plugin")
        assert not list((tmp_path / "plugins").glob(".safe_plugin.*-*"))

    def test_same_plugin_installs_serialize_but_different_plugins_do_not(self, tmp_path):
        handler = _make_handler(tmp_path)
        state_lock = threading.Lock()
        active_by_id = {}
        maximum_by_id = {}
        active_total = 0
        maximum_total = 0

        def critical(plugin_id):
            nonlocal active_total, maximum_total
            with handler._plugin_install_lock(plugin_id):
                with state_lock:
                    active_by_id[plugin_id] = active_by_id.get(plugin_id, 0) + 1
                    maximum_by_id[plugin_id] = max(maximum_by_id.get(plugin_id, 0), active_by_id[plugin_id])
                    active_total += 1
                    maximum_total = max(maximum_total, active_total)
                time.sleep(0.03)
                with state_lock:
                    active_by_id[plugin_id] -= 1
                    active_total -= 1

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(critical, ["same", "same", "other-a", "other-b"]))

        assert maximum_by_id["same"] == 1
        assert maximum_total >= 2


@pytest.mark.unittest
def test_download_rejects_oversized_stream_and_removes_partial_file(tmp_path):
    handler = _make_handler(tmp_path)
    (tmp_path / "plugins").mkdir()
    payload = b"12345"
    response = MagicMock()
    response.__enter__.return_value = response
    response.iter_content.return_value = [payload]
    session = MagicMock()
    session.requests_session.get.return_value = response
    plugin = {
        "plugin_id": "safe_plugin",
        "version": "1",
        "package_url": "https://example.invalid/plugin.zip",
        "package_sha256": "0" * 64,
    }

    with (
        patch("compresso.libs.plugins.Session", return_value=session),
        patch("compresso.libs.plugins.MAX_PLUGIN_ARCHIVE_BYTES", 4),
        pytest.raises(ValueError, match="compressed size"),
    ):
        handler.download_plugin(plugin)

    assert not (tmp_path / "plugins" / "safe_plugin-1.zip").exists()


@pytest.mark.unittest
def test_npm_dependencies_use_lockfile_without_lifecycle_scripts(tmp_path):
    from compresso.libs.plugins import PluginsHandler

    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "package-lock.json").write_text("{}")
    with patch("subprocess.call", return_value=0) as call:
        PluginsHandler.install_npm_modules(str(tmp_path))

    assert Path(call.call_args.args[0][0]).stem.casefold() == "npm"
    assert call.call_args.args[0][1:] == ["ci", "--ignore-scripts", "--omit=dev"]
    assert call.call_args.kwargs["cwd"] == str(tmp_path)


@pytest.mark.unittest
def test_plugin_sort_rejects_unknown_fields_before_query(tmp_path):
    handler = _make_handler(tmp_path)

    with patch("compresso.libs.plugins.Plugins.select") as select, pytest.raises(ValueError, match="sort field"):
        handler.get_plugin_list_filtered_and_sorted(order=[{"column": "__dict__", "dir": "asc"}])

    select.assert_not_called()
