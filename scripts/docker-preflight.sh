#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.13}"
IMAGE_TAG="${IMAGE_TAG:-compresso:local-preflight}"

cd "${ROOT_DIR}"

echo "==> Building fresh Python wheel artifact"
rm -rf build dist
"${PYTHON_BIN}" -m build --no-isolation --skip-dependency-check --wheel

wheel_count="$(find dist -maxdepth 1 -type f -name "*.whl" | wc -l | tr -d ' ')"
if [[ "${wheel_count}" != "1" ]]; then
  echo "Expected exactly one wheel in dist/, found ${wheel_count}." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Docker is not available; skipping image build."
  echo "    Wheel artifact was still rebuilt and checked."
  exit 0
fi

echo "==> Building Docker image ${IMAGE_TAG}"
docker build -f docker/Dockerfile -t "${IMAGE_TAG}" .

echo "==> Inspecting Docker image"
docker image inspect "${IMAGE_TAG}" >/dev/null

echo "==> Docker preflight complete"
