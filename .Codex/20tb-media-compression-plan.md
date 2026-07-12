# 20 TB Media Compression Readiness Plan

## Objective

Safely compress a 20 TB media library with one authoritative Compresso master,
an Apple Silicon worker such as an M4 MacBook Air, and optional additional
workers. The finished system must recover from process, machine, and network
failures without losing originals, losing completed work, or replacing a file
twice.

## Target topology

- The master owns the library scan, task queue, task history, and final media
  replacement.
- Every remote machine runs its own Compresso installation and local cache.
- Remote workers never share the master's Compresso configuration or SQLite
  database.
- The master is the only installation that scans the production library.
- Production traffic stays on a trusted LAN or VPN, with TLS and authentication
  supplied by a reverse proxy when it crosses an untrusted network.

## Delivery phases

### Phase A: restart and file safety

- [x] A1 Preserve recoverable tasks and cache files across restart.
- [x] A2 Requeue interrupted tasks without consuming a normal failure retry.
- [x] A3 Reconcile approval staging and encoded cache output.
- [x] A4 Add a persistent final-replacement journal with crash recovery.
- [x] A5 Add preflight free-space checks and automatic low-space pause.

Acceptance gate: terminating Compresso during scanning, encoding, approval,
and final replacement never loses an original and never permanently loses a
task.

### Phase B: distributed durability

- [x] B0 Apply installation-level worker allocation to active worker groups.
- [x] B1 Add stable job IDs, worker leases, and heartbeats.
- [x] B2 Make task submission and completion idempotent.
- [x] B3 Add resumable chunked uploads and downloads.
- [x] B4 Enable end-to-end checksum validation by default.
- [x] B5 Reconcile master and worker state after either side restarts.
- [x] B6 Clean orphaned remote files and partial transfers automatically.

Acceptance gate: disconnect or restart either machine during a large transfer
or encode and the job resumes or safely requeues without duplicate replacement.

### Phase C: Apple Silicon worker support

- [x] C1 Detect worker OS, encoders, storage, and current capacity.
- [x] C2 Add H.264 and HEVC VideoToolbox presets with native quality controls.
- [x] C3 Preserve HDR, subtitle, audio, and container behavior explicitly.
- [ ] C4 Route jobs according to worker capabilities and measured throughput.
- [~] C5 Add a real master-to-macOS integration smoke test. A two-process
  localhost HTTP/restart drill now passes; the separate-machine M4 canary is
  still required.

Acceptance gate: a representative media set meets the selected quality and
size targets with no unexpected stream or HDR loss.

### Phase D: large-library scale

- [x] D1 Add composite queue indexes and benchmark large task sets.
- [x] D2 Replace unbounded scan queues with bounded, resumable batches.
- [x] D3 Remove full-history and linear membership work from the scan hot path.
- [x] D4 Add load-aware scheduling across heterogeneous workers.
- [x] D5 Add queue, transfer, worker, cache, and disk-pressure observability.

Acceptance gate: at least 500,000 synthetic media entries scan and schedule
without excessive memory growth, SQLite locking, or UI degradation. The
metadata enumeration/SQLite portion now passes; NAS traversal, file probing,
concurrent contention, and UI behavior still need production-shaped evidence.

### Phase E: progressive production validation

- [ ] E1 Process 20 representative files and inspect every result.
- [ ] E2 Run a 100 GB fault-injection test.
- [ ] E3 Run a 500 GB overnight test.
- [ ] E4 Run a 1 TB multi-day unattended soak.
- [ ] E5 Process production in snapshot-backed 500 GB to 1 TB batches.
- [ ] E6 Produce a final before/after manifest and account for every input.

## Production rollout rules

- Keep restorable snapshots or backups of originals.
- Start the M4 worker at one concurrent encode.
- Keep cache on fast local storage with space for several largest-case files.
- Use approval mode for the representative canary, not as an unbounded 20 TB
  backlog.
- Stop automatically on low disk space, repeated integrity failures, or a lost
  worker that cannot reconcile.
- Advance to the next batch only when every task in the current batch is
  completed, intentionally skipped, or explicitly recorded as failed.

## Current implementation status

The code foundation for a restart-safe split deployment is now implemented:

- Local task/cache recovery and a durable, replayable final-replacement journal.
- Disk preflight checks with automatic pause and retry at encode, staging, and
  final replacement.
- Stable job IDs, durable leases, heartbeats, remote binding, and idempotent
  submission/completion.
- Resumable 8 MiB chunk transfers with per-chunk and whole-file SHA-256 checks,
  crash reconciliation, and scheduled orphan cleanup.
- Remote hardware/capability discovery and load-aware selection that rejects a
  worker missing the configured encoder.
- Deterministic, bounded library scanning with durable per-directory restart
  checkpoints and indexed per-path history checks.
- Explicit FFmpeg mapping of every stream, global metadata, and chapters, with
  subtitles, data streams, and attachments copied. An incompatible output
  container fails visibly rather than silently losing streams.
- A combined operations endpoint at `/compresso/api/v2/system/operations` for
  queue, task, lease, worker, transfer, scan-checkpoint, cache, and disk-reserve
  status. Worker capability detail is at
  `/compresso/api/v2/system/capabilities`.

This makes the branch ready for a copied or snapshot-backed 20-file canary. It
does **not** make an untested 20 TB destructive run safe. The real-machine gates
C4-C5 and E1-E6 still need to be executed.

## Validation evidence

- 3,579 unit tests passed; 8 environment-specific tests skipped.
- 21 integration tests passed, including a two-process HTTP transfer/restart drill.
- Repository-wide Ruff lint and format checks passed.
- Mypy passed across 231 source files with only existing untyped-function notes.
- Frontend validation passed 416 Vitest tests, lint, coverage thresholds, the
  production build, 3 mocked Playwright journeys, and 3 real-backend Playwright
  journeys.
- A 500,000-entry metadata scan/scheduling benchmark completed in 3.775 seconds
  on the local 10-core arm64 machine with 4.00 MB peak RSS growth, an 81.56 MB
  SQLite queue, 0.0197 ms indexed lookup p95, and 14.4042 ms deep-page p95. See
  `docs/performance/large-library-baseline.md` for method and limitations.
- The localhost master/worker drill validated discovery over HTTP, resumed a
  checksummed upload after worker restart, rejected a stale chunk, kept one task
  across repeated finalization and restart, and preserved separate databases.
- A local distributed fault drill passed repeated transfer-store restarts,
  injected chunk corruption rejection, durable offset recovery, and final
  SHA-256 validation.
- A deeper reliability pass fixed 20 reproduced transfer, lease, scanner,
  postprocessor, journal, manifest, capacity, and identity defects. The full
  evidence is in `.Codex/20tb-deep-reliability-audit.md`.
- A real HEVC VideoToolbox smoke encode completed on Apple Silicon at about
  7.6x real time for the small synthetic clip. This proves the command works,
  not the throughput of a production media library.

## Operating the next gate

1. Copy 20 representative files into a canary directory. Include the largest
   file, H.264 and HEVC, SDR and HDR, multiple audio tracks, subtitles, chapters,
   attachments, and every container used in production.
2. Record the before-state:

   ```bash
   ./scripts/media-canary.py create /path/to/canary /path/to/canary-before.json
   ```

3. Run one master worker and one M4 remote worker. Start the M4 at one encode.
   Keep approval mode enabled and watch both system endpoints above.
4. Restart each Compresso process once during upload, encode, download, staging,
   and final replacement. Confirm the same job ID resumes and no duplicate task
   or replacement appears.
5. Verify every result:

   ```bash
   ./scripts/media-canary.py verify /path/to/canary-before.json \
     --root /path/to/canary --report /path/to/canary-after.json
   ```

   Do not advance if the command exits nonzero, any file is unaccounted for, or
   visual/audio inspection finds a regression.
6. Exercise the transfer mechanism independently before a large batch:

   ```bash
   ./scripts/distributed-fault-drill.py --size-mb 102400 --chunk-mb 8
   ```

7. Only after the 20-file canary passes, run E2 (100 GB), E3 (500 GB), and E4
   (1 TB) in that order. Record throughput separately for the master and M4 so
   C4 can be completed with measured data, not estimates.
8. Benchmark a 500,000-entry synthetic scan before claiming the Phase D
   acceptance gate. The bounded implementation is present, but this scale run
   has not yet been executed.
9. Process production only in snapshot-backed 500 GB to 1 TB batches, creating
   and verifying a manifest for every batch.

Do not point this branch at the only copy of the 20 TB library. The earliest
recommended use is a copied or snapshot-backed 20-file canary with one local
worker and one M4 worker.
