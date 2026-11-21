"""Git-specific terminal selection without changing shared launcher defaults."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

import shlex
import subprocess
import sys


def launch(command, cwd, preference='System default'):
    if preference == 'iTerm' and sys.platform == 'darwin':
        text = f'cd -- {shlex.quote(cwd)} && {command}'
        escaped = text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        script = 'tell application "iTerm"\nactivate\nset w to (create window with default profile)\ntell current session of w\nwrite text "' + escaped + '"\nend tell\nend tell'
        subprocess.Popen(['osascript', '-e', script])
        return True
    from commonUtils.integrations.wrappers.cmdShellWrapper.terminal import exec_cmd_new_window
    return exec_cmd_new_window(command, cwd)
