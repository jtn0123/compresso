#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
    tests.unit.test_benchmark.py

    Performance benchmarks for critical Compresso operations.
    Run with: pytest tests/unit/test_benchmark.py -v --benchmark-enable
    Requires pytest-benchmark: pip install pytest-benchmark
"""

import os
import pytest

try:
    import pytest_benchmark  # noqa: F401
    HAS_BENCHMARK = True
except ImportError:
    HAS_BENCHMARK = False

from compresso.libs import common


@pytest.mark.skipif(not HAS_BENCHMARK, reason="pytest-benchmark not installed")
@pytest.mark.benchmark
@pytest.mark.unittest
class TestCommonBenchmarks:

    def test_file_checksum_performance(self, benchmark, tmp_path):
        """Benchmark MD5 checksum on a 1MB file."""
        test_file = tmp_path / "bench.bin"
        test_file.write_bytes(os.urandom(1024 * 1024))
        benchmark(common.get_file_checksum, str(test_file))

    def test_file_fingerprint_sampled_performance(self, benchmark, tmp_path):
        """Benchmark sampled xxhash fingerprint on a 10MB file."""
        test_file = tmp_path / "bench_large.bin"
        test_file.write_bytes(os.urandom(10 * 1024 * 1024))
        benchmark(common.get_file_fingerprint, str(test_file), "sampled_xxhash_v1")

    def test_file_fingerprint_full_performance(self, benchmark, tmp_path):
        """Benchmark full xxhash fingerprint on a 1MB file."""
        test_file = tmp_path / "bench_full.bin"
        test_file.write_bytes(os.urandom(1024 * 1024))
        benchmark(common.get_file_fingerprint, str(test_file), "full_xxhash_v1")

    def test_json_dump_performance(self, benchmark, tmp_path):
        """Benchmark JSON write with validation."""
        out_file = str(tmp_path / "bench.json")
        data = {"key_{}".format(i): "value_{}".format(i) for i in range(100)}
        benchmark(common.json_dump_to_file, data, out_file)

    def test_random_string_performance(self, benchmark):
        """Benchmark random string generation."""
        benchmark(common.random_string, 32)
