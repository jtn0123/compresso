# 20 TB Media Compression Runbook

This runbook is the release gate for compressing a 20 TB media library with one authoritative Compresso master, an Apple Silicon worker such as an M4 MacBook Air, and optional additional workers. A green test suite is necessary but is not permission to run destructively against the only copy of the library.

## Supported topology

- The master owns the production scan, task queue, task history, and final media replacement.
- Every remote machine runs its own Compresso installation, database, and fast local cache.
- Only the master scans the production library. Never share a Compresso SQLite database between machines.
- Keep traffic on a trusted LAN or VPN. Put TLS and authentication at a reverse proxy before crossing an untrusted network.
- Start the M4 worker with one concurrent encode. Increase concurrency only from measured thermal, memory, and throughput evidence.

## Non-negotiable safeguards

- Keep restorable snapshots or verified backups of every original.
- Size each cache for several copies of the largest expected file and keep disk-pressure pause enabled.
- Use approval mode for the representative canary, not as an unbounded 20 TB backlog.
- Stop on low disk space, checksum or manifest failures, unexplained duplicate tasks, lost workers that do not reconcile, or stream/HDR regressions.
- Advance only when every file in the current batch is completed, intentionally skipped, or explicitly recorded as failed.

## Progressive rollout gates

Run these in order. A failed gate sends the workflow back to the previous passing size.

1. **20 representative files:** include the largest file; H.264 and HEVC; SDR and HDR; multiple audio tracks; subtitles; chapters; attachments; and every production container.
2. **100 GB fault-injection run:** restart the master and worker during upload, encode, download, staging, and final replacement.
3. **500 GB overnight run:** verify unattended recovery, disk reserve, task accounting, and stable temperatures.
4. **1 TB multi-day soak:** measure master and worker throughput separately and confirm queue/UI stability.
5. **Production batches:** process snapshot-backed 500 GB to 1 TB batches, verifying a manifest after every batch.
6. **Final reconciliation:** produce a before/after manifest and account for every input.

## Canary procedure

Run the deployment doctor on each node before creating the canary manifest. An
offline run records everything available on that machine and may finish with
warnings. The final connected gate must be strict and must include the linked
worker. Supply the worker token through an environment variable so it is not
stored in shell history:

```bash
compresso doctor --role worker --output worker-readiness.json

export COMPRESSO_DOCTOR_PEER_TOKEN="<worker API token>"
compresso doctor --role master --peer m4-worker --strict \
  --output master-readiness.json
```

Reports expire after 24 hours. Do not begin a batch from an expired report or
when the strict command exits nonzero. Connected peer probes require the linked
installation address to use HTTPS. `--output` accepts a filename, not a path;
reports are stored under the node's user-data `readiness` directory.

Create a manifest before Compresso touches the copied canary:

```bash
./scripts/media-canary.py create /path/to/canary /path/to/canary-before.json
```

Run one master worker and one M4 remote worker. Keep approval enabled. Watch `/compresso/api/v2/system/operations` and `/compresso/api/v2/system/capabilities`. Restart each process once during the transfer and file-finalization phases, then confirm the same stable job ID resumes without a duplicate replacement.

Verify every result:

```bash
./scripts/media-canary.py verify /path/to/canary-before.json \
  --root /path/to/canary --report /path/to/canary-after.json
```

Do not advance if the command exits nonzero, a file is unaccounted for, or visual/audio inspection finds a regression.

Exercise the complete synthetic fault laboratory before a large batch. The
one-command form creates a marked ephemeral workspace and never reads the
configured media library:

```bash
export COMPRESSO_FAULT_LAB=1
compresso fault-lab --scenario all --seed 20 \
  --report fault-lab-seed-20.json
```

For a persistent scratch workspace, initialize it explicitly before running:

```bash
compresso fault-lab --workspace /path/to/empty/scratch --init-workspace
compresso fault-lab --workspace /path/to/empty/scratch --scenario all \
  --seed 20 --report fault-lab-seed-20.json
```

The guard requires both `COMPRESSO_FAULT_LAB=1` and a generated marker for an
explicit workspace. It rejects config, cache, library, user-data, repository,
and home-directory overlap. The ordered run covers restart/resume, corrupt
chunks and checkpoints, stale offsets, injected disk-full/read-only failures,
interrupted finalization, duplicate lease contention, a real two-process HTTP
restart, 10,000/100,000-entry queues, and a compact FFprobe-verified media
fixture. Any failed invariant stops the remaining scenarios and exits nonzero.

## Readiness interpretation

Compresso has restart recovery, durable final-replacement journaling, disk preflight, stable job IDs, leases and heartbeats, resumable checksummed transfers, bounded scanning, capability discovery, and operational status endpoints. Local automated tests and synthetic scale benchmarks cover those mechanisms.

The remaining proof is production-shaped evidence: a separate-machine M4 canary, NAS traversal and file-probing behavior, concurrent contention, real media fidelity, and the progressive 100 GB through 1 TB gates. Until those pass, the supported next action is a copied or snapshot-backed 20-file canary—not a monolithic 20 TB destructive run.
