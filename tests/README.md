# Testing

The authoritative testing guide is [docs/DEVELOPING.md](../docs/DEVELOPING.md)
(see its "Testing" section). This page is a quick reference.

## Layout

- `tests/unit/` — unit tests, marked `@pytest.mark.unittest`
- `tests/integration/` — integration tests, marked `@pytest.mark.integrationtest`
- `tests/fixtures/` — shared fixture media/data
- `tests/support_/`, `tests/scripts_/` — helper assets and scripts (the
  trailing underscore keeps pytest from collecting them)

Markers are declared in `pyproject.toml`.

## Running tests

From the repository root, inside a dev venv (see docs/DEVELOPING.md for setup):

```bash
# Full unit suite
python3.13 -m pytest tests/unit -q

# A single file or test
python3.13 -m pytest tests/unit/test_task.py -q
python3.13 -m pytest tests/unit/test_task.py::test_name -q

# Integration suite
python3.13 -m pytest -m integrationtest -q
```

## CI-parity verification

To run the same gates CI runs (lint, format, types, locks, audits, unit tests,
frontend gates):

```bash
bash scripts/verify-local.sh fast   # everyday lane
bash scripts/verify-local.sh full   # required before merge/release
```

Linting is ruff + ruff-format + mypy (configured in `pyproject.toml`), also
available via `pre-commit run --all-files`.

## Frontend tests

```bash
cd compresso/webserver/frontend
npm run test -- --run      # vitest unit tests
npm run test:e2e           # mocked Playwright journeys
```
