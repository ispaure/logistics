"""Real local repositories prove source isolation without provider credentials."""
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from Scripts.build_snapshots import identity, materialize


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='snapshot-contract-')
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.root = self.directory / 'project'
        self.root.mkdir()
        self.git(self.root, 'init', '-q')
        (self.root / 'Python/commonUtils').mkdir(parents=True)
        self.shared = self.root / 'Python/commonUtils'
        self.git(self.shared, 'init', '-q')
        (self.shared / 'library.py').write_text('VERSION = 1\n')
        self.commit(self.shared)
        (self.root / '.gitignore').write_text('.private/\n')
        (self.root / 'source.py').write_text('VERSION = 1\n')
        self.commit(self.root)

    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], text=True,
            stderr=subprocess.DEVNULL, env=dict(os.environ, GIT_AUTHOR_NAME='Fixture',
                GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_NAME='Fixture',
                GIT_COMMITTER_EMAIL='fixture@example.invalid')).strip()

    def commit(self, root):
        self.git(root, 'add', '.')
        self.git(root, 'commit', '-qm', 'fixture')

    def test_exact_history_working_edits_and_shared_pin_exclude_ignored_inputs(self):
        original = identity(self.root, 'HEAD')
        (self.root / 'source.py').write_text('VERSION = 2\n')
        (self.root / 'new.py').write_text('NEW = True\n')
        (self.root / '.private').mkdir()
        (self.root / '.private/credential').write_text('synthetic-secret')
        destination = self.directory / 'snapshot'
        selected = materialize(self.root, destination)
        self.assertTrue(selected['dirty'])
        self.assertNotEqual(original['fingerprint'], selected['fingerprint'])
        self.assertEqual((destination / 'source.py').read_text(), 'VERSION = 2\n')
        self.assertTrue((destination / 'new.py').is_file())
        self.assertFalse((destination / '.private').exists())
        self.assertEqual(self.git(destination / 'Python/commonUtils', 'rev-parse', 'HEAD'), selected['commonUtils_commit'])
        self.assertEqual(self.git(destination, 'show', 'HEAD:source.py'), 'VERSION = 1')
        self.assertEqual(json.loads((destination / '.manager-source.json').read_text())['source'], selected)
        self.assertEqual(materialize(self.root, destination), selected)
        (destination / 'source.py').write_text('unexpected modification')
        with self.assertRaisesRegex(ValueError, 'different source'):
            materialize(self.root, destination)
        committed = self.directory / 'committed'
        materialize(self.root, committed, 'HEAD')
        self.assertFalse(self.git(committed, 'status', '--porcelain'))
        self.assertFalse((committed / 'new.py').exists())

    def test_uncommitted_shared_changes_block_incomplete_snapshot(self):
        (self.shared / 'library.py').write_text('VERSION = 2\n')
        with self.assertRaisesRegex(ValueError, 'commonUtils'):
            materialize(self.root, self.directory / 'snapshot')
        self.assertFalse((self.directory / 'snapshot').exists())
