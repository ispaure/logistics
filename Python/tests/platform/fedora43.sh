#!/usr/bin/env bash
set -euo pipefail

# Run inside the official Fedora 43 container with this repository at /workspace.
dnf install -y git python3-pip mesa-libEGL mesa-libGL libxkbcommon dbus-libs \
    fontconfig dejavu-sans-fonts glib2 libstdc++ pulseaudio-libs tar gzip openssl-libs
python3 -m pip install uv
uv venv --python 3.12.2 --seed /tmp/logistics-platform-venv
git config --global --add safe.directory /workspace
git config --global --add safe.directory /workspace/Python/commonUtils
/tmp/logistics-platform-venv/bin/python Python/tests/run_platform_checks.py --install
