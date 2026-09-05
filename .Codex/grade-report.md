# Codebase Grade Report

**Project:** Compresso — media library optimizer (Python 3.13 / Tornado / Peewee-SQLite backend, Vue 3 / Quasar / Vite frontend)

**Audited:** 2026-07-20

**Baseline:** `master` at `51cbec1` (post-v1.16.2)

**Method:** Nine-category audit performed by parallel deep-inspection passes over the full tree (~51.4k LOC Python across 439 files, ~34k LOC frontend across 162 JS/Vue files), with every grade-driving claim independently re-verified against source at the cited line numbers. All findings below were confirmed in the current tree; no category was graded without direct inspection. Line numbers reference this revision.

**Grading policy:** Security (E) and Testing & Reliability (D) are double-weighted in the overall grade, per audit charter.

---

## Summary

| ID | Category | Grade | Findings |
|----|----------|-------|----------|
| A | Architecture & Design | **B-** | 5 |
| B | Backend Quality | **C+** | 9 |
| C | Frontend Quality | **C+** | 7 |
| D | Testing & Reliability | **B** | 6 |
| E | Security | **C+** | 4 (+ cross-ref B2) |
| F | Dependencies & Tech Currency | **A-** | 5 |
| G | Performance & Scalability | **C+** | 7 |
| H | Documentation & Onboarding | **B+** | 4 |
| I | Developer Experience & Tooling | **A-** | 4 |
| **Overall** (E, D ×2) | | **B-** | **41** |

The headline: this codebase has *elite process hygiene* (hash-locked dependencies, SHA-pinned CI, CI-parity local verification, semantic-release, real OpenAPI docs, crash-journaled finalization) wrapped around a core that still carries real product-level defects — a verified user-data-loss bug, security-off-by-default posture, and a web layer that blocks its single event loop. The gap between the tooling grade (A-) and the code grades (C+) is itself the diagnosis: the mock-heavy test suite (145 of 172 unit files use mocks) green-lights bugs that only exist at real integration boundaries (see B1, B3).

### Top 5 highest-leverage improvements

1. **E1 — Enable API auth + CSRF by default** (Major, Effort S–M, lifts E from C+ toward B+). Everything else in the security posture is already built; the defaults just don't turn it on.
2. **B1 — Fix the `keep_both` data-loss bug** (Major, Effort S–M, lifts B from C+ toward B-). `postprocessor.py:749` calls a method that doesn't exist; the error is swallowed and the user's original file is replaced despite them choosing "keep both."
3. **B2 — Turn off Tornado `debug=True` in production** (Major, Effort S, lifts B and E). One line; currently every unhandled API error serves a full traceback to the client.
4. **D1 — Run the 75% coverage gate on `pull_request` events** (Major, Effort S, lifts D from B toward B+). The only enforcement point is skipped for fork PRs — the main OSS contribution path is un-gated.
5. **G1 — Move blocking DB/file work off the Tornado IOLoop** (Major, Effort M, lifts G from C+ toward B). A single decorator on `_invoke_route` covers most routes; today one slow write freezes every client.

---

## A — Architecture & Design — B-

**Why this grade:** The macro-architecture is deliberate and unusually defensive: named supervised threads with startup verification and a fail-fast critical-thread watchdog (`compresso/service.py:84-497`), a crash-safe file-operation journal with phased finalization (`compresso/libs/postprocessor.py:60-74, 553-725`), a sound `unffmpeg` codec/container abstraction, and a correct answer to threads-vs-SQLite (`SqliteQueueDatabase` + WAL, `compresso/libs/unmodels/lib/basemodel.py:138-153`). What holds it to B- is structural: singleton wiring everywhere, an inverted dependency edge from `libs/` back into `webserver/`, and 1,200–1,500-line god modules at the highest-churn points.

### Findings

**A1. Pervasive mutable singleton state as the wiring mechanism — Major**
- **Where:** `compresso/libs/singleton.py:37-47`; used by 13 classes incl. `Config` (`compresso/config.py:73`), `PluginsHandler` (`compresso/libs/plugins.py:77`), `Links` (`compresso/libs/installation_link.py:53`), `CompressoDataQueues`/`CompressoRunningThreads` (`compresso/libs/uiserver.py:66-89`); module-level singletons at `compresso/webserver/api_v2/rate_limiter.py:112-124`, `compresso/webserver/helpers/library_analysis.py:29-30`.
- **What's wrong:** Components reach sideways into singletons instead of receiving dependencies. `SingletonType.__call__` silently ignores constructor args after first instantiation — `config.Config(port=args.port)` in `service.py:536` only works because it happens to be first; any earlier `Config()` construction silently drops the CLI port. Initialization order is load-bearing and invisible.
- **Impact:** Major · **Fix:** Introduce an application context object created in `service.py` and passed down; minimally, make `SingletonType.__call__` raise when called with args after the instance exists. · **Effort:** L (M for the guard alone) · **Grade lift:** A → B with A2.

**A2. Layering inversion: `libs/` and `ops/` import from `webserver/` — Major**
- **Where:** `compresso/libs/request_handler.py:35`, `compresso/libs/healthcheck.py:23`, `compresso/libs/uiserver.py:48,248,260,270,298,315` (an entire Tornado server living in `libs/`), `compresso/ops/doctor.py:33`, `compresso/ops/planner.py:22`.
- **What's wrong:** The intended direction is `webserver → libs`; these back-edges create a de facto circular package dependency (`webserver.websocket` → `libs.uiserver` → `webserver.*`) kept alive only by deferred in-function imports. The root cause is business logic (551-line `library_analysis.py`, zero Tornado imports) living under `webserver/helpers/`.
- **Impact:** Major · **Fix:** Move `library_analysis.py` into `libs/`, move `API_AUTH_HEADER_NAME` to a libs-level constants module, relocate `uiserver.py` into `webserver/`. · **Effort:** M · **Grade lift:** A → B with A1.

**A3. God modules at the highest-risk points — Moderate**
- **Where:** `compresso/libs/installation_link.py` (1,459 lines — HTTP client + link registry + transfer locks + config sync + resumable transfers + remote-task API in one singleton), `compresso/libs/postprocessor.py` (1,394), `compresso/libs/plugins.py` (1,208), `compresso/libs/foreman.py` (928).
- **Impact:** Moderate · **Fix:** Split `Links` into transport / registry / transfer manager; extract Foreman's remote-manager pool. · **Effort:** L · **Grade lift:** part of A → B.

**A4. Plugin executor mutates process-global `sys.path`/`sys.modules`; substring-based module reload — Moderate**
- **Where:** `compresso/libs/unplugins/executor.py:135-144` (plugin dirs + site-packages appended to `sys.path`, never removed), `:224-240` (`reload_plugin_module` matches `if plugin_id in m` — plugin `foo` matches `foobar.plugin`).
- **What's wrong:** All plugins share one flat interpreter namespace; two plugins vendoring different versions of a dependency shadow each other by load order. Reload can unload the wrong plugin's modules. (Credit: path containment at `:117-133`, trust gating at `:198-211`, and child-process execution with PID reaping in `child_process.py:47-103` are well designed.)
- **Impact:** Moderate · **Fix:** Prefix-match module names (`m == pid or m.startswith(pid + ".")`); import plugin modules under isolated names. · **Effort:** M · **Grade lift:** minor.

**A5. Hand-rolled second routing layer inside API handlers — Minor**
- **Where:** `compresso/webserver/api_v2/base_api_handler.py:405-461` — `action_route` loops over route dicts compiling `PathMatches` per request.
- **Impact:** Minor · **Fix:** Precompile per class at import time (S) or migrate to Tornado URLSpecs (L). · **Effort:** S–L · **Grade lift:** minor.

### Positives
- Supervised thread topology with staged `StartupState` readiness and `monitor_critical_threads` fail-fast (`compresso/service.py:103-114, 327-346, 378-396`).
- Idempotent, resumable finalization journal (`file_committed → history_committed → metadata_committed → task_deleted`, `postprocessor.py:68-74, 432-451`) — a design most media servers don't attempt.
- `unffmpeg` and `unmodels` layers are clean, documented abstractions; two-phase schema strategy is unusually well documented (`compresso/libs/unmodels/lib/db_migrate.py:166-201`).
- Near-zero TODO/FIXME density (4 in the backend); zero bare `except:` clauses.

---

## B — Backend Quality — C+

**Why this grade:** The craftsmanship floor is high — atomic JSON writes, `.part`-suffix copy-then-rename with rollback (`postprocessor.py:1110-1179`), poisoned-task containment (`workers.py:217-236`), grep-able structured log tokens. But the audit verified **three Major functional defects in the current tree**, one of which loses user data, and all three share a signature: broad `except` arms plus mock-based tests that can't see them. That combination caps the grade at C+ despite the strong surrounding engineering.

### Findings

**B1. "keep_both" replacement policy calls a method that doesn't exist → original file silently replaced — Major**
- **Where:** `compresso/libs/postprocessor.py:749` calls `self.current_task.set_destination_path(new_path)`. No such method exists on `Task` (`compresso/libs/task.py` defines `modify_path`, `set_cache_path`, … but not this). Verified: repo-wide grep finds the name only at the call site and in Mock-based tests (`tests/unit/test_postprocessor_extended.py:296,312,325`, `tests/unit/test_flow_features.py:692-758`).
- **What's wrong:** At runtime the `AttributeError` is swallowed by `except (OSError, AttributeError, KeyError, TypeError)` at `postprocessor.py:750-751` (logged as a warning), then finalization proceeds with the *unmodified* destination — the default move that replaces the original file. A user who chose "keep both" loses their original. Unit tests pass because `Mock` accepts any attribute.
- **Impact:** Major (user data loss) · **Fix:** Implement `Task.set_destination_path` (persist a destination override consumed by `get_destination_data`) and add a non-mock integration test that asserts both files exist afterward. · **Effort:** S (method) + M (test) · **Grade lift:** B1+B3+B7 together lift B from C+ to ~B.

**B2. Production Tornado app runs with `debug=True` → tracebacks served to API clients — Major**
- **Where:** `compresso/libs/uiserver.py:54-63` — `"debug": True, "autoreload": False` unconditionally. Tornado sets `serve_traceback=True` whenever `debug` is truthy; `compresso/webserver/api_v2/base_api_handler.py:323-328` then embeds `traceback.format_exception(...)` in every 500 response.
- **What's wrong:** Internal paths, code, and exception detail leak to any API client in normal deployments — defeating the careful error-ID design in `handle_unhandled_error` (`base_api_handler.py:288-306`). Also disables template/static caching.
- **Impact:** Major (information disclosure; counts against E too) · **Fix:** Default `"debug": False`; set `debug`/`serve_traceback` only in `update_tornado_settings` when dev mode is requested (that hook already exists at `uiserver.py:167-171`). · **Effort:** S · **Grade lift:** contributes to both B and E lifts.

**B3. `TaskDataStore.import_task_state`/`delete_task_state` silently lose data under the multiprocessing Manager — Major**
- **Where:** `compresso/service.py:417-418` swaps `TaskDataStore._runner_state`/`_task_state` for `Manager().dict()` proxies. `compresso/libs/task.py:750-762` (`import_task_state`) does `t = cls._task_state.setdefault(task_id, {})` then mutates `t` in place; `task.py:709-724` (`delete_task_state`) mutates the dict returned by `.get()`. On a `DictProxy` those return *copies*; mutations never propagate.
- **What's wrong:** In the real service, remote task state imported at `compresso/libs/remote_task_manager.py:875` is discarded, and `delete_task_state` never deletes. The sibling methods `set_runner_value`/`set_task_state` (`task.py:636-645, 685-689`) were correctly written copy-then-reassign — this is an inconsistency, invisible to unit tests that run with plain dicts.
- **Impact:** Major · **Fix:** Rewrite both methods copy-then-reassign. · **Effort:** S · **Grade lift:** see B1.

**B4. Pending-task claim is not atomic — duplicate-assignment window — Moderate**
- **Where:** `compresso/libs/taskqueue.py:247-266` returns the task still in status `pending`; `mark_item_in_progress` (`:318-328`) is never called on this path; status flips only when the worker reaches `compresso/libs/workers.py:282`, up to ~1.5 s after `Foreman.hand_task_to_workers` (`compresso/libs/foreman.py:665-700`).
- **What's wrong:** The next Foreman iteration (~2 s) can fetch the same still-`pending` row and hand it to another idle worker — two workers encoding the same file under slow DB writes or a paused worker holding an unstarted task (`workers.py:108-112`).
- **Impact:** Moderate · **Fix:** Claim atomically at fetch (`UPDATE … SET status='in_progress' WHERE id=? AND status='pending'`). · **Effort:** S–M · **Grade lift:** part of concurrency-correctness lift.

**B5. Foreman worker registry mutated from two threads without locks — Moderate**
- **Where:** `compresso/libs/foreman.py` — `worker_threads`/`paused_worker_threads` mutated by the Foreman loop (`:254-294`, `:739-756`) and by Tornado API handlers (`:563-657` via `compresso/webserver/api_v2/workers_api.py:86-190`).
- **What's wrong:** Compound sequences race: API `resume_worker_thread` can `list.remove` concurrently with the Foreman clearing the paused list (lost pause records or `ValueError`); `get_tags_configured_for_worker` (`:525-529`) can `KeyError` between check and access.
- **Impact:** Moderate · **Fix:** One `threading.Lock` around registry mutations, or route API commands through a queue consumed by the Foreman loop. · **Effort:** M.

**B6. Environment-variable booleans are truthy strings — `enable_library_scanner=false` *enables* the scanner — Moderate**
- **Where:** `compresso/config.py:237-246` assigns raw env strings; getters returning raw values: `get_enable_library_scanner` (`:556-562`), `get_run_full_scan_on_start` (`:564-570`), `get_follow_symlinks` (`:580-586`), `get_first_run` (`:476-482`), `get_auto_manage_completed_tasks` (`:516-522`), `get_always_keep_failed_tasks` (`:540-546`), `get_clear_pending_tasks_on_restart` (`:508-514`). Verified: `_as_bool` (`:67-70`) is applied to a dozen *other* getters (e.g. `:641, :660, :699, :702`) but not these.
- **What's wrong:** In Docker deployments, `enable_library_scanner=false` or `follow_symlinks=0` do the opposite of what the operator asked; `clear_pending_tasks_on_restart="false"` would wipe queues.
- **Impact:** Moderate (deployment foot-gun) · **Fix:** Apply `_as_bool` in the remaining boolean getters. · **Effort:** S · **Grade lift:** cheap, visible correctness win.

**B7. Failed worker runner reported as successful to the frontend — Moderate**
- **Where:** `compresso/libs/workers.py:573-574` — after the per-runner loop, `success = True; status = "complete"` runs unconditionally, overwriting `success = False` recorded at `:484-494`, `:546-547`, `:475-477`.
- **Impact:** Moderate (misleads incident triage; overall task failure is tracked separately) · **Fix:** Only set `True` if not already marked failed. · **Effort:** S.

**B8. Mislabeled catch-alls, dead code, slow drain loop — Minor**
- **Where:** `compresso/libs/postprocessor.py:209-210, 219-221, 461, 741-743` — generic `except Exception` arms log invented labels (`GuardrailRejectionError`, `PolicyResolutionError`, …) for any exception type (the B1 swallow is the concrete cost). `compresso/libs/task.py:389-426` — dead `Tasks.DoesNotExist` branch whose `query = []` fallback would crash at `:426`. `compresso/libs/foreman.py:727-737` — `event.wait(0.5)` before every `get_nowait` adds 0.5 s per completed task.
- **Impact:** Minor · **Fix:** Log `type(e).__name__`; delete the dead branch; move the wait out of the loop. · **Effort:** S.

**B9. Substring-based path guards gate recursive deletes — Minor**
- **Where:** `compresso/libs/workers.py:661`, `compresso/libs/postprocessor.py:1103` (`if "compresso_file_conversion" not in path` gating `shutil.rmtree`), `compresso/libs/task.py:450-452`.
- **What's wrong:** The marker is matched anywhere in the full path, so a user directory containing the marker string becomes delete-eligible. Correct component-wise checks already exist in the same codebase (`compresso/libs/common.py:183-218`, `postprocessor.py:1082-1091`).
- **Impact:** Minor (low likelihood, high blast radius) · **Fix:** Check the basename component and verify containment under the configured cache path. · **Effort:** S.

### Positives
- Robust failure containment: catch-log-continue guards with heartbeat health snapshots (`ThreadHealthMixin` in `postprocessor.py:88-129`, `scheduler.py:55-113`); subprocess handling with `start_new_session`, psutil-based terminate, communicate timeouts (`workers.py:777-850`).
- Resource cleanup above average: atomic JSON writes throughout, plugin child-process reaping incl. SIGCONT-before-terminate (`unplugins/child_process.py:61-103`).
- DB layer: WAL + FK pragmas on runtime and migration connections (`db_migrate.py:120-126`); defensive idempotent migrations (`migrations_v1/006, 008`); deliberate performance indexes (007, 009).

---

## C — Frontend Quality — C+

**Why this grade:** Security-relevant discipline is genuinely good (every `v-html` sink traced through DOMPurify, zero raw `console.*`, solid CSRF/token plumbing) and the tooling is modern. The grade is held down by structural debt: eight 700–1,250-line monolith components, a hand-rolled global-singleton state layer that the repo's own docs misdescribe, no static typing, and a 24% coverage floor.

### Findings

**C1. Eight monolithic components over 700 lines with duplicated template logic — Major**
- **Where:** `compresso/webserver/frontend/src/components/dashboard/completed/CompletedTasksListDialog.vue` (1,251), `src/pages/ApprovalQueue.vue` (1,159 — table fetch + approval settings + preview-job poller at `:979-1045` + filter debounce `:780-790` + refresh interval `:1071` in one `setup()`), `src/components/preview/VideoCompare.vue` (1,001), `src/components/settings/library/LibraryConfigDialog.vue` (855), `src/pages/HealthCheck.vue` (777), `src/pages/TaskHistory.vue` (769), `src/pages/SettingsLibrary.vue` (768), `src/components/dashboard/pending/PendingTasksListDialog.vue` (765). Completed/Pending dialogs duplicate ~600 lines of near-identical toolbar markup despite logic already being shared via `useTaskListController`.
- **Impact:** Major (maintainability, test cost) · **Fix:** Extract a shared `TaskListToolbar`; pull the preview-job poller into a `usePreviewJob()` composable. · **Effort:** M–L · **Grade lift:** C1+C2 lift C from C+ to ~B-.

**C2. Ad-hoc global-singleton state; declared Vuex dependency never used; AGENTS.md documents a store that doesn't exist — Major**
- **Where:** `src/js/compressoGlobals.js` (mutable `$compresso` object), `src/js/compressoWebsocket.js:47-99` (listener registry as expando properties on the raw socket), `src/js/sharedLinksStore.js:8-30`; `package.json:37` declares `vuex: ^4.1.0` with zero imports anywhere; `quasar.config.js:76-84`, `vitest.config.js:30-38`, `jsconfig.json` alias a nonexistent `stores/` dir; `AGENTS.md` claims "State Management: Vuex".
- **Impact:** Major (misleads contributors and AI agents; untestable state) · **Fix:** Remove `vuex`, correct AGENTS.md, migrate `$compresso` caches to Pinia or one documented reactive store module. · **Effort:** M.

**C3. Unguarded `JSON.parse` in the WebSocket message handler — Moderate**
- **Where:** `src/js/compressoWebsocket.js:335` — no try/catch; one malformed frame throws in the `message` listener. Dead code nearby: unused `icon` (`:218`), unused `timeout` param (`:191`), `serverId` returned by value (`:468`) so `handler.serverId` stays `null`.
- **Impact:** Moderate · **Fix:** try/catch + `log.error`; delete dead code. · **Effort:** S.

**C4. Placeholder axios instance pointing at `https://api.example.com` registered app-wide as `$api` — Moderate**
- **Where:** `src/boot/axios.js:86` (`axios.create({ baseURL: 'https://api.example.com' })`), registered at `:95`, exported at `:101`.
- **What's wrong:** Quasar scaffolding leftover; unused today, but the first future use silently sends requests (without the CSRF/token interceptors, which are attached to the default instance) to a third-party domain.
- **Impact:** Moderate (latent) · **Fix:** Delete it, or point at `getCompressoServerUrl()` and move interceptors onto it. · **Effort:** S.

**C5. Silent error swallowing; argument-less `reject()` — Moderate**
- **Where:** `src/pages/ApprovalQueue.vue:831-833` (`catch { // ignore }` on approval-settings fetch), `:1022-1026` (preview poll failure clears state with no notification); `src/js/compressoGlobals.js` — `getCompressoSession`/`getCompressoPrivacyPolicy` call bare `reject()`, losing the error.
- **Impact:** Moderate · **Fix:** Log ignored catches; `reject(err)`. · **Effort:** S.

**C6. Dead legacy templates with third-party branding shipped in the package — Minor**
- **Where:** `compresso/webserver/templates/global/insufficient-permissions.html`, `login-popup.html`, `support-future-development.html` — Patreon/Unmanic-era modals, zero references anywhere in `compresso/`.
- **Impact:** Minor · **Fix:** Delete `templates/global/`; verify MANIFEST.in. · **Effort:** S.

**C7. Single-locale i18n with stray hardcoded strings — Minor**
- **Where:** Only `src/language/en.json` exists; hardcoded `<q-tooltip>Notifications</q-tooltip>` at `src/layouts/MainLayout.vue:89` (line 77 correctly uses `$t()` for the same button's aria-label); literal `'CPU'/'MEM'/'GPU'` at `:245-249`.
- **Impact:** Minor · **Fix:** Route strays through `$t()`. · **Effort:** S.

### Positives
- XSS discipline: every `v-html` sink traced goes through DOMPurify (`src/js/sanitize.js`; e.g. `PluginInfoDialog.vue:417-418`, `ApplicationLogsDialog.vue:165-171`); websocket-delivered strings escaped (`compressoWebsocket.js:10-18`).
- Auth plumbing: CSRF cookie header + API token + origin check before attaching credentials (`src/boot/axios.js:24-30`), retry-once-on-401; websocket auth via base64url subprotocol (`src/js/apiAuth.js`).
- `useTaskListController.js` is a well-designed shared composable with a thorough unit test.
- Zero raw `console.*` in `src/` — all logging via `createLogger` (`src/composables/useLogger.js`).
- Playwright e2e includes axe-core accessibility scans and mobile/Firefox/WebKit projects (`playwright.config.js:24-46`).

---

## D — Testing & Reliability — B

**Why this grade:** By volume and infrastructure this is an A-tier suite: 3,784 backend test functions across 177 files, a 3-OS matrix with 3-way pytest-split sharding, ~453 frontend unit cases, mocked + live Playwright lanes, `asyncio_mode = "strict"`, and exceptional conftest hygiene (leaked-thread reaper, singleton resets — `tests/conftest.py:110-202`). The app's own reliability engineering (journaled crash recovery, watchdog, staged startup) is verified and tested. It doesn't grade higher because the gates have holes exactly where it matters: the coverage gate never runs on PRs, and the suite's mock-heaviness (145/172 unit files) is precisely why B1 and B3 — both invisible to Mocks — shipped.

### Findings

**D1. The 75% coverage gate never runs on `pull_request` events — Major**
- **Where:** `.github/workflows/python_lint_and_run_unit_tests.yml:140` — the `coverage_report` combine job has `if: github.event_name == 'push'`; each shard runs `--cov-fail-under=0` (`:118-119`). `fail_under = 75` lives in `pyproject.toml:25`.
- **What's wrong:** Same-repo branches get gated via the parallel push run, but fork PRs — the normal OSS contribution path — are never coverage-gated, and the PR check list never contains the coverage result.
- **Impact:** Major · **Fix:** Run the combine job on both events. · **Effort:** S · **Grade lift:** D1+D3 lift D from B toward B+.

**D2. Integration coverage is thin and unit tests are mock-heavy — Moderate**
- **Where:** `tests/integration/` — 5 files, 21 tests vs 3,763 unit tests (0.6%); 145/172 unit files import `unittest.mock`; even integration tests patch internals (`tests/integration/test_taskhandler.py:137` patches `PluginsHandler`; `test_file_pipeline.py:174` patches `shutil.move`).
- **What's wrong:** Much of the suite verifies mock interactions, not behavior. B1 (`set_destination_path` on a Mock) and B3 (plain dicts vs Manager proxies) are the proof: both pass unit tests and fail in reality.
- **Impact:** Moderate (weighted heavily here) · **Fix:** Grow integration tests around the highest-risk flows: full task lifecycle with a real small video (fixture exists), crash-mid-encode recovery, approval → postprocess → file replacement with `keep_both`. · **Effort:** L · **Grade lift:** with D1, D → B+/A-.

**D3. `.test_durations` is stale — shard balance degrading — Moderate**
- **Where:** `.test_durations` last regenerated 2026-04-07; contains 2,483 entries vs 3,763 current unit tests (>34% unknown to pytest-split), used by `--splits 3 --group N` (`python_lint_and_run_unit_tests.yml:120`).
- **Impact:** Moderate (CI wall time) · **Fix:** Scheduled workflow running `pytest --store-durations` monthly. · **Effort:** S.

**D4. Sleep-based synchronization and class-shared state in integration tests — Moderate**
- **Where:** `tests/integration/test_taskhandler.py:86, 134, 149, 158, 180, 189, 209, 219, 238, 248, 269, 278, 298` — fixed `time.sleep(0.2/0.5/2)` then a single assertion; `setup_class` shares one DB connection and one long-lived task-handler thread across all 7 tests (order-dependent).
- **Impact:** Moderate (flakiness by design; ~6 s dead time/run) · **Fix:** `wait_for(predicate, timeout)` helper; per-test fixtures. · **Effort:** S–M.

**D5. Frontend coverage floor is 24/16/17/24 — Moderate**
- **Where:** `compresso/webserver/frontend/vitest.config.js:17-24`. Tests concentrate in `src/js/` and composables; only ~6 page and ~4 component tests for a many-page SPA. Credit: the config comment documents an honest all-source baseline and forbids shrinking `include` to game the gate.
- **Impact:** Moderate · **Fix:** Enforce the promised ratchet (+2%/month); target the largest untested pages first. · **Effort:** M.

**D6. No per-test timeout, no clock control — Minor**
- **Where:** No `pytest-timeout`/`pytest-rerunfailures` in `requirements-dev.txt`; zero freezegun/fake-clock use against 93 raw `datetime.now()`/`time.time()` reads in tests (e.g. `tests/unit/test_link_reconnection.py:72,97`). In a thread-heavy suite, one deadlock hangs a shard until the runner's job timeout.
- **Impact:** Minor · **Fix:** `pytest-timeout` default ~120 s; a monkeypatched-clock fixture for timestamp tests. · **Effort:** S.

### Positives
- 3,784 tests, 3-OS matrix (ubuntu/macos/windows), sharded with per-shard `.coverage` properly combined; `asyncio_mode = "strict"` (`pyproject.toml:8`).
- `tests/conftest.py` hygiene is exceptional: autouse leaked-thread reaper (`:110-131`), atexit/reload-hook cleanup (`:134-161`), singleton/shared-state resets (`:164-202`).
- App reliability verified in code: journal-based crash recovery before workers start (`compresso/service.py:246-272`, tested by `tests/unit/test_restart_recovery.py` et al.), critical-thread watchdog paired with Docker `HEALTHCHECK` (`service.py:378-396`, `docker/Dockerfile:57-58`), graceful shutdown with join timeouts (`:348-361`). One nit: the DB shutdown wait at `service.py:494-496` has no deadline.
- Playwright setup above average: CI retries with trace/video on failure, tag-scoped mobile/Firefox/WebKit, mocked + live-backend lanes run on every push/PR.

---

## E — Security — C+

**Why this grade:** The *mechanics* are near-exemplary for this class of app — and were each verified: constant-time token comparison (`compresso/webserver/request_auth.py:43-60`), CSRF double-submit support, a strict CSP with no inline/eval script (`compresso/webserver/security_headers.py:50-64`), websocket origin checks + command allowlist (`compresso/webserver/websocket.py:57-105,119-123`), sha256-required remote plugin packages (`compresso/libs/plugins.py:487-498`), zip extraction with member validation, 64 MiB cap, staged install/rollback and permission sanitization (`plugins.py:600-680`), no `shell=True`/`os.system` anywhere in source, SHA-pinned CI actions enforced by `scripts/check-action-pins.sh`. What drags the grade to C+ is that the *defaults leave it all switched off*, plus the debug-traceback leak (B2) and an uncontained file browser. Ship-state, not capability, is what an operator experiences.

### Findings

**E1. API auth and CSRF protection are disabled by default; no login layer exists — Major**
- **Where:** `compresso/config.py:156-158` (`api_auth_enabled = False`, `api_auth_token = ""`, `csrf_protection_enabled = False`); enforcement is opt-in in `compresso/webserver/request_auth.py:63-79` and `compresso/webserver/api_v2/base_api_handler.py:170-193`.
- **What's wrong:** There is no user/password login at all — only an optional bearer token. With defaults, every endpoint (settings write, library config, plugin install, file browse, proxy) is open and CSRF-unprotected. In typical NAS deployments users remap the port LAN-wide; any LAN device (or a DNS-rebinding page) then has full admin — and plugin installation is arbitrary code execution in the server process by design.
- **Impact:** Major · **Fix:** Auto-enable API auth on first run (the token generator at `config.py:197` already exists — flip the default and surface the token in log/UI), or force-enable auth whenever `ui_address` is non-loopback (the condition is already detected and warned at `uiserver.py:183-184`). Enable CSRF by default. · **Effort:** S–M · **Grade lift:** E C+ → B+ with E2.

**E2. File browser exposes the entire filesystem with no containment — Major**
- **Where:** `compresso/webserver/helpers/filebrowser.py:43-57` — `_validate_browsable_path` normalizes and rejects null bytes but accepts any path under `/`; used by `POST /filebrowser/list` (`compresso/webserver/api_v2/filebrowser_api.py:105-118`).
- **What's wrong:** `current_path: "/etc"` or `/root/.ssh` enumerates any readable directory in the container and all mounted host paths. Combined with E1, an unauthenticated LAN client can map the NAS filesystem. Containment patterns already exist in `compresso/webserver/downloads.py:102-123` and `preview_api.py:69-95` — this endpoint just doesn't use them.
- **Impact:** Major · **Fix:** Constrain to configured library roots plus an explicit browse-root setting, reusing the existing containment helpers; at minimum require auth for this route. · **Effort:** M.

**E3. Container init sources plugin/user shell scripts as root at startup — Major**
- **Where:** `docker/root/etc/cont-init.d/60-custom-setup-script` — `source /config/startup.sh` executed by the root-running init stage (the app itself then drops to the PUID user via `docker/root/etc/cont-init.d/10-init-user`, `20-permission-config`).
- **What's wrong:** Anything that can write `/config` (the app itself runs as the PUID user with ownership of `/config`) can stage a script that runs as root on next container start — a privilege-escalation chain from app compromise (e.g. via E1 + plugin install) to container root.
- **Impact:** Major · **Fix:** Run the custom setup hook as the PUID user (`s6-setuidgid`), or gate it behind an explicit env opt-in and refuse scripts not owned by root. · **Effort:** M.

**E4. Tornado `debug=True` serves tracebacks (cross-ref B2) — Major**
- See B2 (`compresso/libs/uiserver.py:61`, `base_api_handler.py:323-328`). Counted once in the improvement list but weighed in both grades.

### Positives (verified)
- Strict CSP: `script-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, no unsafe-inline/eval for scripts (`security_headers.py:50-64`); full security-header set incl. nosniff, X-Frame-Options DENY, Referrer-Policy, Permissions-Policy, conditional HSTS (`:23-40`).
- Remote plugin installs require a valid `package_sha256` digest and verify it streamingly (`plugins.py:487-498`); archives are size-capped, member-validated, extracted to staging with rollback and 0600/0700 modes (`plugins.py:600-680`).
- Websocket: origin validation (`websocket.py:119`), auth during `prepare()` with the credential in a separate non-echoed subprotocol (`:122-128`).
- No `shell=True`, no `os.system` in source; ffmpeg invocations are list-based.
- All third-party GitHub Actions pinned to full commit SHAs across all 9 workflows; no `pull_request_target` checkout-of-PR-head patterns found.
- `.trivyignore` suppressions each carry written justifications (see F1 for the expiry gap).

---

## F — Dependencies & Tech Currency — A-

**Why this grade:** This is the strongest category, verified end-to-end: hash-locked reproducible Python installs (`requirements.lock` with 588 sha256 hashes, `requirements-dev.lock` with 1,133; CI installs with `--require-hashes` and a lock-drift check via `scripts/check-requirements-locks.sh`), pip-audit on both locks in CI, Trivy + cosign + SBOM in the release path, Dependabot across all five ecosystems, digest-pinned Docker bases with a weekly rebuild, and a current toolchain (Python 3.13 everywhere, Node 24 LTS, Vue 3.5 / Quasar 2.21 / Vite 7 / Vitest 4, tornado 6.5.7 / peewee current, actions/checkout v7 etc.). The findings are process refinements, not staleness.

### Findings

**F1. `.trivyignore`: 93 suppressed CVEs, no expiry dates, one duplicate — Moderate**
- **Where:** `.trivyignore` (93 non-comment lines, 92 unique; `CVE-2026-43185` appears at lines 84 and 108).
- **What's wrong:** All suppressions are open-ended; ~85 are base-image entries that are *supposed* to clear on the next weekly rebuild, but nothing forces re-review if they don't. The rationale comments are good.
- **Impact:** Moderate · **Fix:** Add `exp:` dates (30–60 days for base-image entries); delete the duplicate. · **Effort:** S · **Grade lift:** F A- → A with F2.

**F2. Manual CVE hot-patching in the app Dockerfile signals base-image digest lag — Moderate**
- **Where:** `docker/Dockerfile:5` (hand-pinned base digest), `:10-17` (apt upgrade of `linux-libc-dev` for CVE-2026-43185), `:26-45` (in-place `npm pack`/tar overwrite of `picomatch`/`sigstore` inside Node's bundled npm — fragile, silently no-ops if paths move).
- **What's wrong:** The base rebuilds weekly (`.github/workflows/docker_base_image.yml:10-12`), but the digest in `Dockerfile:5` is updated manually, so ad-hoc patches accumulate and must be remembered and removed by hand.
- **Impact:** Moderate · **Fix:** Have the base-image workflow open an automated PR bumping the digest after each successful rebuild; drop the patch blocks once absorbed. · **Effort:** M.

**F3. Unmaintained frontend runtime parsers handling user-facing markup — Moderate**
- **Where:** `compresso/webserver/frontend/package.json:30-31,38` — `remarkable ^2.0.1` (last release ~2019), `remarkable-admonitions ^0.2.2`, `xbbcode-parser ^0.3.1` (~2014-era); used in `src/js/markupParser.js:1-5`.
- **What's wrong:** Parser bugs/ReDoS in these will never get upstream fixes. Mitigated by DOMPurify sanitization downstream (with tests in `src/js/__tests__/sanitize.test.js`), so exposure is bounded.
- **Impact:** Moderate · **Fix:** Migrate to `markdown-it` (+ admonition plugin); vendor-and-own or replace the tiny bbcode parser. · **Effort:** M.

**F4. `vuex` declared but never imported (cross-ref C2) — Minor**
- **Where:** `compresso/webserver/frontend/package.json:37`; zero imports repo-wide; stale `stores/` alias at `quasar.config.js:76-84`.
- **Impact:** Minor · **Fix:** `npm uninstall vuex`; drop the alias. · **Effort:** S.

**F5. Stale intermediate `webserver` npm package — Minor**
- **Where:** `compresso/webserver/package.json:17` — `"node": ">=14.17.2"` (Node 14 EOL since 2023, contradicting `.nvmrc` = 24); `package-lock.json` still lockfileVersion 2; lone dep `vendor-copy` is dormant upstream.
- **Impact:** Minor · **Fix:** Bump engines, re-lock with modern npm, or replace `vendor-copy` with a 3-line `fs.cpSync` script. · **Effort:** S.

### Positives
- CVE-driven pins documented inline (`requirements.txt:10-13` urllib3, `:24-25` click); cross-platform hash markers handled thoughtfully in the locks.
- Dependabot: pip + all three npm roots + actions + docker, weekly, with grouping for pip/npm (`.github/dependabot.yml`). (Nit: no grouping for actions; docker only monthly.)
- No vendored third-party code in the tree; Swagger UI assets come from the lock-tracked `swagger-ui-py` package.

---

## G — Performance & Scalability — C+

**Why this grade:** The persistence layer and scan enumeration are genuinely designed for scale — WAL + single-writer queue, purposeful indexes matched to hot queries, streamed `os.walk` with a bounded test queue and resume checkpoints, keyset-paginated startup recovery, bounded in-memory buffers, enforced API pagination. But the web layer undoes much of it by running every DB and file operation on the single IOLoop thread, the per-file scan flow pays its most expensive checks first, and the CI scale benchmark measures a synthetic path that bypasses all of the real cost centers.

### Findings

**G1. All DB and file I/O in the web layer runs synchronously on the single IOLoop — Major**
- **Where:** `compresso/webserver/api_v2/base_api_handler.py:373-381` (handlers are `async def` with 100% sync bodies); e.g. `pending_api.py:245-268`; all six websocket stream loops (`compresso/webserver/websocket.py:476-620`). Writes through `SqliteQueueDatabase` block the calling thread up to `results_timeout=15.0` s (`compresso/libs/unmodels/lib/basemodel.py:144`). Only a few newer endpoints offload via `asyncio.to_thread` (`transfer_api.py`, `upload_api.py`, `plugin_repos_mixin.py`).
- **Impact at scale:** During a 100k-file scan the writer queue saturates; any UI write stalls the IOLoop for seconds, freezing every client's websocket streams and API calls; a bulk delete can block the whole web server for minutes (see G6).
- **Impact:** Major · **Fix:** Route handler bodies through `asyncio.to_thread` via a decorator on `_invoke_route`; move websocket data collection off-loop. · **Effort:** M · **Grade lift:** G1+G2 lift G from C+ to ~B.

**G2. Per-file scan flow: a DB fetch and often an ffprobe fork per file, ordered before the cheap checks — Major**
- **Where:** `compresso/libs/filetest.py:109-146` (codec pre-filter probes), `:150-167` (near-free `.compressoignore` and indexed history checks run *after* the probe); `Library(self.library_id)` constructed per file (`compresso/libs/library.py:277` — a DB query); two plugin-list DB queries per queued file (`compresso/libs/plugins.py:1197-1208` fired from `filetest.py:272-280`, `taskhandler.py:358-367`).
- **Impact at scale:** 100k files ⇒ ~100k library lookups + up to 100k ffprobe spawns (50–200 ms each ⇒ hours) + hundreds of thousands of sqliteq round trips, concurrent with UI traffic (G1).
- **Impact:** Major · **Fix:** Hoist `Library(...)` and codec parsing into `FileTest.__init__`; reorder checks ignore → history → probe → plugins; TTL-cache the enabled-event-plugin list. · **Effort:** S (hoist/reorder) + M (caching).

**G3. The "large library scale" CI benchmark does not exercise the real code path — Moderate**
- **Where:** `.github/workflows/large_library_scale.yml` + `compresso/libs/library_scale_benchmark.py:61-135` — synthetic `os.walk` iterable inserting rows via raw `sqlite3.executemany` into a hand-rolled schema; no peewee, no `SqliteQueueDatabase`, no FileTest, no dedupe SELECT. PR runs use only the 10k tier; `filetest.py`/`taskhandler.py`/`unmodels/**` aren't even in the workflow's `paths:` filter.
- **What's wrong:** The green "500k in <600s" signal says nothing about real scan throughput; regressions in the actual hot path are invisible.
- **Impact:** Moderate (false confidence) · **Fix:** Add a tier driving `TaskHandler.add_path_to_task_queue`/`FileTest` against a temp DB via the real models (ffprobe stubbed); extend the path filter. · **Effort:** M.

**G4. Daemon threads re-derive full plugin/library configuration from DB and disk every 1–2 s — Moderate**
- **Where:** Foreman loop → `get_current_library_configuration` (`compresso/libs/foreman.py:113-153, 893-908`) — all libraries, then per-library enabled plugins *with settings* (module/JSON loads via `library.py:599-617`), JSON-serialized and MD5-hashed every ~2 s; PostProcessor validates config every 1 s (`postprocessor.py:132-135`); EventMonitor per-library loop every ~2.5 s (`eventmonitor.py:139-186`); `get_incompatible_enabled_plugins` (`plugins.py:1097-1140`) polled independently by three threads.
- **Impact:** Moderate (steady-state idle load growing linearly with libraries × plugins) · **Fix:** Config-generation counter bumped by settings writes; rebuild/hash only on change; share one TTL-cached incompatibility result. · **Effort:** M.

**G5. Websocket: per-connection polling; system-logs stream re-reads the whole log file every second — Moderate**
- **Where:** `compresso/webserver/websocket.py:79-94` (intervals), `:484-496` + `compresso/config.py:372-384` (`read_system_logs` does `f.readlines()` on the full 10 MB-rotated log per second per client); pending/completed loops run ~5 queries per 3 s tick per client (`webserver/helpers/pending_tasks.py:127-143`, `helpers/completed_tasks.py:88-102`); dedup still `json.dumps(sort_keys=True)` on every poll (`websocket.py:414-453`).
- **Impact:** Moderate (5 dashboard clients ⇒ ~50 MB/s log reads + dozens of COUNTs/s on a 100k-row table, all on the IOLoop) · **Fix:** Compute each stream once in a shared periodic task and fan out; track log file offsets. · **Effort:** M.

**G6. Bulk deletes are N+1 row-at-a-time; "select all filtered" loads every ID into memory — Moderate**
- **Where:** `compresso/libs/task.py:428-459` (`delete_instance(recursive=True)` per row + per-row filesystem checks), `compresso/libs/history.py:232-257` (same), `webserver/helpers/pending_tasks.py:173-200` (unbounded ID query, Python-side exclusion), invoked from `pending_api.py:245-268` on the IOLoop.
- **Impact:** Moderate ("delete all pending" at 100k tasks ⇒ 200k+ serialized write-queue ops, minutes-plus with the UI frozen per G1) · **Fix:** Chunked `DELETE ... WHERE id IN (...)` per child table then parent; pre-fetch paths for cleanup; run off-loop. · **Effort:** M.

**G7. Scanner/tester handshake: 2 s idle sleeps + per-directory barrier — Moderate**
- **Where:** `compresso/libs/filetest.py:239-247` (`queue.Empty → self.event.wait(2)`), `compresso/libs/libraryscanner.py:359-366` (scanner won't feed the next directory until the current fully drains), drain spin at `:342-344`.
- **Impact:** Moderate (many-small-directory libraries — typical TV — can accrue up to ~2 s of pure sleep per directory boundary) · **Fix:** Blocking `Queue.get(timeout=0.25)` in testers; or checkpoint every N files. · **Effort:** S.

Also noted (Minor): Foreman materializes the full processed-task list every 2 s just to count it (`foreman.py:544`, unbounded query at `taskqueue.py:105-130`); `model_to_dict(backrefs=True)` on history detail pulls entire ffmpeg command logs (`basemodel.py:230-237` via `history.py:214-230`); sqliteq pragmas omit `synchronous=NORMAL`/`busy_timeout` that the benchmark itself sets (`basemodel.py:140-150` vs `library_scale_benchmark.py:64-66`).

### Positives
- WAL + single-writer queue eliminates cross-thread lock storms by design (`basemodel.py:138-153`).
- Purposeful indexes matched to hot queries: `tasks(status, priority)` (migration 007), `completedtasks(abspath, task_success)` (migration 009) with `.exists()`-based history checks (`history.py:205-212`).
- Streamed scan: `os.walk` generator + bounded queue (500) + resume checkpoints (`libraryscanner.py:231-235,342`, `scan_checkpoint.py`) — flat memory at 500k entries.
- Keyset-paginated startup recovery in batches of 500 (`taskhandler.py:279-284`); bounded deques for worker logs/GPU history; enforced 0–1000 API page caps (`task.py:382-383`).
- Bulk single-statement updates where implemented: `reorder_tasks`/`set_tasks_status` (`task.py:487-506`).

---

## H — Documentation & Onboarding — B+

**Why this grade:** For a project of this size the documentation is unusually complete and, more importantly, *live*: 17 docs totaling ~2,600 lines including a real 1,000-line plugin-authoring guide, genuine architecture notes, env-var reference tables, and a two-path onboarding (Docker and venv) that works; a real OpenAPI spec generated from code (apispec + Marshmallow, `compresso/webserver/api_v2/schema/swagger.py:84`) served via Swagger UI at `/compresso/swagger` (`compresso/libs/uiserver.py:328-335`); an auto-maintained CHANGELOG current to today; and machine-enforced license consistency (`scripts/check-license-consistency.sh`). Held below A- by patchy docstrings exactly where the code is hardest, plus fork-era drift, including a doc that actively misinforms (AGENTS.md, counted under C2).

### Findings

**H1. Docstring coverage is thinnest in the most complex orchestration modules — Moderate**
- **Where:** (AST-sampled) `compresso/libs/library.py` 10/44 functions docstringed, `compresso/libs/uiserver.py` 2/14, `compresso/libs/foreman.py` 21/42, `compresso/libs/postprocessor.py` 24/47 — vs `compresso/webserver/api_v2/approval_api.py` 6/6 and `compresso/config.py` 56/73. Many existing docstrings are empty `:return:` stubs.
- **Impact:** Moderate · **Fix:** Docstring the public methods of these four modules; optionally enable ruff `D1xx` for new files. · **Effort:** M · **Grade lift:** H B+ → A-.

**H2. Vendored frontend docs contradict root docs; fork leftovers — Moderate**
- **Where:** `compresso/webserver/frontend/README.md:16` claims Node 22 baseline vs Node 24 in root `README.md`/`docs/DEVELOPING.md`; `frontend/README.md:5` links to nonexistent `github.com/Compresso/compresso`; `frontend/.env.example:1` still says "Unmanic Frontend"; `AGENTS.md` documents a Vuex store that does not exist (see C2).
- **Impact:** Moderate (misleads humans and coding agents) · **Fix:** One alignment pass. · **Effort:** S.

**H3. Frontend hot-reload workflow undocumented in the main dev guide — Minor**
- **Where:** `docs/DEVELOPING.md` (frontend section) documents only ci/test/lint/build; the actual dev loop (`quasar dev` on :8889 proxying to the backend via `COMPRESSO_BACKEND_URL`, `compresso/webserver/frontend/quasar.config.js:89-104`) is only discoverable in the frontend dir.
- **Impact:** Minor · **Fix:** Add a "Frontend dev server" subsection with the two-terminal workflow. · **Effort:** S.

**H4. Small metadata/template drift — Minor**
- **Where:** `setup.cfg:3` (`license = GPLv3`) vs `setup.py:230` (`GPL-3.0-only`), and `scripts/check-license-consistency.sh:19` doesn't check `setup.cfg`; duplicate issue/PR templates in `docs/` vs `.github/` (the `docs/` copies, still referenced from `docs/CONTRIBUTING.md:18`, silently drift); seven internal AI-audit reports committed under `.Codex/` (only `.codex_tmp/` is gitignored).
- **Impact:** Minor · **Fix:** Align `setup.cfg`, extend the check script, delete the duplicate templates, relocate/ignore `.Codex/`. · **Effort:** S.

### Positives
- `docs/PLUGIN_DEVELOPMENT.md` (1,000 lines, 43 sections) is a real authoring guide; `docs/CONFIGURATION.md` has full env-var/volume/port tables; `docs/ARCHITECTURE.md` genuinely explains queue states and the approval lifecycle; a 20 TB rollout runbook and `SECURITY_SUPPLY_CHAIN.md` exist.
- OpenAPI schema is generated from code, committed (`compresso/webserver/docs/api_schema_v2.{json,yaml}`), auto-regenerated in dev mode (`uiserver.py:313-324`), and served via Swagger UI.
- README includes working Docker quick start, source install, three real screenshots, and troubleshooting.
- License consistency is machine-enforced across LICENSE / LICENSES/MIT.txt / THIRD_PARTY_NOTICES.md / package metadata.

---

## I — Developer Experience & Tooling — A-

**Why this grade:** The standout is `scripts/verify-local.sh` — fast/full lanes covering pip-audit, lock drift, lint, type-check, tests, frontend gates, actionlint, clean-wheel inspection, and Playwright — with `.github/workflows/verify-local.yml` running *the same script* in CI so local and CI cannot diverge. Add SHA-pin enforcement (`scripts/check-action-pins.sh`), hash-locked dependency drift checks, 3-way test sharding with lockfile-keyed caches, two-layer Docker builds (app layer ~1-2 min vs ~10-15), semantic-release + commitlint, shareable IDE run configurations, and pre-commit with ruff/mypy. The findings are polish items.

### Findings

**I1. `.test_durations` shard data stale with no refresh process (cross-ref D3) — Moderate**
- **Where:** `.test_durations` (303 KB), last regenerated 2026-04-07; no workflow runs `--store-durations`; no doc mentions refreshing it.
- **Impact:** Moderate (CI wall time) · **Fix:** Scheduled monthly regeneration workflow. · **Effort:** S.

**I2. Machine-local and personal files committed under `.idea/` — Minor**
- **Where:** `.idea/dataSources.local.xml` (JetBrains machine-local file referencing a local SQLite DB and `<secret-storage>master_key</secret-storage>`) and `.idea/dictionaries/josh5.xml` (previous maintainer's personal dictionary — fork residue). `.gitignore:4` excludes only `workspace.xml`. The rest of `.idea/` (run configs, code styles, inspection profiles) is legitimately shareable.
- **Impact:** Minor · **Fix:** `git rm` both; add them to `.gitignore`. · **Effort:** S.

**I3. `.editorconfig` contradicts the pre-commit EOF hook — Minor**
- **Where:** `.editorconfig:8` sets `insert_final_newline = false` while `.pre-commit-config.yaml:7` runs `end-of-file-fixer`, which adds one — a churn loop for editorconfig-aware editors.
- **Impact:** Minor · **Fix:** Set `insert_final_newline = true`. · **Effort:** S.

**I4. Pre-commit mypy runs full-repo per commit in an env that differs from CI's mypy — Minor**
- **Where:** `.pre-commit-config.yaml:18-25` — `mirrors-mypy` with `pass_filenames: false, always_run: true` (whole-repo check per commit, isolated env without project deps, diverging from `scripts/verify-local.sh:56`'s venv mypy).
- **Impact:** Minor · **Fix:** Convert to a `repo: local` hook using the venv mypy, or move to pre-push stage. · **Effort:** S.

Also noted (Minor): no top-level Makefile/justfile mapping single gates (`lint`/`test`/`fe-dev`) to the commands buried in `verify-local.sh` and nine `devops/` scripts; dead `devops/gitlab-runner.sh` and 2020-era fork headers mislead newcomers about which tooling is live; no dev-mode docker-compose variant (the `run_docker.sh --debug` path covers it).

### Positives
- `verify-local.sh` fast/full lanes enforced by CI itself (`verify-local.yml`) — local/CI parity by construction, with skipped full gates explicitly listed.
- Reproducibility rails: `.nvmrc` + `.python-version` + hash-locked requirements + lock-drift and action-pin check scripts.
- Release engineering: immutable-candidate release flow (`release.yml`), recovery workflow (`recover_release.yml`), locked release tooling with its own tests (`.github/release/tests/prepare-candidate.test.mjs`), per-release SBOM.
- Frontend DX: full npm script set incl. mocked and live-backend Playwright lanes; hot reload with websocket-aware proxying.

---

## Complete improvement register (ordered by impact, then grade lift, then effort)

| # | ID | Impact | Effort | Where (primary) | What | Lift |
|---|----|--------|--------|------------------|------|------|
| 1 | E1 | Major | S–M | `compresso/config.py:156-158` | Auth + CSRF disabled by default; no login layer | E C+→B+ (with E2) |
| 2 | B1 | Major | S–M | `compresso/libs/postprocessor.py:749` | `keep_both` calls nonexistent method; original file silently replaced | B C+→B (with B3/B7) |
| 3 | B2/E4 | Major | S | `compresso/libs/uiserver.py:61` | `debug=True` serves tracebacks to API clients | B and E |
| 4 | D1 | Major | S | `.github/workflows/python_lint_and_run_unit_tests.yml:140` | 75% coverage gate skipped on `pull_request` | D B→B+ (with D3) |
| 5 | G1 | Major | M | `compresso/webserver/api_v2/base_api_handler.py:373-381` | All web-layer DB/file I/O blocks the single IOLoop | G C+→B (with G2) |
| 6 | E2 | Major | M | `compresso/webserver/helpers/filebrowser.py:43-57` | File browser exposes entire filesystem | with E1 |
| 7 | B3 | Major | S | `compresso/libs/task.py:709-762` | Manager-proxy mutations silently lost | with B1 |
| 8 | G2 | Major | S–M | `compresso/libs/filetest.py:109-167` | Per-file DB fetch + ffprobe before cheap checks | with G1 |
| 9 | E3 | Major | M | `docker/root/etc/cont-init.d/60-custom-setup-script` | `/config/startup.sh` sourced as root at container start | E |
| 10 | A1 | Major | L | `compresso/libs/singleton.py:37-47` | Singleton wiring; silent arg-dropping constructor | A B-→B (with A2) |
| 11 | A2 | Major | M | `compresso/libs/uiserver.py:48` et al. | `libs/`→`webserver/` layering inversion | with A1 |
| 12 | C1 | Major | M–L | `src/pages/ApprovalQueue.vue` (1,159 lines) et al. | Eight 700–1,250-line monolith components | C C+→B- (with C2) |
| 13 | C2 | Major | M | `src/js/compressoGlobals.js`, `package.json:37` | Ad-hoc global state; unused Vuex; AGENTS.md misdescribes it | with C1 |
| 14 | B6 | Moderate | S | `compresso/config.py:556-586` et al. | Env-var booleans truthy — `"false"` enables features | B |
| 15 | B4 | Moderate | S–M | `compresso/libs/taskqueue.py:247-266` | Non-atomic task claim → duplicate assignment window | B |
| 16 | B5 | Moderate | M | `compresso/libs/foreman.py:563-657` | Worker registry mutated by two threads without locks | B |
| 17 | D3/I1 | Moderate | S | `.test_durations` | Stale shard timings degrade CI wall time | D/I |
| 18 | D2 | Moderate | L | `tests/integration/` (21 tests) | Mock-heavy suite blind to integration bugs (proved by B1/B3) | D B→B+/A- |
| 19 | G3 | Moderate | M | `compresso/libs/library_scale_benchmark.py:61-135` | Scale benchmark bypasses the real code path | G |
| 20 | B7 | Moderate | S | `compresso/libs/workers.py:573-574` | Failed runner reported as successful | B |
| 21 | D4 | Moderate | S–M | `tests/integration/test_taskhandler.py:86-298` | Fixed sleeps + shared class state (flaky by design) | D |
| 22 | G5 | Moderate | M | `compresso/webserver/websocket.py:484-496` | Per-client polling; full log re-read each second | G |
| 23 | G4 | Moderate | M | `compresso/libs/foreman.py:113-153` | Full config re-derivation from DB every 1–2 s | G |
| 24 | G6 | Moderate | M | `compresso/libs/task.py:428-459` | N+1 recursive bulk deletes on the IOLoop | G |
| 25 | G7 | Moderate | S | `compresso/libs/filetest.py:239-247` | 2 s idle sleeps + per-directory scan barrier | G |
| 26 | D5 | Moderate | M | `frontend/vitest.config.js:17-24` | 24% frontend coverage floor, ratchet not yet enforced | D |
| 27 | F1 | Moderate | S | `.trivyignore` | 93 open-ended CVE suppressions, one duplicate | F A-→A |
| 28 | F2 | Moderate | M | `docker/Dockerfile:5-45` | Manual base-digest bumps force ad-hoc CVE patches | F |
| 29 | F3 | Moderate | M | `frontend/package.json:30-38` | Unmaintained markup parsers (remarkable, xbbcode) | F |
| 30 | C3 | Moderate | S | `src/js/compressoWebsocket.js:335` | Unguarded `JSON.parse` in message handler | C |
| 31 | C4 | Moderate | S | `src/boot/axios.js:86` | `$api` instance pointing at `api.example.com` | C |
| 32 | C5 | Moderate | S | `src/pages/ApprovalQueue.vue:831-833` | Silent catches; argument-less `reject()` | C |
| 33 | A3 | Moderate | L | `compresso/libs/installation_link.py` (1,459 lines) | God modules at highest-churn points | A |
| 34 | A4 | Moderate | M | `compresso/libs/unplugins/executor.py:135-240` | Global `sys.path` mutation; substring module reload | A |
| 35 | H1 | Moderate | M | `compresso/libs/{library,uiserver,foreman,postprocessor}.py` | Docstrings thinnest in the hardest modules | H B+→A- |
| 36 | H2 | Moderate | S | `frontend/README.md`, `AGENTS.md` | Frontend docs contradict root docs; fork leftovers | H |
| 37 | B8 | Minor | S | `compresso/libs/postprocessor.py:209-743` | Mislabeled catch-alls; dead branch; slow drain | B |
| 38 | B9 | Minor | S | `compresso/libs/workers.py:661` | Substring path guards on recursive deletes | B |
| 39 | D6 | Minor | S | `requirements-dev.txt` | No pytest-timeout; no clock control | D |
| 40 | I2 | Minor | S | `.idea/dataSources.local.xml` | Machine-local/personal IDE files in VCS | I |
| 41 | C6/C7, F4/F5, H3/H4, I3/I4 | Minor | S | various (see sections) | Dead templates, unused vuex, doc/tooling polish | small |

---

## Closing note

The overall B- is a *defect* grade, not a *neglect* grade. The infrastructure around this code — locking, pinning, gating, releasing, documenting — is in the top decile of open-source projects this size, and the crash-safety engineering inside the postprocessor is genuinely rare. What separates it from a B+/A- codebase is concentrated in a short list: turn the existing security machinery on by default (E1/E2/E3), fix the three verified Major backend bugs that mocks can't see (B1/B2/B3), close the coverage-gate hole that lets exactly those bugs through (D1/D2), and stop blocking the event loop (G1/G2). Every one of those has its fix pattern already present somewhere else in the same codebase — the work is applying the project's own best practices uniformly.
