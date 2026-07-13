# SPDX-License-Identifier: GPL-3.0-only

"""Behavior tests for the deployment readiness doctor."""

import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from compresso.ops import doctor
from compresso.ops.doctor import CheckResult, DeploymentDoctor, DoctorReport, load_latest_report


class FakeSettings:
    """Minimal settings surface used by deployment-doctor tests."""

    def __init__(self, root, *, scanner=True, address="127.0.0.1"):
        self.root = root
        self.scanner = scanner
        self.address = address
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
    settings = FakeSettings(tmp_path)
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
    capabilities = {"video_encoders": ["libx264"], "platform": {"system": "Linux", "machine": "x86_64"}}

    credential = secrets.token_urlsafe(8)
    report = DeploymentDoctor(
        settings,
        "master",
        peers=["http://worker.local:8888"],
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


def test_capability_probe_and_peer_failure_are_reported(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path)
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
