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

    def test_windows_attempt_reclaims_only_disposable_tools_after_evidence_transfer(self):
        tool_paths = {'environment', 'cache', 'python', 'tools', 'downloads'}
        for reuse, transfer_fails, cleanup_fails in (
            (False, False, False), (True, False, False), (False, True, False), (False, False, True),
        ):
            with self.subTest(reuse=reuse, transfer_fails=transfer_fails, cleanup_fails=cleanup_fails), \
                    TemporaryDirectory() as directory:
                root = Path(directory)
                source = {'commit': 'fixture'}
                prepared = dict(vm='test-vm', status='prepared', token='a' * 32, workspace=r'C:\bm\fixture',
                                python='python', git='git', runtime={}, guestArchitecture='ARM64')
                reference = root / 'prepared.json' if reuse else None
                if reference:
                    reference.write_text(json.dumps(prepared))
                args = argparse.Namespace(vm='test-vm', prepared=reference, results=root / 'attempt',
                                          snapshot=root, source_identity=source, manager_checkout=None,
                                          pattern='', shutdown=False)
                with patch.object(windows_backend, 'Parallels') as transport, \
                        patch.object(windows_backend, 'prepare', return_value=prepared) as prepare, \
                        patch.object(windows_backend, 'WindowsGuest') as guest_class, \
                        patch.object(windows_backend, 'source_zip', return_value=b'source'), \
                        patch.object(windows_backend.signal, 'signal'):
                    transport.return_value.start.return_value = dict(uuid='test-vm', status='running')
                    guest = guest_class.return_value
                    guest.call_idempotent.return_value = json.dumps(dict(runtime={}, git='git', path=''))
                    guest.run.return_value = 0
                    evidence = []

                    def collect(paths, destination):
                        if transfer_fails:
                            raise OSError('evidence transfer failed')
                        report = destination / paths[0] / 'manager/result.json'
                        report.parent.mkdir(parents=True)
                        report.write_text(json.dumps(dict(source=source, backend='Parallels Windows',
                                                          status='passed', phases=[])))
                        evidence.append(report)

                    def remove(paths):
                        self.assertTrue(evidence[0].is_file())
                        self.assertEqual(tool_paths.intersection(paths), set() if reuse else tool_paths)
                        if cleanup_fails:
                            raise OSError('cleanup failed')

                    guest.collect.side_effect = collect
                    guest.remove_paths.side_effect = remove
                    self.assertEqual(windows_backend._run_attempt(args), int(transfer_fails or cleanup_fails))
                    if reuse:
                        prepare.assert_not_called()
                    else:
                        prepare.assert_called_once_with('test-vm', args.results / 'prepared.json')
                    if transfer_fails:
                        guest.remove_paths.assert_not_called()
                    else:
                        guest.remove_paths.assert_called_once()
                    result = json.loads((args.results / 'result.json').read_text())
                    self.assertEqual(result['public_tool_cache_retained'], reuse or transfer_fails or cleanup_fails)
