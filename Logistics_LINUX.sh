#!/bin/bash

# ===== AUTOMATIC SUDO ELEVATION =====
if [ "$EUID" -ne 0 ]; then
    sudo "$0" "$@"
    exit $?
fi

# ===== ENSURE SUDOERS CONFIGURATION =====
SCRIPT_PATH=$(realpath "$0")
USERNAME=$(logname)  # Correctly gets the real username

SUDOERS_LINE="$USERNAME ALL=(ALL) NOPASSWD: $SCRIPT_PATH"

if ! grep -qF "$SUDOERS_LINE" /etc/sudoers; then
    echo "Configuring passwordless sudo for user: $USERNAME..."
    echo "$SUDOERS_LINE" | sudo tee -a /etc/sudoers > /dev/null
    echo "Sudoers updated! Restarting script without password prompt..."
    exec sudo -u "$USERNAME" "$SCRIPT_PATH"
    exit $?
fi

# ===== SYSTEM SETUP =====
echo "Initiating Ally Tools"

# Detect Linux Distribution (Fedora, Bazzite, or Ubuntu)
DISTRO=$(lsb_release -si 2>/dev/null || cat /etc/os-release | grep ^ID= | cut -d= -f2)

# Default package manager and installation command (initialization)
if [[ "$DISTRO" == "Ubuntu" ]]; then
    # Ubuntu Installation (apt)
    echo "Detected Ubuntu - using apt for package management"
    PACKAGE_MANAGER="apt"
    INSTALL_CMD="sudo apt install -y"

    # Install common dependencies
    $INSTALL_CMD bash flatpak git jq libfuse2 rsync unzip zenity

    # Detect and install Python 3.12 using pyenv
    if ! command -v pyenv &> /dev/null; then
        echo "pyenv not found! Installing..."
        if ! command -v brew &> /dev/null; then
            echo "Homebrew not found. Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
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

elif [[ "$DISTRO" == "Fedora" ]]; then
    # Fedora Installation (dnf)
    echo "Detected Fedora - using dnf for package management"
    PACKAGE_MANAGER="dnf"
    INSTALL_CMD="sudo dnf install -y"

    # Install common dependencies
    $INSTALL_CMD bash flatpak git jq libfuse2 rsync unzip zenity

    # Detect and install Python 3.12 using pyenv
    if ! command -v pyenv &> /dev/null; then
        echo "pyenv not found! Installing..."
        if ! command -v brew &> /dev/null; then
            echo "Homebrew not found. Installing Homebrew first..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
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

elif [[ "$DISTRO" == "Bazzite" ]]; then
    # Bazzite Installation (rpm-ostree)
    echo "Detected Bazzite - using rpm-ostree for package management"
    PACKAGE_MANAGER="rpm-ostree"
    INSTALL_CMD="sudo rpm-ostree install"

    # Core tools
    sudo rpm-ostree install \
        bash flatpak git jq libfuse rsync unzip zenity

    # Python 3.12 + venv support
    sudo rpm-ostree install \
        python3.12 \
        python3.12-venv \
        python3-pip

    # ===== Qt / PySide6 / XCB / Graphics deps =====
    sudo rpm-ostree install \
        libxcb \
        xcb-util \
        xcb-util-cursor \
        xcb-util-wm \
        xcb-util-image \
        xcb-util-keysyms \
        libX11 \
        libXext \
        libXrender \
        libXi \
        libXcursor \
        libXfixes \
        libXrandr \
        libXinerama \
        libxkbcommon \
        libxkbcommon-x11 \
        mesa-libGL \
        mesa-libEGL \
        fontconfig \
        freetype

    echo ""
    echo "⚠️ rpm-ostree packages installed."
    echo "⚠️ You MUST reboot before running the Python app."
    echo ""

    PYTHON_PATH=$(command -v python3.12)
fi

# Set up the virtual environment
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
VENV_DIR="$SCRIPT_DIR/venv"

# Ensure pyenv version is active before creating the virtual environment
echo "Activating pyenv environment and setting Python version"
source ~/.bashrc
pyenv activate 3.12.2

# Remove broken venv if necessary
if [ -d "$VENV_DIR" ] && [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "Virtual environment seems broken. Removing and recreating..."
    rm -rf "$VENV_DIR"
fi

# Create the virtual environment using the pyenv Python version
if [ ! -d "$VENV_DIR" ]; then
    echo "Setting up virtual environment with Python 3.12.2..."
    "$PYTHON_PATH" -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"

# Install dependencies
pip install --upgrade pip
pip install -r "$SCRIPT_DIR/Python/requirements.txt"

# Launch the main script
python "$SCRIPT_DIR/Python/launch.py"

# Deactivate the virtual environment
deactivate
echo "Script execution complete."
exec bash
