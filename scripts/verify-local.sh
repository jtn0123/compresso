#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="${ROOT_DIR}/compresso/webserver/frontend"
PYTHON_BIN="${PYTHON_BIN:-python3.13}"

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

echo "==> Checking Python environment"
"${PYTHON_BIN}" -m pip check
if ! command -v pip-audit >/dev/null 2>&1; then
  echo "Missing pip-audit. Install requirements-dev.txt before running verify-local." >&2
  exit 1
fi
pip-audit -r "${ROOT_DIR}/requirements.lock"

echo "==> Running Python unit tests"
cd "${ROOT_DIR}"
"${PYTHON_BIN}" -m pytest tests/unit -q --maxfail=1 --disable-warnings

echo "==> Checking Node"
if ! command -v node >/dev/null 2>&1; then
  echo "Missing node. Install Node 24.x, or Node 22.x for local development." >&2
  exit 1
fi

node_major="$(node -p "process.versions.node.split('.')[0]")"
if [[ "${node_major}" != "24" && "${node_major}" != "22" ]]; then
  echo "Node 24.x is the supported baseline; Node 22.x is also accepted locally. Found $(node --version)." >&2
  exit 1
fi
echo "Node $(node --version)"

echo "==> Installing frontend dependencies"
cd "${FRONTEND_DIR}"
npm ci

echo "==> Running frontend tests"
npm run test -- --run

rm -rf coverage

echo "==> Running frontend lint"
npm run lint

echo "==> Running frontend coverage gate"
npx vitest run --coverage

echo "==> Local verification complete"
