# Type-Safety Program

This file is the single source of truth for Compresso's production type-safety migration.
Implementation PRs, CI runs, and issues may link here, but must not maintain competing status
checklists or metrics.

| Field | Value |
|---|---|
| Status | Complete |
| Baseline | `f3f566a8` (`v1.17.0`) |
| Started | 2026-07-20 |
| Last verified | 2026-07-21 |
| Target | Strict production Python and direct production frontend TypeScript |
| Tests | Legacy tests may remain untyped; shared helpers and new or touched tests are typed |

## Completion Contract

- [x] `mypy --strict compresso` completes with zero errors.
- [x] Every production Python function is fully annotated and unchecked production function LOC is zero.
- [x] `vue-tsc --noEmit` completes with zero errors.
- [x] Every production Vue script uses TypeScript and no production `.js` remains under `frontend/src`.
- [x] The committed OpenAPI document and generated TypeScript declarations are current.
- [x] No blanket type-checker suppression or production `Any` annotation remains.
- [x] Python, frontend, integration, packaging, release, audit, Google Chrome, mobile Chrome, WebKit, and packaged live-backend gates pass.

## Current Metrics

Run `python3.13 scripts/type_safety_metrics.py --format markdown` to reproduce the structural metrics.
The reporter is read-only; update this table in the same PR that changes a work item.

| Metric | Baseline | Current | Target |
|---|---:|---:|---:|
| Production Python files | 245 | 249 | All checked |
| Production Python nonblank LOC | 44,273 | 47,683 | All checked |
| Fully annotated Python functions | 137 / 1,707 | 1,869 / 1,869 | 100% |
| Incomplete Python function LOC | 29,894 | 0 | 0 |
| Unchecked Python function LOC | 28,370 | 0 | 0 |
| Normal mypy errors | 0 | 0 | 0 |
| `--check-untyped-defs` errors | 593 in 68 files | 0 in 0 files | 0 |
| Strict mypy errors | 4,944 in 145 files | 0 in 0 files | 0 |
| Production frontend JavaScript files | 33 | 0 | 0 |
| Production frontend JavaScript LOC | 2,451 | 0 | 0 |
| Production frontend TypeScript files | 0 | 45 | All production modules |
| Typed Vue components | 0 / 88 | 88 / 88 | 100% |
| Vue script LOC | 12,182 | 12,805 | All checked |

## Work Ledger

The first non-complete item is the next default action. A work item becomes complete only when its
required gates and evidence are recorded here.

| ID | Deliverable | Status | Required evidence | PR / commit |
|---|---|---|---|---|
| TS-00 | Ledger, reproducible metrics, and roadmap pointer | Complete | Focused unit tests, Ruff, metrics output | — |
| TS-10 | OpenAPI output-path support, complete schema generation, generated REST declarations, drift gate | Complete | Schema tests, generation check, frontend type generation | — |
| TS-20 | Direct strict TypeScript conversion of all production frontend code | Complete | `vue-tsc`, lint, coverage, build, Chrome, WebKit, and live-backend evidence | — |
| PY-10 | Strict foundations: configuration, common/file helpers, requests, system/GPU, FFmpeg | Complete | Strict mypy on migrated modules and focused unit tests | — |
| PY-20 | Strict task/media lifecycle: models, metadata, queues, workers, links, post-processing | Complete | Strict mypy and lifecycle regression suites | — |
| PY-30 | Strict service/web boundaries: helpers, APIs, WebSocket, proxy/auth, plugins, migrations | Complete | Strict mypy, API suites, packaged live backend, and clean wheel | — |
| TS-90 | Global strict ratchet, exception cleanup, and final verification | Complete | All completion-contract gates | — |

## Verification Evidence

| ID | Evidence recorded 2026-07-20 |
|---|---|
| TS-00 | `pytest tests/unit/test_type_safety_metrics.py -q` (2 passed); focused Ruff check and format check; reporter ignores installed frontend dependencies |
| TS-10 | OpenAPI generator reports zero undocumented routes; schema and contract tests (24 passed); backend `--check`, frontend `contract:check`, Prettier, and ESLint pass; drift gates added to local verification and CI |
| TS-20 | Zero production JS; all 88 Vue scripts typed; ESLint, `vue-tsc`, production-only type check, contract drift, 481 Vitest tests, coverage thresholds (26.70% lines, 19.57% functions, 21.31% branches, 26.74% statements), and Quasar production build pass |
| PY-10 | Common/config/logging/request/system/GPU/file/FFprobe/FFmpeg/migrations strict; more than 900 focused assertions passed; fixed invalid float seek offsets, boolean string parsing, malformed FFmpeg listing handling, and subtitle fallback crash |
| PY-20 | Models, metadata, queues, workers, scanner/checkpoint, manifests, analysis, scheduler, links, post-processing, monitoring, and lifecycle services strict; focused suites passed, including 127 foreman, 134 file/scanner, 56 manifest, 81 analysis, 85 health, and 257 support assertions; fixed remote-upload cleanup, nullable cache paths, malformed worker slots, FFprobe boundary validation, and scheduled history cleanup treating dictionary rows as model objects |
| PY-30 | All 246 mypy source files pass `mypy --strict`; the complete unit suite passes (4,031 tests), integration passes (24), release contracts pass (11), and the packaged live backend passes (3). Fixed inherited v1 dispatch awaiting its synchronous router, typed write-result handling, malformed WebSocket payloads, optional-watchdog wheel imports, service registration argument misuse, duplicate queue initialization, and stoppable resource logging |
| TS-90 | `verify-local.sh full` passed under an isolated Node 24.11.1 runtime with only Playwright skipped: action pins, licenses, locks, both pip audits, Ruff/format, strict mypy, OpenAPI, 4,031 unit tests, 481 frontend tests plus coverage, build, actionlint, 24 integration tests, 11 release tests, 3 release-tool tests, and clean-wheel inspection. Separate Playwright verification uses installed Google Chrome as the primary desktop, mobile, and packaged live-backend browser plus WebKit for Safari coverage: mocked browser tests 9 passed and packaged live-backend tests 3 passed. `npm audit --omit=dev` reports zero production vulnerabilities |

## Defects Prevented or Fixed

The migration was kept behavior-preserving except where stricter boundary checks exposed a concrete defect.

- Remote uploads now clean up only after a remote identifier exists; nullable task cache paths are rejected before use.
- Malformed worker slots/configuration, FFprobe JSON/numeric/path data, API JSON, dynamic routes, and WebSocket messages fail safely instead of reaching typed internals.
- Session registration no longer passes an installation UUID into a boolean `force` parameter, and service startup no longer initializes `TaskQueue` twice.
- Peewee writes distinguish required integer row counts from intentionally ignored results, preventing mocks or driver changes from silently becoming truthy control-flow values.
- Resource logging uses a real stoppable thread, and optional watchdog types no longer crash an installed wheel when watchdog is absent.
- The OpenAPI schema now expands nested response shapes and generated frontend declarations are checked for drift.
- Bundled plugin identifiers and settings filenames are allowlisted and confined to their configured roots, preventing malformed metadata or symlinks from escaping the plugin directory or forging log lines.
- Worker metric timing no longer accepts and immediately overwrites a caller-supplied interval; the interval now has one clear owner based on current worker activity.
- A post-review fix pass (2026-07-21) repaired regressions the migration itself introduced: the library settings page rejecting the real `settings/read` payload, plugin-settings imports saving under the wrong plugin id, websocket streams losing their 10-row limit to stringly params, worker start times and exception tracebacks disappearing, and the tightened `settings/library/write` schema rejecting supported partial updates. Boundary narrowing now lives in `compresso/libs/narrowing.py`.

## Decisions

| Decision | Locked choice | Reason |
|---|---|---|
| Tracking | This committed file | Keeps status, evidence, exceptions, and decisions together |
| Python scope | All production code under `compresso/` | Test typing is valuable but not a completion dependency |
| Frontend scope | Direct TypeScript conversion | Avoids a prolonged mixed-language production tree |
| Vue migration | Preserve Options and Composition API structure | Type safety is not an architecture rewrite |
| REST contracts | Generate from the backend OpenAPI 3 schema | Prevents manually maintained request/response drift |
| WebSocket/browser contracts | Hand-written discriminated unions with runtime narrowing | These inputs are not represented by the REST schema |
| Runtime validation | Preserve Marshmallow and explicit boundary guards | Static types do not validate untrusted runtime data |
| Browser test matrix | Installed Google Chrome + WebKit; Firefox smoke projects removed from the local Playwright config and CI | The migration validated against branded Chrome (matching the primary user base) after reproducible local Firefox launch failures; the full Linux CI parity gate retains its own coverage. Revisit if Gecko-specific regressions surface |
| Boundary narrowing helpers | Single `compresso/libs/narrowing.py` module with explicit `strict_*` vs `coerce_*` families | Divergent per-module private helpers caused real regressions (stringly websocket stream params silently defaulting); one module makes the chosen semantics visible at each call site |

## Exception Ledger

No production `Any` annotation, `type: ignore`, global missing-import suppression, or skipped-import
configuration remains. Small checked adapters and local stubs describe third-party libraries at their
boundaries; they do not suppress checking. If a future exception is necessary, add its exact location,
checker code, boundary validation, and removal condition here.

| Location | Exception | Boundary protection | Removal condition |
|---|---|---|---|
| None approved | — | — | — |

## Update and Resume Protocol

1. Refresh `origin/master` and confirm the branch base before starting a work item.
2. Run the metrics reporter plus the relevant type checker and tests.
3. Work only on the first in-progress or not-started ledger item unless a dependency is documented.
4. Update the current metrics, work status, exceptions, and exact verification evidence in this file.
5. Merge the implementation and ledger update together; then record the merged PR and commit.
