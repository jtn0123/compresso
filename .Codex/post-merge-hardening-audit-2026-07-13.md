# Post-Merge Hardening and Simplification Audit

Date: 2026-07-13  
Baseline: `origin/master` at `9d1507fb` (`fix: secure master worker boundary (#200)`)

## Implementation tracking

This audit is the tracking document for the ordered 20 TB master-plus-M4 hardening series. A branch status is not a release gate; only a merged PR with green required checks advances the row.

| PR | Scope | Findings | Status |
|---|---|---|---|
| 1 | Secure the master/worker boundary | 1-5 | Merged as PR #200 (`9d1507fb`) after all required checks passed |
| 2 | Bound and clean file transfers | 6-9 | Merged as PR #201 (`e2cc35ba`) after all required checks passed |
| 3 | Make configuration and JSON state crash-safe | 13-14 | Merged as PR #202 (`3f2d7058`) after all required checks passed |
| 4 | Stream large health scans safely | 15-17 | Implemented on `codex/20tb-streaming-health`; merge validation pending |
| 5 | Make plugin installation transactional | 10-12 | Not started |
| 6 | Simplify critical backend workflows | 18 | Not started |
| 7 | Test and simplify the task dialogs | 19-20 | Not started |

PR 1 secured and deprecated v1, made service-token requests CSRF-independent while preserving browser CSRF enforcement, sanitized general settings, rejected protected settings writes, added a local-only masked token per remote, and allow-listed proxy request/response metadata. PR 2 retires legacy media upload, bounds and reserves resumable-transfer capacity, latches disk exhaustion, adds intentional abandonment, and separates the 64 MiB plugin upload path. PR 3 routes persistent JSON state through a shared fsynced atomic writer, rejects invalid settings shapes conservatively, and protects remote task metadata with owner-only permissions. PR 4 streams deterministic discovery through the configured bounded queue, reports traversal failure and explicit phases, checks cancellation throughout the pipeline, and scales workers in both directions.

## Executive verdict

PR #199 merged cleanly and the merged application still passes its automated baseline. The previous two fuzz audits fixed 40 real defects, and none of those items are repeated here.

There is meaningful hardening work left. PRs #200 through #202 closed the validated network-boundary, transfer, and crash-safety findings. The remaining health-scan merge gate, plugin, complexity, and frontend work is tracked above.

Current safe boundary:

- A copied, loopback-only 20-file canary remains reasonable.
- The master-plus-M4 control plane may now be tested on a restricted LAN using unique per-node tokens and host firewall rules; this does not authorize media processing beyond copied canaries.
- Do not begin the 100 GB fault run until findings 6-9 and 13-17 are addressed.
- The application remains unsuitable for an unattended, monolithic 20 TB destructive run.

## 20 validated findings

| # | Area | Layman explanation | Evidence | Impact | Ease |
|---|---|---|---|---|---|
| 1 | Legacy API v1 bypasses the security boundary | Turning on the API token does not protect the old v1 endpoints. An unauthenticated caller can still reach filesystem browsing and legacy pending/plugin operations. | `compresso/webserver/api_v1/base_api_handler.py:42-93` has no authentication `prepare()`; `compresso/webserver/api_request_router.py:49-75` still dynamically publishes v1. A live Tornado probe with auth configured returned HTTP 200 for an unauthenticated v1 file-browser request. | High | Medium |
| 2 | General settings response exposes worker passwords | The normal settings endpoint removes the master API token but returns each linked worker's stored username and password to every frontend caller. The dedicated link endpoint already knows how to mask this secret, but the broad endpoint bypasses it. | `compresso/webserver/api_v2/settings_api.py:181-182` removes only `api_auth_token`. A handler probe returned `remote_installations: [{password: "worker-secret"}]`; many frontend surfaces read this endpoint, including `src/pages/SettingsLink.vue:360-369`. | High | Easy |
| 3 | An empty settings list can erase every remote link | The settings writer tries to block updates to `remote_installations`, but only removes the field when the value is truthy. Sending an empty list passes through and wipes the saved master/worker links. | `compresso/webserver/api_v2/settings_api.py:247-255`; a handler probe forwarded `{"remote_installations": [], "ui_port": 9999}` unchanged to `set_bulk_config_items`. | High | Easy |
| 4 | The proxy leaks master credentials to workers | Requests proxied to a worker copy the caller's API token, bearer authorization, and cookies. A compromised or merely logging worker can capture credentials for the master. | `compresso/webserver/proxy.py:139-151` copies all request headers and removes only five transport headers. A live handler probe observed `X-Compresso-Api-Token: master-secret`, `Authorization: Bearer master-secret`, and the master cookie at the remote client. | High | Easy |
| 5 | A worker can set cookies on the master's browser origin | The proxy relays `Set-Cookie` from the worker back through the master. The browser treats that as a master-origin cookie, allowing a remote node to poison UI/CSRF state. | `compresso/webserver/proxy.py:161-165` filters only content length, transfer encoding, connection, and server. The live probe relayed `Set-Cookie: remote_cookie=owned; Path=/`. | High | Easy |
| 6 | Multipart uploads break when headers cross network chunks | The legacy upload parser assumes the complete multipart header is present in the first body chunk. TCP/Tornado chunk boundaries make no such promise, so an otherwise valid large upload can fail before its file is opened. | `compresso/webserver/api_v2/upload_api.py:109-135`; feeding a split first header reproduced `IndexError: list index out of range`. Existing tests always put the complete header in chunk one. | High | Medium |
| 7 | Legacy upload accepts up to 100 TB without reserving disk | A single authenticated upload can keep writing until the cache volume fills. The existing disk reserve guard is not consulted on this path. | `MAX_STREAMED_SIZE = 100 * TB` at `upload_api.py:50-51`; `prepare()` raises the request limit to that value at lines 96-97. No `DiskSpaceGuard` call exists in the handler. | High | Medium |
| 8 | Failed uploads leave partial cache trees behind | On an error or disconnect, the handler closes the file but does not delete the request's unique cache directory. Repeated failures can accumulate large abandoned files and consume the worker cache. | `_handle_upload_error()` at `upload_api.py:78-86` clears only UI state; `on_finish()` at lines 138-144 only closes the handle. Cleanup occurs only in one successful dedupe case. | High | Easy |
| 9 | Resumable transfers trust any declared total size | The newer transfer path limits each chunk, but does not cap the complete transfer or reserve free space before accepting it. A peer can declare and stream a 100 TB session in 8 MB pieces. | `transfer_schemas.py:11` has `Range(min=0)` with no maximum; `resumable_transfer.py:196-239` checks only type/nonnegative; neither path invokes `DiskSpaceGuard`. A schema probe accepted `109951162777600` bytes. | High | Medium |
| 10 | Plugin ZIP packages have no expansion budget | Archive extraction blocks traversal and symlinks, but does not limit entry count, uncompressed bytes, or compression ratio. A small ZIP bomb can exhaust the config/plugin volume. | `compresso/libs/plugins.py:515-525` iterates names and then calls `extractall()` without size/count checks; `info.json` is also read into memory without a size cap at lines 535-539. | High | Medium |
| 11 | Plugin upgrades modify the live plugin before validation | A bad update is extracted directly over the working plugin. ID validation and dependency installation happen afterward, so either failure leaves a mixed or partially replaced plugin. | `plugins.py:547-568`. A temporary-fixture probe started with `payload.txt = old`; an ID-mismatched archive raised `ValueError` but left the live payload as `new`. | High | Hard |
| 12 | Unknown plugin sort columns become server errors | The API accepts any string as a sort field, then uses it as a Python model attribute. A typo or crafted request becomes a 500 response instead of a controlled 400 or a safe default. | `plugin_schemas.py:14-20` has no allow-list; `plugins.py:696-705` calls `attrgetter()` on the supplied value. The schema accepted `not_a_column`. | Medium | Easy |
| 13 | A valid non-object settings file crashes startup | `settings.json` is checked for valid JSON syntax but not for the required object shape. A list containing a setting name reaches string-key indexing and aborts configuration loading. | `compresso/config.py:258-267` passes decoded JSON directly to `set_bulk_config_items()` at lines 342-355. A fixture containing `["ui_port"]` reproduced `TypeError: list indices must be integers or slices, not str`. | High | Easy |
| 14 | Remote task `data.json` still uses the crash-unsafe JSON writer | Safety state and settings use atomic same-directory replacement, but remote task metadata still truncates the live file first and relies on cleanup code running afterward. A process or power loss can leave invalid JSON. | `common.py:259-303` is the legacy direct-write/temporary-backup branch; `postprocessor.py:1235-1260` calls it without atomic `file_mode`. A simulated interruption left the file as `{"partial":`. | High | Medium |
| 15 | Health scan builds the whole library twice before work starts | Health checking first stores every media path in a list, then enqueues all references. No file is checked until the complete NAS traversal finishes. | `compresso/libs/healthcheck.py:404-433`. A synthetic 500,000-path inventory consumed 52.2 MiB before per-file probe/DB overhead; a million paths scales to roughly twice that. | Medium | Medium |
| 16 | Health scan silently treats unreadable trees as empty | The walk supplies no error callback, so permission and I/O failures are omitted. If all relevant directories are unreadable, the scan logs a successful "no files" completion. | `healthcheck.py:404-428` uses default `os.walk()` error handling and treats an empty result as normal. This is separate from the hardened planner/manifest walkers. | High | Easy |
| 17 | Health scan controls do not control the inventory or downscale workers | Cancel is checked only after the full inventory is built, and lowering the worker target never stops already-running workers. Operators can click stop or reduce load and see no timely effect on a slow NAS. | Inventory loop at `healthcheck.py:404-409` has no cancel check; cancel begins at lines 452-462. The monitor only handles `current_alive < requested` at lines 466-485 and has no downscale branch. | Medium | Medium |
| 18 | Critical backend workflows remain too complex to change safely | Fifty functions exceed complexity 10. Recovery, final replacement, media verification, worker execution, and health scanning are among the largest, so small fixes carry broad regression risk. | `ruff C901` with threshold 10 reported 50 functions. Examples: `verify_manifest`, `_finalize_local_task_with_capacity`, and `recover_tasks_on_startup` are complexity 20; `post_process_file` is 19. `remote_task_manager.__send_task_to_remote_worker_and_monitor` is 578 lines. | High | Hard |
| 19 | Frontend tests exercise only a small part of the UI logic | The suite count looks healthy, but most UI functions and branches never execute in tests. The largest task dialogs have no measured function coverage. | Local Vitest coverage: 20.45% statements, 15.81% branches, 13.33% functions. `CompletedTasksListDialog.vue` has 11.7% line and 0% function coverage; `PendingTasksListDialog.vue` has 10.96% line and 0% function coverage. | Medium | Medium |
| 20 | The two task dialogs duplicate a large, weakly tested feature surface | Completed and pending task dialogs independently implement much of the same table, filtering, responsive, and action behavior. Fixes must be repeated and can drift. | The files are 1,550 and 1,055 lines. A line-sequence comparison found 706 matching lines and 54.2% similarity, including repeated blocks up to 30 lines. | Medium | Medium |

## Recommended order

### Batch A: close the network boundary before connecting the M4

1. Remove API-v1 routing or make its base handler use the same auth, rate-limit, and CSRF preparation as v2 (#1).
2. Introduce a public settings DTO that never contains secrets; keep link passwords write-only/masked (#2-3).
3. Give the proxy an explicit outbound-header allow-list and response-header deny-list (#4-5).

### Batch B: make file ingress bounded and restart-clean

1. Retire the handwritten multipart parser in favor of the resumable transfer protocol (#6).
2. Enforce a configured maximum file size, reserve disk before accepting a session, recheck during progress, and latch/pause on reserve failure (#7 and #9).
3. Track and clean abandoned upload sessions deterministically (#8).
4. Validate decoded configuration as an object before passing it to
   `set_bulk_config_items()` (#13).
5. Make every persistent JSON write use one atomic, fsynced implementation (#14).

### Batch C: make plugin installation transactional

1. Validate archive count, expanded size, ratio, metadata, and ID in a staging directory (#10).
2. Install dependencies in staging, then atomically swap the complete plugin directory with rollback (#11).
3. Validate plugin sort fields at the schema boundary (#12).

### Batch D: reuse the hardened inventory engine

Replace the health check's private `os.walk`/list/queue pipeline with the bounded, error-aware inventory machinery already used by the planner/scanner. Stream paths through a bounded queue, surface traversal errors, check cancellation during discovery, and use cooperative worker retirement (#15-17).

### Batch E: simplify with proof

1. Split the high-complexity lifecycle functions behind tested state-transition helpers; lower the CI complexity ceiling gradually from 20 (#18).
2. Add interaction/contract tests for the task dialogs, then extract one shared task-table composable/component rather than refactoring both blindly (#19-20).

## Validation run

- PR #199 was marked ready and squash-merged only after live GitHub state was `CLEAN`/`MERGEABLE` and every required check passed. Merge commit: `8d64a937`.
- The PR's full parity CI passed, including Linux/macOS/Windows unit shards, integration, frontend, CodeQL, Sonar, package, Docker amd64, scale, and the 16-minute `verify-local.sh` job.
- Local `bash scripts/verify-local.sh fast` passed on the merged baseline:
  - Python lint, format, mypy, lock parity, and both `pip-audit` graphs passed.
  - Python unit suite: 3,864 passed, 8 skipped.
  - Frontend: 31 files and 437 tests passed; lint and production build passed.
  - Local fast mode intentionally skipped integration, release contracts, wheel, and browser gates; those were covered by the PR's full parity CI.
- `npm audit --audit-level=high`: 0 vulnerabilities.
- Deterministic probes reproduced findings 1-6, 9, 11, 13, and 14.
- Structural measurements covered complexity, frontend coverage, component similarity, and a 100,000/500,000-path health inventory fixture.
- PR 4 branch validation passed the complete synthetic fault laboratory (all 10 scenarios), a 500,000-entry threshold gate at 147,075 entries/second with 3.94 MiB peak RSS growth, and `verify-local.sh fast` with 3,892 Python tests plus 444 frontend tests.

## Candidates checked and rejected

- Preview `NaN` duration: current Marshmallow rejects special numeric values, so it is not a finding.
- The frontend install prints a transitive `glob` deprecation warning, but both `npm audit` runs report zero vulnerabilities; it was not promoted into the list.
- The 40 issues in `.Codex/20tb-bug-fuzz-audit-2026-07-13.md` and `.Codex/20tb-bug-fuzz-audit-2-2026-07-13.md` were checked first and excluded from this report.
