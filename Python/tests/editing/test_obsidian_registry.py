"""Registry publication keeps format/mode and preserves originals on failure."""

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from features.obsidian import actions
from features.obsidian.actions import _write_registry


class RegistryWrites(unittest.TestCase):
    def test_preserves_mode_and_utf8_serialization(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'obsidian.json'
            path.write_text('{}')
            path.chmod(0o640)
            _write_registry(path, {'vaults': {'é': {}}})
            self.assertEqual(path.read_bytes(), '{"vaults":{"é":{}}}\n'.encode())
            if os.name != 'nt':
                self.assertEqual(path.stat().st_mode & 0o777, 0o640)
            self.assertEqual(json.loads(path.read_text()), {'vaults': {'é': {}}})

    def test_failed_publication_keeps_original_and_cleans_stage(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'obsidian.json'
            path.write_bytes(b'{}\n')
            with patch('commonUtils.persistence.atomic.os.replace', side_effect=PermissionError('denied')):
                with self.assertRaisesRegex(RuntimeError, 'Could not write Obsidian registry'):
                    _write_registry(path, {'vaults': {}})
            self.assertEqual(path.read_bytes(), b'{}\n')
            self.assertEqual(list(path.parent.iterdir()), [path])


class VaultRegistration(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        root = Path(directory)
        self.registry_path = root / 'config' / 'obsidian.json'
        vault_path = root / 'vault'
        (vault_path / '.obsidian').mkdir(parents=True)
        self.vault = actions.Directory(vault_path)
        self.enterContext(patch.object(actions, 'get_registry_path', return_value=self.registry_path))
        self.enterContext(patch.object(actions, 'is_obsidian_installed', return_value=True))
        self.running = self.enterContext(patch.object(actions, 'is_obsidian_running', return_value=False))
        self.launch = self.enterContext(patch.object(actions, '_open_uri'))
        self.show_error = self.enterContext(patch.object(actions, '_show_error'))

    def test_external_write_during_registration_staging_survives(self):
        external = b'{"vaults":{"other":{"path":"/another/vault"}},"unknown":true}\n'
        fsync = os.fsync

        def external_write(fd):
            fsync(fd)
            self.registry_path.write_bytes(external)

        for initial in (b'{"vaults":{}}\n', None):
            with self.subTest(initial=initial):
                self.registry_path.unlink(missing_ok=True)
                if initial is not None:
                    self.registry_path.parent.mkdir(parents=True, exist_ok=True)
                    self.registry_path.write_bytes(initial)
                self.launch.reset_mock()
                self.show_error.reset_mock()
                with patch('commonUtils.persistence.atomic.os.fsync', side_effect=external_write):
                    opened = actions.open_vault(self.vault)
                self.assertEqual(self.registry_path.read_bytes(), external)
                self.assertFalse(opened)
                self.launch.assert_not_called()
                self.assertIn('registry changed', self.show_error.call_args.args[0])
                self.assertEqual(list(self.registry_path.parent.iterdir()), [self.registry_path])

    def test_launch_failure_keeps_registration_and_retry_reuses_it(self):
        self.registry_path.parent.mkdir()
        existing = {'vaults': {'other': {'path': str(self.vault.path.parent / 'other'), 'custom': 1}},
                    'unknown': {'keep': True}}
        self.registry_path.write_text(json.dumps(existing), encoding='utf-8')
        self.registry_path.chmod(0o640)
        self.launch.side_effect = OSError('launch failed')
        self.assertFalse(actions.open_vault(self.vault))
        saved = self.registry_path.read_bytes()
        registry = json.loads(saved)
        self.assertEqual(registry['unknown'], existing['unknown'])
        self.assertEqual(registry['vaults']['other'], existing['vaults']['other'])
        new_id, = registry['vaults'].keys() - existing['vaults'].keys()
        self.assertEqual(registry['vaults'][new_id]['path'], str(self.vault.path.resolve()))
        if os.name != 'nt':
            self.assertEqual(self.registry_path.stat().st_mode & 0o777, 0o640)
        self.launch.side_effect = None
        self.running.reset_mock()
        self.assertTrue(actions.open_vault(self.vault))
        self.running.assert_not_called()
        self.launch.assert_called_with(f'obsidian://open?vault={new_id}')
        self.assertEqual(self.registry_path.read_bytes(), saved)

    def test_first_registration_creates_missing_registry(self):
        self.assertTrue(actions.open_vault(self.vault))
        registry = json.loads(self.registry_path.read_bytes())
        vault_id, = registry['vaults']
        self.assertEqual(registry['vaults'][vault_id]['path'], str(self.vault.path.resolve()))
        self.launch.assert_called_once_with(f'obsidian://open?vault={vault_id}')
