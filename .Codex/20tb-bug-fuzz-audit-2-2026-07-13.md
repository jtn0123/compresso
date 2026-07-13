# 20 TB Bug and Fuzzing Audit, Pass 2 — 2026-07-13

## Outcome

This is a second set of 20 validated defects, not a restatement of the first
audit. The pass concentrated on malformed durable state, adversarial peer
responses, path ownership, lease loss, transfer boundaries, and health-check
concurrency. All 20 defects were reproduced against the pre-fix code, fixed,
and covered by regression tests. The new deterministic fuzz suite also exercises
800 malformed checkpoint, safety-state, recovery-journal, and transfer-manifest
cases.

These results strengthen code-level readiness for a 20 TB master/worker move.
They do not replace the NAS canary, interruption drill, and soak gates.

| # | Area | Layman explanation | Evidence | Impact | Ease |
|---|------|--------------------|----------|--------|------|
| 1 | Scan checkpoint shape (fixed) | A valid JSON value such as a list could crash checkpoint loading because only JSON syntax, not the expected object shape, was checked. | `test_scan_checkpoint_rejects_non_object_json_without_crashing`; non-object checkpoints now fail closed. | High | Easy |
| 2 | Transfer metadata shape (fixed) | A transfer manifest could contain list or scalar metadata and still be accepted, leaving later consumers to fail unpredictably. | `test_manifest_rejects_non_object_metadata`; manifest loading now requires metadata to be an object. | Medium | Easy |
| 3 | False completed transfer (fixed) | A manifest marked complete could claim an offset smaller than the declared file, so status could advertise an unfinished transfer as finished. | `test_complete_manifest_requires_terminal_offset`; complete manifests now require offset to equal total size. | High | Easy |
| 4 | Non-finite transfer time (fixed) | `NaN` or infinity in the last-update field could make stale-state comparisons permanently false and prevent cleanup. | `test_nonfinite_manifest_timestamp_is_cleaned_as_corrupt`; timestamps must now be finite and nonnegative. | High | Easy |
| 5 | Oversized partial transfer (fixed) | Status accepted a partial file larger than the declared transfer, hiding corrupt or cross-transfer state. | `test_status_rejects_partial_larger_than_declared_transfer`; active partial size is checked against the manifest total. | High | Easy |
| 6 | Malformed download size (fixed) | A peer could send a negative, boolean, or malformed size and push the downloader into unsafe arithmetic or misleading completion behavior. | `test_resumable_download_rejects_malformed_manifest_size`; remote totals must be exact nonnegative integers. | High | Easy |
| 7 | Oversized network chunk (fixed) | A peer could return more bytes than requested or more than remained, and the downloader would publish data beyond the declared file boundary. | `test_resumable_download_rejects_chunk_beyond_declared_size`; every chunk is bounded by requested and remaining bytes. | High | Easy |
| 8 | Cache-root destination escape (fixed) | Supplying the cache directory itself as a file destination caused the temporary `.part` path to become a sibling outside the cache and could raise a raw directory error. | `test_resumable_download_rejects_cache_root_as_file_destination`; destinations and partial files must be strict children of the cache. | High | Easy |
| 9 | Polling after lease loss (fixed) | After the master lost ownership of a remote task, it kept polling and could continue acting on work assigned elsewhere. | `test_polling_stops_immediately_when_remote_lease_is_lost`; a failed heartbeat now terminates polling immediately. | High | Easy |
| 10 | Malformed remote result list (fixed) | A peer response with the wrong `results` shape crashed result handling instead of becoming a controlled task failure. | `test_malformed_remote_results_fail_closed_without_crashing`; the response and each result row are now validated. | High | Easy |
| 11 | Peer-selected local path (fixed) | A peer could name an existing path outside the configured library and trick the master into copying that local file as the task result. | `test_remote_result_outside_library_uses_checksummed_network_download`; local reuse is confined to the configured library and every outside path uses the authenticated, checksummed transfer API. | Critical | Medium |
| 12 | Remote task-state shape (fixed) | A peer returning a list or scalar task state triggered raw attribute errors in the master. | `test_non_object_remote_task_state_fails_closed`; remote task state must now be an object. | Medium | Easy |
| 13 | Recovery journal root type (fixed) | A syntactically valid non-object journal crashed recovery before it could report a controlled safety failure. | `test_recovery_rejects_non_object_journal_as_controlled_failure`; journals are validated before any field access or mutation. | High | Easy |
| 14 | Unknown recovery state (fixed) | Recovery treated an unrecognized state as rollback work and could delete a file listed as newly created by a corrupt journal. | `test_recovery_rejects_unknown_state_without_deleting_created_file`; state and phase enums are checked before rollback. | Critical | Medium |
| 15 | Resume identity mismatch (fixed) | `resume_committed` accepted a journal belonging to a different task or operation, allowing the wrong recovery transaction to be finalized. | `test_resume_committed_rejects_mismatched_task_identity`; expected task identity is now mandatory. | High | Easy |
| 16 | Unowned backup replacement (fixed) | A crafted backup pair could point at an unrelated file and replace the original during rollback. | `test_recovery_rejects_unowned_backup_pair_without_replacing_original`; backups must use the exact owned `.compresso.bak` path. | Critical | Medium |
| 17 | Malformed safety event (fixed) | Invalid event rows in otherwise valid JSON crashed safety snapshots, potentially taking the operator status surface down during an incident. | `test_malformed_event_fails_closed_instead_of_crashing_snapshot`; event structure is validated on load. | High | Easy |
| 18 | Contradictory safety state (fixed) | Persisted state could contain an active safety event while claiming no pause was required, incorrectly presenting the deployment as ready. | `test_active_event_cannot_coexist_with_ready_persisted_state`; contradictory state is now corrupt and fail-closed. | High | Easy |
| 19 | Non-finite media duration (fixed) | A health probe treated `NaN` or infinite duration as healthy because ordinary less-than checks do not reject `NaN`. | `test_nonfinite_duration_is_not_reported_healthy`; media duration must now be finite and positive. | High | Easy |
| 20 | Health lock registry race (fixed) | A per-file lock was removed while another check was waiting on it, allowing a third check to enter concurrently and duplicate expensive probes. | `test_file_lock_registry_does_not_allow_third_check_to_overlap_waiter`; refcounted lock ownership now covers holders and waiters. | Medium | Medium |

## Validation Run

- Red proof before fixes: exactly 20 failed and 268 passed in the focused lane.
- Focused green proof after fixes: 288 passed.
- Deterministic malformed-state fuzzing: 800 generated cases passed.
- Direct consumer suites: 232 passed across postprocessing, services, task
  management, file operations, transfer APIs, scheduling, and health APIs.
- Full Python unit suite: 3,869 passed with four-worker concurrency.
- Python integration suite: 21 passed.
- Release workflow and artifact-integrity contracts: 11 passed.
- Python Ruff lint and format: passed across 427 files.
- Mypy: passed across 241 source files; only existing untyped-body notes remain.
- Runtime and development locks match their inputs; both `pip-audit` runs found
  no known vulnerabilities.
- Frontend: lint passed, 437 Vitest tests passed, production publish build passed,
  and npm audit found no vulnerabilities.
- Browser journeys: 9 passed in Chromium, mobile Chromium, and WebKit; 3 live
  packaged-backend Chromium journeys passed. The two local Firefox cases could
  not launch because Playwright's bundled Firefox software renderer failed to
  map its headless framebuffer before the app opened; GitHub CI remains the
  independent Firefox runner.
- Synthetic fault laboratory, seed 40: 10/10 scenarios passed.
- Clean wheel build and contents inspection passed for
  `compresso-1.13.4.post9-py3-none-any.whl`.

## Suggested Order

1. Let the draft PR's independent CI rerun all supported-platform checks,
   including Firefox.
2. Review and merge only after required checks are green.
3. On the NAS, execute the documented mixed-codec master/M4 canary and force one
   interruption in upload, encode, download, and replacement.
4. Run the 100 GB fault drill, save its evidence bundle, then advance through
   the 500 GB and 1 TB soak gates before the full 20 TB move.

## Discarded Candidates

- Three initial test-harness cases supplied invalid fixtures for the wrong
  reason; they were corrected and rerun before the exact 20 red findings were
  counted.
- The local Firefox launch failure occurs before page creation and reproduces
  serially with a software-renderer framebuffer error. It is recorded as a test
  environment limitation, not counted as an application defect.
- The release-tooling test warning that local Node 24.2 is below the declared
  Node 24.10 floor was not counted: its three tests passed, and CI supplies the
  supported toolchain.
- No finding from the first 20-item audit was reused to reach this pass's count.
