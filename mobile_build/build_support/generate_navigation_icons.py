"""Bundle the desktop destination artwork for native mobile bars and rails.

Run with the desktop development interpreter; mobile needs no Qt dependency.
"""
import argparse
from base64 import b64encode
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Python'))


def render_icons():
    from commonUtils.ui import pyside as qt
    from desktop.sidebar import DestinationIcon

    app = qt.QApplication.instance() or qt.QApplication([])
    palette = app.palette()
    palette.setColor(qt.QPalette.ColorRole.ButtonText, qt.QColor('black'))
    app.setPalette(palette)
    result = {}
    for name, desktop in (('nav_home', 'home'), ('nav_notebooks', 'notebooks'), ('nav_files', 'hub'),
                          ('nav_documents', 'documents'), ('nav_chat', 'lm'),
                          ('nav_settings', 'settings')):
        pixmap = DestinationIcon(desktop).pixmap(qt.QSize(72, 72),
            qt.QIcon.Mode.Normal, qt.QIcon.State.Off)
        data = qt.QByteArray()
        buffer = qt.QBuffer(data)
        buffer.open(qt.QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buffer, 'PNG')
        result[name] = b64encode(bytes(data)).decode('ascii')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'Python/mobile/hub_icons.py'
    original = path.read_text(encoding='utf-8')
    updated = original
    for name, data in render_icons().items():
        entry = f"    '{name}': '{data}',\n"
        pattern = rf"    '{name}': '[^']+',\n"
        if re.search(pattern, updated):
            updated = re.sub(pattern, lambda match: entry, updated)
        else:
            updated = updated.replace('ICONS = {\n', 'ICONS = {\n' + entry, 1)
    if args.check:
        if updated != original:
            parser.exit(1, 'Navigation icons are stale; run mobile_build/generate_navigation_icons.py.\n')
        print('Navigation icons match desktop destination artwork.')
    else:
        path.write_text(updated, encoding='utf-8')


if __name__ == '__main__':
    main()
