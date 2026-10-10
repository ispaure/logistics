"""Verify Perforce console connection and interactive command forwarding."""

import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from commonUtils.osUtils import OS
from features.perforce import actions, detection, ui_contributions
from models.folder_entry import FolderEntry
from models.local_folder import LocalFolder


class PerforceConsoleTests(unittest.TestCase):
    def test_server_paths_and_port_keep_argument_boundaries_and_launch_failure(self):
        import shlex
        with TemporaryDirectory(prefix="p4 server ' ") as tmp:
            root = Path(tmp)
            (root/'remoteConfig.ini').write_text('[Perforce]\np4d_path=bin/p4 daemon\ndata_path=server data\nport=27182\n')
            with patch.object(actions, 'get_os', return_value=OS.LINUX), patch.object(
                    actions.cmdShellWrapper, 'exec_cmd', return_value=False) as launch:
                self.assertFalse(actions.launch_server(LocalFolder(root)))
            self.assertEqual(shlex.split(launch.call_args.args[0]),
                [str((root/'bin/p4 daemon').resolve()), '-C1', '-r', str((root/'server data').resolve()), '-p', '27182'])

    @unittest.skipUnless(os.name == 'posix', 'POSIX shell integration requires a POSIX host')
    def test_console_forwards_arguments_and_keeps_connection_in_interactive_shell(self):
        with TemporaryDirectory(prefix="p4 console ' ") as tmp:
            root = Path(tmp)
            (root / 'remoteConfig.ini').write_text(
                '[Perforce]\np4d_path=p4d\ndata_path=data\nport=27182\n'
            )
            client = root / 'p4'
            client.write_text('#!/bin/sh\nprintf "ARG:%s\\n" "$@"\n')
            client.chmod(0o755)
            folder = LocalFolder(root)
            with patch.object(actions, 'get_os', return_value=OS.LINUX), patch.object(
                actions.cmdShellWrapper, 'exec_cmd', return_value=[]
            ) as launch:
                self.assertTrue(actions.open_console(folder))
            command = launch.call_args.args[0]
            self.assertEqual(launch.call_args.kwargs, {'in_new_window': True, 'cwd': root})
            result = subprocess.run(
                ['bash', '-lc', command], cwd=root,
                input='p4 -u marca passwd\np4 info "argument with spaces"\nexit\n',
                text=True, capture_output=True, timeout=10
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('ARG:-p\nARG:localhost:27182\nARG:-u\nARG:marca\nARG:passwd', result.stdout)
            self.assertIn('ARG:info\nARG:argument with spaces', result.stdout)
            with patch.object(ui_contributions, 'get_os', return_value=OS.LINUX):
                buttons = ui_contributions._get_actions(FolderEntry('server', local=folder))
            self.assertEqual(buttons[1].name, 'Open P4 Console (Port: 27182)')
            self.assertTrue(buttons[1].enabled)

    def test_missing_client_and_system_client_fallback(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'remoteConfig.ini').write_text('[Perforce]\nport=27182\n')
            folder = LocalFolder(root)
            with patch.object(detection.shutil, 'which', return_value='/usr/bin/p4'):
                self.assertEqual(detection.get_p4_client_path(folder), '/usr/bin/p4')
            with patch.object(detection.shutil, 'which', return_value=None), patch.object(
                actions, 'get_os', return_value=OS.LINUX
            ), patch.object(actions.cmdShellWrapper, 'exec_cmd') as launch:
                self.assertFalse(actions.open_console(folder))
                launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
