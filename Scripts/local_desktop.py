"""Logistics desktop prerequisites; shared backend machinery owns no app policy."""
import json
import subprocess
import sys
import time


def main():
    started = time.monotonic()
    from PySide6.QtCore import qVersion
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
