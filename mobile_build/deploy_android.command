#!/bin/sh
# Double-click to stage, build, install and launch on a connected Android device.
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
exec "$MOBILE_DIR/.venv/bin/python" "$MOBILE_DIR/android_deploy.py" "$@"
