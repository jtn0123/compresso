# SPDX-License-Identifier: GPL-3.0-only

"""Read-only capacity planning tests for large media libraries."""

import json
import os
import sqlite3
import stat
from contextlib import closing
from types import SimpleNamespace

import pytest

from compresso.ops import planner
from compresso.webserver.helpers import library_analysis


class FakeSettings:
    def __init__(self, root):
        self.root = root
        for name in ("config", "cache", "userdata"):
            (root / name).mkdir(parents=True)

    def get_config_path(self):
        return str(self.root / "config")

    def get_cache_path(self):
        return str(self.root / "cache")

    def get_userdata_path(self):
        return str(self.root / "userdata")

    def get_minimum_free_space_gb(self):
        return 2

    def get_disk_space_output_multiplier(self):
        return 2.0

    def get_default_worker_cap(self):
        return 2

    def get_remote_installations(self):
        return [
            {
                "name": "m4-worker",
                "available": True,
                "capabilities": {
                    "platform": {"system": "Darwin", "machine": "arm64"},
                    "video_encoders": ["h264_videotoolbox", "hevc_videotoolbox"],
                },
            }
        ]


def _write_media(root, name, size):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes([size % 251]) * size)
    return path


def test_library_analysis_iterator_is_bounded_sorted_and_media_only(tmp_path):
    _write_media(tmp_path, "b/movie.mkv", 5)
    _write_media(tmp_path, "a/clip.mp4", 4)
    _write_media(tmp_path, "a/readme.txt", 3)

    relative = [path.relative_to(tmp_path).as_posix() for path in library_analysis.iter_media_files(tmp_path)]

    assert relative == ["a/clip.mp4", "b/movie.mkv"]


def test_sampled_plan_inventory_is_exact_and_probe_selection_is_deterministic(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    for index in range(8):
        _write_media(source, f"movie-{index}.mkv", 100 + index)
    _write_media(source, "poster.jpg", 50)
    probed = []

    def probe(path):
        probed.append(path)
        return {"codec": "h264", "resolution": "1080p", "file_size": 100, "bitrate_mbps": 8}

    monkeypatch.setattr(
        planner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=10_000, used=2_000, free=8_000),
    )
    first = planner.build_capacity_plan(settings, source, sample_size=3, seed=20, probe=probe)
    first_selection = list(probed)
    probed.clear()
    second = planner.build_capacity_plan(settings, source, sample_size=3, seed=20, probe=probe)

    assert first["inventory"]["media_files"] == 8
    assert first["inventory"]["total_bytes"] == sum(100 + index for index in range(8))
    assert first["inventory"]["sampled_files"] == 3
    assert first["inventory"]["largest_file"]["relative_path"] == "movie-7.mkv"
    assert first_selection == probed
    assert first["inventory"] == second["inventory"]


def test_full_inventory_probes_every_media_file(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    for index in range(4):
        _write_media(source, f"movie-{index}.mkv", 20)
    probes = []
    monkeypatch.setattr(
        planner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=10_000, used=2_000, free=8_000),
    )

    report = planner.build_capacity_plan(
        settings,
        source,
        sample_size=1,
        full_inventory=True,
        probe=lambda path: probes.append(path) or {"codec": "hevc", "resolution": "4K", "file_size": 20, "bitrate_mbps": 2},
    )

    assert len(probes) == 4
    assert report["inventory"]["sampled_files"] == 4
    assert report["inventory"]["mode"] == "full-probe"


def test_savings_and_runtime_ranges_use_history_without_false_precision(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    _write_media(source, "movie.mkv", 1_000)
    historical = {("h264", "1080p"): {"avg_savings_pct": 40.0, "count": 25}}
    monkeypatch.setattr(
        planner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=100_000, used=20_000, free=80_000),
    )

    report = planner.build_capacity_plan(
        settings,
        source,
        sample_size=10,
        probe=lambda _path: {
            "codec": "h264",
            "resolution": "1080p",
            "file_size": 1_000,
            "bitrate_mbps": 8,
        },
        historical_savings=historical,
        throughput_bytes_per_second=[100.0, 200.0, 300.0, 400.0],
    )

    assert report["savings"]["status"] == "estimated"
    assert report["savings"]["confidence"] == "high"
    assert report["savings"]["range_pct"] == {"low": 35.0, "high": 45.0}
    assert report["runtime"]["status"] == "estimated"
    assert report["runtime"]["single_slot_seconds"]["low"] < report["runtime"]["single_slot_seconds"]["high"]


def test_missing_history_is_reported_as_unknown(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    _write_media(source, "movie.mkv", 100)
    monkeypatch.setattr(
        planner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=1_000, used=100, free=900),
    )

    report = planner.build_capacity_plan(
        settings,
        source,
        probe=lambda _path: {"codec": "unknown", "resolution": "unknown", "file_size": 100},
    )

    assert report["savings"]["status"] == "unknown"
    assert report["savings"]["range_pct"] is None
    assert report["runtime"] == {"status": "unknown", "historical_samples": 0, "single_slot_seconds": None}


def test_cache_allocation_and_batch_advice_are_conservative(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    _write_media(source, "large.mkv", 1_000)
    monkeypatch.setattr(
        planner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=10_000, used=4_000, free=6_000),
    )

    report = planner.build_capacity_plan(settings, source, probe=lambda _path: {"codec": "hevc", "file_size": 1_000})

    assert report["cache"]["largest_file_working_set_bytes"] == 2_000
    assert report["cache"]["can_stage_largest_file"] is False
    assert report["allocation"]["master"]["scanner"] is True
    assert report["allocation"]["remote_workers"][0]["initial_encode_slots"] == 1
    assert report["batch_recommendation"]["maximum_bytes"] == 1024**4


def test_plan_report_filename_is_confined_to_userdata(tmp_path):
    settings = FakeSettings(tmp_path)
    payload = {"schema_version": 1, "inventory": {}}

    destination = planner.save_plan(settings, "capacity.json", payload)

    assert destination == tmp_path / "userdata" / "planning" / "capacity.json"
    assert json.loads(destination.read_text()) == payload
    mode = destination.stat().st_mode
    assert mode & stat.S_IRUSR
    assert mode & stat.S_IWUSR
    if os.name != "nt":
        assert mode & 0o777 == 0o600
    with pytest.raises(ValueError, match="filename"):
        planner.save_plan(settings, "../outside.json", payload)


def test_source_path_rejects_protected_and_non_directory_paths(tmp_path):
    settings = FakeSettings(tmp_path)
    file_path = tmp_path / "source.mkv"
    file_path.write_bytes(b"x")

    with pytest.raises(ValueError, match="directory"):
        planner.validate_source_path(file_path, settings)
    with pytest.raises(ValueError, match="protected"):
        planner.validate_source_path(tmp_path / "config", settings)


def test_library_id_resolution_reads_sqlite_without_mutating_it(tmp_path):
    settings = FakeSettings(tmp_path)
    database_path = tmp_path / "config" / "compresso.db"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("CREATE TABLE libraries (id INTEGER PRIMARY KEY, name TEXT, path TEXT, skip_codecs TEXT)")
        connection.execute(
            "INSERT INTO libraries(id, name, path, skip_codecs) VALUES (7, 'Movies', '/Volumes/Media', '[\"hevc\"]')"
        )
    before = database_path.read_bytes()

    record = planner.load_library_record(settings, 7)

    assert record == {"id": 7, "name": "Movies", "path": "/Volumes/Media", "skip_codecs": ["hevc"]}
    assert database_path.read_bytes() == before


def test_invalid_sample_size_is_rejected(tmp_path):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    source.mkdir()

    with pytest.raises(ValueError, match="sample_size"):
        planner.build_capacity_plan(settings, source, sample_size=0)


def test_historical_evidence_reads_savings_and_throughput(tmp_path):
    settings = FakeSettings(tmp_path)
    database_path = tmp_path / "config" / "compresso.db"
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            "CREATE TABLE compressionstats (source_size INTEGER, destination_size INTEGER, source_codec TEXT, "
            "source_resolution TEXT, encoding_duration_seconds REAL, library_id INTEGER)"
        )
        connection.executemany(
            "INSERT INTO compressionstats VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1_000, 600, "H264", "1080p", 10, 7),
                (2_000, 1_000, "h264", "1080p", 20, 7),
                (500, 400, "hevc", "4K", 0, 8),
            ],
        )

    historical, throughput = planner.load_historical_evidence(settings, 7)

    assert historical[("h264", "1080p")]["count"] == 2
    assert historical[("h264", "1080p")]["avg_savings_pct"] == pytest.approx(46.666, rel=0.01)
    assert throughput == [100.0, 100.0]


def test_historical_evidence_and_library_lookup_fail_closed_without_database(tmp_path):
    settings = FakeSettings(tmp_path)

    assert planner.load_historical_evidence(settings, None) == ({}, [])
    with pytest.raises(ValueError, match="does not exist"):
        planner.load_library_record(settings, 1)


def test_partial_savings_evidence_reports_coverage_and_low_confidence(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    _write_media(source, "known.mkv", 20)
    _write_media(source, "unknown.mp4", 80)
    monkeypatch.setattr(
        planner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=1_000, used=100, free=900),
    )

    report = planner.build_capacity_plan(
        settings,
        source,
        full_inventory=True,
        probe=lambda path: {
            "codec": "h264" if path.endswith("known.mkv") else "unknown",
            "resolution": "1080p",
        },
        historical_savings={("h264", "1080p"): {"avg_savings_pct": 40, "count": 25}},
    )

    assert report["savings"]["known_sample_coverage_pct"] == 20.0
    assert report["savings"]["confidence"] == "low"


def test_empty_inventory_and_short_runtime_history_remain_unknown(tmp_path, monkeypatch):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    source.mkdir()
    monkeypatch.setattr(
        planner.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=1_000, used=100, free=900),
    )

    report = planner.build_capacity_plan(settings, source, throughput_bytes_per_second=[100, 200])

    assert report["inventory"]["largest_file"] is None
    assert report["runtime"]["status"] == "unknown"
    assert report["runtime"]["historical_samples"] == 2


def test_cli_path_mode_saves_planner_result(tmp_path, monkeypatch, capsys):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    source.mkdir()
    payload = {"schema_version": 1, "inventory": {"media_files": 0}}
    monkeypatch.setattr(planner, "Config", lambda: settings)
    monkeypatch.setattr(planner, "load_historical_evidence", lambda _settings, _library_id: ({}, []))
    monkeypatch.setattr(planner, "build_capacity_plan", lambda *_args, **_kwargs: payload)

    exit_code = planner.main(["--path", str(source), "--output", "capacity.json"])

    assert exit_code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["inventory"]["media_files"] == 0
    assert (tmp_path / "settings" / "userdata" / "planning" / "capacity.json").is_file()


def test_cli_returns_two_for_invalid_output_filename(tmp_path, monkeypatch, capsys):
    settings = FakeSettings(tmp_path / "settings")
    source = tmp_path / "library"
    source.mkdir()
    monkeypatch.setattr(planner, "Config", lambda: settings)
    monkeypatch.setattr(planner, "load_historical_evidence", lambda _settings, _library_id: ({}, []))
    monkeypatch.setattr(planner, "build_capacity_plan", lambda *_args, **_kwargs: {"schema_version": 1})

    exit_code = planner.main(["--path", str(source), "--output", "../outside.json"])

    assert exit_code == 2
    assert "filename" in json.loads(capsys.readouterr().err)["error"]
