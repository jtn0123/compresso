#!/usr/bin/python3

"""Create and verify representative media canary manifests."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from compresso.libs.media_manifest import create_manifest, verify_manifest  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    create = subcommands.add_parser("create", help="record checksums and stream/HDR metadata before processing")
    create.add_argument("root")
    create.add_argument("output")
    create.add_argument("--sample-size", type=int)
    create.add_argument("--seed", type=int, default=20)
    verify = subcommands.add_parser("verify", help="account for and validate every manifest entry after processing")
    verify.add_argument("manifest")
    verify.add_argument("--root")
    verify.add_argument("--report")
    args = parser.parse_args()

    if args.command == "create":
        result = create_manifest(args.root, args.output, sample_size=args.sample_size, seed=args.seed)
        print(json.dumps({"manifest": args.output, "files": len(result["files"])}, indent=2))  # noqa: T201
        return 0
    result = verify_manifest(args.manifest, current_root=args.root, report_path=args.report)
    print(json.dumps({key: value for key, value in result.items() if key != "files"}, indent=2))  # noqa: T201
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
