"""Stdlib-only child launched inside the native terminal by Blender's Python."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import json
import os
from pathlib import Path
import subprocess
import sys
import time


def run(request_path):
    folder = request_path.parent
    request = json.loads(request_path.read_text(encoding='utf-8'))
    if time.time() > request['deadline']:
        raise ValueError('This console launch expired; launch Blender again from Logistics')
    def status(value):
        if not folder.is_dir():
            return
        temporary = folder / 'status.tmp'
        temporary.write_text(json.dumps(value), encoding='utf-8')
        os.replace(temporary, folder / 'status.json')
    try:
        env = {k: v for k, v in os.environ.items() if not k.startswith('BLENDER_')
               and k not in {'PYTHONHOME', 'PYTHONPATH', 'LOGISTICS_BLENDER_ADDONS'}}
        env.update(request['environment'])
        child = subprocess.Popen(request['command'], cwd=request['cwd'], env=env)
        status(dict(pid=child.pid, returncode=None))
        request_path.unlink(missing_ok=True)
        code = child.wait()
        status(dict(pid=child.pid, returncode=code))
        print(f'Blender exited with code {code}.', flush=True)
        return code
    except Exception as error:
        status(dict(error=str(error)))
        raise


if __name__ == '__main__':
    raise SystemExit(run(Path(sys.argv[1])))
