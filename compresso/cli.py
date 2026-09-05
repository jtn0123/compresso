# SPDX-License-Identifier: GPL-3.0-only

"""Backward-compatible Compresso service and operations CLI dispatcher."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import cast

from compresso.ops.doctor import main as doctor_main
from compresso.ops.fault_lab import main as fault_lab_main
from compresso.ops.planner import main as planner_main
from compresso.ops.state_backup import main as state_main
from compresso.service import main as service_main


def main(argv: list[str] | None = None) -> int | None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "doctor":
        return doctor_main(arguments[1:])
    if arguments and arguments[0] == "fault-lab":
        return fault_lab_main(arguments[1:])
    if arguments and arguments[0] == "plan":
        return planner_main(arguments[1:])
    if arguments and arguments[0] == "state":
        return state_main(arguments[1:])
    if argv is not None:
        previous = sys.argv
        try:
            sys.argv = [previous[0], *arguments]
            return cast("Callable[[], int | None]", service_main)()
        finally:
            sys.argv = previous
    return cast("Callable[[], int | None]", service_main)()


if __name__ == "__main__":
    raise SystemExit(main())
