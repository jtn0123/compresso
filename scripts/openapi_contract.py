#!/usr/bin/env python3

"""Generate or verify Compresso's checked-in OpenAPI contract."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from compresso.webserver.api_v2.schema.swagger import generate_swagger_file  # noqa: E402

DEFAULT_CONTRACT = ROOT / "compresso" / "webserver" / "docs" / "api_schema_v2.json"


class ContractGenerationError(RuntimeError):
    """Raised when one or more registered routes cannot be documented."""


class ContractDriftError(RuntimeError):
    """Raised when the checked-in contract differs from a fresh generation."""


def _display_path(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def render_contract() -> bytes:
    """Return a freshly generated contract, rejecting undocumented routes."""
    with tempfile.TemporaryDirectory(prefix="compresso-openapi-") as directory:
        generated_path = Path(directory) / "api_schema_v2.json"
        errors = generate_swagger_file(generated_path)
        if errors:
            details = "\n".join(f"  - {error}" for error in errors)
            raise ContractGenerationError(f"OpenAPI generation failed:\n{details}")
        return generated_path.read_bytes()


def write_contract(output_path: Path = DEFAULT_CONTRACT) -> None:
    """Regenerate ``output_path`` only after every route succeeds."""
    generated = render_contract()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(generated)


def check_contract(output_path: Path = DEFAULT_CONTRACT) -> None:
    """Fail when ``output_path`` is missing or differs from current routes."""
    generated = render_contract()
    if not output_path.is_file() or output_path.read_bytes() != generated:
        raise ContractDriftError(
            f"OpenAPI contract drift detected in {_display_path(output_path)}. "
            "Run scripts/openapi_contract.py to regenerate it."
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the checked-in contract without modifying it",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_CONTRACT,
        help="OpenAPI JSON output path",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    output_path: Path = args.output.resolve()
    try:
        if args.check:
            check_contract(output_path)
            print(f"OpenAPI contract is current: {_display_path(output_path)}")  # noqa: T201
        else:
            write_contract(output_path)
            print(f"Generated OpenAPI contract: {_display_path(output_path)}")  # noqa: T201
    except (ContractDriftError, ContractGenerationError) as error:
        print(str(error))  # noqa: T201
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
