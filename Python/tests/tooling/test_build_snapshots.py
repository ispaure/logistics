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

    def test_committed_ref_alias_reuses_only_exact_verified_snapshot(self):
        destination = self.directory/'committed'
        before = materialize(self.root, destination, 'HEAD')
        selected = materialize(self.root, destination, before['logistics_commit'])
        self.assertEqual(selected['fingerprint'], before['fingerprint'])
        self.assertEqual(selected['selection'], before['logistics_commit'])
        self.assertEqual(json.loads((destination/'.manager-source.json').read_text())['source'], before)
        (destination/'source.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'different source'):
            materialize(self.root, destination, before['logistics_commit'])

    def test_uncommitted_shared_changes_block_incomplete_snapshot(self):
        (self.shared / 'library.py').write_text('VERSION = 2\n')
        with self.assertRaisesRegex(ValueError, 'commonUtils'):
            materialize(self.root, self.directory / 'snapshot')
        self.assertFalse((self.directory / 'snapshot').exists())

    @unittest.skipIf(os.name == 'nt', 'Windows executable mode is not POSIX')
    def test_executable_change_invalidates_cache_and_is_preserved(self):
        before = identity(self.root)
        (self.root/'source.py').chmod(0o755)
        self.assertNotEqual(identity(self.root)['fingerprint'], before['fingerprint'])
        destination = self.directory/'snapshot'
        materialize(self.root, destination)
        self.assertTrue((destination/'source.py').stat().st_mode & 0o100)
        (destination/'source.py').chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'different source'):
            materialize(self.root, destination)

    def test_internal_link_is_preserved_and_external_link_blocks_source(self):
        (self.root/'link.py').symlink_to('source.py')
        destination = self.directory/'snapshot'
        materialize(self.root, destination)
        self.assertTrue((destination/'link.py').is_symlink())
        self.assertEqual(os.readlink(destination/'link.py'), 'source.py')
        outside = self.directory/'outside'
        outside.write_text('private fixture must not be copied')
        (self.root/'escape').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escapes the checkout'):
            materialize(self.root, self.directory/'rejected')
        self.assertFalse((self.directory/'rejected').exists())

    def test_deleted_and_file_to_directory_paths_overlay_without_stale_bytes(self):
        (self.root/'source.py').unlink()
        (self.root/'source.py').mkdir()
        (self.root/'source.py/child.py').write_text('new directory content')
        destination = self.directory/'snapshot'
        materialize(self.root, destination)
        self.assertEqual((destination/'source.py/child.py').read_text(), 'new directory content')
