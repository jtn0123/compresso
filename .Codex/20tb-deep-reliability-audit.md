# 20 TB Deep Reliability and Fuzzing Audit

## Outcome

This pass concentrated on the new data-safety surface required for a split
master/worker deployment. Every item below was reproduced with a failing test or
bounded deterministic fuzz case before its fix was implemented. All 20 findings
are fixed on `codex/20tb-media-readiness`.

| # | Area | Layman explanation | Evidence | Impact | Ease |
|---|------|--------------------|----------|--------|------|
| 1 | Transfer request race (fixed) | Each API request created a different lock, so simultaneous chunks could both believe they owned the same byte offset and corrupt a resumable upload. | `test_store_instances_for_same_root_share_one_process_lock`; stores now share a root-scoped lock. | High | Medium |
| 2 | Corrupt upload retry loop (fixed) | A full-file checksum failure kept the bad partial file, causing every retry to fail forever at the same point. | `test_full_checksum_failure_resets_partial_for_clean_retry`; checksum failure now atomically resets the session to offset zero. | High | Easy |
| 3 | Oversized partial recovery (fixed) | A partial file larger than the declared media size could never be repaired through the normal protocol. | `test_begin_repairs_partial_larger_than_declared_transfer`; begin now resets impossible partial state. | High | Easy |
| 4 | Cleanup blocked by one corrupt manifest (fixed) | One damaged JSON manifest stopped cleanup of every other stale transfer. | `test_cleanup_skips_corrupt_manifest_and_continues_with_valid_stale_transfer`. | Medium | Easy |
| 5 | Zero-byte transfer finalization (fixed) | An empty file had no partial file to hash, so finalization crashed instead of producing a valid empty result. | `test_zero_byte_transfer_finalizes_with_empty_sha256`. | Low | Easy |
| 6 | Corrupt download retry loop (fixed) | A complete-size but corrupt `.part` download was retained, so the client never fetched clean bytes on its next retry. | `test_resumable_download_discards_full_corrupt_partial_for_next_retry`. | High | Easy |
| 7 | Weak transfer request validation (fixed) | Empty job IDs and non-SHA-256 checksum strings could enter the durable transfer journal and fail much later. | Five invalid request variants in `test_begin_rejects_invalid_transfer_identity_and_checksum`. | Medium | Easy |
| 8 | Same-worker lease not renewed (fixed) | A restarted worker could resume its token with only seconds left, allowing the lease to expire during hashing or upload. | `test_reacquire_by_same_worker_renews_nearly_expired_lease`. | High | Easy |
| 9 | Wrong-token completion replay (fixed) | After completion, any caller presenting the same checksum was accepted even when it did not own the lease token. | `test_idempotent_completion_still_requires_owning_token`. | High | Easy |
| 10 | Remote identity rebind (fixed) | An idempotent retry could overwrite an existing task's lease or master UUID instead of rejecting the conflict. | `test_remote_identity_binding_is_idempotent_but_rejects_conflict` and `test_finalize_rejects_conflicting_identity_rebind`. | High | Medium |
| 11 | Scanner dequeue/checkpoint race (fixed) | There was a small window after a tester removed a file from the queue but before it reported busy; the scanner could checkpoint that directory too early. | `test_dequeued_but_unfinished_file_blocks_checkpoint`; queue acknowledgements now track unfinished work. | High | Medium |
| 12 | Checkpoint writer collision (fixed) | Multiple checkpoint-store instances used separate locks and one fixed temporary filename. | `test_store_instances_share_lock_and_do_not_share_fixed_temp_filename`; root-scoped lock plus unique temp files. | Medium | Easy |
| 13 | Existing backup overwrite (fixed) | A real file already named `*.compresso.bak` could be overwritten by the recovery system. | `test_safe_remove_refuses_to_overwrite_preexisting_backup`. | High | Easy |
| 14 | Failed rollback forgotten (fixed) | A failed restore logged an error, cleared its state, and deleted its journal, removing the information needed to recover later. | `test_failed_rollback_keeps_durable_journal_for_startup_recovery`; failed entries and journal now remain. | High | Medium |
| 15 | Commit cleanup forgotten (fixed) | Failure to delete a large backup was ignored and its path was removed from the journal, potentially leaking substantial disk space. | `test_commit_cleanup_failure_remains_recoverable`; startup recovery now finishes pending commit cleanup. | High | Medium |
| 16 | Recovery journal overwrite (fixed) | Retrying the same task could silently replace an unrecovered journal from its previous destructive operation. | `test_existing_operation_journal_cannot_be_silently_overwritten`. | High | Easy |
| 17 | False-success finalization (fixed) | History, metadata, task deletion, and success notifications continued even when final file movement threw an exception or returned failure. | `test_stops_finalization_on_post_process_error` and `test_stops_finalization_when_file_movement_reports_failure`; destructive phase extracted into one fail-closed gate. | High | Medium |
| 18 | Encoded cache lost after move failure (fixed) | A move failure cleaned the staging part and the cache, destroying the completed encode that could have been retried. | `TestFileMovePipeline.test_preexisting_destination_restored_when_final_move_fails`; encoded cache is restored and retained. | High | Medium |
| 19 | Canary manifest unsafe inputs (fixed) | Escaping paths, malformed entries, empty manifests, and zero-sized samples could crash verification or allow a meaningless pass. | `test_verify_rejects_manifest_path_that_escapes_root`, malformed-path parameter cases, empty-manifest and sample-size tests. | High | Medium |
| 20 | Malformed capacity configuration (fixed) | Invalid remote load payloads and `NaN`/`Infinity` disk settings could crash worker selection or the disk guard rather than failing safely. | Bounded capacity fuzzing plus `test_score_fails_closed_for_malformed_remote_capacity_values` and `test_nonfinite_capacity_settings_fall_back_instead_of_crashing`. | Medium | Easy |

## Validation run

- Critical-path suite: 242 tests passed.
- Critical-module coverage: 88.06% across transfer, lease, scanner checkpoint,
  media manifest, operations status, disk guard, worker capabilities, and file
  operation journal modules.
- Deterministic transfer fuzzing: 40 seeds, randomized payloads, randomized
  chunk boundaries, and randomized store reconstruction points.
- Capacity fuzzing: 500 malformed remote-capability payload combinations and a
  matrix of invalid/non-finite disk reserve and output multiplier values.
- Full unit suite: 3,555 passed; 8 environment-specific tests skipped.
- Integration suite: 20 passed.
- Ruff lint and format: passed.
- Mypy: passed across 231 source files.
- Diff whitespace validation: passed.

## Suggested order from here

The code-level defects above are complete. Remaining validation should happen in
increasingly realistic environments:

1. Run the documented 20-file master/M4 canary and deliberately interrupt each
   upload, encode, download, and replacement phase.
2. Run the 100 GB distributed fault drill while watching
   `/compresso/api/v2/system/operations`.
3. Execute the 500,000-entry synthetic scan benchmark and record peak RSS,
   SQLite latency, and queue depth.
4. Proceed through 500 GB and 1 TB soak gates only after the preceding manifest
   reports account for every file.

## Discarded or deferred candidates

- Cross-process file locking was not added. Compresso currently serves this API
  in one process, and the validated defect was cross-request locking inside that
  process. A future multi-process server would require an OS-backed lock.
- A conservative finalization disk estimate can overstate space when cache and
  library are on different volumes. That is intentional fail-safe behavior, not
  a data-loss bug.
- Full-production manifest generation still holds its result set in memory. The
  documented rollout uses 500 GB to 1 TB batches; a streaming JSONL manifest is
  still worthwhile before attempting one monolithic 20 TB manifest.
- Capability routing now tolerates malformed metrics, but C4 remains open until
  real master-versus-M4 throughput measurements are collected.
