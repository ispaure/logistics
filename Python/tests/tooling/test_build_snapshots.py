"""Real local repositories prove source isolation without provider credentials."""
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from logistics_build.build_snapshots import identity, materialize


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
        from mobile_build.tools import captured_source_fingerprint
        self.assertEqual(captured_source_fingerprint(destination), selected['fingerprint'])
        (destination / 'source.py').write_text('unexpected modification')
        with self.assertRaisesRegex(ValueError, 'Captured source changed'):
            captured_source_fingerprint(destination)
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

    def test_retention_pin_preserves_snapshot_identity_without_hiding_source_changes(self):
        destination = self.directory / 'pinned'
        before = materialize(self.root, destination)
        (destination / '.keep').write_text('Active native validation\n')
        self.assertEqual(materialize(self.root, destination), before)
        from logistics_build.build_snapshots import source_members
        self.assertNotIn('.keep', source_members(destination))
        (destination / 'source.py').write_text('unexpected source change')
        with self.assertRaisesRegex(ValueError, 'different source'):
            materialize(self.root, destination)

    def test_uncommitted_shared_edits_additions_deletions_and_ignored_files_are_isolated(self):
        (self.shared / '.gitignore').write_text('private/\n')
        (self.shared / 'removed.py').write_text('old')
        self.commit(self.shared)
        self.commit(self.root)
        (self.shared / 'library.py').write_text('VERSION = 2\n')
        (self.shared / 'new.py').write_text('new API')
        (self.shared / 'removed.py').unlink()
        (self.shared / 'private').mkdir()
        (self.shared / 'private/secret').write_text('synthetic secret')
        captured = identity(self.root)
        self.assertTrue(captured['dirty'])
        self.assertTrue(captured['commonUtils_dirty'])
        destination = self.directory / 'snapshot'
        materialize(self.root, destination, expected=captured)
        shared = destination / 'Python/commonUtils'
        self.assertEqual((shared / 'library.py').read_text(), 'VERSION = 2\n')
        self.assertEqual((shared / 'new.py').read_text(), 'new API')
        self.assertFalse((shared / 'removed.py').exists())
        self.assertFalse((shared / 'private').exists())
        self.assertEqual(materialize(self.root, destination), captured)
        # Later live edits neither mutate nor relabel the prepared checkout.
        (self.shared / 'library.py').write_text('VERSION = 3\n')
        self.assertEqual((shared / 'library.py').read_text(), 'VERSION = 2\n')
        self.assertNotEqual(identity(self.root)['fingerprint'], captured['fingerprint'])
        (shared / 'new.py').write_text('tampered')
        from mobile_build.tools import captured_source_fingerprint
        with self.assertRaisesRegex(ValueError, 'Captured source changed'):
            captured_source_fingerprint(destination)

    def test_shared_edits_do_not_enter_committed_selection(self):
        (self.shared / 'library.py').write_text('VERSION = 2\n')
        (self.shared / 'new.py').write_text('new API')
        destination = self.directory / 'snapshot'
        captured = materialize(self.root, destination, 'HEAD')
        self.assertFalse(captured['dirty'])
        self.assertFalse(captured['commonUtils_dirty'])
        self.assertEqual((destination / 'Python/commonUtils/library.py').read_text(), 'VERSION = 1\n')
        self.assertFalse((destination / 'Python/commonUtils/new.py').exists())

    def test_shared_source_race_and_escaping_links_are_rejected(self):
        captured = identity(self.root)
        (self.shared / 'new.py').write_text('late API')
        with self.assertRaisesRegex(ValueError, 'shared planning capture'):
            materialize(self.root, self.directory / 'late', expected=captured)
        (self.shared / 'escape').symlink_to('../../source.py')
        with self.assertRaisesRegex(ValueError, 'escapes the checkout'):
            materialize(self.root, self.directory / 'escaped')

    def test_distribution_guard_rejects_dirty_inputs_but_accepts_committed_selection(self):
        from logistics_build.build_snapshots import require_committed_source
        for source in ({'dirty': True}, {'dirty': False, 'commonUtils_dirty': True}):
            with self.assertRaisesRegex(ValueError, 'requires committed source'):
                require_committed_source(source, 'Tester build')
        require_committed_source(identity(self.root, 'HEAD'), 'Tester build')

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

    def test_private_mobile_references_do_not_break_snapshot_reuse_or_enter_transfer(self):
        from logistics_build.build_snapshots import source_members
        destination=self.directory/'mobile-snapshot'
        original=materialize(self.root,destination,'HEAD')
        (destination/'mobile_build').mkdir()
        outside=self.directory/'private-signing';outside.mkdir()
        (outside/'credential').write_text('synthetic protected data')
        (destination/'mobile_build/.android-beta').symlink_to(outside,target_is_directory=True)
        # Simulate an older cached snapshot with only directory-style ignores.
        (destination/'.git/info/exclude').write_text('.manager-source.json\n')
        with self.assertRaisesRegex(ValueError,'escapes the checkout'):identity(destination)
        self.assertEqual(materialize(self.root,destination,'HEAD'),original)
        self.assertNotIn('mobile_build/.android-beta',source_members(destination))
        self.assertEqual((outside/'credential').read_text(),'synthetic protected data')
        (destination/'source.py').write_text('unexpected edit')
        with self.assertRaisesRegex(ValueError,'different source'):materialize(self.root,destination,'HEAD')

    def test_runtime_reference_excludes_refuse_linked_git_metadata(self):
        from logistics_build.build_snapshots import exclude_private_runtime_references
        destination=self.directory/'snapshot';materialize(self.root,destination,'HEAD')
        outside=self.directory/'outside-config';outside.write_text('preserve')
        exclude=destination/'.git/info/exclude';exclude.unlink();exclude.symlink_to(outside)
        with self.assertRaisesRegex(ValueError,'metadata must not be linked'):
            exclude_private_runtime_references(destination)
        self.assertEqual(outside.read_text(),'preserve')

    def test_shared_capture_rejects_source_change_before_snapshot_creation(self):
        captured = identity(self.root)
        (self.root / 'source.py').write_text('VERSION = 3\n')
        destination = self.directory / 'changed-after-capture'
        with self.assertRaisesRegex(ValueError, 'shared planning capture'):
            materialize(self.root, destination, expected=captured)
        self.assertFalse(destination.exists())
