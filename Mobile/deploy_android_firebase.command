#!/bin/sh
# Double-click to authenticate, build/sign, then choose whether to distribute.
set -eu
MOBILE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PATH="$MOBILE_DIR/.tools/go/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
exec "$MOBILE_DIR/.venv/bin/python" "$MOBILE_DIR/firebase_deploy.py" "$@"
