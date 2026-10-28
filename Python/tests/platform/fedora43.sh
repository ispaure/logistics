#!/usr/bin/env bash
set -euo pipefail

# Run inside the official Fedora 43 container with this repository at /workspace.
dnf install -y git python3-pip mesa-libEGL mesa-libGL libxkbcommon dbus-libs \
    fontconfig dejavu-sans-fonts dejavu-sans-mono-fonts glib2 libstdc++ pulseaudio-libs \
    nspr nss alsa-lib libdrm libXcomposite libXdamage libXrandr libxkbfile \
    libXtst libXScrnSaver cups-libs gtk3 tar gzip openssl-libs
# Qt WebEngine runs only synthetic test pages in this disposable root container.
export QTWEBENGINE_DISABLE_SANDBOX=1
python3 -m pip install uv
uv venv --python 3.12.2 --seed /tmp/logistics-platform-venv
git config --global --add safe.directory /workspace
git config --global --add safe.directory /workspace/Python/commonUtils
export LOGISTICS_MANAGER_CHECKOUT=/tmp/logistics-build-deployment-manager
/tmp/logistics-platform-venv/bin/python logistics_build/install_build_manager.py --from-pin "$LOGISTICS_MANAGER_CHECKOUT"
/tmp/logistics-platform-venv/bin/python Python/tests/run_platform_checks.py --install
/tmp/logistics-platform-venv/bin/python -m unittest discover -s .github/scripts -p 'test_*.py' -v
