# Compresso Codebase Regrade and Release Readiness

Audited: 2026-07-11<br>
Commit: `750a0b50ef6b386b2a46897d1ea7e3e34ee3bf59` (`v1.13.0`, current `origin/master`)<br>
Scope: architecture, backend, frontend, testing, security, dependencies, performance, documentation, developer experience, live GitHub release/package state, and the 20 TB master/M4 rollout plan.

## Verdict

**Overall grade: B** (up from the previous B- baseline).

The application code is in release-candidate shape, and the post-merge validation is strong. It is **not safe to call the current distribution process release-ready**, because the `v1.13.0` GitHub Release was created before the full gates completed while the package workflow independently built `1.12.1.post7` and moved the GHCR `latest` tag to that version. The exact source passed its gates later, but the published version identities are not coherent.

For the 20 TB master plus M4 worker objective, the restart-safe code foundation is credible, but production approval remains a no-go until the real-machine and scale gates are run. The repository itself explicitly leaves C4-C5, the 500,000-entry scan acceptance run, and E1-E6 open.

## Grade summary

| Area | Grade | Release interpretation |
|---|---:|---|
| A. Architecture | B | Sound single-process service and durable job design; boundaries remain too broad. |
| B. Backend | B+ | Strong fail-closed data-safety work and 88% coverage; transaction and typing edges remain. |
| C. Frontend | B- | Useful, functional UI with growing tests; oversized components and standards drift raise change risk. |
| D. Testing | B+ | Excellent Python coverage/fuzzing; weak full-stack and real distributed validation. |
| E. Security | B | Good scanning and request guards; trusted-LAN posture and unsandboxed plugins must be explicit. |
| F. Dependencies | A- | Locked and clean audits; release tooling is not reproducibly pinned. |
| G. Performance | B- | Bounded implementations exist, but the scale claims lack measured evidence. |
| H. Documentation | B+ | Strong operator warnings and rollout plan; release and licensing text need correction. |
| I. Developer experience | C+ | Good local/CI tooling is undercut by a major release-orchestration defect. |

## Evidence that is already strong

- Live `master` validation completed successfully after the release: 3,569 unit tests, 20 integration tests, repository Ruff/format/mypy, 88% Python coverage, SonarCloud, and CodeQL.
- The frontend local recheck passed 26 files and 416 tests. Coverage was 35.61% lines, 24.90% functions, and 25.08% branches.
- Runtime and development Python locks passed `pip-audit`; `pip check` passed; production npm audit reported zero known vulnerabilities.
- The package workflow passed frontend reproducibility, integration, wheel checks, amd64/arm64 Docker builds, runtime smoke, Trivy, keyless signing, SBOM generation, and manifest creation.
- The distributed reliability pass documents 20 reproduced-and-fixed defects, 242 critical-path tests, deterministic transfer fuzzing, capacity fuzzing, restart recovery, checksummed chunking, durable leases, and fail-closed replacement.

## Top 5 release priorities

1. **Make versioning, validation, and publishing one gated release transaction.** Do not create a GitHub Release or move `latest` until the exact version commit has passed all required tests and the same commit produced every artifact.
2. **Repair the current release identity.** Verify or quarantine `v1.13.0`/GHCR `latest`, then publish a corrective version whose source tag, app version, wheel metadata, Docker labels/tags, changelog, and SBOM all agree.
3. **Run a real full-stack master/M4 canary.** Exercise upload, encode, download, restart, lease expiry, low disk, corruption rejection, and final replacement against copied/snapshot-backed media.
4. **Add a real-backend browser lane.** Keep the fast mocked Playwright smoke test, but add a second lane that boots the packaged backend and proves its main user journeys and API contracts together.
5. **Close the scale evidence gates.** Run the 500,000-entry scan benchmark and the 20-file, 100 GB, 500 GB, and 1 TB staged soaks; record memory, SQLite latency, queue depth, integrity accounting, and per-machine throughput.

## A. Architecture — B

### A1. Filesystem journals and database state do not share one commit boundary

- **Where:** `compresso/libs/postprocessor.py:58-83`, `compresso/webserver/api_v2/transfer_api.py:99-118`, and `compresso/libs/resumable_transfer.py:203-228`.
- **What’s wrong:** Finalized files/manifests and task/database records are updated in separate operations. Retry logic reduces the risk, but there is no single durable state machine transaction spanning both stores.
- **Impact:** Major — a crash at the boundary can leave an artifact completed without the expected task/history transition.
- **Fix:** Model finalization as an idempotent outbox/state machine with explicit prepared, artifact-committed, database-committed, and reconciled states; add crash tests at every transition.
- **Effort:** L
- **Grade lift:** B to A-

### A2. Core responsibilities remain concentrated in very large modules

- **Where:** `compresso/libs/installation_link.py` (1,470 lines), `compresso/libs/postprocessor.py` (1,174), `compresso/libs/plugins.py` (976), and `compresso/webserver/api_v2/pending_api.py` (987).
- **What’s wrong:** Networking, orchestration, persistence, recovery, and API behavior still coexist in modules large enough that changes have wide and difficult-to-predict blast radii.
- **Impact:** Moderate — distributed and destructive workflows become harder to reason about and review safely.
- **Fix:** Extract explicit services for link transport, lease/job coordination, finalization, plugin installation, and pending-task query/action handling; keep adapters thin.
- **Effort:** L
- **Grade lift:** B to B+

### A3. API v1 and v2 duplicate cross-cutting handler infrastructure

- **Where:** `compresso/webserver/api_v1/base_api_handler.py:42` and `compresso/webserver/api_v2/base_api_handler.py:85`.
- **What’s wrong:** Two base-handler stacks can drift on authentication, security headers, error behavior, routing, and validation.
- **Impact:** Moderate — a fix applied to one API generation may leave the other exposed or inconsistent.
- **Fix:** Move shared request security, error serialization, headers, and observability into one common base/middleware layer; isolate only version-specific routing and schemas.
- **Effort:** M
- **Grade lift:** B to B+

## B. Backend — B+

### B1. Transfer finalization has a recoverable but fragile split write

- **Where:** `compresso/webserver/api_v2/transfer_api.py:99-118`.
- **What’s wrong:** The transfer store finalizes first, then creates/binds the pending task. An exception between those operations returns an error after the durable artifact has already advanced.
- **Impact:** Major — retries must perfectly reconstruct intent or operators can see confusing completed-transfer/orphan-task states.
- **Fix:** Persist a finalization intent before moving the artifact, make task creation idempotent on the transfer/job identity, and reconcile unfinished intents at startup.
- **Effort:** M
- **Grade lift:** B+ to A-

### B2. Generic exception-to-response handling exposes internal reason text

- **Where:** `compresso/webserver/api_v2/base_api_handler.py:286-340`.
- **What’s wrong:** Unhandled exceptions set the HTTP reason from `str(exc)`, which is then returned in the JSON error string even when traceback serving is disabled.
- **Impact:** Moderate — filesystem paths, database details, or internal state may leak to API clients.
- **Fix:** Return a stable public error code/message, generate a correlation ID, and keep the original exception only in structured server logs.
- **Effort:** S
- **Grade lift:** B+ to A-

### B3. Type checking permits important blind spots

- **Where:** `pyproject.toml:53-71`.
- **What’s wrong:** Mypy ignores missing imports and untyped third-party boundaries and does not enable strict optional, disallow-untyped-defs, or related strictness incrementally.
- **Impact:** Moderate — orchestration payload and return-shape defects can survive until runtime.
- **Fix:** Add strictness per module, starting with transfer, lease, worker capability, disk guard, manifests, and API schema boundaries; add typed protocol objects for link transports and persistence services.
- **Effort:** M
- **Grade lift:** B+ to A-

### B4. The SQLite concurrency posture is safe but operationally narrow

- **Where:** `compresso/libs/unmodels/lib/basemodel.py:137-154` and `README.md:147-148`.
- **What’s wrong:** A queued SQLite writer and WAL are sensible for one service process, but the application documents database-lock pressure and has no validated high-cardinality latency envelope.
- **Impact:** Moderate — large scans and concurrent UI/worker activity may create latency spikes or backlogs before obvious failure.
- **Fix:** Add DB queue-depth/latency telemetry, explicit busy-timeout policy, slow-query reporting, and scale acceptance thresholds; keep one owner per config DB.
- **Effort:** M
- **Grade lift:** B+ to A-

## C. Frontend — B-

### C1. Several UI components are too large to change safely

- **Where:** `CompletedTasksListDialog.vue` (1,550 lines), `ApprovalQueue.vue` (1,150), `PendingTasksListDialog.vue` (1,055), and `VideoCompare.vue` (1,001).
- **What’s wrong:** Fetching, state, actions, dialogs, tables, formatting, and presentation are combined in single files.
- **Impact:** Major — regressions and merge conflicts become likely as release features accumulate.
- **Fix:** Split each surface into data/composable, table, toolbar, row/action, dialog, and formatting units with contract tests around the composables.
- **Effort:** L
- **Grade lift:** B- to B+

### C2. The codebase is split between Composition and Options API styles

- **Where:** 85 Vue components: 46 use `<script setup>` and 39 retain Options API; standard is documented in `compresso/webserver/frontend/AGENTS.md:83-87`.
- **What’s wrong:** Two state/lifecycle patterns raise review overhead and encourage duplicate helpers.
- **Impact:** Moderate — frontend maintenance and onboarding stay more difficult than necessary.
- **Fix:** Convert only when touching large legacy components, prioritizing the four largest surfaces and shared drawers/settings pages.
- **Effort:** L
- **Grade lift:** B- to B

### C3. Responsive implementation violates the project’s own standard

- **Where:** `SettingsLink.vue:8,99`, `SettingsLibrary.vue:10,92`, `SettingsWorkers.vue:10`, `MobileSettingsQuickNav.vue:3`, and plugin partials; rule at `AGENTS.md:147-152`.
- **What’s wrong:** Components directly use `$q.platform.is.mobile` and inline layout expressions instead of width-aware visibility classes, media queries, or `useMobile`.
- **Impact:** Moderate — desktop windows on mobile devices and narrow desktop browsers can select the wrong layout.
- **Fix:** Replace direct platform checks with Quasar breakpoints/CSS and keep exceptional JavaScript switching behind `useMobile`.
- **Effort:** M
- **Grade lift:** B- to B

### C4. Some click targets are not semantic keyboard controls

- **Where:** `compresso/webserver/frontend/src/components/drawers/DrawerNotifications.vue:19-23`.
- **What’s wrong:** Click handlers are attached to `q-item-section` content without explicit button semantics or keyboard activation.
- **Impact:** Moderate — keyboard and assistive-technology users may not be able to trigger notification actions reliably.
- **Fix:** Put the action on a clickable `q-item`/button, add accessible names and focus states, and cover keyboard activation with component or browser tests.
- **Effort:** S
- **Grade lift:** B- to B

### C5. User-visible text still bypasses i18n

- **Where:** `MainLayout.vue:89`, `VideoCompare.vue:20,24`, and other direct English labels found under `src/`.
- **What’s wrong:** Strings such as “Notifications”, “VMAF: N/A”, and “SSIM: N/A” are embedded in templates even though translation infrastructure exists.
- **Impact:** Minor — localization and consistent product copy are incomplete.
- **Fix:** Add translation keys and an ESLint/static check for raw user-facing template text outside approved technical tokens.
- **Effort:** S
- **Grade lift:** B- to B

## D. Testing — B+

### D1. Browser E2E is mocked rather than full-stack

- **Where:** `compresso/webserver/frontend/AGENTS.md:61-72`, `playwright.config.js:18-29`, and the single `tests/e2e/compresso-smoke.spec.js`.
- **What’s wrong:** Playwright intercepts API calls and serves a static build, so it cannot catch packaged-backend routing, schema drift, auth/CSRF, websocket, database, or startup defects.
- **Impact:** Major — the deployed product can break while both frontend and backend tests pass independently.
- **Fix:** Add a separate live-backend Playwright project that boots a disposable packaged server/database and runs the critical dashboard, queue, approval, settings, and recovery journeys.
- **Effort:** M
- **Grade lift:** B+ to A-

### D2. The most important distributed tests have not run on real machines

- **Where:** `.Codex/20tb-media-compression-plan.md:115-117,135-176`.
- **What’s wrong:** C4-C5 and E1-E6 remain open: no real master/M4 interruption canary, representative-media validation, or staged 100 GB/500 GB/1 TB soak evidence.
- **Impact:** Major — network, filesystem, sleep/wake, VideoToolbox, thermal, and real media behavior remain assumptions.
- **Fix:** Execute the documented gates in order with snapshots, manifests, forced restarts, corruption injection, and an archived result bundle for every stage.
- **Effort:** L
- **Grade lift:** B+ to A

### D3. Scale acceptance benchmarks are described but not automated

- **Where:** `.Codex/20tb-media-compression-plan.md:169-171` and `.Codex/20tb-deep-reliability-audit.md:54-61`.
- **What’s wrong:** The 500,000-entry scanner benchmark and production soak metrics have no reproducible CI/nightly harness or stored baseline.
- **Impact:** Major — performance regressions can invalidate 20 TB readiness without failing a normal PR.
- **Fix:** Add benchmark fixtures, machine metadata, RSS/latency/queue metrics, thresholds, and scheduled/manual artifact retention.
- **Effort:** M
- **Grade lift:** B+ to A

### D4. Frontend coverage remains shallow

- **Where:** `compresso/webserver/frontend/vitest.config.js:11-20`; local result: 35.61% lines, 24.90% functions, 25.08% branches.
- **What’s wrong:** The enforced floor is only 30/20/20/30, leaving most UI behavior and error branches unmeasured.
- **Impact:** Moderate — large components can regress outside the small tested surface.
- **Fix:** Raise thresholds by changed-file or module tiers, starting with approval, distributed worker status, destructive actions, settings, and API/auth error states.
- **Effort:** M
- **Grade lift:** B+ to A-

### D5. Frontend tests pass with excessive unresolved-component warnings

- **Where:** `src/test-utils/mount-helpers.js:48-112` and tests using `shallowMountWithQuasar`.
- **What’s wrong:** The local 416-test run emitted thousands of Vue warnings for unresolved Quasar components/directives, making real warnings easy to miss and reducing render fidelity.
- **Impact:** Moderate — a noisy green suite can hide template and component-registration defects.
- **Fix:** Install Quasar in the test harness or deliberately stub every framework component/directive, then fail CI on unexpected Vue warnings.
- **Effort:** M
- **Grade lift:** B+ to A-

## E. Security — B

### E1. Authentication and CSRF are disabled by default and reads remain unauthenticated

- **Where:** `compresso/config.py:149-156`, `base_api_handler.py:137-198`, and `docs/FORK_DEPLOYMENT.md:45-49`.
- **What’s wrong:** The default model intentionally trusts localhost/LAN, and token checks protect mutations rather than the entire API. A mistaken bind/proxy configuration can expose library/task metadata and control surfaces.
- **Impact:** Major — deployment error can expose sensitive paths/media metadata or allow destructive control when protection is not enabled correctly.
- **Fix:** Add a production mode that requires a generated token, protects all non-health endpoints, validates proxy headers/TLS assumptions, and fails startup on unsafe non-loopback exposure.
- **Effort:** M
- **Grade lift:** B to A-

### E2. Plugins install and execute unsandboxed third-party code

- **Where:** `compresso/libs/plugins.py:535-564` and worker plugin subprocess paths.
- **What’s wrong:** Plugin requirements run `pip install`, `npm install`, and `npm run build`, while worker plugins are designed to execute commands with the Compresso process’s filesystem authority.
- **Impact:** Major — a compromised or malicious plugin can read/modify the media library, configuration, credentials, and host-visible mounts.
- **Fix:** Add signed/provenance-checked plugin manifests, explicit permission review, allowlisted repositories, isolated runtime/container execution, and a no-network/read-only option.
- **Effort:** L
- **Grade lift:** B to A-

### E3. The frontend CSP permits inline scripts and eval

- **Where:** `compresso/webserver/security_headers.py:42-60`.
- **What’s wrong:** `script-src` includes both `'unsafe-inline'` and `'unsafe-eval'`, weakening the main browser control against injected script execution.
- **Impact:** Moderate — a future injection bug has a much easier exploitation path.
- **Fix:** Build a CSP-compatible bundle, replace inline content with nonces/hashes where needed, remove `unsafe-eval`, and add a browser security-header test.
- **Effort:** M
- **Grade lift:** B to B+

### E4. CI supply-chain pinning is inconsistent

- **Where:** `.github/workflows/*.yml`; Docker, PyPI, signing, and SBOM actions use SHAs while checkout, setup, cache, upload/download, Sonar, Trivy, and stale actions use tags.
- **What’s wrong:** Mutating tags remain part of workflows that receive repository/package permissions.
- **Impact:** Moderate — an upstream tag compromise can alter trusted CI execution.
- **Fix:** Pin every third-party action to a reviewed commit SHA and let Dependabot update those pins.
- **Effort:** S
- **Grade lift:** B to B+

## F. Dependencies — A-

### F1. Release tooling is installed dynamically without a lock

- **Where:** `.github/workflows/release.yml:17-25`.
- **What’s wrong:** Every release runs an unversioned `npm install --no-save` for semantic-release and plugins, so the same commit can release differently on different days.
- **Impact:** Major — release behavior and credentials are entrusted to an unreproducible dependency resolution.
- **Fix:** Commit a dedicated locked release-tool package, use `npm ci`, pin Node/action versions, and test the release configuration without publishing.
- **Effort:** S
- **Grade lift:** A- to A

### F2. Dependabot does not cover the frontend npm lock

- **Where:** `.github/dependabot.yml:1-30`.
- **What’s wrong:** Pip, GitHub Actions, and Docker are configured, but the 640-package frontend development graph has no npm update lane.
- **Impact:** Moderate — fixes and compatible updates depend on manual discovery.
- **Fix:** Add an npm entry for `compresso/webserver/frontend`, group safe updates, and keep major upgrades isolated.
- **Effort:** S
- **Grade lift:** A- to A

### F3. Several major-version migrations remain unplanned

- **Where:** `compresso/webserver/frontend/package.json:19-55`; `npm outdated` flagged major lines for `@quasar/extras`, `js-bbcode-parser`, `vue-router`, and `xbbcode-parser`.
- **What’s wrong:** Current versions are audited clean, but aging parser/router contracts can accumulate migration cost and ecosystem incompatibility.
- **Impact:** Minor — not an immediate release blocker, but delay increases future upgrade risk.
- **Fix:** Track one compatibility issue per major upgrade, add focused contract tests, and avoid bundling parser/router majors into release-critical work.
- **Effort:** M
- **Grade lift:** A- to A

## G. Performance — B-

### G1. The 500,000-entry scan target is unproven

- **Where:** `.Codex/20tb-media-compression-plan.md:169-171`.
- **What’s wrong:** Checkpointing and bounded traversal are implemented, but peak RSS, database latency, scan duration, and queue depth at the acceptance scale have not been measured.
- **Impact:** Major — a 20 TB library can stall or exhaust resources despite small-test correctness.
- **Fix:** Run the synthetic benchmark on release hardware, capture metrics, set acceptance limits, and preserve the result as a build artifact/baseline.
- **Effort:** M
- **Grade lift:** B- to B+

### G2. Worker routing lacks measured master-versus-M4 throughput

- **Where:** `.Codex/20tb-deep-reliability-audit.md:74-75` and `.Codex/20tb-media-compression-plan.md:166-168`.
- **What’s wrong:** Capability/load-aware routing exists, but C4 is open because real codec/container throughput and thermal behavior have not been measured.
- **Impact:** Major — routing can be correct yet inefficient enough to make the migration impractical.
- **Fix:** Benchmark representative codecs, resolutions, HDR, subtitles, and largest files on both machines; route from observed throughput and error rates.
- **Effort:** M
- **Grade lift:** B- to B+

### G3. Production manifests scale in memory

- **Where:** `compresso/libs/media_manifest.py:125-180` and `.Codex/20tb-deep-reliability-audit.md:71-73`.
- **What’s wrong:** File paths, probe summaries, verification results, and final JSON are accumulated in lists before being written.
- **Impact:** Moderate — one monolithic 20 TB inventory can consume unnecessary memory and lose all progress on interruption.
- **Fix:** Stream deterministic JSONL records, checkpoint traversal/probe state, and generate a compact signed summary/index after completion.
- **Effort:** M
- **Grade lift:** B- to B

### G4. SQLite pressure has no release threshold

- **Where:** `compresso/libs/unmodels/lib/basemodel.py:137-150`, `README.md:147-148`, and open scale-gate documentation.
- **What’s wrong:** WAL and a queued writer are good safeguards, but there is no defined maximum write latency, queue depth, or UI-read latency under scan plus worker load.
- **Impact:** Moderate — operations may degrade gradually without triggering an automated stop condition.
- **Fix:** Export database queue/latency metrics to the operations endpoint and add pause/backpressure thresholds validated by the 500k run.
- **Effort:** M
- **Grade lift:** B- to B+

## H. Documentation — B+

### H1. The critical 20 TB runbook lives in an internal `.Codex` directory

- **Where:** `.Codex/20tb-media-compression-plan.md` and `.Codex/20tb-deep-reliability-audit.md`.
- **What’s wrong:** The strongest safety guidance, open gates, recovery drills, and no-go language are not part of the normal public/operator documentation path.
- **Impact:** Major — an operator can follow README/Docker quick start without seeing the 20 TB-specific constraints.
- **Fix:** Promote a maintained production migration runbook into `docs/`, link it prominently from README and release notes, and version its acceptance checklist.
- **Effort:** S
- **Grade lift:** B+ to A-

### H2. Release documentation describes a sequence the workflows do not enforce

- **Where:** `docs/GENERATING_MASTER_RELEASE.md:7-18` versus `.github/workflows/release.yml:1-25` and the package workflow.
- **What’s wrong:** The guide implies the release and package publication form one coherent automated process, but they run independently from different commits/versions.
- **Impact:** Major — maintainers can believe a green release is internally consistent when it is not.
- **Fix:** Correct the workflow first, then document exact commit, gate, artifact, tag, signing, rollback, and verification order.
- **Effort:** S
- **Grade lift:** B+ to A-

### H3. README currently points users at an inconsistent `latest`

- **Where:** `README.md:19-30` and live GHCR publication from run `29147749073`.
- **What’s wrong:** Quick start pulls `jtn0123/compresso:latest`, while the current master package run moved `latest` using metadata `1.12.1.post7` during the `v1.13.0` release.
- **Impact:** Major — operators cannot tell which version they installed and rollback/support become ambiguous.
- **Fix:** Repair the tag, publish immutable digest/version examples, and make release notes list the verified digest.
- **Effort:** S
- **Grade lift:** B+ to A-

### H4. License text is internally contradictory

- **Where:** `README.md:150-167` versus the repository `LICENSE` (GPLv3).
- **What’s wrong:** README says GPLv3, “All Rights Reserved,” and then includes an MIT-style permission grant.
- **Impact:** Moderate — users and contributors cannot confidently determine their rights and obligations.
- **Fix:** Replace the mixed block with a concise GPLv3 statement, SPDX identifier, copyright attribution, and a link to `LICENSE`; review inherited file headers separately.
- **Effort:** S
- **Grade lift:** B+ to A-

## I. Developer Experience — C+

### I1. Release publication races validation and produces mismatched versions

- **Where:** `.github/workflows/release.yml:1-25`, `.releaserc.json:7-14`, and `.github/workflows/integration_test_and_build_all_packages_ci.yml:182-218,253-320,582-618`.
- **What’s wrong:** Both workflows start on the pre-release `master` commit. Semantic-release created/tagged `1.13.0` at 09:27:53Z, while the package workflow built `compresso-1.12.1.post7` and later pushed GHCR `latest` plus `1.12.1.post7`. Full unit/Sonar gates finished after publication.
- **Impact:** Major — a public release can precede failure and its source, app metadata, and Docker tags can disagree.
- **Fix:** Use one orchestrated workflow: determine version, create an immutable candidate commit, build/test/scan that SHA, verify artifact metadata, publish, then create/move release tags only after all required jobs pass.
- **Effort:** M
- **Grade lift:** C+ to B+

### I2. The generated release commit is not the commit that package CI validates

- **Where:** `.releaserc.json:7-13`; live release commit `750a0b5` versus validated/package commit `cf04a2e`.
- **What’s wrong:** VERSION/CHANGELOG are committed after the original push workflows start, and the token-generated commit does not run the same complete build/package matrix.
- **Impact:** Major — the tag’s exact source tree and version metadata are not the artifact-producing input.
- **Fix:** Generate version metadata before candidate validation, or build from the created tag in a `workflow_run`/reusable workflow that requires upstream success and asserts `VERSION == tag == package metadata`.
- **Effort:** M
- **Grade lift:** C+ to B+

### I3. The local parity script omits several canonical gates

- **Where:** `scripts/verify-local.sh:22-77`.
- **What’s wrong:** It runs unit/frontend checks but omits the development-lock audit, Ruff, format, mypy, Python integration tests, wheel metadata checks, and Docker preflight from its default all-up path.
- **Impact:** Moderate — “Local verification complete” is weaker than the release matrix and can give false confidence before push.
- **Fix:** Add fast/full modes; make full mode call the exact reusable scripts/jobs used by CI and print a machine-readable gate summary.
- **Effort:** M
- **Grade lift:** C+ to B

### I4. Repository-specific IDE state is tracked

- **Where:** `.idea/` contains 18 tracked files, including local data sources and run configurations.
- **What’s wrong:** Personal/editor state creates churn and can include machine-specific paths or database metadata.
- **Impact:** Minor — noisy diffs and accidental local-state leakage reduce repository hygiene.
- **Fix:** Keep only intentionally shared run configurations in an editor-neutral location, remove the rest from version control, and update `.gitignore`.
- **Effort:** S
- **Grade lift:** C+ to B-

### I5. GitHub Releases carry no built artifact or verification manifest

- **Where:** Live `v1.13.0` GitHub Release has zero uploaded assets; package/SBOM artifacts remain attached to workflow runs.
- **What’s wrong:** Operators cannot retrieve a release-bound wheel, SBOM, digest list, checksum, or verification statement from the release itself.
- **Impact:** Moderate — provenance and reproducible installation/rollback are harder than necessary.
- **Fix:** Attach the validated wheel/sdist, checksums, SBOMs, image digests, and a signed release manifest generated from the exact tag.
- **Effort:** M
- **Grade lift:** C+ to B

## Release gates from here

### Gate 0 — Correct the release pipeline and current tags

- Stop treating `v1.13.0`/`latest` as a verified coherent artifact set.
- Make candidate version generation precede validation.
- Assert source tag, `VERSION`, Python metadata, runtime version, Docker tag/label, changelog, SBOM, and digest all match.
- Publish a corrective release only after all required jobs succeed on the exact candidate SHA.

### Gate 1 — Product-level release smoke

- Boot the packaged artifact/container from scratch.
- Run live-backend browser journeys for onboarding, dashboard, queue, approval/reject, settings, workers, health, websocket reconnect, restart, and upgrade/migration.
- Confirm authentication/CSRF behavior in production mode and trusted-LAN behavior in local mode.

### Gate 2 — Distributed canary

- Use copied or snapshot-backed representative media only.
- Run one master plus one M4 worker at one encode.
- Interrupt upload, encode, download, staging, and final replacement.
- Require one stable job ID, no duplicate replacement, checksum integrity, complete manifest accounting, and clean recovery after process restart/sleep.

### Gate 3 — Scale acceptance

- Execute 500,000-entry scan benchmark.
- Execute 100 GB fault drill, 500 GB overnight soak, and 1 TB multi-day soak.
- Record per-machine throughput, peak RSS, disk high-water mark, SQLite latency/queue depth, retries, thermal throttling, integrity failures, and final accounting.
- Only then process production in snapshot-backed 500 GB to 1 TB batches.

## Bottom line

The app has moved materially closer to release: the backend, reliability engineering, dependency hygiene, and test coverage are substantially stronger than the earlier B- baseline. The immediate release decision is still **no-go** until the version/publication race is fixed and a coherent corrective artifact set is produced. After that, it is reasonable to release for guarded normal use with the trusted-LAN limitation documented. A 20 TB production run remains a separate approval and must wait for the nine open real-machine/scale gates.
