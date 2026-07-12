#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.13}"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TEMP_DIR}"' EXIT

cp \
  "${ROOT_DIR}/requirements.txt" \
  "${ROOT_DIR}/requirements-dev.txt" \
  "${ROOT_DIR}/requirements.lock" \
  "${ROOT_DIR}/requirements-dev.lock" \
  "${TEMP_DIR}/"

compile_lock() {
  local input_file="$1"
  local output_file="$2"
  shift 2

  (
    cd "${TEMP_DIR}"
    "${PYTHON_BIN}" -m piptools compile \
      --generate-hashes \
      --output-file="${output_file}" \
      --quiet \
      --strip-extras \
      "$@" \
      "${input_file}"
  )

  if ! cmp -s "${TEMP_DIR}/${output_file}" "${ROOT_DIR}/${output_file}"; then
    echo "${output_file} is stale. Regenerate it with:" >&2
    echo "  ${PYTHON_BIN} -m piptools compile --generate-hashes --output-file=${output_file} --strip-extras $* ${input_file}" >&2
    diff -u "${ROOT_DIR}/${output_file}" "${TEMP_DIR}/${output_file}" || true
    return 1
  fi
}

compile_lock requirements.txt requirements.lock
compile_lock requirements-dev.txt requirements-dev.lock --allow-unsafe

echo "Python requirement locks match their source inputs."
