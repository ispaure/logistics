#!/bin/sh
# Run the optional DOM check with explicit, disposable browser configuration.
set -eu

task_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
task_node_root="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/node"

if [ -z "${LOGISTICS_NODE:-}" ]; then
    if command -v node >/dev/null 2>&1; then
        LOGISTICS_NODE=$(command -v node)
    elif [ -x "$task_node_root/bin/node" ]; then
        LOGISTICS_NODE="$task_node_root/bin/node"
    else
        echo 'Node is required: install it or set LOGISTICS_NODE to its executable.' >&2
        exit 2
    fi
fi
export LOGISTICS_NODE

if [ -z "${NODE_PATH:-}" ] && [ -f "$task_node_root/node_modules/playwright/package.json" ]; then
    export NODE_PATH="$task_node_root/node_modules"
fi
if [ -z "${LOGISTICS_CHROME:-}" ] && [ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" ] &&
        [ -x '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' ]; then
    export LOGISTICS_CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
fi

exec "${PYTHON:-python3}" "$task_root/dev.py" test mobile test_chat_dom.py "$@"
