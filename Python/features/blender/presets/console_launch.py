"""Launch Blender in a real terminal using commonUtils, retaining its actual PID."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import base64
import json
import os
from pathlib import Path
import shlex
import sys
from tempfile import TemporaryDirectory
import time

from commonUtils.integrations.wrappers import cmdShellWrapper
from commonUtils.runtime.updates.transaction import pid_alive


def bundled_python(executable, version):
    executable = Path(executable)
    base = executable.parent
    if sys.platform == 'darwin':
        base = base.parent / 'Resources'
    folder = base / '.'.join(version.split('.')[:2]) / 'python/bin'
    candidates = [folder / 'python.exe', folder / 'python3.exe', folder / 'python3']
    candidates += sorted(folder.glob('python3.*'))
    result = next((p for p in candidates if p.is_file() and not p.name.endswith('-config')), None)
    if result is None:
        raise ValueError('Blender’s bundled Python is missing; reinstall this Blender version before using its console')
    return result


def terminal_command(arguments):
    if os.name == 'nt':
        # A fixed encoded PowerShell command avoids CMD expansion of %, &, etc.
        command = '& ' + ' '.join("'" + str(a).replace("'", "''") + "'" for a in arguments)
        return 'powershell.exe -NoProfile -EncodedCommand ' + base64.b64encode(command.encode('utf-16-le')).decode()
    return shlex.join(map(str, arguments))


class ConsoleProcess:
    def __init__(self, pid, workspace):
        self.pid, self.workspace = pid, workspace
        self.returncode = None

    def poll(self):
        if self.returncode is None:
            path = Path(self.workspace.name) / 'status.json'
            try:
                self.returncode = json.loads(path.read_text())['returncode']
            except (OSError, ValueError, KeyError):
                pass
            if self.returncode is None and not pid_alive(self.pid):
                self.returncode = -1
            if self.returncode is not None:
                self.workspace.cleanup()
        return self.returncode


def launch_in_console(command, environment, cwd, version):
    python = bundled_python(command[0], version)
    workspace = TemporaryDirectory(prefix='logistics-blender-console-')
    folder = Path(workspace.name)
    # The terminal has its own login environment. Transfer only Blender's
    # explicit launch settings, never unrelated credentials from Logistics.
    overrides = {key: value for key, value in environment.items()
                 if key.startswith('BLENDER_') or key in {'LOGISTICS_BLENDER_ADDONS', 'PYTHONUNBUFFERED'}}
    request = dict(command=command, environment=overrides, cwd=str(cwd),
                   deadline=time.time() + 20)
    (folder / 'request.json').write_text(json.dumps(request), encoding='utf-8')
    arguments = [python, '-I', Path(__file__).with_name('console_runner.py'), folder / 'request.json']
    try:
        result = cmdShellWrapper.exec_cmd(terminal_command(arguments), in_new_window=True,
                                         wait_for_output=False, cwd=str(cwd))
        if result is False:
            raise ValueError('Could not open a console/terminal window')
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            status = folder / 'status.json'
            if status.is_file():
                info = json.loads(status.read_text(encoding='utf-8'))
                if info.get('error'):
                    raise ValueError(info['error'])
                return ConsoleProcess(info['pid'], workspace)
            time.sleep(0.05)
        raise ValueError('The terminal did not start Blender. Check terminal/automation permissions and try again.')
    except Exception:
        workspace.cleanup()
        raise
