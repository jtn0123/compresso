#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK_MODE="${1:-}" 

if [[ -n "${CHECK_MODE}" && "${CHECK_MODE}" != "--check" ]]; then
  echo "Usage: $0 [--check]"
  exit 2
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

python3 -m venv "${TMP_DIR}/venv"
# shellcheck disable=SC1091
source "${TMP_DIR}/venv/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r "${ROOT_DIR}/requirements.txt"
pip freeze --all | sort > "${TMP_DIR}/constraints.txt"
python -m pip install -r "${ROOT_DIR}/requirements-dev.txt" -c "${TMP_DIR}/constraints.txt"
pip freeze --all | sort > "${TMP_DIR}/constraints-dev.txt"

if [[ "${CHECK_MODE}" == "--check" ]]; then
  diff -u "${ROOT_DIR}/constraints.txt" "${TMP_DIR}/constraints.txt"
  diff -u "${ROOT_DIR}/constraints-dev.txt" "${TMP_DIR}/constraints-dev.txt"
  echo "Constraint files are up-to-date."
else
  cp "${TMP_DIR}/constraints.txt" "${ROOT_DIR}/constraints.txt"
  cp "${TMP_DIR}/constraints-dev.txt" "${ROOT_DIR}/constraints-dev.txt"
  echo "Updated constraints.txt and constraints-dev.txt"
fi
