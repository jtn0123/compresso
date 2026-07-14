# 20 TB Bug and Fuzzing Audit — 2026-07-13

## Outcome

This pass targeted failure modes that could invalidate a long media migration or
a split master/M4-worker deployment. Each finding was reproduced against baseline
commit `32ae4a8cc072c22f78a55f3dbdbf6bae705b06f5`, then fixed with regression
coverage. All 20 findings below are fixed in this worktree. This is code-level
evidence, not a substitute for the remaining NAS canary and soak gates.

| # | Area | Layman explanation | Evidence | Impact | Ease |
|---|------|--------------------|----------|--------|------|
| 1 | Python dependency lock (fixed) | Both release dependency graphs contained Click 8.3.1, which the security gate now identifies as vulnerable. A clean release verification therefore could not pass. | Pre-fix `pip-audit` reported `PYSEC-2026-2132`; `requirements.txt` now pins Click 8.3.3, both locks were regenerated, and both audits report no known vulnerabilities. | High | Easy |
| 2 | Doctor path isolation (fixed) | The deployment doctor rejected a cache equal to the library but incorrectly approved a cache nested inside it. Cache cleanup or exhaustion could therefore affect durable media. | `test_cache_nested_inside_library_fails_separation_check`; the doctor now rejects equality and containment in either direction. | High | Easy |
| 3 | Missing remote library mapping (fixed) | If a master could not find the matching library configuration on a worker, it called methods on `None` and crashed the remote task instead of uploading the media. | `test_missing_remote_library_mapping_falls_back_to_send_file`; missing or incomplete mappings now use the checksummed upload path. | High | Easy |
| 4 | Transfer lock expiry and lease loss (fixed) | A network slot expired after 60 seconds even while a large chunk was still moving. A second transfer could enter the same slot, and a lost task lease did not stop the first transfer. | `test_network_transfer_lock_refresh_extends_slow_transfer_lease`, `test_large_upload_progress_renews_network_lock`, both failed-heartbeat tests; locks now have a bounded 30-minute TTL, renew on progress, release in `finally`, and abort when lease heartbeat fails. | High | Medium |
| 5 | Busy and paused worker advertisement (fixed) | A busy worker without queue preloading and a paused worker were advertised as able to take more work. The master could keep assigning jobs that had nowhere to run. | `test_does_not_advertise_busy_worker_without_preloading` and `test_paused_worker_is_not_advertised_even_with_preloading`. | High | Medium |
| 6 | Preload slot off-by-one (fixed) | A preload limit of three created four pending slots because the loop included both endpoints. Combined with the worker slot, one worker advertised five jobs instead of four. | `test_preloading_adds_extra_slots` now asserts exactly four total slots for one idle worker plus three pending slots. | Medium | Easy |
| 7 | Missing completed transfer artifact (fixed) | A manifest marked `complete` stayed complete even after its media file disappeared. Operations status could report success for a result that no longer existed. | `test_complete_transfer_is_not_reported_when_artifact_is_missing`; status and summary now fail closed on a missing or wrong-sized artifact. | High | Easy |
| 8 | Corrupt finalization recovery (fixed) | After a crash during finalization, the presence of a destination file was enough to mark the transfer complete, even when its bytes were corrupt. | `test_finalizing_recovery_rehashes_artifact_before_marking_complete`; recovery now verifies size and full SHA-256 before completing. | High | Medium |
| 9 | Corrupt transfer cleanup (fixed) | One malformed manifest either aborted cleanup or was skipped forever, leaving stale partial and completed artifacts behind. | `test_cleanup_removes_corrupt_manifest_and_continues_with_valid_stale_transfer` and `test_cleanup_removes_invalid_manifest_and_owned_artifacts`; corrupt owned state is removed without blocking other cleanup. | High | Easy |
| 10 | Recovery database authenticity (fixed) | A valid but empty or unrelated SQLite file passed a backup rehearsal. The operator could get a green recovery report for a database Compresso could not actually use. | `test_integrity_check_rejects_non_compresso_sqlite_database` and `test_integrity_check_rejects_tables_without_compresso_schema`; rehearsal now requires core tables and columns. | High | Medium |
| 11 | Recovery journal semantics (fixed) | Rehearsal only proved that journal files were JSON. Invalid states, identities, phases, path pairs, or paths outside configured roots could still receive a green report. | `test_create_rejects_invalid_recovery_journal` and `test_create_rejects_invalid_journal_finalization_phase`; creation and rehearsal validate the durable journal schema and path boundaries. | High | Medium |
| 12 | Backup without settings (fixed) | Backup creation succeeded without `settings.json`, producing an archive that could not restore the installation configuration. | `test_create_requires_settings_file` and `test_create_requires_object_settings_file`; settings are now required and must be a JSON object. | High | Easy |
| 13 | Concurrent backup publication (fixed) | Two requests using the same backup name could both pass the existence check and report success while one silently replaced the other. | `test_concurrent_creates_cannot_both_publish_same_backup_name`; publication now reserves the destination atomically with `O_EXCL`. | High | Medium |
| 14 | Mutable backup source race (fixed) | The backup hashed live settings and journals separately from writing them. A change between those operations could create a “successful” archive whose contents did not match its manifest. | `test_archive_uses_staged_settings_snapshot_when_live_file_changes`; all control-plane files are copied and validated in an isolated staging tree before hashing and zipping. | High | Medium |
| 15 | Zero-file plan or manifest (fixed) | An empty or wrong-path source could produce a zero-file capacity plan or canary manifest and look like a successful rehearsal. | `test_empty_inventory_is_rejected_instead_of_producing_a_zero_file_plan` and `test_create_manifest_rejects_empty_media_root`; both tools now require at least one supported media file. | High | Easy |
| 16 | Manifest symlink escape (fixed) | Manifest creation followed a media symlink outside the selected root, so a canary could account for and later operate on data the operator did not select. | `test_create_manifest_rejects_symlinked_media`; symbolic-link media inputs are rejected. | High | Easy |
| 17 | Non-bijective media reconciliation (fixed) | Duplicate manifest rows were accepted and extra output files were ignored. A report could therefore claim every expected row passed without proving one-to-one file accounting. | `test_verify_rejects_duplicate_entries_and_unexpected_outputs`; verification now detects duplicates and inventories unexpected output media. | High | Medium |
| 18 | Malformed media manifest schema (fixed) | Unknown versions, malformed media objects, and `NaN` durations could crash verification or bypass duration checks. | `test_verify_rejects_unknown_version_and_nonfinite_duration` plus malformed-path parameter coverage; schema faults become explicit failed rows. | High | Medium |
| 19 | Silent unreadable-directory omission (fixed) | Filesystem walking ignored permission and I/O errors. A 20 TB plan or manifest could silently omit an unreadable directory and still report success. | `test_inventory_rejects_silently_unreadable_directories`; planner, analysis, and manifest walkers now surface traversal errors, and media inventory refuses symlink inputs. | High | Easy |
| 20 | Unsafe or stale scan checkpoint (fixed) | A crafted checkpoint could contain `../` paths, and a resumed alphabetical scan skipped new directories inserted before its saved marker. Those files could remain unscanned indefinitely. | `test_scan_checkpoint_rejects_unsafe_completed_root` and `test_changed_earlier_root_invalidates_checkpoint_and_is_scanned`; checkpoint roots are confined and skipped roots are checked for post-checkpoint mutation before resume. | High | Medium |

## Validation Run

- Focused hardening suite: 272 passed.
- Full Python unit suite: 3,848 passed with four-worker concurrency stress.
- Python integration suite: 21 passed.
- Deterministic transfer restart fuzzing: 40 seeds with randomized payload sizes,
  chunk boundaries, and store reconstruction points.
- Synthetic fault laboratory, seed 20: 10/10 scenarios passed, including transfer
  restart/corruption, stale offsets, filesystem faults, finalization recovery,
  lease contention, process restart, 10k/100k queues, and a media fixture.
- Python Ruff lint and format: passed across 426 files.
- Mypy: passed (only the repository's existing untyped-body notes remain).
- Runtime and development locks match their inputs; both `pip-audit` runs report
  no known vulnerabilities.
- Release workflow and artifact-integrity contracts: 11 passed.
- Frontend baseline (unchanged by this pass): 437 tests passed, lint passed,
  production build passed, and npm reported zero vulnerabilities.

## Suggested Order

The code fixes are complete. Continue validation in this order:

1. Review and merge this patch; the whole-repository test lanes are green.
2. On the NAS, run a 20-file mixed-codec master/M4 canary and interrupt upload,
   encode, download, and replacement once each.
3. Run the documented 100 GB distributed fault drill and save doctor, operations,
   planner, manifest, backup, and recovery-rehearsal evidence.
4. Advance through 500 GB and 1 TB soak gates only when every file is reconciled
   and no stale transfer, journal, lease, or checkpoint remains.

## Discarded Candidates

- Shared-machine `pip check` failures involving unrelated Safety,
  `dataclasses-json`, Marshmallow, and psutil installations were environmental;
  the isolated locked graphs are internally consistent and audit clean.
- Ruff 0.6.9 findings were discarded after rerunning with the repository-pinned
  Ruff 0.15.21.
- The doctor readiness fallback was challenged but correctly failed when a peer
  explicitly returned `ready: false`.
- Cross-process transfer locking remains a future requirement only if Compresso
  moves from its current single-process API architecture to multiple server
  processes.
