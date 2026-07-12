#!/usr/bin/env python3

"""Tests for the metadata-only large-library benchmark."""

import pytest

from compresso.libs.library_scale_benchmark import matching_threshold, run_benchmark, synthetic_walk, threshold_failures
from compresso.libs.libraryscanner import iter_sorted_library_directories


@pytest.mark.unittest
def test_synthetic_walk_is_bounded_and_exact():
    batches = list(synthetic_walk(2_501, files_per_directory=1_000))

    assert [len(files) for _root, _subfolders, files in batches] == [1_000, 1_000, 501]
    assert sum(len(files) for _root, _subfolders, files in batches) == 2_501


@pytest.mark.unittest
def test_scanner_directory_iterator_sorts_each_bounded_batch():
    walk = [("/media", ["b", "a"], ["z.mkv", "a.mkv"])]

    assert list(iter_sorted_library_directories(walk)) == [("/media", ["a.mkv", "z.mkv"])]
    assert walk[0][1] == ["a", "b"]


@pytest.mark.unittest
def test_small_benchmark_schedules_every_entry_and_reports_latency():
    result = run_benchmark(1_500, batch_size=250)

    assert result["entry_count"] == 1_500
    assert result["database_bytes_per_entry"] > 0
    assert result["peak_rss_delta_mb"] < 128
    assert result["sqlite_lookup_p95_ms"] >= 0
    assert result["sqlite_page_p95_ms"] >= 0


@pytest.mark.unittest
def test_threshold_selection_and_failures():
    config = {
        "tiers": {
            "10000": {"max_duration_seconds": 2},
            "100000": {"max_duration_seconds": 20},
        }
    }
    assert matching_threshold(9_000, config)["max_duration_seconds"] == 2
    assert matching_threshold(50_000, config)["max_duration_seconds"] == 20

    result = {
        "duration_seconds": 3,
        "peak_rss_delta_mb": 1,
        "sqlite_lookup_p95_ms": 1,
        "sqlite_page_p95_ms": 1,
    }
    thresholds = {
        "max_duration_seconds": 2,
        "max_peak_rss_delta_mb": 2,
        "max_sqlite_lookup_p95_ms": 2,
        "max_sqlite_page_p95_ms": 2,
    }
    assert threshold_failures(result, thresholds) == ["duration_seconds=3.0 exceeded max_duration_seconds=2.0"]


@pytest.mark.unittest
def test_empty_threshold_configuration_has_clear_error():
    with pytest.raises(ValueError, match="no tier entries"):
        matching_threshold(10_000, {"tiers": {}})
