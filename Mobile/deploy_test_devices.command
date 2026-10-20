#!/bin/sh
# Double-click for the small PySide deployment window.
set -eu
MOBILE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$MOBILE_DIR/../.venv/bin/python" "$MOBILE_DIR/deploy_ui.py" "$@"
