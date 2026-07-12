#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "${ROOT_DIR}"

# Local reusable workflows use a relative path and are intentionally excluded.
# Every third-party action must use a full 40-character commit SHA; the trailing
# version comment remains available to humans and Dependabot.
violations=""
while IFS= read -r match; do
  action_ref="${match#*uses:}"
  action_ref="${action_ref#"${action_ref%%[![:space:]]*}"}"
  action_ref="${action_ref%%[[:space:]#]*}"
  if [[ "${action_ref}" == ./* ]]; then
    continue
  fi

  ref="${action_ref##*@}"
  if [[ ! "${ref}" =~ ^[0-9a-f]{40}$ ]]; then
    violations+="${match}"$'\n'
  fi
done < <(
  find .github/workflows -type f \( -name '*.yml' -o -name '*.yaml' \) \
    -exec grep -HnE 'uses:[[:space:]]*[^[:space:]#]+' {} + || true
)

if [[ -n "${violations}" ]]; then
  echo "Third-party GitHub Actions must be pinned to a full commit SHA:" >&2
  echo "${violations}" >&2
  exit 1
fi

echo "All third-party GitHub Actions are pinned to immutable commits."
