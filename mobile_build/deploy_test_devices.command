#!/bin/sh
# Double-click for the small PySide deployment window.
set -eu
MOBILE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$MOBILE_DIR/.."
exec "$MOBILE_DIR/../.venv/bin/python" -m mobile_build.deployment.deploy_ui "$@"
