#!/usr/bin/env python3
"""
compresso.type_safety_metrics.py

Written by:               Compresso contributors
Date:                     Monday July 20 2026

Copyright:
       Copyright (C) Josh Sunnex - All Rights Reserved

       Permission is hereby granted, free of charge, to any person obtaining a copy
       of this software and associated documentation files (the "Software"), to deal
       in the Software without restriction, including without limitation the rights
       to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
       copies of the Software, and to permit persons to whom the Software is
       furnished to do so, subject to the following conditions:

       The above copyright notice and this permission notice shall be included in all
       copies or substantial portions of the Software.

       THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
       IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
       FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
       AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
       LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
       OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
       SOFTWARE.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

GENERATED_START = "<!-- BEGIN GENERATED TYPE SAFETY METRICS -->"
GENERATED_END = "<!-- END GENERATED TYPE SAFETY METRICS -->"


@dataclass(frozen=True)
class PythonMetrics:
    files: int = 0
    nonblank_loc: int = 0
    functions: int = 0
    complete_functions: int = 0
    incomplete_function_loc: int = 0
    unchecked_function_loc: int = 0


@dataclass(frozen=True)
class FrontendMetrics:
    production_js_files: int = 0
    production_js_loc: int = 0
    production_ts_files: int = 0
    production_ts_loc: int = 0
    test_js_files: int = 0
    test_js_loc: int = 0
    vue_files: int = 0
    typed_vue_files: int = 0
    vue_script_loc: int = 0


@dataclass(frozen=True)
class TypeSafetyMetrics:
    revision: str
    python_production: PythonMetrics
    python_tests: PythonMetrics
    frontend: FrontendMetrics


def _nonblank_count(lines: Iterable[str]) -> int:
    return sum(bool(line.strip()) for line in lines)


def _function_is_complete(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    parameters = list(function.args.posonlyargs) + list(function.args.args) + list(function.args.kwonlyargs)
    if parameters and parameters[0].arg in {"self", "cls"}:
        parameters = parameters[1:]
    if function.args.vararg:
        parameters.append(function.args.vararg)
    if function.args.kwarg:
        parameters.append(function.args.kwarg)
    return function.returns is not None and all(parameter.annotation is not None for parameter in parameters)


def _function_has_annotation(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    parameters = list(function.args.posonlyargs) + list(function.args.args) + list(function.args.kwonlyargs)
    if parameters and parameters[0].arg in {"self", "cls"}:
        parameters = parameters[1:]
    if function.args.vararg:
        parameters.append(function.args.vararg)
    if function.args.kwarg:
        parameters.append(function.args.kwarg)
    return function.returns is not None or any(parameter.annotation is not None for parameter in parameters)


def _collect_python(paths: Iterable[Path]) -> PythonMetrics:
    files = nonblank_loc = functions = complete_functions = incomplete_function_loc = unchecked_function_loc = 0
    for path in paths:
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source, filename=str(path), type_comments=True)
        files += 1
        nonblank_loc += _nonblank_count(lines)
        incomplete_lines: set[int] = set()
        unchecked_lines: set[int] = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            functions += 1
            line_range = range(node.lineno, (node.end_lineno or node.lineno) + 1)
            if _function_is_complete(node):
                complete_functions += 1
            else:
                incomplete_lines.update(line_range)
            if not _function_has_annotation(node):
                unchecked_lines.update(line_range)
        incomplete_function_loc += _nonblank_count(lines[line_number - 1] for line_number in incomplete_lines)
        unchecked_function_loc += _nonblank_count(lines[line_number - 1] for line_number in unchecked_lines)
    return PythonMetrics(
        files=files,
        nonblank_loc=nonblank_loc,
        functions=functions,
        complete_functions=complete_functions,
        incomplete_function_loc=incomplete_function_loc,
        unchecked_function_loc=unchecked_function_loc,
    )


def _is_test_script(path: Path) -> bool:
    return "__tests__" in path.parts or path.name.endswith((".test.js", ".spec.js", ".test.ts", ".spec.ts"))


def _vue_script_blocks(source: str) -> list[tuple[str, str]]:
    folded = source.casefold()
    blocks: list[tuple[str, str]] = []
    cursor = 0
    while True:
        opening_start = folded.find("<script", cursor)
        if opening_start < 0:
            return blocks
        opening_name_end = opening_start + len("<script")
        if opening_name_end < len(folded) and not (
            folded[opening_name_end].isspace() or folded[opening_name_end] == ">"
        ):
            cursor = opening_name_end
            continue
        opening_end = folded.find(">", opening_name_end)
        if opening_end < 0:
            return blocks

        closing_start = folded.find("</script", opening_end + 1)
        if closing_start < 0:
            return blocks
        closing_name_end = closing_start + len("</script")
        if closing_name_end < len(folded) and not (
            folded[closing_name_end].isspace() or folded[closing_name_end] == ">"
        ):
            cursor = closing_name_end
            continue
        closing_end = folded.find(">", closing_name_end)
        if closing_end < 0:
            return blocks

        blocks.append((source[opening_start : opening_end + 1], source[opening_end + 1 : closing_start]))
        cursor = closing_end + 1


def _vue_script_loc(source: str) -> int:
    return sum(_nonblank_count(body.splitlines()) + 2 for _, body in _vue_script_blocks(source))


def _collect_frontend(frontend_root: Path) -> FrontendMetrics:
    if not frontend_root.exists():
        return FrontendMetrics()

    production_js_files = production_js_loc = production_ts_files = production_ts_loc = 0
    test_js_files = test_js_loc = vue_files = typed_vue_files = vue_script_loc = 0
    for path in sorted(frontend_root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix == ".vue":
            source = path.read_text(encoding="utf-8")
            vue_files += 1
            typed_vue_files += int(
                any(
                    re.search(r"\blang=[\"']ts[\"']", opening, flags=re.IGNORECASE)
                    for opening, _ in _vue_script_blocks(source)
                )
            )
            vue_script_loc += _vue_script_loc(source)
            continue
        if path.suffix not in {".js", ".ts"}:
            continue
        nonblank_loc = _nonblank_count(path.read_text(encoding="utf-8").splitlines())
        if _is_test_script(path):
            if path.suffix == ".js":
                test_js_files += 1
                test_js_loc += nonblank_loc
            continue
        if path.suffix == ".js":
            production_js_files += 1
            production_js_loc += nonblank_loc
        else:
            production_ts_files += 1
            production_ts_loc += nonblank_loc

    return FrontendMetrics(
        production_js_files=production_js_files,
        production_js_loc=production_js_loc,
        production_ts_files=production_ts_files,
        production_ts_loc=production_ts_loc,
        test_js_files=test_js_files,
        test_js_loc=test_js_loc,
        vue_files=vue_files,
        typed_vue_files=typed_vue_files,
        vue_script_loc=vue_script_loc,
    )


def _git_revision(root: Path) -> str:
    git_binary = shutil.which("git")
    if git_binary is None:
        return "unknown"
    try:
        return subprocess.check_output(  # noqa: S603 - trusted git binary resolved from PATH
            [git_binary, "rev-parse", "--short", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def collect_metrics(root: Path) -> TypeSafetyMetrics:
    root = root.resolve()
    python_paths = [
        path
        for path in (root / "compresso").rglob("*.py")
        if not {"node_modules", ".quasar", "dist", "coverage", "__pycache__"}.intersection(path.parts)
    ]
    return TypeSafetyMetrics(
        revision=_git_revision(root),
        python_production=_collect_python(sorted(python_paths)),
        python_tests=_collect_python(sorted((root / "tests").rglob("*.py"))),
        frontend=_collect_frontend(root / "compresso" / "webserver" / "frontend" / "src"),
    )


def render_json(metrics: TypeSafetyMetrics) -> str:
    return json.dumps(asdict(metrics), indent=2, sort_keys=True)


def render_markdown(metrics: TypeSafetyMetrics) -> str:
    python = metrics.python_production
    frontend = metrics.frontend
    return "\n".join(
        [
            f"Revision: `{metrics.revision}`",
            "",
            "| Metric | Current |",
            "|---|---:|",
            f"| Production Python files | {python.files:,} |",
            f"| Production Python nonblank LOC | {python.nonblank_loc:,} |",
            f"| Fully annotated functions | {python.complete_functions:,} / {python.functions:,} |",
            f"| Incomplete Python function LOC | {python.incomplete_function_loc:,} |",
            f"| Unchecked Python function LOC | {python.unchecked_function_loc:,} |",
            f"| Production frontend JavaScript files | {frontend.production_js_files:,} |",
            f"| Production frontend JavaScript LOC | {frontend.production_js_loc:,} |",
            f"| Production frontend TypeScript files | {frontend.production_ts_files:,} |",
            f"| Typed Vue components | {frontend.typed_vue_files:,} / {frontend.vue_files:,} |",
            f"| Vue script LOC | {frontend.vue_script_loc:,} |",
        ]
    )


def render_program_metrics(metrics: TypeSafetyMetrics) -> str:
    """Render the reproducible structural rows used by the program ledger."""
    python = metrics.python_production
    frontend = metrics.frontend
    return "\n".join(
        [
            "| Metric | Baseline | Current | Target |",
            "|---|---:|---:|---:|",
            f"| Production Python files | 245 | {python.files:,} | All checked |",
            f"| Production Python nonblank LOC | 44,273 | {python.nonblank_loc:,} | All checked |",
            "| Fully annotated Python functions | 137 / 1,707 | "
            f"{python.complete_functions:,} / {python.functions:,} | 100% |",
            f"| Incomplete Python function LOC | 29,894 | {python.incomplete_function_loc:,} | 0 |",
            f"| Unchecked Python function LOC | 28,370 | {python.unchecked_function_loc:,} | 0 |",
            f"| Production frontend JavaScript files | 33 | {frontend.production_js_files:,} | 0 |",
            f"| Production frontend JavaScript LOC | 2,451 | {frontend.production_js_loc:,} | 0 |",
            f"| Production frontend TypeScript files | 0 | {frontend.production_ts_files:,} | All production modules |",
            f"| Typed Vue components | 0 / 88 | {frontend.typed_vue_files:,} / {frontend.vue_files:,} | 100% |",
            f"| Vue script LOC | 12,182 | {frontend.vue_script_loc:,} | All checked |",
        ]
    )


def replace_document_metrics(document: str, metrics: TypeSafetyMetrics) -> str:
    """Replace exactly one generated metrics section without touching prose."""
    if document.count(GENERATED_START) != 1 or document.count(GENERATED_END) != 1:
        raise ValueError("Document must contain exactly one pair of generated metrics markers")
    before, marked, remainder = document.partition(GENERATED_START)
    generated, ended, after = remainder.partition(GENERATED_END)
    if not marked or not ended or GENERATED_END in generated:
        raise ValueError("Document has invalid generated metrics markers")
    return f"{before}{GENERATED_START}\n{render_program_metrics(metrics)}\n{GENERATED_END}{after}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Report or verify Compresso type-safety migration metrics.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    document_mode = parser.add_mutually_exclusive_group()
    document_mode.add_argument("--check-document", type=Path)
    document_mode.add_argument("--write-document", type=Path)
    args = parser.parse_args()
    metrics = collect_metrics(args.root)
    document_path: Path | None = args.check_document or args.write_document
    if document_path is not None:
        current = document_path.read_text(encoding="utf-8")
        expected = replace_document_metrics(current, metrics)
        if args.check_document:
            if current != expected:
                print(f"Generated metrics are stale in {document_path}")  # noqa: T201
                return 1
            print(f"Generated metrics are current in {document_path}")  # noqa: T201
            return 0
        document_path.write_text(expected, encoding="utf-8")
        print(f"Updated generated metrics in {document_path}")  # noqa: T201
        return 0
    print(render_json(metrics) if args.format == "json" else render_markdown(metrics))  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
