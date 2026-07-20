# Codebase Grade Report

**Project:** Compresso

**Audited:** 2026-07-20

**Baseline:** `master` at `f3f566a` (`v1.17.0`), audited on branch `claude/codebase-audit-grading-15a5em`

**Stack:** Python 3.13, Tornado, Peewee/SQLite, Vue 3.5, Quasar 2.21/Vite 7, pytest, Vitest, Playwright, GitHub Actions

**Method:** Nine parallel category audits, followed by manual verification of the highest-impact claims — each Major *code* finding was re-read at the cited lines before inclusion. Code findings cite file:line evidence; module-level findings (e.g. A4) cite the files/packages concerned, and repo-wide metrics (B3's type-hint coverage, H4's docstring coverage) are AST-computed aggregates reproducible from the stated scope rather than single line ranges. Security was reviewed directly against `request_auth.py`, `security_headers.py`, `downloads.py`, `proxy.py`, `websocket.py`, the plugin install/execution chain, rate limiting, and `.trivyignore`. No source code was modified. Grades are calibrated (A = exemplary, C = average working code) with Security and Testing weighted double in the overall grade.

**Prior audit:** 2026-07-12 against `v1.13.2` graded the repo **B-** overall; 33 of its 37 items were completed. This audit confirms the improvement is real: Testing rose B → A-, Security C+ → B+, Performance C+ → B+, Dependencies B → A-, Docs C+ → B+, Tooling B → A. Of the prior audit's four open items, **A3** (split large orchestration modules) and **E4** (plugin isolation) remain partially open and are folded into A6/C1 and the Security strengths below; the prior report's **I2/I3** (release-convention enforcement, duplicate master-push validation) were not re-examined in depth; they remain open but are excluded from section I's grading. Note that all finding IDs in this report are issued fresh for the 2026-07-20 baseline — the I2/I3 findings in section I below are new items, unrelated to the prior report's I2/I3.

## Summary

| ID | Category | Grade | Prior (07-12) | Items |
|----|----------|-------|----------------|-------|
| A | Architecture & Design | **B-** | B- | 7 |
| B | Backend Quality | **B+** | B | 7 |
| C | Frontend Quality | **B-** | C | 8 |
| D | Testing & Reliability | **A-** | B | 6 |
| E | Security | **B+** | C+ | 5 |
| F | Dependencies & Tech Currency | **A-** | B | 5 |
| G | Performance & Scalability | **B+** | C+ | 7 |
| H | Documentation & Onboarding | **B+** | C+ | 6 |
| I | Developer Experience & Tooling | **A** | B | 3 |
| **Overall** (D & E double-weighted) | | **B+** | B- | **54** |

**Top 5 highest-leverage improvements:** B1, G2, G1, E1, C1 (details at the end).

---

## A — Architecture & Design — B-

A mature, deliberately-hardened Unmanic fork with genuinely good bones — a startup readiness state machine, crash-recovery journal, schema-validated v2 API, and cleanly deprecated v1 — but it still carries the ancestor's structural debt: a service-locator built on ~14 singletons, a libs↔webserver layering inversion held together by deferred imports, a reflection-based API router, an 883-line god-object `Config`, and a ~2,900-line dead abstraction (`unffmpeg`). Above "average working code" on engineering rigor; held back from B+ by coupling and global state.

### A1 — Service-locator singletons hand live `threading.Thread` objects to HTTP handlers

- **Where:** `compresso/libs/uiserver.py:69-92` (`CompressoDataQueues` / `CompressoRunningThreads` singletons, populated at `uiserver.py:116-119`); consumers at `compresso/webserver/api_v2/workers_api.py:84-86`, `compresso/webserver/websocket.py:111-113`, `compresso/webserver/helpers/workers.py:42-43` (pattern repeated six times); 14 classes use `SingletonType` (`config.py:73`, `libs/plugins.py:77`, `libs/session.py:40`, `libs/installation_link.py:53`, `libs/startup.py:23`, `webserver/downloads.py:45`, …)
- **What's wrong:** API handlers call methods directly on the live `Foreman` thread fetched from an untyped global dict (`foreman.pause_worker_thread(...)`). There is no interface between HTTP and the orchestrator; handlers are coupled to Foreman's internal registry/locking discipline, and tests must construct half-initialized `Foreman` objects (acknowledged at `foreman.py:55-57`). This is the central coupling mechanism of the whole app.
- **Impact:** Major
- **Fix:** Define a narrow `WorkerControl`/`SystemStatus` facade owned by `service.py`, inject it via Tornado `Application` settings, and have handlers use `self.application.settings` instead of `CompressoRunningThreads()`. Retire the two registry singletons.
- **Effort:** M
- **Grade lift:** B- → B+ (largest single architecture lever)

### A2 — Layering inversion: `libs/uiserver.py` is a webserver component living in `libs`

- **Where:** `compresso/libs/uiserver.py:48` (top-level `from compresso.webserver.downloads import DownloadsHandler`); deferred imports of five webserver modules inside `make_web_app()` (`uiserver.py:252,264,274,302,319`); reverse imports at `compresso/webserver/helpers/workers.py:32`, `webserver/websocket.py:49`, `webserver/api_v2/workers_api.py:32`, `webserver/api_v2/system_api.py:24`
- **What's wrong:** `libs` imports the presentation layer at module import time while five webserver modules import back into `libs.uiserver`. The cycle only avoids `ImportError` because most webserver imports are deferred — import order is load-bearing and invisible.
- **Impact:** Moderate
- **Fix:** Move `UIServer` and the registry classes into `compresso/webserver/` (`service.py` already owns construction, so only import paths change). Enforce direction with an import-linter contract (`libs` must not import `webserver`).
- **Effort:** S
- **Grade lift:** B- → B

### A3 — `Config` is an 883-line god-object that persists its own live `__dict__`

- **Where:** `compresso/config.py:223-229` (`get_config_as_dict()` returns the *live* `self.__dict__`), `config.py:300-302` (every instance attribute serialized to `settings.json`), `config.py:396-883` (~490 lines of hand-written getter/setter boilerplate); duplicated bool parsing at `config.py:799-801` and `config.py:848-850` despite `_as_bool` existing at `config.py:67`
- **What's wrong:** No settings schema. Any transient attribute assigned to the singleton leaks into `settings.json`; callers of `get_config_as_dict()` can mutate config state without persistence; every new setting requires editing four places.
- **Impact:** Moderate
- **Fix:** Introduce a declarative settings table (dataclass fields or a registry of `Setting(default, type, persist)`); serialize only registered keys; return a copy from `get_config_as_dict()`; route all bool getters through `_as_bool`.
- **Effort:** M
- **Grade lift:** B- → B

### A4 — `unffmpeg` is a ~2,900-line abstraction with exactly one live consumer

- **Where:** `compresso/libs/unffmpeg/` (2,944 lines across 12 container classes, 4 video-codec classes, audio/subtitle codecs, handles); sole product import verified at `compresso/libs/worker_capabilities.py:15` (uses only `Info.get_ffmpeg_video_encoders()` / hw-accel detection, `worker_capabilities.py:42-48`)
- **What's wrong:** Transcode command construction moved to the plugin system (`bundled_plugins/encoding_presets`), but the whole codec/container hierarchy remains, inflating the maintenance surface and misleading readers about where encoding decisions live. It also harbors the B1 correctness bug.
- **Impact:** Moderate
- **Fix:** Extract `Info`/`probe.py`/`lib/cli.py` into a small `libs/ffmpeg_info.py`; delete the container/codec class hierarchy (or move it into the encoding-presets plugin).
- **Effort:** S
- **Grade lift:** B- → B (cleanliness, not behavior)

### A5 — Reflection-based API routing recompiles regexes and dispatches stringly-typed per request

- **Where:** `compresso/webserver/api_request_router.py:74-83` (URL segments select modules via `importlib.import_module` + `getattr`); `compresso/webserver/api_v1/base_api_handler.py:59-97` (`action_route()` compiles `tornado.routing.PathMatches(...)` on every request at line 79, dispatches via `getattr(self, route.get("call_method"))()`); per-handler route dicts, e.g. `compresso/webserver/api_v2/pending_api.py:61-117`
- **What's wrong:** Tornado's native routing is bypassed twice; a `call_method` typo becomes a runtime `AttributeError`; regexes are recompiled per request; `ModuleNotFoundError` is used as control flow.
- **Impact:** Moderate
- **Fix:** At app build time, walk each handler's `routes` list once and register real Tornado URLSpecs with precompiled matchers; keep the dict format as the declaration source so Swagger tooling is untouched.
- **Effort:** M
- **Grade lift:** B- → B

### A6 — `Foreman` remains a 961-line multi-responsibility orchestrator

- **Where:** `compresso/libs/foreman.py:52-90` (constructor wires safety latch, dual pending queues, remote link managers, schedule state, config-hash tracking); `foreman.py:211-224` (minute-resolution string-compare scheduler: `if time_now == self.last_schedule_run: return` silently skips events if an iteration stalls past the minute); `foreman.py:728-751` (remote heartbeat), `foreman.py:826-916` (assignment algorithm)
- **What's wrong:** Local worker lifecycle, distributed dispatch, event scheduling, metrics, and queue-idle notifications all live in one class with one lock — which is why the API layer needs the raw object (A1). Successor to prior-audit item A3, still open.
- **Impact:** Moderate
- **Fix:** Extract `RemoteDispatcher` (heartbeat + link managers + remote queues) and `WorkerScheduler` (event schedules) as owned sub-objects; Foreman keeps local worker registry + assignment. Shrinks the facade needed for A1.
- **Effort:** L
- **Grade lift:** B → B+ (after A1)

### A7 — Pure polling threading model; the global shutdown `Event` doubles as a sleep timer

- **Where:** `compresso/libs/foreman.py:926-927` (`self.event.wait(2)` main tick), `compresso/libs/workers.py:104-120` (`event.wait(1)`/`wait(5)`/`wait(0.5)` pacing), `foreman.py:753-756` (0.5s wait per drained completed task), `compresso/service.py:486-489` (`time.sleep(1)` main loop)
- **What's wrong:** The process-wide shutdown event is reused everywhere as "sleep unless shutting down" — a *set* event turns every loop into a busy-spin until each thread notices its own flag — and task hand-off latency stacks poll intervals (2s + 1s) despite `queue.Queue` objects already existing (`foreman.py:72-74`).
- **Impact:** Minor–Moderate
- **Fix:** Blocking hand-off (`Queue.get(timeout=...)` or per-worker `Event`), per-concern events for pacing, drop the per-item drain wait.
- **Effort:** M
- **Grade lift:** B- → B-/B

**Strengths:** Startup lifecycle and crash recovery are well above hobby-fork grade — `service.py:103-113` verifies threads stay alive, `service.py:378-396` turns a dead critical thread into visible shutdown, `service.py:247-272` replays the file-operation journal before any worker claims work. The v2 API layer is genuinely well-structured (Marshmallow schemas per endpoint, auth/CSRF/rate-limit guards and offloaded route bodies in `api_v2/base_api_handler.py:53-135`, v1 as a clean deprecation shim stamping `Deprecation` headers). Plugin execution is process-isolated with real cleanup discipline (`libs/unplugins/child_process.py:44-80` locked PID registry; `service.py:409-420` atexit/autoreload wiring).

---

## B — Backend Quality — B+

A disciplined, defensively engineered backend: **zero** bare `except:` clauses in 245 files, narrow typed exception tuples, journaled crash-safe file operations, ruff with security/bugbear/complexity rules, and 64.7k lines of tests for 51.8k lines of code. Kept out of the A range by near-absent type hints (12.3% of functions), god functions behind `noqa: C901` waivers, an inherited correctness bug in `unffmpeg`, and the `Config` singleton (graded under A3).

**Metrics:** bare `except:`: 0; `except Exception`: 320 (top: `installation_link.py` 18, `postprocessor.py` 15); functions with any annotation: 210/1,707 (12.3%), files with any: 28/245; functions >100 lines: 22; largest files: `installation_link.py` 1,459, `postprocessor.py` 1,403, `plugins.py` 1,208; logger style: 200 lazy `%s` calls, 0 f-string calls; TODO/FIXME: 4.

### B1 — Wrong subprocess success check in unffmpeg CLI wrappers (false failures *and* missed failures)

- **Where:** `compresso/libs/unffmpeg/lib/cli.py:56` and `cli.py:81` — `if pipe.returncode == 1 or "error" in raw_output:` (verified; duplicated in both `ffmpeg_cmd` and `ffprobe_cmd`, with stdout+stderr merged at `cli.py:48`)
- **What's wrong:** Two bugs in one line: (a) only exit code `1` is treated as failure — ffmpeg/ffprobe exit codes 8, 69, 234, and negative signal-death codes are silently treated as success; (b) the substring test raises a false failure whenever "error" appears anywhere in legitimate output (e.g. a file path or encoder description containing the word). Probe results feed the whole pipeline.
- **Impact:** Major
- **Fix:** `if pipe.returncode != 0:` and drop the substring heuristic (or restrict it to ffprobe's `-show_error` JSON field). Add regression tests for non-1 exit codes and "error"-containing paths.
- **Effort:** S
- **Grade lift:** B+ → A- (with B2)

### B2 — Subprocess/pipe leak on exception path in worker command execution

- **Where:** `compresso/libs/workers.py:777-883` (`__exec_command_subprocess`): `Popen` at line 787; `terminate_proc()`/`unset_proc()` reached only on the normal path (lines 860-863); the handler at 879-883 logs and returns `False` with **no `finally`**
- **What's wrong:** If `sub_proc.stdout.readline()` (line 830) or `psutil.Process(...)` raises `OSError` mid-loop, the running ffmpeg is never terminated and the stdout pipe never closed; the orphaned encoder keeps consuming CPU/disk while the worker moves on. (The *outer* crash path `_fail_current_task_after_unexpected_error`, lines 217-236, does terminate — but exceptions here are caught locally and never reach it.)
- **Impact:** Moderate
- **Fix:** Wrap the post-Popen body in `try/finally` calling `terminate_proc()` + `unset_proc()` and closing `sub_proc.stdout`.
- **Effort:** S
- **Grade lift:** B+ → A- (with B1)

### B3 — Type hints essentially absent

- **Where:** AST-measured: 210 of 1,707 functions annotated (12.3%); 28 of 245 files contain any annotation. Zero annotations in `compresso/libs/postprocessor.py` (47 defs), `libs/task.py` (46 defs), `libs/metadata.py`, `libs/history.py`. mypy is configured (`pyproject.toml:53-67`) but has almost nothing to check.
- **What's wrong:** Dict-shaped payloads (`data`, `manager_info`, `task_data`) flow through dozens of functions with no contracts; several defensive `except (AttributeError, TypeError)` blocks exist precisely to paper over this.
- **Impact:** Moderate
- **Fix:** Annotate public interfaces of the ~15 central modules first (task, taskqueue, foreman, workers, postprocessor); introduce TypedDicts/dataclasses for the payload shapes.
- **Effort:** L
- **Grade lift:** B+ → A- over time

### B4 — God functions waived with `noqa: C901`

- **Where:** `compresso/libs/workers.py:347` (`__exec_worker_runners_on_set_task`, **281 lines**, nested closure thread launcher at line 457); `compresso/libs/libraryscanner.py:269` (`scan_library_path`, 200 lines, incl. the `double_check` polling hack at 369-389); `compresso/libs/postprocessor.py:851` (`post_process_file`, 173 lines); `compresso/libs/installation_link.py:505` (197 lines); 22 functions exceed 100 lines
- **What's wrong:** The most failure-prone paths in the system are the hardest to test in isolation.
- **Impact:** Moderate
- **Fix:** Extract the runner-pass loop into `_run_single_runner_pass()` (the file already demonstrates this style); replace the scan `double_check` poll with condition-based completion.
- **Effort:** M
- **Grade lift:** +⅓ grade

### B5 — Dead `DoesNotExist` handlers on lazy peewee selects, and a lost return value

- **Where:** `compresso/libs/history.py:76-79`, `compresso/libs/task.py:445-448` and `task.py:487-489` — `except Tasks.DoesNotExist:` around `.select()` chains that are lazy and never raise it (only `.get()` does); `delete_tasks_recursively` (task.py:452-489) falls through with an implicit `None` where the contract returns `True`/`False`
- **Impact:** Minor
- **Fix:** Delete the unreachable handlers; make the return explicit.
- **Effort:** S
- **Grade lift:** marginal

### B6 — Unlocked reads of `worker_threads` despite a documented lock protocol

- **Where:** `compresso/libs/foreman.py:53-58` documents `worker_registry_lock`; mutation sites honor it, but read paths iterate without it: `get_all_worker_status` (948-952), `get_worker_status` (954-961), `fetch_available_worker_ids` (508-514), `check_for_idle_workers` (516-521), `_check_queue_idle_transition` (812-814). Concurrent `del` at `foreman.py:270` can raise `RuntimeError: dictionary changed size during iteration` in an API thread.
- **Impact:** Minor
- **Fix:** Snapshot under the lock: `with self.worker_registry_lock: threads = list(self.worker_threads.values())`.
- **Effort:** S
- **Grade lift:** marginal

### B7 — Copy-paste duplication in `unffmpeg`

- **Where:** `compresso/libs/unffmpeg/info.py:66-106` vs `108-148` (~40 lines duplicated except "encoder"/"decoder"); `info.py:244-263` duplicates `get_all_supported_codecs_of_type("video")` (216-242); `lib/cli.py:39-61` vs `64-86` twins (unused `err` at 49/74)
- **What's wrong:** Bug-fix divergence risk — B1's bug already exists in two places.
- **Impact:** Minor
- **Fix:** One `_parse_codec_table(raw, kind)` helper; one `_media_tool_cmd(binary, params, exc_class)`. (Or resolve via A4 deletion.)
- **Effort:** S
- **Grade lift:** marginal

**Strengths:** Crash-safe journaled finalization (`postprocessor.py:60-74` explicit `FINALIZATION_PHASE_ORDER` state machine; `_postprocess_local_file_safely` at 616-643 resumes from a persisted journal; `service.py:246-272` replays on startup). Exception and subprocess hygiene enforced by tooling (ruff `S`, `B`, `SIM`, `T20`, `C90` enabled in `pyproject.toml:36`; the 54 swallow sites are nearly all narrow with justified `noqa` waivers, e.g. `gpu_monitor.py:51`). Thoughtful async web layer (`api_v2/base_api_handler.py:382-442` offloads sync bodies from the IOLoop; `handle_unhandled_error` at 295-315 gives clients opaque correlated error IDs).

---

## C — Frontend Quality — B-

A genuinely disciplined codebase for its class — modern pinned stack (Vue 3.5, Quasar 2.21, Vite 7, vitest 4, Playwright 1.61), real unit + e2e + accessibility testing, complete i18n coverage (~1,730 `t()` call sites, no hardcoded strings in the sampled 1,000-line components), and a proper composables layer. Held back by several 750–1,250-line monolith components, a plain-JS codebase with no TypeScript, a self-admitted ~24% coverage baseline, mixed Options/`<script setup>` styles, and ad-hoc global-singleton state.

**Metrics:** 88 Vue SFCs (25,245 lines); largest: `CompletedTasksListDialog.vue` 1,251 / `ApprovalQueue.vue` 1,095 / `VideoCompare.vue` 1,001 / `LibraryConfigDialog.vue` 855; 36 vitest unit files (6,160 lines) + 2 Playwright specs; 49 files `<script setup>` vs 34 Options-wrapper; no Pinia/Vuex — module-level `reactive()` singletons.

### C1 — Monolithic components (1,000+ lines, dialogs-within-dialogs)

- **Where:** `compresso/webserver/frontend/src/components/dashboard/completed/CompletedTasksListDialog.vue` (1,251 lines; nests four additional `q-dialog`s at lines 356, 419, 459); `src/pages/ApprovalQueue.vue` (1,095); `src/components/preview/VideoCompare.vue` (1,001); `LibraryConfigDialog.vue` (855)
- **What's wrong:** Single files own toolbar UI, sub-dialogs, selection logic, and API calls; these giants are exactly the files without component tests.
- **Impact:** Major
- **Fix:** Extract each nested `q-dialog` into `ui/dialogs/` components; move approve/reject flows into a composable like the existing `useApprovalQueueData.js`; add component tests as pieces are carved out (pairs with D1).
- **Effort:** M
- **Grade lift:** B- → B

### C2 — No TypeScript; typing is runtime-props only

- **Where:** `jsconfig.json` (not tsconfig); `eslint.config.mjs:64-77,89-101` (`@babel/eslint-parser`, `requireConfigFile: false`); coercion smells TS would catch, e.g. `ApprovalQueue.vue:833-834` (`=== true || === 'true'`); lint tier is only `vue/strongly-recommended` + prettier
- **Impact:** Moderate
- **Fix:** Incremental adoption — `allowJs` tsconfig + `vue-tsc` in CI, convert `src/js/` and `src/composables/` first; bump ESLint to `flat/recommended`.
- **Effort:** L
- **Grade lift:** B → B+/A- long-term

### C3 — Split personality: `<script setup>` vs Options-wrapper `setup()`

- **Where:** 49 vs 34 files; e.g. `ApprovalQueue.vue:630-633` (Options wrapper) beside `CompletedTasksListDialog.vue:496` (`<script setup>`) in the same feature area
- **Impact:** Moderate
- **Fix:** Migrate the 34 Options-wrapper files (mechanical — they already use Composition API inside `setup()`), then enable `vue/component-api-style: ['error', ['script-setup']]`.
- **Effort:** M
- **Grade lift:** B- → B (with C1)

### C4 — Ad-hoc global state; installation switch does `location.reload()`

- **Where:** `src/js/sharedLinksStore.js:24-29` (`setTarget()` → `localStorage.setItem` → `location.reload()`); `src/js/compressoGlobals.js:79` (`let $compresso = {}` mutable module singleton, stuffed with websocket listener registries by `compressoWebsocket.js`)
- **What's wrong:** Full-page reload as a state transition defeats SPA routing/state; the untyped `$compresso` bag is shared mutable state with no devtools visibility, while Quasar bundles Pinia support unused.
- **Impact:** Moderate
- **Fix:** Pinia stores for installation target, toast settings, and websocket connection state; make target switching re-fetch instead of reloading.
- **Effort:** M
- **Grade lift:** +⅓ grade in maintainability

### C5 — Auth retry via `window.prompt()` on the mutated global axios instance

- **Where:** `src/js/apiAuth.js:33-36` (`globalThis.prompt(promptText)`); wired at `src/boot/axios.js:64-78` (401 → prompt → retry); interceptors installed on the **global** axios default instance (lines 40, 64) which every page imports directly
- **What's wrong:** A blocking native prompt is poor UX/accessibility (no i18n, blocks the event loop) — especially since a proper `LoginDialog.vue` already exists (`src/components/drawers/partials/LoginDialog.vue`); mutating global axios leaks interceptors to any code sharing the module.
- **Impact:** Moderate
- **Fix:** Promise-based auth gate using the existing LoginDialog; one dedicated `axios.create()` app instance imported everywhere.
- **Effort:** M
- **Grade lift:** +⅓ grade (with C3)

### C6 — Coverage gate honest but very low

- **Where:** `compresso/webserver/frontend/vitest.config.js:17-24` — `thresholds: { lines: 24, functions: 16, branches: 17, statements: 24 }` ("Honest all-source baseline (2026-07-12). Ratchet upward…")
- **What's wrong:** Tests concentrate on `src/js/` and `src/composables/`; the five largest, riskiest components (C1) have no component tests. Cross-referenced as D1 — the ratchet is a comment, not a mechanism.
- **Impact:** Moderate
- **Fix:** See D1.
- **Effort:** M–L
- **Grade lift:** B- → B

### C7 — 11 unscoped `<style>` blocks leaking global CSS

- **Where:** 44/55 style blocks scoped; unscoped include `src/components/settings/plugins/partials/PluginsInstalledTable.vue:627`, `src/components/dashboard/completed/CompletedTaskLogDialog.vue:81`, `src/components/docs/HelpSupportDialog.vue:382`, `src/pages/SettingsPlugins.vue:68`, `src/components/FooterData.vue:65`, +6 more; plus a 604-line global `app.scss`
- **Impact:** Minor
- **Fix:** Add `scoped` + `:deep()` where global reach isn't required; enable `vue/enforce-style-attribute`.
- **Effort:** S
- **Grade lift:** hygiene

### C8 — Dead boilerplate axios instance with placeholder production URL

- **Where:** `src/boot/axios.js:86` — `const api = axios.create({ baseURL: 'https://api.example.com' })` (verified), injected as `$api` (line 95) and exported (line 101); zero consumers found in `src/`
- **Impact:** Minor
- **Fix:** Delete the scaffold instance, export, and comments (lines 80-97).
- **Effort:** S
- **Grade lift:** hygiene

**Strengths:** Layered test setup with accessibility scanning (36 colocated unit test files; axe-core audit at `tests/e2e/compresso-smoke.spec.js:405`; a live-backend Playwright config). Security-conscious API layer (`src/boot/axios.js:24-56` origin-checks every request before attaching auth/CSRF headers; `src/js/sanitize.js` wraps DOMPurify with an explicit allowlist; the auth token travels in WebSocket subprotocols, not query strings — `src/js/apiAuth.js:18-31`). Complete i18n discipline and 12 purpose-built composables, each with a matching test.

---

## D — Testing & Reliability — A-

An unusually mature test and reliability posture: ~4,000 backend tests with genuinely behavioral assertions, an enforced 75% combined-coverage gate, cross-OS PR shards, fail-closed fuzz tests for every persistence primitive, and real-filesystem integration tests of the data-loss-critical file-move path. Kept from A/A+ by the very low frontend coverage gate, a thin marked integration suite whose coverage is invisible in Sonar, and a stale test-durations file.

**Metrics:** ~4,036 Python tests on 3.13 (3,947 collected on the audit box's 3.11 with one env-only collection error); ~4,012 unit (175 files) vs **24 integration** (7 files); backend gate `fail_under = 75` (`pyproject.toml:25`) enforced in CI (`python_lint_and_run_unit_tests.yml:176`); frontend thresholds 24/16/17/24; 36 vitest files (~432 cases) + 2 Playwright specs.

### D1 — Frontend coverage gate is very low relative to backend rigor

- **Where:** `compresso/webserver/frontend/vitest.config.js:17-24` (24% lines / 16% functions vs backend 75%); only 6 of 15 pages in `src/pages/*.vue` have tests
- **What's wrong:** The "ratchet upward" is a comment, not a mechanism — nothing prevents it staying at 24% forever.
- **Impact:** Moderate
- **Fix:** CI step that fails if achieved coverage exceeds thresholds by >2 points without a threshold bump (auto-ratchet); component tests for the 9 untested pages, starting with the C1 extraction targets.
- **Effort:** M
- **Grade lift:** A- → A

### D2 — Marked integration suite is thin; its coverage is unenforced and invisible

- **Where:** `.github/workflows/integration_test_and_build_all_packages_ci.yml:112` (`--cov-fail-under=0`); `sonar-project.properties:27-30` (documented but unimplemented cross-workflow consolidation); 24 tests across 7 files (`test_service_startup.py` has 3, `test_distributed_process_drill.py` has 1)
- **Impact:** Moderate
- **Fix:** Compose the unit/integration workflows via `workflow_call` under one parent (the pattern already exists — `release.yml` calls both), merge coverage artifacts, and add integration tests for remote-worker lease/handoff and websocket push paths.
- **Effort:** M–L
- **Grade lift:** A- → A

### D3 — `.test_durations` is 2 months stale and covers ~62% of unit tests

- **Where:** `.test_durations` (2,483 entries spanning 105 files vs ~4,012 tests in 174 files; last touched `2026-05-20`); `refresh_test_durations.yml:9` (monthly cron whose output hasn't landed since May — the workflow exits silently on failure/unmerged PR)
- **Impact:** Minor
- **Fix:** `workflow_dispatch` the refresh now; add failure notification or auto-merge label so refresh PRs don't rot.
- **Effort:** S
- **Grade lift:** marginal

### D4 — E2E depth is one smoke spec per mode, with silent retry masking

- **Where:** `tests/e2e-live/compresso-live-smoke.spec.js` (94 lines — the only test of the real frontend↔backend contract); `playwright.config.js:11` (`retries: process.env.CI ? 2 : 0`, no flake reporting)
- **Impact:** Minor–Moderate
- **Fix:** Add 2-3 live journeys (settings save round-trip, approval action, history pagination); enable the JSON reporter and annotate when `retry > 0` occurred.
- **Effort:** M
- **Grade lift:** A- → A (with D1)

### D5 — Coverage-campaign test-file sprawl

- **Where:** five foreman files (`test_foreman.py`, `_deep`, `_extended`, `_queue_empty`, `_run_refactor`), plus `test_additional_api_coverage.py`, `test_api_deferred_coverage.py`, `test_config_round2.py`, a broad `*_extended.py` family. Sampled tests are real (drive Tornado handlers over HTTP, assert payloads) — organizational debt, not shallow testing.
- **Impact:** Minor
- **Fix:** Consolidate per-module; ban `*_coverage`/`*_round2` naming in a CONTRIBUTING note.
- **Effort:** M
- **Grade lift:** marginal

### D6 — `ThreadHealthMixin` has no dedicated unit test

- **Where:** `compresso/libs/thread_health.py:1-43` (the watchdog telemetry primitive); coverage only indirect via consumers (`tests/unit/test_scheduler.py:44,451-485`, `test_postprocessor.py:674-706`)
- **Impact:** Minor
- **Fix:** Direct suite including a concurrent hammer test.
- **Effort:** S
- **Grade lift:** marginal

**Strengths:** Data-loss invariants tested against the real filesystem with injected failure — `tests/integration/test_file_pipeline.py:153-187` injects `OSError` on the final rename and asserts byte-for-byte restoration of the destination, source survival, and cache retention. Fail-closed primitives each have adversarial suites (`test_safety_state.py:77-121` corrupt-state forcing pause; `test_20tb_state_fuzz.py` 200 seeded malformed-JSON iterations; `test_retry.py` 520 lines against a real SQLite DB). CI rigor: hash-locked deps, pip-audit, ruff+mypy blocking, 3-way shards × {ubuntu, macos, windows}, combined 75% gate, Docker runtime smoke test, and autouse fixtures that reap leaked threads/singletons (`tests/conftest.py:110-202`).

---

## E — Security — B+

Genuinely strong, deliberate security engineering for a self-hosted tool: auth and CSRF are force-enabled whenever the UI listens beyond loopback (with an auto-generated token persisted at mode 0600), token comparison is constant-time, the plugin supply chain is HTTPS-only with mandatory SHA-256 and one of the most thorough zip validators you'll see in this class of app, the remote-installation proxy is SSRF-guarded with header allowlists, and the backend contains zero `eval`/`exec`/`pickle`/`shell=True`. Remaining findings are defense-in-depth and secrets-at-rest hardening, not exposed defaults. (Prior audit: C+ — the E1/E2/E3/E5/E6 hardening from that round is verifiably in place.)

### E1 — WebSocket `prepare()` ignores `authorize_request`'s return value

- **Where:** `compresso/webserver/websocket.py:122-123` — `def prepare(self): authorize_request(self, allow_websocket_protocol=True)` (verified: return value unchecked); contrast HTTP handlers, e.g. `proxy.py:182-184` (`if not authorize_request(self): return`)
- **What's wrong:** Rejection relies on the side effect that `authorize_request` calls `handler.finish()` (`request_auth.py:83-85`), which aborts the handshake today because Tornado skips the upgrade after a finished response. Nothing in *this* handler enforces the auth decision; a refactor of `authorize_request` (e.g. returning without finishing) or of Tornado's prepare/upgrade sequencing silently opens every stream — workers, logs, task data — to unauthenticated clients. The socket also never re-checks auth after open despite long-lived connections.
- **Impact:** Moderate (defense-in-depth on the heaviest data-exposure surface)
- **Fix:** Check the return and raise `tornado.web.HTTPError(401)` when false; add a regression test asserting an unauthenticated websocket handshake is refused when `api_auth_enforced` is on.
- **Effort:** S
- **Grade lift:** B+ → A-

### E2 — Single static bearer token; remote-installation credentials plaintext at rest

- **Where:** `compresso/config.py:201-210` (auto-generated token persisted to `settings.json`); `config.py:302` (file written 0600 — good); `compresso/webserver/proxy.py:162-171` (remote basic-auth `username`/`password` and `api_token` read as plaintext from settings); `config.py:229` (`get_config_as_dict()` returns the live dict including `api_auth_token`, so any settings-dump surface must remember to redact)
- **What's wrong:** One long-lived shared token with no rotation or expiry; compromise means silent full API access until manually changed. Remote-worker credentials sit unencrypted in the same file, and the live-dict export makes accidental token disclosure a one-line mistake in any future settings endpoint.
- **Impact:** Moderate
- **Fix:** Add a token-rotation endpoint/CLI and creation timestamp; return a redacted copy from `get_config_as_dict()` by default (allowlist callers that need secrets); document credential scoping for remote links.
- **Effort:** M
- **Grade lift:** B+ → A- (with E1)

### E3 — CSRF cookie never sets the `Secure` flag

- **Where:** `compresso/webserver/api_v2/base_api_handler.py:162` — `self.set_cookie(CSRF_COOKIE_NAME, csrf_token, httponly=False, samesite="Strict")` (httponly=False is required by the double-submit pattern; `Secure` is simply absent even when serving HTTPS)
- **Impact:** Minor
- **Fix:** `secure=self.request.protocol == "https"` (or always-on when `get_ssl_enabled()`).
- **Effort:** S
- **Grade lift:** marginal

### E4 — Proxy SSRF check has a DNS-rebinding TOCTOU window

- **Where:** `compresso/webserver/proxy.py:87-104` (`_is_blocked_address` resolves and validates), then `proxy.py:212` (`client.fetch(url, ...)` re-resolves independently). Practical risk is low — targets come only from operator-configured remote installations (`proxy.py:112-147`), not request input — but a malicious DNS answer could pass validation then rebind to loopback/metadata.
- **Impact:** Minor
- **Fix:** Resolve once, validate the IP, and connect to that IP with the Host header pinned (or re-validate in a custom resolver hook).
- **Effort:** M
- **Grade lift:** marginal

### E5 — `DownloadsHandler` skips the security-header mixin and auth

- **Where:** `compresso/webserver/downloads.py:77` — `class DownloadsHandler(web.RequestHandler)` (no `SecurityHeadersMixin`, no `authorize_request`). Mitigated: links are unguessable UUID4 capabilities expiring in 60s (`downloads.py:63-69`) and paths are realpath-confined to library/cache roots (`downloads.py:102-123`), so this is header hygiene plus a note that a leaked link is exercisable without a token for its 60-second life.
- **Impact:** Minor
- **Fix:** Add the mixin; optionally require the auth header when `api_auth_enforced` is on (links are already minted by authenticated callers).
- **Effort:** S
- **Grade lift:** marginal

**Strengths (verified):** Secure-by-default network posture — auth+CSRF force-enabled off-loopback unless explicitly opted out (`config.py:159-161, 740-758`), auto-generated token (`config.py:201-210`), constant-time comparisons via `hmac.compare_digest` (`request_auth.py:56-65`), per-IP/path rate limiting with headers (`base_api_handler.py:115-133`). Plugin supply chain: HTTPS-only + mandatory SHA-256 with hex validation (`plugins.py:486-513`), 64 MiB download cap, and archive validation rejecting absolute/traversal paths, symlinks/special files, encrypted members, entry-count/size/compression-ratio bombs (`plugins.py:520-569`); external plugin execution requires an explicit `COMPRESSO_TRUSTED_PLUGIN_IDS` allowlist (`libs/unplugins/executor.py:155-211`). Proxy hardening: request/response header allowlists, credential injection only for the resolved target, redirect blocking, fail-closed DNS, loopback/link-local/metadata blocklist (`proxy.py:16-104`). Strict CSP with no `unsafe-inline`/`unsafe-eval` script sources (`security_headers.py:50-64`), websocket origin validation (`security_headers.py:67-81`), token carried in websocket subprotocol rather than query string. `.trivyignore` entries all carry written justifications (kernel-header CVEs unreachable in-container; npm-internal tooling), and the container drops privileges via `gosu "${PUID}:${PGID}"` (`docker/root/entrypoint.sh:167-168`). Suppression-hygiene gaps in `.trivyignore` are tracked as F2.

---

## F — Dependencies & Tech Currency — A-

Runtime and dev Python dependencies are fully pinned and compiled into hash-locked files enforced with `--require-hashes`, backed by CI lock-consistency checks, `pip-audit` on both locks, `npm audit`, digest-pinned Docker base images, and six-ecosystem weekly Dependabot. Versions are current for mid-2026 (Python 3.13, Node 24 LTS, Tornado 6.5.x, urllib3 2.7.0, Vue 3.5, Vite 7, Quasar 2.21). Deductions for pre-commit tool drift, `.trivyignore` hygiene, and stale metadata.

### F1 — Pre-commit hook versions drifted from CI-pinned tools (mypy a major version behind)

- **Where:** `.pre-commit-config.yaml:12` (ruff `v0.15.7`) and `:19` (mirrors-mypy `v1.19.1`) vs `requirements-dev.txt:3` (`ruff==0.15.22`) and `:16` (`mypy==2.3.0`); `dependabot.yml` has no `pre-commit` ecosystem
- **What's wrong:** Local hooks run mypy 1.19 while CI runs 2.3 — pass locally, fail CI (or vice versa), and nothing keeps the revs fresh.
- **Impact:** Moderate
- **Fix:** Bump the two `rev:` values; add pre-commit autoupdate automation or a CI assertion that revs match the dev pins.
- **Effort:** S
- **Grade lift:** A- → A

### F2 — `.trivyignore` suppressions never expire, contain a duplicate, and suppress an already-patched CVE

- **Where:** `.trivyignore:84` and `:108` (CVE-2026-43185 listed twice) while `docker/Dockerfile:11` patches that same CVE; ~100 suppressions with no `exp:` dates
- **What's wrong:** A fix regression would never resurface in scans; the suppression would hide the Dockerfile patch silently breaking.
- **Impact:** Moderate
- **Fix:** Use `CVE-XXXX exp:YYYY-MM-DD` tied to the next base-image rebuild; dedupe; remove entries patched in the Dockerfile so the scan verifies the patch.
- **Effort:** S
- **Grade lift:** A- → A

### F3 — Stale/EOL Node engine floor in webserver package.json

- **Where:** `compresso/webserver/package.json:17-18` (`"node": ">=14.17.2"`, `"npm": ">=6.14.13"`) vs `.nvmrc` (`24`) and `frontend/package.json:71` (`"node": "^24 || ^22"`)
- **Impact:** Minor. **Fix:** Align to `^24 || ^22` / `npm >=10`. **Effort:** S. **Lift:** hygiene.

### F4 — License metadata inconsistency uncovered by the consistency check

- **Where:** `setup.cfg:3` (`license = GPLv3`, non-SPDX) vs setup.py (`GPL-3.0-only`); `scripts/check-license-consistency.sh:19` checks setup.py but never setup.cfg
- **Impact:** Minor. **Fix:** Set `GPL-3.0-only` in setup.cfg (or delete the duplicate field) and add it to the check script. **Effort:** S. **Lift:** marginal.

### F5 — Dependabot pip updates can't regenerate the hash-locked `.lock` files

- **Where:** `.github/dependabot.yml:3-13` (pip, weekly, grouped) + locks named `requirements.lock`/`requirements-dev.lock` (pip-compile output, `requirements.lock:1-6`) + the drift gate at `python_lint_and_run_unit_tests.yml:58`
- **What's wrong:** Dependabot bumps `requirements.txt` but leaves the hash locks stale, so every grouped Dependabot PR fails the lock gate until a human recompiles — freshness automation and the reproducibility gate work against each other. (CI correctly blocks the stale state, so this is friction, not a gap.)
- **Impact:** Minor
- **Fix:** Rename to the `requirements.in`/`.txt` convention Dependabot regenerates, or add a workflow step that runs pip-compile on Dependabot branches.
- **Effort:** M
- **Grade lift:** A- → A (with F1)

**Strengths:** True hash-locked reproducible chain end-to-end (588 sha256 hashes in `requirements.lock`; `--require-hashes` install at `docker/Dockerfile.base:201`; drift blocked by `scripts/check-requirements-locks.sh:40-41` in CI; digest-pinned base images at `docker/Dockerfile:5` / `Dockerfile.base:4`). Active vulnerability management with documented reasoning (CVE-driven pins with inline rationale at `requirements.txt:10-13,24-25`; `pip-audit` on both locks; `npm audit --omit=dev`; targeted in-image patches at `docker/Dockerfile:26-44`). Six-ecosystem grouped Dependabot plus CI-enforced license hygiene (`LICENSES/`, `THIRD_PARTY_NOTICES.md`, wheel ships license files at `setup.py:229`).

---

## G — Performance & Scalability — B+

Deliberate, above-average performance engineering: correct composite indexes on the two hot queries, durable scan checkpointing with backpressure, an atomic task-claim UPDATE, and a versioned scale-benchmark harness wired into CI. Held back by real hot-path costs that all bite at the 100k+ scale the tooling advertises, and a CI scale gate loose enough to let order-of-magnitude regressions through on PRs.

### G1 — Task ingestion does 3-4 serialized writes + a dedupe SELECT + an N+1 library lookup per file

- **Where:** `compresso/libs/task.py:271-307` (`Tasks.create(...)` then redundant `self.save()`, `set_cache_path()`, per-file `Library(...)` lookup at line 290 → `Libraries.get_or_none` per file via `library.py:277`, then `set_status("pending")` = another save); `compresso/libs/taskhandler.py:337-338` (pre-SELECT dedupe despite `abspath` being `unique=True` at `unmodels/tasks.py:52` with the `IntegrityError` path already handled at `task.py:309`)
- **What's wrong:** Queuing one file = 1 SELECT + 1 INSERT + redundant save + 1 SELECT + 1-2 UPDATEs, all serialized through the single-writer `SqliteQueueDatabase`. The project's own real-pipeline threshold tolerates ~11 files/s; at that floor a 100k-file first scan spends hours in scheduling alone.
- **Impact:** Major
- **Fix:** Drop the pre-SELECT (rely on the UNIQUE constraint), remove the redundant save, cache library priority scores per scan, add a chunked `insert_many` path with a single bulk UPDATE per chunk.
- **Effort:** M
- **Grade lift:** B+ → A-

### G2 — Every WebSocket client re-reads the entire log file into memory every second

- **Where:** `compresso/config.py:389-394` — `with open(log_file) as f: all_lines = f.readlines()` then slices the last N (verified); called from `compresso/webserver/websocket.py:484-496` (`read_system_logs(lines=1000)`) on a 1-second interval (`websocket.py:81`, `STREAM_POLL_INTERVALS["system_logs"] = 1` — verified)
- **What's wrong:** `readlines()` loads the whole unbounded `compresso.log` (hundreds of MB on a busy server) into a list once per second per connected client, on the Tornado IO thread. The stream dedupe only skips the *send*, not the read.
- **Impact:** Major
- **Fix:** Tail by seeking from the end (bounded byte window, e.g. last 256 KB), and short-circuit on unchanged `st_mtime`/`st_size` between polls.
- **Effort:** S
- **Grade lift:** B+ → A- (with G3)

### G3 — Per-client WS polling loops re-run full-table COUNTs; no shared broadcast

- **Where:** `compresso/webserver/websocket.py:504-586` (per-client 3s loops); `webserver/helpers/completed_tasks.py:87-113` (**four** COUNT queries per tick against unbounded `completedtasks`); `compresso/libs/task.py:390-392` (unfiltered COUNT with a pointless `ORDER BY`)
- **What's wrong:** Cost is O(clients × tables scanned) every 3 seconds; 10 open dashboard tabs ≈ 27 duplicated queries/s against the same SQLite file at 100k+ rows.
- **Impact:** Moderate
- **Fix:** Compute each stream payload once in a single periodic broadcaster and fan out to registered handlers; cache counts for the poll interval; drop the ORDER BY.
- **Effort:** M
- **Grade lift:** B+ → A- (with G2)

### G4 — Scan pipeline stalls at every directory boundary

- **Where:** `compresso/libs/libraryscanner.py:358-366` (walk blocks until all queued files in the current directory are tested — a hard drain barrier per directory); `compresso/libs/filetest.py:249-257` (testers use `get_nowait()` then `event.wait(2)` on empty queue)
- **What's wrong:** Directory walking and file testing never overlap across boundaries, and drained testers sleep up to 2s while the next directory's files wait. Media libraries are one-directory-per-title — tens of thousands of stall points.
- **Impact:** Moderate
- **Fix:** Blocking `queue.get(timeout=0.25)`; checkpoint on a trailing frontier instead of a per-directory drain barrier.
- **Effort:** M
- **Grade lift:** B+ → A-

### G5 — Row-at-a-time recursive deletes for history purges and task deletions

- **Where:** `compresso/libs/history.py:249-251` (`delete_instance(recursive=True)` per row, driven by the retention job at `scheduler.py:290` which selects **all** expired rows); same pattern with a per-row `os.path.exists` stat at `task.py:469-479`
- **What's wrong:** The first retention run on a long-lived install (200k expired tasks + logs) is hundreds of thousands of serialized statements blocking all other writers.
- **Impact:** Moderate
- **Fix:** Chunk IDs (~500) and issue set-based deletes on the dependent tables, then the parents.
- **Effort:** S
- **Grade lift:** B+ → A- (small)

### G6 — CI scale gate asserts little on PRs

- **Where:** `.github/workflows/large_library_scale.yml:63-70,79-85` (PRs: 10k synthetic tier + real tier pinned to `--entries 2000`); `docs/performance/large-library-thresholds.json` (`real_tiers.2000.max_duration_seconds: 180` ≈ 11 entries/s pass bar; an unused `real_tiers.10000` exists); `compresso/libs/library_scale_benchmark.py:61-77,126-129` (synthetic tiers use hand-rolled raw sqlite3 `executemany` — code production never runs; production goes row-by-row through peewee, see G1)
- **What's wrong:** A 5-10x regression in real scheduling throughput passes PR CI; the impressive 100k/500k numbers validate a synthetic floor sharing almost nothing with production; nothing asserts `entries_per_second`.
- **Impact:** Moderate
- **Fix:** Run the real-pipeline tier at 10,000 entries on PRs, tighten `max_duration_seconds` to ~2x recorded baseline, add a `min_entries_per_second` check to `threshold_failures` (`library_scale_benchmark.py:297-313`).
- **Effort:** S
- **Grade lift:** B+ → A-

### G7 — Debug mode JSON-serializes every directory's file list during scans

- **Where:** `compresso/libs/libraryscanner.py:335-336` — `self.logger.debug(json.dumps(files, indent=2))`
- **What's wrong:** O(total files) extra serialization and log volume exactly when users enable debugging to report slow scans — which then feeds G2's whole-file log reads.
- **Impact:** Minor. **Fix:** Log `len(files)` + root only. **Effort:** S. **Lift:** hygiene.

**Strengths:** Indexes match the hot queries — composite `(status, priority)` on Tasks (`unmodels/tasks.py:82-83`, migration `007_add_task_queue_index.py`) matches the scheduler's claim query, `(abspath, task_success)` on history (migration 009) backs the per-file failed-path check via an indexed `.exists()` (`history.py:205-212`), and the pending-claim is an atomic conditional UPDATE (`taskqueue.py:274-281`). Scans are checkpointed, bounded, resumable (atomic-JSON journal with per-root locks; backpressure at `libraryscanner.py:342-344` caps queue depth; startup recovery pages the tasks table in 500-row keyset batches at `taskhandler.py:279-284`). Genuine versioned scale tooling with tracemalloc/RSS/p95 latency budgets and a real-pipeline mode that honestly documents its exclusions — well beyond what comparable projects ship (G6 critiques its assertion tightness, not its existence).

---

## H — Documentation & Onboarding — B+

The core onboarding path is genuinely good — `docs/DEVELOPING.md` is accurate and matches the real tooling, `README.md` is complete, and there are 17 topical docs including a 1,000-line plugin guide, an architecture doc, and an operator runbook. Pulled down by a ring of stale legacy documentation that actively misleads, and ~46% backend docstring coverage.

### H1 — `tests/README.md` is almost entirely stale and misleading

- **Where:** `tests/README.md:9` (`tests/scripts/setup_tests.sh` — path doesn't exist; actual is `tests/scripts_/`), `:20` (`pycodestyle ./` — repo uses ruff/mypy per `pyproject.toml:27-51`), `:41` (`pytest ... lib/common.py` — no `lib/` dir), `:84` (legacy `docker-compose` v1 syntax)
- **What's wrong:** Every command fails or points at an abandoned tool; a contributor hits four dead ends before finding `scripts/verify-local.sh`.
- **Impact:** Moderate. **Fix:** Rewrite to ~30 lines pointing at `pytest tests/unit`, `verify-local.sh fast|full`, and the marker scheme. **Effort:** S. **Lift:** B+ → A- (with H2).

### H2 — Frontend README contradicts the repo and has broken links/typos

- **Where:** `compresso/webserver/frontend/README.md:16` ("Node.js 22" vs `.nvmrc` = 24), `:5` (link to nonexistent `github.com/Compresso/compresso`), `:39` ("This projected is licensed under th GPL" + MIT notice under a GPL heading), `:56` (broken `docs/CONTRIBUTING.md` relative link)
- **Impact:** Moderate. **Fix:** One-pass rewrite. **Effort:** S. **Lift:** with H1.

### H3 — `devops/local_dev_venv.sh` and `frontend_install.sh` are undocumented and stale

- **Where:** zero doc references to either script; `devops/local_dev_venv.sh:25` runs `git submodule update --init --recursive` against a repo with no submodules (README.md:14 says none required), installs un-hash-pinned (lines 36-37) contra `DEVELOPING.md:60`; same stale submodule call at `devops/run_docker.sh:258`
- **Impact:** Moderate. **Fix:** Update to the lock-based flow or delete in favor of DEVELOPING.md. **Effort:** S. **Lift:** part of the stale-docs cleanup.

### H4 — Backend docstring coverage ~46%

- **Where:** AST-measured across `compresso/libs/` (145 modules): functions 484/1,044 (46%), classes 73/166 (44%); worst core files: `library.py` 10/44, `taskhandler.py` 7/17, `foreman.py` 21/42
- **Impact:** Minor–Moderate. **Fix:** Document the task-lifecycle files first (ARCHITECTURE.md points readers there). **Effort:** M. **Lift:** minor.

### H5 — Duplicate, divergent legacy issue/PR templates

- **Where:** `docs/ISSUE_TEMPLATE.md` and `docs/PULL_REQUEST_TEMPLATE.md` coexist with (and differ from) the live `.github/` forms; `docs/CONTRIBUTING.md:18` still points at the legacy one
- **Impact:** Minor. **Fix:** Delete the legacy pair; point CONTRIBUTING at the .github forms. **Effort:** S.

### H6 — `AGENTS.md` names a nonexistent config file

- **Where:** `frontend/AGENTS.md:57` (`quasar.config.cjs` — actual file is `quasar.config.js`); line 7 carries the stale org link
- **Impact:** Minor. **Fix:** Two-line edit. **Effort:** S.

**Strengths:** `docs/DEVELOPING.md:144-186` is accurate and complete — documented verify-local lanes, `SKIP_E2E=1`, and lock-regeneration commands all match the real scripts. Substantive references: `docs/ARCHITECTURE.md` (queue states, approval lifecycle, API-security model at `:37-55`), `docs/CONFIGURATION.md:5-24` env-var table. Depth beyond basics: `docs/PLUGIN_DEVELOPMENT.md` (1,000 lines), `docs/20TB_MEDIA_COMPRESSION_RUNBOOK.md`, `docs/SECURITY_SUPPLY_CHAIN.md`, and a semantic-release-maintained CHANGELOG.

---

## I — Developer Experience & Tooling — A

Top-tier tooling for a project this size: pre-commit with ruff/ruff-format/mypy, a CI-parity `verify-local.sh` that CI itself validates, SHA-pinned actions enforced by a checker script, hash-pinned locks with drift checks and pip-audit, six-ecosystem Dependabot, Sonar, and duration-based pytest sharding with automated monthly refresh. Remaining issues are genuinely small.

### I1 — `.editorconfig` contradicts the pre-commit end-of-file-fixer

- **Where:** `.editorconfig:8` (`insert_final_newline = false`) vs `.pre-commit-config.yaml:7` (`end-of-file-fixer`)
- **What's wrong:** Editor and hook fight over the last byte on every save/commit cycle.
- **Impact:** Minor. **Fix:** `insert_final_newline = true`. **Effort:** S. **Lift:** polish.

### I2 — User-local IDE state committed to VCS

- **Where:** `.idea/dataSources.local.xml` (machine-specific DataGrip state) and `.idea/dictionaries/josh5.xml` tracked; `.gitignore:4` excludes only `workspace.xml`. (The committed `runConfigurations/` are a legitimate DX asset and should stay.)
- **Impact:** Minor. **Fix:** `git rm --cached` the two files; extend `.gitignore`. **Effort:** S.

### I3 — Pre-commit runs full-repo mypy on every commit and covers no frontend files

- **Where:** `.pre-commit-config.yaml:18-24` (mypy with `pass_filenames: false` / `always_run: true` — the slowest configuration) and lines 6/8 (`exclude: ^compresso/webserver/frontend/` with no eslint/prettier hook anywhere)
- **What's wrong:** Slow commits on the backend side; frontend lint errors surface only in CI.
- **Impact:** Minor. **Fix:** Add a scoped eslint/prettier hook; scope or deliberately accept the mypy cost with a comment. **Effort:** S/M. **Lift:** polish.

**Strengths:** CI-parity verification with a self-testing gate — `scripts/verify-local.sh` (154 lines) mirrors CI exactly, and `verify-local.yml:9-22` runs the script in CI whenever it or its inputs change, so the local lane cannot silently drift. Supply-chain discipline enforced by tooling, not convention (40-char SHA pins with `check-action-pins.sh` failing the build; lock drift detected by recompiling in a temp dir). Duration-balanced sharding with automated upkeep (`.test_durations` feeds 3-way pytest-split; `refresh_test_durations.yml` regenerates monthly and opens a PR only on change — see D3 for the current staleness). Well-commented configs (`pyproject.toml:37-48` documents every ruff ignore; `sonar-project.properties:12-26` explains each exclusion).

---

## Top 5 Highest-Leverage Improvements

Ranked by impact × grade lift ÷ effort, with Security and Testing weighted:

1. **B1 — Fix the ffmpeg/ffprobe success check** (`compresso/libs/unffmpeg/lib/cli.py:56,81`). Major correctness bug, Small effort: non-1 exit codes pass as success and any output containing "error" fails spuriously — and probe results feed the entire pipeline. One-line fix per site plus regression tests. Lift: B+ → A- for Backend.

2. **G2 — Stop re-reading the whole log file per client per second** (`compresso/config.py:389-394`, `websocket.py:81,484-496`). Major hot-path cost, Small effort: seek-from-end tailing plus an mtime/size short-circuit removes an O(log-size × clients) load from the Tornado IO thread. Lift: toward A- for Performance.

3. **G1 — Batch task ingestion** (`task.py:271-307`, `taskhandler.py:337-338`). Major at the 100k-file scale the project explicitly targets: drop the redundant dedupe SELECT and save, cache library scores per scan, add chunked `insert_many`. Turns hours of first-scan scheduling into minutes. Lift: B+ → A- for Performance (pair with G6 so CI would catch regressions).

4. **E1 — Enforce websocket auth explicitly** (`websocket.py:122-123`). Small effort on the heaviest data-exposure surface: check `authorize_request`'s return and raise 401 instead of relying on a `finish()` side effect, plus a regression test that an unauthenticated handshake is refused. Security-weighted. Lift: B+ → A- for Security (with E2's token rotation as the follow-up).

5. **C1 — Break up the monolith components and test the pieces** (`CompletedTasksListDialog.vue` 1,251 lines, `ApprovalQueue.vue` 1,095, `VideoCompare.vue` 1,001). Major maintainability drag and the direct cause of the frontend's 24% coverage floor: extract the nested dialogs and flows into components/composables and add tests as pieces land (satisfies D1's ratchet at the same time). Lift: B- → B for Frontend and A- → A for Testing.

**Strategic runner-up:** A1 (replace the `CompressoRunningThreads` service locator with an injected facade) — the largest architecture lever, prerequisite to safely splitting `Foreman` (A6).
