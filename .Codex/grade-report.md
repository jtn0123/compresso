# Codebase Grade Report

**Project:** Compresso
**Audited:** 2026-07-11
**Baseline:** promoted `master` candidate `7f0d942f1e9750facdfcde2a0d88c94a0fa10a7b` plus release-recovery hardening `dcc5c0b`
**Stack:** Python 3.13, Tornado, Peewee/SQLite, Vue 3, Quasar/Vite, pytest, Vitest, Playwright, GitHub Actions

## Summary

| ID | Category | Grade | Items |
|----|----------|-------|-------|
| A | Architecture & Design | B | 3 |
| B | Backend Quality | A- | 3 |
| C | Frontend Quality | B- | 3 |
| D | Testing & Reliability | B+ | 4 |
| E | Security | B | 4 |
| F | Dependencies & Tech Currency | A- | 3 |
| G | Performance & Scalability | B | 4 |
| H | Documentation & Onboarding | B+ | 3 |
| I | Developer Experience & Tooling | B+ | 4 |
| **Overall** | | **B+** | **31** |

**Top 5 highest-leverage remaining fixes:** E1, A1, C1, G2, D1

## 2026-07-11 NAS-free implementation update

- **B1 completed:** remote file, history, path, and completion writes now fail
  closed; recoverable cache output is retained until every boundary succeeds.
- **D1 materially advanced:** CI and `verify-local` now run a separate
  real-backend Playwright project. It exposed and fixed the macOS GPU schema 500
  and browser-visible API-token field. Packaged-wheel startup and seeded
  approval/reject/restart journeys remain.
- **D2/G1 metadata gate completed:** generated 10k, 100k, and 500k tiers now
  record wall time, peak Python/RSS memory, SQLite size, indexed lookup latency,
  and deep-page latency. Pull requests run 10k; scheduled CI runs 500k.
- **D3 materially advanced:** a localhost master and worker now validate each
  other through the real API, resume a checksummed transfer after process
  restart, reject stale chunks, finalize idempotently, survive another restart,
  and prove database isolation. Real encode handoff/download interruption and a
  separate M4 remain.
- **All-up evidence:** 3,588 backend unit tests, 21 integration tests, 416
  frontend tests, Ruff, formatting, Mypy, frontend lint/coverage/build, 3 mocked
  Playwright tests, and 3 real-backend Playwright tests pass.

## Evidence boundary

This rerun deliberately excludes NAS and real-media claims. It uses the merged source, live GitHub CI/release state, package and dependency audits, existing automated test results, and static inspection. M4 throughput, NAS I/O behavior, sleep/reconnect recovery, thermal throttling, and the 20 TB acceptance gates remain unproven rather than estimated.

The merged release work fixes the confirmed `v1.13.0` publication race: release candidates are now versioned first, validated by exact SHA, and published only after the Python, frontend, integration, package, Docker, scan, signing, and SBOM gates. The first `1.13.1` publication attempt also exposed a missing tagger identity; `dcc5c0b` adds the regression and an exact-artifact GitHub/GHCR recovery workflow. The next engineering gains available without the NAS are the top five items above.

---

## A — Architecture & Design — B

The durable queue, resumable-transfer, disk-pressure, and file-operation journal layers are a strong foundation. However, destructive filesystem state and Peewee task state still cross separate durability domains in `postprocessor.py` and `task.py`, while critical behavior remains concentrated in very large modules such as `installation_link.py` and `postprocessor.py`. The v1/v2 API trees also retain parallel handler infrastructure.

### A1 — Coordinate filesystem journals and task-state commits

- **Where:** `compresso/libs/postprocessor.py:536-550`, `compresso/libs/postprocessor.py:621-759`, `compresso/libs/file_operation_tracker.py:39-229`, `compresso/libs/task.py:285-349`
- **What's wrong:** File replacement is journaled durably, but task status/path changes commit independently through Peewee. A crash between those boundaries requires recovery code to infer which side won instead of replaying one explicit state machine.
- **Impact:** Major — an unlucky crash can leave the media state and authoritative task state disagreeing even though each subsystem is individually restart-safe.
- **Fix:** Introduce a persisted finalization phase on the task record (`prepared`, `files_committed`, `task_committed`, `complete`). Make startup recovery advance or roll back from that phase and add crash-injection tests at every phase boundary.
- **Effort:** L
- **Grade lift:** B → B+ (creates one auditable recovery protocol across both durability domains)

### A2 — Split the critical orchestration modules by responsibility

- **Where:** `compresso/libs/installation_link.py:1-1470`, `compresso/libs/postprocessor.py:1-1174`, `compresso/webserver/api_v2/pending_api.py:1-987`
- **What's wrong:** Networking, retry policy, persistence, lifecycle transitions, formatting, and orchestration are bundled into modules over 900 lines. Changes to one concern require understanding several unrelated state machines.
- **Impact:** Moderate — broad modules increase regression risk and slow future reliability work.
- **Fix:** Extract installation transport/reconciliation, postprocess file-finalization/history, and pending-query/serialization services behind narrow interfaces. Move tests with each extracted unit before changing behavior.
- **Effort:** L
- **Grade lift:** B → B+ (reduces coupling in the three highest-risk maintenance surfaces)

### A3 — Consolidate API cross-cutting infrastructure

- **Where:** `compresso/webserver/api_v1/base_api_handler.py:1-260`, `compresso/webserver/api_v2/base_api_handler.py:1-330`, `compresso/webserver/api_v1/`, `compresso/webserver/api_v2/`
- **What's wrong:** v1 and v2 maintain parallel handler/error/routing conventions. Security, serialization, and error-policy fixes can land in one API generation without the other.
- **Impact:** Moderate — duplicated infrastructure creates inconsistent behavior and repeated security maintenance.
- **Fix:** Extract shared request security, error envelopes, logging, and response helpers into version-neutral modules; keep only schema and route compatibility in each API version.
- **Effort:** L
- **Grade lift:** B → B+ (removes a persistent cross-cutting duplication source)

---

## B — Backend Quality — A-

The backend now has explicit retry/lease handling, durable transfer primitives, disk-space guards, validation schemas, broad failure-path coverage, and fail-closed remote finalization. Error responses still expose raw exception reasons in several handlers, and task setters perform many independent saves.

### B1 — Make remote finalization fail closed [completed]

- **Where:** `compresso/libs/postprocessor.py:579-598`, `compresso/libs/postprocessor.py:801-877`
- **Result:** `_finalize_remote_task()` now requires durable file preparation, history, path, and completion state before success. Every failure returns false, defers retry, and retains the encoded cache; cleanup happens only after the complete transition.
- **Evidence:** Focused regressions cover file exceptions, false copy results, history failures, destination-history overrides, cache retention, and successful cleanup order.
- **Effort:** M
- **Grade lift:** B+ → A- (closes the clearest remaining fail-open media path)

### B2 — Stop returning raw internal exception text to clients

- **Where:** `compresso/webserver/api_v2/base_api_handler.py:210-271`, `compresso/webserver/api_v2/plugins_api.py:353-435`, `compresso/webserver/api_v2/plugins_api.py:646-768`
- **What's wrong:** Multiple handlers pass `str(exception)` into HTTP reason text, and JSON parsing errors can include the received request body. Internal paths, dependency messages, and operator-provided content can escape through API errors.
- **Impact:** Moderate — clients receive unstable implementation details and potentially sensitive diagnostic content.
- **Fix:** Define stable public error codes/messages, log exception details with a correlation ID, and return only the public envelope. Add response tests asserting that paths, bodies, and exception strings are absent.
- **Effort:** M
- **Grade lift:** B+ → A- (standardizes the remaining weak error boundary)

### B3 — Reduce independent task saves in lifecycle transitions

- **Where:** `compresso/libs/task.py:240-349`, `compresso/libs/postprocessor.py:494-528`, `compresso/libs/postprocessor.py:875-877`
- **What's wrong:** Status, success, path, command log, and defer fields are saved through separate setter calls. Multi-field transitions can be partially visible and generate avoidable SQLite write pressure.
- **Impact:** Moderate — partial transitions complicate recovery and increase lock contention under concurrent workers.
- **Fix:** Add explicit transactional transition methods for defer, finalize, retry, and path replacement. Update all related fields in one Peewee atomic block and test rollback on injected database errors.
- **Effort:** M
- **Grade lift:** B+ → A- (makes lifecycle writes atomic and lowers write amplification)

---

## C — Frontend Quality — B-

The Vue/Quasar UI is useful, visually structured, localized in many paths, and backed by 416 unit tests plus Playwright smoke coverage. Maintainability is held back by several 1,000-1,550-line components, a nearly even split between Composition and Options API components, and repeated direct platform/inline-layout logic that conflicts with the frontend guide. Two repository links are clickable spans rather than semantic controls.

### C1 — Decompose the largest workflow components

- **Where:** `compresso/webserver/frontend/src/components/dashboard/completed/CompletedTasksListDialog.vue:1-1550`, `compresso/webserver/frontend/src/pages/ApprovalQueue.vue:1-1150`, `compresso/webserver/frontend/src/components/dashboard/pending/PendingTasksListDialog.vue:1-1055`, `compresso/webserver/frontend/src/components/preview/VideoCompare.vue:1-1001`
- **What's wrong:** Data fetching, filters, dialogs, tables, formatting, actions, and responsive variants coexist in single components. Small UI changes require touching large stateful surfaces.
- **Impact:** Major — these are core user journeys and their size makes regressions and incomplete refactors more likely.
- **Fix:** Extract composables for data/actions, presentational table/card components, and focused dialog bodies. Keep route/page components as orchestration shells and migrate extracted code to `<script setup>` with targeted tests.
- **Effort:** L
- **Grade lift:** B- → B+ (removes the dominant frontend maintainability risk)

### C2 — Finish the responsive-layout standard migration

- **Where:** `compresso/webserver/frontend/src/pages/SettingsLink.vue:8-99`, `compresso/webserver/frontend/src/pages/SettingsWorkers.vue:10`, `compresso/webserver/frontend/src/pages/ApprovalQueue.vue:401-593`, `compresso/webserver/frontend/src/components/settings/plugins/partials/PluginInstallerManageRepos.vue:1-49`
- **What's wrong:** Components still use `$q.platform.is.mobile`, fixed minimum widths, and inline layout strings despite the project standard requiring Quasar breakpoints, visibility classes, and responsive CSS.
- **Impact:** Moderate — tablet, resized-window, and desktop-touch layouts can select the wrong structure or overflow.
- **Fix:** Replace platform detection with `lt-md`/`gt-sm`, `$q.screen`, or `useMobile`; move fixed layout rules into scoped responsive CSS; add viewport tests at phone, tablet, and desktop widths.
- **Effort:** M
- **Grade lift:** B- → B (makes responsive behavior consistent and testable)

### C3 — Replace clickable text spans with semantic links or buttons

- **Where:** `compresso/webserver/frontend/src/components/settings/plugins/partials/PluginInstallerManageRepos.vue:62-68`, `compresso/webserver/frontend/src/components/settings/plugins/partials/PluginInstallerManageRepos.vue:92-99`
- **What's wrong:** Repository URLs are `<span @click>` elements without keyboard semantics, focus behavior, or link destinations.
- **Impact:** Moderate — keyboard and assistive-technology users cannot reliably activate an important plugin-management action.
- **Fix:** Render sanitized URLs as `<a>` elements with safe `target`/`rel` attributes or use a semantic Quasar button. Add keyboard and accessible-name assertions.
- **Effort:** S
- **Grade lift:** B- → B (closes a concrete accessibility failure)

---

## D — Testing & Reliability — B+

Python reliability evidence is unusually strong: 3,588 unit tests, 21 integration tests, deterministic fault tests/fuzzing, a 75% enforced floor, and cross-platform PR shards. Frontend CI runs Vitest coverage, lint, build, mocked Playwright, and a separate real-backend Playwright project. A two-process boundary drill and synthetic scale workflow now exist; packaged-wheel and real-machine interruption coverage remain incomplete.

### D1 — Add a packaged live-backend Playwright lane [both] [advanced]

- **Where:** `compresso/webserver/frontend/tests/e2e/compresso-smoke.spec.js:1-260`, `compresso/webserver/frontend/playwright.config.js`, `.github/workflows/frontend_lint_and_build.yml:70-85`
- **Result:** A separate real-backend project now boots Compresso with isolated config/cache/media roots and validates readiness, system/settings contracts, token redaction, dashboard websocket frames, and an empty approval queue. It caught and fixed a macOS GPU schema 500 and API-token exposure.
- **Remaining:** Boot the packaged wheel rather than the source tree, seed approval/reject/settings/worker journeys, and add browser-visible restart and migration coverage.
- **Effort:** M
- **Grade lift:** B → B+ (adds the missing product-level release proof without requiring the NAS)

### D2 — Build a reproducible 500,000-entry scanner benchmark [BE] [metadata gate completed]

- **Where:** `tests/unit/test_benchmark.py`, `tests/unit/test_libraryscanner_coverage.py`, `compresso/libs/libraryscanner.py:261-350`, `.Codex/20tb-media-compression-plan.md:58-69`
- **Result:** Generated 10k, 100k, and 500k metadata tiers now record wall time, Python/RSS memory, SQLite size, indexed lookup latency, and deep-page latency against versioned thresholds. Pull requests run 10k, scheduled CI runs 500k, and results are retained as artifacts.
- **Remaining:** Add real directory traversal, file probing, concurrent SQLite contention, and large-queue UI measurements before treating the metadata result as the whole Phase D gate.
- **Effort:** M
- **Grade lift:** B → B+ (turns the main scale claim into repeatable evidence)

### D3 — Add a two-process distributed fault harness [BE] [advanced]

- **Where:** `tests/unit/test_remote_task_manager.py`, `tests/unit/test_restart_recovery.py`, `tests/unit/test_resumable_transfer.py`, `compresso/libs/remote_task_manager.py`, `compresso/libs/installation_link.py`
- **Result:** A localhost master and worker now validate through the real API, resume a checksummed upload after worker restart, reject a stale chunk, finalize one task idempotently, survive another restart, and prove database isolation.
- **Remaining:** Interrupt real encode handoff and result download, verify lease expiry/reconciliation and bounded cleanup, then repeat across the master/M4 machine boundary.
- **Effort:** L
- **Grade lift:** B → B+ (bridges unit reliability work to the eventual real-machine canary)

### D4 — Raise frontend coverage in measured steps [FE]

- **Where:** `compresso/webserver/frontend/vitest.config.js:11-20`, `compresso/webserver/frontend/src/components/`, `compresso/webserver/frontend/src/pages/`
- **What's wrong:** CI permits 30% lines/statements, 20% functions, and 20% branches. The most stateful dialogs and settings flows have little direct component coverage relative to their size.
- **Impact:** Moderate — frontend refactors can regress error/loading/action branches while the coverage gate remains green.
- **Fix:** Add tests around the C1 extraction seams and ratchet thresholds after each batch, targeting at least 50% lines/statements and 40% functions/branches before the next broad UI refactor.
- **Effort:** L
- **Grade lift:** B → B+ (makes the frontend gate commensurate with backend reliability)

---

## E — Security — B

The project has rate limiting, schema validation, SSRF guards, CSRF/token support, security headers, dependency audits, CodeQL, SonarCloud, Trivy, signed images, and SBOMs. Its default remains a trusted-LAN application rather than a hardened multi-user service: API auth and CSRF are off, reads remain unauthenticated when enabled, plugins execute installation/build code in-process, CSP permits eval/inline code, and many Actions use mutable tags.

### E1 — Make the network trust boundary explicit and safer by default

- **Where:** `compresso/config.py:149-156`, `compresso/webserver/api_v2/base_api_handler.py:53-73`, `compresso/webserver/api_v2/base_api_handler.py:180-198`, `README.md:18-31`
- **What's wrong:** `api_auth_enabled` and `csrf_protection_enabled` default to false, read-style POST routes bypass mutation protection, and quick start binds a web service without an adjacent trusted-LAN warning.
- **Impact:** Major — a mistaken port exposure can reveal library/task data and permit state changes without a meaningful authentication boundary.
- **Fix:** Default Docker/source installs to loopback or require an explicit trusted-LAN opt-in, generate a first-run token, protect reads when auth is enabled, and show the exposure mode prominently in onboarding/readiness. Preserve an explicit compatibility switch for existing trusted LAN installs.
- **Effort:** M
- **Grade lift:** B → B+ (reduces the largest operator-dependent security risk)

### E2 — Isolate third-party plugin installation and execution

- **Where:** `compresso/libs/plugins.py:505-575`, `compresso/libs/unplugins/executor.py:400-575`, `docs/FORK_DEPLOYMENT.md:109-126`
- **What's wrong:** Plugins may run pip/npm installs, builds, and Python plugin code with the Compresso process's filesystem and network privileges. Documentation warns operators, but there is no technical sandbox.
- **Impact:** Major — a compromised or malicious plugin can read configuration, modify media, or execute arbitrary host commands.
- **Fix:** Run plugin build/execution in a restricted subprocess/container profile with an explicit capability manifest, read-only media by default, bounded network access, and operator confirmation for elevated permissions.
- **Effort:** L
- **Grade lift:** B → A- (turns a documented trust assumption into enforced isolation)

### E3 — Remove `unsafe-eval` and reduce inline CSP allowances

- **Where:** `compresso/webserver/security_headers.py:47-57`, `compresso/webserver/frontend/quasar.config.cjs`, `compresso/webserver/frontend/src/`
- **What's wrong:** The production CSP permits `script-src 'unsafe-inline' 'unsafe-eval'` and inline styles. That materially weakens CSP as an XSS containment layer.
- **Impact:** Moderate — a future injection bug has fewer browser-enforced barriers.
- **Fix:** Inspect the production bundle for eval/inline requirements, select a CSP-compatible Vue build, move inline scripts/styles to hashed or nonce-backed assets, and add browser assertions for the final policy.
- **Effort:** M
- **Grade lift:** B → B+ (restores CSP's intended defense-in-depth value)

### E4 — Pin all third-party GitHub Actions by commit SHA

- **Where:** `.github/workflows/python_lint_and_run_unit_tests.yml:34-201`, `.github/workflows/frontend_lint_and_build.yml:31-85`, `.github/workflows/integration_test_and_build_all_packages_ci.yml:49-123`, `.github/workflows/issues-stale.yml:18-51`
- **What's wrong:** Most actions use mutable major/version tags while only selected Docker/signing/publishing actions are pinned to immutable SHAs.
- **Impact:** Moderate — a compromised or unexpectedly changed action tag can alter trusted CI and release execution.
- **Fix:** Pin every external action to a reviewed commit SHA, retain version comments, and let Dependabot update the pins through review.
- **Effort:** M
- **Grade lift:** B → B+ (closes a broad release supply-chain gap)

---

## F — Dependencies & Tech Currency — A-

Python runtime/dev locks, frontend npm, and release-tool npm are reproducible; live `pip-audit` and `npm audit` checks found no known vulnerabilities. The frontend has several safe patch/minor updates and a few major migrations to plan, while Dependabot currently covers only root pip, Actions, and Docker. One declared BBCode parser is unused.

### F1 — Add Dependabot coverage for every npm lock

- **Where:** `.github/dependabot.yml:1-35`, `compresso/webserver/frontend/package-lock.json`, `.github/release/package-lock.json`, `compresso/webserver/package-lock.json`
- **What's wrong:** Dependabot has no npm entries, so three JavaScript lockfiles rely on manual discovery even though CI audits only some of them.
- **Impact:** Moderate — security and compatibility updates can age silently between manual audits.
- **Fix:** Add separate weekly npm entries for the frontend, release tooling, and webserver directories with grouped patch/minor updates and conservative PR limits.
- **Effort:** S
- **Grade lift:** A- → A (completes automated dependency coverage)

### F2 — Land safe frontend updates and isolate major migrations

- **Where:** `compresso/webserver/frontend/package.json:20-63`, `compresso/webserver/frontend/package-lock.json`
- **What's wrong:** Live registry comparison shows multiple available patch/minor updates and major gaps for Quasar build tooling, router, ESLint, and selected parsers. Mixing these into one upgrade would make regressions hard to attribute.
- **Impact:** Moderate — delayed majors increase future migration cost, while stale patch/minor releases miss fixes.
- **Fix:** First batch compatible patch/minor updates under the full frontend gate. Create separate migration briefs and branches for Quasar 3/router 5/ESLint 10, each with build, unit, Playwright, and browser-support evidence.
- **Effort:** M
- **Grade lift:** A- → A (keeps the supported stack current without risky upgrade bundling)

### F3 — Remove the unused BBCode parser dependency

- **Where:** `compresso/webserver/frontend/package.json:20-38`, `compresso/webserver/frontend/src/js/markupParser.js:1-6`
- **What's wrong:** `js-bbcode-parser` is declared but source uses `xbbcode-parser`; no import or runtime reference uses the former package.
- **Impact:** Minor — the unused package adds install and supply-chain surface with no product value.
- **Fix:** Remove `js-bbcode-parser`, regenerate the lockfile, and run markup parser tests plus the production build.
- **Effort:** S
- **Grade lift:** A- → A (removes verified dependency clutter)

---

## G — Performance & Scalability — B

The code bounds scan queues, worker counts, transfer chunks, retries, and disk pressure, and it records worker metrics. The generated scanner-metadata/SQLite path now has 10k, 100k, and 500k measurements plus versioned thresholds and scheduled artifacts. NAS traversal, probing, concurrent worker contention, and UI scale remain unmeasured. Manifest creation/verification still materializes full lists, and scheduler decisions do not use observed throughput.

### G1 — Prove and optimize the 500,000-entry scan path [metadata gate completed]

- **Where:** `compresso/libs/libraryscanner.py:261-350`, `compresso/config.py:62`, `compresso/config.py:110`, `.Codex/20tb-media-compression-plan.md:58-69`
- **Result:** The metadata-only 500,000-entry tier completed in 3.775 seconds with 4.00 MB RSS growth, an 81.56 MB SQLite queue, 0.0197 ms lookup p95, and 14.4042 ms deep-page p95 on the local arm64 baseline. The generator, method, machine class, limitations, thresholds, scheduled workflow, and artifact retention are versioned under `docs/performance/`.
- **Remaining boundary:** Repeat on CI over time, then add NAS traversal, file probing, concurrent contention, and UI-scale measurements before treating this as the whole Phase D acceptance gate.
- **Effort:** M
- **Grade lift:** B- → B (replaces the largest unsupported scale claim with evidence)

### G2 — Stream media manifests and verification reports

- **Where:** `compresso/libs/media_manifest.py:50-63`, `compresso/libs/media_manifest.py:125-156`, `compresso/libs/media_manifest.py:159-235`
- **What's wrong:** `_media_files()` builds all paths, `create_manifest()` builds all file records, `verify_manifest()` loads the whole JSON document, and both retain all results before writing.
- **Impact:** Major — large inventories consume memory proportional to the entire library and lose more progress if interrupted.
- **Fix:** Add a versioned JSONL/SQLite manifest format with incremental fsync/checkpoints, streaming verification, resumable offsets, and a compact aggregate summary. Keep v1 JSON import compatibility.
- **Effort:** M
- **Grade lift:** B- → B+ (bounds memory and makes long inventory jobs resumable)

### G3 — Feed capability and throughput telemetry into routing

- **Where:** `compresso/libs/foreman.py:723-790`, `compresso/libs/worker_group.py:156-225`, `compresso/libs/installation_link.py`
- **What's wrong:** Worker metrics are emitted, but assignment primarily checks local/remote availability and static worker grouping. It does not rank eligible workers by encoder capability, queue depth, recent throughput, transfer cost, or thermal state.
- **Impact:** Moderate — the master and M4 can be used inefficiently even when both are healthy.
- **Fix:** Persist rolling per-capability throughput/latency, expose remote queue/capability state, and rank only compatible workers using a simple documented score. Add deterministic scheduler tests before enabling adaptive routing.
- **Effort:** L
- **Grade lift:** B- → B (turns existing telemetry into useful scheduling decisions)

### G4 — Define SQLite contention metrics and release thresholds

- **Where:** `compresso/libs/db_migrate.py:120-131`, `compresso/libs/task.py:285-349`, `compresso/libs/taskqueue.py:1-180`, `README.md:147-148`
- **What's wrong:** WAL/busy-timeout tuning and operator advice exist, but CI and readiness do not track write latency, lock retries, queue delay, or database size under load.
- **Impact:** Moderate — growing contention can degrade scheduling gradually without a clear failure signal.
- **Fix:** Instrument transaction latency/lock retries, expose them in readiness/metrics, and set warning/fail thresholds from the synthetic scan and two-process harness.
- **Effort:** M
- **Grade lift:** B- → B (makes the SQLite operating envelope observable)

---

## H — Documentation & Onboarding — B+

Architecture, deployment, security supply chain, development, release recovery, and operator guardrails are documented well. The corrective release sequence now matches the workflow. The most important 20 TB plan is still hidden under `.Codex`, the README quick start does not put the trusted-LAN warning beside the exposed port, and license prose contradicts the repository's GPL-3.0-only declaration.

### H1 — Publish the 20 TB runbook in operator documentation

- **Where:** `.Codex/20tb-media-compression-plan.md:1-177`, `.Codex/20tb-deep-reliability-audit.md:1-75`, `docs/FORK_DEPLOYMENT.md:66-128`, `README.md:117-133`
- **What's wrong:** The authoritative master-only scan rule, separate-config rule, canary sequence, interruption drills, and scale gates live primarily in an internal `.Codex` directory.
- **Impact:** Major — an operator can follow public deployment docs without seeing the safeguards that define safe large-library use.
- **Fix:** Move the operational plan to `docs/LARGE_LIBRARY_RUNBOOK.md`, condense the audit evidence into an appendix, and link it from README, deployment, and roadmap documents.
- **Effort:** S
- **Grade lift:** B+ → A- (puts the critical safety contract in the supported documentation path)

### H2 — Resolve the license contradiction

- **Where:** `README.md:150-167`, `LICENSE:1-20`, `setup.py:230`, copyright headers across `compresso/`
- **What's wrong:** The repository declares GPL-3.0-only but README and source headers include MIT-style permission language and “All Rights Reserved.” The effective licensing message is internally inconsistent.
- **Impact:** Moderate — contributors and redistributors cannot confidently determine their obligations.
- **Fix:** Have the copyright holder select the intended license, then align LICENSE, package metadata, README, headers, and third-party notices in one reviewed change.
- **Effort:** M
- **Grade lift:** B+ → A- (removes the largest onboarding/legal ambiguity)

### H3 — Put the trusted-LAN warning beside Quick Start

- **Where:** `README.md:18-31`, `README.md:117-133`, `docs/FORK_DEPLOYMENT.md:45-55`
- **What's wrong:** The Docker command exposes port 8888 before the README explains that Compresso is not a hardened public multi-user service.
- **Impact:** Moderate — operators may expose the service based on the shortest documented path.
- **Fix:** Add a concise warning immediately above/below Quick Start, show a loopback-bound example, and link directly to the network exposure model.
- **Effort:** S
- **Grade lift:** B+ → A- (makes the default onboarding path communicate the actual trust model)

---

## I — Developer Experience & Tooling — B+

The merged release pipeline is now exact-SHA gated, locked, regression-tested, and artifact-verifying, which is a large improvement from the previous C+ release-engineering grade. Local and CI tooling are broad and the PR matrix is strong. Remaining friction comes from publication recovery after the tag is pushed, duplicate master/release validation, incomplete local parity, and tracked IDE state.

### I1 — Extend release recovery to optional external registries

- **Where:** `.github/workflows/release.yml:182-255`, `.github/workflows/recover_release.yml:1-180`, `docs/GENERATING_MASTER_RELEASE.md:68-76`
- **What's wrong:** Recovery now re-downloads and revalidates the exact GitHub artifacts, verifies/creates the tag and draft release, and idempotently republishes GHCR. Optional PyPI and Docker Hub recovery remain disabled/manual, and registry failure points are covered by contracts rather than an end-to-end failure drill.
- **Impact:** Moderate — repositories that enable the optional registries can still need careful operator intervention after a partial external publish.
- **Fix:** Add explicit recovery inputs for PyPI/Docker Hub, verify existing immutable package/image identities before skipping, reject mismatches, and exercise failures after tag, PyPI, GHCR, Docker Hub, and release publication in a sandbox repository.
- **Effort:** M
- **Grade lift:** B+ → A- (completes idempotent recovery across every supported registry)

### I2 — Remove duplicate validation on release-bound master pushes

- **Where:** `.github/workflows/release.yml:3-16`, `.github/workflows/python_lint_and_run_unit_tests.yml:3-10`, `.github/workflows/frontend_lint_and_build.yml:3-10`, `.github/workflows/integration_test_and_build_all_packages_ci.yml:3-9`
- **What's wrong:** A merge to master starts direct Python, frontend, and package workflows while the release workflow repeats their gates against the candidate SHA. This consumes runners and produces duplicate Sonar/coverage/status noise.
- **Impact:** Moderate — release feedback is slower and harder to interpret, with avoidable CI cost and queue contention.
- **Fix:** Keep PR validation broad, make master publication validation owned by `release.yml`, and retain a clearly named scheduled/manual non-publishing package lane. Add workflow contract tests preventing duplicate publish-bound triggers.
- **Effort:** M
- **Grade lift:** B+ → A- (simplifies the release signal and shortens the critical path)

### I3 — Bring `verify-local.sh` to canonical CI parity

- **Where:** `scripts/verify-local.sh:22-79`, `.github/workflows/python_lint_and_run_unit_tests.yml:45-76`, `.github/workflows/integration_test_and_build_all_packages_ci.yml:43-127`, `.github/release/package.json`
- **What's wrong:** The local script runs unit/frontend/browser checks but omits Ruff, format, mypy, dev-lock audit, integration tests, release-tool tests, workflow lint, and artifact-integrity verification.
- **Impact:** Moderate — developers can receive “Local verification complete” and still fail canonical CI/release gates.
- **Fix:** Add fast/full modes, run all static checks in fast mode, and include integration/package/release/actionlint checks in full mode. Print an explicit skipped-gate summary when tools such as Docker are unavailable.
- **Effort:** M
- **Grade lift:** B+ → A- (makes local success a trustworthy predictor of CI)

### I4 — Stop tracking personal IDE state

- **Where:** `.idea/`, `.idea/dataSources.local.xml`, `.idea/runConfigurations/`
- **What's wrong:** Repository history includes user-specific JetBrains datasource, dictionary, module, and run-configuration state.
- **Impact:** Minor — personal environment drift creates noisy diffs and accidental local metadata sharing.
- **Fix:** Keep only intentionally shared run configurations if the team needs them, remove local datasource/dictionary/module files, and expand `.gitignore` accordingly.
- **Effort:** S
- **Grade lift:** B+ → A- (removes routine repository noise)

---

## Remaining NAS-free execution order

1. **E1** — safer network/auth defaults and onboarding.
2. **A1** — coordinated filesystem/task finalization phases.
3. **G2** — streaming/resumable manifests.
4. Finish **D1** with packaged-wheel and restart/migration browser journeys.
5. Finish **D3** with real encode-handoff/download interruption.
6. **I1** — optional PyPI/Docker Hub recovery and sandbox failure drills.
7. Then take the resulting build to the NAS/M4 canary and collect the evidence this audit deliberately does not invent.
