# Fork Deployment Guide

This fork is intended to build from a single repository checkout. The frontend is vendored at `unmanic/webserver/frontend`, and clean builds are validated with Node.js 22.

## Canonical Source Build

```bash
python3 -m pip install -r requirements.txt -r requirements-dev.txt
python3 -m build --no-isolation --skip-dependency-check --wheel
python3 -m pip install --user dist/*.whl
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

## Large-Library Guardrails

- Put `/tmp/unmanic` on fast local storage with enough headroom for multiple in-flight transcodes.
- Keep `/config` on persistent storage so queue history, library settings, and migrations survive restarts.
- Keep backups or snapshots of original media before enabling destructive or replacement-style workflows.
- Start with conservative worker counts and increase only after CPU, memory, cache, and disk behavior look stable.
- Review plugin behavior carefully before enabling automation against the whole library.
- Keep the first production run limited to a canary directory or a small library subset.

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
