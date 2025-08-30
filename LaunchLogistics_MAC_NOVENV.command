#!/bin/bash

# Display an initiation message
echo "Initiating Logistics"

# Detect Python 3.12.2 (or at least 3.12.x)
echo "Detecting Python 3.12..."
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 not found. Please install Python 3.12.2 (https://www.python.org/downloads/) and rerun this script."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1)
if [[ "$PYTHON_VERSION" != "Python 3.12."* ]]; then
    echo "ERROR: Expected Python 3.12.2 (or compatible 3.12.x). Found: $PYTHON_VERSION"
    echo "Please install Python 3.12.2 from https://www.python.org/downloads/"
    exit 1
fi

PYTHON_PATH=$(command -v python3)
echo "Using $PYTHON_PATH ($PYTHON_VERSION)"

# Verify Server folder exists
if [ ! -d "$HOME/Server" ]; then
    echo "ERROR: Expected folder $HOME/Server does not exist."
    echo "Please create it before running this script."
    exit 1
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# Install dependencies globally (not in a venv)
echo "Installing dependencies (system-wide for this user)..."
"$PYTHON_PATH" -m pip install --user --upgrade pip
"$PYTHON_PATH" -m pip install --user -r "$SCRIPT_DIR/Python/requirements.txt"

# Launch the main script
echo "Executing Logistics Script"
"$PYTHON_PATH" "$SCRIPT_DIR/Python/launch.py"

echo "Script execution complete."
