# Compresso Architecture

Compresso is a Python/Tornado service with a Vue/Quasar frontend served from the same process. SQLite stores configuration, queue state, task history, compression stats, health data, and file-scoped metadata.

## Runtime Flow

1. Libraries produce pending tasks through scanners, manual actions, uploads, or linked installations.
2. Worker groups claim pending tasks, execute plugin-defined processing, and write output into the cache path.
3. The postprocessor serializes final file operations so replacement, keep-both, remote completion, history, and cleanup cannot race each other.
4. The frontend polls API endpoints and websocket streams for queue, worker, approval, health, and compression state.

## Queues And Workers

Tasks move through `pending`, `in_progress`, `processed`, `awaiting_approval`, `approved`, and `complete` states. Worker groups only perform processing; final file moves are centralized in the postprocessor.

Retry metadata lives on `Tasks.retry_count`, `Tasks.max_retries`, and `Tasks.deferred_until`. Failed tasks can return to `pending` with backoff unless the failure was an intentional guardrail rejection.

## Approval Lifecycle

When approval is required, the postprocessor copies the encoded cache file into a per-task staging directory and marks the task as `awaiting_approval`. It also stores approval metadata on the task row:

- `source_codec`
- `staged_codec`
- `staged_size`
- `metadata_updated_at`

The approval API uses those fields first. Legacy rows that predate the fields are lazily backfilled when the approval list or summary must inspect them.

Approval accepts either explicit task IDs or `all_matching` filters. Reject can discard staged/cache files or requeue the task.

## Metadata And Caches

Plugin file metadata uses `FileMetadata` and `FileMetadataPaths`, keyed by content fingerprint. Library analysis also stores per-file probe metadata there under `_compresso_library_analysis`, so unchanged files can skip repeated ffprobe work. Missing files fall out of new aggregates and stale analysis path rows are cleaned best-effort.

`LibraryAnalysisCache` stores the aggregate analysis result per library and preserves the existing `start_analysis` and `get_analysis_status` API shapes.

## API Safety

Compresso remains compatible with trusted localhost/LAN installs by default. Optional API protection can be enabled with:

- `api_auth_enabled=true`
- `api_auth_token=<token>`
- `csrf_protection_enabled=true`

When token auth is enabled, mutating API requests require either `Authorization: Bearer <token>` or `X-Compresso-Api-Token: <token>`. Read-only endpoints remain available without a token.

When CSRF protection is enabled, mutating browser-originating requests must echo the `compresso_csrf_token` cookie in `X-Compresso-CSRF-Token`.

Public internet exposure still requires a reverse proxy with TLS and authentication. Do not expose Compresso directly.
