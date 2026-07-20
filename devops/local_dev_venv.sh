#!/usr/bin/env bash
###
# File: local_dev_venv.sh
# Project: devops
#
# Bootstrap a local development venv using the same hash-locked dependency
# graph that CI installs. Mirrors the "Option 2: Pip" flow documented in
# docs/DEVELOPING.md - see that file for the authoritative walkthrough.
###
#
# After running this script you can run compresso with the following commands:
#
#   source venv/bin/activate
#   export HOME_DIR="${PWD}/dev_environment"
#   compresso
#

set -euo pipefail

script_path=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_root=$(readlink -e "${script_path}/..")

pushd "${project_root}" || exit 1

# Ensure we have created a venv
if [[ ! -e venv/bin/activate ]]; then
    python3.13 -m venv venv
fi

# Activate the venv
source venv/bin/activate

# Install the hash-locked dependency graph (runtime + dev) - the same
# graph CI audits and installs. Do not install from the unpinned
# requirements*.txt files here.
python3 -m pip install --upgrade pip
python3 -m pip install --require-hashes -r requirements-dev.lock

# Build the frontend into compresso/webserver/public, then install the
# project in editable mode
devops/frontend_install.sh
python3 -m pip install --editable .

popd || exit 1
