"""Portable option validation and dependency boundaries for both hosts."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import os
from pathlib import Path
import subprocess
import sys
import unittest

from features.rclone.transfers.transfer_options import TransferOptions, validate_excludes


class TransferOptionTests(unittest.TestCase):
    def test_mobile_backend_imports_do_not_initialize_the_app_or_ui(self):
        code = '''
import sys
from features.rclone.mobile.cloud import CloudClient
from features.rclone.localcrypt.mobile.copies import LocalCryptCopies
from features.rclone.localcrypt.mobile.resources import CryptFiles
from features.rclone.transfers.mobile.jobs import MirrorJobs
from features.rclone.mobile.credential_vault import ProtectedVault
assert not any(name.startswith(('PySide', 'toga', 'mobile.app',
    'mobile.provider_ui', 'features.rclone.configuration', 'config')) for name in sys.modules)
'''
        result = subprocess.run([sys.executable, '-c', code],
            env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2])),
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_scope_uses_desktop_folder_inference(self):
        from features.rclone.transfers.scope import push_scope, pull_name
        self.assertEqual(push_scope('Books'), ('Books', ''))
        self.assertEqual(push_scope('Comics', 'Books', specific=True), ('Books', 'Comics'))
        self.assertEqual(pull_name('Books'), 'Books')
        with self.assertRaises(ValueError):
            push_scope('../outside')

    def test_import_does_not_load_desktop_configuration_or_ui(self):
        code = '''
import sys
from features.rclone.transfers.transfer_options import TransferOptions
assert TransferOptions().copy_links
assert not any(name.startswith(('PySide', 'toga', 'rubicon', 'features.rclone.configuration', 'config'))
               for name in sys.modules)
'''
        result = subprocess.run([sys.executable, '-c', code],
            env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2])),
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_options_reject_invalid_switches_limits_and_injected_filters(self):
        for values in ({'copy_links': 'false'}, {'track_renames': 1}, {'bw_limit': 0},
                       {'bw_limit': -1}, {'bw_limit': True}, {'excludes': ['*.pdf\n--delete-excluded']}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                TransferOptions(**values)
        options = TransferOptions(bw_limit='12', excludes=[' *.pdf ', '*.pdf'])
        self.assertEqual(options.bw_limit, 12)
        self.assertEqual(options.excludes, ('*.pdf',))
        self.assertEqual(validate_excludes([]), ())
