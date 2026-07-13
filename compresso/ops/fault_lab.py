# SPDX-License-Identifier: GPL-3.0-only

"""Deterministic synthetic fault laboratory for distributed deployment safety."""

from __future__ import annotations

import argparse
import datetime
import errno
import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
import wave
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from compresso.config import Config
from compresso.libs.library_scale_benchmark import run_benchmark
from compresso.libs.resumable_transfer import ResumableTransferStore, file_sha256

ENABLE_ENV = "COMPRESSO_FAULT_LAB"
MARKER_NAME = ".compresso-fault-lab.json"
MARKER_PAYLOAD = {"kind": "compresso-synthetic-fault-lab", "schema_version": 1}
SCHEMA_VERSION = 1


class SafetyError(RuntimeError):
    """The requested workspace is not isolated enough for destructive drills."""


class InvariantViolation(RuntimeError):
    """A fault scenario broke a required data-safety invariant."""


def _checksum(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _deterministic_bytes(seed: int, length: int) -> bytes:
    result = bytearray()
    counter = 0
    while len(result) < length:
        result.extend(hashlib.sha256(f"{seed}:{counter}".encode()).digest())
        counter += 1
    return bytes(result[:length])


def write_report(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically persist a private JSON report."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    except Exception:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def initialize_workspace(path: Path) -> Path:
    """Create a lab marker only in a new, empty, or already-marked directory."""
    workspace = Path(path).expanduser().resolve()
    workspace.mkdir(mode=0o700, parents=True, exist_ok=True)
    entries = list(workspace.iterdir())
    if entries and {entry.name for entry in entries} != {MARKER_NAME}:
        raise SafetyError("fault-lab workspace must be empty before initialization")
    marker = workspace / MARKER_NAME
    if marker.exists():
        try:
            existing = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SafetyError("existing fault-lab marker is invalid") from error
        if existing != MARKER_PAYLOAD:
            raise SafetyError("existing fault-lab marker has the wrong identity")
    else:
        write_report(marker, MARKER_PAYLOAD)
    os.chmod(workspace, 0o700)
    return workspace


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _reject_home_root(workspace: Path) -> None:
    home = Path.home().resolve()
    if workspace == home or home.is_relative_to(workspace):
        raise SafetyError("fault-lab workspace cannot be the home directory or one of its parents")


def validate_workspace(path: Path, protected_paths: Iterable[Path] = ()) -> Path:
    """Fail closed unless both the environment and on-disk marker authorize the lab."""
    if os.environ.get(ENABLE_ENV) != "1":
        raise SafetyError(f"set {ENABLE_ENV}=1 to authorize synthetic fault injection")
    workspace = Path(path).expanduser().resolve()
    marker = workspace / MARKER_NAME
    try:
        marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SafetyError("fault-lab workspace marker is missing or invalid") from error
    if marker_payload != MARKER_PAYLOAD:
        raise SafetyError("fault-lab workspace marker has the wrong identity")
    _reject_home_root(workspace)
    for protected in protected_paths:
        candidate = Path(protected).expanduser().resolve()
        if _paths_overlap(workspace, candidate):
            raise SafetyError(f"fault-lab workspace overlaps protected path: {candidate}")
    return workspace


@dataclass(frozen=True)
class FaultContext:
    workspace: Path
    seed: int = 20

    def fresh_directory(self, name: str) -> Path:
        destination = self.workspace / "scenarios" / name
        if destination.exists():
            shutil.rmtree(destination)
        destination.mkdir(parents=True)
        return destination


def run_transfer_restart(context: FaultContext) -> dict[str, Any]:
    root = context.fresh_directory("transfer-restart")
    payload = _deterministic_bytes(context.seed, 64 * 1024 + 37)
    store = ResumableTransferStore(root)
    status = store.begin("restart-job", "synthetic.mkv", len(payload), _checksum(payload))
    transfer_id = status["transfer_id"]
    offset = 0
    chunks = 0
    while offset < len(payload):
        chunk_size = 257 + ((context.seed + chunks * 7_919) % 3_840)
        chunk = payload[offset : offset + chunk_size]
        store.append(transfer_id, offset, chunk, _checksum(chunk))
        offset += len(chunk)
        chunks += 1
        store = ResumableTransferStore(root)
        if store.status(transfer_id)["offset"] != offset:
            raise InvariantViolation("durable transfer offset changed after restart")
    completed = store.finalize(transfer_id)
    if completed.read_bytes() != payload:
        raise InvariantViolation("finalized transfer differs from the source payload")
    return {"chunks": chunks, "final_checksum": "verified", "restart_resume": "verified"}


def run_transfer_corruption(context: FaultContext) -> dict[str, Any]:
    root = context.fresh_directory("transfer-corruption")
    payload = b"deterministic-corruption-probe"
    store = ResumableTransferStore(root / "chunks")
    status = store.begin("corrupt-job", "synthetic.mkv", len(payload), _checksum(payload))
    try:
        store.append(status["transfer_id"], 0, payload, _checksum(b"wrong"))
    except ValueError:
        pass
    else:
        raise InvariantViolation("corrupt transfer chunk was accepted")
    if store.status(status["transfer_id"])["offset"] != 0:
        raise InvariantViolation("corrupt chunk advanced the durable offset")

    damaged = ResumableTransferStore(root / "manifests")
    damaged_status = damaged.begin("manifest-job", "synthetic.mkv", 1, _checksum(b"x"))
    damaged._manifest_path(damaged_status["transfer_id"]).write_text("not-json", encoding="utf-8")
    if damaged.summary()["corrupt"] != 1:
        raise InvariantViolation("damaged transfer manifest was not quarantined")
    return {"corrupt_inputs": "rejected", "damaged_checkpoint": "quarantined"}


def run_stale_offset(context: FaultContext) -> dict[str, Any]:
    root = context.fresh_directory("stale-offset")
    payload = b"0123456789"
    store = ResumableTransferStore(root)
    status = store.begin("offset-job", "synthetic.mkv", len(payload), _checksum(payload))
    store.append(status["transfer_id"], 0, payload[:4], _checksum(payload[:4]))
    try:
        store.append(status["transfer_id"], 0, payload[4:], _checksum(payload[4:]))
    except ValueError:
        pass
    else:
        raise InvariantViolation("stale transfer offset was accepted")
    if store.status(status["transfer_id"])["offset"] != 4:
        raise InvariantViolation("stale offset attempt changed received bytes")
    return {"durable_offset": 4, "stale_offset": "rejected"}


def run_filesystem_faults(context: FaultContext) -> dict[str, Any]:
    root = context.fresh_directory("filesystem-faults")
    failures = [errno.ENOSPC, errno.EROFS]

    def inject(operation: str, _path: Path) -> None:
        if operation == "append" and failures:
            raise OSError(failures.pop(0), "synthetic filesystem fault")

    payload = b"filesystem-retry-payload"
    store = ResumableTransferStore(root, fault_injector=inject)
    status = store.begin("filesystem-job", "synthetic.mkv", len(payload), _checksum(payload))
    observed = []
    for expected_error in (errno.ENOSPC, errno.EROFS):
        try:
            store.append(status["transfer_id"], 0, payload, _checksum(payload))
        except OSError as error:
            observed.append(error.errno)
        else:
            raise InvariantViolation("synthetic filesystem fault did not interrupt the append")
        if store.status(status["transfer_id"])["offset"] != 0:
            raise InvariantViolation("filesystem fault advanced the durable offset")
        if observed[-1] != expected_error:
            raise InvariantViolation("wrong synthetic filesystem fault was observed")
    store.append(status["transfer_id"], 0, payload, _checksum(payload))
    completed = store.finalize(status["transfer_id"])
    if completed.read_bytes() != payload:
        raise InvariantViolation("filesystem retry produced different bytes")
    return {"faults": ["disk-full", "read-only"], "recovery": "verified"}


def run_finalization_recovery(context: FaultContext) -> dict[str, Any]:
    root = context.fresh_directory("finalization-recovery")
    fail_replace = [True]

    def inject(operation: str, _path: Path) -> None:
        if operation == "final_replace" and fail_replace.pop():
            raise OSError(errno.EIO, "synthetic finalization interruption")

    payload = b"finalization-payload"
    store = ResumableTransferStore(root, fault_injector=inject)
    status = store.begin("finalize-job", "synthetic.mkv", len(payload), _checksum(payload))
    store.append(status["transfer_id"], 0, payload, _checksum(payload))
    try:
        store.finalize(status["transfer_id"])
    except OSError:
        pass
    else:
        raise InvariantViolation("finalization interruption was not injected")
    restarted = ResumableTransferStore(root)
    completed = restarted.finalize(status["transfer_id"])
    if file_sha256(completed) != _checksum(payload):
        raise InvariantViolation("finalization retry checksum differs")
    return {"interruption": "survived", "retry": "verified"}


def run_lease_contention(context: FaultContext) -> dict[str, Any]:
    from compresso.libs.remote_task_lease import RemoteTaskLease
    from compresso.libs.unmodels.lib import Database
    from compresso.libs.unmodels.tasks import Tasks

    root = context.fresh_directory("lease-contention")
    database = Database.select_database(
        {"TYPE": "SQLITE", "FILE": str(root / "leases.db"), "MIGRATIONS_DIR": str(root / "migrations")}
    )
    try:
        database.create_tables([Tasks])
        task = Tasks.create(
            abspath="/synthetic/library/movie.mkv",
            cache_path="/synthetic/cache/movie.mkv",
            status="pending",
            type="local",
            library_id=1,
        )
        now = datetime.datetime(2026, 1, 1, 12, 0, 0)
        first = RemoteTaskLease.acquire(task, "worker-a", now=now)
        duplicate = RemoteTaskLease.acquire(task, "worker-b", now=now)
        resumed = RemoteTaskLease.acquire(task, "worker-a", now=now)
        if not first or duplicate is not None or resumed != first:
            raise InvariantViolation("active task lease was duplicated or could not be resumed")
        return {"duplicate_lease": "rejected", "same_worker_resume": "stable"}
    finally:
        database.close()


def run_process_restart(_context: FaultContext) -> dict[str, Any]:
    run_drill = importlib.import_module("compresso.libs.distributed_process_drill").run_drill
    result = run_drill(size_mb=1, chunk_mb=1)
    required = {
        "restart_during_upload": "resumed",
        "stale_offset": "rejected",
        "duplicate_finalization": "idempotent",
        "restart_after_finalization": "preserved",
        "database_isolation": "preserved",
    }
    if any(result.get(name) != expected for name, expected in required.items()):
        raise InvariantViolation("two-process restart drill broke a distributed invariant")
    return required


def _run_queue_scale(entry_count: int) -> dict[str, Any]:
    result = run_benchmark(entry_count, batch_size=1_000)
    if result.get("entry_count") != entry_count:
        raise InvariantViolation(f"synthetic queue did not retain all {entry_count} entries")
    return {"entries": entry_count, "inventory": "exact", "queries": "completed"}


def run_queue_10k(_context: FaultContext) -> dict[str, Any]:
    return _run_queue_scale(10_000)


def run_queue_100k(_context: FaultContext) -> dict[str, Any]:
    return _run_queue_scale(100_000)


def run_media_fixture(context: FaultContext) -> dict[str, Any]:
    from compresso.libs.ffprobe_utils import probe_file

    root = context.fresh_directory("media-fixture")
    fixture = root / "synthetic.wav"
    with wave.open(str(fixture), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\0\0" * 8_000)
    payload = probe_file(str(fixture), timeout=30)
    if not fixture.is_file() or not isinstance(payload, dict) or not payload.get("streams"):
        raise InvariantViolation("synthetic media fixture could not be verified with FFprobe")
    return {"fixture": "generated", "ffprobe": "verified"}


ScenarioRunner = Callable[[FaultContext], dict[str, Any]]
DEFAULT_SCENARIOS: OrderedDict[str, ScenarioRunner] = OrderedDict(
    (
        ("transfer-restart", run_transfer_restart),
        ("transfer-corruption", run_transfer_corruption),
        ("stale-offset", run_stale_offset),
        ("filesystem-faults", run_filesystem_faults),
        ("finalization-recovery", run_finalization_recovery),
        ("lease-contention", run_lease_contention),
        ("process-restart", run_process_restart),
        ("queue-10k", run_queue_10k),
        ("queue-100k", run_queue_100k),
        ("media-fixture", run_media_fixture),
    )
)


class FaultLab:
    """Run ordered scenarios inside one validated synthetic workspace."""

    def __init__(
        self,
        workspace: Path,
        *,
        seed: int = 20,
        protected_paths: Iterable[Path] = (),
        scenario_runners: Mapping[str, ScenarioRunner] | None = None,
    ) -> None:
        self.workspace = validate_workspace(workspace, protected_paths)
        self.seed = int(seed)
        self.scenario_runners = OrderedDict(scenario_runners or DEFAULT_SCENARIOS)

    def run(self, scenario: str = "all") -> dict[str, Any]:
        if scenario == "all":
            selected = list(self.scenario_runners)
        elif scenario in self.scenario_runners:
            selected = [scenario]
        else:
            raise ValueError(f"unknown fault-lab scenario: {scenario}")
        identity = json.dumps({"seed": self.seed, "scenarios": selected}, sort_keys=True).encode()
        report: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": hashlib.sha256(identity).hexdigest()[:16],
            "seed": self.seed,
            "scenario_requested": scenario,
            "overall_status": "pass",
            "scenarios": [],
        }
        context = FaultContext(self.workspace, self.seed)
        for name in selected:
            try:
                evidence = self.scenario_runners[name](context)
                if not isinstance(evidence, dict):
                    raise InvariantViolation("scenario evidence is not an object")
                report["scenarios"].append({"scenario": name, "status": "pass", "evidence": evidence})
            except Exception as error:
                report["overall_status"] = "fail"
                report["scenarios"].append({"scenario": name, "status": "fail", "error": str(error)})
                break
        return report


def _protected_paths(settings: Any) -> list[Path]:
    paths = [Path.cwd(), Path(__file__).resolve().parents[2]]
    for getter_name in ("get_config_path", "get_cache_path", "get_library_path", "get_userdata_path"):
        value = getattr(settings, getter_name)()
        if value:
            paths.append(Path(value))
    return paths


def _run_main(args: argparse.Namespace) -> int:
    settings = Config()
    protected = _protected_paths(settings)
    if args.init_workspace:
        if os.environ.get(ENABLE_ENV) != "1":
            raise SafetyError(f"set {ENABLE_ENV}=1 before initializing a synthetic lab")
        workspace = Path(args.workspace).expanduser().resolve()
        _reject_home_root(workspace)
        for path in protected:
            if _paths_overlap(workspace, path.expanduser().resolve()):
                raise SafetyError(f"fault-lab workspace overlaps protected path: {path}")
        initialize_workspace(workspace)
        sys.stdout.write(json.dumps({"workspace": str(workspace), "initialized": True}, sort_keys=True) + "\n")
        return 0

    if args.workspace:
        workspace = Path(args.workspace)
        report = FaultLab(workspace, seed=args.seed, protected_paths=protected).run(args.scenario)
    else:
        with tempfile.TemporaryDirectory(prefix="compresso-fault-lab-") as temporary:
            workspace = initialize_workspace(Path(temporary))
            report = FaultLab(workspace, seed=args.seed, protected_paths=protected).run(args.scenario)
    write_report(Path(args.report), report)
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0 if report["overall_status"] == "pass" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compresso fault-lab", description=__doc__)
    parser.add_argument("--workspace")
    parser.add_argument("--init-workspace", action="store_true")
    parser.add_argument("--scenario", default="all", choices=("all", *DEFAULT_SCENARIOS))
    parser.add_argument("--seed", type=int, default=20)
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    if args.init_workspace and not args.workspace:
        parser.error("--init-workspace requires --workspace")
    if not args.init_workspace and not args.report:
        parser.error("--report is required when running scenarios")
    try:
        return _run_main(args)
    except SafetyError as error:
        sys.stderr.write(json.dumps({"error": str(error), "type": "safety"}, sort_keys=True) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
