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

Compresso binds to `127.0.0.1` by default. Container templates explicitly bind `0.0.0.0`; use a host firewall or trusted LAN and enable API protection before exposing that port beyond the host.

Optional API protection can be enabled with:

- `api_auth_enabled=true`
- `api_auth_token=<token>` (generated into owner-only `settings.json` when omitted)
- `csrf_protection_enabled=true`

When token auth is enabled, every dynamic API, proxy, plugin API, and WebSocket request requires the token. This includes deprecated API v1 routes; v1 responses carry deprecation headers and v1 will be removed in the next major release. The readiness endpoint remains public for container health checks. The browser asks for the token once per tab and keeps it in session storage.

When CSRF protection is enabled, mutating browser-originating requests must echo the `compresso_csrf_token` cookie in `X-Compresso-CSRF-Token`. A request carrying the installation's valid API token is treated as non-cookie service authentication and does not also need a browser CSRF cookie.

Each remote-link record can store a separate `api_token` for the destination worker while continuing to use optional Basic authentication. The token is local-only: it is sent to that worker in `X-Compresso-Api-Token`, masked by the dedicated link API, omitted from general settings responses, and never synchronized back to the worker. Proxy requests discard browser cookies, master credentials, CSRF/origin headers, and target-selection headers before applying the selected worker's credentials. Proxy responses expose only required content, cache, range, checksum, and transfer metadata.

`GET /compresso/api/v2/settings/read` is a public browser serializer, not a configuration backup endpoint. It omits the master API token, notification credentials, and remote authentication fields. Those values are managed only through their dedicated endpoints; `/settings/write` rejects protected keys.

Public internet exposure still requires a reverse proxy with TLS and authentication. Do not expose Compresso directly.
