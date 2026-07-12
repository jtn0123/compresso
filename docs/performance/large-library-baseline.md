# Large-library metadata baseline

This benchmark exercises Compresso's deterministic, directory-sized scanner
enumeration and schedules every generated path into an indexed SQLite queue.
The fixture is metadata-only: it creates paths lazily in batches of 1,000 and
does not allocate or probe media payloads.

## Reproduce

```bash
python3.13 scripts/library-scale-benchmark.py \
  --entries 500000 \
  --output large-library-500000.json \
  --assert-thresholds
```

Pull requests run the 10,000-entry tier. The scheduled workflow runs 500,000
entries weekly, and manual runs can select 10,000, 100,000, or 500,000. Each CI
run uploads its JSON result for 90 days. Regression limits are versioned in
`large-library-thresholds.json`; they are intentionally broad across runner
classes and should only be tightened from several CI samples.

## First baseline

Recorded 2026-07-11 on an Apple Silicon arm64 machine with 10 logical CPUs,
macOS 27.0, Python 3.13.5, SQLite WAL mode, and batches of 1,000 entries.

| Entries | Wall time | Entries/s | Peak RSS growth | SQLite DB | Indexed lookup p95 | Queue page p95 |
|---:|---:|---:|---:|---:|---:|---:|
| 10,000 | 0.0955 s | 104,730 | 3.77 MB | 1.59 MB | 0.0082 ms | 0.4339 ms |
| 100,000 | 0.8088 s | 123,641 | 4.16 MB | 16.16 MB | 0.0146 ms | 3.0740 ms |
| 500,000 | 3.7750 s | 132,451 | 4.00 MB | 81.56 MB | 0.0197 ms | 14.4042 ms |

The queue-page sample is distributed from the first page through the deepest
page so it exposes the cost of large SQLite offsets rather than measuring only
the first few pages.

## Evidence boundary

This result proves that generated scanner metadata stays bounded and that
500,000 paths can be inserted and queried through the queue's important SQLite
indexes on this machine. It does not measure NAS directory latency, `ffprobe`,
plugin file tests, frontend rendering of a huge queue, real media transfer, or
concurrent worker contention. Those remain separate canary and soak gates in
the large-library runbook.
