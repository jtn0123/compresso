# SPDX-License-Identifier: GPL-3.0-only

"""Read-only capacity planner for large media compression deployments."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import heapq
import json
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from compresso.config import Config
from compresso.libs.json_state import atomic_json_write
from compresso.webserver.helpers import library_analysis

SCHEMA_VERSION = 1
GIB = 1024**3
TIB = 1024**4
PLAN_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.json")
CONFIDENCE_SPREAD = {"high": 5.0, "medium": 10.0, "low": 15.0, "optimal": 0.0}


def _database_path(settings: Any) -> Path:
    return Path(settings.get_config_path()).expanduser().resolve() / "compresso.db"


def _readonly_connection(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise ValueError(f"Compresso database does not exist: {path}")
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)


def load_library_record(settings: Any, library_id: int) -> dict[str, Any]:
    """Resolve one configured library through a read-only SQLite connection."""
    try:
        with contextlib.closing(_readonly_connection(_database_path(settings))) as connection:
            row = connection.execute(
                "SELECT id, name, path, skip_codecs FROM libraries WHERE id = ?",
                (int(library_id),),
            ).fetchone()
    except sqlite3.Error as error:
        raise ValueError(f"could not read configured library {library_id}") from error
    if row is None:
        raise ValueError(f"configured library {library_id} does not exist")
    try:
        parsed_skip = json.loads(row[3] or "[]")
    except (TypeError, json.JSONDecodeError):
        parsed_skip = []
    skip_codecs = [str(item).lower() for item in parsed_skip] if isinstance(parsed_skip, list) else []
    return {"id": int(row[0]), "name": str(row[1]), "path": str(row[2]), "skip_codecs": skip_codecs}


def load_historical_evidence(settings: Any, library_id: int | None) -> tuple[dict, list[float]]:
    """Read savings and throughput evidence without initializing the ORM."""
    try:
        with contextlib.closing(_readonly_connection(_database_path(settings))) as connection:
            query = (
                "SELECT source_size, destination_size, source_codec, source_resolution, encoding_duration_seconds "
                "FROM compressionstats"
            )
            parameters: tuple[Any, ...] = ()
            if library_id is not None:
                query += " WHERE library_id = ?"
                parameters = (int(library_id),)
            rows = connection.execute(query, parameters).fetchall()
    except (ValueError, sqlite3.Error):
        return {}, []

    grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"source": 0.0, "destination": 0.0, "count": 0.0})
    throughput = []
    for source_size, destination_size, codec, resolution, duration in rows:
        source = float(source_size or 0)
        destination = float(destination_size or 0)
        seconds = float(duration or 0)
        if source > 0 and destination > 0 and destination < source:
            key = (str(codec or "").lower(), str(resolution or ""))
            grouped[key]["source"] += source
            grouped[key]["destination"] += destination
            grouped[key]["count"] += 1
        if source > 0 and seconds > 0:
            throughput.append(source / seconds)
    historical = {
        key: {
            "avg_savings_pct": (values["source"] - values["destination"]) / values["source"] * 100,
            "count": int(values["count"]),
        }
        for key, values in grouped.items()
        if values["source"] > 0
    }
    return historical, throughput


def validate_source_path(path: str | Path, settings: Any) -> Path:
    """Resolve a read-only scan root and reject application state paths."""
    source = Path(path).expanduser().resolve()
    if not source.is_dir():
        raise ValueError("planning source must be an existing directory")
    protected = [settings.get_config_path(), settings.get_cache_path(), settings.get_userdata_path()]
    for value in protected:
        candidate = Path(value).expanduser().resolve()
        if source == candidate or source.is_relative_to(candidate) or candidate.is_relative_to(source):
            raise ValueError(f"planning source overlaps protected application path: {candidate}")
    return source


def _select_inventory(source: Path, sample_size: int, full_inventory: bool, seed: int) -> tuple[dict, list[dict]]:
    sample_heap: list[tuple[int, str, int]] = []
    total_bytes = 0
    media_files = 0
    unreadable_files = 0
    traversal_errors: list[OSError] = []
    largest: tuple[int, str] = (0, "")
    all_entries = []
    for path in library_analysis.iter_media_files(source, on_error=traversal_errors.append):
        try:
            size = path.stat().st_size
        except OSError:
            unreadable_files += 1
            continue
        relative = str(path.relative_to(source))
        media_files += 1
        total_bytes += size
        largest = max(largest, (size, relative))
        entry = {"path": str(path), "relative_path": relative, "size_bytes": size}
        if full_inventory:
            all_entries.append(entry)
            continue
        score = int.from_bytes(hashlib.sha256(f"{seed}:{relative}".encode()).digest()[:8], "big")
        item = (-score, relative, size)
        if len(sample_heap) < sample_size:
            heapq.heappush(sample_heap, item)
        elif item > sample_heap[0]:
            heapq.heapreplace(sample_heap, item)
    if traversal_errors:
        suffix = "y" if len(traversal_errors) == 1 else "ies"
        raise ValueError(f"planning source contains {len(traversal_errors)} unreadable director{suffix}")
    if media_files == 0:
        raise ValueError("planning source contains no supported media files")
    if full_inventory:
        selected = all_entries
    else:
        selected = [
            {"path": str(source / relative), "relative_path": relative, "size_bytes": size}
            for _score, relative, size in sorted(sample_heap, key=lambda item: item[1])
        ]
    inventory = {
        "mode": "full-probe" if full_inventory else "sampled-probe",
        "media_files": media_files,
        "total_bytes": total_bytes,
        "sampled_files": len(selected),
        "unreadable_files": unreadable_files,
        "largest_file": {"relative_path": largest[1], "size_bytes": largest[0]} if media_files else None,
    }
    return inventory, selected


def _savings_summary(
    total_bytes: int,
    samples: list[dict[str, Any]],
    historical: dict,
    skip_codecs: set[str],
) -> dict[str, Any]:
    known_bytes = 0
    weighted_low = 0.0
    weighted_high = 0.0
    confidences = []
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for sample in samples:
        codec = str(sample.get("codec") or "unknown").lower()
        resolution = str(sample.get("resolution") or "unknown")
        size = int(sample.get("size_bytes") or 0)
        if codec in skip_codecs:
            point, count, confidence = 0.0, 0, "optimal"
        else:
            point, count, confidence = library_analysis.lookup_savings(historical, codec, resolution)
        key = (codec, resolution)
        group = groups.setdefault(
            key,
            {
                "codec": codec,
                "resolution": resolution,
                "sample_files": 0,
                "sample_bytes": 0,
                "historical_samples": count,
                "confidence": confidence if confidence != "none" else "unknown",
            },
        )
        group["sample_files"] += 1
        group["sample_bytes"] += size
        if confidence == "none":
            continue
        spread = CONFIDENCE_SPREAD[confidence]
        low = max(0.0, float(point) - spread)
        high = min(100.0, float(point) + spread)
        known_bytes += size
        weighted_low += size * low
        weighted_high += size * high
        confidences.append(confidence)
        group["range_pct"] = {"low": round(low, 1), "high": round(high, 1)}
    sampled_bytes = sum(int(sample.get("size_bytes") or 0) for sample in samples)
    if not known_bytes or not sampled_bytes:
        return {
            "status": "unknown",
            "confidence": "unknown",
            "known_sample_coverage_pct": 0.0,
            "range_pct": None,
            "range_bytes": None,
            "groups": list(groups.values()),
        }
    low_pct = weighted_low / known_bytes
    high_pct = weighted_high / known_bytes
    coverage = known_bytes / sampled_bytes * 100
    rank = {"optimal": 3, "high": 3, "medium": 2, "low": 1}
    confidence = min(confidences, key=lambda item: rank[item])
    if coverage < 80:
        confidence = "low"
    return {
        "status": "estimated",
        "confidence": confidence,
        "known_sample_coverage_pct": round(coverage, 1),
        "range_pct": {"low": round(low_pct, 1), "high": round(high_pct, 1)},
        "range_bytes": {
            "low": int(total_bytes * low_pct / 100),
            "high": int(total_bytes * high_pct / 100),
        },
        "groups": list(groups.values()),
    }


def _runtime_summary(total_bytes: int, throughput: list[float]) -> dict[str, Any]:
    valid = sorted(float(value) for value in throughput if float(value) > 0)
    if len(valid) < 3:
        return {"status": "unknown", "historical_samples": len(valid), "single_slot_seconds": None}
    low_index = max(0, int((len(valid) - 1) * 0.25))
    high_index = min(len(valid) - 1, int((len(valid) - 1) * 0.75))
    slow = valid[low_index]
    fast = valid[high_index]
    return {
        "status": "estimated",
        "historical_samples": len(valid),
        "single_slot_seconds": {
            "low": round(total_bytes / fast, 1),
            "high": round(total_bytes / slow, 1),
        },
        "throughput_bytes_per_second": {"low": round(slow, 1), "high": round(fast, 1)},
    }


def _allocation(settings: Any) -> dict[str, Any]:
    workers = []
    remotes = settings.get_remote_installations()
    if isinstance(remotes, list):
        for remote in remotes:
            if not isinstance(remote, dict) or not remote.get("available"):
                continue
            raw_capabilities = remote.get("capabilities")
            capabilities: dict[str, Any] = raw_capabilities if isinstance(raw_capabilities, dict) else {}
            workers.append(
                {
                    "name": str(remote.get("name") or "linked-worker"),
                    "initial_encode_slots": 1,
                    "platform": capabilities.get("platform", {}),
                    "video_encoders": capabilities.get("video_encoders", []),
                }
            )
    return {
        "master": {"scanner": True, "initial_encode_slots": 1, "configured_worker_cap": settings.get_default_worker_cap()},
        "remote_workers": workers,
        "guidance": "Start with one encode slot per node; increase only after canary temperature and throughput evidence.",
    }


def build_capacity_plan(
    settings: Any,
    source_path: str | Path,
    *,
    library_id: int | None = None,
    sample_size: int = 200,
    full_inventory: bool = False,
    seed: int = 20,
    skip_codecs: list[str] | None = None,
    probe=None,
    historical_savings: dict | None = None,
    throughput_bytes_per_second: list[float] | None = None,
) -> dict[str, Any]:
    """Build a read-only plan from bounded metadata and probe evidence."""
    if sample_size < 1:
        raise ValueError("sample_size must be positive")
    source = validate_source_path(source_path, settings)
    inventory, selected = _select_inventory(source, sample_size, full_inventory, seed)
    probe_file = probe or library_analysis.probe_analysis_file
    samples = []
    probe_failures = 0
    for entry in selected:
        try:
            metadata = probe_file(entry["path"])
            if not isinstance(metadata, dict):
                raise ValueError("probe returned no metadata")
            samples.append({**metadata, "size_bytes": entry["size_bytes"]})
        except (OSError, TypeError, ValueError):
            probe_failures += 1
    inventory["probe_failures"] = probe_failures
    total_bytes = int(inventory["total_bytes"])
    history = historical_savings or {}
    throughput = throughput_bytes_per_second or []
    cache_path = Path(settings.get_cache_path()).expanduser().resolve()
    disk = shutil.disk_usage(cache_path)
    reserve = int(float(settings.get_minimum_free_space_gb()) * GIB)
    largest_size = int(inventory["largest_file"]["size_bytes"]) if inventory["largest_file"] else 0
    working_set = int(largest_size * float(settings.get_disk_space_output_multiplier()))
    start_batch = min(total_bytes, 500 * GIB)
    return {
        "schema_version": SCHEMA_VERSION,
        "source": {"path": str(source), "library_id": library_id},
        "inventory": inventory,
        "savings": _savings_summary(total_bytes, samples, history, {item.lower() for item in (skip_codecs or [])}),
        "runtime": _runtime_summary(total_bytes, throughput),
        "cache": {
            "path": str(cache_path),
            "free_bytes": int(disk.free),
            "reserve_bytes": reserve,
            "largest_file_working_set_bytes": working_set,
            "can_stage_largest_file": int(disk.free) >= reserve + working_set,
        },
        "allocation": _allocation(settings),
        "batch_recommendation": {
            "minimum_bytes": 500 * GIB,
            "maximum_bytes": TIB,
            "starting_bytes": start_batch,
            "guidance": "Use copied or snapshot-backed batches and require a clean verification gate between batches.",
        },
        "evidence_boundary": {
            "task_or_library_writes": False,
            "full_hashing": False,
            "cluster_runtime_projection": "unknown until master-plus-M4 canary throughput is recorded",
        },
    }


def _plan_destination(settings: Any, output_name: str) -> Path:
    if Path(output_name).name != output_name or PLAN_NAME_PATTERN.fullmatch(output_name) is None:
        raise ValueError("plan output must be a JSON filename without directory components")
    root = (Path(settings.get_userdata_path()) / "planning").resolve()
    destination = (root / output_name).resolve()
    if not destination.is_relative_to(root):
        raise ValueError("plan output filename escapes the planning directory")
    return destination


def save_plan(settings: Any, output_name: str, payload: dict[str, Any]) -> Path:
    destination = _plan_destination(settings, output_name)
    atomic_json_write(destination, payload, mode=0o600)
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compresso plan", description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--library-id", type=int)
    source.add_argument("--path")
    parser.add_argument("--sample-size", type=int, default=200)
    parser.add_argument("--full-inventory", action="store_true", help="Probe every media file instead of a bounded sample.")
    parser.add_argument("--seed", type=int, default=20)
    parser.add_argument("--output", required=True, help="JSON filename stored under the user-data planning directory.")
    args = parser.parse_args(argv)
    settings = Config()
    try:
        record = load_library_record(settings, args.library_id) if args.library_id is not None else None
        source_path = record["path"] if record else args.path
        library_id = int(record["id"]) if record else None
        skip_codecs = record["skip_codecs"] if record else []
        historical, throughput = load_historical_evidence(settings, library_id)
        report = build_capacity_plan(
            settings,
            source_path,
            library_id=library_id,
            sample_size=args.sample_size,
            full_inventory=args.full_inventory,
            seed=args.seed,
            skip_codecs=skip_codecs,
            historical_savings=historical,
            throughput_bytes_per_second=throughput,
        )
        destination = save_plan(settings, args.output, report)
    except (OSError, TypeError, ValueError) as error:
        sys.stderr.write(json.dumps({"error": str(error)}, sort_keys=True) + "\n")
        return 2
    sys.stdout.write(json.dumps({**report, "saved_to": str(destination)}, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
