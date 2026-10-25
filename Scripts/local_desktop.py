"""Logistics desktop prerequisites; shared backend machinery owns no app policy."""
import json
from pathlib import Path
import subprocess
import sys
import time


def verify_qt():
    try:
        import PySide6.QtWebEngineCore
    except ImportError:
        if sys.platform.startswith('linux'):
            import PySide6
            for library in Path(PySide6.__file__).parent.rglob('libQt6WebEngineCore.so.6'):
                result = subprocess.run(['ldd', str(library)], text=True, capture_output=True, timeout=30)
                for line in result.stdout.splitlines():
                    if 'not found' in line:
                        print('Missing Qt native dependency: ' + line.strip(), flush=True)
        raise


def main():
    started = time.monotonic()
    from PySide6.QtCore import qVersion
    verify_qt()
    from commonUtils.runtime.streams.downloads import provision
    from services.software import get_software
    executable = provision(*get_software('rclone'))
    version = subprocess.check_output([str(executable), 'version'], text=True, timeout=30).splitlines()[0]
    print(json.dumps(dict(qt=qVersion(), rclone=version, rclone_path=str(executable),
                          preparation_seconds=time.monotonic() - started)))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print('Desktop prerequisite failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
