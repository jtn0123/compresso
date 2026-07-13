# SPDX-License-Identifier: GPL-3.0-only

"""Backward-compatible Compresso service and operations CLI dispatcher."""

from __future__ import annotations

import sys

from compresso.ops.doctor import main as doctor_main
from compresso.service import main as service_main


def main(argv: list[str] | None = None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "doctor":
        return doctor_main(arguments[1:])
    if argv is not None:
        previous = sys.argv
        try:
            sys.argv = [previous[0], *arguments]
            return service_main()
        finally:
            sys.argv = previous
    return service_main()


if __name__ == "__main__":
    raise SystemExit(main())
