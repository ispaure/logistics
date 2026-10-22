#!/bin/sh
# Run both device installs and both beta distributions, sequentially.
set -eu
MOBILE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PATH="$MOBILE_DIR/.tools/go/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
export PATH
exec "$MOBILE_DIR/.venv/bin/python" "$MOBILE_DIR/deploy_all.py" "$@"
