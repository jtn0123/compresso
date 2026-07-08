#!/usr/bin/env bash
set -euo pipefail

IMAGE_REF="${1:-compresso:local-preflight}"
REPORT_PATH="${REPORT_PATH:-trivy-report.json}"

if ! command -v trivy >/dev/null 2>&1; then
  echo "Trivy is not installed; skipping vulnerability grouping."
  echo "Install Trivy and rerun: scripts/trivy-group-report.sh ${IMAGE_REF}"
  exit 0
fi

echo "==> Scanning ${IMAGE_REF} with Trivy"
trivy image --format json --output "${REPORT_PATH}" "${IMAGE_REF}"

echo "==> Grouped findings"
python3 - "${REPORT_PATH}" <<'PY'
import json
import sys
from collections import defaultdict

report_path = sys.argv[1]
with open(report_path, "r", encoding="utf-8") as handle:
    report = json.load(handle)

groups = defaultdict(lambda: defaultdict(int))

def classify(target, vulnerability):
    target_lower = (target or "").lower()
    pkg_path = (vulnerability.get("PkgPath") or "").lower()

    if "node_modules" in target_lower or "node_modules" in pkg_path:
        if "/npm/" in target_lower or "/npm/" in pkg_path:
            return "npm-bundled"
        return "app-owned"
    if "python" in target_lower or "site-packages" in pkg_path:
        return "python"
    if target_lower.endswith("dockerfile"):
        return "app-owned"
    return "base-image"

for result in report.get("Results", []):
    target = result.get("Target", "")
    for vulnerability in result.get("Vulnerabilities", []) or []:
        bucket = classify(target, vulnerability)
        package = vulnerability.get("PkgName") or "unknown"
        severity = vulnerability.get("Severity") or "UNKNOWN"
        groups[bucket][f"{package} [{severity}]"] += 1

if not groups:
    print("No vulnerabilities reported.")
    raise SystemExit(0)

for bucket in ("base-image", "npm-bundled", "python", "app-owned"):
    findings = groups.get(bucket, {})
    if not findings:
        continue
    print(f"\n{bucket}:")
    for package, count in sorted(findings.items()):
        print(f"  {package}: {count}")
PY

echo "Raw Trivy JSON: ${REPORT_PATH}"
