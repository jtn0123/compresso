# Codebase Grade Report

**Project:** Compresso

**Audited:** 2026-07-12

**Baseline:** released `master` at `668ba24b8085f8d060fe0f861acfd88ebd307ccf` (`v1.13.2`)

**Stack:** Python 3.13, Tornado, Peewee/SQLite, Vue 3, Quasar/Vite, pytest, Vitest, Playwright, GitHub Actions

## Summary

| ID | Category | Grade | Items |
|----|----------|-------|-------|
| A | Architecture & Design | B- | 3 |
| B | Backend Quality | B | 5 |
| C | Frontend Quality | C | 5 |
| D | Testing & Reliability | B | 4 |
| E | Security | C+ | 6 |
| F | Dependencies & Tech Currency | B | 3 |
| G | Performance & Scalability | C+ | 5 |
| H | Documentation & Onboarding | C+ | 3 |
| I | Developer Experience & Tooling | B | 3 |
| **Overall** | | **B-** | **37** |

**Top 5 highest-leverage fixes:** E1, A1, B1, C1, G1

## Validation Snapshot

- PR `#184` merged cleanly, release `v1.13.2` published successfully, and no open PRs remained.
- Ruff and formatting passed across the Python source/tests; Mypy passed across 232 source files.
- Integration suite passed 21 tests; the full unit suite and post-merge cross-platform GitHub matrix were run against the merged revision.
- Frontend passed 416 unit tests, ESLint, isolated coverage, and a production build.
- Frontend coverage was 35.6% lines, 25.1% branches, and 24.9% functions, with 59 of 110 application files absent from the report.
- Python and npm security audits reported no known vulnerabilities.
- Focused repros confirmed stale-lease revival, duplicate analysis starts, unlimited negative pagination, invalid task types, scheduler exception propagation, and a download-link concurrency crash.
- This remains a NAS-free audit: real-media quality, NAS behavior, and physical M4 interruption/thermal evidence are still outside the evidence boundary.

### Implementation validation — `codex/audit-fix-batch`

- **18 of 37** addressable grade items are marked complete below; G1 received meaningful partial fixes but remains open until bounded streaming is complete.
- Python unit suite: **3,609 passed, 8 skipped**; focused changed-area suite: **342 passed, 2 skipped**; integration suite: **21 passed**.
- Ruff and format checks passed across 409 files; Mypy passed across 232 source files.
- Frontend: **427 passed**, coverage gate passed, ESLint passed, production build passed on Quasar 2.21.2, and all 3 strict mocked Playwright journeys passed.
- Frontend production dependency audit reported **0 vulnerabilities** after the compatible update batch.
- Security hardening: **129 focused backend tests** and **17 focused frontend tests** passed; the broader backend suite passed **3,623 tests with 8 skips** before the final seven focused security cases were added, and the full frontend suite passed **431 tests** plus production build.

---

## A — Architecture & Design — B-

Compresso now has strong durability primitives—leases, resumable transfers, scan checkpoints, a replacement journal, and explicit disk guards. The overall design is held back by unsupervised critical threads, separate filesystem/database durability protocols, and very large orchestration modules that combine several state machines.

### Architecture improvements

#### ~~A1~~ ✓ done 2026-07-12 — Add fault containment and health supervision for critical service threads

- **Where:** `compresso/libs/postprocessor.py:95-118`, `compresso/libs/scheduler.py:69-99`, `compresso/service.py:100-138`
- **What's wrong:** The postprocessor and scheduled-task loops have no per-iteration exception boundary. One unexpected database, filesystem, plugin, or cleanup exception can permanently end finalization or all recurring maintenance.
- **Impact:** Major — the installation can remain superficially alive while essential work has stopped.
- **Fix:** Contain each work item, record last-success/error and consecutive failures, expose thread health through readiness, and make the root service restart or fail visibly when a critical thread exits.
- **Effort:** M
- **Grade lift:** B- → B (prevents single exceptions from disabling whole subsystems)

#### A2 — Unify file replacement, history, and task state into one replayable protocol

- **Where:** `compresso/libs/postprocessor.py:386-412,801-846`, `compresso/libs/file_operation_tracker.py:106-125`, `compresso/libs/taskhandler.py:166-172`
- **What's wrong:** Files, history/metadata, and task deletion commit in separate durability domains. Recovery can treat the file as committed and delete the task without replaying missing audit/statistics state.
- **Impact:** Major — a crash can preserve media while silently losing authoritative history and operational evidence.
- **Fix:** Persist explicit finalization phases on the task, make each phase idempotent, and replay or roll back every phase before deleting task/journal state. Add crash injection at each boundary.
- **Effort:** L
- **Grade lift:** B- → B+ (creates one auditable recovery state machine)

#### A3 — Split the largest orchestration modules by state-machine responsibility

- **Where:** `compresso/libs/installation_link.py:1-1470`, `compresso/libs/postprocessor.py:1-1221`, `compresso/webserver/api_v2/pending_api.py:1-987`, `compresso/webserver/frontend/src/pages/ApprovalQueue.vue:1-1100`
- **What's wrong:** Networking, retry policy, persistence, lifecycle transitions, serialization, and UI actions coexist in modules near or above 1,000 lines.
- **Impact:** Moderate — small changes require understanding unrelated state machines and increase regression risk.
- **Fix:** Extract transport/reconciliation, finalization/history, pending-query, and approval-data/action services behind narrow interfaces; move tests with each seam before behavior changes.
- **Effort:** L
- **Grade lift:** B- → B (reduces coupling in the highest-risk maintenance surfaces)

---

## B — Backend Quality — B

The backend has strong schema coverage, checksummed transfers, retry/defer handling, and broad unit tests. Confirmed lifecycle defects remain around exceptional worker cleanup, lease expiry, task-domain validation, history transactions, and API error ownership.

### Backend improvements

#### ~~B1~~ ✓ done 2026-07-12 — Always release or defer a worker task after unexpected exceptions

- **Where:** `compresso/libs/workers.py:102-128,209-282`
- **What's wrong:** The loop logs unexpected exceptions but clears `current_task` only after a successful happy path. A failure can leave one worker retrying the same in-progress task forever.
- **Impact:** Major — one malformed file, plugin failure, or database error can permanently consume a worker and strand work.
- **Fix:** Wrap the task lifecycle in `try/finally`, persist a retry/defer or failed state, terminate residual subprocess state, and always detach the task. Add injected failures at each persistence boundary.
- **Effort:** M
- **Grade lift:** B → B+ (closes the clearest backend liveness defect)

#### ~~B2~~ ✓ done 2026-07-12 — Enforce lease expiry during heartbeat and first completion

- **Where:** `compresso/libs/remote_task_lease.py:61-93`
- **What's wrong:** Heartbeat and completion check token ownership but not whether the lease is still live. A stale worker can revive an expired lease or complete after its ownership window.
- **Impact:** Major — distributed exactly-once ownership can break during disconnect/reconnect races.
- **Fix:** Add `lease_expires_at > now` to heartbeat and first-completion predicates, and create a separate explicit reconciliation path for late identical results.
- **Effort:** S
- **Grade lift:** B → B+ (makes the lease contract match its expiry semantics)

#### ~~B3~~ ✓ done 2026-07-12 — Validate pagination and task types at both schema and domain boundaries

- **Where:** `compresso/webserver/api_v2/schema/schemas.py:118-160`, `approval_schemas.py:28-60`, `pending_schemas.py:151-180`, `compresso/libs/task.py:243-280,366-406`
- **What's wrong:** Negative/unlimited pagination is accepted, and task `type` accepts arbitrary strings even though lifecycle code handles only `local` and `remote`.
- **Impact:** Major — one request can load an entire large table or create a permanently stuck unique-path task.
- **Fix:** Require `start >= 0`, cap page sizes, restrict type to `local|remote`, and clamp/revalidate inside query and task-creation methods.
- **Effort:** S
- **Grade lift:** B → B+ (turns two reproduced API failures into rejected input)

#### B4 — Make history persistence transactional and idempotent

- **Where:** `compresso/libs/history.py:279-313`, `compresso/libs/postprocessor.py:386-412,1081-1103`
- **What's wrong:** Completed-task, command-log, and statistics rows are independent writes. A false late result is ignored and finalization can delete the task after partial history.
- **Impact:** Moderate — failures can lose statistics/logs or produce duplicate completed records on retry.
- **Fix:** Use an idempotency key and one database transaction for all history rows; treat any false result as a deferred finalization failure.
- **Effort:** M
- **Grade lift:** B → B+ (makes task history an all-or-nothing boundary)

#### B5 — Give the v2 API one structured error writer

- **Where:** `compresso/webserver/api_v2/base_api_handler.py:210-233,267-340`, `compresso/webserver/api_v2/pending_api.py:529-535`
- **What's wrong:** Request parsing writes an error and then raises, while many handlers catch and write again. Raw request bodies and exception strings can also become client-visible reasons.
- **Impact:** Moderate — malformed requests can cause double-finish behavior and leak unstable or sensitive implementation details.
- **Fix:** Make parsing raise a structured public error without writing, route expected/unexpected errors through one response owner, and log private diagnostics with correlation IDs.
- **Effort:** M
- **Grade lift:** B → B+ (standardizes the remaining weak API boundary)

---

## C — Frontend Quality — C

The Vue/Quasar interface is useful and has a coherent visual system, localization, and substantial unit coverage. Confirmed user-intent bugs, autosave races, disabled-control bypasses, platform-specific path handling, and accessibility/responsive failures prevent a professional B grade.

### Frontend improvements

#### ~~C1~~ ✓ done 2026-07-12 — Scope approval keyboard shortcuts to safe focus contexts

- **Where:** `compresso/webserver/frontend/src/pages/ApprovalQueue.vue:1047-1055`
- **What's wrong:** A window-level Enter handler approves whenever the detail dialog is open, regardless of whether Reject, Close, preview, or another interactive control has focus.
- **Impact:** Major — a normal keyboard action can replace the wrong media file.
- **Fix:** Ignore editable/interactive targets, require an explicit modifier or focused Approve action, guard re-entry, and add keyboard tests for every dialog control.
- **Effort:** S
- **Grade lift:** C → C+ (removes the highest-risk frontend action bug)

#### ~~C2~~ ✓ done 2026-07-12 — Serialize plugin autosaves without dropping edits

- **Where:** `compresso/webserver/frontend/src/components/settings/plugins/PluginInfoDialog.vue:470-505,564-575`
- **What's wrong:** Watcher events are discarded while a save is active; the first completion then refetches server state. A second edit can be overwritten without ever being sent.
- **Impact:** Major — operators can lose configuration changes with no warning.
- **Fix:** Queue one trailing save using immutable snapshots/version numbers, refetch only after the latest version is acknowledged, and test two edits around a delayed request.
- **Effort:** M
- **Grade lift:** C → C+ (makes autosave preserve user intent)

#### ~~C3~~ ✓ done 2026-07-12 — Prevent disabled plugin settings from changing through wrapper events

- **Where:** `compresso/webserver/frontend/src/components/settings/plugins/PluginInfoDialog.vue:148-160,470-489`
- **What's wrong:** The checkbox is disabled, but the parent click handler still toggles the bound value and the save request persists it.
- **Impact:** Moderate — settings presented as immutable can still be modified.
- **Fix:** Remove the wrapper handler or guard it on enabled state; use the checkbox event as the single owner and add a disabled-click regression.
- **Effort:** S
- **Grade lift:** C → C+ (restores the control contract)

#### ~~C4~~ ✓ done 2026-07-12 — Centralize cross-platform path presentation

- **Where:** `src/composables/useApprovalQueueData.js:17-20`, `src/boot/compressoWebsocket.js:358`, `src/components/dashboard/WorkersPanel.vue:273`, `src/pages/HealthCheck.vue:479`
- **What's wrong:** Filename extraction splits only on `/`; Windows paths display as the entire absolute path.
- **Impact:** Moderate — Windows deployments show broken labels in several core views.
- **Fix:** Add one tested path-display utility supporting `/` and `\\`, then replace all ad hoc splits.
- **Effort:** S
- **Grade lift:** C → C+ (fixes a repeated platform defect)

#### C5 — Enforce responsive and accessible interaction standards

- **Where:** `frontend/index.html:10`, `SettingsLibrary.vue:10,92`, `SettingsLink.vue:8,99`, `FirstRunWizard.vue:2-4`, `PluginInstallerManageRepos.vue:62-99`
- **What's wrong:** Browser zoom is disabled, platform detection replaces viewport breakpoints, several dialogs impose 400-560px minimum widths, and important actions use clickable spans.
- **Impact:** Moderate — narrow windows, phones, keyboard users, and low-vision users can be blocked from core setup/actions.
- **Fix:** Restore zoom, use `lt-md`/`useMobile`, maximize dialogs on small viewports, replace spans with semantic links/buttons, and add keyboard/mobile assertions.
- **Effort:** M
- **Grade lift:** C → B- (addresses the broadest UX/accessibility debt cluster)

---

## D — Testing & Reliability — B

Python reliability evidence is broad: thousands of unit tests, integration tests, cross-platform shards, fault/fuzz coverage, and a 75% floor. Frontend testing passes but measures only imported files, and browser lanes do not yet prove packaged destructive workflows or diverse clients.

### Testing improvements

#### D1 — Measure every frontend source file and ratchet meaningful thresholds

- **Where:** `compresso/webserver/frontend/vitest.config.js:11-20`, `compresso/webserver/frontend/src/`
- **What's wrong:** No source include pattern means unimported files count as nonexistent; 59 of 110 application files were absent while 30/20/20/30 thresholds passed.
- **Impact:** Major — core pages can have zero coverage without lowering the reported gate.
- **Fix:** Include all JS/Vue source with intentional generated/vendor exclusions, add tests for uncovered core flows, and ratchet thresholds from the resulting honest baseline.
- **Effort:** M
- **Grade lift:** B → B+ (makes frontend coverage representative rather than selective)

#### D2 — Exercise a packaged, state-changing release workflow end to end

- **Where:** `frontend/tests/e2e-live/compresso-live-smoke.spec.js:3-52`, `frontend/scripts/start-live-backend.mjs:20-29`
- **What's wrong:** Live E2E starts source through `PYTHONPATH` and checks mostly read-oriented startup contracts. It does not prove the wheel, migration, encode handoff, approval/reject, or restart workflow.
- **Impact:** Major — a release can pass while the installed product's core media lifecycle is broken.
- **Fix:** Install the built wheel in a disposable environment, seed a tiny media fixture, run queue→process→approve/reject→restart journeys, and assert disk/database outcomes.
- **Effort:** L
- **Grade lift:** B → B+ (adds genuine product-release proof)

#### ~~D3~~ ✓ done 2026-07-12 — Make mock E2E fail on unknown requests and runtime transport errors

- **Where:** `frontend/tests/e2e/compresso-smoke.spec.js:60-175,219-221`, `frontend/tests/e2e-live/compresso-live-smoke.spec.js:23-40`
- **What's wrong:** Unknown mock endpoints receive a generic HTTP 200 success, and suites inconsistently ignore console errors, request failures, and unexpected non-2xx responses.
- **Impact:** Moderate — renamed/misspelled endpoints and browser transport failures can leave smoke tests green.
- **Fix:** Reject unknown routes, fail on unexpected console/request/HTTP errors, and add deliberate 4xx/5xx recovery scenarios.
- **Effort:** S
- **Grade lift:** B → B+ (raises the signal of the existing browser lanes)

#### D4 — Add browser, mobile, and accessibility coverage

- **Where:** `frontend/playwright.config.js:24-29`, `frontend/playwright.live.config.js:51-56`, `.github/workflows/frontend_lint_and_build.yml:85-92`
- **What's wrong:** E2E runs only desktop Chromium and has no automated keyboard/axe gate despite responsive and accessibility requirements.
- **Impact:** Moderate — Safari/WebKit, Firefox, mobile layouts, and semantic failures are detected only manually.
- **Fix:** Add one mobile Chromium project, focused WebKit/Firefox smoke, axe checks, and keyboard traversal for approval/setup/plugin workflows.
- **Effort:** M
- **Grade lift:** B → B+ (covers declared client diversity and key accessibility contracts)

---

## E — Security — C+

The project has schema validation, rate limiting, security headers, SSRF guards, CodeQL, Sonar, Trivy, signed images, SBOMs, and clean advisory scans. The effective trust boundary is still incomplete: first launch is unauthenticated on all interfaces, protected mode exempts sensitive reads and whole handler families, secrets are stored weakly, plugins have full process privileges, CSP is permissive, and most Actions use mutable tags.

### Security improvements

#### ~~E1~~ ✓ done 2026-07-12 — Make authentication cover sensitive reads, WebSockets, proxying, and plugin APIs

- **Where:** `base_api_handler.py:53-73,141-193`, `settings_api.py:182-191`, `settings_link_mixin.py:147-169`, `websocket.py:56-171`, `proxy.py:116-189`, `plugins.py:121-205`
- **What's wrong:** API auth protects only selected mutation routes. Sensitive settings can return remote passwords, while WebSockets, proxy, and plugin APIs bypass the guarded base handler.
- **Impact:** Major — enabling auth does not actually create the boundary operators expect.
- **Fix:** Add shared authentication middleware for every dynamic route, protect all sensitive reads, return password-present placeholders instead of secrets, and add unauthorized integration tests for each handler family.
- **Effort:** M
- **Grade lift:** C+ → B (closes the largest confidentiality and boundary gap)

#### ~~E2~~ ✓ done 2026-07-12 — Use a safe first-launch network posture

- **Where:** `compresso/config.py:77-80,149-156`, `compresso/libs/uiserver.py:205-215`, `README.md:19-30`
- **What's wrong:** The default binds all interfaces with auth and CSRF disabled, while Quick Start publishes the port without an adjacent warning.
- **Impact:** Major — a mistaken router/container exposure permits unauthenticated media-changing requests.
- **Fix:** Bind loopback by default or require explicit trusted-LAN opt-in, generate a first-run token, and surface exposure mode in onboarding/readiness.
- **Effort:** M
- **Grade lift:** C+ → B- (reduces the most likely operator-driven exposure)

#### ~~E3~~ ✓ done 2026-07-12 — Store configuration secrets atomically with mode 0600 and redact failures

- **Where:** `compresso/config.py:263-273,323-327`, `compresso/libs/common.py:225-260`
- **What's wrong:** Settings inherit the process umask and write failures log the complete configuration, including credentials.
- **Impact:** Major — local users, backups, or logs can expose tokens, passwords, and webhooks.
- **Fix:** Write/replace with explicit `0600`, secure backups, preserve ownership, and recursively redact secret fields from every log/response path.
- **Effort:** S
- **Grade lift:** C+ → B- (protects stored credentials with a narrow change)

#### E4 — Isolate plugin installation and execution

- **Where:** `compresso/libs/plugins.py:486-564`, `compresso/libs/workers.py:736-751`
- **What's wrong:** Plugin ZIPs can trigger pip/npm install/build and runtime commands—including shell execution—with the full privileges of the Compresso process.
- **Impact:** Major — a compromised plugin can read configuration, alter media, or execute arbitrary host commands.
- **Fix:** Require trusted/signed sources, execute in a restricted container/process profile, default media to read-only, and grant network/filesystem capabilities explicitly.
- **Effort:** L
- **Grade lift:** C+ → B+ (turns a documented trust assumption into technical isolation)

#### E5 — Restore meaningful production CSP protection

- **Where:** `compresso/webserver/security_headers.py:46-59`, `compresso/webserver/frontend/quasar.config.cjs`
- **What's wrong:** Production permits both `unsafe-eval` and inline scripts/styles, sharply reducing CSP's value against future injection bugs.
- **Impact:** Moderate — a later XSS defect faces fewer browser-enforced barriers.
- **Fix:** Audit the bundle, choose a CSP-compatible Vue build, externalize or hash/nonce inline content, and add browser assertions that eval/inline execution is rejected.
- **Effort:** M
- **Grade lift:** C+ → B- (restores defense in depth)

#### E6 — Pin every third-party GitHub Action to an immutable commit

- **Where:** `.github/workflows/` (54 mutable-tag uses; examples in `python_lint_and_run_unit_tests.yml`, `integration_test_and_build_all_packages_ci.yml`, `release.yml`)
- **What's wrong:** Most Actions use mutable major tags even though selected release steps are already SHA-pinned.
- **Impact:** Moderate — an altered tag can change trusted CI or release behavior without a repository diff.
- **Fix:** Pin all external actions to reviewed SHAs with version comments and let Dependabot update those pins through review.
- **Effort:** M
- **Grade lift:** C+ → B- (closes broad CI supply-chain drift)

---

## F — Dependencies & Tech Currency — B

Runtime/dev Python locks and npm locks exist, and live audits found no known vulnerabilities. Reproducibility is weakened because tested/installed graphs differ, npm update automation is missing, and safe frontend updates plus an unused parser remain.

### Dependency improvements

#### F1 — Install the same hash-locked Python graph that CI audits

- **Where:** `requirements.lock`, `requirements-dev.lock`, `python_lint_and_run_unit_tests.yml:45-57,99-104`, `integration_test_and_build_all_packages_ci.yml:105-111`, `verify-local.yml:34-37`, `docker/Dockerfile.base:169-202`
- **What's wrong:** Audits inspect lockfiles, but CI, integration, local parity, and Docker install unlocked `.txt` inputs whose transitives can drift.
- **Impact:** Major — the code can run and ship with versions different from those that passed the security audit.
- **Fix:** Make hash-locked installs canonical, derive cache keys from locks, and add a check that source requirement inputs regenerate without diff.
- **Effort:** M
- **Grade lift:** B → B+ (aligns audit, test, package, and runtime graphs)

#### ~~F2~~ ✓ done 2026-07-12 — Add Dependabot coverage for all npm lockfiles

- **Where:** `.github/dependabot.yml:1-35`, `compresso/webserver/frontend/package-lock.json`, `compresso/webserver/package-lock.json`, `.github/release/package-lock.json`
- **What's wrong:** Dependabot covers pip, Actions, and Docker but none of the three npm directories.
- **Impact:** Moderate — JavaScript security and compatibility updates rely on manual discovery.
- **Fix:** Add weekly npm entries per directory with grouped patch/minor updates and conservative PR limits.
- **Effort:** S
- **Grade lift:** B → B+ (completes automated dependency coverage)

#### ~~F3~~ ✓ done 2026-07-12 — Remove dead dependencies and batch compatible frontend updates

- **Where:** `compresso/webserver/frontend/package.json:20-63`, `src/js/markupParser.js:2`
- **What's wrong:** `js-bbcode-parser` is declared but unused, and compatible updates are available for Axios, Quasar, Vue, Vitest, DOMPurify, and related tooling.
- **Impact:** Moderate — unused/stale packages add supply-chain surface and future migration cost.
- **Fix:** Remove the unused parser, batch patch/minor updates under full frontend gates, and isolate Quasar-app/router/ESLint majors into separate migration lanes.
- **Effort:** M
- **Grade lift:** B → B+ (keeps the supported stack current without upgrade bundling)

---

## G — Performance & Scalability — C+

The metadata benchmark, indexes, bounded scan queues, worker caps, transfer chunks, disk guards, and restart handling are meaningful gains. The actual library-analysis path remains materially different from the benchmark and contains confirmed duplicate scans, O(file-count) memory, repeated probing/hashing, and event-loop blocking I/O.

### Performance improvements

#### G1 — Rebuild real library analysis as one bounded, single-flight pipeline

- **Where:** `compresso/webserver/helpers/library_analysis.py:49-76,226-270`, `libraryanalysiscache.py:16-27`
- **What's wrong:** Concurrent starts can launch duplicate scans, and each scan stores every path in a list then a set before probing.
- **Impact:** Major — two requests can duplicate a 20 TB scan while each consumes memory proportional to file count.
- **Fix:** Make start atomic, enforce one row/job per library, stream files in bounded batches, mark rows by analysis generation, and remove stale rows after the pass.
- **Effort:** M
- **Grade lift:** C+ → B (fixes the biggest gap between the benchmark and production path)

#### ~~G2~~ ✓ done 2026-07-12 — Move remote transfer hashing and durable writes off Tornado's event loop

- **Where:** `compresso/webserver/api_v2/transfer_api.py:97-169`, `compresso/libs/resumable_transfer.py:181-227`
- **What's wrong:** Async handlers perform synchronous chunk/file hashing plus data and manifest `fsync` operations.
- **Impact:** Major — large or slow transfers can freeze every web/API/readiness request on the process.
- **Fix:** Use bounded worker threads for store operations/hashing, stream progress, and batch durability checkpoints while preserving crash recovery.
- **Effort:** M
- **Grade lift:** C+ → B- (keeps the control plane responsive during large transfers)

#### G3 — Avoid content hashing unchanged files during cached analysis

- **Where:** `compresso/webserver/helpers/library_analysis.py:160-177`, `compresso/libs/common.py:315-399`
- **What's wrong:** Cache lookup computes a fingerprint first; large files reread ten 8 MiB samples even when unchanged.
- **Impact:** Major — repeated cached analysis still creates heavy random NAS I/O across a huge library.
- **Fix:** Gate content hashes behind persisted size/mtime/file-ID checks and hash only new or changed candidates.
- **Effort:** M
- **Grade lift:** C+ → B- (makes cache hits cheap enough for production use)

#### ~~G4~~ ✓ done 2026-07-12 — Reuse one ffprobe result per analysis file

- **Where:** `compresso/webserver/helpers/library_analysis.py:135-149`, `compresso/libs/ffprobe_utils.py:66-118`
- **What's wrong:** Metadata extraction probes the file, then bitrate extraction launches ffprobe again for data already available in the first result.
- **Impact:** Moderate — a 100,000-file analysis launches roughly 200,000 probe processes.
- **Fix:** Return/reuse the original probe payload and derive codec, resolution, duration, and bitrate in one pass.
- **Effort:** S
- **Grade lift:** C+ → B- (halves a dominant external-process cost)

#### G5 — Allocate distributed workers from runnable demand and measured throughput

- **Where:** `compresso/libs/scheduler.py:149-210`, `compresso/libs/task.py:362-364`, `compresso/libs/foreman.py:723-790`
- **What's wrong:** Allocation counts every task status and does not rank compatible workers by queue depth, throughput, transfer cost, or thermal/capability state.
- **Impact:** Moderate — approval/deferred backlogs can attract workers despite no runnable work, starving the M4 or another installation.
- **Fix:** Count only runnable non-deferred work, persist rolling per-capability throughput, and apply one deterministic allocation score with bounded rounded totals.
- **Effort:** L
- **Grade lift:** C+ → B (turns existing telemetry into useful distributed scheduling)

---

## H — Documentation & Onboarding — C+

Architecture, deployment, development, release recovery, and supply-chain controls are documented. The primary Docker command currently fails, the critical 20 TB runbook is hidden under `.Codex`, and licensing guidance contradicts the declared GPL license.

### Documentation improvements

#### ~~H1~~ ✓ done 2026-07-12 — Fix every Docker quick-start image reference

- **Where:** `README.md:19-30`, `docker/docker-compose.yml:11-15`, `docs/CONFIGURATION.md:69-78`
- **What's wrong:** Documentation uses `jtn0123/compresso:latest`, which denied public manifest access, while the published GHCR image resolved successfully.
- **Impact:** Major — the shortest supported onboarding path cannot start the product.
- **Fix:** Point all examples to GHCR or restore verified public Docker Hub publishing; add a CI smoke check for every documented image reference.
- **Effort:** S
- **Grade lift:** C+ → B (restores the primary install path)

#### ~~H2~~ ✓ done 2026-07-12 — Publish the 20 TB safety plan as supported operator documentation

- **Where:** `.Codex/20tb-media-compression-plan.md:1-191`, `docs/FORK_DEPLOYMENT.md:66-131`, `README.md`
- **What's wrong:** Master/worker separation, staged 20-file→100 GB→500 GB→1 TB gates, and snapshot-backed batches live in an internal audit directory with no public-doc link.
- **Impact:** Major — operators can deploy a large library without seeing the rules that define safe use.
- **Fix:** Move the plan to `docs/LARGE_LIBRARY_RUNBOOK.md` and link it from README, deployment, and roadmap docs.
- **Effort:** S
- **Grade lift:** C+ → B (puts the safety contract on the supported path)

#### H3 — Resolve the repository's license contradiction

- **Where:** `LICENSE`, `setup.py:227-231`, `README.md:150-164`, copyright headers across `compresso/`
- **What's wrong:** Metadata/LICENSE say GPL-3.0-only, while README and hundreds of source headers mix MIT permission text with “All Rights Reserved.”
- **Impact:** Moderate — contributors and redistributors cannot confidently determine obligations.
- **Fix:** Obtain the copyright-holder decision, then align LICENSE, metadata, README, headers, frontend license, and third-party notices in one reviewed change.
- **Effort:** M
- **Grade lift:** C+ → B- (removes the largest onboarding/legal ambiguity)

---

## I — Developer Experience & Tooling — B

CI is broad and unusually capable: cross-platform shards, integration, frontend, package reproducibility, Docker, CodeQL, Sonar, signing, SBOMs, and recovery workflows. Local parity does not actually mirror those gates, release semantics are not enforced, and master/release workflows duplicate substantial validation.

### Developer-experience improvements

#### I1 — Make local verification explicitly match fast and full CI modes

- **Where:** `scripts/verify-local.sh:18-79`, `.github/workflows/python_lint_and_run_unit_tests.yml`, `.github/workflows/integration_test_and_build_all_packages_ci.yml`
- **What's wrong:** The script claims parity but omits Ruff/format/Mypy, dev-lock audit, integration, release-tool tests, actionlint/contracts, and clean package/artifact validation.
- **Impact:** Moderate — a developer can receive “Local verification complete” while required CI gates would still fail.
- **Fix:** Add documented fast/full modes, run the canonical commands, and print an explicit skipped-gates summary.
- **Effort:** M
- **Grade lift:** B → B+ (makes the local result truthful and actionable)

#### I2 — Enforce release-driving commit or PR-title conventions

- **Where:** `docs/GENERATING_MASTER_RELEASE.md:3-17`, `.github/release/prepare-candidate.mjs:54-74`, `commitlint.config.js:1-3`, `.github/pull_request_template.md:1-18`
- **What's wrong:** Conventional Commit syntax drives release selection, but commitlint is not installable from the root and no workflow validates merge titles.
- **Impact:** Moderate — valid changes can silently produce no release or the wrong release level.
- **Fix:** Add PR-title validation, wire a real local commitlint dependency/script, and document squash/merge-title expectations in the template.
- **Effort:** S
- **Grade lift:** B → B+ (protects the release trigger contract)

#### I3 — Remove duplicate validation from publication-bound master pushes

- **Where:** `.github/workflows/release.yml:3-16`, `python_lint_and_run_unit_tests.yml:3-10`, `frontend_lint_and_build.yml:3-10`, `integration_test_and_build_all_packages_ci.yml:3-9`
- **What's wrong:** A master merge starts direct Python/frontend/package workflows while release validation repeats many gates against the candidate SHA.
- **Impact:** Moderate — duplicated runners slow feedback and create noisy duplicate coverage/Sonar/status results.
- **Fix:** Keep broad PR validation, make release-bound master validation owned by one workflow, and retain a clearly named scheduled/manual non-publishing package lane.
- **Effort:** M
- **Grade lift:** B → B+ (simplifies the release signal and critical path)
