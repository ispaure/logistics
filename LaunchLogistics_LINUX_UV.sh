#!/usr/bin/env bash
set -euo pipefail

echo "Launching Logistics..."
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

# ensure uv exists
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

PY_DIR="$SCRIPT_DIR/Python"
VENV_DIR="$SCRIPT_DIR/venv"

cd "$PY_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  uv venv "$VENV_DIR"
fi

# Activate so pip installs into the venv
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# Install deps (fast if already satisfied)
uv pip install -r "$PY_DIR/requirements.txt"

python "$PY_DIR/launch.py"

echo
read -r -p "Press Enter to close..." _
