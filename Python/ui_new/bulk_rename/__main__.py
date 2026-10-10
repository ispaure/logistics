"""Launch with PYTHONPATH=<package-parent> python -m ui_new.bulk_rename [folder]."""
import argparse
from pathlib import Path
import sys
from commonUtils.ui import pyside as qt
from . import open_bulk_rename


def main():
    parser = argparse.ArgumentParser(description='Preview and safely batch-rename selected files and folders.')
    parser.add_argument('directory', nargs='?', type=Path, default=None)
    parser.add_argument('--paths', nargs='+', type=Path, help='Start with only these explicitly selected paths')
    args = parser.parse_args()
    app = qt.QApplication.instance() or qt.QApplication(sys.argv[:1])
    window = open_bulk_rename(args.directory or (None if args.paths else Path.cwd()), paths=args.paths or (), standalone=True)
    window.show()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
