#!/bin/bash

# Display an initiation message
echo "Initiating Logistics"

echo "Detecting Python 3.12.2 installation..."
if ! command -v pyenv &> /dev/null; then
    echo "pyenv not found! Installing..."
    if ! command -v brew &> /dev/null; then
        echo "Homebrew not found. Please install Homebrew first and rerun this script."
        exit 1
    fi
    brew install pyenv
    echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.bashrc
    echo 'eval "$(pyenv init --path)"' >> ~/.bashrc
    source ~/.bashrc
fi

if ! pyenv versions | grep -q "3.12.2"; then
    echo "Installing Python 3.12.2..."
    pyenv install 3.12.2
fi

pyenv global 3.12.2
PYTHON_PATH=$(pyenv which python3)

echo "Python 3.12.2 ready!"

# Set up the virtual environment (fixed location for Logistics)
VENV_DIR="$HOME/Server/Logistics-VENV"
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)

# Verify Server folder exists
if [ ! -d "$HOME/Server" ]; then
    echo "ERROR: Expected folder $HOME/Server does not exist."
    echo "Please create it before running this script."
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up virtual environment..."
    "$PYTHON_PATH" -m venv "$VENV_DIR"
    echo "Virtual environment created!"
else
    echo "Virtual environment already exists."
fi

# Activate the virtual environment and install dependencies
source "$VENV_DIR/bin/activate"
echo "Installing dependencies..."
python -m pip install --upgrade pip
pip install -r "$SCRIPT_DIR/Python/requirements.txt"

# Launch the main script
echo "Executing Logistics Script"
python "$SCRIPT_DIR/Python/launch.py"

deactivate
echo "Script execution complete."
