"""Resolve and launch Calibre using argument lists rather than shell commands."""

from pathlib import Path
import shutil
import subprocess

import config
from commonUtils import zipUtils
from commonUtils.osUtils import OS, get_os


def launch_library(path: Path) -> None:
    platform = get_os()
    if platform == OS.WIN:
        executable = config.LogisticsConfig().path_logistics_software_win / 'Calibre2/calibre.exe'
    elif platform == OS.MAC:
        executable = Path('/Applications/calibre.app/Contents/MacOS/calibre')
        if not executable.is_file():
            archive = config.LogisticsConfig().path_logistics_software_mac / 'calibre.app.zip'
            if not zipUtils.unzip_file(archive, Path('/Applications')):
                raise OSError('Could not install the bundled Calibre application')
    elif platform == OS.LINUX:
        executable = shutil.which('calibre')
        if executable is None:
            flatpak = shutil.which('flatpak')
            if flatpak is None:
                raise FileNotFoundError('Calibre is not installed')
            result = subprocess.run([flatpak, 'info', 'com.calibre_ebook.calibre'],
                                    capture_output=True, timeout=5)
            if result.returncode:
                raise FileNotFoundError('The Calibre Flatpak is not installed')
            arguments = [flatpak, 'run', 'com.calibre_ebook.calibre']
        else:
            arguments = [executable]
    else:
        raise OSError(f'Unsupported Calibre platform: {platform}')
    if platform in (OS.WIN, OS.MAC):
        if not executable.is_file():
            raise FileNotFoundError(f'Calibre executable not found: {executable}')
        arguments = [str(executable)]
    subprocess.Popen([*arguments, '--with-library', str(path)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
