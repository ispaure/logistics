"""Registry publication keeps format/mode and preserves originals on failure."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

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
            with patch('commonUtils.persistence.os.replace', side_effect=PermissionError('denied')):
                with self.assertRaisesRegex(RuntimeError, 'Could not write Obsidian registry'):
                    _write_registry(path, {'vaults': {}})
            self.assertEqual(path.read_bytes(), b'{}\n')
            self.assertEqual(list(path.parent.iterdir()), [path])
