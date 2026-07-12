#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

failures=0

require_text() {
  local file="$1"
  local text="$2"
  if ! grep -Fq "${text}" "${file}"; then
    echo "Missing '${text}' in ${file}" >&2
    failures=$((failures + 1))
  fi
}

require_text LICENSE "GNU GENERAL PUBLIC LICENSE"
require_text setup.py 'license="GPL-3.0-only"'
require_text compresso/webserver/package.json '"license": "GPL-3.0-only"'
require_text compresso/webserver/frontend/package.json '"license": "GPL-3.0-only"'
require_text .github/release/package.json '"license": "GPL-3.0-only"'
require_text docs/LICENSING.md "GPL-3.0-only"
require_text LICENSES/MIT.txt "Permission is hereby granted"
require_text THIRD_PARTY_NOTICES.md "software bill of materials"

while IFS= read -r file; do
  if ! grep -Fq "Permission is hereby granted" "${file}"; then
    echo "Historical copyright restriction lacks its accompanying permission notice: ${file}" >&2
    failures=$((failures + 1))
  fi
done < <(
  find compresso docs -type f \( -name '*.py' -o -name '*.md' \) \
    -exec grep -FIl "Copyright (C) Josh Sunnex - All Rights Reserved" {} +
  grep -FIl "Copyright (C) Josh Sunnex - All Rights Reserved" setup.py README.md || true
)

if ((failures > 0)); then
  exit 1
fi

echo "Repository license metadata and retained notices are consistent."
