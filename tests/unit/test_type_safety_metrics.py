#!/usr/bin/env python3
"""Tests for the read-only type-safety metrics reporter."""

import json

import pytest


@pytest.mark.unittest
def test_collect_metrics_separates_production_and_test_code(tmp_path):
    from scripts.type_safety_metrics import collect_metrics

    package = tmp_path / "compresso"
    package.mkdir()
    (package / "sample.py").write_text(
        "def unchecked(value):\n    return value\n\ndef checked(value: str) -> str:\n    return value\n",
        encoding="utf-8",
    )

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_sample.py").write_text("def test_sample():\n    assert True\n", encoding="utf-8")

    frontend = package / "webserver" / "frontend" / "src"
    (frontend / "__tests__").mkdir(parents=True)
    (frontend / "utility.js").write_text("export const value = 1\n", encoding="utf-8")
    (frontend / "typed.ts").write_text("export const typed: number = 1\n", encoding="utf-8")
    (frontend / "__tests__" / "utility.test.js").write_text("expect(true).toBe(true)\n", encoding="utf-8")
    (frontend / "Panel.vue").write_text(
        '<template><div /></template>\n<script setup lang="ts">\nconst count: number = 1\n</script>\n',
        encoding="utf-8",
    )
    dependency = package / "webserver" / "frontend" / "node_modules" / "vendor.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("def unchecked_dependency(value):\n    return value\n", encoding="utf-8")

    metrics = collect_metrics(tmp_path)

    assert metrics.python_production.files == 1
    assert metrics.python_production.functions == 2
    assert metrics.python_production.complete_functions == 1
    assert metrics.python_production.unchecked_function_loc == 2
    assert metrics.python_tests.files == 1
    assert metrics.frontend.production_js_files == 1
    assert metrics.frontend.production_ts_files == 1
    assert metrics.frontend.test_js_files == 1
    assert metrics.frontend.vue_files == 1
    assert metrics.frontend.typed_vue_files == 1


@pytest.mark.unittest
def test_metrics_json_is_machine_readable(tmp_path):
    from scripts.type_safety_metrics import collect_metrics, render_json

    (tmp_path / "compresso").mkdir()
    (tmp_path / "tests").mkdir()

    payload = json.loads(render_json(collect_metrics(tmp_path)))

    assert payload["python_production"]["files"] == 0
    assert payload["frontend"]["production_js_files"] == 0


@pytest.mark.unittest
def test_collect_metrics_recognizes_case_insensitive_vue_script_tags(tmp_path):
    from scripts.type_safety_metrics import collect_metrics

    frontend = tmp_path / "compresso" / "webserver" / "frontend" / "src"
    frontend.mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (frontend / "Panel.vue").write_text(
        '<template><div /></template>\n<SCRIPT SETUP LANG="TS">\nconst count: number = 1\n</SCRIPT\t\n data-close>\n',
        encoding="utf-8",
    )

    metrics = collect_metrics(tmp_path)

    assert metrics.frontend.typed_vue_files == 1
    assert metrics.frontend.vue_script_loc == 3
