#!/bin/sh
# Double-click to authenticate, build/sign, then choose whether to distribute.
set -eu
MOBILE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PATH="$MOBILE_DIR/.tools/go/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
cd "$MOBILE_DIR/.."
exec "$MOBILE_DIR/.venv/bin/python" -m mobile_build.deployment.firebase_deploy "$@"
