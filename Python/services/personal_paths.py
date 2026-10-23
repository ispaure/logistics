"""Historical personal paths used by Logistics; no automatic account discovery."""
from pathlib import Path
import os
from commonUtils.filesystem import files as fileUtils
from commonUtils.runtime.platform import get_os, OS


def get_marc_dropbox_root() -> Path:
    if get_os() == OS.WIN:
        if os.path.isdir('B:\\Yagi Dropbox'):
            return Path('B:\\Yagi Dropbox\\Marc-Andre Voyer')
    return fileUtils.get_user_home_dir() / 'Yagi Dropbox' / 'Marc-Andre Voyer'
