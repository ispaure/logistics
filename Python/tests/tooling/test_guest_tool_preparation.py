"""Logistics pins feed reusable preparation without changing backend receipts."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from build_manager.guest_tools import LINUX_BOOTSTRAP, WINDOWS_PREPARE, linux_parameters
from logistics_build import vm_backend, windows_backend


class GuestToolPreparationTests(unittest.TestCase):
    def test_linux_catalog_keeps_existing_runtime_and_uv_pins(self):
        catalog = json.loads(Path(vm_backend.__file__).with_name('build_manager_tools.json').read_text())
        self.assertEqual(linux_parameters(**catalog['linux']), dict(python='3.12.2', uv_version='0.12.18'))
        self.assertEqual(vm_backend.BOOTSTRAP, LINUX_BOOTSTRAP)

    def test_windows_preparation_delegates_with_project_pins_and_keeps_receipt(self):
        with TemporaryDirectory() as directory, patch.object(windows_backend, 'Parallels') as transport:
            client = transport.return_value
            client.start.return_value = dict(uuid='test-vm', status='stopped')
            client.powershell.return_value = json.dumps(dict(workspace='owned', python='python', uv='uv', git='git',
                runtime={'version': '3.12.2'}, guestArchitecture='ARM64', session=1))
            output = Path(directory) / 'prepared.json'
            result = windows_backend.prepare('selected-vm', output)
            client.start.assert_called_once_with('selected-vm')
            vm, script, parameters = client.powershell.call_args.args
            self.assertEqual((vm, script), ('test-vm', WINDOWS_PREPARE))
            self.assertEqual(parameters['python'], 'cpython-3.12.2-windows-x86_64')
            self.assertEqual(parameters['guest_architecture'], 'ARM64')
            self.assertEqual(parameters['python_architecture'], 'x86_64')
            self.assertEqual(parameters['tools']['uv']['version'], '0.12.18')
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
