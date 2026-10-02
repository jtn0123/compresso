# Codebase Grade Report

**Project:** Compresso
**Audited:** 2026-07-10
**Revision:** `master` at `a034f4f806c67fabd941288ca7686c76b758ae77` (matches `origin/master`)
**Stack:** Python 3.13, Tornado, Peewee/SQLite, Vue 3, Quasar/Vite, Vitest, and Playwright

## Summary

| ID | Category | Grade | Items |
|----|----------|-------|-------|
| A | Architecture & Design | B− | 3 |
| B | Backend Quality | B | 4 |
| C | Frontend Quality | B− | 4 |
| D | Testing & Reliability | B+ | 4 |
| E | Security | C+ | 5 |
| F | Dependencies & Tech Currency | B+ | 2 |
| G | Performance & Scalability | B− | 4 |
| H | Documentation & Onboarding | B | 4 |
| I | Developer Experience & Tooling | B+ | 4 |
| **Overall** | | **B−** | **34** |

**Top 5 highest-leverage fixes:** E1, E2, B1, D1, G1

## Validation Snapshot

- The baseline audit ran `bash scripts/verify-local.sh` successfully with `PYTHON_BIN=/opt/homebrew/bin/python3.13`.
- Current Python follow-up: 3,434 passed and 8 skipped in the full unit suite; the latest approval/proxy/API-focused suite also passed 32/32 after the full run began.
- Frontend: 27 test files and 420 tests passed; ESLint, Prettier, coverage gate, and production build passed.
- Frontend coverage: 35.93% lines, 25.12% functions, and 25.55% branches.
- Playwright: 3 mocked Chromium tests and 3 live-backend Chromium tests passed.
- Ruff lint/format, mypy (219 source files), workflow lint, and generated-diff checks passed.
- Runtime and development Python lockfile audits found no known vulnerabilities; full npm audit found none.
- Docker/Trivy execution was not rerun locally for this audit.

## Testing Follow-up — 2026-07-10

This implementation completed the first testing batch without replacing the fast mocked browser lane:

- **B1 completed:** approval and rejection now validate that every requested task exists in `awaiting_approval`, use conditional state updates, reject mixed or stale batches with HTTP 409, and validate before filesystem cleanup.
- **D1 completed:** the Python coverage-summary job now runs on pull requests as well as pushes.
- **D2 HTTP boundary completed:** Tornado tests cover proxied auth, CSRF, rate limiting, and valid-token routing; frontend tests cover same-origin CSRF attachment and prevention of header leakage to external origins. WebSocket authentication and a secure operator-session flow remain open under E2/E4.
- **D3 phase 1 completed:** a live Playwright lane starts a disposable real Python backend and database, proxies the built SPA to it, verifies readiness/system/settings contracts, loads the dashboard, and loads an empty approval queue. Sample-media task creation through history remains a later expansion.
- **E1 HTTP portion completed:** `ProxyHandler` now uses the same authorization, CSRF, rate-limit, and security-header preparation as local API handlers. The separate remote WebSocket handshake still needs the E4 authorization design.
- **Additional regressions fixed:** live testing found and now covers the macOS GPU schema mismatch that made `/system/status` return 500; `/settings/read` no longer returns `api_auth_token`.

The grades below remain the audit baseline so IDs stay stable; rerun the grade after the remaining E2/E4 security design is implemented.

---

## A — Architecture & Design — B−

The repository has a recognizable service/API/frontend split and now documents the primary runtime flow in `docs/ARCHITECTURE.md:1-35`. The core orchestration boundaries remain concentrated, however: `PostProcessor` owns the destructive media lifecycle in `compresso/libs/postprocessor.py:65-1021`, `Links` combines remote state, networking, synchronization, and task transfer in `compresso/libs/installation_link.py:49-1279`, and web/runtime code still resolves shared services through singletons such as `Config`, `CompressoDataQueues`, and `CompressoRunningThreads` (`compresso/webserver/websocket.py:105-114`). These are working boundaries, but not yet easy-to-isolate reference architecture.

#### A1 — Split the destructive post-processing lifecycle into explicit stages
- **Where:** `compresso/libs/postprocessor.py:65-230`, `compresso/libs/postprocessor.py:274-517`, `compresso/libs/postprocessor.py:526-1021`
- **What's wrong:** One stateful thread owns guardrails, approval staging, replacement policy, local and remote finalization, rollback-aware file moves, cleanup, metadata, history, and notifications. Failures are handled at many different levels, so it is difficult to prove which state is durable after an interruption.
- **Impact:** Major — this is the file-replacement path, where unclear recovery behavior can leave media or task state partially finalized.
- **Fix:** Extract stage objects for validation, approval staging, local finalization, remote finalization, cleanup, and history/notification commit. Give each stage an explicit input/result contract and idempotency tests; keep `PostProcessor.run()` as the state-machine coordinator.
- **Effort:** L
- **Grade lift:** B− → B (creates a testable recovery boundary around the highest-risk workflow)

#### A2 — Decompose the remote-installation singleton
- **Where:** `compresso/libs/installation_link.py:49-217`, `compresso/libs/installation_link.py:230-388`, `compresso/libs/installation_link.py:491-1279`
- **What's wrong:** `Links` is a 1,200-line singleton that owns link health/backoff, config merging, HTTP transport, downloads/uploads, remote worker discovery, task lifecycle calls, and library import. Network behavior and state reconciliation cannot be tested or replaced independently without patching the singleton.
- **Impact:** Moderate — changes to remote linking have a broad blast radius and require more regression testing than the individual behavior warrants.
- **Fix:** Extract `LinkTransport`, `LinkRegistry`, and `RemoteTaskClient` behind constructor-injected interfaces. Preserve `Links` as a compatibility facade while migrating call sites and tests in small slices.
- **Effort:** L
- **Grade lift:** B− → B (removes the largest cross-domain backend object)

#### A3 — Pass a runtime context instead of rediscovering global services
- **Where:** `compresso/service.py:231-282`, `compresso/webserver/websocket.py:105-114`, `compresso/webserver/api_v2/base_api_handler.py:180-185`, `compresso/libs/uiserver.py:159-218`
- **What's wrong:** The root service constructs queues and threads explicitly, but downstream handlers rediscover configuration, queues, running threads, sessions, and link state through singletons. That hides dependency direction and makes request-level tests rely on global resets and patches.
- **Impact:** Moderate — hidden runtime dependencies slow integration testing and make multi-instance or isolated service execution harder.
- **Fix:** Introduce a small immutable `RuntimeContext` containing settings, queues, thread registry, session provider, and link provider. Inject it through Tornado handler initialization and thread constructors while retaining default adapters for existing callers.
- **Effort:** L
- **Grade lift:** B− → B (makes ownership and dependency direction explicit)

---

## B — Backend Quality — B

Backend quality is generally strong: Marshmallow schemas are pervasive, API routes are documented in handler docstrings, SQL aggregates replaced several row-heavy paths, and the suite covers the major helpers. The most serious remaining correctness issue is that approval mutation endpoints accept arbitrary task IDs and then report success without enforcing the approval state (`compresso/webserver/api_v2/approval_api.py:153-244`, `compresso/webserver/helpers/approval.py:387-435`). Pagination and handler error patterns also need one more consolidation pass.

#### B1 — Enforce legal task-state transitions for approval actions — Completed 2026-07-10
- **Where:** `compresso/webserver/api_v2/approval_api.py:153-244`, `compresso/webserver/helpers/approval.py:387-435`, `compresso/libs/task.py:461-470`
- **What's wrong:** Approve performs `UPDATE ... WHERE id IN (...)` without requiring `status='awaiting_approval'`; reject can clean files and delete or requeue any task ID. Both endpoints ignore the affected-row/result value and always return HTTP 200.
- **Impact:** Major — a stale or crafted request can approve, delete, or requeue a task that is pending, running, or already finalized.
- **Fix:** Select and lock/validate all requested rows as `awaiting_approval`, reject mixed-state batches with a conflict response, apply a conditional status update, and return requested/changed/not-found counts. Add tests for pending, in-progress, duplicate, missing, and concurrent state-change cases.
- **Effort:** M
- **Grade lift:** B → B+ (closes the largest business-state correctness hole)

#### B2 — Make rejection cleanup recoverable and result-aware
- **Where:** `compresso/webserver/helpers/approval.py:398-435`, `compresso/libs/task.py:396-429`
- **What's wrong:** Rejection deletes staging/cache directories before the database status/delete operation, while recursive task deletion can stop halfway through a batch. A filesystem or database failure can therefore leave a task row without its files, or a partially deleted batch, while the API still reports success.
- **Impact:** Major — partial failure can strand or destroy work with no clear retry contract.
- **Fix:** Build a per-task rejection plan, mark rows with a transitional state in a database transaction, perform idempotent cleanup, then commit the final pending/deleted state. Return structured per-task failures and add interruption/retry tests.
- **Effort:** M
- **Grade lift:** B → B+ (adds an explicit recovery contract to destructive rejection)

#### B3 — Bound every list endpoint at the schema boundary
- **Where:** `compresso/webserver/api_v2/schema/schemas.py:118-135`, `compresso/webserver/api_v2/schema/approval_schemas.py:28-46`, `compresso/libs/task.py:354-394`, `compresso/webserver/api_v2/schema/history_schemas.py:113-130`
- **What's wrong:** Generic and approval `start`, `length`, `offset`, and `limit` fields have no non-negative or maximum validation. A falsy `length=0` means no SQL limit, so clients can request the entire table; negative and very large values are also accepted by the schema layer.
- **Impact:** Moderate — accidental or hostile requests can cause large response bodies, expensive enrichment, and avoidable memory/CPU use.
- **Fix:** Add shared pagination fields with `Range(min=0)` and a documented maximum page size, make “all rows” an internal-only code path, and return validation errors for invalid bounds. Add contract tests across pending, history, approval, health, plugins, metadata, and compression lists.
- **Effort:** S
- **Grade lift:** B → B+ (standardizes a core API contract and caps work per request)

#### B4 — Finish centralizing API error handling
- **Where:** `compresso/webserver/api_v2/base_api_handler.py:263-301`, `compresso/webserver/api_v2/compression_api.py:110-196`, `compresso/webserver/api_v2/pending_api.py:121-948`, `compresso/webserver/api_v2/plugins_api.py:160-834`
- **What's wrong:** The base handler now has reusable expected/unhandled error methods, but the API package still contains 112 broad exception handlers and many manually repeat log/status/write sequences. Newer approval handlers use the shared methods while older handler families still diverge.
- **Impact:** Moderate — error payloads and logging behavior can differ depending on which endpoint fails, and fixes must be repeated widely.
- **Fix:** Add one route-execution wrapper that maps validation, domain, not-found, conflict, and unexpected exceptions to stable responses. Migrate one handler family at a time and assert the common error contract.
- **Effort:** M
- **Grade lift:** B → B+ (removes a broad consistency and maintenance hotspot)

---

## C — Frontend Quality — B−

The Vue/Quasar frontend has good route-level code splitting, sanitizes all sampled `v-html` paths, uses a shared dialog/button system, and now has meaningful Vitest and Playwright coverage. Maintainability is held back by four components over 1,000 lines, 97 direct `$compresso` references, and a mixed Options/Composition API estate (39 of 85 Vue files still use `export default`). The user experience is coherent, but several large screens still combine transport, polling, filtering, selection, dialogs, and presentation.

#### C1 — Split the four largest workflow components
- **Where:** `compresso/webserver/frontend/src/components/dashboard/completed/CompletedTasksListDialog.vue:1-1550`, `compresso/webserver/frontend/src/pages/ApprovalQueue.vue:1-1150`, `compresso/webserver/frontend/src/components/dashboard/pending/PendingTasksListDialog.vue:1-1055`, `compresso/webserver/frontend/src/components/preview/VideoCompare.vue:1-1001`
- **What's wrong:** Each component combines multiple dialogs, tables, selection state, filters, polling, API calls, keyboard behavior, and styling. Their tests must mount large surfaces to validate small changes.
- **Impact:** Major — these are high-traffic screens where routine changes carry unnecessary regression risk and review cost.
- **Fix:** Extract presentational table/filter/selection components and composables for data loading, bulk actions, preview polling, and media controls. Preserve current route behavior and add focused tests before shrinking each parent to orchestration.
- **Effort:** L
- **Grade lift:** B− → B (removes the frontend’s largest change-risk hotspots)

#### C2 — Create one application API client and request-state layer
- **Where:** `compresso/webserver/frontend/src/boot/axios.js:1-46`, `compresso/webserver/frontend/src/js/compressoGlobals.js:1-263`, `compresso/webserver/frontend/src/js/compressoWebsocket.js:1-484`, direct `$compresso` call sites under `compresso/webserver/frontend/src/`
- **What's wrong:** API URL creation, Axios imports, `$compresso` globals, proxy target state, retries, notifications, and websocket state are spread across components and global utilities. The audit counted 97 direct `$compresso` references.
- **Impact:** Moderate — transport, error, auth, and cancellation behavior cannot be changed consistently in one place.
- **Fix:** Provide a single injected API client with endpoint modules, normalized errors, cancellation, proxy targeting, and request-state composables. Migrate high-traffic pages first, retaining a compatibility wrapper for legacy Options API components.
- **Effort:** L
- **Grade lift:** B− → B (creates a stable frontend/backend boundary)

#### C3 — Complete the Composition API migration when touching legacy views
- **Where:** 39 Vue files containing `export default`, including `compresso/webserver/frontend/src/pages/MainDashboard.vue:1-591`, `compresso/webserver/frontend/src/pages/SettingsLink.vue:1-677`, and `compresso/webserver/frontend/src/pages/SettingsNotifications.vue:1-480`
- **What's wrong:** The codebase maintains two state/lifecycle patterns, and some legacy components combine Options API with newer composables and shared globals. This is allowed by the frontend guide, but the remaining split increases cognitive load and makes shared logic extraction slower.
- **Impact:** Moderate — developers must reason about two component models in the same workflows.
- **Fix:** Adopt a “major edit pays migration cost” rule, extract behavior into tested composables first, then convert the touched view to `<script setup>`. Track remaining legacy views without a big-bang rewrite.
- **Effort:** L
- **Grade lift:** B− → B (reduces frontend pattern fragmentation over time)

#### C4 — Finish localization and accessibility cleanup
- **Where:** `compresso/webserver/frontend/src/components/docs/ApplicationLogsDialog.vue:46-55`, `compresso/webserver/frontend/src/components/settings/plugins/PluginInfoDialog.vue:50-69`, `compresso/webserver/frontend/src/components/charts/EncodingSpeedChart.vue:14`, `compresso/webserver/frontend/src/pages/DataPanels.vue:4`
- **What's wrong:** A small set of labels and accessible names remain hardcoded in English (`Clear`, `Version`, `Changelog`, chart/iframe labels) despite the project rule that user-facing strings use i18n.
- **Impact:** Minor — untranslated and fixed-language accessibility labels create polish and localization gaps.
- **Fix:** Move the remaining labels into `src/language/en.json`, use `t()`/`$t()` for visible and ARIA text, and add a lint/test check for common hardcoded label attributes.
- **Effort:** S
- **Grade lift:** B− → B (closes a visible standards-compliance gap)

---

## D — Testing & Reliability — B+

Testing is a strength: 3,425 Python tests passed, 416 frontend tests passed, cross-platform unit shards run in CI, integration tests use real media, and Playwright covers three important UI flows. The largest reliability issue is the Python 75% coverage gate running only on pushes, not on pull requests (`.github/workflows/python_lint_and_run_unit_tests.yml:123-152`). Frontend coverage is real but still shallow at 35.61% lines and 25.08% branches, and the browser suite mocks the backend.

#### D1 — Enforce the Python coverage floor on pull requests — Completed 2026-07-10
- **Where:** `.github/workflows/python_lint_and_run_unit_tests.yml:100-127`, `.github/workflows/python_lint_and_run_unit_tests.yml:146-152`, `pyproject.toml:18-25`
- **What's wrong:** Each PR shard uses `--cov-fail-under=0`, while the combine-and-enforce job has `if: github.event_name == 'push'`. A PR can reduce coverage below 75% and still pass all PR checks; the failure appears only after merge/push.
- **Impact:** Major — CI can give a green merge signal for a change that violates the repository’s stated coverage policy.
- **Fix:** Run the coverage summary job for pull requests, download only one OS’s shard artifacts, combine them, and enforce `fail_under=75` before merge. Keep the cross-platform execution matrix independent of coverage aggregation.
- **Effort:** S
- **Grade lift:** B+ → A− (makes the existing Python coverage policy a real pre-merge gate)

#### D2 — Add cross-boundary tests for auth, proxy routing, and the shipped client — HTTP boundary completed 2026-07-10
- **Where:** `tests/unit/test_api_auth.py:48-130`, `tests/unit/test_proxy.py:39-96`, `compresso/webserver/frontend/src/boot/axios.js:1-24`, no `ProxyHandler` authorization integration test
- **What's wrong:** Auth tests exercise `BaseApiHandler`, and proxy tests exercise only target resolution. No test sends a protected mutation through `APIRequestRouter`/`ProxyHandler`, and no frontend test proves the security headers required by the backend are attached.
- **Impact:** Major — the current proxy authorization bypass and unusable frontend auth configuration were both able to pass the suite.
- **Fix:** Add Tornado integration tests for local/proxied GET and mutation requests under every auth mode, plus frontend interceptor tests for CSRF and API credentials. Include websocket handshake authorization cases.
- **Effort:** M
- **Grade lift:** B+ → A− (covers the most important missing system boundary)

#### D3 — Add one real backend-connected browser smoke lane — Phase 1 completed 2026-07-10
- **Where:** `compresso/webserver/frontend/tests/e2e/compresso-smoke.spec.js:1-278`, `compresso/webserver/frontend/scripts/serve-e2e.mjs:1-99`, `.github/workflows/frontend_lint_and_build.yml:61-65`
- **What's wrong:** The three Playwright tests mock API responses and cover dashboard/approval behavior only. They verify frontend wiring but cannot catch API schema drift, auth/header mismatches, startup failures, database behavior, or backend 500/429 regressions.
- **Impact:** Major — the full shipped stack still lacks a browser-level release signal.
- **Fix:** Start Compresso with an isolated temporary config/database and sample media, then run a small Playwright journey covering readiness, dashboard, task creation, approval/rejection, history, and one protected-mode mutation. Keep the fast mocked suite as the default frontend job.
- **Effort:** M
- **Grade lift:** B+ → A− (adds the missing end-to-end contract check)

#### D4 — Ratchet frontend coverage around critical workflows
- **Where:** `compresso/webserver/frontend/vitest.config.js:11-20`, 26 frontend test files under `compresso/webserver/frontend/src/`, large unisolated components listed in C1
- **What's wrong:** The gate is 30% lines/statements and 20% functions/branches; current measured coverage is only 35.61% lines, 24.90% functions, and 25.08% branches. Critical settings, remote-link, file-replacement, and large dialog paths remain lightly isolated.
- **Impact:** Moderate — substantial UI behavior can regress while the global threshold remains green.
- **Fix:** Add per-file thresholds for newly extracted composables and critical modules, require coverage on changed files, and raise global floors in documented increments after each batch of tests.
- **Effort:** M
- **Grade lift:** B+ → A− (turns the conservative floor into a meaningful regression ratchet)

---

## E — Security — C+

The repo has strong building blocks: clean dependency audits, CSP/security headers, DOMPurify on sampled HTML paths, WebSocket origin checking, SSRF address guards, upload tests, rate limiting, token comparison via `hmac.compare_digest`, and CSRF primitives. The security feature is not yet a complete boundary. `ProxyHandler` bypasses `BaseApiHandler.prepare()`, the frontend sends neither advertised protection header, the default server binds all interfaces with auth disabled, and authenticated mode intentionally leaves reads and WebSocket streams open.

#### E1 — Apply authorization and rate limiting before proxy routing — HTTP portion completed 2026-07-10
- **Where:** `compresso/webserver/api_request_router.py:58-65`, `compresso/webserver/proxy.py:116-189`, `compresso/webserver/api_v2/base_api_handler.py:106-128`, `compresso/webserver/websocket.py:121-150`
- **What's wrong:** Any request with `X-Compresso-Target-Installation` is routed directly to `ProxyHandler`, which has a no-op `prepare()` and does not run token auth, CSRF checks, security headers, or the API rate limiter. The websocket proxy path similarly resolves and connects to a configured remote without enforcing the local API-auth policy.
- **Impact:** Major — enabling API auth does not protect proxied remote mutations, and the local instance can become an unauthenticated control path to configured remote nodes.
- **Fix:** Move authorization/rate-limit logic into a shared request guard used by both `BaseApiHandler` and `ProxyHandler`; explicitly classify proxied methods as reads or mutations. Require an authorized websocket handshake and add integration tests for local and remote targets.
- **Effort:** M
- **Grade lift:** C+ → B− (closes a direct bypass of the advertised security control)

#### E2 — Make API auth and CSRF usable by the shipped frontend
- **Where:** `compresso/webserver/frontend/src/boot/axios.js:5-24`, `compresso/webserver/api_v2/base_api_handler.py:151-198`, `docs/ARCHITECTURE.md:37-49`
- **What's wrong:** The backend requires `Authorization`/`X-Compresso-Api-Token` and, optionally, `X-Compresso-CSRF-Token`, but the frontend interceptor only attaches the remote-target header. Enabling either protection breaks normal mutating UI actions rather than producing a secured working UI.
- **Impact:** Major — operators must choose between a functioning built-in UI and the advertised application-level protections.
- **Fix:** Design a secure operator session/bootstrap flow, have the Axios client echo the CSRF cookie, attach credentials only to same-origin Compresso requests, and handle 401/403 centrally. Do not persist the long-lived administrator token in localStorage; prefer an HttpOnly session derived from an explicit login/unlock step.
- **Effort:** L
- **Grade lift:** C+ → B− (turns security primitives into a deployable end-to-end control)

#### E3 — Replace the open-by-default network posture with a safe startup policy
- **Where:** `compresso/config.py:72-73`, `compresso/config.py:136-143`, `compresso/libs/uiserver.py:205-215`, `README.md:19-30`
- **What's wrong:** Source defaults use an empty bind address, which Tornado exposes as `0.0.0.0`, while API auth and CSRF are disabled. The documented Docker quick start publishes that unauthenticated service on port 8888.
- **Impact:** Major — a default install is reachable by every host on its attached network and includes destructive queue/settings/media operations.
- **Fix:** Default source installs to loopback. Require Docker to opt into `0.0.0.0` explicitly, emit a high-visibility startup warning when binding non-loopback without auth, and optionally refuse that combination unless an explicit insecure-LAN acknowledgement is configured.
- **Effort:** M
- **Grade lift:** C+ → B− (makes safe deployment the default rather than a documentation warning)

#### E4 — Protect sensitive reads and WebSocket streams when auth is enabled
- **Where:** `compresso/webserver/api_v2/base_api_handler.py:53-73`, `compresso/webserver/api_v2/base_api_handler.py:137-145`, `compresso/webserver/websocket.py:56-93`, `compresso/webserver/frontend/src/components/docs/ApplicationLogsDialog.vue:116-208`
- **What's wrong:** All GET/HEAD requests and allowlisted POST reads bypass token auth, including filesystem browsing/probing, settings reads, metadata, and approval details. The websocket has origin checks but no token/session authorization and can stream system logs, worker data, pending/completed task paths, and system status.
- **Impact:** Major — authenticated mode still exposes sensitive paths, configuration, logs, and operational state to unauthenticated same-network clients.
- **Fix:** Define public readiness/version endpoints separately; require auth for all other API reads and websocket handshakes when auth is enabled. Add scope/role distinctions later only if a real multi-user requirement appears.
- **Effort:** M
- **Grade lift:** C+ → B− (aligns authenticated mode with operator expectations)

#### E5 — Stop returning raw exception text in production API responses
- **Where:** `compresso/webserver/api_v2/base_api_handler.py:286-301`, `compresso/webserver/api_v2/base_api_handler.py:303-340`, repeated handlers such as `compresso/webserver/api_v2/compression_api.py:138-196`
- **What's wrong:** Unexpected exceptions set the HTTP reason to `str(exc)`, which becomes the JSON error text even when traceback serving is disabled. Filesystem, database, command, and dependency errors can disclose paths or internal details.
- **Impact:** Moderate — internal environment details can leak to unauthenticated or low-trust clients.
- **Fix:** Return a stable public error code/message with a correlation ID, log the full exception server-side, and include detailed text/tracebacks only under an explicit developer mode.
- **Effort:** S
- **Grade lift:** C+ → B− (closes a common information-disclosure path)

---

## F — Dependencies & Tech Currency — B+

Python runtime and development dependencies are pinned with hashes and audited clean; the npm lockfile is also clean, and recent commits refreshed Python dependencies. The main gap is operational: Dependabot covers pip, Actions, and Docker but not the vendored frontend. There is also a manageable major-version backlog in the frontend toolchain, though current versions build and test successfully.

#### F1 — Add Dependabot coverage for the vendored npm project
- **Where:** `.github/dependabot.yml:1-30`, `compresso/webserver/frontend/package.json:1-66`, `compresso/webserver/frontend/package-lock.json`
- **What's wrong:** Dependabot has no npm ecosystem entry for `compresso/webserver/frontend`, even though the audited install contains roughly 640 packages. Frontend security and compatibility updates currently depend on manual checks.
- **Impact:** Moderate — important browser/toolchain updates can age unnoticed despite otherwise strong dependency automation.
- **Fix:** Add a weekly npm entry for `/compresso/webserver/frontend`, group safe minor/patch updates, cap open PRs, and keep major upgrades separate with the existing test/build/E2E checks required.
- **Effort:** S
- **Grade lift:** B+ → A− (completes automated monitoring across all package ecosystems)

#### F2 — Plan the remaining frontend major upgrades and parser consolidation
- **Where:** `compresso/webserver/frontend/package.json:19-55`; live `npm outdated` results for `@quasar/app-vite`, `@quasar/extras`, `dotenv`, `eslint`, `js-bbcode-parser`, `vue-router`, and `xbbcode-parser`
- **What's wrong:** The current dependency set is vulnerability-free, but several major versions are behind and two BBCode parser packages are retained. `npm ci` also emits a deprecated `glob@10.5.0` transitive warning.
- **Impact:** Moderate — deferring majors and redundant parsers increases the size and risk of the eventual migration.
- **Fix:** Create separate tested lanes for Quasar app tooling, ESLint 10, Vue Router 5, and parser consolidation. Use `npm explain glob` to identify and upgrade the owner of the deprecated transitive dependency without overriding blindly.
- **Effort:** M
- **Grade lift:** B+ → A− (reduces known upgrade debt while preserving the clean audit state)

---

## G — Performance & Scalability — B−

The repo has meaningful performance work: incremental metadata storage, SQL aggregation for compression/pending estimates, background analysis, route-level frontend splitting, and indexes on many filter columns. The largest remaining bottleneck is library analysis: each run walks the full tree and samples up to roughly 80 MiB from every large media file before it can use cached metadata (`compresso/webserver/helpers/library_analysis.py:160-177`, `compresso/libs/common.py:313-379`). Approval enrichment and overlapping frontend polling also scale linearly with queue size and open views.

#### G1 — Avoid re-fingerprinting every unchanged media file during analysis
- **Where:** `compresso/webserver/helpers/library_analysis.py:160-177`, `compresso/webserver/helpers/library_analysis.py:236-280`, `compresso/libs/common.py:313-379`
- **What's wrong:** Cache lookup computes a content fingerprint first. For files over 100 MiB the sampled algorithm reads ten 8 MiB regions, so even a fully cached rescan performs up to about 80 MiB of I/O per file; probing is then processed serially.
- **Impact:** Major — large media libraries can spend substantial time and disk bandwidth proving unchanged files are unchanged.
- **Fix:** Persist size, mtime/inode, and fingerprint metadata; use the cheap stat tuple as the first cache key and fingerprint only changed/ambiguous files. Process misses with a bounded worker pool and an I/O concurrency setting, then benchmark cold and warm scans on a representative library.
- **Effort:** M
- **Grade lift:** B− → B (turns the incremental cache into a genuinely cheap warm scan)

#### G2 — Move approval filters and summaries fully into persisted SQL data
- **Where:** `compresso/webserver/helpers/approval.py:49-105`, `compresso/webserver/helpers/approval.py:127-160`, `compresso/webserver/helpers/approval.py:188-235`, `compresso/webserver/helpers/approval.py:260-319`
- **What's wrong:** Missing source/staged metadata triggers media probing during list/summary requests, and derived codec/VMAF filters force all matching tasks into Python before pagination. Summary totals also iterate every enriched item.
- **Impact:** Major — large approval queues can make ordinary page loads and filter changes perform repeated filesystem/media work.
- **Fix:** Persist all filter/sort fields at staging time, backfill legacy rows in a background migration, add SQL predicates/aggregates for summary data, and reserve file probing for the single-task detail view.
- **Effort:** M
- **Grade lift:** B− → B (makes approval latency depend on page size rather than queue size)

#### G3 — Consolidate overlapping frontend polling and websocket refreshes
- **Where:** `compresso/webserver/frontend/src/layouts/MainLayout.vue:229-322`, `compresso/webserver/frontend/src/pages/ApprovalQueue.vue:999-1073`, `compresso/webserver/frontend/src/components/dashboard/CompactStatsGrid.vue:208-212`, `compresso/webserver/frontend/src/components/dashboard/HealthCheckPanel.vue:156-161`, `compresso/webserver/frontend/src/components/drawers/DrawerMainNav.vue:329-336`
- **What's wrong:** Layout, drawers, dashboard panels, approval, health, and task dialogs each own intervals while websocket streams already deliver some overlapping state. Multiple mounted surfaces can refresh the same backend independently.
- **Impact:** Moderate — idle clients create avoidable API/database work and increase the chance of rate-limit bursts or stale competing state.
- **Fix:** Add a shared visibility-aware query/cache scheduler, deduplicate endpoint requests, pause polling in background tabs, and let websocket events invalidate cached queries instead of running parallel timers.
- **Effort:** M
- **Grade lift:** B− → B (reduces idle load and centralizes freshness policy)

#### G4 — Add composite indexes for the dominant queue and metadata query shapes
- **Where:** `compresso/libs/unmodels/tasks.py:47-72`, `compresso/libs/task.py:354-387`, `compresso/libs/unmodels/filemetadatapaths.py:40-53`, `compresso/webserver/helpers/library_analysis.py:226-231`
- **What's wrong:** `Tasks` has individual indexes on status, library, type, and priority, but common queries filter status/library and then sort by priority or finish time. Analysis cleanup filters `path_type` without an index, and the current metadata-path composite begins with `file_metadata`, not `path_type`.
- **Impact:** Moderate — SQLite must scan/sort more rows as queues, history, and metadata caches grow.
- **Fix:** Capture `EXPLAIN QUERY PLAN` for pending/approval/history and analysis cleanup, then add only the composite indexes shown to help (for example status/library/priority and path_type/path). Add migration and query-plan regression tests.
- **Effort:** M
- **Grade lift:** B− → B (aligns indexes with real multi-column access patterns)

---

## H — Documentation & Onboarding — B

Documentation is broad and useful: the README has Docker/source quick starts, `docs/ARCHITECTURE.md` explains the new queue/approval/cache design, and the plugin guide is unusually thorough. The main omissions concern the newly added security mode and generated API docs. Licensing text is also contradictory across the GPL metadata/LICENSE and MIT-style headers/README language.

#### H1 — Document an executable secure-deployment configuration
- **Where:** `docs/ARCHITECTURE.md:37-49`, `docs/APPROVAL_API.md:39-55`, `docs/CONFIGURATION.md:1-87`, `compresso/config.py:209-218`
- **What's wrong:** The docs name lowercase auth/CSRF settings but do not show exactly how to set them in `settings.json`, Docker, or a supported environment-variable convention. `CONFIGURATION.md` omits them entirely, and the current frontend limitations are not disclosed.
- **Impact:** Major — operators can read that protection exists without having a reliable, working procedure to enable and verify it.
- **Fix:** After E1-E4, add a secure local/LAN/reverse-proxy matrix with exact config, token generation, frontend login/session behavior, curl checks, websocket behavior, and rollback steps. Document a namespaced uppercase environment interface if one is added.
- **Effort:** M
- **Grade lift:** B → B+ (makes the security model actionable instead of conceptual)

#### H2 — Verify and publish current OpenAPI artifacts in CI
- **Where:** `compresso/libs/uiserver.py:298-318`, `compresso/webserver/api_v2/schema/swagger.py:78-111`, `compresso/webserver/docs/api_schema_v2.yaml`, `compresso/webserver/docs/api_schema_v2.json`
- **What's wrong:** API artifacts are regenerated only in developer mode and have not been committed since March. The checked-in schema does not reflect all newer approval filters/auth behavior, while production Swagger serves the checked-in JSON.
- **Impact:** Moderate — API consumers can receive documentation that disagrees with the running handlers.
- **Fix:** Add a deterministic schema-generation command and CI check that fails on a diff, regenerate both JSON/YAML, and document security requirements per operation. Package only verified artifacts.
- **Effort:** S
- **Grade lift:** B → B+ (keeps the public API contract synchronized automatically)

#### H3 — Reconcile contradictory license statements
- **Where:** `LICENSE:1-20`, `setup.py:9-27`, `setup.py:230`, `setup.cfg:1-4`, `README.md:150-164`, repeated source-file headers under `compresso/`
- **What's wrong:** Package metadata and LICENSE declare GPLv3/GPL-3.0-only, while the README and many source headers reproduce MIT-style permission language alongside “All Rights Reserved.” The project’s actual reuse terms are therefore ambiguous.
- **Impact:** Moderate — contributors and downstream packagers cannot confidently determine the governing license from the repository text.
- **Fix:** Confirm the intended license and upstream obligations, replace contradictory boilerplate with an SPDX identifier/copyright notice, and make README, package metadata, frontend metadata, and LICENSE agree. Obtain maintainer/legal review where ownership is unclear.
- **Effort:** M
- **Grade lift:** B → B+ (removes a material onboarding and distribution ambiguity)

#### H4 — Remove the remaining runtime-version contradictions
- **Where:** `README.md:50-55`, `README.md:66-75`, `setup.cfg:6-9`, `.python-version:1`
- **What's wrong:** The README still says “Python 3.x” even though packaging requires 3.13+, and the generic `.python-version` does not resolve in the current pyenv installation. Later sections correctly require Python 3.13.
- **Impact:** Minor — first-time contributors can select an unsupported interpreter or hit an unexplained pyenv failure.
- **Fix:** State Python 3.13+ consistently, document the supported patch/install command, and ensure the version-manager file matches the chosen workflow.
- **Effort:** S
- **Grade lift:** B → B+ (makes the first setup step deterministic)

---

## I — Developer Experience & Tooling — B+

Developer tooling is strong: CI runs Ruff, formatting, mypy, cross-platform Python tests, frontend coverage/lint/format/build/E2E, integration packaging, and security audits; pre-commit hooks and a local verifier are present. The current machine exposed a real bootstrap problem: `.python-version` points to an unavailable `3.13` pyenv version even though Homebrew Python 3.13.5 is installed. The “parity” script also omits several checks it claims to mirror.

#### I1 — Make the Python version-manager bootstrap deterministic
- **Where:** `.python-version:1`, `docs/DEVELOPING.md:44-67`, `scripts/verify-local.sh:4-20`
- **What's wrong:** Entering the repo makes bare `python` fail with `pyenv: version '3.13' is not installed` on this checkout. The verifier succeeds only when `PYTHON_BIN=/opt/homebrew/bin/python3.13` is supplied explicitly.
- **Impact:** Moderate — ordinary Python commands fail before a contributor reaches the documented setup steps, creating misleading local failures.
- **Fix:** Pin or generate an exact supported pyenv patch version, document `pyenv install`/venv bootstrap, and add a friendly bootstrap check that distinguishes pyenv selection from a missing system Python.
- **Effort:** S
- **Grade lift:** B+ → A− (eliminates the main observed local-environment trap)

#### I2 — Make `verify-local.sh` match its parity claim
- **Where:** `scripts/verify-local.sh:22-79`, `.github/workflows/python_lint_and_run_unit_tests.yml:44-66`, `.github/workflows/frontend_lint_and_build.yml:37-55`
- **What's wrong:** The script runs tests, runtime pip audit, frontend lint/coverage/build/E2E, but omits the development lock audit, Ruff lint/format, mypy, and Prettier check that are blocking CI jobs.
- **Impact:** Moderate — a developer can receive “Local verification complete” and still push a change that predictably fails CI.
- **Fix:** Add named fast/static/full phases, run every blocking static check in full parity mode, audit both Python locks, and print a final checklist showing executed/skipped gates.
- **Effort:** S
- **Grade lift:** B+ → A− (makes the one-command verifier trustworthy)

#### I3 — Align pre-commit and CI tool versions
- **Where:** `.pre-commit-config.yaml:11-24`, `requirements-dev.txt:1-11`
- **What's wrong:** Pre-commit pins Ruff 0.15.7 and mypy 1.19.1 while the development environment/CI pins Ruff 0.15.21 and mypy 2.2.0. A local hook can disagree with the commands CI executes.
- **Impact:** Moderate — version-specific lint/type behavior can create avoidable “passed locally, failed in CI” churn.
- **Fix:** Update hooks with the same versions as `requirements-dev.txt`, or invoke repository-local tools from a single lock-managed environment. Add a small CI check that detects version drift.
- **Effort:** S
- **Grade lift:** B+ → A− (removes a deterministic tooling inconsistency)

#### I4 — Remove duplicate installs and builds from the full local verifier
- **Where:** `scripts/verify-local.sh:47-74`, `compresso/webserver/frontend/package.json:7-18`
- **What's wrong:** A full run performs `npm ci`, builds once, installs Playwright, then `npm run test:e2e` builds the frontend a second time. The Python suite took about ten minutes in this audit, so redundant frontend work further slows the feedback loop.
- **Impact:** Minor — slower validation encourages developers to skip the most comprehensive gate.
- **Fix:** Add an E2E script that accepts an already-built `dist/spa`, cache/verify the Playwright browser, and support documented `static`, `unit`, `frontend`, and `full` modes without weakening CI.
- **Effort:** S
- **Grade lift:** B+ → A− (shortens the full feedback cycle while preserving coverage)
