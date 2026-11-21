"""Historical personal paths used by Logistics; no automatic account discovery."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from pathlib import Path
import os
from commonUtils.filesystem import files as fileUtils
from commonUtils.runtime.platform import get_os, OS


def get_marc_dropbox_root() -> Path:
    if get_os() == OS.WIN:
        if os.path.isdir('B:\\Yagi Dropbox'):
            return Path('B:\\Yagi Dropbox\\Marc-Andre Voyer')
    return fileUtils.get_user_home_dir() / 'Yagi Dropbox' / 'Marc-Andre Voyer'
