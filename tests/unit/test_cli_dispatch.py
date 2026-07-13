# SPDX-License-Identifier: GPL-3.0-only

"""Tests for backward-compatible operational CLI dispatch."""

from unittest.mock import MagicMock

from compresso import cli


def test_no_subcommand_preserves_legacy_service_entrypoint(monkeypatch):
    monkeypatch.setattr(cli.sys, "argv", ["compresso"])
    legacy = MagicMock(return_value=None)
    monkeypatch.setattr(cli, "service_main", legacy)

    assert cli.main() is None
    legacy.assert_called_once_with()


def test_doctor_subcommand_is_dispatched_without_starting_service(monkeypatch):
    doctor = MagicMock(return_value=1)
    legacy = MagicMock()
    monkeypatch.setattr(cli, "doctor_main", doctor)
    monkeypatch.setattr(cli, "service_main", legacy)

    assert cli.main(["doctor", "--role", "worker", "--strict"]) == 1
    doctor.assert_called_once_with(["--role", "worker", "--strict"])
    legacy.assert_not_called()


def test_explicit_legacy_arguments_are_forwarded(monkeypatch):
    original_argv = list(cli.sys.argv)
    observed_argv = []

    def capture_argv():
        observed_argv.append(list(cli.sys.argv))
        return "served"

    legacy = MagicMock(side_effect=capture_argv)
    monkeypatch.setattr(cli, "service_main", legacy)

    assert cli.main(["--port", "9999"]) == "served"
    legacy.assert_called_once_with()
    assert observed_argv == [[original_argv[0], "--port", "9999"]]
    assert cli.sys.argv == original_argv
