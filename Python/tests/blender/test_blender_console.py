"""Native terminal launch quoting, process identity and preset environment."""

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
import shlex
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory

from commonUtils.testing.stages import TestStage
from features.blender.presets import console_launch

TEST_STAGE = TestStage.REGRESSION


class BlenderConsoleTests(unittest.TestCase):
    def test_terminal_arguments_preserve_spaces_and_shell_characters(self):
        args = ['/a path/python', "a'file;$().py", '/tmp/request.json']
        with patch.object(console_launch.os, 'name', 'posix'):
            self.assertEqual(shlex.split(console_launch.terminal_command(args)), args)
        with patch.object(console_launch.os, 'name', 'nt'):
            self.assertTrue(console_launch.terminal_command(args).startswith('powershell.exe -NoProfile -EncodedCommand '))

    def test_real_runner_inherits_console_and_records_actual_child_pid(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / 'child.json'
            arguments = []
            children = []
            transferred = []
            def command(args):
                arguments.extend(map(str,args));return 'terminal-command'
            def terminal(_command, **kwargs):
                request = Path(arguments[-1])
                transferred.append(json.loads(request.read_text())['environment'])
                children.append(subprocess.Popen(arguments, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                return []
            script = 'import os,json,time;from pathlib import Path;Path('+repr(str(output))+').write_text(json.dumps({"pid":os.getpid(),"config":os.environ["BLENDER_USER_CONFIG"]}));time.sleep(.2)'
            # Match a directly launched Blender executable. A Windows venv's Python
            # redirector starts a second process before executing the test script.
            executable = sys._base_executable if os.name == 'nt' else sys.executable
            with patch.object(console_launch,'bundled_python',return_value=Path(sys.executable)), \
                    patch.object(console_launch,'terminal_command',side_effect=command), \
                    patch.object(console_launch.cmdShellWrapper,'exec_cmd',side_effect=terminal):
                process = console_launch.launch_in_console([executable,'-c',script],
                    dict(BLENDER_USER_CONFIG=str(root/'preset'),UNRELATED_SECRET='do not transfer'),root,'5.2.2')
            try:
                children[0].wait(timeout=5)
                info = json.loads(output.read_text())
                self.assertEqual(info['pid'],process.pid)
                self.assertEqual(info['config'],str(root/'preset'))
                self.assertNotIn('UNRELATED_SECRET',transferred[0])
                self.assertEqual(process.poll(),0)
                self.assertFalse(Path(process.workspace.name).exists())
            finally:
                if children[0].poll() is None:children[0].kill();children[0].wait()
                process.workspace.cleanup()

    def test_missing_terminal_does_not_launch_blender(self):
        with patch.object(console_launch,'bundled_python',return_value=Path(sys.executable)), \
                patch.object(console_launch.cmdShellWrapper,'exec_cmd',return_value=False):
            with self.assertRaisesRegex(ValueError,'Could not open'):
                console_launch.launch_in_console(['blender'],{},Path.cwd(),'5.2.2')
