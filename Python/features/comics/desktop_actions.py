"""Open and reveal local items through the platform's file applications."""

from pathlib import Path
import subprocess
from urllib.parse import quote
from commonUtils.osUtils import OS, get_os
from commonUtils.ui import pyside as qt


def open_default(path):
    if not qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(str(Path(path).absolute()))):
        raise RuntimeError('Could not open the default application')


def reveal_label():
    return {OS.MAC: 'Reveal in Finder', OS.WIN: 'Reveal in Explorer'}.get(get_os(), 'Reveal in Linux File Explorer')


def reveal(path):
    path = Path(path).absolute()
    platform = get_os()
    if platform == OS.MAC:
        subprocess.run(['open', '-R', str(path)], check=True)
    elif platform == OS.WIN:
        subprocess.Popen(['explorer', '/select,', str(path)])
    else:
        # Desktop file managers implementing the standard interface select the file.
        try:
            result = subprocess.run(['dbus-send', '--session', '--dest=org.freedesktop.FileManager1',
                                 '--type=method_call', '--print-reply', '/org/freedesktop/FileManager1',
                                 'org.freedesktop.FileManager1.ShowItems',
                                 'array:string:' + quote(path.as_uri(), safe=':/%'), 'string:'], capture_output=True, check=False, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            result = None
        if result is None or result.returncode:
            open_default(path if path.is_dir() else path.parent)
