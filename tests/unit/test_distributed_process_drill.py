#!/usr/bin/env python3

"""Unit coverage for the isolated two-process distributed drill."""

from unittest.mock import MagicMock, patch

import pytest

from compresso.libs.distributed_process_drill import _CompressoProcess


@pytest.mark.unittest
def test_drill_process_does_not_inherit_the_hosts_production_disk_reserve(tmp_path):
    process = MagicMock()
    process.poll.return_value = None
    node = _CompressoProcess("worker", tmp_path / "worker", 54321, tmp_path)

    with (
        patch("compresso.libs.distributed_process_drill.subprocess.Popen", return_value=process) as popen,
        patch(
            "compresso.libs.distributed_process_drill._request_json",
            return_value=(200, {"ready": True}),
        ),
    ):
        node.start()
        node.stop()

    environment = popen.call_args.kwargs["env"]
    assert environment["HOME_DIR"] == str(tmp_path / "worker")
    for name in ("config", "cache", "logs", "plugins", "staging", "library", "userdata"):
        assert environment[f"{name.removesuffix('s')}_path" if name == "logs" else f"{name}_path"] == str(
            tmp_path / "worker" / name
        )
    assert environment["minimum_free_space_gb"] == "0"
