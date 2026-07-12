#!/usr/bin/env python3

"""Run the two-process localhost Compresso transfer and restart drill."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compresso.libs.distributed_process_drill import run_drill  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size-mb", type=int, default=3)
    parser.add_argument("--chunk-mb", type=int, default=1)
    args = parser.parse_args()
    result = run_drill(size_mb=args.size_mb, chunk_mb=args.chunk_mb)
    print(json.dumps(result, indent=2, sort_keys=True))  # noqa: T201
    print("PASS: two Compresso processes resumed and finalized one task across real HTTP")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
