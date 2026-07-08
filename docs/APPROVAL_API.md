# Approval API

Approval endpoints live under `/compresso/api/v2/approval`.

## List Tasks

`POST /approval/tasks`

Returns a paginated list of tasks in `awaiting_approval`.

Filters:

- `search_value`: substring match on file path
- `library_ids`: list of library IDs
- `codec`: matches source or staged codec
- `quality_min`: minimum VMAF score; values above `0` exclude rows without VMAF
- `order_by`: allowlisted task column
- `order_direction`: `asc` or `desc`

## Summary

`POST /approval/summary`

Returns aggregate approval queue counts, sizes, savings, average VMAF, largest savings file, and available codec options. It uses persisted approval metadata first and lazily probes only legacy rows that are missing metadata.

## Approve And Reject

`POST /approval/approve`

`POST /approval/reject`

Both endpoints accept either:

- `id_list`: explicit task IDs
- `all_matching: true` plus the same filters used by task listing

Reject also accepts `requeue: true` to return matching tasks to `pending` rather than deleting them.

## Auth

By default, behavior is unchanged for trusted localhost/LAN installs. If `api_auth_enabled` is true, approve and reject require one of:

```bash
Authorization: Bearer <token>
X-Compresso-Api-Token: <token>
```

If `csrf_protection_enabled` is true, mutating browser requests must also send:

```bash
Cookie: compresso_csrf_token=<token>
X-Compresso-CSRF-Token: <token>
```

Read-only approval endpoints are exempt from token auth and CSRF mutation checks.
