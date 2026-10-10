"""Logistics software policy; reusable verification/download mechanics live in commonUtils."""
from configparser import Error as ConfigError
import json
from pathlib import Path

import config
from commonUtils.streams.downloads import DownloadSpec
from commonUtils.fileTypes.iniType import INIFile
from commonUtils.osUtils import Arch, OS, get_arch, get_os


MANIFEST_PATH = Path(__file__).resolve().parents[1] / 'software_manifest.json'
RCLONE_CONFIG_PATH = Path(__file__).resolve().parents[1] / 'features' / 'rclone' / 'config.ini'


def get_software(tool):
    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    if tool == 'rclone':
        platform = {OS.WIN: 'windows', OS.MAC: 'osx', OS.LINUX: 'linux'}.get(get_os())
        arch = {Arch.X86_64: 'amd64', Arch.ARM_64: 'arm64'}.get(get_arch())
        key = f'{platform}-{arch}'
        if key not in manifest[tool]:
            raise ValueError(f'Unsupported rclone platform: {get_os().value}/{get_arch().value}')
        entry = dict(manifest[tool][key])
        if RCLONE_CONFIG_PATH.is_file():
            settings = INIFile(RCLONE_CONFIG_PATH).read()
            for field in ('version', 'url', 'sha256', 'installed_sha256', 'archive_member', 'path'):
                value = settings.get(key, field + '_str')
                if value is not None:
                    entry[field] = value
    else:
        entry = dict(manifest[tool])
    relative_path = Path(entry.pop('path'))
    root = config.LogisticsConfig().path_logistics_software
    destination = root / relative_path
    if relative_path.is_absolute() or not destination.resolve().is_relative_to(root.resolve()):
        raise ValueError('Software destination must stay inside the configured Software folder')
    return DownloadSpec(**entry), destination


def ensure_software(tool, *, install=False):
    from commonUtils.ui.download import ensure_download
    from commonUtils import ui
    try:
        spec, destination = get_software(tool)
        return ensure_download(spec, destination, install=install)
    except (OSError, ValueError, ConfigError) as error:
        ui.display_msg_box_ok('Software Unavailable', str(error))
        return None
