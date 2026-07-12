#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"

# Local reusable workflows use a relative path and are intentionally excluded.
# Every third-party action must use a full 40-character commit SHA; the trailing
# version comment remains available to humans and Dependabot.
violations="$({
  rg -n --pcre2 \
    'uses:\s*(?!\./)[^\s#]+@(?![0-9a-f]{40}(?:\s|#|$))[^\s#]+' \
    .github/workflows \
    --glob '*.yml' \
    --glob '*.yaml' || true
})"

if [[ -n "${violations}" ]]; then
  echo "Third-party GitHub Actions must be pinned to a full commit SHA:" >&2
  echo "${violations}" >&2
  exit 1
fi

echo "All third-party GitHub Actions are pinned to immutable commits."
