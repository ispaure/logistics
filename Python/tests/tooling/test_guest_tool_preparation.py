"""Logistics pins feed reusable preparation without changing backend receipts."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager.guest_tools import LINUX_BOOTSTRAP, WINDOWS_PREPARE, linux_parameters
from logistics_build import vm_backend, windows_backend


class GuestToolPreparationTests(unittest.TestCase):
    def test_portable_download_trust_preserves_custom_policy_and_restores_environment(self):
        from logistics_build.notebook_validation import download_certificates
        import certifi
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'failed download'):
                with download_certificates():
                    self.assertEqual(os.environ['SSL_CERT_FILE'], certifi.where())
                    raise RuntimeError('failed download')
            self.assertNotIn('SSL_CERT_FILE', os.environ)
        with patch.dict(os.environ, {'SSL_CERT_FILE': '/custom/roots.pem'}):
            with download_certificates():
                self.assertEqual(os.environ['SSL_CERT_FILE'], '/custom/roots.pem')
            self.assertEqual(os.environ['SSL_CERT_FILE'], '/custom/roots.pem')

    def test_notebook_guest_selection_preserves_full_coverage_and_timeout(self):
        from logistics_build.notebook_validation import arguments, command
        parser = argparse.ArgumentParser()
        arguments(parser, windows=True)
        args = parser.parse_args(['--notebook-profile', 'full', '--notebook-rendering', 'all',
                                  '--notebook-go', 'C:\\Tools\\go.exe'])
        argv, timeout = command(args, 'python.exe', 'reports', windows=True)
        self.assertIn('full', argv)
        self.assertEqual(argv[argv.index('--go') + 1], 'C:\\Tools\\go.exe')
        self.assertEqual(argv[argv.index('--latency-mode') + 1], 'enforce')
        from Python.tests.notebooks.notebook_platform_probe import PROBES
        self.assertEqual(timeout, sum(limit * (4 if renderer else 1)
                                      for _, limit, renderer in PROBES.values()) + 30)

    def test_notebook_linux_focus_forwards_noncore_checks(self):
        from logistics_build.notebook_validation import arguments, command
        parser = argparse.ArgumentParser()
        arguments(parser)
        args = parser.parse_args(['--notebook-probe', 'encrypted-storage',
                                  '--notebook-probe', 'mobile-laptop'])
        argv, timeout = command(args, 'python', 'reports')
        self.assertEqual(argv.count('--probe'), 2)
        self.assertIn('mobile-laptop', argv)
        self.assertEqual(timeout, 510)

    def test_linux_catalog_keeps_existing_runtime_and_uv_pins(self):
        catalog = json.loads(Path(vm_backend.__file__).with_name('build_manager_tools.json').read_text())
        self.assertEqual(linux_parameters(**catalog['linux']), dict(python='3.12.2', uv_version='0.13.4'))
        self.assertEqual(vm_backend.BOOTSTRAP, LINUX_BOOTSTRAP)

    def test_windows_preparation_delegates_with_project_pins_and_keeps_receipt(self):
        with TemporaryDirectory() as directory, patch.object(windows_backend, 'Parallels') as transport:
            client = transport.return_value
            client.start.return_value = dict(uuid='test-vm', status='stopped')
            client.powershell.side_effect = lambda vm, script, parameters, **kwargs: json.dumps(dict(
                token=parameters['token'], workspace='owned', python='python', uv='uv', git='git',
                runtime={'version': '3.12.2'}, guestArchitecture='ARM64', session=1))
            output = Path(directory) / 'prepared.json'
            result = windows_backend.prepare('selected-vm', output)
            client.start.assert_called_once_with('selected-vm')
            vm, script, parameters = client.powershell.call_args.args
            self.assertEqual((vm, script), ('test-vm', WINDOWS_PREPARE))
            self.assertEqual(parameters['python'], 'cpython-3.12.2-windows-x86_64')
            self.assertEqual(parameters['guest_architecture'], 'ARM64')
            self.assertEqual(parameters['python_architecture'], 'x86_64')
            self.assertEqual(parameters['tools']['uv']['version'], '0.13.4')
            self.assertEqual(result, json.loads(output.read_text()))
            self.assertEqual(result['status'], 'prepared')
            self.assertEqual(result['original_state'], 'stopped')
            self.assertFalse(result['tests_run'])

    def test_failed_preparation_retains_owned_recovery_identity(self):
        with TemporaryDirectory() as directory, patch.object(windows_backend, 'Parallels') as transport:
            client = transport.return_value
            client.start.return_value = dict(uuid='test-vm', status='stopped')
            client.powershell.side_effect = RuntimeError('download failed')
            output = Path(directory) / 'prepared.json'
            with self.assertRaisesRegex(RuntimeError, 'download failed'):
                windows_backend.prepare('selected-vm', output)
            result = json.loads(output.read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['vm'], 'test-vm')
            self.assertEqual(result['token'], client.powershell.call_args.args[2]['token'])
            self.assertFalse(result['tests_run'])
