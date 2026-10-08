"""Logistics software policy; reusable verification/download mechanics live in commonUtils."""
import json
from pathlib import Path

import config
from commonUtils.downloads import DownloadSpec
from commonUtils.osUtils import Arch, OS, get_arch, get_os


MANIFEST_PATH = Path(__file__).resolve().parents[1] / 'software_manifest.json'


def get_software(tool):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    if tool == 'rclone':
        platform = {OS.WIN: 'windows', OS.MAC: 'osx', OS.LINUX: 'linux'}.get(get_os())
        arch = {Arch.X86_64: 'amd64', Arch.ARM_64: 'arm64'}.get(get_arch())
        key = f'{platform}-{arch}'
        if key not in manifest[tool]:
            raise ValueError(f'Unsupported rclone platform: {get_os().value}/{get_arch().value}')
        entry = dict(manifest[tool][key])
    else:
        entry = dict(manifest[tool])
    relative_path = Path(entry.pop('path'))
    root = config.LogisticsConfig().path_logistics_software
    return DownloadSpec(**entry), root / relative_path


def ensure_software(tool, *, install=False):
    from commonUtils.ui.download import ensure_download
    from commonUtils import ui
    try:
        spec, destination = get_software(tool)
        return ensure_download(spec, destination, install=install)
    except (OSError, ValueError) as error:
        ui.display_msg_box_ok('Software Unavailable', str(error))
        return None
