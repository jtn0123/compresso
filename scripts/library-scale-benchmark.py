#!/usr/bin/env python3

"""Run Compresso's metadata-only large-library scan and scheduling benchmark."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compresso.libs.library_scale_benchmark import (  # noqa: E402
    matching_threshold,
    run_benchmark,
    run_real_pipeline_benchmark,
    threshold_failures,
    write_result,
)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=int, default=10_000)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument(
        "--mode",
        choices=("synthetic", "real"),
        default="synthetic",
        help="synthetic: raw SQLite scheduling floor; real: the actual peewee task pipeline",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--thresholds",
        type=Path,
        default=root / "docs" / "performance" / "large-library-thresholds.json",
    )
    parser.add_argument("--assert-thresholds", action="store_true")
    args = parser.parse_args()

    if args.mode == "real":
        result = run_real_pipeline_benchmark(args.entries, args.batch_size)
    else:
        result = run_benchmark(args.entries, args.batch_size)
    if args.output:
        write_result(result, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))  # noqa: T201

    if not args.assert_thresholds:
        return 0
    threshold_config = json.loads(args.thresholds.read_text())
    if args.mode == "real":
        real_tiers = threshold_config.get("real_tiers")
        if not real_tiers:
            print("FAIL: threshold configuration has no real_tiers object", file=sys.stderr)  # noqa: T201
            return 1
        threshold_config = {"tiers": real_tiers}
    thresholds = matching_threshold(args.entries, threshold_config)
    failures = threshold_failures(result, thresholds)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)  # noqa: T201
        return 1
    print(f"PASS: {args.entries} entries stayed within the versioned scale thresholds")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
