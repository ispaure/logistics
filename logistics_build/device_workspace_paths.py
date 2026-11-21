"""Roots for legacy and newly located managed device workspaces."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path

LEGACY_DEVICE_WORKSPACES = Path('mobile_build/.tools/build-manager/workspaces/devices')
DEVICE_WORKSPACES = Path('tmp/build/mobile')
