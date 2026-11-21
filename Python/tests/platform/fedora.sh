#!/usr/bin/env bash

# Copyright (c) 2026 Marc-Andre Voyer (marcandre.voyer@gmail.com)
# SPDX-License-Identifier: MIT

set -euo pipefail

# Run in fedora.Containerfile's prepared, disposable CI container at /workspace.
# Local rootless validation uses the same image without disabling its sandbox.
export QTWEBENGINE_DISABLE_SANDBOX=1
mkdir -p tmp/test-results
results=${LOGISTICS_PLATFORM_RESULTS:-$(mktemp -d tmp/test-results/fedora.XXXXXX)}
mkdir -p "$results"
export LOGISTICS_TEST_TIMING_DIRECTORY="$results/test-timings"
run_step() {
    local name=$1 limit=$2 started=$SECONDS code=0
    shift 2
    echo "Fedora: starting $name"
    timeout --kill-after=10s "$limit" "$@" || code=$?
    echo "Fedora: $name finished in $((SECONDS - started))s (exit $code)" | tee -a "$results/fedora-setup.log"
    return "$code"
}
workspace=$(mktemp -d "${TMPDIR:-/tmp}/logistics-platform.XXXXXX")
trap 'rm -rf "$workspace"' EXIT
run_step interpreter 300s uv venv --python "${TEST_PYTHON:-3.12.2}" --seed "$workspace/environment"
git config --global --add safe.directory /workspace
git config --global --add safe.directory /workspace/Python/commonUtils
export LOGISTICS_MANAGER_CHECKOUT="$workspace/manager"
python="$workspace/environment/bin/python"
run_step manager 180s "$python" logistics_build/install_build_manager.py --from-pin "$LOGISTICS_MANAGER_CHECKOUT"
run_step dependencies 600s "$python" Python/tests/run_platform_checks.py --install --prepare-only
if [[ ${GITHUB_ACTIONS:-} == true ]]; then
    run_step worker-budget 30s "$python" -c 'import os; from build_manager.test_workers import configure; workers = min(2, len(os.sched_getaffinity(0))); configure(dict(per_platform=workers, host=workers))'
fi
# Dependency preparation above exercises real crypt setup. Retain its required
# coverage when invoking validation separately for useful setup/test timings.
export LOGISTICS_REQUIRE_LOCALCRYPT_TESTS=1
export SSL_CERT_FILE
SSL_CERT_FILE=$("$python" -c 'import certifi; print(certifi.where())')
status=0
run_step platform 5400s "$python" Python/tests/run_platform_checks.py --results-dir "$results" || status=1
run_step release-tooling 300s "$python" -m unittest discover -s .github/scripts -p 'test_*.py' -v || status=1
exit "$status"
