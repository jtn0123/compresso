# SPDX-License-Identifier: GPL-3.0-only

"""Deterministic safety and fault-injection tests for the synthetic lab."""

import json
import os
import stat
from collections import OrderedDict
from types import SimpleNamespace

import pytest

from compresso.ops import fault_lab


def test_initialize_and_validate_workspace_requires_explicit_lab_environment(tmp_path, monkeypatch):
    workspace = tmp_path / "fault-lab"
    fault_lab.initialize_workspace(workspace)

    monkeypatch.delenv(fault_lab.ENABLE_ENV, raising=False)
    with pytest.raises(fault_lab.SafetyError, match=fault_lab.ENABLE_ENV):
        fault_lab.validate_workspace(workspace)

    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")
    assert fault_lab.validate_workspace(workspace) == workspace.resolve()
    mode = (workspace / fault_lab.MARKER_NAME).stat().st_mode
    assert mode & stat.S_IRUSR
    assert mode & stat.S_IWUSR
    if os.name != "nt":
        assert mode & 0o777 == 0o600


def test_workspace_without_marker_and_protected_workspace_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")
    unmarked = tmp_path / "unmarked"
    unmarked.mkdir()

    with pytest.raises(fault_lab.SafetyError, match="marker"):
        fault_lab.validate_workspace(unmarked)

    protected = tmp_path / "library"
    fault_lab.initialize_workspace(protected)
    with pytest.raises(fault_lab.SafetyError, match="protected"):
        fault_lab.validate_workspace(protected, protected_paths=[protected])


def test_report_is_deterministic_and_runs_scenarios_in_declared_order(tmp_path, monkeypatch):
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")
    workspace = tmp_path / "lab"
    fault_lab.initialize_workspace(workspace)
    calls = []

    def scenario(name):
        def run(_context):
            calls.append(name)
            return {"invariant": name, "value": 1}

        return run

    runners = OrderedDict((name, scenario(name)) for name in ("first", "second", "third"))
    lab = fault_lab.FaultLab(workspace, seed=20, scenario_runners=runners)

    first = lab.run("all")
    second = lab.run("all")

    assert first == second
    assert calls == ["first", "second", "third", "first", "second", "third"]
    assert first["overall_status"] == "pass"
    assert [item["scenario"] for item in first["scenarios"]] == ["first", "second", "third"]


def test_fault_lab_stops_after_first_invariant_failure(tmp_path, monkeypatch):
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")
    workspace = tmp_path / "lab"
    fault_lab.initialize_workspace(workspace)

    def never(_context):
        pytest.fail("later scenario should not run")

    runners = OrderedDict(
        (
            ("broken", lambda _context: (_ for _ in ()).throw(fault_lab.InvariantViolation("offset changed"))),
            ("later", never),
        )
    )

    report = fault_lab.FaultLab(workspace, scenario_runners=runners).run("all")

    assert report["overall_status"] == "fail"
    assert report["scenarios"] == [{"scenario": "broken", "status": "fail", "error": "offset changed"}]


def test_atomic_report_write_uses_private_permissions(tmp_path):
    destination = tmp_path / "reports" / "fault-lab.json"
    payload = {"schema_version": 1, "overall_status": "pass"}

    fault_lab.write_report(destination, payload)

    assert json.loads(destination.read_text()) == payload
    mode = destination.stat().st_mode
    assert mode & stat.S_IRUSR
    assert mode & stat.S_IWUSR
    if os.name != "nt":
        assert mode & 0o777 == 0o600
    assert not list(destination.parent.glob("*.tmp"))


def test_cli_refuses_unmarked_workspace_without_touching_report(tmp_path, monkeypatch):
    workspace = tmp_path / "unmarked"
    workspace.mkdir()
    report = tmp_path / "report.json"
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")

    exit_code = fault_lab.main(["--workspace", str(workspace), "--scenario", "all", "--report", str(report)])

    assert exit_code == 2
    assert not report.exists()


def test_transfer_fault_scenarios_preserve_invariants(tmp_path):
    context = fault_lab.FaultContext(workspace=tmp_path, seed=20)

    assert fault_lab.run_transfer_restart(context)["final_checksum"] == "verified"
    assert fault_lab.run_transfer_corruption(context)["corrupt_inputs"] == "rejected"
    assert fault_lab.run_stale_offset(context)["stale_offset"] == "rejected"
    assert fault_lab.run_filesystem_faults(context)["recovery"] == "verified"
    assert fault_lab.run_finalization_recovery(context)["retry"] == "verified"


def test_environment_value_must_be_exactly_one(tmp_path, monkeypatch):
    workspace = tmp_path / "lab"
    fault_lab.initialize_workspace(workspace)
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "true")

    with pytest.raises(fault_lab.SafetyError):
        fault_lab.validate_workspace(workspace)

    assert os.environ[fault_lab.ENABLE_ENV] == "true"


def test_dedicated_home_child_is_allowed_but_home_itself_is_rejected(tmp_path, monkeypatch):
    home = tmp_path / "home"
    child = home / "labs" / "run-20"
    fault_lab.initialize_workspace(child)
    monkeypatch.setattr(fault_lab.Path, "home", lambda: home)
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")

    assert fault_lab.validate_workspace(child) == child.resolve()

    direct_home = tmp_path / "home-itself"
    fault_lab.initialize_workspace(direct_home)
    monkeypatch.setattr(fault_lab.Path, "home", lambda: direct_home)
    with pytest.raises(fault_lab.SafetyError, match="home"):
        fault_lab.validate_workspace(direct_home)


def test_initialize_rejects_nonempty_and_wrong_marker_workspaces(tmp_path):
    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "media.mkv").write_bytes(b"not a lab")
    with pytest.raises(fault_lab.SafetyError, match="empty"):
        fault_lab.initialize_workspace(nonempty)

    wrong = tmp_path / "wrong"
    wrong.mkdir()
    (wrong / fault_lab.MARKER_NAME).write_text('{"kind":"production"}')
    with pytest.raises(fault_lab.SafetyError, match="wrong identity"):
        fault_lab.initialize_workspace(wrong)


def test_builtin_process_and_queue_runners_validate_real_result_shapes(tmp_path, monkeypatch):
    process_result = {
        "restart_during_upload": "resumed",
        "stale_offset": "rejected",
        "duplicate_finalization": "idempotent",
        "restart_after_finalization": "preserved",
        "database_isolation": "preserved",
    }
    monkeypatch.setattr(
        fault_lab.importlib,
        "import_module",
        lambda _name: SimpleNamespace(run_drill=lambda **_kwargs: process_result),
    )
    monkeypatch.setattr(fault_lab, "run_benchmark", lambda entries, batch_size: {"entry_count": entries})
    context = fault_lab.FaultContext(tmp_path, 20)

    assert fault_lab.run_process_restart(context) == process_result
    assert fault_lab.run_queue_10k(context)["entries"] == 10_000
    assert fault_lab.run_queue_100k(context)["entries"] == 100_000


def test_process_and_queue_runners_fail_closed_on_bad_results(tmp_path, monkeypatch):
    monkeypatch.setattr(
        fault_lab.importlib,
        "import_module",
        lambda _name: SimpleNamespace(run_drill=lambda **_kwargs: {}),
    )
    with pytest.raises(fault_lab.InvariantViolation, match="distributed invariant"):
        fault_lab.run_process_restart(fault_lab.FaultContext(tmp_path))

    monkeypatch.setattr(fault_lab, "run_benchmark", lambda _entries, batch_size: {"entry_count": 1})
    with pytest.raises(fault_lab.InvariantViolation, match="retain"):
        fault_lab.run_queue_10k(fault_lab.FaultContext(tmp_path))


def test_media_fixture_is_compact_and_probe_verified(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "compresso.libs.ffprobe_utils.probe_file",
        lambda path, timeout: {"streams": [{"codec_type": "audio", "path": path, "timeout": timeout}]},
    )

    evidence = fault_lab.run_media_fixture(fault_lab.FaultContext(tmp_path))

    fixture = tmp_path / "scenarios" / "media-fixture" / "synthetic.wav"
    assert evidence == {"fixture": "generated", "ffprobe": "verified"}
    assert 1_000 < fixture.stat().st_size < 32_000


def test_unknown_scenario_and_non_object_evidence_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")
    workspace = fault_lab.initialize_workspace(tmp_path / "lab")
    lab = fault_lab.FaultLab(workspace, scenario_runners={"bad": lambda _context: []})

    with pytest.raises(ValueError, match="unknown"):
        lab.run("missing")
    report = lab.run("bad")

    assert report["overall_status"] == "fail"
    assert report["scenarios"][0]["error"] == "scenario evidence is not an object"


def test_cli_initializes_explicit_workspace(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "new-lab"
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")

    exit_code = fault_lab.main(["--workspace", str(workspace), "--init-workspace"])

    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["initialized"] is True
    assert (workspace / fault_lab.MARKER_NAME).is_file()


def test_cli_ephemeral_run_writes_report(tmp_path, monkeypatch):
    report_path = tmp_path / "report.json"
    monkeypatch.setenv(fault_lab.ENABLE_ENV, "1")
    monkeypatch.setattr(
        fault_lab,
        "DEFAULT_SCENARIOS",
        OrderedDict({"tiny": lambda _context: {"synthetic": "verified"}}),
    )

    exit_code = fault_lab.main(["--scenario", "tiny", "--report", str(report_path)])

    assert exit_code == 0
    assert json.loads(report_path.read_text())["scenarios"][0]["evidence"] == {"synthetic": "verified"}
