# Compresso Bug and Risk Analysis

**Audited:** 2026-07-12

**Baseline:** released `master` at `668ba24b8085f8d060fe0f861acfd88ebd307ccf` (`v1.13.2`)

**Scope:** backend, frontend, distributed processing, security, scaling, CI, packaging, and operator documentation

**Method:** source inspection, focused repros, full local validation, live dependency/image checks, and post-merge GitHub CI

## Top 20 validated findings

| # | Area | Layman explanation | Evidence | Impact | Ease |
|---|------|--------------------|----------|--------|------|
| 1 | Default service exposure has no authentication | A normal first launch listens on every interface while API authentication and CSRF are disabled. A machine unintentionally exposed beyond a trusted LAN gives callers access to queue and media-changing operations. | `compresso/config.py:77-80,149-156`; `compresso/libs/uiserver.py:205-215`; `README.md:19-30` | High | Medium |
| 2 | Sensitive settings reads bypass API-token protection | Even after an operator enables API auth, all GETs and selected read-style POST routes bypass it. General settings remove only the API token, while link settings return stored remote usernames and passwords. | `compresso/webserver/api_v2/base_api_handler.py:53-73,141-145,187-193`; `settings_api.py:182-191`; `settings_link_mixin.py:147-169` | High | Easy |
| 3 | Authentication does not cover every dynamic route | WebSockets stream logs and task data with only an Origin check; proxy and plugin API handlers do not inherit the guarded v2 base handler. The advertised API-auth switch is therefore not a complete boundary. | `compresso/webserver/websocket.py:56-75,118-171`; `compresso/webserver/proxy.py:116-189`; `compresso/webserver/plugins.py:121-205` | High | Medium |
| 4 | Configuration secrets are world-readable and can be logged | Settings containing API tokens, remote passwords, and webhooks are written using the process umask; with a normal `022` umask the file is `0644`. A write failure logs the entire configuration dictionary. | `compresso/config.py:263-273,323-327`; `compresso/libs/common.py:225-249`; temp-file repro produced mode `0644` | High | Easy |
| 5 | An unexpected worker error can trap a task forever | The worker catches and logs unexpected errors but clears `current_task` only after the whole happy path. One database, plugin, or queue exception can make the worker retry the same in-progress task indefinitely. | `compresso/libs/workers.py:102-128,209-282` | High | Medium |
| 6 | One unexpected exception can kill all post-processing | The only postprocessor thread has no outer per-iteration exception boundary. A transient database, filesystem, or plugin error can end finalization for the entire installation while encodes continue accumulating. | `compresso/libs/postprocessor.py:95-118` | High | Easy |
| 7 | One scheduled-job exception can kill all recurring maintenance | `run_pending()` is unguarded, and the scheduler library propagates job exceptions. A failure in link refresh, cleanup, worker allocation, or repository update terminates every recurring maintenance task. | `compresso/libs/scheduler.py:69-99`; isolated scheduled-job repro propagated `RuntimeError` | High | Easy |
| 8 | Expired remote leases can be revived by stale workers | Lease heartbeat and first completion check the token but not whether the lease is still live. A disconnected worker can return after its TTL and extend or complete stale work. | `compresso/libs/remote_task_lease.py:61-93`; temp-database repro heartbeated an expired one-second lease successfully | High | Easy |
| 9 | File replacement and database finalization are separate recovery protocols | Files can be committed before history, metadata, and task deletion are durable. Startup recovery may delete the task for a committed journal without replaying missing history or statistics. | `compresso/libs/postprocessor.py:386-412,801-846`; `file_operation_tracker.py:106-125`; `taskhandler.py:166-172` | High | Hard |
| 10 | Large remote transfers can freeze the web server | Async transfer handlers call synchronous hashing, writes, and `fsync` work directly. Finalizing or manifesting a multi-gigabyte result can pause UI, websocket, readiness, and API traffic on that process. | `compresso/webserver/api_v2/transfer_api.py:97-169`; `compresso/libs/resumable_transfer.py:181-227` | High | Medium |
| 11 | Concurrent analysis requests can duplicate a full-library scan | The “already running” check and registration use separate lock sections, and the database does not enforce one cache row per library. Two requests can hash and probe the same 20 TB library simultaneously. | `compresso/webserver/helpers/library_analysis.py:49-76`; `libraryanalysiscache.py:16-27`; two-thread barrier repro started two analysis threads | High | Easy |
| 12 | Negative pagination can request an entire large table | Table schemas accept negative starts and `length=-1`. SQLite interprets `LIMIT -1` as unlimited, allowing one request to load and serialize every pending/history/approval row. | `compresso/webserver/api_v2/schema/schemas.py:118-160`; `approval_schemas.py:28-60`; schema/SQLite repro returned the full table | High | Easy |
| 13 | Invalid task types create permanently stuck rows | The create-task schema accepts any string, but lifecycle code advances only exact `local` and `remote` values. A request such as `type="banana"` leaves a unique-path task in `creating` forever. | `compresso/webserver/api_v2/schema/pending_schemas.py:151-180`; `pending_api.py:460-510`; `compresso/libs/task.py:243-280`; schema repro accepted `banana` | Medium | Easy |
| 14 | History writes can partially fail and finalization ignores the failure | Completed-task, command-log, and statistics rows are independent writes. `save_task_history()` can return false after a partial write, but the caller proceeds and deletes the task. | `compresso/libs/history.py:279-313`; `compresso/libs/postprocessor.py:386-412,1081-1103` | Medium | Medium |
| 15 | Pressing Enter can approve the wrong media | While the approval detail dialog is open, a window-level Enter handler approves regardless of which control has focus. Enter on Reject, Close, or preview controls can commit an unintended replacement. | `compresso/webserver/frontend/src/pages/ApprovalQueue.vue:1047-1055` | High | Easy |
| 16 | Plugin autosave can lose rapid edits | Changes that occur while a save is in flight are ignored by the watcher. The first request then snapshots current local state and refetches server data, so a second edit can be overwritten without ever being sent. | `PluginInfoDialog.vue:470-505,564-575` | High | Medium |
| 17 | Disabled plugin checkboxes remain clickable | The checkbox is disabled, but its parent click handler still flips the bound value. That changed value is later submitted by the settings save call. | `PluginInfoDialog.vue:148-160,470-489` | Medium | Easy |
| 18 | The frontend coverage gate omits more than half the source files | Coverage is measured only for files imported by tests, and the low threshold still passes. The clean run included 51 of 110 application files and measured 35.6% lines, 25.1% branches, and 24.9% functions. | `compresso/webserver/frontend/vitest.config.js:11-20`; isolated `npx vitest run --coverage` | High | Medium |
| 19 | The documented Docker quick start uses an inaccessible image | The primary README and compose example point to Docker Hub, where the image cannot be pulled publicly. The GHCR `latest` manifest is available and multi-architecture. | `README.md:19-30`; `docker/docker-compose.yml:11-15`; live manifest check: Docker Hub denied, GHCR succeeded | High | Easy |
| 20 | CI audits lockfiles but installs different dependency graphs | Security audits check hash-locked requirements, while Python CI, integration, local parity, and the Docker base install the unlocked `.txt` inputs. Transitive versions can drift away from the graph that passed the audit. | `python_lint_and_run_unit_tests.yml:45-57,99-104`; `integration_test_and_build_all_packages_ci.yml:105-111`; `verify-local.yml:34-37`; `docker/Dockerfile.base:169-202` | High | Medium |

## Validation Run

### 2026-07-12 implementation follow-up

- Fixed findings **4-8, 10-13, 15-17, and 19** on `codex/audit-fix-batch` with targeted regression coverage.
- Partially reduced finding **11** by making in-process analysis registration single-flight; bounded streaming and database-level uniqueness remain open.
- Findings **1-3, 9, 14, 18, and 20** remain open and should stay on the release-risk list.
- Current branch validation: **3,609 unit tests passed, 8 skipped; 21 integration tests passed; 427 frontend tests passed; strict mocked E2E passed 3/3; Ruff, formatting, Mypy, ESLint, coverage, production build, and npm production audit passed.**

- PR `#184` merged at `f0594b9`, the release workflow promoted `v1.13.2` at `668ba24b`, and no open PRs remained.
- Python unit suite: **3,588 passed, 8 skipped** in 12 minutes 10 seconds against merged master.
- Integration suite: **21 passed**, 3,596 deselected.
- Ruff: **passed** across `compresso/` and `tests/`; format check covered 409 files.
- Mypy: **passed** across 232 source files, with three untyped-body notes.
- Frontend: **416/416 passed**, ESLint passed, isolated coverage passed, and production build succeeded.
- Frontend coverage: **35.6% lines, 25.1% branches, 24.9% functions**.
- Dependency audits: Python runtime/dev locks and npm production graph reported no known vulnerabilities.
- Focused repros confirmed the download-link dictionary race, expired-lease revival, duplicate analysis start, negative/unbounded pagination, invalid task types, and scheduler exception propagation.
- Docker image check: `jtn0123/compresso:latest` denied access; `ghcr.io/jtn0123/compresso:latest` resolved successfully.
- A transient frontend coverage `ENOENT` was discarded after proving it came from two concurrent audit processes sharing the generated coverage directory; an isolated rerun passed.

## Suggested Order

1. **Immediate safety:** 1-4, 8, 12, 15.
2. **Prevent silent operational stalls/data loss:** 5-7, 9, 13-14, 16-17.
3. **Scale and release confidence:** 10-11, 18-20.

## Discarded Candidates

- Transfer-store path traversal was rejected because transfer IDs and filenames are constrained and resolved beneath the transfer root.
- A queue-claim race was rejected because the current architecture has one Foreman assigning tasks.
- The transient coverage-directory failure was rejected as shared-worktree interference, not a repository defect.
- Scan-checkpoint resume-after-directory behavior was rejected because it is deliberate and clears after successful completion.
