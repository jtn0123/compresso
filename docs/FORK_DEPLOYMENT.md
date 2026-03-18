# Fork Deployment Guide

This fork is intended to build from a single repository checkout. The frontend is vendored at `unmanic/webserver/frontend`, and clean builds are validated with Node.js 22.

Config precedence for this fork is: built-in defaults, then environment variables, then `settings.json`, then explicit CLI or constructor arguments, and finally the large-library safe-default layer only for still-unset values. In practice, explicit operator configuration wins over the fork safety profile.

## Canonical Source Build

```bash
rm -rf build dist
python3 -m pip install -r requirements.txt -r requirements-dev.txt
python3 -m build --no-isolation --skip-dependency-check --wheel
python3 -m pip install --user "$(find dist -maxdepth 1 -type f -name '*.whl' | sort | tail -n 1)"
unmanic
```

If you want to mirror CI locally before building the package, run:

```bash
cd unmanic/webserver/frontend
npm ci
npm run lint
npm run build:publish
cd ../../..
```

## Canonical Docker Build

```bash
rm -rf build dist
python3 -m pip install -r requirements.txt -r requirements-dev.txt
python3 -m build --no-isolation --skip-dependency-check --wheel
python3 -m build --no-isolation --skip-dependency-check --sdist
docker build -f ./docker/Dockerfile -t josh5/unmanic:staging .
```

Mount these paths for production:

- `/config` for persistent application state and database files
- `/library` for the media library
- `/tmp/unmanic` for the transcode and processing cache

## Verify Readiness

- Wait for `GET /unmanic/api/v2/healthcheck/readiness` to return `200`.
- Treat any `503` response as "startup is not complete yet" and inspect the returned `stages`, `details`, and `errors`.
- Confirm the startup logs include `STARTUP_SUMMARY` lines before enabling real work.

## Troubleshooting

- If readiness stays `503`, inspect `/config/.unmanic/logs/unmanic.log` for `STARTUP_VALIDATION_FAILED`, `STARTUP_READINESS_TIMEOUT`, `STARTUP_READINESS_PARTIAL_FAILURE`, or `UI_SERVER_STARTUP_FAILED`.
- If the root page does not load but readiness is healthy, inspect `/config/.unmanic/logs/tornado.log` for routing or handler exceptions.
- If startup fails immediately, verify `/config` is writable, `/library` exists and is readable, and `/tmp/unmanic` exists on writable fast storage.
- If worker threads fail to settle, look for `WORKER_THREAD_STARTUP_FAILED` or `WORKER_THREAD_STOP_TIMEOUT` in the application log before retrying.
- If jobs are picked up but fail during processing, look for `WORKER_TASK_PROCESSING_FAILED`, `WORKER_RUNNER_FAILED`, `WORKER_COMMAND_FAILED`, or `WORKER_FINAL_MOVE_FAILED`.
- If post-processing fails after a worker run, look for `POSTPROCESS_FILE_COPY_FAILED`, `POSTPROCESS_DESTINATION_SIZE_UNAVAILABLE`, or `POSTPROCESS_SOURCE_METADATA_UNAVAILABLE`.

## Large-Library Guardrails

- Put `/tmp/unmanic` on fast local storage with enough headroom for multiple in-flight transcodes.
- Keep `/config` on persistent storage so queue history, library settings, and migrations survive restarts.
- Keep backups or snapshots of original media before enabling destructive or replacement-style workflows.
- Start with conservative worker counts and increase only after CPU, memory, cache, and disk behavior look stable.
- Review plugin behavior carefully before enabling automation against the whole library.
- Keep the first production run limited to a canary directory or a small library subset.

## Plugin Review Checklist

- Treat any plugin that replaces, renames, or relocates media as a high-risk workflow until it has succeeded on a disposable test file set.
- Prefer enabling scanners or inotify automation only after plugin settings have been reviewed for output paths, overwrite behavior, and post-processing expectations.
- If library automation is enabled with plugins, watch for `PLUGIN_AUTOMATION_REVIEW_RECOMMENDED` in the logs as a reminder to validate the workflow before widening scope.
- If jobs fail after a plugin run, inspect worker and post-processing markers together instead of treating them as separate failures. A bad plugin output path often shows up as a worker success followed by post-processing failure.

## Safe Defaults Reference

- `large_library_safe_defaults=true` keeps this fork conservative unless you explicitly opt out.
- `default_worker_cap=2` is the fallback only when `number_of_workers` is unset.
- Explicit settings in `settings.json` or CLI arguments override the fork-safe defaults.
- `cache_path` should point at fast writable storage; it is not just scratch space, it is part of the normal processing pipeline.

## Small-Library Canary Run

- Start the container with your final `/config`, `/library`, and `/tmp/unmanic` mounts.
- Wait for the readiness endpoint to report `200`.
- Enable one safe processing flow against a small test subset and watch logs for worker and post-processing errors.
- Stop the container cleanly if you see repeated `STARTUP_`, `UI_SERVER_`, or worker failure messages, then inspect `/config/.unmanic/logs`.
- Restart once using the same mounted `/config` directory and confirm the app comes back ready before scaling up.

## Production Checklist

- The repo builds cleanly from a fresh checkout.
- `npm ci`, `npm run lint`, and `npm run build:publish` succeed in `unmanic/webserver/frontend`.
- `python3 -m build --no-isolation --skip-dependency-check --wheel` succeeds.
- The Docker image builds successfully if you are deploying with Docker.
- `/config`, `/library`, and `/tmp/unmanic` are mounted to the intended persistent locations.
- `GET /unmanic/api/v2/healthcheck/readiness` returns `200`.
- A sample file or small test library completes scan, queue, processing, and post-processing successfully.
- Application logs show expected startup, worker, and plugin activity with no repeated errors.
- Only after the sample run is clean should you enable the full media library.
