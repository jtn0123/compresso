#!/usr/bin/env python3

"""
tests.unit.test_trivyignore_policy.py

Trivy suppressions hide real findings, so every entry has to say why it is safe
and carry a date on which that reasoning gets re-checked. These tests cover the
checker that enforces it, and assert the committed file passes.
"""

import datetime
import importlib.util
import pathlib

import pytest
import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "scripts" / "check-trivyignore.py"
COMMITTED_PATH = REPO_ROOT / ".trivyignore.yaml"

_spec = importlib.util.spec_from_file_location("check_trivyignore", CHECKER_PATH)
assert _spec is not None and _spec.loader is not None
check_trivyignore = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_trivyignore)

TODAY = datetime.date(2026, 8, 1)
GOOD_STATEMENT = "Not reachable from inside the image; the container shares the host kernel and never loads it."


def _write(tmp_path: pathlib.Path, entries: list[dict[str, object]]) -> pathlib.Path:
    path = tmp_path / ".trivyignore.yaml"
    path.write_text(yaml.safe_dump({"vulnerabilities": entries}), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def no_legacy_file(monkeypatch, tmp_path):
    """Point the legacy-file check at an empty directory unless a test sets one."""
    monkeypatch.setattr(check_trivyignore, "LEGACY_PATH", tmp_path / "absent" / ".trivyignore")


@pytest.mark.unittest
class TestCommittedFile:
    def test_committed_suppressions_pass_the_policy(self):
        problems = check_trivyignore.check(COMMITTED_PATH, check_trivyignore.DEFAULT_MAX_DAYS, TODAY)
        assert problems == []

    def test_legacy_plain_trivyignore_is_gone(self):
        assert not (REPO_ROOT / ".trivyignore").exists(), (
            "Trivy reads .trivyignore automatically; keeping it alongside .trivyignore.yaml "
            "would give suppressions two sources of truth."
        )

    def test_every_committed_entry_is_dated(self):
        document = yaml.safe_load(COMMITTED_PATH.read_text(encoding="utf-8"))
        assert document["vulnerabilities"]
        for entry in document["vulnerabilities"]:
            assert entry.get("expired_at"), f"{entry.get('id')} has no review date"


@pytest.mark.unittest
class TestPolicyRejections:
    def test_rejects_a_missing_expiry(self, tmp_path):
        path = _write(tmp_path, [{"id": "CVE-2026-1", "statement": GOOD_STATEMENT}])
        problems = check_trivyignore.check(path, 180, TODAY)
        assert any("expired_at" in problem for problem in problems)

    def test_rejects_an_expired_entry(self, tmp_path):
        path = _write(tmp_path, [{"id": "CVE-2026-1", "statement": GOOD_STATEMENT, "expired_at": "2026-07-01"}])
        problems = check_trivyignore.check(path, 180, TODAY)
        assert any("expired on 2026-07-01" in problem for problem in problems)

    def test_rejects_an_effectively_permanent_entry(self, tmp_path):
        path = _write(tmp_path, [{"id": "CVE-2026-1", "statement": GOOD_STATEMENT, "expired_at": "2030-01-01"}])
        problems = check_trivyignore.check(path, 180, TODAY)
        assert any("more than 180 days out" in problem for problem in problems)

    def test_rejects_a_missing_or_thin_justification(self, tmp_path):
        path = _write(tmp_path, [{"id": "CVE-2026-1", "statement": "wontfix", "expired_at": "2026-09-01"}])
        problems = check_trivyignore.check(path, 180, TODAY)
        assert any("statement" in problem for problem in problems)

    def test_rejects_duplicate_suppressions(self, tmp_path):
        entry = {"id": "CVE-2026-1", "statement": GOOD_STATEMENT, "expired_at": "2026-09-01"}
        path = _write(tmp_path, [entry, dict(entry)])
        problems = check_trivyignore.check(path, 180, TODAY)
        assert any("duplicate" in problem for problem in problems)

    def test_accepts_a_well_formed_entry(self, tmp_path):
        path = _write(tmp_path, [{"id": "CVE-2026-1", "statement": GOOD_STATEMENT, "expired_at": "2026-09-01"}])
        assert check_trivyignore.check(path, 180, TODAY) == []

    def test_flags_a_surviving_legacy_file(self, tmp_path, monkeypatch):
        legacy = tmp_path / ".trivyignore"
        legacy.write_text("CVE-2026-1\n", encoding="utf-8")
        monkeypatch.setattr(check_trivyignore, "LEGACY_PATH", legacy)
        path = _write(tmp_path, [{"id": "CVE-2026-1", "statement": GOOD_STATEMENT, "expired_at": "2026-09-01"}])
        problems = check_trivyignore.check(path, 180, TODAY)
        assert any("two places" in problem for problem in problems)
