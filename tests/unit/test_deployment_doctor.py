# SPDX-License-Identifier: GPL-3.0-only

"""Behavior tests for the deployment readiness doctor."""

import json
import secrets
import socket
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open

import pytest

from compresso.ops import doctor
from compresso.ops.doctor import CheckResult, DeploymentDoctor, DoctorReport, load_latest_report


class FakeSettings:
    """Minimal settings surface used by deployment-doctor tests."""

    def __init__(self, root, *, scanner=True, address="127.0.0.1", remotes=None):
        self.root = root
        self.scanner = scanner
        self.address = address
        self.remotes = list(remotes or [])
        for name in ("config", "library", "cache", "userdata", "plugins"):
            (root / name).mkdir()

    def get_config_path(self):
        return str(self.root / "config")

    def get_library_path(self):
        return str(self.root / "library")

    def get_cache_path(self):
        return str(self.root / "cache")

    def get_userdata_path(self):
        return str(self.root / "userdata")

    def get_plugins_path(self):
        return str(self.root / "plugins")

    def get_minimum_free_space_gb(self):
        return 1

    def get_large_library_safe_defaults(self):
        return True

    def get_enable_library_scanner(self):
        return self.scanner

    def get_api_auth_enabled(self):
        return True

    def get_api_auth_token(self):
        return "do-not-export"

    def get_csrf_protection_enabled(self):
        return True

    def get_ui_address(self):
        return self.address

    def get_ssl_enabled(self):
        return False

    def get_remote_installations(self):
        return list(self.remotes)


def _addrinfo(ip):
    if ":" in ip:
        return [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (ip, 0, 0, 0))]
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]


def test_report_status_and_strict_warning_behavior():
    now = datetime(2026, 7, 12, tzinfo=UTC)
    warning = CheckResult("peer.optional", "network", "warn", False, "No peer supplied")

    normal = DoctorReport.create("master", [warning], now=now, strict=False)
    strict = DoctorReport.create("master", [warning], now=now, strict=True)

    assert normal.overall_status == "warn"
    assert normal.exit_code == 0
    assert strict.overall_status == "fail"
    assert strict.exit_code == 1
    assert strict.expires_at == now + timedelta(hours=24)


def test_report_redacts_nested_secret_values():
    report = DoctorReport.create(
        "master",
        [
            CheckResult(
                "security.auth",
                "security",
                "pass",
                True,
                "Authentication enabled",
                evidence={"api_auth_token": "secret", "nested": {"password": "hidden", "mode": "on"}},
            )
        ],
    )

    payload = report.to_dict()
    evidence = payload["checks"][0]["evidence"]
    redacted = "[" + "redacted]"
    assert evidence["api_auth_token"] == redacted
    assert evidence["nested"]["password"] == redacted
    assert evidence["nested"]["mode"] == "on"


def test_offline_master_report_is_persisted_atomically(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path)
    monkeypatch.setattr("compresso.ops.doctor.sys.version_info", (3, 13, 1))
    monkeypatch.setattr("compresso.ops.doctor.platform.system", lambda: "Linux")
    monkeypatch.setattr("compresso.ops.doctor.platform.machine", lambda: "x86_64")
    monkeypatch.setattr("compresso.ops.doctor.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "compresso.ops.doctor.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=10 * 1024**3, used=1, free=9 * 1024**3),
    )
    capabilities = {
        "video_encoders": ["libx264", "libx265"],
        "hardware_accelerators": [],
        "platform": {"system": "Linux", "machine": "x86_64"},
    }

    report = DeploymentDoctor(settings, "master", capability_probe=lambda _settings: capabilities).run()
    saved_path = report.save(settings.get_userdata_path())

    assert report.overall_status == "warn"
    assert saved_path.is_file()
    assert load_latest_report(settings.get_userdata_path())["report_id"] == report.report_id
    assert not list(saved_path.parent.glob("*.tmp"))


def test_worker_fails_when_scanner_is_enabled(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path, scanner=True)
    monkeypatch.setattr("compresso.ops.doctor.sys.version_info", (3, 13, 1))
    monkeypatch.setattr("compresso.ops.doctor.platform.system", lambda: "Darwin")
    monkeypatch.setattr("compresso.ops.doctor.platform.machine", lambda: "arm64")
    monkeypatch.setattr("compresso.ops.doctor.shutil.which", lambda name: f"/opt/homebrew/bin/{name}")
    monkeypatch.setattr(
        "compresso.ops.doctor.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=10 * 1024**3, used=1, free=9 * 1024**3),
    )
    capabilities = {
        "video_encoders": ["h264_videotoolbox", "hevc_videotoolbox"],
        "hardware_accelerators": ["videotoolbox"],
        "platform": {"system": "Darwin", "machine": "arm64"},
    }

    report = DeploymentDoctor(settings, "worker", capability_probe=lambda _settings: capabilities).run()

    scanner_check = next(check for check in report.checks if check.check_id == "role.worker_scanner_disabled")
    assert scanner_check.status == "fail"
    assert scanner_check.blocking is True
    assert report.exit_code == 1


def test_invalid_role_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="role"):
        DeploymentDoctor(FakeSettings(tmp_path), "scheduler")


def test_load_latest_report_rejects_malformed_root(tmp_path):
    readiness = tmp_path / "readiness"
    readiness.mkdir()
    (readiness / "latest.json").write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    assert load_latest_report(tmp_path) is None


def test_strict_master_passes_with_valid_database_and_ready_peer(tmp_path, monkeypatch):
    settings = FakeSettings(
        tmp_path,
        remotes=[{"name": "worker-m4", "uuid": "worker-uuid", "address": "http://worker.local:8888"}],
    )
    with sqlite3.connect(tmp_path / "config" / "compresso.db") as connection:
        connection.execute("CREATE TABLE readiness (id INTEGER PRIMARY KEY)")
    monkeypatch.setattr("compresso.ops.doctor.sys.version_info", (3, 13, 1))
    monkeypatch.setattr("compresso.ops.doctor.platform.system", lambda: "Linux")
    monkeypatch.setattr("compresso.ops.doctor.platform.machine", lambda: "x86_64")
    monkeypatch.setattr("compresso.ops.doctor.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "compresso.ops.doctor.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=10 * 1024**3, used=1, free=9 * 1024**3),
    )
    responses = []
    for payload in (
        {"success": True, "ready": True},
        {"version": doctor.metadata.read_version_string("short")},
        {"video_encoders": ["libx264"]},
    ):
        response = MagicMock(status_code=200)
        response.json.return_value = payload
        responses.append(response)
    get = MagicMock(side_effect=responses)
    monkeypatch.setattr("compresso.ops.doctor.requests.get", get)
    monkeypatch.setattr("compresso.ops.doctor.socket.getaddrinfo", MagicMock(return_value=_addrinfo("192.168.1.44")))
    capabilities = {"video_encoders": ["libx264"], "platform": {"system": "Linux", "machine": "x86_64"}}

    credential = secrets.token_urlsafe(8)
    report = DeploymentDoctor(
        settings,
        "master",
        peers=["worker-m4"],
        peer_token=credential,
        strict=True,
        capability_probe=lambda _settings: capabilities,
    ).run()

    assert report.overall_status == "pass"
    assert report.exit_code == 0
    assert next(check for check in report.checks if check.check_id == "database.integrity").status == "pass"
    assert next(check for check in report.checks if check.check_id == "peer.0.readiness").status == "pass"
    assert next(check for check in report.checks if check.check_id == "peer.0.version").status == "pass"
    assert next(check for check in report.checks if check.check_id == "peer.0.capabilities").status == "pass"
    assert all(call.kwargs["headers"]["X-Compresso-Api-Token"] == credential for call in get.call_args_list)
    assert all(call.kwargs["allow_redirects"] is False for call in get.call_args_list)


@pytest.mark.parametrize(
    ("peer", "resolved_ip"),
    [
        ("file:///etc/passwd", "192.168.1.44"),
        ("http://user:password@worker.local:8888", "192.168.1.44"),
        ("http://worker.local:8888/untrusted-path", "192.168.1.44"),
        ("http://metadata.local", "169.254.169.254"),
        ("http://localhost:8888", "127.0.0.1"),
    ],
)
def test_peer_probe_rejects_unsafe_targets_without_requesting(tmp_path, monkeypatch, peer, resolved_ip):
    settings = FakeSettings(tmp_path)
    get = MagicMock()
    monkeypatch.setattr("compresso.ops.doctor.requests.get", get)
    monkeypatch.setattr("compresso.ops.doctor.socket.getaddrinfo", MagicMock(return_value=_addrinfo(resolved_ip)))

    checks = DeploymentDoctor(settings, "master", peers=[peer])._peer_checks()

    assert len(checks) == 1
    assert checks[0].status == "fail"
    assert checks[0].check_id == "peer.0.target"
    get.assert_not_called()


def test_peer_probe_rejects_linked_metadata_address_without_requesting(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path, remotes=[{"name": "metadata", "address": "http://metadata.local"}])
    get = MagicMock()
    monkeypatch.setattr("compresso.ops.doctor.requests.get", get)
    monkeypatch.setattr(
        "compresso.ops.doctor.socket.getaddrinfo",
        MagicMock(return_value=_addrinfo("169.254.169.254")),
    )

    checks = DeploymentDoctor(settings, "master", peers=["metadata"])._peer_checks()

    assert checks[0].check_id == "peer.0.target"
    get.assert_not_called()


def test_corrupt_database_and_untrusted_plugin_are_blockers(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path)
    (tmp_path / "config" / "compresso.db").write_bytes(b"not sqlite")
    plugin = tmp_path / "plugins" / "outside"
    plugin.mkdir()
    (plugin / "info.json").write_text('{"id":"outside"}', encoding="utf-8")
    monkeypatch.delenv("COMPRESSO_TRUSTED_PLUGIN_IDS", raising=False)
    monkeypatch.setattr("compresso.ops.doctor.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        "compresso.ops.doctor.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=10 * 1024**3, used=1, free=9 * 1024**3),
    )

    report = DeploymentDoctor(settings, "master", capability_probe=lambda _settings: {"video_encoders": []}).run()

    assert next(check for check in report.checks if check.check_id == "database.integrity").status == "fail"
    assert next(check for check in report.checks if check.check_id == "security.plugins").status == "fail"
    assert report.overall_status == "fail"


def test_non_object_plugin_manifest_is_reported_as_untrusted(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path)
    plugin = tmp_path / "plugins" / "malformed"
    plugin.mkdir()
    (plugin / "info.json").write_text("[]", encoding="utf-8")

    check = next(
        item for item in DeploymentDoctor(settings, "master")._security_checks() if item.check_id == "security.plugins"
    )

    assert check.status == "fail"
    assert check.evidence["untrusted_plugin_ids"] == ["malformed"]


def test_non_object_power_preferences_are_reported_as_warning(monkeypatch):
    monkeypatch.setattr("builtins.open", mock_open(read_data=b"plist"))
    monkeypatch.setattr("compresso.ops.doctor.plistlib.load", MagicMock(return_value=[]))

    check = DeploymentDoctor._mac_power_check()

    assert check.status == "warn"


def test_capability_probe_and_peer_failure_are_reported(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path, remotes=[{"name": "offline", "address": "http://offline.local"}])
    monkeypatch.setattr("compresso.ops.doctor.socket.getaddrinfo", MagicMock(return_value=_addrinfo("192.168.1.45")))
    monkeypatch.setattr("compresso.ops.doctor.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "compresso.ops.doctor.shutil.disk_usage",
        lambda _path: SimpleNamespace(total=10, used=9, free=1),
    )
    monkeypatch.setattr(
        "compresso.ops.doctor.requests.get",
        MagicMock(side_effect=doctor.requests.ConnectionError("offline")),
    )

    def fail_capabilities(_settings):
        raise RuntimeError("probe failed")

    report = DeploymentDoctor(
        settings,
        "master",
        peers=["http://offline.local"],
        capability_probe=fail_capabilities,
    ).run()

    assert next(check for check in report.checks if check.check_id == "capability.snapshot").status == "fail"
    assert next(check for check in report.checks if check.check_id == "peer.0.readiness").status == "fail"
    assert next(check for check in report.checks if check.check_id == "path.cache_reserve").status == "fail"


def test_peer_failure_is_attributed_to_the_endpoint(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path, remotes=[{"uuid": "worker-id", "address": "http://worker.local"}])
    readiness = MagicMock()
    readiness.json.return_value = {"ready": True}
    get = MagicMock(side_effect=[readiness, doctor.requests.ConnectionError("version offline")])
    monkeypatch.setattr("compresso.ops.doctor.socket.getaddrinfo", MagicMock(return_value=_addrinfo("192.168.1.45")))
    monkeypatch.setattr("compresso.ops.doctor.requests.get", get)

    checks = DeploymentDoctor(settings, "master", peers=["worker-id"])._peer_checks()

    assert len(checks) == 1
    assert checks[0].check_id == "peer.0.version"
    assert checks[0].evidence["endpoint"] == "version"


def test_malformed_peer_payloads_become_failed_checks(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path, remotes=[{"name": "worker", "address": "http://worker.local"}])
    responses = []
    for payload in ([], ["not-version"], {"video_encoders": []}):
        response = MagicMock()
        response.json.return_value = payload
        responses.append(response)
    monkeypatch.setattr("compresso.ops.doctor.socket.getaddrinfo", MagicMock(return_value=_addrinfo("192.168.1.45")))
    monkeypatch.setattr("compresso.ops.doctor.requests.get", MagicMock(side_effect=responses))

    checks = DeploymentDoctor(settings, "master", peers=["worker"])._peer_checks()

    assert [check.check_id for check in checks] == ["peer.0.readiness", "peer.0.version", "peer.0.capabilities"]
    assert all(check.status == "fail" for check in checks)


def test_doctor_main_saves_and_prints_report(tmp_path, monkeypatch, capsys):
    settings = FakeSettings(tmp_path)
    report = DoctorReport.create("worker", [])
    runner = MagicMock()
    runner.run.return_value = report
    monkeypatch.setattr(doctor, "Config", MagicMock(return_value=settings))
    monkeypatch.setattr(doctor, "DeploymentDoctor", MagicMock(return_value=runner))

    exit_code = doctor.main(["--role", "worker", "--output", str(tmp_path / "doctor.json")])

    assert exit_code == 0
    assert (tmp_path / "doctor.json").is_file()
    assert json.loads(capsys.readouterr().out)["report_id"] == report.report_id
