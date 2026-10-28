"""Shared Release archive forwards every explicitly configured signing profile."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from logistics_build import manager_packages
from mobile_build.deployment import testflight_deploy, testflight_tools


class ArchiveSigningTests(unittest.TestCase):
    def test_all_manual_profiles_reach_archive_but_not_preview(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / 'build/testflight/123'
            workspace.mkdir(parents=True)
            (workspace / 'release.json').write_text('{}')
            arguments = ['--profile', 'main', '--inbox-profile', 'inbox',
                         '--widget-profile', 'widgets', '--widget-actions-profile', 'actions']
            with patch.object(testflight_deploy, 'ROOT', root), \
                    patch.object(testflight_deploy, 'reserve_build', return_value='123'), \
                    patch.object(testflight_tools, 'archive_fingerprint', return_value='a'*64), \
                    patch.object(manager_packages.subprocess, 'run') as run:
                manager_packages.archive(root/'state.json', arguments)
            preview, archive = [call.args[0] for call in run.call_args_list]
            self.assertNotIn('--profile', preview)
            self.assertEqual(archive[-len(arguments):], arguments)
            self.assertEqual(json.loads((root/'state.json').read_text())['build_number'], '123')
