#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/compresso/webserver/frontend"
RELEASE_DIR="${ROOT_DIR}/.github/release"
PYTHON_BIN="${PYTHON_BIN:-python3.13}"
MODE="${1:-fast}"
SKIPPED_GATES=()

if [[ "${MODE}" != "fast" && "${MODE}" != "full" ]]; then
  echo "Usage: $0 [fast|full]" >&2
  exit 2
fi

skip_gate() {
  SKIPPED_GATES+=("$1")
}

echo "==> Verification mode: ${MODE}"
echo "==> Checking Python"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Missing ${PYTHON_BIN}. Install Python 3.13 or set PYTHON_BIN=/path/to/python3.13." >&2
  exit 1
fi

"${PYTHON_BIN}" - <<'PY'
import sys

if sys.version_info < (3, 13):
    raise SystemExit(f"Python 3.13+ is required, found {sys.version.split()[0]}")
print(f"Python {sys.version.split()[0]}")
PY

cd "${ROOT_DIR}"

echo "==> Checking immutable GitHub Action pins"
bash scripts/check-action-pins.sh

echo "==> Checking license metadata and retained notices"
bash scripts/check-license-consistency.sh

echo "==> Checking Python environment and lock drift"
"${PYTHON_BIN}" -m pip check
PYTHON_BIN="${PYTHON_BIN}" bash scripts/check-requirements-locks.sh

echo "==> Auditing locked runtime and development graphs"
"${PYTHON_BIN}" -m pip_audit -r requirements.lock
"${PYTHON_BIN}" -m pip_audit -r requirements-dev.lock

echo "==> Running Python lint, format, and type gates"
"${PYTHON_BIN}" -m ruff check compresso/ tests/
"${PYTHON_BIN}" -m ruff format --check compresso/ tests/
"${PYTHON_BIN}" -m mypy compresso/ --ignore-missing-imports --no-error-summary

echo "==> Running Python unit tests"
"${PYTHON_BIN}" -m pytest tests/unit -q --maxfail=1 --disable-warnings

echo "==> Checking Node"
if ! command -v node >/dev/null 2>&1; then
  echo "Missing node. Install Node 24.x, or Node 22.x for fast local development." >&2
  exit 1
fi

node_major="$(node -p "process.versions.node.split('.')[0]")"
if [[ "${node_major}" != "24" && "${node_major}" != "22" ]]; then
  echo "Node 24.x is supported; Node 22.x is accepted only in fast mode. Found $(node --version)." >&2
  exit 1
fi
if [[ "${MODE}" == "full" ]] && ! node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major > 24 || (major === 24 && minor >= 10) ? 0 : 1)'; then
  echo "Full verification requires Node 24.10.0 or newer. Found $(node --version)." >&2
  exit 1
fi
echo "Node $(node --version)"

echo "==> Installing and verifying frontend dependencies"
cd "${FRONTEND_DIR}"
npm ci
rm -rf coverage
npm run lint
npx vitest run --coverage
node scripts/check-coverage-ratchet.mjs
npm run build:publish

if [[ "${MODE}" == "full" ]]; then
  cd "${ROOT_DIR}"

  echo "==> Linting GitHub Actions workflows"
  if ! command -v actionlint >/dev/null 2>&1; then
    echo "Full verification requires actionlint." >&2
    exit 1
  fi
  actionlint -shellcheck=

  echo "==> Running integration and release contract tests"
  "${PYTHON_BIN}" -m pytest -m integrationtest -q --maxfail=1 --disable-warnings
  "${PYTHON_BIN}" -m pytest \
    tests/unit/test_release_workflows.py \
    tests/unit/test_verify_release_integrity.py \
    -q --maxfail=1 --disable-warnings

  echo "==> Testing locked release tooling"
  cd "${RELEASE_DIR}"
  npm ci
  npm test

  echo "==> Building and inspecting a clean wheel"
  cd "${ROOT_DIR}"
  rm -rf build dist
  "${PYTHON_BIN}" -m build --no-isolation --skip-dependency-check --wheel
  wheel_count="$(find dist -maxdepth 1 -type f -name '*.whl' | wc -l | tr -d ' ')"
  if [[ "${wheel_count}" != "1" ]]; then
    echo "Expected exactly one wheel, found ${wheel_count}." >&2
    exit 1
  fi
  wheel_path="$(find dist -maxdepth 1 -type f -name '*.whl' | sort | head -n 1)"
  "${PYTHON_BIN}" -m zipfile -l "${wheel_path}" | grep 'compresso/webserver/public/index.html' >/dev/null
  if "${PYTHON_BIN}" -m zipfile -l "${wheel_path}" | grep 'compresso/webserver/frontend/' >/dev/null; then
    echo "Wheel unexpectedly contains frontend source files." >&2
    exit 1
  fi
  if "${PYTHON_BIN}" -m zipfile -l "${wheel_path}" | grep 'node_modules' >/dev/null; then
    echo "Wheel unexpectedly contains node_modules." >&2
    exit 1
  fi

  if [[ "${SKIP_E2E:-0}" != "1" ]]; then
    cd "${FRONTEND_DIR}"
    echo "==> Installing Playwright browsers"
    if [[ "$(uname -s)" == "Linux" ]]; then
      npx playwright install --with-deps chromium firefox webkit
    else
      npx playwright install chromium firefox webkit
    fi
    echo "==> Running mocked and packaged live-backend browser tests"
    npm run test:e2e:run
    PYTHON_BIN="${PYTHON_BIN}" npm run test:e2e:live:run
  else
    skip_gate "Playwright mocked and packaged live-backend tests (SKIP_E2E=1)"
  fi
else
  skip_gate "GitHub Actions syntax lint (immutable pin policy still checked)"
  skip_gate "integration tests"
  skip_gate "release tooling and release contract tests"
  skip_gate "clean wheel artifact validation"
  skip_gate "Playwright mocked and packaged live-backend tests"
fi

echo "==> Verification complete (${MODE})"
if [[ "${#SKIPPED_GATES[@]}" -gt 0 ]]; then
  echo "==> Skipped gates:"
  printf '  - %s\n' "${SKIPPED_GATES[@]}"
else
  echo "==> Skipped gates: none"
fi
