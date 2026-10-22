#!/bin/sh
# Run from any directory; double-click to deploy to all saved iOS devices.
set -eu
MOBILE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -x "$MOBILE_DIR/.tools/go/bin/go" ]; then
    PATH="$MOBILE_DIR/.tools/go/bin:$PATH"
    export PATH
fi
if [ ! -x "$MOBILE_DIR/.venv/bin/python" ]; then
    echo 'Create mobile_build/.venv with Python 3.12 and install briefcase==0.4.5; see docs/development/mobile-launchers.md.' >&2
    exit 1
fi
if [ "$#" -eq 0 ]; then
    set -- deploy-all --allow-wired
fi
exec "$MOBILE_DIR/.venv/bin/python" "$MOBILE_DIR/device_tools.py" "$@"
