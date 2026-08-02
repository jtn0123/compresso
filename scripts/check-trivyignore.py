#!/usr/bin/env python3

"""Enforce review discipline on Trivy vulnerability suppressions.

A suppression that never expires hides a finding forever: the reasoning that
made it safe (`not reachable from inside the image`, `only used during package
installation`) can stop being true after a refactor, and nothing re-checks it.

Trivy itself stops applying an entry once its ``expired_at`` date passes, so the
image scan is the real enforcement. This script runs in the fast lint lane so
the problems are reported before a Docker build: it rejects entries that are
missing a justification or an expiry, entries whose expiry is so far out that it
is effectively permanent, and entries that have already lapsed.

Usage:
    python scripts/check-trivyignore.py [--path .trivyignore.yaml] [--max-days 180]
"""

import argparse
import datetime
import sys
from pathlib import Path

import yaml

DEFAULT_PATH = Path(".trivyignore.yaml")
DEFAULT_MAX_DAYS = 180
LEGACY_PATH = Path(".trivyignore")


def _parse_date(value: object) -> datetime.date | None:
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, str):
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            return None
    return None


def check(path: Path, max_days: int, today: datetime.date) -> list[str]:
    problems: list[str] = []

    if LEGACY_PATH.exists():
        problems.append(
            f"{LEGACY_PATH} still exists. Trivy reads it automatically, so suppressions would come "
            f"from two places. Move any remaining entries into {path} and delete it."
        )

    if not path.exists():
        return [f"{path} is missing."]

    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = document.get("vulnerabilities")
    if not isinstance(entries, list):
        return [f"{path} has no `vulnerabilities:` list."]

    seen: set[str] = set()
    horizon = today + datetime.timedelta(days=max_days)

    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            problems.append(f"entry {position} is not a mapping")
            continue

        identifier = entry.get("id")
        label = identifier if isinstance(identifier, str) and identifier else f"entry {position}"

        if not isinstance(identifier, str) or not identifier:
            problems.append(f"{label}: missing `id`")
        elif identifier in seen:
            problems.append(f"{label}: duplicate suppression")
        else:
            seen.add(identifier)

        statement = entry.get("statement")
        if not isinstance(statement, str) or len(statement.strip()) < 40:
            problems.append(
                f"{label}: needs a `statement` explaining why this finding is not reachable (at least 40 characters)"
            )

        expires = _parse_date(entry.get("expired_at"))
        if expires is None:
            problems.append(f"{label}: needs an `expired_at` date (YYYY-MM-DD)")
            continue
        if expires < today:
            problems.append(
                f"{label}: expired on {expires.isoformat()}. Re-verify the finding, then either fix it "
                f"or renew the entry with fresh reasoning."
            )
        elif expires > horizon:
            problems.append(
                f"{label}: expires {expires.isoformat()}, more than {max_days} days out. "
                f"Suppressions must be revisited on a schedule."
            )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--max-days", type=int, default=DEFAULT_MAX_DAYS)
    args = parser.parse_args()

    problems = check(args.path, args.max_days, datetime.date.today())
    if problems:
        print(f"{args.path}: {len(problems)} problem(s)", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print(f"{args.path}: all suppressions carry a justification and an unexpired review date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
